"""Offline tests for the paste-ready bu.js call emitter; no browser is opened."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "browser_payload.py"
SPEC = importlib.util.spec_from_file_location("browser_payload", SCRIPT)
payload = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(payload)


class BrowserPayloadTests(unittest.TestCase):
    def test_page_bu_call_is_paste_ready(self):
        snippet = payload.build_bu_call("questions", "page")
        self.assertIn("bu.js(", snippet)
        self.assertIn("json.dumps(options", snippet)
        self.assertIn("account_alias", snippet)
        self.assertNotIn("<BODY_SELECTOR>", snippet, "page scope must not require a body selector")
        self.assertIn("(options) =>", snippet)

    def test_element_bu_call_includes_body_selector(self):
        snippet = payload.build_bu_call("tasks", "element")
        self.assertIn('document.querySelector(\\"<BODY_SELECTOR>\\")', snippet)
        self.assertIn("(body, options) =>", snippet)

    def test_main_emit_flag_returns_zero_without_out(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = payload.main(["questions", "--scope", "page", "--emit-bu-call"])
        self.assertEqual(code, 0)
        self.assertIn("bu.js(", stdout.getvalue())

    def test_main_without_out_or_flag_is_an_error(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = payload.main(["questions", "--scope", "page"])
        self.assertEqual(code, 2)
        self.assertIn("--out", json.loads(stderr.getvalue())["error"])


if __name__ == "__main__":
    unittest.main()
