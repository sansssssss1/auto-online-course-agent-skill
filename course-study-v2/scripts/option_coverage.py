"""Check quiz option wording against subtitle or transcript evidence before submitting.

The precheck answers one narrow question: is this option's wording present in the
course text? For enumeration items (三创/三要素/几原则) it also looks for several
options listed in the same cue, which is the strongest signal the platform offers.
It never submits anything and never claims an option is wrong just because it is
missing: distractor options are supposed to be absent.
"""

import argparse
import json
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_REVIEW = 5

TIMESTAMP = re.compile(
    r'(\d{1,3}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(?:\d{1,3}):(\d{2}):(\d{2})[,.](\d{1,3})')
PUNCTUATION = re.compile(
    r'[\s\u3000·、，,。.；;：:！!？?（）()\[\]【】「」『』“”"\'’‘\-—…/\\|]+')
SEPARATOR = re.compile(r'[、，,；;和与及/]')
RULE = ('Coverage only says whether an option\'s words appear in the course text; it does not '
        'prove which option is correct. A cue that lists several options together is stronger '
        'evidence for exactly those options than scattered single-word hits. Missing text is a '
        'warning by default, because many correct answers are never spoken in the video; '
        '--strict turns that warning into a blocker.')


class CoverageError(Exception):
    """A failure that maps to an exit code instead of a traceback."""

    def __init__(self, message, code=EXIT_INPUT):
        super().__init__(message)
        self.code = code


def normalize(text):
    """Drop whitespace and punctuation so short Chinese options compare reliably."""
    return PUNCTUATION.sub('', text or '')


def _milliseconds(match):
    hours, minutes, seconds, fraction = match.groups()[:4]
    fraction = str(fraction).ljust(3, '0')[:3]
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(fraction)


def format_time(milliseconds):
    seconds, millis = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return '{0:02d}:{1:02d}:{2:02d}.{3:03d}'.format(hours, minutes, seconds, millis)


def parse_corpus(text):
    """Parse SRT/VTT-ish blocks or a plain transcript into ordered cues."""
    normalized = (text or '').replace('\ufeff', '').replace('\r\n', '\n').replace('\r', '\n')
    blocks = [block for block in re.split(r'\n[ \t]*\n', normalized.strip()) if block.strip()]
    cues = []
    timed = any(TIMESTAMP.search(block) for block in blocks)
    if timed:
        for block in blocks:
            lines = [line.strip() for line in block.split('\n') if line.strip()]
            stamp = next((line for line in lines if TIMESTAMP.search(line)), None)
            if stamp is None:
                continue
            match = TIMESTAMP.search(stamp)
            spoken = ' '.join(lines[lines.index(stamp) + 1:]).strip()
            if spoken:
                cues.append({'index': len(cues) + 1, 'start_ms': _milliseconds(match), 'text': spoken})
    else:
        for raw in normalized.split('\n'):
            line = raw.strip()
            if line:
                cues.append({'index': len(cues) + 1, 'start_ms': None, 'text': line})
    if not cues:
        raise CoverageError('corpus has no usable lines')
    return {'cues': cues}


def load_corpus(path):
    file = Path(path)
    if not file.is_file():
        raise CoverageError('corpus file does not exist: ' + str(file))
    raw = file.read_bytes()
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode('utf-8', errors='replace')
    return parse_corpus(text)


def option_terms(text, other_texts, low=2, high=8):
    """Distinctive fragments of one option, longest first.

    A fragment is distinctive when it does not also occur in another option, so a
    hit cannot be explained by a neighbouring answer.
    """
    whole = normalize(text)
    if len(whole) < low:
        return []
    others = [normalize(other) for other in other_texts if other]
    terms = []
    for size in range(min(high, len(whole)), low - 1, -1):
        for start in range(0, len(whole) - size + 1):
            candidate = whole[start:start + size]
            if any(candidate in other for other in others):
                continue
            if candidate not in terms:
                terms.append(candidate)
    return terms


def find_cue(corpus, term):
    """First cue containing the term, preferring a literal hit over a normalized one."""
    for cue in corpus['cues']:
        if term in cue['text']:
            return cue
    for cue in corpus['cues']:
        if term in normalize(cue['text']):
            return cue
    return None


def summarize_cue(cue):
    summary = {'index': cue['index'], 'text': cue['text']}
    summary['time'] = format_time(cue['start_ms']) if cue['start_ms'] is not None else 'line ' + str(cue['index'])
    return summary


def check_options(corpus, options):
    """Classify each option as direct / partial / missing against the corpus."""
    texts = [option['text'] for option in options]
    records = []
    for option in options:
        others = [text for text in texts if text != option['text']]
        whole = normalize(option['text'])
        terms = option_terms(option['text'], others)
        record = {'key': option['key'], 'text': option['text'], 'terms': terms[:6],
                  'coverage': 'missing', 'matched_term': None, 'cue': None}
        cue = find_cue(corpus, whole) if whole else None
        if cue is not None:
            record.update(coverage='direct', matched_term=whole, cue=summarize_cue(cue))
        else:
            for term in terms:
                cue = find_cue(corpus, term)
                if cue is not None:
                    record.update(coverage='partial', matched_term=term, cue=summarize_cue(cue))
                    break
        records.append(record)
    return records


def find_enumeration(corpus, records, window=1):
    """Find the cue that lists the most options together (三要素/三创/几原则 style)."""
    best = {'detected': False, 'listed': [], 'cue': None, 'window': window}
    cues = corpus['cues']
    for start in range(len(cues)):
        span = cues[start:start + window]
        raw = ' '.join(cue['text'] for cue in span)
        flattened = normalize(raw)
        listed = [record['key'] for record in records
                  if normalize(record['text']) and normalize(record['text']) in flattened]
        if len(listed) < 2:
            continue
        if len(listed) < 3 and not SEPARATOR.search(raw):
            continue
        if len(listed) > len(best['listed']):
            best = {'detected': True, 'listed': listed, 'window': window,
                    'cue': summarize_cue(span[0]), 'text': raw}
    return best


def validate_payload(payload):
    if not isinstance(payload, dict):
        raise CoverageError('options payload must be a JSON object')
    return normalize_payload(payload)


def normalize_payload(payload):
    """Validate an options payload and fill in stable A/B/C keys."""
    options = payload.get('options')
    if not isinstance(options, list) or not options:
        raise CoverageError('payload needs a non-empty options array')
    normalized, seen = [], set()
    for position, entry in enumerate(options):
        if not isinstance(entry, dict):
            raise CoverageError('every option must be a JSON object')
        text = entry.get('text')
        if not isinstance(text, str) or not text.strip():
            raise CoverageError('every option needs non-empty text')
        key = entry.get('key') or chr(ord('A') + position)
        if not isinstance(key, str) or not key.strip():
            raise CoverageError('option keys must be non-empty strings')
        key = key.strip()
        if key in seen:
            raise CoverageError('duplicate option key: ' + key)
        seen.add(key)
        normalized.append({'key': key, 'text': text.strip()})
    selected = payload.get('selected') or []
    if not isinstance(selected, list) or any(not isinstance(item, str) for item in selected):
        raise CoverageError('selected must be an array of option keys')
    unknown = [item for item in selected if item.strip() not in seen]
    if unknown:
        raise CoverageError('selected keys are not in options: ' + ','.join(unknown))
    window = payload.get('window', 1)
    if not isinstance(window, int) or isinstance(window, bool) or window < 1:
        raise CoverageError('window must be a positive integer')
    return {'question': payload.get('question'), 'type': payload.get('type') or 'multi',
            'selected': [item.strip() for item in selected], 'options': normalized,
            'window': window}


def check_report(corpus, payload, corpus_path=None, strict=False):
    question = validate_payload(payload)
    records = check_options(corpus, question['options'])
    enumeration = find_enumeration(corpus, records, question['window'])
    selected = question['selected']
    by_key = {record['key']: record for record in records}

    blockers, warnings = [], []
    if not selected:
        blockers.append({'code': 'no-selection',
                         'detail': 'no option is selected, so there is no answer to check'})
    gaps = []
    for key in selected:
        record = by_key[key]
        if record['coverage'] == 'missing':
            gaps.append({'code': 'selected-no-evidence', 'option': key, 'text': record['text'],
                         'detail': 'the selected wording never appears in the corpus; this is normal '
                                   'for answers that come from subject knowledge, so verify by hand'})
    if enumeration['detected']:
        listed = enumeration['listed']
        if set(selected) != set(listed):
            blockers.append({'code': 'enumeration-mismatch',
                             'missing': [key for key in listed if key not in selected],
                             'extra': [key for key in selected if key not in listed],
                             'listed': listed, 'selected': selected,
                             'detail': 'the strongest cue lists ' + ','.join(listed)
                                       + ' but the selection is ' + (','.join(selected) or 'empty')})
    if gaps:
        (blockers if strict else warnings).extend(gaps)

    advice = []
    for record in records:
        if record['coverage'] == 'missing':
            advice.append('{0} 文本在原文中没有出现（可能是干扰项，也可能视频没讲），需要时人工确认'.format(record['key']))
        elif record['coverage'] == 'partial':
            advice.append('{0} 只命中片段「{1}」，按整句再核一遍'.format(record['key'], record['matched_term']))
    if enumeration['detected']:
        advice.append('同一处并列列出：' + '、'.join(enumeration['listed']) + '；枚举题优先按这组作答')
    report = {
        'schema_version': 1, 'tool': 'option_coverage', 'kind': 'check',
        'corpus': {'path': corpus_path, 'cues': len(corpus['cues'])},
        'question': question['question'], 'type': question['type'],
        'options': records, 'enumeration': enumeration,
        'selected': selected, 'strict': strict,
        'blockers': blockers, 'warnings': warnings,
        'verdict': 'review' if blockers else 'ready',
        'advice': advice, 'rule': RULE,
        'answer_correct': None, 'requires_semantic_review': True, 'automatic_actions': [],
    }
    return report


def brief_report(report):
    lines = []
    for record in report['options']:
        cue = record['cue']['time'] if record['cue'] else '-'
        lines.append('{0} {1} {2} {3}'.format(record['key'], record['text'], record['coverage'], cue))
    enumeration = report['enumeration']
    if enumeration['detected']:
        lines.append('ENUM {0} listed={1}'.format(
            enumeration['cue']['time'], ','.join(enumeration['listed'])))
    for blocker in report['blockers']:
        lines.append('BLOCK {0} {1}'.format(blocker['code'], blocker.get('option') or blocker.get('listed')))
    for warning in report['warnings']:
        lines.append('WARN {0} {1}'.format(warning['code'], warning.get('option')))
    lines.append('VERDICT=' + report['verdict'])
    lines.append('SEMANTIC_REVIEW=required')
    return '\n'.join(lines)


def error(message, code):
    print(json.dumps({'status': 'error', 'tool': 'option_coverage', 'error': message,
                      'exit_code': code}, ensure_ascii=False))
    return code


def command_check(args):
    corpus = load_corpus(args.corpus)
    try:
        payload = json.loads(Path(args.options).read_text(encoding='utf-8-sig'))
    except OSError as failure:
        raise CoverageError('options file is not readable: ' + str(failure))
    except json.JSONDecodeError as failure:
        raise CoverageError('options file is not valid JSON: ' + str(failure))
    if args.selected:
        payload = dict(payload, selected=[item.strip() for item in args.selected.split(',') if item.strip()])
    report = check_report(corpus, payload, args.corpus, strict=args.strict)
    if args.out:
        target = Path(args.out)
        if target.resolve() in (Path(args.corpus).resolve(), Path(args.options).resolve()):
            raise CoverageError('output must not overwrite the corpus or option input')
        if target.exists() and not args.force:
            raise CoverageError('output exists, pass --force to replace it: ' + str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(brief_report(report) if args.brief else json.dumps(report, ensure_ascii=False, indent=2))
    return EXIT_OK if report['verdict'] == 'ready' else EXIT_REVIEW


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('check', help='Compare each option with the corpus before submitting')
    check.add_argument('--corpus', required=True, help='SRT, VTT or plain-text transcript')
    check.add_argument('--options', required=True, help='JSON with question/type/options and optional selected')
    check.add_argument('--selected', help='Comma-separated keys, overrides selected in the JSON')
    check.add_argument('--strict', action='store_true',
                       help='Treat a selected option with no textual support as a blocker')
    check.add_argument('--out', help='Write the full report to this new file')
    check.add_argument('--force', action='store_true', help='Allow --out to replace an existing file')
    check.add_argument('--brief', action='store_true', help='One line per option plus VERDICT')
    check.set_defaults(handler=command_check)
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except CoverageError as failure:
        return error(str(failure), failure.code)
    except OSError as failure:
        return error(str(failure), EXIT_INPUT)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
