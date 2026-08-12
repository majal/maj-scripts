from __future__ import annotations

import argparse
import io
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from tests.support import load_script_module


class JwslTimeParsingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.jwsl = load_script_module("jwsl")

    def test_parse_hms(self) -> None:
        self.assertAlmostEqual(self.jwsl.parse_hms("00:00:12.212"), 12.212)
        self.assertAlmostEqual(self.jwsl.parse_hms("00:01:07.267"), 67.267)
        self.assertAlmostEqual(self.jwsl.parse_hms("01:00:00.000"), 3600.0)

    def test_markers_to_verse_times(self) -> None:
        markers = [
            {"verseNumber": 1, "startTime": "00:00:12.212", "duration": "00:00:25.592", "label": "Revelation 1:1"},
            {"verseNumber": 2, "startTime": "00:00:37.804", "duration": "00:00:07.707", "label": "Revelation 1:2"},
        ]
        times = self.jwsl.markers_to_verse_times(markers)
        self.assertAlmostEqual(times[1]["start"], 12.212)
        self.assertAlmostEqual(times[1]["end"], 37.804)
        self.assertAlmostEqual(times[2]["start"], 37.804)

    def test_markers_to_verse_times_skips_malformed_entries(self) -> None:
        times = self.jwsl.markers_to_verse_times([{"verseNumber": "not-a-number"}, None])
        self.assertEqual(times, {})

    def test_verse_markers_unwraps_api_shape(self) -> None:
        # GETPUBMEDIALINKS wraps the marker list: file['markers'] = {..., 'markers': [...]}
        file = {"markers": {"bibleBookNumber": 66, "markers": [{"verseNumber": 1}]}}
        self.assertEqual(self.jwsl.verse_markers(file), [{"verseNumber": 1}])

    def test_verse_markers_handles_missing_field(self) -> None:
        self.assertEqual(self.jwsl.verse_markers({}), [])


class JwslLangListTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.jwsl = load_script_module("jwsl")

    def test_single_code_passthrough(self) -> None:
        config = {"languages": "ASL,FSL,BVL,INI,SPE"}
        self.assertEqual(self.jwsl.get_lang_list(config, "fsl"), ["FSL"])

    def test_comma_list_splits_and_uppercases(self) -> None:
        config = {"languages": "ASL,FSL"}
        self.assertEqual(self.jwsl.get_lang_list(config, "asl,bvl"), ["ASL", "BVL"])

    def test_all_uses_configured_languages(self) -> None:
        config = {"languages": "ASL,FSL,BVL,INI,SPE"}
        self.assertEqual(self.jwsl.get_lang_list(config, "all"), ["ASL", "FSL", "BVL", "INI", "SPE"])

    def test_none_defaults_to_configured_languages(self) -> None:
        config = {"languages": "ASL,FSL"}
        self.assertEqual(self.jwsl.get_lang_list(config), ["ASL", "FSL"])


class JwslEncodeArgsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.jwsl = load_script_module("jwsl")

    def test_default_cpu_matches_legacy_proven_settings(self) -> None:
        config = {"hardware_encoder": "cpu", "video_codec": "h264", "video_crf": "20", "video_preset": "slow"}
        args = self.jwsl.build_encode_args(config)
        self.assertIn("libx264", args)
        self.assertIn("-crf", args)
        self.assertIn("20", args)
        self.assertIn("-preset", args)
        self.assertIn("slow", args)
        self.assertIn("-pix_fmt", args)
        self.assertIn("+faststart", args)

    def test_videotoolbox_uses_quality_not_crf(self) -> None:
        config = {"hardware_encoder": "videotoolbox", "video_codec": "h264", "video_crf": "20", "video_preset": "slow"}
        args = self.jwsl.build_encode_args(config)
        self.assertIn("h264_videotoolbox", args)
        self.assertIn("-q:v", args)
        self.assertNotIn("-crf", args)

    def test_hevc_codec_selects_libx265_on_cpu(self) -> None:
        config = {"hardware_encoder": "cpu", "video_codec": "hevc", "video_crf": "20", "video_preset": "slow"}
        args = self.jwsl.build_encode_args(config)
        self.assertIn("libx265", args)


class JwslCacheBudgetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.jwsl = load_script_module("jwsl")

    def test_lru_eviction_keeps_most_recently_used(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cache_dir = Path(td) / "cache" / "ASL"
            cache_dir.mkdir(parents=True)
            state: dict = {}
            for name in ("oldest.mp4", "middle.mp4", "newest.mp4"):
                p = cache_dir / name
                p.write_bytes(b"0" * (1024 * 1024))
                self.jwsl.note_cache_use(state, p)
                time.sleep(0.01)

            config = {
                "cache_dir": str(cache_dir.parent),
                "cache_policy": "lru",
                "cache_max_gb": str(2 * 1024 * 1024 / (1024 ** 3)),
            }
            self.jwsl.enforce_cache_budget(config, state)

            remaining = sorted(p.name for p in cache_dir.iterdir())
            self.assertEqual(remaining, ["middle.mp4", "newest.mp4"])

    def test_keep_all_policy_never_evicts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cache_dir = Path(td) / "cache" / "ASL"
            cache_dir.mkdir(parents=True)
            p = cache_dir / "a.mp4"
            p.write_bytes(b"0" * (1024 * 1024))
            state: dict = {}
            config = {"cache_dir": str(cache_dir.parent), "cache_policy": "keep_all", "cache_max_gb": "0"}
            self.jwsl.enforce_cache_budget(config, state)
            self.assertTrue(p.exists())

    def test_never_writes_the_real_state_file_itself(self) -> None:
        # Regression guard: enforce_cache_budget used to call save_state()
        # internally, which always writes to the one real on-disk
        # state.json regardless of what throwaway `state` dict a caller (or
        # a test) passed in — silently clobbering real user data. It must
        # only mutate the dict in memory; persisting is the caller's job.
        with tempfile.TemporaryDirectory() as td:
            cache_dir = Path(td) / "cache" / "ASL"
            cache_dir.mkdir(parents=True)
            p = cache_dir / "a.mp4"
            p.write_bytes(b"0" * (2 * 1024 * 1024))
            state: dict = {}
            config = {"cache_dir": str(cache_dir.parent), "cache_policy": "lru", "cache_max_gb": str(1 / 1024)}

            fake_state_file = Path(td) / "should-never-be-created.json"
            original_state_file = self.jwsl.STATE_FILE
            self.jwsl.STATE_FILE = fake_state_file
            try:
                self.jwsl.enforce_cache_budget(config, state)
            finally:
                self.jwsl.STATE_FILE = original_state_file

            self.assertFalse(fake_state_file.exists(), "enforce_cache_budget must not call save_state() itself")


class JwslInternetAvailableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.jwsl = load_script_module("jwsl")

    def test_http_error_still_counts_as_online(self) -> None:
        # Regression guard: b.jw-cdn.org 403s a bare root HEAD request, but
        # that's a real HTTP response — proof the network path works, not
        # evidence of being offline. Previously any exception (including
        # HTTPError) was treated as "offline", so the daily check silently
        # never ran despite a working connection.
        def raise_http_error(*args, **kwargs):
            raise urllib.error.HTTPError("https://b.jw-cdn.org", 403, "Forbidden", {}, io.BytesIO(b""))

        with mock.patch.object(self.jwsl.urllib.request, "urlopen", raise_http_error):
            self.assertTrue(self.jwsl.internet_available())

    def test_connection_failure_counts_as_offline(self) -> None:
        def raise_url_error(*args, **kwargs):
            raise urllib.error.URLError("no route to host")

        with mock.patch.object(self.jwsl.urllib.request, "urlopen", raise_url_error):
            self.assertFalse(self.jwsl.internet_available())

    def test_success_counts_as_online(self) -> None:
        with mock.patch.object(self.jwsl.urllib.request, "urlopen", mock.MagicMock()):
            self.assertTrue(self.jwsl.internet_available())


class JwslAutoSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        # Fresh module + isolated state/config paths per test, so this never
        # touches the real ~/.config/maj-scripts/jwsl — same lesson as
        # test_never_writes_the_real_state_file_itself above.
        self.jwsl = load_script_module("jwsl")
        self._tmp = tempfile.TemporaryDirectory()
        tmp_dir = Path(self._tmp.name)
        self.jwsl.CONFIG_DIR = tmp_dir
        self.jwsl.STATE_FILE = tmp_dir / "state.json"
        self.jwsl.INDEX_DIR = tmp_dir / "index"
        self.sync_calls: list = []
        self.jwsl.sync_languages = lambda langs, config, state, quiet=False: self.sync_calls.append(langs)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def base_config(self, **overrides):
        config = {"languages": "ASL,FSL", "auto_sync": "true", "auto_sync_interval_hours": "24"}
        config.update(overrides)
        return config

    def test_skips_when_disabled_via_flag(self) -> None:
        args = argparse.Namespace(no_auto_sync=True)
        self.jwsl.maybe_auto_sync(args, self.base_config())
        self.assertFalse(self.jwsl.STATE_FILE.exists())
        self.assertEqual(self.sync_calls, [])

    def test_skips_when_disabled_via_config(self) -> None:
        args = argparse.Namespace(no_auto_sync=False)
        self.jwsl.maybe_auto_sync(args, self.base_config(auto_sync="false"))
        self.assertFalse(self.jwsl.STATE_FILE.exists())
        self.assertEqual(self.sync_calls, [])

    def test_skips_within_interval_no_network_check(self) -> None:
        args = argparse.Namespace(no_auto_sync=False)
        recent = time.time() - 3600  # 1 hour ago, well under the 24h default
        self.jwsl.save_state({"_auto_sync": {"last_attempt": recent}})
        self.jwsl.internet_available = lambda: (_ for _ in ()).throw(AssertionError("should not check connectivity when not due"))

        self.jwsl.maybe_auto_sync(args, self.base_config())

        self.assertEqual(self.jwsl.get_state()["_auto_sync"]["last_attempt"], recent)
        self.assertEqual(self.sync_calls, [])

    def test_marks_attempt_even_when_offline(self) -> None:
        args = argparse.Namespace(no_auto_sync=False)
        self.jwsl.save_state({"_auto_sync": {"last_attempt": 0}})
        self.jwsl.internet_available = lambda: False

        self.jwsl.maybe_auto_sync(args, self.base_config())

        self.assertGreater(self.jwsl.get_state()["_auto_sync"]["last_attempt"], time.time() - 10)
        self.assertEqual(self.sync_calls, [])

    def test_syncs_configured_languages_when_due_and_online(self) -> None:
        args = argparse.Namespace(no_auto_sync=False)
        self.jwsl.save_state({"_auto_sync": {"last_attempt": 0}})
        self.jwsl.internet_available = lambda: True

        self.jwsl.maybe_auto_sync(args, self.base_config(languages="ASL,FSL,BVL"))

        self.assertEqual(self.sync_calls, [["ASL", "FSL", "BVL"]])
        self.assertGreater(self.jwsl.get_state()["_auto_sync"]["last_attempt"], time.time() - 10)


if __name__ == "__main__":
    unittest.main()
