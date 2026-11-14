"""Compress quiz OCR output: keep only the question panel, drop TOC/chat chrome."""

import argparse
import json
import sys


def line_box(line):
    """Return (x0, y0, x1, y1) for an OCR line's quad box."""
    xs = [point[0] for point in line["box"]]
    ys = [point[1] for point in line["box"]]
    return min(xs), min(ys), max(xs), max(ys)


def filter_lines(lines, x_min=300.0, x_max=1150.0, y_min=0.0):
    """Split lines into (kept, dropped) by panel geometry, kept sorted top-to-bottom."""
    kept, dropped = [], []
    for line in lines:
        x0, y0, x1, _y1 = line_box(line)
        text = line["text"].strip()
        if x0 >= x_min and x1 <= x_max and y0 >= y_min:
            kept.append((y0, x0, text, line["confidence"]))
        else:
            dropped.append((x0, y0, text))
    kept.sort()
    return kept, dropped


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ocr_json")
    parser.add_argument("--x-min", type=float, default=300.0)
    parser.add_argument("--x-max", type=float, default=1150.0)
    parser.add_argument("--y-min", type=float, default=0.0)
    parser.add_argument("--show-dropped", action="store_true")
    args = parser.parse_args(argv)

    with open(args.ocr_json, encoding="utf-8-sig") as handle:
        data = json.load(handle)
    lines = data["images"][0]["lines"]
    kept, dropped = filter_lines(lines, args.x_min, args.x_max, args.y_min)

    text = " ".join(item[2] for item in kept if item[2])
    print("KEPT", len(kept), "DROPPED", len(dropped))
    print(text)
    if args.show_dropped:
        for x0, y0, dropped_text in dropped[:40]:
            print("DROP x=%.0f y=%.0f %s" % (x0, y0, dropped_text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
