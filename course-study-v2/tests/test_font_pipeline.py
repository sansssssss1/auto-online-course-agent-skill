"""Offline tests for the parameterised font-decode pipeline (R1) and high-res merge (R3)."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load_module(name):
    path = SCRIPTS / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


glyph_map = load_module("glyph_map")
decode_batch = load_module("decode_batch")
build_manifest = load_module("build_merge_manifest")
merger = load_module("merge_images")

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def write_json(path, payload):
    Path(path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def make_image(path, width, height, color=(40, 90, 200)):
    Image.new("RGB", (width, height), color).save(path)


class DecodeBatchTest(unittest.TestCase):
    def sample_batch(self):
        return {"questions": [
            {"id": "q1",
             "stem": [{"text": "abc"}],
             "options": [{"label": "A", "runs": [{"text": "a"}]}]},
        ]}

    def test_hex_mapping_decodes_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            batch = folder / "b.json"
            mapping = folder / "m.json"
            out = folder / "d.json"
            write_json(batch, self.sample_batch())
            # 0x61 = 'a' -> 'X'; unmapped b,c pass through
            write_json(mapping, {"0x61": "X"})
            code = decode_batch.main([
                "--batch", str(batch), "--mapping", str(mapping),
                "--out", str(out)])
            self.assertEqual(code, 0)
            result = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(result[0]["stem"], "Xbc")
            self.assertEqual(result[0]["options"][0]["text"], "X")

    def test_decimal_mapping_key_accepted(self):
        self.assertEqual(
            decode_batch.normalize_mapping({"97": "X"}), {97: "X"})

    def test_unmapped_char_passes_through(self):
        self.assertEqual(decode_batch.decode_text("ab", {97: "X"}), "Xb")

    def test_missing_batch_is_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            mapping = folder / "m.json"
            write_json(mapping, {"0x61": "X"})
            self.assertEqual(decode_batch.main([
                "--batch", str(folder / "ghost.json"),
                "--mapping", str(mapping),
                "--out", str(folder / "o.json")]), 2)

    def test_bad_mapping_value_is_error(self):
        with self.assertRaises(decode_batch.DecodeError):
            decode_batch.normalize_mapping({"0x61": "too long"})

    def test_mapping_not_object_is_error(self):
        with self.assertRaises(decode_batch.DecodeError):
            decode_batch.normalize_mapping(["a"])

    def test_batch_without_questions_is_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            batch = folder / "b.json"; mapping = folder / "m.json"
            write_json(batch, {}); write_json(mapping, {"0x61": "X"})
            self.assertEqual(decode_batch.main([
                "--batch", str(batch), "--mapping", str(mapping),
                "--out", str(folder / "o.json")]), 2)


class BuildMergeManifestTest(unittest.TestCase):
    def sample_batch(self):
        return {"questions": [
            {"id": "q1", "images": [
                {"src": "https://x/a.png", "role": "stem"},
                {"src": "https://x/b.png", "role": "option",
                 "option_label": "A"},
                {"src": "https://x/a.png", "role": "stem"},  # duplicate
            ]},
            {"id": "q2", "images": [
                {"src": "https://x/c.png", "role": "stem"}]},
        ]}

    def test_groups_and_unique_urls(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            batch = folder / "b.json"
            out = folder / "mm.json"
            write_json(batch, self.sample_batch())
            code = build_manifest.main([
                "--batch", str(batch), "--tag", "9-9",
                "--out", str(out), "--image-dir", str(folder / "imgs")])
            self.assertEqual(code, 0)
            result = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(result["unique_urls"],
                             ["https://x/a.png", "https://x/b.png",
                              "https://x/c.png"])
            self.assertEqual([g["id"] for g in result["groups"]],
                             ["q1", "q2"])
            # order preserved, duplicate removed within q1
            self.assertEqual(len(result["groups"][0]["images"]), 2)
            self.assertTrue(
                result["groups"][0]["images"][0].endswith("a.png"))
            self.assertTrue(
                result["groups"][0]["images"][1].endswith("b.png"))

    def test_default_image_dir_uses_tag(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            batch = folder / "b.json"
            out = folder / "nested" / "mm.json"
            write_json(batch, self.sample_batch())
            code = build_manifest.main([
                "--batch", str(batch), "--tag", "9-9", "--out", str(out)])
            self.assertEqual(code, 0)
            result = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(result["image_dir"].endswith("9-9-images"))

    def test_no_images_is_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            batch = folder / "b.json"
            write_json(batch, {"questions": [{"id": "q1", "images": []}]})
            self.assertEqual(build_manifest.main([
                "--batch", str(batch), "--tag", "t",
                "--out", str(folder / "o.json")]), 2)

    def test_missing_batch_is_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            self.assertEqual(build_manifest.main([
                "--batch", str(folder / "ghost.json"), "--tag", "t",
                "--out", str(folder / "o.json")]), 2)


@unittest.skipUnless(PIL_AVAILABLE, "Pillow is required")
class HighResMergeTest(unittest.TestCase):
    def test_min_width_upscales_group(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            p = folder / "a.png"; make_image(p, 50, 20)
            sheet = merger.merge_group([p], spacing=0, margin=0, min_width=100)
            self.assertEqual(sheet.width, 100)
            self.assertEqual(sheet.height, 40)

    def test_scale_factor_upscales(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            p = folder / "a.png"; make_image(p, 40, 20)
            sheet = merger.merge_group([p], spacing=0, margin=0, scale=2.0)
            self.assertEqual((sheet.width, sheet.height), (80, 40))

    def test_manifest_min_width_applies(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            p = folder / "a.png"; make_image(p, 50, 20)
            manifest = folder / "m.json"
            write_json(manifest, {"min_width": 100,
                                  "groups": [{"id": "q1", "images": ["a.png"]}]})
            out = folder / "out"
            code = merger.main(["--input", str(manifest), "--out", str(out)])
            self.assertEqual(code, 0)
            with Image.open(out / "q1.png") as sheet:
                self.assertEqual(sheet.width, 140)  # 100 + 2*margin

    def test_cli_min_width_overrides_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            p = folder / "a.png"; make_image(p, 50, 20)
            manifest = folder / "m.json"
            write_json(manifest, {"min_width": 100,
                                  "groups": [{"id": "q1", "images": ["a.png"]}]})
            out = folder / "out"
            code = merger.main(["--input", str(manifest), "--out", str(out),
                                "--min-width", "200", "--margin", "0"])
            self.assertEqual(code, 0)
            with Image.open(out / "q1.png") as sheet:
                self.assertEqual(sheet.width, 200)

    def test_bad_scale_is_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            p = folder / "a.png"; make_image(p, 20, 20)
            with self.assertRaises(merger.MergeError):
                merger.merge_group([p], scale=0.5)


@unittest.skipUnless(PIL_AVAILABLE, "Pillow is required")
class GlyphMapCLITest(unittest.TestCase):
    def find_system_font(self):
        for candidate in (r"C:\Windows\Fonts\arial.ttf",
                          r"C:\Windows\Fonts\consola.ttf"):
            if Path(candidate).is_file():
                return candidate
        return None

    def test_render_chart_from_real_font(self):
        font = self.find_system_font()
        if not font:
            self.skipTest("no system font available")
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "g.png"
            code = glyph_map.main([
                "--font", font, "--out", str(out), "--cols", "4"])
            self.assertEqual(code, 0)
            self.assertTrue(out.is_file())
            with Image.open(out) as image:
                self.assertEqual(image.mode, "RGB")

    def test_missing_font_is_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(glyph_map.main([
                "--font", str(Path(temporary) / "ghost.ttf"),
                "--out", str(Path(temporary) / "o.png")]), 2)


if __name__ == "__main__":
    unittest.main()
