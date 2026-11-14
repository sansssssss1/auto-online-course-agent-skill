"""Decode an obfuscated question batch using a human-read glyph mapping.

Offline, standard library only. The mapping JSON is the only part a human
produces by reading the glyph chart; everything else is deterministic. The
batch is never modified; the decoded result is written atomically.
"""

import argparse
import json
import os
import sys
from pathlib import Path

EXIT_INPUT = 2


class DecodeError(Exception):
    """A user-facing input error; the CLI maps it to a non-zero exit."""


def write_atomic(path, text):
    """Write text via a same-directory temp file then atomically replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(str(temporary), str(path))


def _load_json(path, what):
    path = Path(path)
    if not path.is_file():
        raise DecodeError("%s not found: %s" % (what, path))
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise DecodeError("invalid %s JSON: %s" % (what, exc))


def normalize_mapping(raw):
    """Turn mapping keys ('0x630b'/'25355'/int) into {int codepoint: char}."""
    if not isinstance(raw, dict):
        raise DecodeError("mapping must be a JSON object {codepoint: char}")
    mapping = {}
    for key, value in raw.items():
        text = str(key).strip()
        try:
            codepoint = int(text, 16) if text.lower().startswith("0x") else int(text)
        except ValueError:
            raise DecodeError("mapping key is not a codepoint: " + str(key))
        if not isinstance(value, str) or len(value) != 1:
            raise DecodeError(
                "mapping value for %s must be a single character" % text)
        mapping[codepoint] = value
    if not mapping:
        raise DecodeError("mapping is empty")
    return mapping


def decode_text(text, mapping):
    """Replace mapped codepoints; unmapped characters pass through unchanged."""
    return "".join(mapping.get(ord(char), char) for char in text)


def runs_text(runs, mapping):
    if not isinstance(runs, list):
        raise DecodeError("each stem/option must contain a runs list")
    return decode_text("".join(run.get("text", "") for run in runs), mapping)


def decode_questions(batch, mapping):
    if not isinstance(batch, dict) or not isinstance(batch.get("questions"), list):
        raise DecodeError("batch must contain a questions list")
    if not batch["questions"]:
        raise DecodeError("batch contains no questions")
    decoded = []
    for question in batch["questions"]:
        decoded.append({
            "id": question.get("id"),
            "stem": runs_text(question.get("stem"), mapping).strip(),
            "options": [
                {"label": option.get("label"),
                 "text": runs_text(option.get("runs"), mapping).strip()}
                for option in question.get("options", [])
            ],
            "images": question.get("images", []),
        })
    return decoded


def run(args):
    batch = _load_json(args.batch, "batch")
    mapping = normalize_mapping(_load_json(args.mapping, "mapping"))
    decoded = decode_questions(batch, mapping)
    out_path = Path(args.out).resolve()
    write_atomic(out_path,
                 json.dumps(decoded, ensure_ascii=False, indent=2) + "\n")
    return {"batch": str(Path(args.batch).resolve()),
            "mapping_size": len(mapping), "out": str(out_path),
            "questions": len(decoded)}


def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--batch", required=True,
                        help="Path to the captured questions-batch.json")
    parser.add_argument("--mapping", required=True,
                        help="Path to the human-read mapping JSON")
    parser.add_argument("--out", required=True, help="Output decoded.json")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run(args)
    except DecodeError as exc:
        print("DECODE_ERROR: " + str(exc), file=sys.stderr)
        return EXIT_INPUT
    print(json.dumps({"status": "ok", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
