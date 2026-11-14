"""Read only usage counters from one explicitly selected Codex JSONL session.

No session discovery, conversation export, browser access, or quota estimates.
Pair an output probe with the model request issuing the following probe: usage
events can be persisted at tool completion, so nearest-after-output is wrong.
"""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys

CORE = ('input_tokens', 'cached_input_tokens', 'output_tokens', 'total_tokens')
OPTIONAL = ('reasoning_output_tokens', 'cache_write_input_tokens')


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Probe timestamps require an explicit timezone')
    return result


def counters(value):
    if not isinstance(value, dict):
        raise ValueError('Usage counters are unavailable')
    result = {key: value.get(key) for key in CORE + OPTIONAL}
    for key in CORE + OPTIONAL:
        item = result[key]
        if key in OPTIONAL and item is None:
            continue
        if not isinstance(item, int) or isinstance(item, bool) or item < 0:
            raise ValueError('Invalid usage counter: ' + key)
    if result['cached_input_tokens'] > result['input_tokens'] or result['total_tokens'] != result['input_tokens'] + result['output_tokens']:
        raise ValueError('Inconsistent token counters')
    if result['reasoning_output_tokens'] is not None and result['reasoning_output_tokens'] > result['output_tokens']:
        raise ValueError('Reasoning is a subset of output, not extra tokens')
    return result


def read_usage(path, thread_id):
    events, user_times = [], []
    duplicates = malformed = unavailable = resets = 0
    previous = None
    with Path(path).open(encoding='utf-8-sig') as stream:
        first = json.loads(next(stream))
        if first.get('type') != 'session_meta' or first.get('payload', {}).get('id') != thread_id:
            raise ValueError('Session identity does not match the selected thread')
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1  # A currently appended final line may be partial.
                continue
            payload = row.get('payload', {})
            if not isinstance(payload, dict):
                continue
            if ((row.get('type') == 'event_msg' and payload.get('type') == 'user_message') or
                    (row.get('type') == 'response_item' and payload.get('type') == 'message' and payload.get('role') == 'user')):
                user_times.append(row.get('timestamp'))  # Never copy message content.
            if row.get('type') != 'event_msg' or payload.get('type') != 'token_count':
                continue
            try:
                info = payload.get('info') or {}
                total = counters(info.get('total_token_usage'))
                last = counters(info.get('last_token_usage'))
                timestamp(row['timestamp'])
            except (ValueError, KeyError, TypeError):
                unavailable += 1
                continue
            if previous and all(total[key] == previous[key] for key in CORE):
                duplicates += 1
                continue
            reset = previous is not None and any(total[key] < previous[key] for key in CORE)
            resets += int(reset)
            matches = previous is None or reset or all(total[key] - previous[key] == last[key] for key in CORE)
            events.append({'timestamp': row['timestamp'], 'epoch': resets, 'cumulative': total,
                           'last': last, 'increment_matches_last': matches})
            previous = total
    return {'events': events, 'user_input_timestamps': user_times, 'duplicates': duplicates,
            'malformed_lines': malformed, 'unavailable_usage_events': unavailable, 'counter_resets': resets}


def attribute_probes(probes, usage, excluded=(), tolerance_ms=1000):
    if not isinstance(tolerance_ms, int) or not 0 <= tolerance_ms <= 5000:
        raise ValueError('Usage-event tolerance must be 0..5000 ms')
    rows, seen = [], set()
    for index, probe in enumerate(probes):
        key = (probe.get('batch'), probe.get('sequence'))
        if key in seen:
            raise ValueError('Duplicate probe identity')
        seen.add(key)
        if probe.get('kind') not in ('full', 'compact', 'sentinel'):
            raise ValueError('Unsupported probe kind')
        start, end = timestamp(probe['started_at']), timestamp(probe['ended_at'])
        if start > end:
            raise ValueError('Probe ended before it started')
        if probe['kind'] == 'sentinel':
            continue
        result = {key: probe.get(key) for key in ('batch', 'sequence', 'kind', 'started_at', 'ended_at', 'elapsed_ms', 'summary_json_bytes')}
        following = probes[index + 1] if index + 1 < len(probes) else None
        if not following or following.get('batch') != probe.get('batch'):
            rows.append({**result, 'status': 'missing-following-probe'})
            continue
        low, high = timestamp(following['started_at']), timestamp(following['ended_at'])
        if end > low:
            raise ValueError('Probe windows overlap or are out of order')
        candidates = [event for event in usage['events'] if low <= timestamp(event['timestamp']) <= high + timedelta(milliseconds=tolerance_ms)]
        confounded = probe['sequence'] in excluded or any(end < timestamp(t) <= low for t in usage['user_input_timestamps'] if t)
        result.update({'consumer_sequence': following['sequence'], 'confounded': confounded})
        if len(candidates) != 1 or not candidates[0]['increment_matches_last']:
            rows.append({**result, 'status': 'ambiguous-or-missing-usage', 'candidate_count': len(candidates)})
            continue
        event = candidates[0]
        last = event['last']
        rows.append({**result, 'status': 'confounded' if confounded else 'measured', 'usage_at': event['timestamp'],
                     'next_model_request': {**last, 'uncached_input_tokens': last['input_tokens'] - last['cached_input_tokens']}})
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', required=True, help='Explicit local Codex JSONL; never auto-discovered')
    parser.add_argument('--thread-id', required=True)
    parser.add_argument('--probes', help='JSONL of full/compact probes followed by a sentinel')
    parser.add_argument('--exclude-sequence', action='append', type=int, default=[])
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    try:
        usage = read_usage(args.session, args.thread_id)
        probes = [json.loads(line) for line in Path(args.probes).read_text(encoding='utf-8-sig').splitlines() if line.strip()] if args.probes else []
        rows = attribute_probes(probes, usage, args.exclude_sequence)
        report = {'schema_version': 1, 'thread_id': args.thread_id, 'usage_available': bool(usage['events']),
                  'usage_event_count': len(usage['events']), 'duplicates_ignored': usage['duplicates'],
                  'counter_resets': usage['counter_resets'], 'malformed_lines': usage['malformed_lines'],
                  'unavailable_usage_events': usage['unavailable_usage_events'],
                  'latest_cumulative': usage['events'][-1]['cumulative'] if usage['events'] else None,
                  'probes': rows, 'subscription_quota_saving': None,
                  'scope': 'Recorded counters for the model request consuming the prior probe output; includes agent context and response overhead. No token or billing percentage inferred.'}
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        print(json.dumps({'usage_available': report['usage_available'], 'events': report['usage_event_count'],
                          'probes': [{'sequence': r['sequence'], 'kind': r['kind'], 'status': r['status'],
                                      'uncached_input_tokens': r.get('next_model_request', {}).get('uncached_input_tokens')}
                                     for r in rows]}, ensure_ascii=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        print(json.dumps({'status': 'unavailable-or-invalid-input', 'usage_claimed': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
