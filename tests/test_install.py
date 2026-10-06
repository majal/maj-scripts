from __future__ import annotations

import re
import subprocess
import unittest

from tests.support import REPO_ROOT
from tests.test_readme import root_scripts


def bash_tools(path: str) -> list[str]:
    match = re.search(r"^TOOLS=\((.*?)\)", (REPO_ROOT / path).read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"{path} has no TOOLS=(...) list"
    return match.group(1).split()


def ps_tools(path: str) -> list[str]:
    match = re.search(r"^\$Tools = @\((.*?)\)", (REPO_ROOT / path).read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"{path} has no $Tools list"
    return re.findall(r'"([^"]+)"', match.group(1))


class InstallerTest(unittest.TestCase):
    def test_unix_installers_list_every_root_script(self) -> None:
        for path in ("install.sh", "uninstall.sh"):
            with self.subTest(path=path):
                self.assertEqual(sorted(bash_tools(path)), root_scripts())

    def test_windows_installers_list_only_python_scripts(self) -> None:
        python_scripts = [
            name for name in root_scripts()
            if (REPO_ROOT / name).read_text(encoding="utf-8").splitlines()[0].startswith("#!/usr/bin/env python")
            and name != "ubuntu-hibernate"
        ]
        for path in ("install.ps1", "uninstall.ps1"):
            with self.subTest(path=path):
                self.assertEqual(sorted(ps_tools(path)), python_scripts)

    def test_shell_installers_parse(self) -> None:
        for path in ("install.sh", "uninstall.sh"):
            with self.subTest(path=path):
                result = subprocess.run(["bash", "-n", str(REPO_ROOT / path)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_windows_installer_checks_real_python_and_valid_winget_id(self) -> None:
        text = (REPO_ROOT / "install.ps1").read_text(encoding="utf-8")
        self.assertIn("Test-RealPython", text)
        self.assertRegex(text, r'Python\.Python\.3\.\d+')
        self.assertNotRegex(text, r'"Python\.Python\.3"')


if __name__ == "__main__":
    unittest.main()
