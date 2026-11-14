"""Build an independent install or a public export; never touches old skills."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ('SKILL.md', 'README.md', 'LICENSE', '.gitignore', 'agents', 'adapters', 'references', 'scripts', 'tests')
LOCAL_METADATA = ('homework-profile.md', 'legacy-paths.json', 'runtime.json')


def files():
    result = []
    for name in PUBLIC:
        path = ROOT / name
        candidates = [path] if path.is_file() else sorted(path.rglob('*')) if path.is_dir() else []
        for candidate in candidates:
            relative = candidate.relative_to(ROOT)
            if candidate.is_file() and '__pycache__' not in relative.parts and '.pytest_cache' not in relative.parts and candidate.suffix != '.pyc':
                if candidate.is_symlink():
                    raise ValueError('Public packages do not follow symlink resources: ' + str(relative))
                result.append((candidate, relative))
    return result


def public_scan(entries, denylist):
    findings = []
    for path, relative in entries:
        try:
            text = path.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError:
            findings.append({'path': str(relative), 'kind': 'unreviewed-binary'})
            continue
        if '\x00' in text:
            findings.append({'path': str(relative), 'kind': 'unreviewed-binary'})
            continue
        # These are only basic checks. Personal names/class/student ids require
        # an explicit local denylist and review of the exported files.
        for label, pattern in (
            ('personal-windows-path', r'[A-Za-z]:[\\/]Users[\\/](?!<|\{|\$)[A-Za-z0-9_.-]+'),
            ('phone-number', r'(?<!\d)1[3-9]\d{9}(?!\d)'),
            ('email', r'\b[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
            ('provider-secret', r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{24,})'),
        ):
            if re.search(pattern, text):
                findings.append({'path': str(relative), 'kind': label})
        placeholder = re.compile(r'^(?:<[^>]+>|\$?\{[^}]+\}|YOUR_[A-Z_]+|EXAMPLE[_A-Z0-9]*|PRIVATE|DUMMY|TEST|account-[a-z]|\d{1,4})$', re.I)
        literals = re.finditer(r'''(?i)(?<![A-Za-z0-9_-])["']?(?:password|passwd|pwd|username|student_id|api_key|apikey|client_secret|access_token|refresh_token|authorization|cookie)["']?\s*[:=]\s*["']([^"'\r\n]+)["']''', text)
        if any(not placeholder.fullmatch(match[1].strip()) for match in literals):
            findings.append({'path': str(relative), 'kind': 'credential-literal'})
        queries = re.finditer(r'''(?i)[?&](?:enc|stuenc|space_token|uid|cpi|clazzid|classid|studentid|token|signature|sign|access_token|refresh_token|ticket)=([^&\s<>"'`]+)''', text)
        if any(not placeholder.fullmatch(match[1]) for match in queries):
            findings.append({'path': str(relative), 'kind': 'private-session-url'})
        for value in denylist:
            if value in text:
                findings.append({'path': str(relative), 'kind': 'local-denylist-match'})
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('export')
    export.add_argument('--out', required=True)
    export.add_argument('--denylist', help='Local JSON array or object with values: [...]; matches never printed')
    install = sub.add_parser('install')
    install.add_argument('--target', required=True)
    install.add_argument('--include-local', action='store_true', help='Include only private location/config metadata, never credentials or profiles')
    args = parser.parse_args(argv)
    try:
        output = Path(args.out if args.command == 'export' else args.target).expanduser().resolve()
        if output == ROOT or ROOT in output.parents and not (ROOT / 'dist') in output.parents:
            raise ValueError('Choose an independent output directory, or a new directory under dist/')
        if args.command == 'install' and output.name != 'course-study-v2':
            raise ValueError('Install target must be a new course-study-v2 directory')
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise ValueError('Refusing to overwrite an existing installation or nonempty output')
        entries = files()
        denylist = []
        if args.command == 'export':
            if args.denylist:
                denylist = json.loads(Path(args.denylist).read_text(encoding='utf-8-sig'))
                if isinstance(denylist, dict):
                    denylist = denylist.get('values')
                if not isinstance(denylist, list) or any(not isinstance(v, str) or not v for v in denylist):
                    raise ValueError('denylist must be a JSON array of nonempty strings')
            findings = public_scan(entries, denylist)
            if findings:
                print(json.dumps({'status': 'blocked', 'findings': findings}, ensure_ascii=False, indent=2))
                return 2
        elif args.include_local:
            for name in LOCAL_METADATA:
                path = ROOT / 'local' / name
                if path.is_file():
                    entries.append((path, path.relative_to(ROOT)))
        output.mkdir(parents=True, exist_ok=True)
        records = []
        for source, relative in entries:
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            records.append({'path': relative.as_posix(), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
        manifest = {'skill': 'course-study-v2', 'version': '2.0.0-preview.10',
                    'kind': args.command, 'includes_private_metadata': args.command == 'install' and args.include_local,
                    'files': records,
                    'note': 'Public export excludes local/runs/profiles/validation. Basic scans do not replace manual identity/secret review. No GitHub upload.'}
        (output / 'package-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'status': 'ok', 'command': args.command, 'files': len(records),
                          'output': str(output), 'uploaded': False}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
