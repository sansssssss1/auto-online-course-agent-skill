"""Decide whether a quiz stem was read badly, and re-crop it when it was.

The guard is the automated fallback for the case that cost a node in practice:
the whole-page OCR returns the type tag but loses the stem text. It measures the
stem, and only when the stem is short, empty or carries an unbalanced bracket does
it call crop_ocr with automatic anchors and re-OCR the crop.
"""

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_CROP = 3
EXIT_OCR = 4
EXIT_REVIEW = 5
MIN_STEM = 8
TAG = re.compile(r'^\s*\d{1,3}\s*(?:[.、．)）]\s*)?[【\[]([^】\]]*)[】\]]')


def _sibling(name):
    """Load a sibling script as a module without installing it as a package."""
    path = Path(__file__).resolve().with_name(name + '.py')
    spec = importlib.util.spec_from_file_location('_ocr_guard_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


crop_ocr = _sibling('crop_ocr')
quiz_panel = _sibling('quiz_panel')


def strip_tag(text):
    """Remove a leading number plus 【单选/多选/判断】 tag and return the stem body."""
    return TAG.sub('', (text or '').strip(), count=1).strip()


def stem_quality(text):
    """Report whether a stem line is too damaged to answer from."""
    raw = (text or '').strip()
    body = strip_tag(raw)
    reasons = []
    if not raw:
        reasons.append('empty-stem')
    if len(body) < MIN_STEM:
        reasons.append('short-stem')
    if any(body.count(left) != body.count(right) for left, right in (('【', '】'), ('[', ']'), ('（', '）'), ('(', ')'))):
        reasons.append('unbalanced-tag')
    return {'text': raw, 'body': body, 'chars': len(body),
            'suspect': bool(reasons), 'reasons': reasons}


def find_stem(lines, x_min=100.0, x_max=1100.0):
    """Return the first numbered question line inside the panel, else the first kept line."""
    kept, _dropped = quiz_panel.filter_lines(lines, x_min, x_max)
    for _y, _x, text, _confidence in kept:
        if crop_ocr.question_start(text):
            return text
    return kept[0][2] if kept else ''


def load_lines(path):
    file = Path(path)
    if not file.is_file():
        raise OSError('ocr json does not exist: ' + str(file))
    data = json.loads(file.read_text(encoding='utf-8-sig'))
    lines = data['images'][0]['lines']
    if not isinstance(lines, list):
        raise ValueError('ocr json has no lines array')
    return lines


def run(command):
    return subprocess.run(command, capture_output=True, text=True, encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('png')
    parser.add_argument('ocr_json')
    parser.add_argument('--x-min', type=float, default=100.0)
    parser.add_argument('--x-max', type=float, default=1100.0)
    parser.add_argument('--out', help='Where the re-cropped image goes')
    parser.add_argument('--dry-run', action='store_true', help='Only report the decision')
    args = parser.parse_args(argv)

    try:
        lines = load_lines(args.ocr_json)
        stem = find_stem(lines, args.x_min, args.x_max)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as failure:
        print(json.dumps({'status': 'error', 'tool': 'ocr_guard', 'error': str(failure),
                          'exit_code': EXIT_INPUT}, ensure_ascii=False))
        return EXIT_INPUT

    quality = stem_quality(stem)
    report = {'status': 'ok', 'tool': 'ocr_guard', 'kind': 'stem', 'png': args.png,
              'stem': quality['text'], 'body': quality['body'], 'chars': quality['chars'],
              'suspect': quality['suspect'], 'reasons': quality['reasons'],
              'min_stem': MIN_STEM, 'action': 'none'}
    if not quality['suspect']:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return EXIT_OK
    if args.dry_run:
        report['action'] = 'would-crop'
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return EXIT_OK

    out = args.out or str(Path(args.png).with_suffix('')) + '-stem.png'
    target = Path(out).resolve()
    if target.exists() or target in (Path(args.png).resolve(), Path(args.ocr_json).resolve()):
        report.update(action='output-refused', needs_review=True)
        print(json.dumps(report, ensure_ascii=False))
        return EXIT_INPUT
    cropper = Path(__file__).resolve().with_name('crop_ocr.py')
    crop = run([sys.executable, str(cropper), args.png, args.ocr_json, '--auto', '--json',
                '--out', out, '--x-min', str(args.x_min), '--x-max', str(args.x_max)])
    if crop.returncode != 0:
        report.update(action='crop-failed', error=(crop.stderr or '').strip()[-200:])
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return EXIT_OCR if crop.returncode == EXIT_OCR else EXIT_CROP
    report['action'] = 'cropped'
    report['crop'] = out
    # crop_ocr already performs OCR. Reuse its machine result instead of
    # starting the OCR engine a second time on the same image.
    try:
        result = json.loads(crop.stdout)
        lines = result['images'][0]['lines']
        report['reocr'] = [{'text': line['text'], 'confidence': line['confidence']} for line in lines]
        report['rechecked'] = stem_quality(find_stem(lines, 0, float('inf')))
    except (ValueError, KeyError, IndexError, TypeError):
        report.update(action='ocr-unreadable', needs_review=True)
        print(json.dumps(report, ensure_ascii=False))
        return EXIT_OCR
    report['needs_review'] = report['rechecked']['suspect']
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return EXIT_REVIEW if report['needs_review'] else EXIT_OK


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
