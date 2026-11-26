from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.support import load_script_module


class ThumbOutputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.thumb = load_script_module("thumb")

    def test_file_output_defaults_next_to_source(self) -> None:
        src = Path("/media/pics/a.png")
        dst = self.thumb.output_for(src, src.parent, src.parent, False, "jpg", "")
        self.assertEqual(dst, Path("/media/pics/a.png.jpg"))

    def test_suffix_and_format(self) -> None:
        src = Path("/media/pics/a.png")
        dst = self.thumb.output_for(src, src.parent, src.parent, False, "webp", "-t")
        self.assertEqual(dst, Path("/media/pics/a.png-t.webp"))

    def test_load_config_normalizes_dashes(self) -> None:
        with TemporaryDirectory() as td:
            cfg = Path(td) / "config.toml"
            cfg.write_text('file-output = "th"\nsize = 128\n', encoding="utf-8")
            try:
                import tomllib  # noqa: F401
            except ImportError:
                self.skipTest("tomllib needs Python 3.11+")
            self.assertEqual(
                self.thumb.load_config(cfg), {"file_output": "th", "size": 128}
            )

    def test_load_config_rejects_unknown_key(self) -> None:
        with TemporaryDirectory() as td:
            cfg = Path(td) / "config.toml"
            cfg.write_text('bogus = 1\n', encoding="utf-8")
            try:
                import tomllib  # noqa: F401
            except ImportError:
                self.skipTest("tomllib needs Python 3.11+")
            with self.assertRaises(SystemExit):
                self.thumb.load_config(cfg)

    def test_folder_scan_skips_videos_unless_requested(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.jpg").write_bytes(b"x")
            (root / "b.mp4").write_bytes(b"x")
            out = root / "thumbnails"
            names = lambda **kw: sorted(
                p.name for p in self.thumb.iter_media(root, False, out, [], [], **kw)
            )
            self.assertEqual(names(videos=False), ["a.jpg"])
            self.assertEqual(names(videos=True), ["a.jpg", "b.mp4"])

    def test_scan_ignores_leftover_part_files(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.jpg").write_bytes(b"x")
            (root / f".a.jpg.jpg{self.thumb.PART_MARK}.jpg").write_bytes(b"x")
            found = [p.name for p in self.thumb.iter_media(root, False, root / "t", [], [])]
            self.assertEqual(found, ["a.jpg"])

    def test_failed_conversion_leaves_no_temp_file(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            src = root / "bad.jpg"
            src.write_bytes(b"not an image")
            res = self.thumb.process_one(
                src, root / "bad.jpg.jpg",
                outfmt="jpg", size=256, quality=85, samples=120,
                prefer_artwork=True, artwork_only=False,
                force=False, mtime_only=False, dry_run=False,
            )
            self.assertEqual(res.status, "fail")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["bad.jpg"])

    def test_scan_skips_hidden_unless_asked(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.jpg").write_bytes(b"x")
            (root / "._a.jpg").write_bytes(b"x")
            (root / ".hid").mkdir()
            (root / ".hid" / "b.jpg").write_bytes(b"x")
            scan = lambda **kw: sorted(
                str(p.relative_to(root))
                for p in self.thumb.iter_media(root, True, root / "t", [], [], **kw)
            )
            self.assertEqual(scan(), ["a.jpg"])
            self.assertEqual(scan(hidden=True), ["._a.jpg", ".hid/b.jpg", "a.jpg"])

    def test_scan_order_is_sorted(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            for n in ("c.jpg", "a.jpg", "b.jpg"):
                (root / n).write_bytes(b"x")
            found = [p.name for p in self.thumb.iter_media(root, False, root / "t", [], [])]
            self.assertEqual(found, ["a.jpg", "b.jpg", "c.jpg"])

    def test_resolve_video_at(self) -> None:
        r = self.thumb.resolve_video_at
        self.assertIsNone(r("auto", 100.0))
        self.assertEqual(r("25%", 200.0), 50.0)
        self.assertEqual(r("12.5", 100.0), 12.5)
        self.assertAlmostEqual(r("999", 10.0), 9.9)
        with self.assertRaises(ValueError):
            r("abc", 10.0)

    def test_fingerprint_reflects_settings(self) -> None:
        fp = self.thumb.fingerprint
        self.assertNotEqual(fp(256, 85, "jpg", "auto", False), fp(128, 85, "jpg", "auto", False))
        self.assertNotEqual(fp(256, 85, "jpg", "auto", False), fp(256, 50, "jpg", "auto", False))
        self.assertEqual(fp(256, 85, "png", "auto", False), fp(256, 50, "png", "auto", False))
        self.assertNotEqual(fp(256, 85, "jpg", "25%", True), fp(256, 85, "jpg", "auto", True))

    def test_unsupported_file_is_skipped(self) -> None:
        res = self.thumb.process_one(
            Path("notes.txt"), Path("notes.txt.jpg"),
            outfmt="jpg", size=256, quality=85, samples=120,
            prefer_artwork=True, artwork_only=False,
            force=False, mtime_only=False, dry_run=True,
        )
        self.assertEqual(res.status, "skip")


if __name__ == "__main__":
    unittest.main()
