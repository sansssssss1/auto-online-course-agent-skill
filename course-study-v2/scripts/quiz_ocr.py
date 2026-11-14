"""Decode a quiz screenshot locally with RapidOCR; return text and confidence only."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_DEPENDENCY = 3
EXIT_OCR = 4

DEPENDENCY = 'rapidocr_onnxruntime'


class OcrError(Exception):
    """A failure that maps to a documented exit code instead of a traceback."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def available():
    """Report whether the optional OCR dependency can be imported."""
    return importlib.util.find_spec(DEPENDENCY) is not None


def load_engine():
    """Start RapidOCR once; model loading is slow, so callers reuse the engine."""
    if not available():
        raise OcrError('OCR dependency is not installed: ' + DEPENDENCY, EXIT_DEPENDENCY)
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as error:
        raise OcrError('OCR dependency failed to import: ' + str(error), EXIT_DEPENDENCY)
    try:
        return RapidOCR()
    except Exception as error:  # missing models or broken onnx runtime
        raise OcrError('OCR engine failed to start: ' + str(error), EXIT_DEPENDENCY)


def normalize_box(value):
    """Turn a detector box into rounded floats so the record stays JSON-safe."""
    try:
        return [[round(float(point[0]), 1), round(float(point[1]), 1)] for point in value]
    except (IndexError, TypeError, ValueError):
        return None


def normalize_confidence(value):
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def decode_image(engine, image, threshold):
    """Run the engine on one already-captured screenshot and keep its reading order."""
    try:
        result, _ = engine(str(image))
    except Exception as error:  # the OCR runtime reports failures as exceptions only
        raise OcrError('OCR failed on {0}: {1}'.format(image, error), EXIT_OCR)
    lines = []
    for row in result or []:
        if not isinstance(row, (list, tuple)):
            continue
        try:
            text = str(row[1])
        except (IndexError, TypeError):
            continue
        if text.strip() == '':
            continue
        confidence = normalize_confidence(row[2]) if len(row) > 2 else None
        lines.append({
            'index': len(lines),
            'text': text,
            'confidence': confidence,
            'low_confidence': confidence is not None and confidence < threshold,
            'box': normalize_box(row[0]) if row else None,
        })
    scores = [line['confidence'] for line in lines if line['confidence'] is not None]
    return {
        'path': str(image),
        'line_count': len(lines),
        'low_confidence_lines': sum(1 for line in lines if line['low_confidence']),
        'mean_confidence': round(sum(scores) / len(scores), 4) if scores else None,
        'lines': lines,
    }


def build_result(engine, images, threshold):
    decoded = [decode_image(engine, image, threshold) for image in images]
    return {
        'schema_version': 1,
        'tool': 'quiz_ocr',
        'engine': 'RapidOCR',
        'min_confidence': threshold,
        'status': 'ok' if any(item['line_count'] for item in decoded) else 'empty',
        'lines': sum(item['line_count'] for item in decoded),
        'images': decoded,
        'note': 'OCR reads the page text; it does not choose an option or prove a score.',
    }


def format_text(result):
    out = []
    for item in result['images']:
        if len(result['images']) > 1:
            out.append('# ' + item['path'])
        for line in item['lines']:
            label = '?' if line['confidence'] is None else '{0:.2f}'.format(line['confidence'])
            flag = ' !' if line['low_confidence'] else ''
            out.append('{0}\t{1}{2}'.format(label, line['text'], flag))
    return '\n'.join(out)


def write_atomic(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(target)


def error(message, code):
    print(json.dumps({'status': 'error', 'tool': 'quiz_ocr', 'error': message,
                      'exit_code': code}, ensure_ascii=False))
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='+', help='Screenshot files captured from the quiz view')
    parser.add_argument('--min-confidence', type=float, default=0.80,
                        help='Flag decoded lines below this confidence (default 0.80)')
    parser.add_argument('--out', help='Write the full JSON record to this new file')
    parser.add_argument('--force', action='store_true', help='Allow --out to replace an existing file')
    parser.add_argument('--json', action='store_true', help='Print the JSON record instead of text lines')
    args = parser.parse_args(argv)
    if not 0.0 <= args.min_confidence <= 1.0:
        return error('--min-confidence must be between 0 and 1', EXIT_INPUT)
    images = [Path(value) for value in args.images]
    missing = [str(image) for image in images if not image.is_file()]
    if missing:
        return error('screenshot does not exist: ' + ', '.join(missing), EXIT_INPUT)
    output = Path(args.out) if args.out else None
    if output and output.exists() and not args.force:
        return error('output exists, pass --force to replace it: ' + str(output), EXIT_INPUT)
    try:
        engine = load_engine()
        result = build_result(engine, images, args.min_confidence)
        if output:
            write_atomic(output, json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else format_text(result))
        return EXIT_OK
    except OcrError as failure:
        return error(str(failure), failure.code)
    except OSError as failure:
        return error(str(failure), EXIT_INPUT)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
