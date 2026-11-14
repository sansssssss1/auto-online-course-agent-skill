"""Merge option images into one white-background sheet per question/group.

Offline, Pillow only. The original images are never modified or deleted. Input is
either a directory of images or a JSON manifest that names explicit groups.
"""

import argparse
import json
import re
import sys
from pathlib import Path

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
ALIGN_CHOICES = ("left", "center", "right")


class MergeError(Exception):
    """A user-facing input error; the CLI maps it to a non-zero exit."""


def _resolve(base, value):
    """Resolve a manifest path relative to the manifest directory."""
    path = Path(value)
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


def load_manifest(manifest_path):
    """Return an ordered mapping {group_id: [image paths]} from a JSON file.

    Accepted shapes:
      {"groups": [{"id": "q1", "images": ["a.png", "b.png"]}, ...]}
      [{"path": "a.png", "group": "q1"}, {"path": "b.png", "group": "q1"}]
      ["a.png", "b.png"]                      # one group
    """
    manifest_path = Path(manifest_path).resolve()
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise MergeError("manifest not found: " + str(manifest_path))
    except json.JSONDecodeError as exc:
        raise MergeError("invalid JSON manifest: " + str(exc))

    base = manifest_path.parent
    groups = {}

    def add(group_id, paths):
        group_id = str(group_id)
        if group_id not in groups:
            groups[group_id] = []
        groups[group_id].extend(_resolve(base, p) for p in paths)

    if isinstance(raw, dict) and isinstance(raw.get("groups"), list):
        for index, entry in enumerate(raw["groups"]):
            if not isinstance(entry, dict):
                raise MergeError("each group entry must be an object")
            paths = entry.get("images")
            if not isinstance(paths, list) or not paths:
                raise MergeError("group %s has no images" % entry.get("id", index))
            add(entry.get("id", "group-%d" % (index + 1)), paths)
    elif isinstance(raw, list):
        explicit = [item for item in raw if isinstance(item, dict)]
        if explicit and all("path" in item for item in explicit):
            for item in explicit:
                add(item.get("group", "merged"), [item["path"]])
        elif all(isinstance(item, str) for item in raw):
            add("merged", raw)
        else:
            raise MergeError(
                "manifest list must be all strings, or objects with 'path' (optional 'group')")
    else:
        raise MergeError(
            "manifest must be {'groups': [...]} or a list of paths/objects")

    if not groups:
        raise MergeError("manifest contains no groups")
    return groups


def collect_directory(directory, group_pattern=None, default_group="merged"):
    """Group the image files inside a directory.

    Without a pattern every image lands in one group. With a regex, the first
    capture group of each filename supplies the group id.
    """
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise MergeError("input directory not found: " + str(directory))
    images = sorted(
        (p for p in directory.iterdir()
         if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda p: p.name.lower(),
    )
    if not images:
        raise MergeError("no images found in: " + str(directory))

    groups = {}
    if group_pattern:
        try:
            regex = re.compile(group_pattern)
        except re.error as exc:
            raise MergeError("invalid --group-pattern: " + str(exc))
        for path in images:
            match = regex.search(path.name)
            if not match or not match.groups():
                raise MergeError(
                    "filename does not match --group-pattern: " + path.name)
            group_id = match.group(1)
            groups.setdefault(group_id, []).append(path)
    else:
        groups[default_group] = images
    return groups


def _open_images(paths):
    """Open and validate every image, converting to RGBA for clean pasting."""
    if not paths:
        raise MergeError("a group contains no images")
    opened = []
    for path in paths:
        if not Path(path).is_file():
            raise MergeError("image not found: " + str(path))
        try:
            from PIL import Image
        except ImportError:
            raise MergeError("PIL_MISSING: install Pillow to merge images")
        try:
            image = Image.open(path)
            image.load()
        except Exception as exc:  # Pillow raises a variety of decode errors
            raise MergeError("unreadable image %s: %s" % (path, exc))
        opened.append((Path(path).name, image.convert("RGBA")))
    return opened


def _resample(image, factor):
    """Scale an RGBA image by a factor using high-quality LANCZOS."""
    from PIL import Image
    width = max(1, round(image.width * factor))
    height = max(1, round(image.height * factor))
    return image.resize((width, height), Image.LANCZOS)


def merge_group(paths, spacing=12, margin=20, align="center",
                uniform_width=None, scale=1.0, min_width=0,
                background=(255, 255, 255)):
    """Stack one group's images vertically and return the white-background sheet."""
    if align not in ALIGN_CHOICES:
        raise MergeError("align must be one of " + ",".join(ALIGN_CHOICES))
    if spacing < 0 or margin < 0:
        raise MergeError("spacing and margin must be non-negative")
    if scale < 1.0:
        raise MergeError("--scale must be >= 1")
    if min_width < 0:
        raise MergeError("--min-width must be non-negative")
    opened = _open_images(paths)

    if uniform_width:
        if uniform_width <= 0:
            raise MergeError("--uniform-width must be positive")
        resized = []
        for name, image in opened:
            factor = uniform_width / image.width
            resized.append((name, _resample(image, factor)))
        opened = resized

    # High-resolution default: widen the whole group until the content reaches
    # min_width, then apply the explicit scale, keeping relative sizes/order.
    content_width = max(image.width for _, image in opened)
    effective_scale = scale
    if min_width and content_width < min_width:
        effective_scale *= min_width / content_width
    if effective_scale != 1.0:
        opened = [(name, _resample(image, effective_scale))
                  for name, image in opened]

    content_width = max(image.width for _, image in opened)
    total_height = (
        sum(image.height for _, image in opened)
        + spacing * (len(opened) - 1)
    )
    canvas_width = content_width + margin * 2
    canvas_height = total_height + margin * 2
    try:
        from PIL import Image
    except ImportError:
        raise MergeError("PIL_MISSING: install Pillow to merge images")
    sheet = Image.new("RGBA", (canvas_width, canvas_height), background + (255,))

    y = margin
    for name, image in opened:
        if align == "left":
            x = margin
        elif align == "right":
            x = margin + content_width - image.width
        else:
            x = margin + (content_width - image.width) // 2
        sheet.alpha_composite(image, (x, y))
        y += image.height + spacing
    return sheet.convert("RGB")


def _safe_filename(group_id):
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(group_id)).strip("._")
    return name or "group"


def read_manifest_options(manifest_path):
    """Read optional high-resolution settings stored in a manifest."""
    options = {"min_width": 0, "scale": 1.0}
    try:
        raw = json.loads(Path(manifest_path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return options
    if isinstance(raw, dict):
        if isinstance(raw.get("min_width"), int) and raw["min_width"] > 0:
            options["min_width"] = raw["min_width"]
        if isinstance(raw.get("scale"), (int, float)) and raw["scale"] >= 1:
            options["scale"] = float(raw["scale"])
    return options


def run(args):
    manifest_min_width = 0
    if Path(args.input).is_dir():
        groups = collect_directory(args.input, args.group_pattern, args.group_name)
    else:
        if args.group_pattern:
            raise MergeError("--group-pattern only applies to a directory input")
        manifest_min_width = read_manifest_options(args.input)["min_width"]
        groups = load_manifest(args.input)

    # Explicit CLI min-width wins; otherwise the manifest's min-width applies.
    min_width = args.min_width if args.min_width else manifest_min_width
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if len(set(_safe_filename(gid) for gid in groups)) != len(groups):
        raise MergeError("group ids collide after filename sanitisation")

    written = []
    for group_id, paths in groups.items():
        sheet = merge_group(
            paths, spacing=args.spacing, margin=args.margin, align=args.align,
            uniform_width=args.uniform_width, scale=args.scale,
            min_width=min_width,
        )
        target = out_dir / (_safe_filename(group_id) + ".png")
        sheet.save(target)
        written.append({"group": group_id, "output": str(target),
                        "images": len(paths), "width": sheet.width,
                        "height": sheet.height})
    return written


def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", required=True,
                        help="Directory of images or a JSON manifest")
    parser.add_argument("--out", required=True,
                        help="Output directory; one merged <group>.png per group")
    parser.add_argument("--group-pattern",
                        help="Regex on filenames for directory input; first capture group is the group id")
    parser.add_argument("--group-name", default="merged",
                        help="Group id when merging a whole directory")
    parser.add_argument("--spacing", type=int, default=12,
                        help="Vertical gap in pixels between images")
    parser.add_argument("--margin", type=int, default=20,
                        help="Outer white margin in pixels")
    parser.add_argument("--align", choices=ALIGN_CHOICES, default="center",
                        help="Horizontal placement of narrower images")
    parser.add_argument("--uniform-width", type=int, default=None,
                        help="Scale every image to this width before merging")
    parser.add_argument("--scale", type=float, default=1.0,
                        help="Uniform upscale factor (>=1), high-quality LANCZOS")
    parser.add_argument("--min-width", type=int, default=0,
                        help="Upscale each sheet until content is at least this wide")
    parser.add_argument("--json", action="store_true",
                        help="Print a JSON summary instead of plain text")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        written = run(args)
    except MergeError as exc:
        print("MERGE_ERROR: " + str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"status": "ok", "sheets": written}, ensure_ascii=False,
                         indent=2))
    else:
        for item in written:
            print("%s <- %d images -> %s" %
                  (item["group"], item["images"], item["output"]))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
