"""Offline tests for local option-image merging."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "merge_images.py"
SPEC = importlib.util.spec_from_file_location("merge_images", SCRIPT)
merger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(merger)

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def make_image(path, width, height, color=(200, 30, 30)):
    Image.new("RGB", (width, height), color).save(path)


@unittest.skipUnless(PIL_AVAILABLE, "Pillow is required for merge tests")
class MergeDirectoryTest(unittest.TestCase):
    def test_whole_directory_merges_into_one_sheet(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            make_image(folder / "a.png", 100, 40)
            make_image(folder / "b.png", 100, 60)
            out = folder / "out"
            code = merger.main([
                "--input", str(folder), "--out", str(out),
                "--spacing", "10", "--margin", "5",
            ])
            self.assertEqual(code, 0)
            sheet_path = out / "merged.png"
            self.assertTrue(sheet_path.is_file())
            with Image.open(sheet_path) as sheet:
                # width = 100 + 2*5; height = 40 + 60 + 10 + 2*5
                self.assertEqual((sheet.width, sheet.height), (110, 120))
            # originals are retained
            self.assertTrue((folder / "a.png").is_file())
            self.assertTrue((folder / "b.png").is_file())

    def test_group_pattern_splits_into_multiple_sheets(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            make_image(folder / "q1_a.png", 50, 20)
            make_image(folder / "q1_b.png", 50, 20)
            make_image(folder / "q2_a.png", 50, 20)
            out = folder / "out"
            code = merger.main([
                "--input", str(folder), "--out", str(out),
                "--group-pattern", r"(q\d)_",
            ])
            self.assertEqual(code, 0)
            self.assertTrue((out / "q1.png").is_file())
            self.assertTrue((out / "q2.png").is_file())

    def test_missing_directory_is_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(merger.MergeError):
                merger.collect_directory(Path(temporary) / "absent")

    def test_empty_directory_is_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(merger.MergeError):
                merger.collect_directory(Path(temporary))

    def test_non_matching_filename_is_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            make_image(folder / "a.png", 50, 20)
            with self.assertRaises(merger.MergeError):
                merger.collect_directory(folder, r"(q\d)_")


@unittest.skipUnless(PIL_AVAILABLE, "Pillow is required for merge tests")
class MergeManifestTest(unittest.TestCase):
    def test_groups_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            make_image(folder / "a.png", 80, 30)
            make_image(folder / "b.png", 80, 30)
            manifest = folder / "m.json"
            manifest.write_text(json.dumps({"groups": [
                {"id": "q1", "images": ["a.png", "b.png"]},
            ]}), encoding="utf-8")
            groups = merger.load_manifest(manifest)
            self.assertEqual(list(groups), ["q1"])
            self.assertEqual(len(groups["q1"]), 2)

    def test_flat_object_list_groups(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            make_image(folder / "a.png", 40, 20)
            make_image(folder / "b.png", 40, 20)
            manifest = folder / "m.json"
            manifest.write_text(json.dumps([
                {"path": "a.png", "group": "q1"},
                {"path": "b.png", "group": "q2"},
            ]), encoding="utf-8")
            groups = merger.load_manifest(manifest)
            self.assertEqual(set(groups), {"q1", "q2"})

    def test_string_list_single_group(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            make_image(folder / "a.png", 40, 20)
            manifest = folder / "m.json"
            manifest.write_text(json.dumps(["a.png"]), encoding="utf-8")
            groups = merger.load_manifest(manifest)
            self.assertEqual(list(groups), ["merged"])

    def test_missing_referenced_image_is_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            manifest = folder / "m.json"
            manifest.write_text(json.dumps(["ghost.png"]), encoding="utf-8")
            out = folder / "out"
            code = merger.main(
                ["--input", str(manifest), "--out", str(out)])
            self.assertEqual(code, 2)

    def test_invalid_manifest_is_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            manifest = folder / "m.json"
            manifest.write_text("{not json", encoding="utf-8")
            with self.assertRaises(merger.MergeError):
                merger.load_manifest(manifest)


@unittest.skipUnless(PIL_AVAILABLE, "Pillow is required for merge tests")
class MergeGeometryTest(unittest.TestCase):
    def test_unequal_widths_centered_on_max_width(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            wide = folder / "wide.png"; make_image(wide, 120, 20)
            narrow = folder / "narrow.png"; make_image(narrow, 60, 20)
            sheet = merger.merge_group([wide, narrow], spacing=0, margin=0)
            self.assertEqual(sheet.width, 120)
            self.assertEqual(sheet.height, 40)

    def test_uniform_width_scales_images(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            p = folder / "a.png"; make_image(p, 50, 100)
            sheet = merger.merge_group(
                [p], spacing=0, margin=0, uniform_width=100)
            self.assertEqual(sheet.width, 100)
            self.assertEqual(sheet.height, 200)

    def test_bad_alignment_is_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            p = folder / "a.png"; make_image(p, 20, 20)
            with self.assertRaises(merger.MergeError):
                merger.merge_group([p], align="diagonal")


if __name__ == "__main__":
    unittest.main()
