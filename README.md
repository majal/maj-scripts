# Maj Scripts, vibe version

LLMs have changed the way the programming world works. Welcome to the machine-made code era! 🤖

[![Tests](https://github.com/majal/maj-scripts-vibe/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/majal/maj-scripts-vibe/actions/workflows/tests.yml)

## Overview

`maj-scripts-vibe` is a home for utility scripts, all vibe-coded. 😎

If you're just here to use a script, start here. This README is the friendly map:

- Each script section tells you what the script does, what it needs, and the safest first commands to try.
- Use [Your Local Setup](#your-local-setup) when Python, Git, `ffmpeg`, or package managers need a little help.
- Use [Friendly Launchers](#friendly-launchers) if you prefer double-clicks, drag-and-drop, file pickers, or right-click actions.
- Looking for the jw.org content tools (`slverse`/formerly `jwsl`, `ffrife`, `jwdl`, `jwvideo-mux`)? They moved to their own repo: [`majal/jwkit`](https://github.com/majal/jwkit).

## Table of Contents

- [Overview](#overview)
- [Scripts](#scripts)
  - [`gmail-cleanup`](#gmail-cleanup)
  - [`printing-mode`](#printing-mode)
  - [`ubuntu-hibernate`](#ubuntu-hibernate)
  - [`wh`](#wh)
  - [`whisper`](#whisper)
- [Your Local Setup](#your-local-setup)
  - [Friendly Launchers](#friendly-launchers)
  - [Python](#python)
  - [Git](#git)
  - [Package Managers](#package-managers)
- [Contributing Docs](#contributing-docs)

## Scripts

### [`gmail-cleanup`](./gmail-cleanup)

`gmail-cleanup` is a local-first Gmail attachment cleanup CLI.

Full docs: [docs/gmail-cleanup.md](docs/gmail-cleanup.md)

[↑ TOC](#table-of-contents)

### [`printing-mode`](./printing-mode)

`printing-mode` toggles the Linux printing and printer-discovery stack.

Full docs: [docs/printing-mode.md](docs/printing-mode.md)

[↑ TOC](#table-of-contents)

### [`ubuntu-hibernate`](./ubuntu-hibernate)

`ubuntu-hibernate` is a guided hibernate doctor and setup helper for Ubuntu 26.04.

Full docs: [docs/ubuntu-hibernate.md](docs/ubuntu-hibernate.md)

[↑ TOC](#table-of-contents)

### [`wh`](./wh)

`wh` is a convenience wrapper for `magic-wormhole`.

Full docs: [docs/wh.md](docs/wh.md)

[↑ TOC](#table-of-contents)

### [`whisper`](./whisper)

`whisper` is a self-bootstrapping subtitle and transcription CLI.

Full docs: [docs/whisper.md](docs/whisper.md)

[↑ TOC](#table-of-contents)

## Your Local Setup

Use this section for shared prerequisites and friendlier ways to run scripts without living in a terminal. Script-specific notes can link back here instead of repeating the same setup steps everywhere.

### Friendly Launchers

These scripts stay command-line-first because that keeps them portable, scriptable, and easy to debug. Friendly launchers are thin wrappers around the same commands for people who prefer double-clicking, drag-and-drop, file pickers, or context menus.

Good launchers should:

- show command output or keep a log file so errors are not hidden
- pass selected files and folders through to the script without changing them
- keep the underlying command easy to inspect and edit
- rely on the shared [Python](#python), [Git](#git), and tool setup below

#### macOS Launchers

For a simple double-click launcher, create a `.command` file that runs a script from this repo. For drag-and-drop, create an Automator Application or Shortcuts workflow that accepts files or folders from Finder and passes them to the script.

Helpful macOS patterns:

- Finder Quick Actions work well for right-click workflows.
- Automator Applications work well for drag-and-drop workflows.
- A `.command` file should be executable with `chmod +x`.
- Keep Terminal visible while testing so setup prompts and errors are easy to see.

Example wrapper shape:

```zsh
#!/bin/zsh
cd /path/to/maj-scripts-vibe || exit 1
./script-name "$@"
```

#### Windows Launchers

For Windows, use a PowerShell script, a `.cmd` file, or a shortcut in the `Send to` folder. The `py` launcher is the safest default because it forwards arguments to Python scripts predictably.

Helpful Windows patterns:

- A `Send to` shortcut works well for right-click file workflows.
- A PowerShell wrapper can keep the window open after errors.
- Start with one selected file while testing, then try multiple files.
- If Windows blocks a downloaded script, unblock it from file Properties or use a local wrapper you created yourself.

Example wrapper shape:

```powershell
py C:\path\to\maj-scripts-vibe\script-name @args
```

#### Linux Launchers

For Linux desktops, use a `.desktop` launcher, a file-manager custom action, or a small shell wrapper. Nautilus, Nemo, Dolphin, and Thunar each expose custom actions a little differently, but the core idea is the same: pass selected files to the script and keep output visible.

Helpful Linux patterns:

- Use `Terminal=true` in `.desktop` launchers while testing.
- File-manager custom actions are often the best right-click workflow.
- A shell wrapper can normalize paths and write logs before calling the repo script.
- Desktop environments differ, so keep launcher docs practical rather than tied to one file manager.

Example `.desktop` command shape:

```ini
Exec=/path/to/maj-scripts-vibe/script-name %F
Terminal=true
```

#### Launcher Safety Notes

Treat launchers as convenience wrappers, not separate apps with different behavior. When a launcher is new, test it with a tiny throwaway file or a harmless preview command first. If a script offers a dry-run, doctor, or sample-file command, use that before handing it important files.

[↑ TOC](#table-of-contents)

### [Python](https://www.python.org/downloads/)

Most scripts in this repo are expected to use Python 3.

Check whether Python 3 is already available:

```bash
python3 --version
```

If that command works, you're probably already most of the way there. If not, the platform guidance below will help you get set up.

For this repo, a modern Python 3 release is the safe default.

Python setup by platform:

- [macOS](#python-on-macos)
- [Linux](#python-on-linux)
- [Windows](#python-on-windows)

#### [Python on macOS](https://www.python.org/downloads/macos/)

Do not assume a usable `python3` is already present. A quick check first can save time:

```bash
python3 --version
```

If `python3` is missing:

1. Install [Homebrew](#homebrew-macos) if needed.
2. Install Python with Homebrew.

For scripts that need compiled dependencies or multimedia tools, Xcode Command Line Tools may also be useful:

```bash
xcode-select --install
```

#### [Python on Linux](https://docs.python.org/3/using/unix.html)

Python 3 is often available already, but it is still worth checking first:

```bash
python3 --version
```

If it is missing, Debian/Ubuntu-style setup is a good baseline:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv ffmpeg
```

Other distros should use their normal package manager equivalents.

#### [Python on Windows](https://www.python.org/downloads/windows/)

On Windows, it is best to treat Python installation as an explicit setup step rather than assuming it is already present.

When running Python scripts from this repo on Windows, the safest default is:

```powershell
py <scriptname> [args]
```

The `py` launcher passes arguments after the script name through to the script itself.

First check:

```powershell
py --version
python --version
```

If Python is missing, install it using one of these routes:

- Official Python installer: <https://www.python.org/downloads/windows/>
- a package manager such as [`winget` or Chocolatey](#winget-and-chocolatey-windows)

After installation, verify:

```powershell
py --version
python --version
```

[↑ TOC](#table-of-contents)

### [Git](https://git-scm.com/)

Git is optional if you only want to download a ZIP and try one script. It becomes handy when you want to keep your local copy of this repo up to date without re-downloading everything by hand.

Check whether Git is already available:

```bash
git --version
```

If you have Git, you can make a local copy with:

```bash
git clone https://github.com/majal/maj-scripts-vibe.git
cd maj-scripts-vibe
```

Later, update that copy from inside the repo folder:

```bash
git pull
```

If Git feels like too much, downloading a fresh ZIP from GitHub is still okay. Git just makes updates tidier. If you prefer a visual app, [GitHub Desktop](https://desktop.github.com/) can clone the repo and update it with Fetch/Pull buttons.

[↑ TOC](#table-of-contents)

### Package Managers

Package managers help you install and update command-line tools without chasing individual downloads by hand.

Package manager setup by platform:

- [Homebrew (macOS)](#homebrew-macos)
- [winget and Chocolatey (Windows)](#winget-and-chocolatey-windows)

#### [Homebrew](https://brew.sh/) (macOS)

Install Homebrew by following the official instructions:

- <https://brew.sh/>

Verify Homebrew:

```bash
brew --version
```

Common examples:

```bash
brew install python
brew install ffmpeg
brew install git
```

You can use the same pattern for other command-line tools as new scripts are added to this repo.

Verify installed tools as needed:

```bash
python3 --version
ffmpeg -version
git --version
```

#### [winget](https://learn.microsoft.com/windows/package-manager/winget/) and [Chocolatey](https://chocolatey.org/) (Windows)

For most Windows users, `winget` is the simpler default choice because it is built into modern Windows versions. Chocolatey is also a solid option if you already use it.

Verify `winget` if available:

```powershell
winget --version
```

Common examples with `winget`:

```powershell
winget install Python.Python.3
winget install Gyan.FFmpeg
winget install Git.Git
```

Equivalent examples with Chocolatey:

```powershell
choco install python
choco install ffmpeg
choco install git
```

You can use the same pattern for other command-line tools as new scripts are added to this repo.

Verify installed tools as needed:

```powershell
py --version
ffmpeg -version
git --version
python --version
```

[↑ TOC](#table-of-contents)

## Contributing Docs

When future scripts are added, keep this README as the main navigation page and update it alongside the script so new tools stay easy to discover.

Keep `Your Local Setup` generic and reusable. Script-specific requirements, caveats, and quality-of-life notes should live in the relevant script section instead.

For quick repo checks, run the lightweight test harness before or after changes:

```bash
python3 -m tests
```

On Windows, use:

```powershell
py -m tests
```

The harness covers smoke checks for the top-level CLIs, README consistency checks, and focused behavior tests for `wh` and core `whisper` logic.

Detailed contributor and AI-agent rules live in [`AGENTS.md`](./AGENTS.md).

[↑ TOC](#table-of-contents)
