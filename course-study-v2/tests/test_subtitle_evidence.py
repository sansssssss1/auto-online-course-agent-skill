"""Offline tests for subtitle retrieval and the semantic evidence gate."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "subtitle_evidence.py"
SPEC = importlib.util.spec_from_file_location("subtitle_evidence", SCRIPT)
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)

SRT_BODY = (
    "\ufeff1\r\n"
    "00:00:20,000 --> 00:00:22,000\r\n"
    "宝瓶口的宽度和底高有极严格的控制\r\n"
    "\r\n"
    "2\r\n"
    "00:00:22,000 --> 00:00:25,000\r\n"
    "古人在岩壁上刻了几十条分划\r\n"
    "取名为水则\r\n"
    "\r\n"
    "3\r\n"
    "00:00:25,000 --> 00:00:28,000\r\n"
    "这体现了古人的智慧\r\n"
)

WEBVTT_BODY = (
    "WEBVTT\n\n"
    "00:00:01.000 --> 00:00:02.500 align:start\n"
    "Hello <i>world</i>\n"
)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exception):
        return False


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, name, text, encoding="utf-8"):
        path = self.root / name
        path.write_bytes(text.encode(encoding))
        return path

    def test_srt_handles_bom_crlf_and_multiline_cues(self):
        cues = evidence.parse_srt(SRT_BODY)
        self.assertEqual(len(cues), 3)
        self.assertEqual(cues[0]["start_ms"], 20000)
        self.assertEqual(cues[0]["end_ms"], 22000)
        self.assertEqual(cues[1]["text"], "古人在岩壁上刻了几十条分划 取名为水则")
        self.assertEqual(cues[2]["text"], "这体现了古人的智慧")

    def test_webvtt_dots_tags_and_settings_are_accepted(self):
        cues = evidence.parse_srt(WEBVTT_BODY)
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0]["text"], "Hello world")
        self.assertEqual(cues[0]["start_ms"], 1000)
        self.assertEqual(cues[0]["end_ms"], 2500)

    def test_malformed_srt_is_rejected(self):
        for body in ("", "1\nnot a timestamp\n", "only text\n"):
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    evidence.parse_srt(body)

    def test_plain_text_corpus_keeps_line_numbers(self):
        cues = evidence.parse_lines("第一行\n\n第二行\n")
        self.assertEqual([cue["line"] for cue in cues], [1, 3])
        self.assertIsNone(cues[0]["start_ms"])

    def test_load_corpus_detects_kind_and_hashes_bytes(self):
        srt = self.write("a.srt", SRT_BODY)
        corpus = evidence.load_corpus(srt)
        self.assertEqual(corpus["kind"], "srt")
        self.assertEqual(len(corpus["sha256"]), 64)
        self.assertEqual(len(corpus["cues"]), 3)
        transcript = self.write("notes.txt", "水则\n为人民服务\n")
        self.assertEqual(evidence.load_corpus(transcript)["kind"], "text")

    def test_load_corpus_rejects_missing_or_unreadable_files(self):
        with self.assertRaises(evidence.EvidenceError):
            evidence.load_corpus(self.root / "absent.srt")
        broken = self.write("broken.srt", "no timestamps here\n")
        with self.assertRaises(evidence.EvidenceError):
            evidence.load_corpus(broken)

    def test_locate_requires_all_terms_within_the_window(self):
        cues = evidence.parse_srt(SRT_BODY)
        self.assertEqual(len(evidence.locate(cues, ["宝瓶口", "水则"], window=1)), 0)
        hits = evidence.locate(cues, ["宝瓶口", "水则"], window=3)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["first"]["start_ms"], 20000)
        self.assertIn("取名为水则", hits[0]["text"])

    def test_locate_respects_the_limit(self):
        cues = evidence.parse_lines("水则一\n水则二\n水则三\n")
        self.assertEqual(len(evidence.locate(cues, ["水则"], window=1, limit=2)), 2)

    def test_empty_terms_are_rejected(self):
        with self.assertRaises(evidence.EvidenceError):
            evidence.normalize_terms([])
        with self.assertRaises(evidence.EvidenceError):
            evidence.normalize_terms(["  "])


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.corpus = self.root / "node.srt"
        self.corpus.write_bytes(SRT_BODY.encode("utf-8"))
        self.questions = self.root / "questions.json"
        self.output = self.root / "gate.json"

    def invoke(self, payload, arguments=()):
        self.questions.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = evidence.main(["gate", "--corpus", str(self.corpus), "--questions",
                                  str(self.questions), *arguments])
        return code, stdout.getvalue()

    def supported_payload(self):
        return {"questions": [
            {"id": "Q1", "text": "古人在岩壁上刻分划取名水则", "answer": "A",
             "terms": ["分划", "水则"], "window": 1},
        ]}

    def test_supported_question_carries_a_quote_and_allows_submission(self):
        code, output = self.invoke(self.supported_payload())
        self.assertEqual(code, 0)
        report = json.loads(output)
        self.assertEqual(report["verdict"], "supported")
        question = report["questions"][0]
        self.assertEqual(question["decision"], "submit")
        self.assertFalse(question["low_confidence"])
        self.assertEqual(question["evidence"]["start_ms"], 22000)
        self.assertEqual(question["evidence"]["end_ms"], 25000)
        self.assertEqual(len(question["evidence"]["terms"]), 2)
        self.assertEqual(report["corpus"]["cues"], 3)

    def test_unverified_question_is_low_confidence_and_blocked(self):
        payload = {"questions": [
            {"id": "Q3", "text": "水则就是为人民服务", "answer": "B",
             "terms": ["水则", "为人民服务"]},
        ]}
        code, output = self.invoke(payload)
        self.assertEqual(code, 5)
        report = json.loads(output)
        self.assertEqual(report["verdict"], "low-confidence")
        self.assertEqual(report["low_confidence_ids"], ["Q3"])
        question = report["questions"][0]
        self.assertEqual(question["decision"], "do-not-submit")
        self.assertTrue(question["low_confidence"])
        self.assertTrue(question["partial"])
        self.assertEqual(question["missing_terms"], ["为人民服务"])
        self.assertEqual(question["found_terms"], ["水则"])
        self.assertIsNone(question["evidence"])

    def test_partial_and_empty_terms_are_reported_separately(self):
        payload = {"questions": [
            {"id": "Q1", "terms": ["宝瓶口", "水则"], "window": 1},
            {"id": "Q2", "terms": ["不存在的词"]},
        ]}
        code, output = self.invoke(payload)
        self.assertEqual(code, 5)
        report = json.loads(output)
        self.assertTrue(report["questions"][0]["partial"])
        self.assertEqual(report["questions"][0]["missing_terms"], [])
        self.assertFalse(report["questions"][1]["partial"])
        self.assertEqual(report["questions"][1]["missing_terms"], ["不存在的词"])

    def test_text_transcript_can_serve_as_the_source(self):
        transcript = self.root / "course-notes.txt"
        transcript.write_text("都江堰的核心工程包括鱼嘴\n分水堤把岷江分成内外二江\n", encoding="utf-8")
        self.questions.write_text(json.dumps({"questions": [
            {"id": "Q1", "terms": ["鱼嘴", "岷江"]}]}, ensure_ascii=False), encoding="utf-8")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = evidence.main(["gate", "--corpus", str(transcript), "--questions",
                                  str(self.questions), "--window", "1"])
        self.assertEqual(code, 5)  # 鱼嘴 and 岷江 sit on different lines
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["corpus"]["kind"], "text")
        self.assertIsNone(report["questions"][0]["evidence"])
        self.assertTrue(report["questions"][0]["partial"])
        with contextlib.redirect_stdout(io.StringIO()):
            code = evidence.main(["gate", "--corpus", str(transcript), "--questions",
                                  str(self.questions), "--window", "2"])
        self.assertEqual(code, 0)

    def test_gate_output_file_is_written_and_protected(self):
        code, _ = self.invoke(self.supported_payload(), ["--out", str(self.output)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.output.read_text(encoding="utf-8"))["verdict"], "supported")
        code, output = self.invoke(self.supported_payload(), ["--out", str(self.output)])
        self.assertEqual(code, 2)
        self.assertIn("--force", json.loads(output)["error"])
        code, _ = self.invoke(self.supported_payload(), ["--out", str(self.output), "--force"])
        self.assertEqual(code, 0)

    def test_brief_gate_prints_one_line_per_question(self):
        code, output = self.invoke(self.supported_payload(), ["--brief"])
        self.assertEqual(code, 0)
        self.assertIn("Q1 supported submit", output)
        self.assertIn("VERDICT=supported", output)
        self.assertNotIn('"questions"', output)

    def test_brief_gate_marks_low_confidence_and_still_writes_full_record(self):
        payload = {"questions": [{"id": "Q3", "terms": ["水则", "为人民服务"]}]}
        code, output = self.invoke(payload, ["--brief", "--out", str(self.output)])
        self.assertEqual(code, 5)
        self.assertIn("Q3 low-confidence do-not-submit", output)
        self.assertIn("missing=为人民服务", output)
        record = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(record["verdict"], "low-confidence")
        self.assertEqual(record["low_confidence_ids"], ["Q3"])

    def test_invalid_question_payloads_are_rejected(self):
        for payload in ({"questions": []}, {"questions": "nope"},
                        {"questions": [{"id": "Q1", "terms": []}]},
                        {"questions": [{"id": "", "terms": ["水则"]}]},
                        {"questions": [{"id": "Q1", "terms": ["水则"]}, {"id": "Q1", "terms": ["分划"]}]},
                        {"questions": [{"id": "Q1", "terms": ["水则"], "window": 0}]},
                        {"questions": [{"id": "Q1", "terms": ["水则"], "text": 5}]}):
            with self.subTest(payload=payload):
                self.assertEqual(self.invoke(payload)[0], 2)


class SliceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.corpus = self.root / "node.srt"
        self.corpus.write_bytes(SRT_BODY.encode("utf-8"))

    def invoke(self, arguments):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = evidence.main(["slice", "--corpus", str(self.corpus), *arguments])
        return code, stdout.getvalue()

    def test_time_formats_are_accepted(self):
        self.assertEqual(evidence.parse_time("158"), 158000)
        self.assertEqual(evidence.parse_time("02:38"), 158000)
        self.assertEqual(evidence.parse_time("00:02:38.599"), 158599)

    def test_slice_prints_the_selected_cues(self):
        code, output = self.invoke(["--from", "00:00:21", "--to", "00:00:24"])
        self.assertEqual(code, 0)
        self.assertTrue(output.startswith("[00:00:22.000] "), output)
        self.assertEqual(len(output.strip().splitlines()), 1)

    def test_slice_json_and_empty_window(self):
        code, output = self.invoke(["--from", "1", "--to", "2", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["count"], 0)
        code, output = self.invoke(["--from", "1", "--to", "2"])
        self.assertEqual(code, 0)
        self.assertEqual(output.strip(), "NO_CUES")

    def test_bad_or_reversed_ranges_are_rejected(self):
        self.assertEqual(self.invoke(["--from", "00:00:25", "--to", "00:00:20"])[0], 2)
        self.assertEqual(self.invoke(["--from", "abc", "--to", "20"])[0], 2)


class FindTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.corpus = self.root / "node.srt"
        self.corpus.write_bytes(SRT_BODY.encode("utf-8"))

    def test_find_quotes_the_matching_cues(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = evidence.main(["find", "--corpus", str(self.corpus), "--query", "宝瓶口",
                                  "--query", "水则", "--window", "2"])
        self.assertEqual(code, 0)
        report = json.loads(stdout.getvalue())
        self.assertTrue(report["found"])
        self.assertEqual(report["matches"][0]["time"], "00:00:20.000-00:00:25.000")
        self.assertIn("取名为水则", report["matches"][0]["text"])

    def test_brief_find_prints_timestamped_quotes(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = evidence.main(["find", "--corpus", str(self.corpus), "--query", "宝瓶口",
                                  "--query", "水则", "--window", "2", "--brief"])
        self.assertEqual(code, 0)
        output = stdout.getvalue().strip()
        self.assertTrue(output.startswith("[00:00:20.000-00:00:25.000] "), output)
        self.assertNotIn("{", output)

    def test_brief_find_without_a_match_says_so(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = evidence.main(["find", "--corpus", str(self.corpus), "--query", "不存在的词", "--brief"])
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue().strip(), "NO_MATCH")

    def test_find_without_a_match_is_not_an_error(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = evidence.main(["find", "--corpus", str(self.corpus), "--query", "不存在的词"])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(stdout.getvalue())["found"])


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "node.srt"
        self.payload = {"data": {"srtUrl": "http://example.invalid/a.srt", "other": "ignore me"}}

    def invoke(self, arguments, response=None, error=None):
        stdout = io.StringIO()
        target = mock.patch("urllib.request.urlopen", return_value=response, side_effect=error)
        with target, contextlib.redirect_stdout(stdout):
            code = evidence.main(["fetch", *arguments])
        return code, stdout.getvalue()

    def test_fetch_url_writes_normalized_srt(self):
        code, output = self.invoke(["--url", "http://example.invalid/a.srt", "--out", str(self.output)],
                                   response=FakeResponse(SRT_BODY.encode("utf-8")))
        self.assertEqual(code, 0)
        summary = json.loads(output)
        self.assertEqual(summary["cues"], 3)
        self.assertTrue(summary["network_used"])
        self.assertEqual(len(summary["sha256"]), 64)
        saved = self.output.read_bytes()
        self.assertFalse(saved.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(saved.startswith(b"1\n00:00:20,000"))

    def test_fetch_from_list_picks_the_requested_index(self):
        listing = self.root / "list.json"
        listing.write_text(json.dumps({"data": [
            {"url": "http://example.invalid/first.srt"},
            {"srtUrl": "http://example.invalid/second.srt"}]}), encoding="utf-8")
        code, output = self.invoke(["--list", str(listing), "--choose", "1", "--out", str(self.output)],
                                   response=FakeResponse(SRT_BODY.encode("utf-8")))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["source_url"], "http://example.invalid/second.srt")

    def test_fetch_rejects_bad_lists_and_out_of_range_choices(self):
        listing = self.root / "empty.json"
        listing.write_text(json.dumps({"data": {"note": "no url"}}), encoding="utf-8")
        self.assertEqual(self.invoke(["--list", str(listing), "--out", str(self.output)])[0], 2)
        good = self.root / "good.json"
        good.write_text(json.dumps(self.payload), encoding="utf-8")
        self.assertEqual(self.invoke(["--list", str(good), "--choose", "3", "--out", str(self.output)])[0], 2)
        self.assertFalse(self.output.exists())

    def test_fetch_needs_exactly_one_source(self):
        self.assertEqual(self.invoke(["--out", str(self.output)])[0], 2)
        self.assertEqual(self.invoke(["--url", "http://example.invalid/a.srt", "--list", "x",
                                      "--out", str(self.output)])[0], 2)

    def test_fetch_network_error_maps_to_exit_four(self):
        code, output = self.invoke(["--url", "http://example.invalid/a.srt", "--out", str(self.output)],
                                   error=urllib.error.URLError("offline"))
        self.assertEqual(code, 4)
        self.assertEqual(json.loads(output)["status"], "error")
        self.assertFalse(self.output.exists())

    def test_fetch_non_srt_content_is_rejected_before_writing(self):
        code, output = self.invoke(["--url", "http://example.invalid/a.srt", "--out", str(self.output)],
                                   response=FakeResponse("<html>login required</html>".encode("utf-8")))
        self.assertEqual(code, 2)
        self.assertIn("not readable SRT", json.loads(output)["error"])
        self.assertFalse(self.output.exists())

    def test_fetch_does_not_overwrite_without_force(self):
        self.output.write_text("keep me", encoding="utf-8")
        code, output = self.invoke(["--url", "http://example.invalid/a.srt", "--out", str(self.output)],
                                   response=FakeResponse(SRT_BODY.encode("utf-8")))
        self.assertEqual(code, 2)
        self.assertIn("--force", json.loads(output)["error"])
        self.assertEqual(self.output.read_text(encoding="utf-8"), "keep me")

    def test_candidate_urls_are_deduplicated_in_order(self):
        payload = {"a": ["http://x.invalid/1.srt", "http://x.invalid/1.srt"],
                   "b": {"c": "http://x.invalid/2.srt?token=TEST"}}
        self.assertEqual(evidence.candidate_urls(payload),
                         ["http://x.invalid/1.srt", "http://x.invalid/2.srt?token=TEST"])

    def test_non_http_scheme_is_rejected(self):
        with self.assertRaises(evidence.EvidenceError):
            evidence.download("file:///etc/passwd", 5)


if __name__ == "__main__":
    unittest.main()
