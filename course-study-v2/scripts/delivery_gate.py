#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check delivery files. Usage: python delivery_gate.py MANIFEST.json [or --demo].

Derived from course-homework/references/delivery_gate.py (local, 2026-10-15).
Preserves path/role/min_bytes/pages_min/contains/not_contains/newer_than.
V2 resolves relative paths from the manifest directory, rejects empty or malformed
artifact lists, and optionally checks copy identity with sha256_equal_to.
This gate checks files; it does not establish answer accuracy or visual quality.
Exit codes: 0 PASS, 1 failed check, 2 invalid usage or manifest.
"""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


TEXT_SUFFIXES = {
    ".txt", ".md", ".typ", ".py", ".json", ".html", ".htm", ".csv", ".tsv",
    ".xml", ".log", ".tex", ".yaml", ".yml", ".js", ".mjs", ".css",
}


def validate(manifest):
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")
    claims = manifest.get("claims", [])
    if not isinstance(claims, list) or any(not isinstance(c, str) for c in claims):
        raise ValueError("claims must be a list of strings")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("artifacts must contain at least one file")
    for index, artifact in enumerate(artifacts, 1):
        prefix = f"artifacts[{index}]"
        if not isinstance(artifact, dict):
            raise ValueError(f"{prefix} must be an object")
        for key in ("path", "newer_than", "sha256_equal_to"):
            if key == "path" or key in artifact:
                value = artifact.get(key)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{prefix}.{key} must be a nonempty path")
        if artifact.get("role", "primary") not in ("primary", "source", "copy"):
            raise ValueError(f"{prefix}.role must be primary, source or copy")
        for key in ("min_bytes", "pages_min"):
            if key in artifact:
                value = artifact[key]
                if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                    raise ValueError(f"{prefix}.{key} must be an integer >= 1")
        for key in ("contains", "not_contains"):
            values = artifact.get(key, [])
            if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
                raise ValueError(f"{prefix}.{key} must be a list of nonempty strings")


def resolve(base_dir, path):
    value = Path(path).expanduser()
    return value if value.is_absolute() else base_dir / value


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


def check_one(artifact, base_dir):
    path = resolve(base_dir, artifact["path"])
    reasons = []
    try:
        if not path.is_file():
            return path, 0, [f"file missing: {path}"]
        stat = path.stat()
        size = stat.st_size
        if size < artifact.get("min_bytes", 1):
            reasons.append(f"{size} bytes < required {artifact.get('min_bytes', 1)}")
        if "newer_than" in artifact:
            source = resolve(base_dir, artifact["newer_than"])
            if not source.is_file():
                reasons.append(f"newer_than source missing: {source}")
            elif stat.st_mtime < source.stat().st_mtime - 1:
                reasons.append(f"artifact is older than source: {source}")
        if "sha256_equal_to" in artifact:
            original = resolve(base_dir, artifact["sha256_equal_to"])
            if not original.is_file():
                reasons.append(f"hash reference missing: {original}")
            elif sha256(path) != sha256(original):
                reasons.append(f"SHA-256 differs from: {original}")

        text = None
        if path.suffix.lower() == ".pdf":
            try:
                import pymupdf
                with pymupdf.open(path) as document:
                    if document.page_count < artifact.get("pages_min", 1):
                        reasons.append(f"{document.page_count} pages < required {artifact.get('pages_min', 1)}")
                    text = "".join(page.get_text() for page in document)
            except Exception as error:
                reasons.append(f"PDF parse failed (requires pymupdf): {error}")
        elif path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        elif artifact.get("contains") or artifact.get("not_contains"):
            reasons.append("keyword checks require a PDF or a supported UTF-8 text file")
        if "pages_min" in artifact and path.suffix.lower() != ".pdf":
            reasons.append("pages_min is valid only for PDF files")
        if text is not None:
            if "\ufffd" in text:
                reasons.append(f"text contains {text.count(chr(0xfffd))} replacement characters (U+FFFD)")
            for keyword in artifact.get("contains", []):
                if keyword not in text:
                    reasons.append(f"missing keyword: {keyword!r}")
            for keyword in artifact.get("not_contains", []):
                if keyword in text:
                    reasons.append(f"forbidden marker: {keyword!r}")
        return path, size, reasons
    except OSError as error:
        return path, 0, [f"file check failed: {error}"]


def run(manifest, base_dir):
    validate(manifest)
    print("delivery_gate: file evidence only; content and visual review are separate")
    for claim in manifest.get("claims", []):
        print(f"  claim: {claim}")
    failures = 0
    for index, artifact in enumerate(manifest["artifacts"], 1):
        path, size, reasons = check_one(artifact, base_dir)
        print(f"  [{index}] {'FAIL' if reasons else 'OK'} ({artifact.get('role', 'primary')}, {size:,}B) {path}")
        for reason in reasons:
            print(f"      {reason}")
        failures += bool(reasons)
    print("GATE: PASS" if not failures else f"GATE: FAIL ({failures} artifacts)")
    return 1 if failures else 0


def demo():
    """Offline smoke checks; creates and removes only its own temporary text files."""
    with tempfile.TemporaryDirectory(prefix="course_study_gate_") as temporary:
        base = Path(temporary)
        (base / "answer.txt").write_text("Reference solutions: 1/2", encoding="utf-8")
        (base / "copy.txt").write_text("Reference solutions: 1/2", encoding="utf-8")
        (base / "source.typ").write_text("source", encoding="utf-8")
        os.utime(base / "answer.txt", (1000, 1000))
        os.utime(base / "source.typ", (2000, 2000))
        cases = [
            ({"artifacts": [{"path": "missing.pdf"}]}, 1),
            ({"artifacts": [{"path": "answer.txt", "contains": ["absent"]}]}, 1),
            ({"artifacts": [{"path": "answer.txt", "newer_than": "source.typ"}]}, 1),
            ({"artifacts": [{"path": "answer.txt", "contains": ["Reference solutions"]},
                            {"path": "copy.txt", "role": "copy", "sha256_equal_to": "answer.txt"}]}, 0),
        ]
        for index, (manifest, expected) in enumerate(cases, 1):
            result = run(manifest, base)
            if result != expected:
                print(f"DEMO: FAIL case {index}")
                return 1
        try:
            validate({"artifacts": []})
        except ValueError:
            pass
        else:
            print("DEMO: FAIL empty manifest accepted")
            return 1
    print("DEMO: PASS (5 cases)")
    return 0


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--demo"]:
        return demo()
    if len(args) != 1:
        print(__doc__)
        return 2
    manifest_path = Path(args[0]).expanduser().resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        return run(manifest, manifest_path.parent)
    except (OSError, ValueError) as error:
        print(f"GATE: ERROR - {error}")
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    sys.exit(main())
