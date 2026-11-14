"""Report this skill's local capabilities without changing the environment."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import question_reader


def version(command):
    executable = shutil.which(command)
    if not executable:
        return {'available': False}
    try:
        result = subprocess.run([executable, '--version'], capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=15)
        return {'available': result.returncode == 0, 'path': executable,
                'version': (result.stdout or result.stderr).strip()[:200]}
    except (OSError, subprocess.SubprocessError) as error:
        return {'available': False, 'path': executable, 'error': str(error)}


def main():
    root = Path(__file__).resolve().parent.parent
    result = {
        'skill': 'course-study-v2', 'version': '2.0.0-preview.10',
        'python': {'path': sys.executable, 'version': sys.version.split()[0]},
        'node': version('node'), 'typst': version('typst'),
        'reader': question_reader.doctor(),
        'pdf_checks': {name: importlib.util.find_spec(name) is not None
                       for name in ('pymupdf', 'pypdf', 'reportlab')},
        'resources': {name: (root / name).is_file() for name in (
            'SKILL.md', 'adapters/zcode.md', 'adapters/codex.md', 'adapters/deepseek.md',
            'adapters/doubao.md', 'adapters/workbuddy.md', 'adapters/trae.md',
            'references/chaoxing.md', 'references/homework-flow.md', 'references/course-flow.md',
            'scripts/dsh_probe.py')},
        'browser': {'checked': False, 'reason': 'Use the current harness supported tools; no live session was opened.'},
        'notes': ['Optional OCR/document dependencies do not block DOM or screenshot workflows.',
                  'Harness browser channel is not probed here; use scripts/dsh_probe.py with the current tool list.',
                  'This reports installed files/commands, not live course compatibility.'],
        'network_used': False, 'environment_changed': False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(result['resources'].values()) else 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
