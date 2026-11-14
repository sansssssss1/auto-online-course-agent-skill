"""Build a per-question image merge manifest from a captured question batch.

Offline, standard library only. It collects the unique image URLs (for the
download step), groups them by question without changing option order, and
emits a merge_images-compatible manifest whose local paths point at one image
directory. High-resolution defaults are baked in so the merged sheets are
readable without zooming.
"""

import argparse
import json
import os
import sys
from pathlib import Path

EXIT_INPUT = 2
DEFAULT_MIN_WIDTH = 600


class ManifestError(Exception):
    """A user-facing input error; the CLI maps it to a non-zero exit."""


def write_atomic(path, text):
    """Write text via a same-directory temp file then atomically replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(str(temporary), str(path))


def file_name(src):
    return str(src).split("/")[-1].split("?")[0]


def load_batch(path):
    path = Path(path)
    if not path.is_file():
        raise ManifestError("batch not found: " + str(path))
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ManifestError("invalid batch JSON: " + str(exc))
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        raise ManifestError("batch must contain a questions list")
    if not data["questions"]:
        raise ManifestError("batch contains no questions")
    return data


def build_manifest(batch, tag, image_dir, min_width):
    unique_urls = []
    groups = []
    downloads = []
    for question_index, question in enumerate(batch["questions"], 1):
        seen = []
        for image in question.get("images", []):
            src = image.get("src", "")
            if not src:
                continue
            if src not in seen:
                seen.append(src)
            if src not in unique_urls:
                unique_urls.append(src)
        if not seen:
            continue
        local_paths = [str(Path(image_dir) / file_name(src)) for src in seen]
        groups.append({"id": "q%d" % question_index, "images": local_paths})
    if not groups:
        raise ManifestError("batch contains no images to merge")
    for src in unique_urls:
        record = {"url": src, "filename": file_name(src)}
        downloads.append(record)
    return {
        "tag": tag,
        "image_dir": str(Path(image_dir).resolve()),
        "unique_urls": unique_urls,
        "downloads": downloads,
        "min_width": min_width,
        "groups": groups,
    }


def run(args):
    batch = load_batch(args.batch)
    out_path = Path(args.out).resolve()
    if args.image_dir:
        image_dir = Path(args.image_dir)
    else:
        image_dir = out_path.parent / ("%s-images" % args.tag)
    manifest = build_manifest(batch, args.tag, image_dir, args.min_width)
    write_atomic(out_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return {"batch": str(Path(args.batch).resolve()),
            "out": str(out_path), "image_dir": manifest["image_dir"],
            "unique_urls": len(manifest["unique_urls"]),
            "groups": len(manifest["groups"]),
            "min_width": args.min_width}


def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--batch", required=True,
                        help="Path to the captured questions-batch.json")
    parser.add_argument("--tag", required=True,
                        help="Node tag, e.g. 13-2 (names the default image dir)")
    parser.add_argument("--out", required=True, help="Output merge-manifest.json")
    parser.add_argument("--image-dir",
                        help="Local directory holding downloaded images")
    parser.add_argument("--min-width", type=int, default=DEFAULT_MIN_WIDTH,
                        help="Merged sheet content is upscaled to at least this width")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run(args)
    except ManifestError as exc:
        print("MANIFEST_ERROR: " + str(exc), file=sys.stderr)
        return EXIT_INPUT
    print(json.dumps({"status": "ok", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
