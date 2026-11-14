#!/usr/bin/env python3
"""Render one captured question batch and optionally OCR its individual lines.

This program reads local files only. It does not acquire browser content, infer
answers, submit work, install dependencies, or download OCR models. Input format
and examples are described in the skill's reader reference.

Exit codes: 0 completed; 2 invalid input or unsafe output reuse; 3 unavailable
dependency/font/model; 4 OCR failed after usable rendered artifacts were saved.
All command results and errors are JSON on stdout; diagnostics from third-party
libraries are redirected to stderr.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import contextlib
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import unicodedata


TOOL_VERSION = "1.0.0"
EXIT_INPUT = 2
EXIT_DEPENDENCY = 3
EXIT_OCR = 4
MODEL_FILES = {
    "det_model_path": "ch_PP-OCRv3_det_infer.onnx",
    "cls_model_path": "ch_ppocr_mobile_v2.0_cls_infer.onnx",
    "rec_model_path": "ch_PP-OCRv3_rec_infer.onnx",
}


class ReaderError(Exception):
    def __init__(self, message, code=EXIT_INPUT, **details):
        super().__init__(message)
        self.code = code
        self.details = details


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def available(module):
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def font_candidates():
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = [
        windows / "msyh.ttc", windows / "msyh.ttf", windows / "simhei.ttf",
        windows / "simsun.ttc",
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    ]
    return [str(path.resolve()) for path in candidates if path.is_file()]


def local_models():
    if not available("rapidocr_onnxruntime"):
        return {"engine": "rapidocr_onnxruntime", "available": False, "reason": "package_not_installed"}
    spec = importlib.util.find_spec("rapidocr_onnxruntime")
    if not spec or not spec.origin:
        return {"engine": "rapidocr_onnxruntime", "available": False, "reason": "package_location_unknown"}
    root = Path(spec.origin).parent
    paths = {key: root / "models" / name for key, name in MODEL_FILES.items()}
    files = {key: {"path": str(path.resolve()), "exists": path.is_file(),
                   "bytes": path.stat().st_size if path.is_file() else 0}
             for key, path in paths.items()}
    return {"engine": "rapidocr_onnxruntime", "available": all(item["bytes"] > 0 for item in files.values()),
            "models": files, "downloads": False}


def doctor():
    dependencies = {name: available(name) for name in ("PIL", "fontTools", "rapidocr_onnxruntime", "onnxruntime")}
    fonts = font_candidates()
    models = local_models()
    return {"status": "ok", "tool_version": TOOL_VERSION, "dependencies": dependencies,
            "normal_font_candidates": fonts,
            "render_ready": dependencies["PIL"] and dependencies["fontTools"] and bool(fonts),
            "ocr_ready": dependencies["PIL"] and dependencies["fontTools"] and bool(fonts) and dependencies["onnxruntime"] and models["available"],
            "ocr": models, "downloads": False,
            "note": "A custom --normal-font may be used when no Chinese font was detected. Readiness checks presence; rendering/inference validates runtime usability."}


def require_dependencies():
    missing = [name for name in ("PIL", "fontTools") if not available(name)]
    if missing:
        raise ReaderError("Local rendering dependencies are missing; no installation was attempted.",
                          EXIT_DEPENDENCY, missing_dependencies=missing)


def check_id(value, description):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
        raise ReaderError(description + " must be a nonempty string or integer.")
    return str(value)


def read_input(input_path):
    try:
        raw = input_path.read_bytes()
        data = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReaderError("Cannot read the input JSON.", detail=str(exc)) from exc
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ReaderError("Input schema_version must be 1.")
    if not isinstance(data.get("batch_id"), str) or not data["batch_id"].strip():
        raise ReaderError("batch_id must be a nonempty string identifying this capture.")
    if not isinstance(data.get("source"), dict):
        raise ReaderError("source must be an object describing the captured batch.")
    if not isinstance(data.get("fonts"), list) or not isinstance(data.get("questions"), list) or not data["questions"]:
        raise ReaderError("fonts must be a list and questions must be a nonempty list.")
    return data, digest(raw)


def load_font_bytes(data, base_dir):
    fonts = {}
    for item in data["fonts"]:
        if not isinstance(item, dict):
            raise ReaderError("Each fonts entry must be an object.")
        font_id = check_id(item.get("id"), "Font id")
        if font_id == "normal" or font_id in fonts:
            raise ReaderError("Font ids must be unique and may not be 'normal'.", font_id=font_id)
        has_path = isinstance(item.get("path"), str) and bool(item["path"].strip())
        has_data = isinstance(item.get("data_base64"), str) and bool(item["data_base64"].strip())
        if has_path == has_data:
            raise ReaderError("A batch font requires exactly one of path or data_base64.", font_id=font_id)
        try:
            if has_path:
                path = Path(item["path"]).expanduser()
                path = path if path.is_absolute() else base_dir / path
                content = path.resolve().read_bytes()
                origin = str(path.resolve())
            else:
                encoded = item["data_base64"]
                if encoded.startswith("data:"):
                    prefix, encoded = encoded.split(",", 1)
                    if not prefix.endswith(";base64"):
                        raise ValueError("Only base64 font data URLs are supported")
                content = base64.b64decode(encoded, validate=True)
                origin = "inline_base64"
        except (OSError, ValueError, binascii.Error) as exc:
            raise ReaderError("Cannot read a batch font.", font_id=font_id, detail=str(exc)) from exc
        actual_sha = digest(content)
        supplied_sha = item.get("sha256")
        if supplied_sha is not None:
            if not isinstance(supplied_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", supplied_sha):
                raise ReaderError("Font sha256 must contain 64 hexadecimal characters.", font_id=font_id)
            if actual_sha != supplied_sha.lower():
                raise ReaderError("Font SHA-256 does not match this capture; do not reuse another batch's font.",
                                  font_id=font_id, expected_sha256=supplied_sha.lower(), actual_sha256=actual_sha)
        fonts[font_id] = {"data": content, "sha256": actual_sha, "origin": origin,
                          "batch_id": data["batch_id"], "hash_supplied": supplied_sha is not None}
    return fonts


def validate_runs(runs, fonts, context):
    if not isinstance(runs, list):
        raise ReaderError("Text runs must be a list.", context=context)
    for run in runs:
        if not isinstance(run, dict) or not isinstance(run.get("text"), str) or not isinstance(run.get("font"), str):
            raise ReaderError("A run requires text and font strings.", context=context)
        if run["font"] != "normal" and run["font"] not in fonts:
            raise ReaderError("A run references a font absent from this batch.", context=context, font_id=run["font"])
        capture_warnings(run, context)


def capture_warnings(item, context):
    warnings = item.get("warnings", [])
    if not isinstance(warnings, list) or any(not isinstance(warning, str) for warning in warnings):
        raise ReaderError("Capture warnings must be a list of strings.", context=context)
    return warnings


def capture_flag(item, field, context):
    if field in item and type(item[field]) is not bool:
        raise ReaderError("Capture " + field + " must be a boolean when supplied.", context=context)
    return item.get(field, False)


def image_reference(image, question_id):
    if isinstance(image, str):
        if not image.strip():
            raise ReaderError("Local question image path cannot be empty.", question_id=question_id)
        return "local", image
    if not isinstance(image, dict) or ("path" in image) == ("src" in image):
        raise ReaderError("Question image requires exactly one of local path or page-reference src.", question_id=question_id)
    if "src" in image:
        if not isinstance(image["src"], str) or image.get("requires_visual_review") is not True:
            raise ReaderError("An image src reference requires a string src and requires_visual_review:true.", question_id=question_id)
        # Empty page src values represent a missing image and remain reviewable;
        # they are never converted into local paths or fetched by this tool.
        return "reference", image["src"]
    if not isinstance(image["path"], str) or not image["path"].strip():
        raise ReaderError("Local question image requires a nonempty path.", question_id=question_id)
    return "local", image["path"]


def validate_questions(data, fonts, base_dir):
    capture_warnings(data, "batch")
    ids = set()
    for question in data["questions"]:
        if not isinstance(question, dict):
            raise ReaderError("Each question must be an object.")
        question_id = check_id(question.get("id"), "Question id")
        if question_id in ids:
            raise ReaderError("Question ids must be unique.", question_id=question_id)
        ids.add(question_id)
        capture_warnings(question, question_id)
        capture_flag(question, "needs_review", question_id)
        validate_runs(question.get("stem"), fonts, question_id + "/stem")
        if not isinstance(question.get("options"), list):
            raise ReaderError("Question options must be a list; use [] for questions without choices.", question_id=question_id)
        labels = set()
        for option in question["options"]:
            if not isinstance(option, dict) or not isinstance(option.get("label"), str) or not option["label"].strip():
                raise ReaderError("Option label must be a nonempty string.", question_id=question_id)
            if option["label"] in labels:
                raise ReaderError("Option labels must be unique within a question.", question_id=question_id)
            labels.add(option["label"])
            capture_warnings(option, question_id + "/" + option["label"])
            capture_flag(option, "needs_review", question_id + "/" + option["label"])
            capture_flag(option, "label_inferred", question_id + "/" + option["label"])
            validate_runs(option.get("runs"), fonts, question_id + "/" + option["label"])
        if not isinstance(question.get("images", []), list):
            raise ReaderError("Question images must be a list of local paths, {path, caption?}, or {src, requires_visual_review:true, caption?} objects.", question_id=question_id)
        for image in question.get("images", []):
            kind, path_text = image_reference(image, question_id)
            if isinstance(image, dict):
                if "role" in image and image["role"] not in ("stem", "option"):
                    raise ReaderError("Image role must be 'stem' or 'option' when supplied.", question_id=question_id)
                if "option_label" in image and (not isinstance(image["option_label"], str) or image["option_label"] not in labels):
                    raise ReaderError("Image option_label must match a label in this question.", question_id=question_id)
                if image.get("role") == "option" and "option_label" not in image:
                    raise ReaderError("An option image requires its valid option_label.", question_id=question_id)
            if kind == "reference":
                continue
            path = Path(path_text).expanduser()
            path = path if path.is_absolute() else base_dir / path
            if not path.is_file():
                raise ReaderError("Question image does not exist locally.", question_id=question_id, path=str(path))


def prepare_fonts(batch_fonts, normal_path, size):
    from PIL import ImageFont
    from fontTools.ttLib import TTFont

    candidates = font_candidates()
    if not normal_path and not candidates:
        raise ReaderError("No local Chinese font was found; provide --normal-font PATH. No font was downloaded.", EXIT_DEPENDENCY)
    path = Path(normal_path or candidates[0]).expanduser().resolve()
    try:
        normal_data = path.read_bytes()
    except OSError as exc:
        raise ReaderError("Cannot read --normal-font.", EXIT_DEPENDENCY, path=str(path), detail=str(exc)) from exc
    all_fonts = {"normal": {"data": normal_data, "origin": str(path), "sha256": digest(normal_data)}}
    all_fonts.update(batch_fonts)
    for font_id, item in all_fonts.items():
        try:
            item["pillow"] = ImageFont.truetype(io.BytesIO(item["data"]), size=size, index=0)
            with TTFont(io.BytesIO(item["data"]), fontNumber=0) as font:
                item["cmap"] = set((font.getBestCmap() or {}).keys())
        except Exception as exc:
            raise ReaderError("Invalid or unsupported local font.", font_id=font_id, detail=str(exc)) from exc
    return all_fonts


def fallback_missing_runs(runs, fonts):
    """Opt-in local glyph fallback; preserve text and any encoded glyph present."""
    output = []
    normal_cmap = fonts['normal']['cmap']
    for run in runs:
        chunks = []
        source_font = run['font']
        for char in run['text']:
            glyph = ord(' ') if char == '\t' else ord(char)
            fallback = (source_font != 'normal' and char not in '\r\n'
                        and glyph not in fonts[source_font]['cmap']
                        and glyph in normal_cmap)
            chosen = 'normal' if fallback else source_font
            warnings = list(run.get('warnings', []))
            if fallback:
                warnings.append('normal_font_fallback_for_missing_glyphs:' + source_font)
            if chunks and chunks[-1]['font'] == chosen and chunks[-1]['warnings'] == warnings:
                chunks[-1]['text'] += char
            else:
                chunks.append({**run, 'text': char, 'font': chosen, 'warnings': warnings})
        output.extend(chunks or [{**run, 'warnings': list(run.get('warnings', []))}])
    return output


def font_manifest(fonts):
    return {font_id: {key: item[key] for key in ("sha256", "origin", "batch_id", "hash_supplied") if key in item}
            for font_id, item in fonts.items()}


def review_reasons(text, runs, fonts, has_images=False):
    reasons = []
    if not text.strip():
        reasons.append("empty_text")
    if has_images:
        reasons.append("images_require_visual_review")
    if re.search(r"[\$\^_∫∑√∂∏∞≈≠≤≥⁰¹²³⁴⁵⁶⁷⁸⁹]|\\[([]|\\(?:frac|sqrt|begin)\b", text):
        reasons.append("formula_or_math_layout_requires_visual_review")
    if any(unicodedata.combining(char) for char in text):
        reasons.append("combining_characters_require_visual_review")
    missing = sorted({"U+%04X" % ord(char) for run in runs for char in run["text"]
                      if not char.isspace() and ord(char) not in fonts[run["font"]]["cmap"]})
    if missing:
        reasons.append("missing_font_glyphs:" + ",".join(missing[:20]))
    if any(run["font"] != "normal" and run["text"].strip() for run in runs):
        reasons.append("obfuscated_text_requires_visual_or_ocr_review")
    return reasons


def layout_lines(runs, fonts, width, padding=20):
    """Keep explicit blank lines and wrap measured characters without truncation."""
    lines, current, used = [], [], 0.0
    previous_cr = False
    for run_index, run in enumerate(runs):
        font = fonts[run["font"]]["pillow"]
        for char_index, char in enumerate(run["text"]):
            if char == "\n" and previous_cr:
                previous_cr = False
                continue
            previous_cr = char == "\r"
            if char in "\r\n":
                lines.append(current)
                current, used = [], 0.0
                continue
            visual = "    " if char == "\t" else char
            advance = max(float(font.getlength(visual)), 0.0)
            if current and used + advance > width - 2 * padding:
                lines.append(current)
                current, used = [], 0.0
            current.append({"char": char, "visual": visual, "font": run["font"], "advance": advance,
                            "run_index": run_index, "char_index": char_index})
            used += advance
    lines.append(current)
    return lines


def render_block(runs, fonts, output, prefix, width, warnings=None):
    from PIL import Image, ImageDraw

    source_text = "".join(run["text"] for run in runs)
    warnings = list(warnings or []) + [warning for run in runs for warning in run.get("warnings", [])]
    result = {"source_text": source_text, "runs": runs, "lines": [],
              "warnings": warnings, "review_reasons": review_reasons(source_text, runs, fonts)}
    if warnings:
        result["review_reasons"].append("capture_warnings_require_review")
    for index, chars in enumerate(layout_lines(runs, fonts, width)):
        used_fonts = {char["font"] for char in chars} or {"normal"}
        ascent = max(fonts[key]["pillow"].getmetrics()[0] for key in used_fonts)
        descent = max(fonts[key]["pillow"].getmetrics()[1] for key in used_fonts)
        # Account for overhanging glyphs as well as their horizontal advances.
        left_overhang = 0
        right_extent = 0.0
        x = 0.0
        for char in chars:
            box = fonts[char["font"]]["pillow"].getbbox(char["visual"], anchor="ls")
            left_overhang = min(left_overhang, math.floor(x + box[0]))
            right_extent = max(right_extent, x + box[2])
            ascent, descent = max(ascent, -box[1]), max(descent, box[3])
            x += char["advance"]
        image_width = max(48, math.ceil(max(x, right_extent) - left_overhang) + 40)
        image_height = max(48, ascent + descent + 40)
        image = Image.new("RGB", (image_width, image_height), "white")
        draw = ImageDraw.Draw(image)
        x = 20 - left_overhang
        for char in chars:
            draw.text((x, 20 + ascent), char["visual"], font=fonts[char["font"]]["pillow"], fill="black", anchor="ls")
            x += char["advance"]
        filename = f"{prefix}-line-{index + 1:04d}.png"
        image.save(output / filename)
        result["lines"].append({"index": index + 1, "image": filename, "width": image_width, "height": image_height,
                                "source_text": "".join(char["char"] for char in chars),
                                "font_ids": sorted(used_fonts),
                                "positions": [{"run_index": char["run_index"], "char_index": char["char_index"]} for char in chars],
                                "needs_review": bool(result["review_reasons"]),
                                "ocr": {"status": "not_run", "text": None, "confidence": None}})
    result["needs_review"] = bool(result["review_reasons"])
    return result


def render_option(option, option_index, fonts, output, prefix, width):
    content = render_block(option["runs"], fonts, output, prefix, width, option.get("warnings", []))
    reasons = list(content["review_reasons"])
    if option.get("needs_review", False):
        reasons.append("capture_explicit_needs_review")
    if option.get("label_inferred", False):
        reasons.append("inferred_option_label_requires_review")
    result = {"label": option["label"], "input_index": option_index, "warnings": option.get("warnings", []),
              "content": content, "review_reasons": list(dict.fromkeys(reasons)), "needs_review": bool(reasons)}
    if "label_inferred" in option:
        result["label_inferred"] = option["label_inferred"]
    return result


def render_composite(question_number, item, output, prefix, fonts):
    """Stack one question's rendered lines into one vertical image (opt-in).

    The per-line PNGs are reused unchanged; a header and option-label strips
    are drawn with the normal font. Default per-line output is not affected.
    """
    from PIL import Image, ImageDraw

    normal_font = fonts["normal"]["pillow"]

    def text_strip(text):
        probe = ImageDraw.Draw(Image.new("RGB", (4, 4)))
        bbox = probe.textbbox((0, 0), text, font=normal_font)
        width = max(bbox[2] - bbox[0] + 24, 48)
        height = max(bbox[3] - bbox[1] + 16, 40)
        strip = Image.new("RGB", (width, height), "white")
        ImageDraw.Draw(strip).text((12, 8), text, font=normal_font, fill="black")
        return strip

    strips = [text_strip("第 %d 题" % question_number)]
    for line in item["stem"]["lines"]:
        strips.append(Image.open(output / line["image"]))
    for option in item["options"]:
        strips.append(text_strip("选项 " + option["label"]))
        for line in option["content"]["lines"]:
            strips.append(Image.open(output / line["image"]))

    margin, gap = 20, 8
    width = max(im.width for im in strips) + 2 * margin
    height = sum(im.height for im in strips) + gap * (len(strips) - 1) + 2 * margin
    canvas = Image.new("RGB", (width, height), "white")
    y = margin
    for im in strips:
        canvas.paste(im, (margin, y))
        y += im.height + gap
    filename = f"{prefix}-composite.png"
    canvas.save(output / filename)
    return {"image": filename, "width": width, "height": height, "strip_count": len(strips)}


def check_output(output, identity):
    if output.exists() and not output.is_dir():
        raise ReaderError("--out must be a directory.", path=str(output))
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "reader-manifest.json"
    contents = list(output.iterdir())
    if contents:
        try:
            previous = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReaderError("Output is nonempty without a valid reader manifest; use a new directory.", path=str(output)) from exc
        if previous != identity:
            raise ReaderError("Output belongs to a different batch, input, font, or layout; use a new directory.", path=str(output))
    write_json(manifest, identity)


def image_manifest(images, base_dir):
    result = []
    for image in images:
        kind, text = image_reference(image, "image_manifest")
        if kind == "reference":
            item = {"src": text, "reference_only": True, "fetched": False,
                    "acquisition_status": "not_attempted", "requires_visual_review": True, "needs_review": True}
        else:
            path = Path(text).expanduser()
            path = (path if path.is_absolute() else base_dir / path).resolve()
            item = {"path": str(path), "sha256": digest(path.read_bytes()), "reference_only": False, "needs_review": True}
        if isinstance(image, dict) and isinstance(image.get("caption"), str):
            item["caption"] = image["caption"]
        if isinstance(image, dict):
            for field in ("role", "option_label", "image_index"):
                if field in image:
                    item[field] = image[field]
        result.append(item)
    return result


def start_ocr():
    info = local_models()
    if not info["available"] or not available("onnxruntime"):
        raise ReaderError("Local RapidOCR package/models are unavailable; rendered line images remain usable. No download was attempted.",
                          EXIT_DEPENDENCY, ocr=info)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            from rapidocr_onnxruntime import RapidOCR
            paths = {key: item["path"] for key, item in info["models"].items()}
            # Explicit local model paths and line mode avoid network fetching and
            # whole-page detection; the package's defaults are not relied upon.
            engine = RapidOCR(**paths, use_text_det=False, use_angle_cls=False,
                              print_verbose=False, text_score=0.0)
    except Exception as exc:
        raise ReaderError("Local OCR initialization failed; rendered line images remain usable.", EXIT_OCR, detail=str(exc)) from exc
    return engine


def apply_ocr(result, output, threshold):
    engine = start_ocr()
    for question in result["questions"]:
        blocks = [question["stem"]] + [option["content"] for option in question["options"]]
        for block in blocks:
            block["review_reasons"].append("ocr_output_requires_visual_review")
            block["needs_review"] = True
            for line in block["lines"]:
                if not line["source_text"].strip():
                    line["ocr"] = {"status": "blank", "text": "", "confidence": None, "engine": "rapidocr_onnxruntime"}
                    continue
                try:
                    with contextlib.redirect_stdout(sys.stderr):
                        recognized, _ = engine(str(output / line["image"]))
                    fragments = [{"text": str(item[1]), "confidence": float(item[2])} for item in (recognized or [])]
                    if any(not math.isfinite(item["confidence"]) or not 0 <= item["confidence"] <= 1 for item in fragments):
                        raise ValueError("OCR returned an invalid confidence")
                    text = " ".join(item["text"] for item in fragments)
                    confidence = min((item["confidence"] for item in fragments), default=None)
                    line["ocr"] = {"status": "ok" if text else "empty", "text": text, "confidence": confidence,
                                   "fragments": fragments, "engine": "rapidocr_onnxruntime"}
                    line["needs_review"] = True
                    if not text:
                        block["review_reasons"].append("ocr_empty_result")
                    elif confidence < threshold:
                        block["review_reasons"].append("ocr_below_confidence_threshold")
                except Exception as exc:
                    line["ocr"] = {"status": "error", "text": None, "confidence": None, "detail": str(exc)}
                    line["needs_review"] = True
                    block["review_reasons"].append("ocr_runtime_error")
                    result["status"] = "ocr_error"
            block["review_reasons"] = list(dict.fromkeys(block["review_reasons"]))
        for option in question["options"]:
            option["review_reasons"] = list(dict.fromkeys(option["review_reasons"] + option["content"]["review_reasons"]))
            option["needs_review"] = option["needs_review"] or option["content"]["needs_review"]
        question["needs_review"] = True
    result["needs_review"] = True
    if result["status"] == "ocr_error":
        raise ReaderError("OCR failed for one or more lines; see result.json and retained line images.", EXIT_OCR)


def run(args):
    require_dependencies()
    input_path = Path(args.input).expanduser().resolve()
    output = Path(args.out).expanduser().resolve()
    data, input_sha = read_input(input_path)
    batch_fonts = load_font_bytes(data, input_path.parent)
    validate_questions(data, batch_fonts, input_path.parent)
    fonts = prepare_fonts(batch_fonts, args.normal_font, args.font_size)
    identity = {"schema_version": 1, "tool_version": TOOL_VERSION, "batch_id": data["batch_id"],
                "input_sha256": input_sha, "font_sha256": {key: value["sha256"] for key, value in fonts.items()},
                "max_width": args.max_width, "font_size": args.font_size}
    if getattr(args, 'fallback_missing_glyphs', False):
        identity['fallback_missing_glyphs'] = True
        for question in data['questions']:
            question['stem'] = fallback_missing_runs(question['stem'], fonts)
            for option in question['options']:
                option['runs'] = fallback_missing_runs(option['runs'], fonts)
    # Acquire an exclusive local writer before inspecting or creating artifacts.
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output.parent / (output.name + ".question-reader.lock")
    try:
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ReaderError("Another reader may be writing this output. If no process is running, inspect and remove the stale lock.",
                          path=str(lock_path)) from exc
    try:
        os.write(lock_fd, str(os.getpid()).encode("ascii"))
        os.close(lock_fd)
        check_output(output, identity)
        result = {"schema_version": 1, "tool_version": TOOL_VERSION, "status": "rendered", "batch_id": data["batch_id"],
                  "input_sha256": input_sha, "source": data["source"], "fonts": font_manifest(fonts),
                  "output_dir": str(output), "questions": [], "warnings": data.get("warnings", []), "needs_review": False,
                  "note": "Font ids bind only to this input batch. OCR confidence is not correctness; inspect images/formulas and option labels before use."}
        if getattr(args, 'fallback_missing_glyphs', False):
            result['fallback_missing_glyphs'] = True
        for index, question in enumerate(data["questions"]):
            prefix = f"q-{index + 1:04d}"
            stem = render_block(question["stem"], fonts, output, prefix + "-stem", args.max_width)
            options = [render_option(option, option_index, fonts, output,
                                     prefix + f"-option-{option_index + 1:04d}", args.max_width)
                       for option_index, option in enumerate(question["options"])]
            images = image_manifest(question.get("images", []), input_path.parent)
            warning_review = bool(data.get("warnings")) or bool(question.get("warnings"))
            reasons = ["images_require_visual_review"] if images else []
            if warning_review:
                reasons.append("capture_warnings_require_review")
            if question.get("needs_review", False):
                reasons.append("capture_explicit_needs_review")
            if any(option["needs_review"] for option in options):
                reasons.append("option_requires_review")
            item = {"id": question["id"], "input_index": index, "stem": stem, "options": options, "images": images,
                    "warnings": question.get("warnings", []), "review_reasons": reasons,
                    "needs_review": bool(reasons) or stem["needs_review"]}
            if getattr(args, "composite", None) == "per-question":
                item["composite"] = render_composite(index + 1, item, output, prefix, fonts)
            result["questions"].append(item)
        result["needs_review"] = bool(result["warnings"]) or any(question["needs_review"] for question in result["questions"])
        result_path = output / "result.json"
        write_json(result_path, result)
        if args.command == "ocr":
            result["confidence_threshold"] = args.confidence_threshold
            try:
                apply_ocr(result, output, args.confidence_threshold)
                result["status"] = "ocr_complete"
            except ReaderError as exc:
                result["status"] = "ocr_unavailable" if exc.code == EXIT_DEPENDENCY else "ocr_error"
                result["needs_review"] = True
                result["ocr_error"] = {"message": str(exc), **exc.details}
                write_json(result_path, result)
                raise ReaderError(str(exc), exc.code, result_path=str(result_path), output_dir=str(output), **exc.details) from exc
            write_json(result_path, result)
        return {"status": result["status"], "batch_id": result["batch_id"], "result_path": str(result_path),
                "output_dir": str(output), "question_count": len(result["questions"]), "needs_review": result["needs_review"]}
    finally:
        lock_path.unlink(missing_ok=True)


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ReaderError(message)


def main(argv=None):
    parser = JsonArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check local dependencies, fonts and packaged models without downloads")
    for name in ("render", "ocr"):
        sub = commands.add_parser(name, help="Render a captured local batch" + (" and OCR its lines" if name == "ocr" else ""))
        sub.add_argument("--input", required=True, help="UTF-8 input batch JSON")
        sub.add_argument("--out", required=True, help="Batch-specific output directory")
        sub.add_argument("--normal-font", help="Local regular Chinese font; relative to the current working directory")
        sub.add_argument("--fallback-missing-glyphs", action="store_true",
                         help="Opt in to normal-font fallback for glyphs absent from a captured subset; retain review warnings")
        sub.add_argument("--composite", choices=["per-question"], default=None,
                         help="Also emit one vertical composite image per question; per-line output and default behavior are unchanged")
        sub.add_argument("--font-size", type=int, default=38)
        sub.add_argument("--max-width", type=int, default=1440, help="Maximum target line width in pixels, including margins")
        sub.add_argument("--confidence-threshold", type=float, default=0.90, help="Flag OCR below this confidence; OCR still requires visual review")
    try:
        args = parser.parse_args(argv)
        if args.command != "doctor":
            if not 12 <= args.font_size <= 128 or not 100 <= args.max_width <= 8192:
                raise ReaderError("font-size must be 12..128; max-width must be 100..8192.")
            if not math.isfinite(args.confidence_threshold) or not 0 <= args.confidence_threshold <= 1:
                raise ReaderError("confidence-threshold must be between 0 and 1.")
        result = doctor() if args.command == "doctor" else run(args)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except ReaderError as exc:
        print(json.dumps({"status": "error", "exit_code": exc.code, "message": str(exc), **exc.details}, ensure_ascii=False))
        return exc.code
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "error", "exit_code": EXIT_INPUT, "message": str(exc)}, ensure_ascii=False))
        return EXIT_INPUT
    except ImportError as exc:
        print(json.dumps({"status": "error", "exit_code": EXIT_DEPENDENCY,
                          "message": "A local dependency could not be imported; no installation was attempted.", "detail": str(exc)}, ensure_ascii=False))
        return EXIT_DEPENDENCY
    except Exception as exc:
        print(json.dumps({"status": "error", "exit_code": EXIT_INPUT,
                          "message": "Local reader failed.", "detail": str(exc)}, ensure_ascii=False))
        return EXIT_INPUT


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
