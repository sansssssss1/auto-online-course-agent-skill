"""Offline tests for the multi-select option-vs-evidence coverage precheck."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "option_coverage.py"
SPEC = importlib.util.spec_from_file_location("option_coverage", SCRIPT)
coverage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(coverage)

SRT = """1
00:00:01,000 --> 00:00:04,000
三创是指创新、创优、创业。

2
00:00:05,000 --> 00:00:09,000
创业要素一体化包括资源、机会与团队。

3
00:00:10,000 --> 00:00:14,000
创造性地解决问题需要先定义问题。
"""

THREE_CREATIVE = {
    "question": "三创是指",
    "type": "multi",
    "selected": ["A", "B", "D"],
    "options": [
        {"key": "A", "text": "创新"},
        {"key": "B", "text": "创造"},
        {"key": "C", "text": "创优"},
        {"key": "D", "text": "创业"},
    ],
}

THREE_CREATIVE_RIGHT = dict(THREE_CREATIVE, selected=["A", "C", "D"])


class NormalizeTest(unittest.TestCase):
    def test_strips_punctuation_and_spaces(self):
        self.assertEqual(coverage.normalize(" 三创、是指「创新」创业。 "), "三创是指创新创业")

    def test_empty_text_normalizes_to_empty(self):
        self.assertEqual(coverage.normalize(" ，。 "), "")


class TermTest(unittest.TestCase):
    def test_distinctive_terms_exclude_other_options(self):
        others = ["创优", "创业", "创造"]
        terms = coverage.option_terms("创新", others)
        self.assertIn("创新", terms)
        self.assertNotIn("创", terms)

    def test_shared_fragment_is_not_distinctive(self):
        # 创业 is a whole option here; 创 must not be offered as evidence for it.
        self.assertEqual(coverage.option_terms("创", ["创新"]), [])

    def test_terms_are_longest_first(self):
        terms = coverage.option_terms("创业要素一体化", ["创造"])
        self.assertEqual(terms[0], "创业要素一体化")
        self.assertTrue(all(len(left) >= len(right) for left, right in zip(terms, terms[1:])))


class CoverageTest(unittest.TestCase):
    def setUp(self):
        self.corpus = coverage.parse_corpus(SRT)

    def test_full_option_text_is_direct(self):
        records = coverage.check_options(self.corpus, [
            {"key": "A", "text": "创新"}, {"key": "B", "text": "创优"}])
        self.assertEqual([record["coverage"] for record in records], ["direct", "direct"])
        self.assertEqual(records[0]["cue"]["index"], 1)

    def test_absent_option_is_missing(self):
        records = coverage.check_options(self.corpus, [{"key": "B", "text": "创造"}])
        self.assertEqual(records[0]["coverage"], "direct")  # 创造 appears inside 创造性地
        records = coverage.check_options(self.corpus, [{"key": "E", "text": "创收"}])
        self.assertEqual(records[0]["coverage"], "missing")

    def test_partial_option_reports_the_term_it_matched(self):
        records = coverage.check_options(self.corpus, [{"key": "F", "text": "创优创业一体化"}])
        self.assertEqual(records[0]["coverage"], "partial")
        self.assertIn(records[0]["matched_term"], ("创优", "创业", "创优创业"))


class EnumerationTest(unittest.TestCase):
    def setUp(self):
        self.corpus = coverage.parse_corpus(SRT)
        self.records = coverage.check_options(self.corpus, THREE_CREATIVE["options"])

    def test_three_listed_items_in_one_cue_are_an_enumeration(self):
        enumeration = coverage.find_enumeration(self.corpus, self.records)
        self.assertTrue(enumeration["detected"])
        self.assertEqual(enumeration["listed"], ["A", "C", "D"])
        self.assertEqual(enumeration["cue"]["index"], 1)

    def test_no_enumeration_for_scattered_matches(self):
        records = coverage.check_options(self.corpus, [
            {"key": "A", "text": "三创"}, {"key": "B", "text": "团队"}])
        enumeration = coverage.find_enumeration(self.corpus, records)
        self.assertFalse(enumeration["detected"])

    def test_two_items_need_a_list_separator(self):
        listed = coverage.parse_corpus("1\n00:00:01,000 --> 00:00:02,000\n创新与创业\n")
        records = coverage.check_options(listed, [
            {"key": "A", "text": "创新"}, {"key": "B", "text": "创业"}])
        enumeration = coverage.find_enumeration(listed, records)
        self.assertTrue(enumeration["detected"])
        self.assertEqual(enumeration["listed"], ["A", "B"])

        unlisted = coverage.parse_corpus("1\n00:00:01,000 --> 00:00:02,000\n创新创业\n")
        records = coverage.check_options(unlisted, [
            {"key": "A", "text": "创新"}, {"key": "B", "text": "创业"}])
        self.assertFalse(coverage.find_enumeration(unlisted, records)["detected"])


class VerdictTest(unittest.TestCase):
    def test_word_hits_never_claim_answer_correctness_or_authorize_actions(self):
        corpus = coverage.parse_corpus('不是创新，而是创业。')
        report = coverage.check_report(corpus, {'question': '创新是否是结论',
            'options': [{'key': 'A', 'text': '创新'}], 'selected': ['A']})
        self.assertIsNone(report['answer_correct'])
        self.assertTrue(report['requires_semantic_review'])
        self.assertEqual(report['automatic_actions'], [])
    def setUp(self):
        self.corpus = coverage.parse_corpus(SRT)

    def test_wrong_enumeration_choice_blocks_submit(self):
        report = coverage.check_report(self.corpus, THREE_CREATIVE)
        self.assertEqual(report["verdict"], "review")
        codes = [blocker["code"] for blocker in report["blockers"]]
        self.assertIn("enumeration-mismatch", codes)
        self.assertEqual(report["enumeration"]["listed"], ["A", "C", "D"])

    def test_correct_enumeration_choice_is_ready(self):
        report = coverage.check_report(self.corpus, THREE_CREATIVE_RIGHT)
        self.assertEqual(report["verdict"], "ready")
        self.assertEqual(report["blockers"], [])

    def test_missing_text_is_a_warning_by_default(self):
        payload = {
            "type": "multi",
            "selected": ["A", "E"],
            "options": [{"key": "A", "text": "创新"}, {"key": "E", "text": "创收"}],
        }
        report = coverage.check_report(self.corpus, payload)
        self.assertEqual(report["verdict"], "ready")
        self.assertEqual(report["blockers"], [])
        self.assertIn("selected-no-evidence", [item["code"] for item in report["warnings"]])

    def test_strict_mode_blocks_on_missing_text(self):
        payload = {
            "type": "multi",
            "selected": ["A", "E"],
            "options": [{"key": "A", "text": "创新"}, {"key": "E", "text": "创收"}],
        }
        report = coverage.check_report(self.corpus, payload, strict=True)
        self.assertEqual(report["verdict"], "review")
        self.assertIn("selected-no-evidence", [item["code"] for item in report["blockers"]])

    def test_concept_named_without_listing_does_not_block(self):
        # The real 12.4 case: the video says 双创/三创 but never lists the three items.
        corpus = coverage.parse_corpus("1\n00:00:01,000 --> 00:00:03,000\n原来我们总在强调双创，现在又提出三创。\n")
        payload = {"selected": ["A", "B"],
                   "options": [{"key": "A", "text": "创新"}, {"key": "B", "text": "创优"}]}
        report = coverage.check_report(corpus, payload)
        self.assertFalse(report["enumeration"]["detected"])
        self.assertEqual(report["verdict"], "ready")
        self.assertIn("selected-no-evidence", [item["code"] for item in report["warnings"]])

    def test_no_selection_is_a_blocker(self):
        payload = dict(THREE_CREATIVE_RIGHT, selected=[])
        report = coverage.check_report(self.corpus, payload)
        self.assertEqual(report["verdict"], "review")
        self.assertIn("no-selection", [item["code"] for item in report["blockers"]])

    def test_ordinary_multi_select_with_evidence_is_ready(self):
        payload = {
            "type": "multi",
            "selected": ["A", "B"],
            "options": [{"key": "A", "text": "资源"}, {"key": "B", "text": "机会"}],
        }
        report = coverage.check_report(self.corpus, payload)
        self.assertEqual(report["verdict"], "ready")


class PayloadTest(unittest.TestCase):
    def test_keys_are_derived_when_missing(self):
        payload = coverage.normalize_payload({"options": [{"text": "创新"}, {"text": "创优"}]})
        self.assertEqual([item["key"] for item in payload["options"]], ["A", "B"])

    def test_duplicate_keys_are_rejected(self):
        with self.assertRaises(coverage.CoverageError):
            coverage.normalize_payload({"options": [{"key": "A", "text": "创新"},
                                                    {"key": "A", "text": "创优"}]})

    def test_empty_options_are_rejected(self):
        with self.assertRaises(coverage.CoverageError):
            coverage.normalize_payload({"options": []})

    def test_unknown_selected_key_is_rejected(self):
        with self.assertRaises(coverage.CoverageError):
            coverage.normalize_payload({"selected": ["Z"], "options": [{"key": "A", "text": "创新"}]})


class CommandTest(unittest.TestCase):
    def test_force_does_not_overwrite_either_input(self):
        for target in (self.srt, self.options):
            original = target.read_bytes()
            code, _ = self.run_cli(['check', '--corpus', str(self.srt), '--options', str(self.options),
                                    '--out', str(target), '--force'])
            self.assertEqual(code, coverage.EXIT_INPUT)
            self.assertEqual(target.read_bytes(), original)
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.srt = self.base / "course.srt"
        self.srt.write_text(SRT, encoding="utf-8")
        self.options = self.base / "options.json"
        self.options.write_text(json.dumps(THREE_CREATIVE, ensure_ascii=False), encoding="utf-8")

    def run_cli(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
            code = coverage.main(argv)
        return code, buffer.getvalue()

    def test_review_exit_code_and_brief_lines(self):
        code, output = self.run_cli(["check", "--corpus", str(self.srt),
                                     "--options", str(self.options), "--brief"])
        self.assertEqual(code, coverage.EXIT_REVIEW)
        self.assertIn("VERDICT=review", output)
        self.assertIn("ENUM", output)

    def test_ready_exit_code_writes_report(self):
        right = self.base / "right.json"
        right.write_text(json.dumps(THREE_CREATIVE_RIGHT, ensure_ascii=False), encoding="utf-8")
        report_path = self.base / "report.json"
        code, _ = self.run_cli(["check", "--corpus", str(self.srt), "--options", str(right),
                                "--out", str(report_path)])
        self.assertEqual(code, coverage.EXIT_OK)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["verdict"], "ready")
        self.assertEqual(len(report["options"]), 4)

    def test_missing_corpus_is_an_input_error(self):
        code, _ = self.run_cli(["check", "--corpus", str(self.base / "nope.srt"),
                                "--options", str(self.options)])
        self.assertEqual(code, coverage.EXIT_INPUT)

    def test_strict_flag_escalates_a_warning_to_an_error(self):
        payload = self.base / "gap.json"
        payload.write_text(json.dumps({
            "selected": ["A", "B"], "options": [{"key": "A", "text": "创新"},
                                                {"key": "B", "text": "创收"}]},
            ensure_ascii=False), encoding="utf-8")
        lenient, output = self.run_cli(["check", "--corpus", str(self.srt),
                                        "--options", str(payload), "--brief"])
        self.assertEqual(lenient, coverage.EXIT_OK)
        self.assertIn("WARN selected-no-evidence", output)
        strict, _ = self.run_cli(["check", "--corpus", str(self.srt),
                                  "--options", str(payload), "--strict", "--brief"])
        self.assertEqual(strict, coverage.EXIT_REVIEW)


if __name__ == "__main__":
    unittest.main()
