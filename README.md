# maj-scripts-vibe

Standalone scripts for the `maj-scripts-vibe` repo.

## Table of Contents

- [Overview](#overview)
- [Scripts](#scripts)
  - [`whisper`](#script-whisper)
- [Bootstrap / Platform Setup](#bootstrap--platform-setup)
  - [Python](#python)
  - [macOS](#macos)
  - [Homebrew (macOS)](#homebrew-macos)
  - [Linux](#linux)
  - [Windows](#windows)
- [Script: `whisper`](#script-whisper)
- [Contributing Docs](#contributing-docs)

## Overview

`maj-scripts-vibe` is a home for utility scripts that may not be related to each other.

The root README is the main navigation page:

- shared setup guidance lives here
- each script gets its own section here
- future contributor and AI-agent documentation rules live in [`AGENTS.md`](./AGENTS.md)

[Back to TOC](#table-of-contents)

## Scripts

### `whisper`

Self-bootstrapping subtitle and transcription CLI for media files.

- Script file: [`whisper`](./whisper)
- Primary use: transcribe audio/video files and write subtitles or text output
- Notable behavior: manages its own runtime, can use MLX on Apple Silicon, and includes diagnostic controls for comparing MLX settings

[Back to TOC](#table-of-contents)

## Bootstrap / Platform Setup

Use this section for shared prerequisites. Script-specific notes should link back here instead of duplicating common setup instructions.

### Python

Most scripts in this repo are expected to use Python 3.

Check whether Python 3 is already available:

```bash
python3 --version
```

If that command works, you may already have enough to get started. If it does not, install Python using the platform guidance below.

For this repo, a modern Python 3 release is the safe default. `whisper` can also choose a stable managed-runtime Python automatically for MLX on Apple Silicon.

[Back to TOC](#table-of-contents)

### macOS

Do not assume a usable `python3` is already present. Check first:

```bash
python3 --version
```

If `python3` is missing:

1. Install Homebrew if needed.
2. Install Python with Homebrew.

For scripts that need compiled dependencies or multimedia tools, Xcode Command Line Tools may also be useful:

```bash
xcode-select --install
```

`whisper` also benefits from `ffmpeg` being installed.

[Back to TOC](#table-of-contents)

### Homebrew (macOS)

Install Homebrew by following the official instructions:

- <https://brew.sh/>

Then install Python:

```bash
brew install python
```

Optional but recommended for `whisper`:

```bash
brew install ffmpeg
```

Verify:

```bash
python3 --version
ffmpeg -version
```

[Back to TOC](#table-of-contents)

### Linux

Python 3 is often available already, but still verify first:

```bash
python3 --version
```

If it is missing, Debian/Ubuntu-style setup is a good baseline:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv ffmpeg
```

Other distros should use their normal package manager equivalents.

[Back to TOC](#table-of-contents)

### Windows

On Windows, it is best to treat Python installation as explicit setup rather than assuming it is already present.

First check:

```powershell
py --version
python --version
```

If Python is missing, install it using one of these routes:

- Official Python installer: <https://www.python.org/downloads/windows/>
- `winget`:

```powershell
winget install Python.Python.3
```

After installation, verify:

```powershell
py --version
python --version
```

For `whisper`, make sure Python is available in a normal terminal session before running the script.

[Back to TOC](#table-of-contents)

## Script: `whisper`

`whisper` is a self-bootstrapping subtitle and transcription CLI.

### What It Does

- accepts a media file or folder
- discovers supported audio/video files
- builds and manages its own Python runtime
- selects a backend based on the host, including MLX on Apple Silicon
- writes subtitles by default and can also write text output for MLX diagnostics

### Supported Platforms

- macOS
- Linux
- Windows

MLX support is for Apple Silicon on macOS. Other environments use `faster-whisper`.

### Dependencies

Shared prerequisites:

- [Python](#python)
- platform setup from [macOS](#macos), [Linux](#linux), or [Windows](#windows)

Useful system dependency:

- `ffmpeg` for media workflows, especially subtitle burn-in

### Install / First Run Summary

Basic first run:

```bash
whisper /path/to/file.mp4
```

Useful inspection/setup commands:

```bash
whisper --doctor
whisper --setup-only
```

The script will:

- inspect the host
- choose a managed runtime
- install required Python packages into that runtime
- prompt before downloading packages unless `--yes` is used

### Common Usage Examples

Transcribe one file:

```bash
whisper /path/to/file.mp4
```

Choose a model explicitly:

```bash
whisper /path/to/file.mp4 --model=medium
```

Write output to a chosen folder:

```bash
whisper /path/to/file.mp4 --outdir=/path/to/output
```

Run MLX comparison diagnostics:

```bash
whisper /path/to/file.mp4 --mlx-word-timestamps=off
whisper /path/to/file.mp4 --mlx-output-format=text
whisper /path/to/file.mp4 --model=tiny --mlx-word-timestamps=off --mlx-output-format=text
```

### Important Behavior / Defaults

- The script self-manages its runtime instead of requiring a manually prepared virtualenv.
- On Apple Silicon, MLX runtimes can auto-select a more stable managed-runtime Python.
- Default model selection is hardware-aware.
- MLX diagnostic flags are for comparison and investigation:
  - `--mlx-word-timestamps=auto|on|off`
  - `--mlx-output-format=auto|subtitle|text`
  - `--mlx-model-default=wrapper|official`
- The normal wrapper behavior stays subtitle-oriented unless you explicitly ask for a different comparison mode.

### Notes / Caveats

- First-run setup can take longer because packages and models may need to be installed or downloaded.
- MLX behavior can vary by machine, Python version, and model choice.
- Shared setup belongs in the [Bootstrap / Platform Setup](#bootstrap--platform-setup) section; avoid duplicating it when future scripts are added.

[Back to TOC](#table-of-contents)

## Contributing Docs

When future scripts are added, keep this README as the main navigation page and update it alongside the script.

Detailed contributor and AI-agent rules live in [`AGENTS.md`](./AGENTS.md).

[Back to TOC](#table-of-contents)
