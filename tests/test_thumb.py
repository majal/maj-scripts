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
