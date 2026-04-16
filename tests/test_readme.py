from __future__ import annotations

import re
import unittest

from tests.support import REPO_ROOT


README_PATH = REPO_ROOT / "README.md"
SCRIPT_TEMPLATE_HEADINGS = (
    "What It Does",
    "Supported Platforms",
    "Dependencies",
    "Install / First Run Summary",
    "Common Usage Examples",
    "Important Behavior / Defaults",
    "Notes / Caveats",
)


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

    def test_scripts_section_stays_before_platform_setup(self) -> None:
        scripts_index = self.readme.find("\n## Scripts\n")
        platform_index = self.readme.find("\n## Platform Setup\n")

        self.assertNotEqual(scripts_index, -1, "README must include ## Scripts")
        self.assertNotEqual(platform_index, -1, "README must include ## Platform Setup")
        self.assertLess(scripts_index, platform_index, "## Scripts must stay above ## Platform Setup")

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

    def test_script_sections_keep_standard_template(self) -> None:
        for script_name in self.scripts:
            with self.subTest(script=script_name):
                body = script_section_body(self.readme, script_name)
                previous_index = -1

                for heading in SCRIPT_TEMPLATE_HEADINGS:
                    marker = f"#### {heading}"
                    index = body.find(marker)
                    self.assertNotEqual(index, -1, f"{script_name} missing {marker}")
                    self.assertGreater(index, previous_index, f"{marker} is out of order for {script_name}")
                    previous_index = index

                self.assertIn("[↑ TOC](#table-of-contents)", body)
