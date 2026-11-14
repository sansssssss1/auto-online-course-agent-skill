"""Summarize/compare captured task lists. Never accesses a browser or network."""
import argparse
import json
import sys
from pathlib import Path


def load_snapshot(filename):
    data = json.loads(Path(filename).read_text(encoding='utf-8-sig'))
    if data.get('schema_version') != 1 or not data.get('platform'):
        raise ValueError('snapshot requires schema_version=1 and platform')
    scope = data.get('scope')
    if not isinstance(scope, dict) or not all(isinstance(scope.get(key), str) and scope[key].strip()
                                              for key in ('account_alias', 'course_key', 'view')):
        raise ValueError('scope requires account_alias, course_key and view')
    items = data.get('items')
    if not isinstance(items, list):
        raise ValueError('items must be an array')
    seen = set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'].strip():
            raise ValueError('each item requires a nonempty string id')
        if item['id'] in seen:
            raise ValueError('duplicate item ids; capture stable ids before comparison')
        if not isinstance(item.get('title'), str) or not item['title'].strip():
            raise ValueError('each item requires a nonempty title')
        seen.add(item['id'])
    return data


def summary(data):
    counts = {}
    for item in data['items']:
        status = item.get('status') or 'unknown'
        counts[status] = counts.get(status, 0) + 1
    confirmed_range = data.get('authoritative') is True
    return {'platform': data['platform'], 'scope': data['scope'], 'captured_at': data.get('captured_at'),
            'observed_count': len(data['items']), 'counts': counts, 'loaded_range_confirmed': confirmed_range,
            'completion_claim': 'not-established-by-list-tool',
            'warnings': data.get('warnings', []) + ([] if confirmed_range else ['List range is unconfirmed.'])}


def compare(before, after):
    if before['platform'] != after['platform'] or before['scope'] != after['scope']:
        raise ValueError('cannot compare different platform/account/course/view scopes')
    old = {item['id']: item for item in before['items']}
    new = {item['id']: item for item in after['items']}
    fields = ('title', 'kind', 'status', 'deadline')
    changed = []
    for key in sorted(old.keys() & new.keys()):
        updates = {field: {'before': old[key].get(field), 'after': new[key].get(field)}
                   for field in fields if old[key].get(field) != new[key].get(field)}
        if updates:
            changed.append({'id': key, 'changes': updates})
    authoritative = before.get('authoritative') is True and after.get('authoritative') is True
    return {'schema_version': 1, 'platform': after['platform'], 'scope': after['scope'],
            'range_confirmed': authoritative,
            'added': [new[key] for key in sorted(new.keys() - old.keys())],
            'not_observed_now': [old[key] for key in sorted(old.keys() - new.keys())],
            'changed': changed, 'automatic_actions': [],
            'warnings': [] if authoritative else ['Partial lists: absence is not removal or completion.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    one = commands.add_parser('summary')
    one.add_argument('--input', required=True)
    two = commands.add_parser('diff')
    two.add_argument('--before', required=True)
    two.add_argument('--after', required=True)
    two.add_argument('--out')
    args = parser.parse_args(argv)
    try:
        if args.command == 'summary':
            result = summary(load_snapshot(args.input))
        else:
            result = compare(load_snapshot(args.before), load_snapshot(args.after))
            if args.out:
                output = Path(args.out)
                inputs = {Path(args.before).resolve(), Path(args.after).resolve()}
                if output.resolve() in inputs:
                    raise ValueError('output must not overwrite an input snapshot')
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
