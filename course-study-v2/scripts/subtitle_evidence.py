"""Fetch course subtitles and check an answer against their original words."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_NETWORK = 4
EXIT_LOW_CONFIDENCE = 5

TIMESTAMP = re.compile(
    r'(\d{1,3}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,3}):(\d{2}):(\d{2})[,.](\d{1,3})')
SUBTITLE_URL = re.compile(r'^https?://\S+\.srt(?:\?\S*)?$', re.IGNORECASE)
TAG = re.compile(r'<[^>]*>')
HEADERS = ('WEBVTT', 'NOTE', 'STYLE', 'REGION')


class EvidenceError(Exception):
    """A failure that maps to a documented exit code instead of a traceback."""

    def __init__(self, message, code=EXIT_INPUT):
        super().__init__(message)
        self.code = code


def decode_bytes(raw):
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def _milliseconds(groups):
    hours, minutes, seconds, fraction = groups
    fraction = str(fraction).ljust(3, '0')[:3]
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(fraction)


def parse_srt(text):
    """Parse SRT or WebVTT cues; raises ValueError when a cue has no timestamp."""
    normalized = text.replace('\ufeff', '').replace('\r\n', '\n').replace('\r', '\n')
    body = normalized.strip()
    if body.upper().startswith('WEBVTT'):
        body = body.split('\n', 1)[1] if '\n' in body else ''
    cues = []
    for block in re.split(r'\n[ \t]*\n', body):
        block_lines = [line.strip() for line in block.split('\n') if line.strip() != '']
        if not block_lines or block_lines[0].upper() in HEADERS:
            continue
        timestamp_at = None
        for position, line in enumerate(block_lines[:2]):
            if TIMESTAMP.search(line):
                timestamp_at = position
                break
        if timestamp_at is None:
            raise ValueError('subtitle block without a timestamp: ' + block_lines[0][:60])
        match = TIMESTAMP.search(block_lines[timestamp_at])
        start = _milliseconds(match.groups()[:4])
        end = _milliseconds(match.groups()[4:])
        spoken = ' '.join(TAG.sub('', line) for line in block_lines[timestamp_at + 1:]).strip()
        cues.append({'index': len(cues) + 1, 'start_ms': start, 'end_ms': end, 'text': spoken})
    if not cues:
        raise ValueError('no subtitle cues parsed')
    return cues


def parse_lines(text):
    """Treat a plain transcript as an ordered corpus; each non-empty line is one unit."""
    normalized = text.replace('\ufeff', '').replace('\r\n', '\n').replace('\r', '\n')
    cues = []
    for number, raw in enumerate(normalized.split('\n'), start=1):
        line = raw.strip()
        if line:
            cues.append({'index': len(cues) + 1, 'line': number, 'start_ms': None,
                         'end_ms': None, 'text': line})
    return cues


def load_corpus(path):
    file = Path(path)
    if not file.is_file():
        raise EvidenceError('corpus file does not exist: ' + str(file))
    raw = file.read_bytes()
    text = decode_bytes(raw)
    kind = 'srt' if file.suffix.lower() in ('.srt', '.vtt') else 'text'
    try:
        cues = parse_srt(text) if kind == 'srt' else parse_lines(text)
    except ValueError as error:
        raise EvidenceError('corpus is not readable: ' + str(error))
    if not cues:
        raise EvidenceError('corpus has no usable lines: ' + str(file))
    return {'path': str(file), 'kind': kind, 'sha256': hashlib.sha256(raw).hexdigest(), 'cues': cues}


def format_time(milliseconds):
    seconds, millis = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return '{0:02d}:{1:02d}:{2:02d}.{3:03d}'.format(hours, minutes, seconds, millis)


def describe_span(first, last=None):
    if first.get('start_ms') is None:
        line_first = first.get('line')
        line_last = last.get('line') if last else line_first
        return ('line {0}'.format(line_first) if line_last in (None, line_first)
                else 'line {0}-{1}'.format(line_first, line_last))
    end = last or first
    return '{0}-{1}'.format(format_time(first['start_ms']), format_time(end['end_ms']))


def normalize_terms(values):
    terms = []
    for value in values:
        term = value.strip()
        if not term:
            raise EvidenceError('query terms must be non-empty strings')
        if term not in terms:
            terms.append(term)
    if not terms:
        raise EvidenceError('at least one --query term is required')
    return terms


def locate(cues, terms, window, limit=1):
    """Find spans of at most `window` consecutive cues that contain every term."""
    hits = []
    for start in range(len(cues)):
        span = cues[start:start + window]
        evidence = []
        for term in terms:
            for cue in span:
                if term in cue['text']:
                    evidence.append(cue)
                    break
        if len(evidence) == len(terms):
            hits.append({'first': span[0], 'last': span[-1],
                         'text': ' '.join(cue['text'] for cue in span).strip(),
                         'terms': evidence})
            if len(hits) >= limit:
                break
    return hits


def find_report(corpus, terms, window, limit):
    hits = locate(corpus['cues'], terms, window, limit)
    return {
        'schema_version': 1, 'tool': 'subtitle_evidence', 'kind': 'find',
        'corpus': {'path': corpus['path'], 'kind': corpus['kind'],
                   'sha256': corpus['sha256'], 'cues': len(corpus['cues'])},
        'terms': terms, 'window': window, 'found': bool(hits),
        'matches': [{'text': hit['text'], 'time': describe_span(hit['first'], hit['last']),
                     'start_ms': hit['first']['start_ms'], 'end_ms': hit['last']['end_ms'],
                     'terms': [cue['text'] for cue in hit['terms']]} for hit in hits],
        'note': 'A match quotes the source; it does not decide whether the wording answers the question.',
    }


def validate_questions(payload):
    if not isinstance(payload, dict):
        raise EvidenceError('questions payload must be a JSON object')
    questions = payload.get('questions')
    if not isinstance(questions, list) or not questions:
        raise EvidenceError('questions payload needs a non-empty questions array')
    seen = set()
    for entry in questions:
        if not isinstance(entry, dict):
            raise EvidenceError('every question must be a JSON object')
        identifier = entry.get('id')
        if not isinstance(identifier, str) or not identifier.strip():
            raise EvidenceError('every question needs a non-empty id')
        if identifier in seen:
            raise EvidenceError('duplicate question id: ' + identifier)
        seen.add(identifier)
        entry['terms'] = normalize_terms(entry.get('terms') or [])
        window = entry.get('window', 2)
        if not isinstance(window, int) or isinstance(window, bool) or window < 1:
            raise EvidenceError('window must be a positive integer for ' + identifier)
        for key in ('text', 'answer'):
            if key in entry and not isinstance(entry[key], str):
                raise EvidenceError(key + ' must be a string for ' + identifier)
    return questions


def gate_report(corpus, questions, default_window):
    records = []
    for question in questions:
        terms = question['terms']
        window = question.get('window', default_window)
        hits = locate(corpus['cues'], terms, window, limit=1)
        present = [term for term in terms
                   if any(term in cue['text'] for cue in corpus['cues'])]
        missing = [term for term in terms if term not in present]
        record = {'id': question['id'], 'terms': terms, 'window': window,
                  'status': 'supported' if hits else 'unverified',
                  'decision': 'submit' if hits else 'do-not-submit',
                  'low_confidence': not hits,
                  'partial': bool(not hits and present),
                  'found_terms': present, 'missing_terms': missing,
                  'evidence': None}
        if question.get('text'):
            record['claim'] = question['text']
        if question.get('answer'):
            record['proposed_answer'] = question['answer']
        if hits:
            hit = hits[0]
            record['evidence'] = {'text': hit['text'], 'time': describe_span(hit['first'], hit['last']),
                                  'start_ms': hit['first']['start_ms'], 'end_ms': hit['last']['end_ms'],
                                  'terms': [{'term': term, 'text': cue['text']}
                                            for term, cue in zip(terms, hit['terms'])]}
        records.append(record)
    low = [record['id'] for record in records if record['low_confidence']]
    return {
        'schema_version': 1, 'tool': 'subtitle_evidence', 'kind': 'gate',
        'corpus': {'path': corpus['path'], 'kind': corpus['kind'],
                   'sha256': corpus['sha256'], 'cues': len(corpus['cues'])},
        'default_window': default_window,
        'verdict': 'supported' if not low else 'low-confidence',
        'low_confidence_ids': low, 'questions': records,
        'rule': ('Submit a semantic or judgement answer only when its words are found in the '
                 'subtitle or other original text; otherwise report low confidence instead of guessing.'),
    }


def candidate_urls(payload):
    found = []

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str):
            value = node.strip()
            if SUBTITLE_URL.match(value) and value not in found:
                found.append(value)

    walk(payload)
    return found


def download(url, timeout):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise EvidenceError('subtitle URL must be http or https: ' + url)
    request = urllib.request.Request(url, headers={'User-Agent': 'course-study-v2/subtitle-evidence'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise EvidenceError('subtitle download failed: ' + str(error), EXIT_NETWORK)


def write_atomic(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.tmp')
    temporary.write_text(text, encoding='utf-8', newline='\n')
    os.replace(str(temporary), str(target))


def read_json_argument(value, label):
    if value == '-':
        raw = sys.stdin.read()
    else:
        path = Path(value)
        if not path.is_file():
            raise EvidenceError(label + ' file does not exist: ' + str(path))
        raw = path.read_text(encoding='utf-8-sig')
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise EvidenceError(label + ' is not valid JSON: ' + str(error))


def prepare_output(value, force):
    output = Path(value)
    if output.exists() and not force:
        raise EvidenceError('output exists, pass --force to replace it: ' + str(output))
    return output


def parse_time(value):
    """Accept seconds, MM:SS, or HH:MM:SS(.mmm) and return milliseconds."""
    text = value.strip()
    if text == '':
        raise EvidenceError('empty time value')
    if ':' in text:
        parts = text.split(':')
        if len(parts) > 3:
            raise EvidenceError('time must be seconds, MM:SS or HH:MM:SS: ' + value)
        try:
            seconds = 0.0
            for part in parts:
                seconds = seconds * 60 + float(part)
        except ValueError:
            raise EvidenceError('time value is not a number: ' + value)
        return int(round(seconds * 1000))
    try:
        return int(round(float(text) * 1000))
    except ValueError:
        raise EvidenceError('time value is not a number: ' + value)


def slice_report(corpus, start_ms, end_ms):
    cues = [cue for cue in corpus['cues']
            if cue['start_ms'] is not None and start_ms <= cue['start_ms'] <= end_ms]
    return {'schema_version': 1, 'tool': 'subtitle_evidence', 'kind': 'slice',
            'corpus': {'path': corpus['path'], 'kind': corpus['kind'],
                       'sha256': corpus['sha256'], 'cues': len(corpus['cues'])},
            'from_ms': start_ms, 'to_ms': end_ms, 'count': len(cues), 'cues': cues}


def command_slice(args):
    corpus = load_corpus(args.corpus)
    start = parse_time(args.start)
    end = parse_time(args.end)
    if end < start:
        raise EvidenceError('--to must not be earlier than --from')
    report = slice_report(corpus, start, end)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif not report['cues']:
        print('NO_CUES')
    else:
        for cue in report['cues']:
            print('[{0}] {1}'.format(format_time(cue['start_ms']), cue['text']))
    return EXIT_OK


def command_find(args):
    corpus = load_corpus(args.corpus)
    terms = normalize_terms(args.query)
    report = find_report(corpus, terms, args.window, args.limit)
    if args.brief:
        if not report['matches']:
            print('NO_MATCH')
        else:
            for match in report['matches']:
                print('[{0}] {1}'.format(match['time'], match['text']))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return EXIT_OK


def brief_gate(report):
    lines = []
    for question in report['questions']:
        if question['status'] == 'supported':
            lines.append('{0} supported submit {1} | {2}'.format(
                question['id'], question['evidence']['time'], question['evidence']['text'][:90]))
        else:
            lines.append('{0} low-confidence do-not-submit missing={1} partial={2}'.format(
                question['id'], ','.join(question['missing_terms']) or '-', question['partial']))
    lines.append('VERDICT=' + report['verdict'])
    return '\n'.join(lines)


def command_gate(args):
    corpus = load_corpus(args.corpus)
    payload = read_json_argument(args.questions, 'questions')
    questions = validate_questions(payload)
    output = prepare_output(args.out, args.force) if args.out else None
    report = gate_report(corpus, questions, args.window)
    if output:
        write_atomic(output, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(brief_gate(report) if args.brief else json.dumps(report, ensure_ascii=False, indent=2))
    return EXIT_OK if report['verdict'] == 'supported' else EXIT_LOW_CONFIDENCE


def command_fetch(args):
    output = prepare_output(args.out, args.force)
    if args.url:
        url = args.url
    else:
        payload = read_json_argument(args.list, 'subtitle list')
        urls = candidate_urls(payload)
        if not urls:
            raise EvidenceError('no .srt URL found in the subtitle list payload')
        if not 0 <= args.choose < len(urls):
            raise EvidenceError('--choose is out of range; the list has {0} subtitle URL(s)'.format(len(urls)))
        url = urls[args.choose]
    raw = download(url, args.timeout)
    text = decode_bytes(raw)
    try:
        cues = parse_srt(text)
    except ValueError as error:
        raise EvidenceError('downloaded content is not readable SRT: ' + str(error))
    normalized = text.replace('\ufeff', '').replace('\r\n', '\n').replace('\r', '\n').strip() + '\n'
    write_atomic(output, normalized)
    summary = {'status': 'ok', 'tool': 'subtitle_evidence', 'kind': 'fetch',
               'out': str(output), 'cues': len(cues), 'bytes': len(raw),
               'sha256': hashlib.sha256(normalized.encode('utf-8')).hexdigest(),
               'source_url': url, 'network_used': True}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return EXIT_OK


def error(message, code):
    print(json.dumps({'status': 'error', 'tool': 'subtitle_evidence', 'error': message,
                      'exit_code': code}, ensure_ascii=False))
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)

    find = sub.add_parser('find', help='Quote the cues that contain every query term')
    find.add_argument('--corpus', required=True, help='SRT, VTT or plain-text transcript')
    find.add_argument('--query', action='append', default=[], help='Term that must appear; repeatable')
    find.add_argument('--window', type=int, default=2, help='Consecutive cues allowed between terms')
    find.add_argument('--limit', type=int, default=5, help='Stop after this many spans')
    find.add_argument('--brief', action='store_true', help='One line per match instead of full JSON')
    find.set_defaults(handler=command_find)

    slice_parser = sub.add_parser('slice', help='Print the dialogue between two timestamps')
    slice_parser.add_argument('--corpus', required=True, help='SRT or VTT transcript')
    slice_parser.add_argument('--from', dest='start', required=True, help='Start time: 158 or 02:38 or 00:02:38.599')
    slice_parser.add_argument('--to', dest='end', required=True, help='End time, same formats as --from')
    slice_parser.add_argument('--json', action='store_true', help='Print a JSON report instead of lines')
    slice_parser.set_defaults(handler=command_slice)

    gate = sub.add_parser('gate', help='Decide supported or low-confidence for each question')
    gate.add_argument('--corpus', required=True, help='SRT, VTT or plain-text transcript')
    gate.add_argument('--questions', required=True, help='JSON question file, or - for stdin')
    gate.add_argument('--window', type=int, default=2, help='Default consecutive cues allowed')
    gate.add_argument('--out', help='Write the full gate record to this new file')
    gate.add_argument('--force', action='store_true', help='Allow --out to replace an existing file')
    gate.add_argument('--brief', action='store_true', help='One line per question; --out still gets full JSON')
    gate.set_defaults(handler=command_gate)

    fetch = sub.add_parser('fetch', help='Download one SRT from a URL or a page subtitle list')
    fetch.add_argument('--out', required=True, help='New local SRT file')
    fetch.add_argument('--url', help='Direct SRT URL')
    fetch.add_argument('--list', help='Saved allsubtitle JSON (or - for stdin) to pick a URL from')
    fetch.add_argument('--choose', type=int, default=0, help='Index into the subtitle URL list')
    fetch.add_argument('--timeout', type=float, default=25.0, help='Download timeout in seconds')
    fetch.add_argument('--force', action='store_true', help='Allow --out to replace an existing file')
    fetch.set_defaults(handler=command_fetch)

    args = parser.parse_args(argv)
    if args.command == 'fetch' and bool(args.url) == bool(args.list):
        return error('fetch needs exactly one of --url or --list', EXIT_INPUT)
    if args.command in ('find', 'gate') and args.window < 1:
        return error('--window must be at least 1', EXIT_INPUT)
    if args.command == 'find' and args.limit < 1:
        return error('--limit must be at least 1', EXIT_INPUT)
    try:
        return args.handler(args)
    except EvidenceError as failure:
        return error(str(failure), failure.code)
    except OSError as failure:
        return error(str(failure), EXIT_INPUT)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
