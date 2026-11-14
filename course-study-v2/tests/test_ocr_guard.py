"""Offline tests for the OCR stem guard that decides when to re-crop."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ocr_guard.py"
SPEC = importlib.util.spec_from_file_location("ocr_guard", SCRIPT)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def ocr_line(text, x, y, width=200, height=24):
    return {
        "text": text,
        "confidence": 0.9,
        "box": [[x, y], [x + width, y], [x + width, y + height], [x, y + height]],
    }


class StemQualityTest(unittest.TestCase):
    def test_complete_tagged_stem_is_fine(self):
        quality = guard.stem_quality("1【单选题】人工智能算法关注（）。")
        self.assertFalse(quality["suspect"])
        self.assertEqual(quality["body"], "人工智能算法关注（）。")

    def test_tag_without_body_is_suspect(self):
        quality = guard.stem_quality("1【单选题】")
        self.assertTrue(quality["suspect"])
        self.assertIn("short-stem", quality["reasons"])

    def test_one_character_body_is_suspect(self):
        quality = guard.stem_quality("7【多选题】创")
        self.assertTrue(quality["suspect"])
        self.assertIn("short-stem", quality["reasons"])

    def test_unbalanced_bracket_is_suspect(self):
        quality = guard.stem_quality("1【单选题以下哪句话不能体现")
        self.assertTrue(quality["suspect"])
        self.assertIn("unbalanced-tag", quality["reasons"])

    def test_short_untagged_text_is_suspect(self):
        self.assertTrue(guard.stem_quality("人工智能")["suspect"])

    def test_long_untagged_text_is_fine(self):
        self.assertFalse(guard.stem_quality("以下哪句话不能体现人工智能思维")["suspect"])

    def test_empty_text_is_suspect(self):
        self.assertTrue(guard.stem_quality("")["suspect"])


class FindStemTest(unittest.TestCase):
    def test_picks_the_first_question_line_and_ignores_chrome(self):
        lines = [
            ocr_line("5.2 从管理思维到创业思维", 1176, 183, width=500),
            ocr_line("1【单选题】人工智能算法关注（）。", 210, 444),
            ocr_line("A 资源优势", 210, 492),
        ]
        self.assertEqual(guard.find_stem(lines), "1【单选题】人工智能算法关注（）。")

    def test_falls_back_to_the_first_panel_line(self):
        lines = [ocr_line("目录", 1176, 59, width=300), ocr_line("没有题号的一行文字", 210, 300)]
        self.assertEqual(guard.find_stem(lines), "没有题号的一行文字")


class CommandTest(unittest.TestCase):
    def test_malformed_line_records_are_input_errors(self):
        source = self.write_ocr('broken.json', [None])
        code, _ = self.run_cli([str(self.base / 'shot.png'), str(source), '--dry-run'])
        self.assertEqual(code, guard.EXIT_INPUT)
    def test_recrop_reuses_the_cropper_ocr_exactly_once(self):
        source = self.write_ocr('broken.json', [ocr_line('1【单选题】', 210, 444)])
        recovered = {'images': [{'lines': [ocr_line('1【单选题】这里是完整且可辨认的题干。', 0, 0)]}]}
        response = SimpleNamespace(returncode=0, stdout=json.dumps(recovered), stderr='')
        with patch.object(guard, 'run', return_value=response) as process:
            code, output = self.run_cli([str(self.base / 'shot.png'), str(source)])
        self.assertEqual(code, guard.EXIT_OK)
        self.assertEqual(process.call_count, 1)
        self.assertIn('--json', process.call_args.args[0])
        self.assertFalse(json.loads(output)['needs_review'])

    def test_unreadable_recrop_stops_for_review_instead_of_looping(self):
        source = self.write_ocr('broken.json', [ocr_line('1【单选题】', 210, 444)])
        response = SimpleNamespace(returncode=0, stdout=json.dumps({'images': [{'lines': []}]}), stderr='')
        with patch.object(guard, 'run', return_value=response) as process:
            code, output = self.run_cli([str(self.base / 'shot.png'), str(source)])
        self.assertEqual(code, guard.EXIT_REVIEW)
        self.assertEqual(process.call_count, 1)
        self.assertTrue(json.loads(output)['needs_review'])

    def test_original_image_is_never_used_as_recrop_output(self):
        source = self.write_ocr('broken.json', [ocr_line('1【单选题】', 210, 444)])
        png = str(self.base / 'shot.png')
        with patch.object(guard, 'run') as process:
            code, _ = self.run_cli([png, str(source), '--out', png])
        self.assertEqual(code, guard.EXIT_INPUT)
        process.assert_not_called()
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def write_ocr(self, name, lines):
        path = self.base / name
        path.write_text(json.dumps({"images": [{"lines": lines}]}, ensure_ascii=False), encoding="utf-8")
        return path

    def run_cli(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
            code = guard.main(argv)
        return code, buffer.getvalue()

    def test_broken_stem_dry_run_reports_a_planned_crop(self):
        ocr = self.write_ocr("broken.json", [ocr_line("1【单选题】", 210, 444)])
        code, output = self.run_cli([str(self.base / "shot.png"), str(ocr), "--dry-run"])
        self.assertEqual(code, guard.EXIT_OK)
        report = json.loads(output)
        self.assertTrue(report["suspect"])
        self.assertEqual(report["action"], "would-crop")
        self.assertIn("short-stem", report["reasons"])

    def test_good_stem_needs_no_crop(self):
        ocr = self.write_ocr("good.json", [ocr_line("1【单选题】人工智能算法关注（）。", 210, 444)])
        code, output = self.run_cli([str(self.base / "shot.png"), str(ocr), "--dry-run"])
        self.assertEqual(code, guard.EXIT_OK)
        self.assertFalse(json.loads(output)["suspect"])

    def test_missing_ocr_file_is_an_input_error(self):
        code, _ = self.run_cli([str(self.base / "shot.png"), str(self.base / "nope.json"), "--dry-run"])
        self.assertEqual(code, guard.EXIT_INPUT)


if __name__ == "__main__":
    unittest.main()
