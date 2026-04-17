from __future__ import annotations

import io
import shutil
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.support import load_script_module


def ffmpeg_tools_available() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@unittest.skipUnless(ffmpeg_tools_available(), "ffmpeg and ffprobe are not available")
class WhisperGeneratedMediaIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.whisper = load_script_module("whisper")

    def make_tiny_video(self, output: Path) -> None:
        result = subprocess.run(
            [
                shutil.which("ffmpeg") or "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=32x32:r=1",
                "-t",
                "0.5",
                "-c:v",
                "mpeg4",
                str(output),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            self.skipTest(f"ffmpeg could not generate tiny media: {result.stderr.strip()}")

    def test_embed_file_mode_with_generated_media(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "clip.mp4"
            subtitle = root / "clip.srt"
            output_root = root / "out"
            self.make_tiny_video(video)
            subtitle.write_text("1\n00:00:00,000 --> 00:00:00,500\nHello\n", encoding="utf-8")
            env = {
                "WHISPER_OUTDIR": str(output_root),
                "WHISPER_EMBED": "1",
                "WHISPER_EMBED_FILE": "",
                "WHISPER_IN_PLACE": "0",
                "WHISPER_BURN": "0",
                "WHISPER_BURN_VCODEC": "auto",
                "WHISPER_LANG": "en",
                "WHISPER_FORCE": "0",
            }

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                exit_code = self.whisper.run_embed_file_mode([video], env, recursive=False, jobs=1)

            embedded = output_root / "clip_embedded.mp4"
            self.assertEqual(exit_code, 0)
            self.assertTrue(embedded.is_file())
            self.assertGreaterEqual(self.whisper.probe_subtitle_stream_count(embedded), 1)

    def test_create_sample_media_fixture_writes_video_and_sidecar(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video, subtitle = self.whisper.create_sample_media_fixture(root / "sample.mp4")

            self.assertTrue(video.is_file())
            self.assertTrue(subtitle.is_file())
            self.assertIn("Hello from whisper sample media", subtitle.read_text(encoding="utf-8"))
            self.assertIsNotNone(self.whisper.probe_duration_seconds(video))
