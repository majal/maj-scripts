from __future__ import annotations

import re
import unittest

from tests.support import REPO_ROOT


README_PATH = REPO_ROOT / "README.md"
DOCS_DIR = REPO_ROOT / "docs"
SCRIPT_TEMPLATE_HEADINGS = (
    "What It Does",
    "Supported Platforms",
    "Dependencies",
    "Install / First Run Summary",
    "Common Usage Examples",
    "Important Behavior / Defaults",
    "Notes / Caveats",
)


def doc_filename(script_name: str) -> str:
    """Full per-script docs now live in docs/<script>.md - see AGENTS.md's
    Growth Rule. A trailing .sh is stripped so e.g. jwvideo-mux-shortcuts.sh
    maps to docs/jwvideo-mux-shortcuts.md."""
    base = script_name[:-3] if script_name.endswith(".sh") else script_name
    return f"{base}.md"


def root_scripts() -> list[str]:
    scripts: list[str] = []
    for path in REPO_ROOT.iterdir():
        if not path.is_file() or path.name.startswith("."):
            continue
        try:
            first_line = path.read_text(encoding="utf-8").splitlines()[0]
        except (IndexError, UnicodeDecodeError):
            continue
        if first_line.startswith("#!"):
            scripts.append(path.name)
    return sorted(scripts)


def section_body(readme: str, heading: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(heading)}\n(?P<body>.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(readme)
    if match is None:
        raise AssertionError(f"Missing README section: {heading}")
    return match.group("body")


def script_section_body(readme: str, script_name: str) -> str:
    heading = f"### [`{script_name}`](./{script_name})"
    pattern = re.compile(
        rf"^{re.escape(heading)}\n(?P<body>.*?)(?=^### |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(readme)
    if match is None:
        raise AssertionError(f"Missing README script section: {heading}")
    return match.group("body")


class ReadmeConsistencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = README_PATH.read_text(encoding="utf-8")
        cls.scripts = root_scripts()

    def test_scripts_section_stays_before_local_setup(self) -> None:
        scripts_index = self.readme.find("\n## Scripts\n")
        setup_index = self.readme.find("\n## Your Local Setup\n")

        self.assertNotEqual(scripts_index, -1, "README must include ## Scripts")
        self.assertNotEqual(setup_index, -1, "README must include ## Your Local Setup")
        self.assertLess(scripts_index, setup_index, "## Scripts must stay above ## Your Local Setup")

    def test_root_scripts_are_in_toc_and_have_linked_sections(self) -> None:
        toc = section_body(self.readme, "## Table of Contents")

        for script_name in self.scripts:
            with self.subTest(script=script_name):
                self.assertIn(f"  - [`{script_name}`](#{script_name})", toc)
                self.assertIn(f"### [`{script_name}`](./{script_name})", self.readme)

    def test_documented_root_script_sections_link_existing_scripts(self) -> None:
        scripts_body = section_body(self.readme, "## Scripts")
        documented = re.findall(r"^### \[`([^`]+)`\]\(\./([^)]+)\)", scripts_body, re.MULTILINE)

        self.assertTrue(documented, "README ## Scripts should document at least one script")
        for script_name, linked_path in documented:
            with self.subTest(script=script_name):
                self.assertEqual(linked_path, script_name)
                self.assertTrue((REPO_ROOT / linked_path).is_file(), f"{linked_path} should exist")

        self.assertEqual(sorted(script_name for script_name, _ in documented), self.scripts)

    def test_script_sections_stay_short_and_link_to_docs(self) -> None:
        for script_name in self.scripts:
            with self.subTest(script=script_name):
                body = script_section_body(self.readme, script_name)
                doc_name = doc_filename(script_name)

                self.assertIn(
                    f"docs/{doc_name}", body,
                    f"{script_name}'s README section should link to docs/{doc_name}",
                )
                self.assertIn("[↑ TOC](#table-of-contents)", body)
                # The full template lives in docs/<script>.md now, not inline.
                for heading in SCRIPT_TEMPLATE_HEADINGS:
                    self.assertNotIn(f"#### {heading}", body, f"{script_name} should not inline {heading} in README")

    def test_doc_files_keep_standard_template(self) -> None:
        for script_name in self.scripts:
            with self.subTest(script=script_name):
                doc_path = DOCS_DIR / doc_filename(script_name)
                self.assertTrue(doc_path.is_file(), f"Missing {doc_path.relative_to(REPO_ROOT)}")

                text = doc_path.read_text(encoding="utf-8")
                self.assertIn("../README.md", text, f"{doc_path.name} should link back to the README")

                previous_index = -1
                for heading in SCRIPT_TEMPLATE_HEADINGS:
                    marker = f"## {heading}"
                    index = text.find(marker)
                    self.assertNotEqual(index, -1, f"{doc_path.name} missing {marker}")
                    self.assertGreater(index, previous_index, f"{marker} is out of order in {doc_path.name}")
                    previous_index = index
