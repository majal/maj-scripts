from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from tests.support import load_script_module


class WhisperCoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.whisper = load_script_module("whisper")

    def tearDown(self) -> None:
        self.whisper.load_suppression_rules.cache_clear()
        self.whisper.load_glossary_replacement_items.cache_clear()

    def test_discover_target_files_filters_media_and_dedupes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.mp4"
            ignored = root / "notes.txt"
            media.write_text("video", encoding="utf-8")
            ignored.write_text("ignore me", encoding="utf-8")

            files = self.whisper.discover_target_files([media, root], recursive=False)

            self.assertEqual(files, [media])

    def test_runtime_has_module_discovers_without_importing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "crashy_probe_module.py").write_text(
                "raise RuntimeError('module import should not run during discovery')\n",
                encoding="utf-8",
            )

            with mock.patch.dict(os.environ, {"PYTHONPATH": str(root)}, clear=False):
                self.assertTrue(self.whisper.runtime_has_module(Path(sys.executable), "crashy_probe_module"))

    def test_parse_text_mapping_lines_reads_valid_entries(self) -> None:
        items = self.whisper.parse_text_mapping_lines(
            """
            # comment
            psalm 83 18 => Psalm 83:18
            wi fi = Wi-Fi
            """,
            Path("whisper-glossary.txt"),
        )

        self.assertEqual(
            items,
            (
                ("psalm 83 18", "Psalm 83:18"),
                ("wi fi", "Wi-Fi"),
            ),
        )

    def test_parse_text_mapping_lines_rejects_invalid_lines(self) -> None:
        with self.assertRaisesRegex(ValueError, "should use"):
            self.whisper.parse_text_mapping_lines("missing separator", Path("bad-glossary.txt"))

    def test_load_suppression_rules_supports_text_and_json_inputs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            text_path = root / "suppress.txt"
            json_path = root / "suppress.json"
            text_path.write_text(
                """
                # comment
                start: Welcome back
                any: Please subscribe
                thanks for watching
                end: See you next time
                """,
                encoding="utf-8",
            )
            json_path.write_text(
                '{"start": "Opening Song", "any": ["Midroll Reminder"], "end": ["Final Prayer"]}',
                encoding="utf-8",
            )

            text_rules = self.whisper.load_suppression_rules(text_path)
            json_rules = self.whisper.load_suppression_rules(json_path)

            self.assertEqual(text_rules.start, ("Welcome back",))
            self.assertEqual(text_rules.any, ("Please subscribe", "thanks for watching"))
            self.assertEqual(text_rules.end, ("See you next time",))
            self.assertEqual(json_rules.start, ("Opening Song",))
            self.assertEqual(json_rules.any, ("Midroll Reminder",))
            self.assertEqual(json_rules.end, ("Final Prayer",))

    def test_load_glossary_replacement_items_rejects_non_mapping_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "glossary.json"
            path.write_text(json.dumps(["not", "a", "mapping"]), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "JSON object of string replacements"):
                self.whisper.load_glossary_replacement_items(path)

    def test_load_suppression_rules_rejects_non_string_json_values(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "suppress.json"
            path.write_text(json.dumps({"any": ["ok", 123]}), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "string or list of strings"):
                self.whisper.load_suppression_rules(path)

    def test_postprocess_segments_normalizes_bible_refs_and_glossary_terms(self) -> None:
        segments = [
            {
                "start": 0.0,
                "end": 1.2,
                "text": "psalm 83 18 jehovah",
                "words": [
                    {"start": 0.0, "end": 0.2, "word": "psalm"},
                    {"start": 0.2, "end": 0.5, "word": "83"},
                    {"start": 0.5, "end": 0.8, "word": "18"},
                    {"start": 0.8, "end": 1.2, "word": "jehovah"},
                ],
            }
        ]

        processed = self.whisper.postprocess_segments(
            segments,
            normalize_bible_references=True,
            normalize_bible_reference_phrases=False,
            glossary_replacements=self.whisper.BUILT_IN_GLOSSARY_REPLACEMENTS,
            glossary_lengths=self.whisper.BUILT_IN_GLOSSARY_LENGTHS,
        )

        self.assertEqual(processed[0]["text"], "Psalm 83:18 Jehovah")
        self.assertEqual(
            [word["word"] for word in processed[0]["words"]],
            ["Psalm", "83:18", "Jehovah"],
        )

    def test_postprocess_segments_can_normalize_spoken_bible_reference_phrases(self) -> None:
        segments = [{"text": "psalm chapter 83 verse 18"}]

        processed = self.whisper.postprocess_segments(
            segments,
            normalize_bible_references=True,
            normalize_bible_reference_phrases=True,
            glossary_replacements=self.whisper.BUILT_IN_GLOSSARY_REPLACEMENTS,
            glossary_lengths=self.whisper.BUILT_IN_GLOSSARY_LENGTHS,
        )

        self.assertEqual(processed[0]["text"], "Psalm 83:18")
