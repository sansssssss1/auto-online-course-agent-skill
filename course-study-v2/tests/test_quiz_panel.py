"""Offline tests for the quiz-panel OCR filter."""

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "quiz_panel.py"
SPEC = importlib.util.spec_from_file_location("quiz_panel", SCRIPT)
panel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(panel)


def ocr_line(text, x, y, width=40, height=20, confidence=0.9):
    return {
        "text": text,
        "confidence": confidence,
        "box": [[x, y], [x + width, y], [x + width, y + height], [x, y + height]],
    }


class QuizPanelTest(unittest.TestCase):
    def test_keeps_question_panel_and_drops_toc(self):
        lines = [
            ocr_line("5.2 从管理思维到创业思维", 1176, 183),
            ocr_line("1【单选题】人工智能算法关注（）。", 210, 444),
            ocr_line("A 资源优势", 183, 492),
            ocr_line("目录 讨论 笔记 标注", 1152, 59),
        ]
        kept, dropped = panel.filter_lines(lines, x_min=100, x_max=1100, y_min=0)
        self.assertEqual([item[2] for item in kept], [
            "1【单选题】人工智能算法关注（）。",
            "A 资源优势",
        ])
        self.assertEqual([item[2] for item in dropped], [
            "5.2 从管理思维到创业思维",
            "目录 讨论 笔记 标注",
        ])

    def test_sorted_top_to_bottom(self):
        lines = [ocr_line("second", 150, 300), ocr_line("first", 150, 100)]
        kept, _ = panel.filter_lines(lines, x_min=100, x_max=1100, y_min=0)
        self.assertEqual([item[2] for item in kept], ["first", "second"])

    def test_y_min_drops_header(self):
        lines = [ocr_line("header", 150, 10), ocr_line("body", 150, 200)]
        kept, _ = panel.filter_lines(lines, x_min=100, x_max=1100, y_min=50)
        self.assertEqual([item[2] for item in kept], ["body"])

    def test_boundary_inclusive(self):
        lines = [ocr_line("edge", 100, 0, width=50)]
        kept, dropped = panel.filter_lines(lines, x_min=100, x_max=150, y_min=0)
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, [])


if __name__ == "__main__":
    unittest.main()
