"""Probe DeepSeek Harness skill discovery and tool surface; no network, no browser."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

SKILL_NAME = 'course-study-v2'
GIT_MARKER = '.git'
# Scan order copied from the harness skill provider: lower rank wins inside one layer.
# Project roots are resolved from the session cwd; user roots come from the profile home.
ROOT_ORDER = ('project-dsh', 'project-agents', 'custom', 'user-dsh', 'user-agents')
BROWSER_PATTERN = re.compile(r'(browser|playwright|puppeteer|selenium|webdriver|devtools|cdp)')
SHA256_HEX = re.compile(r'^[0-9a-f]{64}$', re.I)
EXIT_NOT_DISCOVERED = 5
EXIT_WRONG_WINNER = 6
EXIT_DRIFT = 7
CAVEAT = ('Filesystem roots only. An embedded or runtime-registered skill with the same name '
          'could shadow this copy; the harness catalog and the loaded base directory stay authoritative.')


def project_root(cwd):
    path = Path(cwd).resolve()
    for candidate in (path, *path.parents):
        if (candidate / GIT_MARKER).exists():
            return candidate
    return path


def home_root(env_name, fallback):
    configured = os.environ.get(env_name)
    return Path(configured) if configured else Path.home() / fallback


def discovery_roots(cwd=None, dsh_home=None, agents_home=None, custom=()):
    project = project_root(cwd or os.getcwd())
    dsh = Path(dsh_home) if dsh_home else home_root('DSH_HOME', '.dsh')
    agents = Path(agents_home) if agents_home else home_root('DSH_AGENTS_HOME', '.agents')
    roots = [
        (100, 'project-dsh', project / '.dsh' / 'skills'),
        (200, 'project-agents', project / '.agents' / 'skills'),
    ]
    roots += [(300, 'custom', Path(item)) for item in custom]
    roots += [
        (400, 'user-dsh', dsh / 'skills'),
        (500, 'user-agents', agents / 'skills'),
    ]
    return [{'rank': rank, 'source': source, 'path': str(path), 'exists': Path(path).is_dir()}
            for rank, source, path in roots]


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b''):
            digest.update(chunk)
    return digest.hexdigest()


def skill_copies(roots, name=SKILL_NAME):
    copies = []
    for root in roots:
        base = Path(root['path'])
        for kind, candidate in (('bundle', base / name / 'SKILL.md'), ('flat', base / (name + '.md'))):
            if candidate.is_file():
                copies.append({'rank': root['rank'], 'source': root['source'], 'path': root['path'],
                               'kind': kind, 'skill_file': str(candidate),
                               'root_dir': str(base / name) if kind == 'bundle' else str(base),
                               'sha256': sha256_file(candidate)})
                break
    return copies


def manifest_drift(skill_dir, source_root):
    """Compare every file listed in an installed package-manifest.json with the source tree."""
    skill_dir = Path(skill_dir)
    source_root = Path(source_root)
    manifest_path = skill_dir / 'package-manifest.json'
    if not manifest_path.is_file():
        return [], None
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    except (OSError, json.JSONDecodeError):
        return [{'kind': 'manifest-unreadable', 'path': 'package-manifest.json'}], None
    if not isinstance(manifest, dict) or not isinstance(manifest.get('files'), list) or not manifest['files']:
        return [{'kind': 'manifest-invalid', 'path': 'package-manifest.json'}], None
    items, seen = [], set()
    for entry in manifest['files']:
        relative = entry.get('path') if isinstance(entry, dict) else None
        if (not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative or
                relative.startswith('/') or Path(relative).is_absolute() or '..' in Path(relative).parts):
            items.append({'kind': 'manifest-invalid-entry', 'path': 'package-manifest.json'})
            continue
        if relative in seen:
            items.append({'kind': 'manifest-duplicate-entry', 'path': relative})
            continue
        seen.add(relative)
        source = source_root / relative
        installed = skill_dir / relative
        if skill_dir.resolve() not in installed.resolve().parents or source_root.resolve() not in source.resolve().parents:
            items.append({'kind': 'manifest-outside-root', 'path': relative})
            continue
        if not installed.is_file():
            items.append({'kind': 'manifest-missing-in-install', 'path': relative})
            continue
        installed_hash = sha256_file(installed)
        recorded = entry.get('sha256') if isinstance(entry, dict) else None
        # The installed copy can check itself against the hashes recorded at
        # install time. Without this, running the probe from the install dir
        # compares the copy with itself and drift is always empty.
        if not isinstance(recorded, str) or not SHA256_HEX.fullmatch(recorded):
            items.append({'kind': 'manifest-invalid-hash', 'path': relative})
            continue
        if installed_hash != recorded.lower():
            items.append({'kind': 'manifest-hash-mismatch', 'path': relative})
            continue
        if not source.is_file():
            items.append({'kind': 'missing-in-source', 'path': relative})
        elif sha256_file(source) != installed_hash:
            items.append({'kind': 'hash-mismatch', 'path': relative})
    return items, manifest.get('version')


def source_skill(source_root=None, name=SKILL_NAME):
    root = Path(source_root) if source_root else Path(__file__).resolve().parents[1]
    path = root / 'SKILL.md'
    info = {'source_root': str(root), 'skill_file': str(path), 'exists': path.is_file()}
    if info['exists']:
        info['sha256'] = sha256_file(path)
    return info


def tool_names(payload):
    if isinstance(payload, dict):
        payload = payload.get('tools', payload.get('names'))
    if not isinstance(payload, list):
        raise ValueError('tool list must be a JSON array or an object with a tools array')
    names = []
    for entry in payload:
        name = entry.get('name') if isinstance(entry, dict) else entry
        if not isinstance(name, str) or not name.strip():
            raise ValueError('each tool entry must be a non-empty name string or an object with name')
        names.append(name.strip())
    return names


def browser_candidates(names):
    hits = []
    for name in names:
        lowered = name.lower()
        server = None
        if lowered.startswith('mcp__'):
            parts = name.split('__')
            if len(parts) >= 3:
                server = parts[1]
                subject = parts[1] + '__' + '__'.join(parts[2:])
            else:
                subject = name
        else:
            subject = name
        match = BROWSER_PATTERN.search(subject.lower())
        if not match:
            continue
        hits.append({'tool': name, 'namespace': server or 'native', 'matched': match.group(1),
                     'verified': False,
                     'note': 'Candidate only: a tool name does not prove tabs, frames, clicks or page-script write access.'})
    return hits


def build_report(cwd=None, name=SKILL_NAME, tools=None, source_root=None,
                 dsh_home=None, agents_home=None, custom=()):
    roots = discovery_roots(cwd, dsh_home, agents_home, custom)
    copies = skill_copies(roots, name)
    source = source_skill(source_root, name)
    winner = min(copies, key=lambda copy: copy['rank']) if copies else None
    source_is_installed_copy = any(
        Path(copy['root_dir']).resolve() == Path(source['source_root']).resolve() for copy in copies)
    drift = [{'source': copy['source'], 'rank': copy['rank'], 'skill_file': copy['skill_file'],
              'sha256': copy['sha256'], 'matches_source': copy.get('sha256') == source.get('sha256')}
             for copy in copies if copy.get('sha256') != source.get('sha256')]
    manifest_items = []
    for copy in copies:
        if copy['kind'] != 'bundle':
            continue
        items, version = manifest_drift(copy['root_dir'], source['source_root'])
        copy['manifest'] = {'version': version, 'drift': len(items)}
        for item in items:
            kind = item['kind'] if item['kind'].startswith('manifest-') else 'manifest-' + item['kind']
            manifest_items.append({'source': copy['source'], 'rank': copy['rank'],
                                   'skill_file': copy['skill_file'], 'kind': kind,
                                   'path': item['path']})
    if tools is None:
        surface = {'provided': False, 'count': None, 'names': [], 'browser_candidates': [],
                   'verdict': 'unknown',
                   'reason': 'No tool list was supplied; absence of a browser tool was not observed.'}
        browser_channel, live_course_work = 'unknown', 'unknown'
        delivery = ('Discovery only: no tool list was supplied, so live course work is unknown rather '
                    'than blocked. Re-run with --tools <file> to decide the browser surface.')
        next_step = ('No tool list was supplied: this run proves filesystem discovery only. Re-run with '
                     '--tools <file> (or --tools - for stdin) to check the browser surface.')
    else:
        names = tools if isinstance(tools, list) else tool_names(tools)
        hits = browser_candidates(names)
        surface = {'provided': True, 'count': len(names), 'names': names, 'browser_candidates': hits,
                   'verdict': 'candidate' if hits else 'none',
                   'reason': ('A browser-shaped tool name was found; still unverified.'
                              if hits else 'The supplied tool list exposes no browser-shaped tool.')}
        if hits:
            browser_channel, live_course_work = 'candidate', 'needs-verification'
            delivery = ('Use the candidate channel exactly as the current tool documentation describes; '
                        'verify identity, then one node.')
            next_step = 'Verify tabs, cross-frame reads, control clicks, page-script write, screenshots and downloads.'
        else:
            browser_channel, live_course_work = 'none', 'blocked'
            delivery = ('Do not drive a browser from the shell, a hidden debug port or another harness. '
                        'Enable a supported channel, then re-run this probe.')
            next_step = ('Enable a supported browser channel (for example an MCP server), re-run with the '
                         'current tool list, then verify one unfinished node.')
    report = {
        'schema_version': 1, 'skill': name, 'harness': 'deepseek-harness',
        'probe': {'network_used': False, 'browser_opened': False, 'environment_changed': False},
        'cwd': str(Path(cwd or os.getcwd())),
        'discovery': {'scope': 'filesystem-roots-only', 'caveat': CAVEAT, 'roots': roots,
                      'copies': copies, 'winner': winner, 'drift': drift,
                      'manifest_drift': manifest_items, 'source': source,
                      'source_is_installed_copy': source_is_installed_copy},
        'tools': surface,
        'capability': {
            'browser_channel': browser_channel,
            'verified': False,
            'live_course_work': live_course_work,
            'offline_work': 'available',
            'delivery': delivery,
        },
        'next': next_step,
    }
    return report


def summary(report):
    discovery = report['discovery']
    winner = discovery['winner']
    capability = report['capability']
    return {
        'status': 'ok', 'skill': report['skill'], 'harness': report['harness'],
        'project_root': str(project_root(report['cwd'])),
        'source_skill': discovery['source']['skill_file'],
        'winner': None if winner is None else {'source': winner['source'], 'rank': winner['rank'],
                                               'skill_file': winner['skill_file']},
        'drift': sorted({item['source'] for item in discovery['drift']} |
                        {item['source'] for item in discovery.get('manifest_drift', [])}),
        'manifest_drift_files': len(discovery.get('manifest_drift', [])),
        'source_is_installed_copy': discovery.get('source_is_installed_copy', False),
        'copies': len(discovery['copies']),
        'tools': {'provided': report['tools']['provided'], 'count': report['tools']['count'],
                  'verdict': report['tools']['verdict'],
                  'browser_candidates': [item['tool'] for item in report['tools']['browser_candidates']]},
        'capability': capability,
        'next': report['next'],
    }


def load_tools(value):
    if value == '-':
        return tool_names(json.loads(sys.stdin.read()))
    path = Path(value)
    if not path.is_file():
        raise ValueError('tool list file not found: ' + str(path))
    return tool_names(json.loads(path.read_text(encoding='utf-8-sig')))


def write_atomic(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    os.replace(str(temporary), str(target))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cwd', help='Session working directory used to resolve project roots')
    parser.add_argument('--name', default=SKILL_NAME, help='Skill name to look for in each root')
    parser.add_argument('--source', help='Source skill root to compare installed copies against')
    parser.add_argument('--dsh-home', help='Harness config root; defaults to DSH_HOME or ~/.dsh')
    parser.add_argument('--agents-home', help='Shared agent config root; defaults to DSH_AGENTS_HOME or ~/.agents')
    parser.add_argument('--custom-root', action='append', default=[],
                        help='Additional local skill root (rank 300); repeatable')
    parser.add_argument('--tools', help='JSON tool list file (or - for stdin) exported from the current harness')
    parser.add_argument('--out', help='Write the full report to this new file')
    parser.add_argument('--force', action='store_true', help='Allow --out to replace an existing file')
    parser.add_argument('--full', action='store_true', help='Print the full report instead of the summary')
    parser.add_argument('--allow-offline', action='store_true',
                        help='Exit 0 even when no browser channel is available; the report still says blocked')
    parser.add_argument('--require-discovered', action='store_true',
                        help='Exit 5 when no installed copy is found in the scanned roots')
    parser.add_argument('--require-winner', metavar='SKILL_DIR',
                        help='Exit 6 unless the winning copy is this skill directory (SKILL.md is appended if needed)')
    parser.add_argument('--require-clean', action='store_true', help='Exit 7 unless the winner has a valid manifest and no source/install drift')
    args = parser.parse_args(argv)
    try:
        tools = load_tools(args.tools) if args.tools else None
        report = build_report(cwd=args.cwd, name=args.name, tools=tools, source_root=args.source,
                              dsh_home=args.dsh_home, agents_home=args.agents_home,
                              custom=args.custom_root)
        if args.out:
            if Path(args.out).exists() and not args.force:
                raise ValueError('output exists, pass --force to replace it: ' + str(args.out))
            write_atomic(args.out, json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report if args.full else summary(report), ensure_ascii=False, indent=2))
        if args.require_discovered and not report['discovery']['copies']:
            print(json.dumps({'status': 'error', 'error': 'not-discovered',
                              'message': 'no installed copy was found in the scanned roots'},
                             ensure_ascii=False), file=sys.stderr)
            return EXIT_NOT_DISCOVERED
        if args.require_winner:
            expected = Path(args.require_winner).expanduser()
            if expected.name != 'SKILL.md':
                expected = expected / 'SKILL.md'
            winner = report['discovery']['winner']
            actual = winner['skill_file'] if winner else None
            if not winner or Path(actual).resolve() != expected.resolve():
                print(json.dumps({'status': 'error', 'error': 'winner-mismatch',
                                  'expected': str(expected.resolve()),
                                  'winner': actual},
                                 ensure_ascii=False), file=sys.stderr)
                return EXIT_WRONG_WINNER
        if args.require_clean:
            winner = report['discovery']['winner']
            if (not winner or 'manifest' not in winner or winner['manifest']['version'] is None or
                    report['discovery']['drift'] or report['discovery']['manifest_drift']):
                print(json.dumps({'status': 'error', 'error': 'installation-not-verified-clean'}), file=sys.stderr)
                return EXIT_DRIFT
        blocked = report['capability']['live_course_work'] == 'blocked'
        if blocked and not args.allow_offline:
            return 1
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({'status': 'error', 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
