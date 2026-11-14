"""Render a glyph comparison chart for an obfuscated cxsecret font.

Offline, fontTools + Pillow only. Each cell shows the hex codepoint label and
the glyph as the embedded font draws it, so a human can read the real character
and build a mapping JSON. The source font is never modified.
"""

import argparse
import json
import os
import sys
from pathlib import Path

EXIT_INPUT = 2
EXIT_DEPENDENCY = 3


class GlyphMapError(Exception):
    """A user-facing input error; the CLI maps it to a non-zero exit."""


def write_atomic(path, data):
    """Write bytes via a same-directory temp file then atomically replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(str(temporary), str(path))


def load_codepoints(font_path):
    """Return the sorted cmap codepoints of a font file."""
    try:
        from fontTools.ttLib import TTFont
    except ImportError as exc:
        raise GlyphMapError("FONTTOOLS_MISSING: install fontTools (%s)" % exc)
    font_path = Path(font_path)
    if not font_path.is_file():
        raise GlyphMapError("font not found: " + str(font_path))
    try:
        font = TTFont(str(font_path))
        cmap = font.getBestCmap()
    except Exception as exc:  # fontTools raises several parse errors
        raise GlyphMapError("unreadable font %s: %s" % (font_path, exc))
    if not cmap:
        raise GlyphMapError("font has no usable cmap: " + str(font_path))
    return sorted(cmap)


def _load_label_font():
    try:
        from PIL import ImageFont
    except ImportError as exc:
        raise GlyphMapError("PIL_MISSING: install Pillow (%s)" % exc)
    for candidate in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\arial.ttf"):
        try:
            return ImageFont.truetype(candidate, 16)
        except Exception:
            continue
    return ImageFont.load_default()


def render_chart(font_path, codepoints, glyph_size=60, cols=5,
                 cell_width=180, cell_height=130):
    """Render the white-background comparison chart as an RGB image."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise GlyphMapError("PIL_MISSING: install Pillow (%s)" % exc)
    if cols <= 0 or cell_width <= 0 or cell_height <= 0:
        raise GlyphMapError("cols and cell dimensions must be positive")
    secret = ImageFont.truetype(str(font_path), glyph_size)
    label_font = _load_label_font()
    rows = (len(codepoints) + cols - 1) // cols
    image = Image.new("RGB", (cols * cell_width, rows * cell_height), "white")
    draw = ImageDraw.Draw(image)
    for index, codepoint in enumerate(codepoints):
        row, col = divmod(index, cols)
        x, y = col * cell_width, row * cell_height
        draw.rectangle([x, y, x + cell_width - 2, y + cell_height - 2],
                       outline=(180, 180, 180))
        draw.text((x + 6, y + 5), hex(codepoint), fill="blue", font=label_font)
        char = chr(codepoint)
        bbox = draw.textbbox((0, 0), char, font=secret)
        glyph_w = bbox[2] - bbox[0]
        draw.text((x + (cell_width - glyph_w) / 2 - bbox[0],
                   y + 48 - bbox[1]), char, fill="black", font=secret)
    return image


def run(args):
    font_path = Path(args.font).resolve()
    codepoints = load_codepoints(font_path)
    chart = render_chart(
        font_path, codepoints, glyph_size=args.glyph_size,
        cols=args.cols, cell_width=args.cell_width,
        cell_height=args.cell_height,
    )
    out_path = Path(args.out).resolve()
    write_atomic(out_path, _png_bytes(chart))
    return {"font": str(font_path), "out": str(out_path),
            "glyphs": len(codepoints), "size": list(chart.size)}


def _png_bytes(image):
    import io
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--font", required=True,
                        help="Path to the obfuscated cxsecret font (.bin/.ttf)")
    parser.add_argument("--out", required=True,
                        help="Output glyph comparison PNG")
    parser.add_argument("--glyph-size", type=int, default=60,
                        help="Glyph render size in pixels")
    parser.add_argument("--cols", type=int, default=5,
                        help="Number of cells per row")
    parser.add_argument("--cell-width", type=int, default=180)
    parser.add_argument("--cell-height", type=int, default=130)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run(args)
    except GlyphMapError as exc:
        print("GLYPH_MAP_ERROR: " + str(exc), file=sys.stderr)
        return EXIT_INPUT
    print(json.dumps({"status": "ok", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
