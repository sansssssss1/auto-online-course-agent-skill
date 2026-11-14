"""Crop a region of a quiz screenshot by OCR line anchors, upscale, re-OCR."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

QUESTION = re.compile(r'^\s*\d{1,3}\s*(?:【|\[|[.、．)）](?!\d))')
SECTION = re.compile(r'^\s*(?:[一二三四五六七八九十]+|[ⅠⅡⅢⅣⅤ]+)\s*[、.．]')


def line_box(line):
    """Return (x0, y0, x1, y1) for an OCR line's quad box."""
    xs = [point[0] for point in line["box"]]
    ys = [point[1] for point in line["box"]]
    return min(xs), min(ys), max(xs), max(ys)


def question_start(text):
    """True when the line looks like a numbered quiz stem, e.g. '1【单选题】…'."""
    return bool(QUESTION.match(text))


def section_header(text):
    """True for '一.单选题' style part headers that end a question block."""
    return bool(SECTION.match(text))


def find_region(lines, from_text, to_text):
    """Return (start_box, end_box) for the first line containing each anchor."""
    start = None
    end = None
    for line in lines:
        text = line["text"].strip()
        box = line_box(line)
        if start is None and from_text in text:
            start = box
        elif start is not None and to_text in text:
            end = box
            break
    return start, end


def auto_region(lines, x_min=None, x_max=None):
    """Return (start_box, end_box, stem_text) for the first numbered question.

    The block runs from the first stem to the next stem or part header, so options
    below the stem stay inside the crop.
    """
    ordered = sorted(lines, key=lambda line: line_box(line)[1])
    start = None
    end = None
    stem = ""
    for line in ordered:
        text = line["text"].strip()
        box = line_box(line)
        if x_min is not None and box[0] < x_min or x_max is not None and box[0] > x_max:
            continue
        if start is None:
            if question_start(text):
                start, stem = box, text
        elif question_start(text) or section_header(text):
            end = box
            break
    return start, end, stem


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("png")
    parser.add_argument("ocr_json")
    parser.add_argument("--from-text")
    parser.add_argument("--to-text")
    parser.add_argument("--auto", action="store_true",
                        help="Find the first numbered question and end at the next stem or part header")
    parser.add_argument("--json", action="store_true", help="Return crop and OCR lines as one JSON report")
    parser.add_argument("--out", required=True)
    parser.add_argument("--x-min", type=float, default=90.0)
    parser.add_argument("--x-max", type=float, default=1160.0)
    parser.add_argument("--scale", type=float, default=2.0)
    args = parser.parse_args(argv)
    if not args.auto and (not args.from_text or not args.to_text):
        parser.error("--from-text and --to-text are required unless --auto is used")

    with open(args.ocr_json, encoding="utf-8-sig") as handle:
        data = json.load(handle)
    lines = data["images"][0]["lines"]
    if args.auto:
        start, end, stem = auto_region(lines, args.x_min, args.x_max)
        if stem and not args.json:
            print("STEM " + stem)
    else:
        start, end = find_region(lines, args.from_text, args.to_text)
    if start is None:
        print("ANCHOR_MISSING_AUTO" if args.auto else "ANCHOR_MISSING_FROM", file=sys.stderr)
        return 2
    if end is None:
        end = (0, start[3] + 400, 0, start[3] + 400)

    try:
        from PIL import Image
    except ImportError:
        print("PIL_MISSING: install Pillow to crop", file=sys.stderr)
        return 3

    top = max(0, start[1] - 8)
    bottom = end[1] - 4
    image = Image.open(args.png)
    crop = image.crop((int(args.x_min), int(top), int(min(args.x_max, image.width)), int(bottom)))
    crop = crop.resize((int(crop.width * args.scale), int(crop.height * args.scale)), Image.LANCZOS)
    crop.save(args.out)

    ocr_script = Path(__file__).resolve().with_name("quiz_ocr.py")
    proc = subprocess.run([sys.executable, str(ocr_script), args.out, "--json"],
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        print("OCR_FAIL", proc.returncode, proc.stderr[-200:], file=sys.stderr)
        return 4
    result = json.loads(proc.stdout)
    if args.json:
        print(json.dumps({'crop': args.out, 'images': result['images']}, ensure_ascii=False))
        return 0
    for line in result["images"][0]["lines"]:
        print(f"[{line['confidence']:.2f}] {line['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
