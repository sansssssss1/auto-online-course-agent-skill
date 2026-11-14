"""Offline tests for the quiz OCR decoder; the OCR engine itself is always mocked."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "quiz_ocr.py"
SPEC = importlib.util.spec_from_file_location("quiz_ocr", SCRIPT)
quiz = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quiz)

BOX = [[0.0, 0.0], [120.0, 0.0], [120.0, 32.0], [0.0, 32.0]]


def engine_rows(*items):
    """Mimic RapidOCR rows: [box, text, score] in reading order."""
    return [[BOX, text, score] for text, score in items]


class QuizOcrTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.image = self.root / "quiz.png"
        self.image.write_bytes(b"synthetic screenshot placeholder")
        self.output = self.root / "quiz.json"

    def invoke(self, engine, arguments=(), *, dependency=True):
        engine = engine or mock.Mock(return_value=([], None))
        stdout = io.StringIO()
        with mock.patch.object(quiz, "available", return_value=dependency), \
             mock.patch.object(quiz, "load_engine", return_value=engine) as loader, \
             contextlib.redirect_stdout(stdout):
            code = quiz.main(list(arguments) or [str(self.image)])
        return code, stdout.getvalue(), loader

    def test_plain_output_keeps_reading_order_and_confidence(self):
        code, output, _ = self.invoke(mock.Mock(return_value=(engine_rows(
            ("第一题：水则是什么？", "0.94"), ("A. 刻在岩壁上的分划", "0.86")), None)))
        self.assertEqual(code, 0)
        self.assertEqual(output.splitlines(), ["0.94\t第一题：水则是什么？", "0.86\tA. 刻在岩壁上的分划"])

    def test_low_confidence_lines_are_flagged_without_hiding_them(self):
        engine = mock.Mock(return_value=(engine_rows(("模糊的一行", "0.42"), ("清楚的一行", "0.91")), None))
        code, output, _ = self.invoke(engine, ["--json", str(self.image)])
        self.assertEqual(code, 0)
        record = json.loads(output)
        self.assertEqual(record["status"], "ok")
        self.assertEqual(record["lines"], 2)
        self.assertTrue(record["images"][0]["lines"][0]["low_confidence"])
        self.assertFalse(record["images"][0]["lines"][1]["low_confidence"])
        self.assertEqual(record["images"][0]["lines"][0]["box"], [[0.0, 0.0], [120.0, 0.0], [120.0, 32.0], [0.0, 32.0]])
        self.assertEqual(record["images"][0]["low_confidence_lines"], 1)
        json.dumps(record, ensure_ascii=False)

    def test_confidence_threshold_is_configurable(self):
        engine = mock.Mock(return_value=(engine_rows(("中等置信", "0.55")), None))
        code, output, _ = self.invoke(engine, ["--json", "--min-confidence", "0.5", str(self.image)])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(output)["images"][0]["lines"][0]["low_confidence"])

    def test_missing_dependency_reports_exit_three(self):
        stdout = io.StringIO()
        with mock.patch.object(quiz, "available", return_value=False), \
             contextlib.redirect_stdout(stdout):
            code = quiz.main([str(self.image)])
        self.assertEqual(code, 3)
        self.assertIn("rapidocr_onnxruntime", json.loads(stdout.getvalue())["error"])

    def test_missing_screenshot_stops_before_loading_the_engine(self):
        stdout = io.StringIO()
        with mock.patch.object(quiz, "load_engine", side_effect=AssertionError("engine must not load")), \
             contextlib.redirect_stdout(stdout):
            code = quiz.main([str(self.root / "absent.png")])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "error")

    def test_engine_runtime_failure_maps_to_exit_four(self):
        engine = mock.Mock(side_effect=RuntimeError("onnx exploded"))
        code, output, _ = self.invoke(engine)
        self.assertEqual(code, 4)
        self.assertIn("onnx exploded", json.loads(output)["error"])

    def test_empty_result_is_reported_without_error(self):
        code, output, _ = self.invoke(mock.Mock(return_value=([], None)), ["--json", str(self.image)])
        self.assertEqual(code, 0)
        record = json.loads(output)
        self.assertEqual(record["status"], "empty")
        self.assertEqual(record["lines"], 0)

    def test_blank_text_and_malformed_rows_are_skipped(self):
        rows = [[BOX, "   ", "0.99"], [BOX, "有效行", "0.88"], ["not-a-row"], [BOX]]
        code, output, _ = self.invoke(mock.Mock(return_value=(rows, None)), ["--json", str(self.image)])
        self.assertEqual(code, 0)
        record = json.loads(output)
        self.assertEqual([line["text"] for line in record["images"][0]["lines"]], ["有效行"])
        self.assertEqual(record["images"][0]["lines"][0]["box"][0], [0.0, 0.0])

    def test_missing_score_is_kept_as_unknown(self):
        rows = [[BOX, "无分数行"], [BOX, "分数非数字", "n/a"]]
        code, output, _ = self.invoke(mock.Mock(return_value=(rows, None)), ["--json", str(self.image)])
        self.assertEqual(code, 0)
        lines = json.loads(output)["images"][0]["lines"]
        self.assertEqual([line["confidence"] for line in lines], [None, None])
        self.assertFalse(any(line["low_confidence"] for line in lines))
        self.assertIsNone(json.loads(output)["images"][0]["mean_confidence"])

    def test_output_file_is_json_and_protected_unless_forced(self):
        engine = mock.Mock(return_value=(engine_rows(("题目", "0.9")), None))
        code, _, _ = self.invoke(engine, ["--json", "--out", str(self.output), str(self.image)])
        self.assertEqual(code, 0)
        record = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(record["images"][0]["lines"][0]["text"], "题目")
        code, output, _ = self.invoke(engine, ["--json", "--out", str(self.output), str(self.image)])
        self.assertEqual(code, 2)
        self.assertIn("--force", json.loads(output)["error"])
        code, _, _ = self.invoke(engine, ["--json", "--out", str(self.output), "--force", str(self.image)])
        self.assertEqual(code, 0)

    def test_min_confidence_outside_unit_interval_is_rejected(self):
        for value in ("1.5", "-0.1"):
            with self.subTest(value=value):
                code, output, _ = self.invoke(None, ["--min-confidence", value, str(self.image)])
                self.assertEqual(code, 2)
                self.assertIn("between 0 and 1", json.loads(output)["error"])

    def test_multiple_images_are_grouped_and_engine_is_reused(self):
        second = self.root / "second.png"
        second.write_bytes(b"another screenshot")
        engine = mock.Mock(side_effect=[(engine_rows(("第一张", "0.9")), None), ([], None)])
        code, output, loader = self.invoke(engine, ["--json", str(self.image), str(second)])
        self.assertEqual(code, 0)
        record = json.loads(output)
        self.assertEqual([item["line_count"] for item in record["images"]], [1, 0])
        self.assertEqual(engine.call_count, 2)
        self.assertEqual(loader.call_count, 1)


if __name__ == "__main__":
    unittest.main()
