"""Offline tests for state/run-context synchronisation."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_context.py"
SPEC = importlib.util.spec_from_file_location("sync_context", SCRIPT)
syncer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(syncer)


def sample_state():
    return {
        "schema_version": 1,
        "account_alias": "math-account",
        "course_key": "示例课程",
        "authorization": {"read": True, "answer": True, "submit": True},
        "current": {
            "section": "5.3", "title": "连续很有用", "tab": "章节测验",
            "media_key": "5.3-video", "status": "in_progress",
            "note": "quiz open, not submitted",
        },
        "progress": {
            "catalog_start": "19/100", "catalog_verified": "33/100",
            "completed_this_run": [
                {"section": "3.2"}, {"section": "3.3"}, {"section": "5.2"},
            ],
        },
        "pause_reason": "paused for optimization",
        "next_action": "submit 5.3 quiz",
        "updated_at": "2026-11-07T01:35:00+08:00",
    }


class RenderSummaryTest(unittest.TestCase):
    def test_summary_reflects_state_fields(self):
        text = syncer.render_node_summary(sample_state())
        self.assertIn("示例课程", text)
        self.assertIn("5.3 连续很有用", text)
        self.assertIn("33/100", text)
        self.assertIn("3.2、3.3、5.2", text)
        self.assertIn("read=True", text)

    def test_empty_completed_is_handled(self):
        state = sample_state()
        state["progress"]["completed_this_run"] = []
        self.assertIn("已完成节点：无", syncer.render_node_summary(state))


class RunContextUpdateTest(unittest.TestCase):
    def test_preserves_first_two_sections_and_regenerates_third(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            ctx = folder / "run-context.md"
            ctx.write_text(
                "# 运行上下文摘要\n\n"
                "## 一、已读文件清单\n\n| 文件 | sha256 |\n|---|---|\n\n"
                "## 二、已确认环境事实\n\n- 环境事实 A\n",
                encoding="utf-8")
            new_text = syncer.update_run_context(ctx, sample_state())
            self.assertIn("## 一、已读文件清单", new_text)
            self.assertIn("环境事实 A", new_text)
            self.assertIn(syncer.NODE_HEADER, new_text)
            self.assertIn("5.3 连续很有用", new_text)
            # only one section-three header
            self.assertEqual(new_text.count(syncer.NODE_HEADER), 1)

    def test_creates_sections_when_file_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            ctx = Path(temporary) / "run-context.md"
            new_text = syncer.update_run_context(ctx, sample_state())
            self.assertIn("## 一、已读文件清单", new_text)
            self.assertIn(syncer.NODE_HEADER, new_text)


class IdempotencyTest(unittest.TestCase):
    def test_repeated_calls_keep_identical_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            state_path = folder / "state.json"
            ctx_path = folder / "run-context.md"
            state_path.write_text(
                json.dumps(sample_state(), ensure_ascii=False), encoding="utf-8")
            first = syncer.main([
                "--state", str(state_path), "--run-context", str(ctx_path)])
            self.assertEqual(first, 0)
            bytes_after_first = ctx_path.read_bytes()
            second = syncer.main([
                "--state", str(state_path), "--run-context", str(ctx_path)])
            self.assertEqual(second, 0)
            self.assertEqual(bytes_after_first, ctx_path.read_bytes())
            # no leftover temp files
            self.assertEqual(
                list(p.name for p in folder.iterdir() if p.name.endswith(".tmp")),
                [])

    def test_set_updates_state_and_context_together(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            state_path = folder / "state.json"
            ctx_path = folder / "run-context.md"
            state_path.write_text(
                json.dumps(sample_state(), ensure_ascii=False), encoding="utf-8")
            code = syncer.main([
                "--state", str(state_path), "--run-context", str(ctx_path),
                "--set", "current.status=completed",
            ])
            self.assertEqual(code, 0)
            updated = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(updated["current"]["status"], "completed")
            self.assertIn("状态 completed", ctx_path.read_text(encoding="utf-8"))

    def test_missing_state_is_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            code = syncer.main([
                "--state", str(Path(temporary) / "nope.json"),
                "--run-context", str(Path(temporary) / "run-context.md"),
            ])
            self.assertEqual(code, 2)


class SetParsingTest(unittest.TestCase):
    def test_dotted_key_and_json_value(self):
        state = sample_state()
        syncer.apply_sets(state, ["current.status=completed"])
        self.assertEqual(state["current"]["status"], "completed")

    def test_bad_assignment_is_error(self):
        with self.assertRaises(syncer.SyncError):
            syncer.apply_sets(sample_state(), ["noequals"])


if __name__ == "__main__":
    unittest.main()
