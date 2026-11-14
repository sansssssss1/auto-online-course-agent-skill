"""Offline behavior tests using temporary synthetic fonts/text only."""

import base64
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "question_reader.py"
SPEC = importlib.util.spec_from_file_location("question_reader", SCRIPT)
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)


def synthetic_font(path, variant=False):
    """Make test glyphs locally; no system/course fonts or downloads are used."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    builder = FontBuilder(1000, isTTF=True)
    chars = list(range(32, 127)) + [0x4E00, 0xE001]
    names = [".notdef"] + [f"g{codepoint:04x}" for codepoint in chars]
    builder.setupGlyphOrder(names)
    glyphs = {}
    metrics = {}
    for index, name in enumerate(names):
        pen = TTGlyphPen(None)
        if name != "g0020":
            start = 70 + (20 if variant else 0)
            pen.moveTo((start, 0))
            pen.lineTo((500, 0))
            pen.lineTo((400 if index % 2 else 500, 650))
            pen.lineTo((start, 650))
            pen.closePath()
        glyphs[name] = pen.glyph()
        metrics[name] = (600, 0)
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupCharacterMap({codepoint: f"g{codepoint:04x}" for codepoint in chars})
    builder.setupNameTable({"familyName": "ReaderSynthetic", "styleName": "Regular", "uniqueFontIdentifier": "ReaderSynthetic2" if variant else "ReaderSynthetic1",
                            "fullName": "ReaderSynthetic Regular", "psName": "ReaderSynthetic-Regular"})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    builder.setupMaxp()
    builder.save(path)


@unittest.skipUnless(reader.available("PIL") and reader.available("fontTools"), "Rendering dependencies are not installed")
class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.normal = self.root / "regular.ttf"
        self.obfuscated = self.root / "capture.ttf"
        synthetic_font(self.normal)
        synthetic_font(self.obfuscated, variant=True)
        self.input = self.root / "capture.json"
        self.output = self.root / "rendered"
        self.data = {
            "schema_version": 1, "batch_id": "synthetic-batch-1", "source": {"type": "synthetic-offline-fixture"},
            "fonts": [{"id": "capture", "path": "capture.ttf", "sha256": hashlib.sha256(self.obfuscated.read_bytes()).hexdigest()}],
            "questions": [{"id": "q-example", "stem": [{"text": "Normal 一 ", "font": "normal"}, {"text": "\ue001", "font": "capture"}],
                           "options": [{"label": "display-B", "runs": [{"text": "Choice text", "font": "normal"}]},
                                       {"label": "display-A", "runs": [{"text": "Other text", "font": "normal"}]}]}],
        }

    def invoke(self, command="render", *, output=None, extra=()):
        self.input.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        arguments = [command, "--input", str(self.input), "--out", str(output or self.output),
                     "--normal-font", str(self.normal), *extra]
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = reader.main(arguments)
        return code, json.loads(stdout.getvalue())

    def result(self):
        return json.loads((self.output / "result.json").read_text(encoding="utf-8"))

    def test_mixed_fonts_and_option_identity_are_preserved(self):
        code, summary = self.invoke()
        self.assertEqual(code, 0, summary)
        result = self.result()
        question = result["questions"][0]
        self.assertEqual(question["id"], "q-example")
        self.assertEqual([option["label"] for option in question["options"]], ["display-B", "display-A"])
        self.assertEqual(question["stem"]["lines"][0]["font_ids"], ["capture", "normal"])
        self.assertTrue(question["needs_review"])
        self.assertEqual(result["fonts"]["capture"]["batch_id"], "synthetic-batch-1")
        self.assertEqual(result["fonts"]["capture"]["sha256"], self.data["fonts"][0]["sha256"])
        self.assertTrue((self.output / question["stem"]["lines"][0]["image"]).is_file())
        self.assertEqual(list(self.output.glob("*.ttf")), [], "No normal/system fonts should be bundled into output")

    def test_composite_emits_one_image_per_question(self):
        code, summary = self.invoke(extra=("--composite", "per-question"))
        self.assertEqual(code, 0, summary)
        question = self.result()["questions"][0]
        self.assertIn("composite", question)
        composite = question["composite"]
        self.assertTrue((self.output / composite["image"]).is_file())
        self.assertEqual(composite["image"], "q-0001-composite.png")
        # One header + stem lines + one option label per option + option lines.
        expected_strips = 1 + len(question["stem"]["lines"]) + sum(
            1 + len(option["content"]["lines"]) for option in question["options"])
        self.assertEqual(composite["strip_count"], expected_strips)
        from PIL import Image
        with Image.open(self.output / composite["image"]) as opened:
            self.assertEqual(opened.width, composite["width"])
            self.assertEqual(opened.height, composite["height"])

    def test_default_render_does_not_emit_composite(self):
        code, summary = self.invoke()
        self.assertEqual(code, 0, summary)
        question = self.result()["questions"][0]
        self.assertNotIn("composite", question)
        self.assertEqual(list(self.output.glob("*-composite.png")), [])

    def missing_regular_glyph_fixture(self):
        from fontTools.ttLib import TTFont
        with TTFont(self.obfuscated) as font:
            for table in font['cmap'].tables:
                if table.isUnicode():
                    table.cmap.pop(0x4E00, None)
            font.save(self.obfuscated)
        self.data['fonts'][0]['sha256'] = hashlib.sha256(self.obfuscated.read_bytes()).hexdigest()
        self.data['questions'][0]['stem'] = [{'text': '一\ue001', 'font': 'capture'}]

    def test_optional_missing_glyph_fallback_preserves_encoded_glyph(self):
        self.missing_regular_glyph_fixture()
        code, summary = self.invoke(extra=('--fallback-missing-glyphs',))
        self.assertEqual(code, 0, summary)
        self.assertTrue(self.result()['fallback_missing_glyphs'])
        stem = self.result()['questions'][0]['stem']
        self.assertEqual(stem['source_text'], '一\ue001')
        self.assertEqual(stem['lines'][0]['font_ids'], ['capture', 'normal'])
        self.assertEqual([(run['text'], run['font']) for run in stem['runs']],
                         [('一', 'normal'), ('\ue001', 'capture')])
        self.assertTrue(any('normal_font_fallback' in warning for warning in stem['warnings']))
        self.assertTrue(stem['needs_review'])

    def test_missing_glyph_default_behavior_is_unchanged(self):
        self.missing_regular_glyph_fixture()
        code, summary = self.invoke()
        self.assertEqual(code, 0, summary)
        stem = self.result()['questions'][0]['stem']
        self.assertEqual(stem['lines'][0]['font_ids'], ['capture'])
        self.assertTrue(any(reason.startswith('missing_font_glyphs:') for reason in stem['review_reasons']))

    def test_subset_missing_space_uses_normal_whitespace_glyph(self):
        from fontTools.ttLib import TTFont
        self.missing_regular_glyph_fixture()
        with TTFont(self.obfuscated) as font:
            for table in font['cmap'].tables:
                if table.isUnicode():
                    table.cmap.pop(32, None)
            font.save(self.obfuscated)
        self.data['fonts'][0]['sha256'] = hashlib.sha256(self.obfuscated.read_bytes()).hexdigest()
        self.data['questions'][0]['stem'] = [{'text': '\t一\ue001 ', 'font': 'capture'}]
        code, summary = self.invoke(extra=('--fallback-missing-glyphs',))
        self.assertEqual(code, 0, summary)
        stem = self.result()['questions'][0]['stem']
        self.assertEqual(stem['source_text'], '\t一\ue001 ')
        self.assertEqual([(run['text'], run['font']) for run in stem['runs']],
                         [('\t一', 'normal'), ('\ue001', 'capture'), (' ', 'normal')])

    def test_fallback_mode_cannot_mix_with_existing_render_output(self):
        self.missing_regular_glyph_fixture()
        self.assertEqual(self.invoke()[0], 0)
        original = (self.output / 'result.json').read_bytes()
        code, summary = self.invoke(extra=('--fallback-missing-glyphs',))
        self.assertNotEqual(code, 0, summary)
        self.assertEqual((self.output / 'result.json').read_bytes(), original)

    def test_long_text_wraps_without_losing_characters(self):
        text = "Long text with spaces " * 40
        self.data["questions"][0]["stem"] = [{"text": text, "font": "normal"}]
        code, summary = self.invoke(extra=("--max-width", "220"))
        self.assertEqual(code, 0, summary)
        lines = self.result()["questions"][0]["stem"]["lines"]
        self.assertGreater(len(lines), 10)
        self.assertEqual("".join(line["source_text"] for line in lines), text)
        self.assertTrue(all(line["width"] <= 220 for line in lines))

    def test_explicit_blank_lines_are_retained(self):
        self.data["questions"][0]["stem"] = [{"text": "first\n\nthird\r\n", "font": "normal"}]
        self.assertEqual(self.invoke()[0], 0)
        self.assertEqual([line["source_text"] for line in self.result()["questions"][0]["stem"]["lines"]],
                         ["first", "", "third", ""])

    def test_crlf_split_between_runs_is_one_line_break(self):
        self.data["questions"][0]["stem"] = [{"text": "first\r", "font": "normal"}, {"text": "\nsecond", "font": "normal"}]
        self.assertEqual(self.invoke()[0], 0)
        self.assertEqual([line["source_text"] for line in self.result()["questions"][0]["stem"]["lines"]], ["first", "second"])

    def test_relative_font_is_resolved_against_input_directory(self):
        with mock.patch.object(Path, "cwd", return_value=self.root.parent):
            code, summary = self.invoke()
        self.assertEqual(code, 0, summary)
        self.assertEqual(self.result()["fonts"]["capture"]["origin"], str(self.obfuscated.resolve()))

    def test_inline_font_is_supported_and_hash_checked(self):
        self.data["fonts"][0].pop("path")
        self.data["fonts"][0]["data_base64"] = base64.b64encode(self.obfuscated.read_bytes()).decode("ascii")
        self.assertEqual(self.invoke()[0], 0)
        self.assertEqual(self.result()["fonts"]["capture"]["origin"], "inline_base64")

    def test_wrong_hash_stops_before_artifacts(self):
        self.data["fonts"][0]["sha256"] = "0" * 64
        code, summary = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn("SHA-256", summary["message"])
        self.assertFalse(self.output.exists())

    def test_missing_batch_font_does_not_reuse_cached_font(self):
        self.data["fonts"] = []
        code, summary = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn("absent from this batch", summary["message"])

    def test_duplicate_questions_and_option_labels_are_rejected(self):
        self.data["questions"].append(dict(self.data["questions"][0]))
        self.assertEqual(self.invoke()[0], 2)
        self.data["questions"].pop()
        self.data["questions"][0]["options"][1]["label"] = "display-B"
        self.assertEqual(self.invoke()[0], 2)

    def test_cross_batch_reuse_does_not_overwrite_results(self):
        self.assertEqual(self.invoke()[0], 0)
        original = (self.output / "result.json").read_bytes()
        self.data["batch_id"] = "other-batch"
        code, summary = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn("different batch", summary["message"])
        self.assertEqual((self.output / "result.json").read_bytes(), original)

    def test_changed_input_and_changed_font_refuse_same_output(self):
        self.assertEqual(self.invoke()[0], 0)
        original = (self.output / "result.json").read_bytes()
        self.data["questions"][0]["id"] = "different-question"
        self.assertEqual(self.invoke()[0], 2)
        self.data["questions"][0]["id"] = "q-example"
        synthetic_font(self.normal, variant=True)
        self.assertEqual(self.invoke()[0], 2)
        self.assertEqual((self.output / "result.json").read_bytes(), original)

    def test_same_input_can_render_again_or_upgrade_to_ocr(self):
        self.assertEqual(self.invoke()[0], 0)
        self.assertEqual(self.invoke()[0], 0)
        engine = mock.Mock(return_value=([[None, "synthetic text", "0.98"]], None))
        with mock.patch.object(reader, "start_ocr", return_value=engine):
            code, summary = self.invoke("ocr")
        self.assertEqual(code, 0, summary)
        self.assertEqual(self.result()["status"], "ocr_complete")
        self.assertEqual(self.result()["questions"][0]["stem"]["lines"][0]["ocr"]["text"], "synthetic text")
        self.assertTrue(self.result()["needs_review"], "High OCR confidence must not skip visual review")

    def test_unrelated_nonempty_output_is_not_overwritten(self):
        self.output.mkdir()
        (self.output / "keep.txt").write_text("existing local work", encoding="utf-8")
        self.assertEqual(self.invoke()[0], 2)
        self.assertEqual((self.output / "keep.txt").read_text(), "existing local work")

    def test_writer_lock_prevents_concurrent_writes(self):
        (self.root / "rendered.question-reader.lock").write_text("a process", encoding="ascii")
        code, summary = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn("Another reader", summary["message"])
        self.assertFalse(self.output.exists())

    def test_formula_images_and_missing_glyphs_request_review(self):
        self.data["questions"][0]["stem"] = [{"text": "x^2 + ∫ + \u4e8c", "font": "normal"}]
        from PIL import Image
        Image.new("RGB", (12, 12), "white").save(self.root / "diagram.png")
        self.data["questions"][0]["images"] = [{"path": "diagram.png", "caption": "synthetic diagram"}]
        self.assertEqual(self.invoke()[0], 0)
        question = self.result()["questions"][0]
        self.assertTrue(question["needs_review"])
        self.assertIn("formula_or_math_layout_requires_visual_review", question["stem"]["review_reasons"])
        self.assertTrue(any(reason.startswith("missing_font_glyphs:") for reason in question["stem"]["review_reasons"]))
        self.assertTrue(question["images"][0]["needs_review"])
        self.assertEqual(len(question["images"][0]["sha256"]), 64)

    def test_page_image_reference_is_retained_without_file_or_network_access(self):
        self.data["questions"][0]["stem"] = [{"text": "Refer to the diagram", "font": "normal"}]
        self.data["questions"][0]["images"] = [
            {"src": "https://example.invalid/synthetic-diagram.png", "caption": "unfetched diagram", "requires_visual_review": True},
            {"src": "blob:synthetic-page-image", "requires_visual_review": True},
            {"src": "", "caption": "missing image source", "requires_visual_review": True},
        ]
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("No network access permitted")), \
             mock.patch("socket.socket", side_effect=AssertionError("No network sockets permitted")):
            code, summary = self.invoke()
        self.assertEqual(code, 0, summary)
        question = self.result()["questions"][0]
        self.assertTrue(question["needs_review"])
        self.assertTrue(question["stem"]["lines"], "Text should still render when diagrams have not been acquired")
        self.assertEqual(question["images"][0]["src"], "https://example.invalid/synthetic-diagram.png")
        self.assertEqual(question["images"][0]["caption"], "unfetched diagram")
        for image in question["images"]:
            self.assertTrue(image["reference_only"])
            self.assertFalse(image["fetched"])
            self.assertTrue(image["needs_review"])
            self.assertEqual(image["acquisition_status"], "not_attempted")
            self.assertNotIn("sha256", image, "An unfetched reference cannot claim an image hash")

    def test_ambiguous_or_unreviewed_page_image_reference_is_rejected(self):
        self.data["questions"][0]["images"] = [{"src": "https://example.invalid/image.png", "path": "image.png", "requires_visual_review": True}]
        code, summary = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn("exactly one", summary["message"])
        self.data["questions"][0]["images"] = [{"src": "https://example.invalid/image.png"}]
        self.assertEqual(self.invoke()[0], 2)

    def test_image_stem_and_option_associations_survive_for_both_sources(self):
        from PIL import Image
        Image.new("RGB", (12, 12), "white").save(self.root / "diagram.png")
        self.data["questions"][0]["images"] = [
            {"path": "diagram.png", "role": "stem", "image_index": 0},
            {"src": "https://example.invalid/option.png", "requires_visual_review": True,
             "role": "option", "option_label": "display-B", "image_index": 1},
            {"path": "diagram.png", "role": "option", "option_label": "display-A", "image_index": 2},
        ]
        self.assertEqual(self.invoke()[0], 0)
        images = self.result()["questions"][0]["images"]
        self.assertEqual([(image["role"], image.get("option_label"), image["image_index"]) for image in images],
                         [("stem", None, 0), ("option", "display-B", 1), ("option", "display-A", 2)])
        self.assertTrue(all(image["needs_review"] for image in images))

    def test_invalid_image_option_associations_are_rejected(self):
        for metadata in ({"role": "unknown"}, {"role": "option"}, {"role": "option", "option_label": "missing"},
                         {"option_label": "missing"}):
            with self.subTest(metadata=metadata):
                self.data["questions"][0]["images"] = [{"src": "https://example.invalid/option.png",
                                                       "requires_visual_review": True, **metadata}]
                self.assertEqual(self.invoke()[0], 2)

    def test_local_images_remain_strict_about_missing_files(self):
        self.data["questions"][0]["images"] = [{"path": "missing-diagram.png"}]
        code, summary = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn("does not exist locally", summary["message"])

    def test_capture_warnings_are_preserved_and_never_clear_review(self):
        self.data["fonts"] = []
        self.data["warnings"] = ["Font not embedded/readable: synthetic-secret-font"]
        self.data["questions"][0]["stem"] = [{"text": "Encoded text rendered with normal fallback", "font": "normal",
                                                  "warnings": ["stem capture missing its original font"]}]
        self.data["questions"][0]["warnings"] = ["question source needs confirmation"]
        self.data["questions"][0]["options"][0]["warnings"] = ["option font unavailable"]
        self.assertEqual(self.invoke()[0], 0)
        result = self.result()
        question = result["questions"][0]
        self.assertEqual(result["warnings"], self.data["warnings"])
        self.assertEqual(question["warnings"], self.data["questions"][0]["warnings"])
        self.assertEqual(question["stem"]["warnings"], ["stem capture missing its original font"])
        self.assertEqual(question["options"][0]["warnings"], ["option font unavailable"])
        self.assertTrue(question["options"][0]["content"]["needs_review"])
        self.assertTrue(result["needs_review"])
        self.assertTrue(question["needs_review"])

    def test_batch_warning_alone_marks_otherwise_plain_question_for_review(self):
        self.data["fonts"] = []
        self.data["questions"][0]["stem"] = [{"text": "Plain synthetic text", "font": "normal"}]
        self.data["warnings"] = ["capture could not inspect a stylesheet"]
        self.assertEqual(self.invoke()[0], 0)
        result = self.result()
        self.assertTrue(result["questions"][0]["needs_review"])
        self.assertIn("capture_warnings_require_review", result["questions"][0]["review_reasons"])

    def plain_capture(self):
        self.data["fonts"] = []
        self.data["questions"][0]["stem"] = [{"text": "Plain synthetic text", "font": "normal"}]

    def test_explicit_question_review_survives_render_and_ocr(self):
        self.plain_capture()
        self.data["questions"][0]["needs_review"] = True
        self.assertEqual(self.invoke()[0], 0)
        result = self.result()
        self.assertTrue(result["needs_review"])
        self.assertTrue(result["questions"][0]["needs_review"])
        self.assertIn("capture_explicit_needs_review", result["questions"][0]["review_reasons"])
        engine = mock.Mock(return_value=([[None, "synthetic text", "0.99"]], None))
        with mock.patch.object(reader, "start_ocr", return_value=engine):
            self.assertEqual(self.invoke("ocr")[0], 0)
        self.assertIn("capture_explicit_needs_review", self.result()["questions"][0]["review_reasons"])

    def test_explicit_option_review_is_preserved_and_propagated(self):
        self.plain_capture()
        self.data["questions"][0]["options"][0]["needs_review"] = True
        self.assertEqual(self.invoke()[0], 0)
        question = self.result()["questions"][0]
        self.assertTrue(question["options"][0]["needs_review"])
        self.assertIn("capture_explicit_needs_review", question["options"][0]["review_reasons"])
        self.assertTrue(question["needs_review"])

    def test_inferred_label_is_preserved_and_not_trusted_after_successful_ocr(self):
        self.plain_capture()
        self.data["questions"][0]["needs_review"] = False
        self.data["questions"][0]["options"][0]["label_inferred"] = True
        self.assertEqual(self.invoke()[0], 0)
        question = self.result()["questions"][0]
        self.assertTrue(question["options"][0]["label_inferred"])
        self.assertTrue(question["options"][0]["needs_review"])
        self.assertIn("inferred_option_label_requires_review", question["options"][0]["review_reasons"])
        self.assertTrue(question["needs_review"])
        engine = mock.Mock(return_value=([[None, "synthetic text", "0.99"]], None))
        with mock.patch.object(reader, "start_ocr", return_value=engine):
            self.assertEqual(self.invoke("ocr")[0], 0)
        option = self.result()["questions"][0]["options"][0]
        self.assertTrue(option["label_inferred"])
        self.assertTrue(option["needs_review"])
        self.assertIn("inferred_option_label_requires_review", option["review_reasons"])

    def test_explicit_false_flags_remain_false_for_unambiguous_plain_text(self):
        self.plain_capture()
        self.data["questions"][0]["needs_review"] = False
        self.data["questions"][0]["options"][0]["needs_review"] = False
        self.data["questions"][0]["options"][0]["label_inferred"] = False
        self.assertEqual(self.invoke()[0], 0)
        question = self.result()["questions"][0]
        self.assertFalse(question["needs_review"])
        self.assertFalse(question["options"][0]["needs_review"])
        self.assertFalse(question["options"][0]["label_inferred"])

    def test_capture_review_flags_require_boolean_values(self):
        self.plain_capture()
        self.data["questions"][0]["needs_review"] = "true"
        self.assertEqual(self.invoke()[0], 2)
        self.data["questions"][0]["needs_review"] = False
        self.data["questions"][0]["options"][0]["label_inferred"] = "false"
        self.assertEqual(self.invoke()[0], 2)

    def test_ocr_missing_dependency_keeps_rendered_images(self):
        error = reader.ReaderError("No local OCR models", reader.EXIT_DEPENDENCY)
        with mock.patch.object(reader, "start_ocr", side_effect=error):
            code, summary = self.invoke("ocr")
        self.assertEqual(code, 3)
        self.assertTrue(Path(summary["result_path"]).is_file())
        result = self.result()
        self.assertEqual(result["status"], "ocr_unavailable")
        self.assertTrue(list(self.output.glob("*.png")))

    def test_ocr_runtime_failure_keeps_results_and_other_lines(self):
        engine = mock.Mock(side_effect=[RuntimeError("synthetic failure"), ([[None, "A", "0.9"]], None), ([[None, "B", "0.2"]], None)])
        with mock.patch.object(reader, "start_ocr", return_value=engine):
            code, summary = self.invoke("ocr")
        self.assertEqual(code, 4, summary)
        result = self.result()
        self.assertEqual(result["status"], "ocr_error")
        self.assertEqual(result["questions"][0]["stem"]["lines"][0]["ocr"]["status"], "error")
        self.assertEqual(result["questions"][0]["options"][0]["content"]["lines"][0]["ocr"]["text"], "A")
        self.assertIn("ocr_below_confidence_threshold", result["questions"][0]["options"][1]["content"]["review_reasons"])

    def test_invalid_input_and_cli_are_json_errors(self):
        self.data["schema_version"] = True
        self.assertEqual(self.invoke()[0], 2)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = reader.main(["render"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "error")


class DoctorTests(unittest.TestCase):
    def test_doctor_reports_missing_components_without_initializing_ocr(self):
        with mock.patch.object(reader, "available", return_value=False), \
             mock.patch.object(reader, "font_candidates", return_value=[]), \
             mock.patch.object(reader, "start_ocr", side_effect=AssertionError("doctor must not initialize OCR")):
            result = reader.doctor()
        self.assertFalse(result["render_ready"])
        self.assertFalse(result["ocr_ready"])
        self.assertFalse(result["downloads"])


if __name__ == "__main__":
    unittest.main()
