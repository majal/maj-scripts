# Maj Scripts, vibe version

LLMs have changed the way the programming world works. Welcome to the machine-made code era! 🤖

## Overview

`maj-scripts-vibe` is a home for utility scripts, all vibe-coded. 😎

The root README is the main navigation page:

- shared setup guidance lives here
- each script gets its own section here
- future contributor and AI-agent documentation rules live in [`AGENTS.md`](./AGENTS.md)

## Table of Contents

- [Overview](#overview)
- [Scripts](#scripts)
  - [`wh`](#wh)
  - [`whisper`](#whisper)
- [Platform Setup](#platform-setup)
  - [Python](#python)
  - [Package Managers](#package-managers)
- [Contributing Docs](#contributing-docs)

## Scripts

### [`wh`](./wh)

`wh` is a convenience wrapper for `magic-wormhole`.

#### What It Does

- wraps the `wormhole` CLI
- auto-adds `--code-length=4` for code-generating flows
- passes all other commands through normally
- can help install `wormhole` when it is missing

#### Supported Platforms

- macOS
- Linux
- Windows

#### Dependencies

Shared prerequisites:

- [Python](#python)
- platform setup from [macOS](#python-on-macos), [Linux](#python-on-linux), or [Windows](#python-on-windows)

Primary external tool:

- `wormhole`

#### Install / First Run Summary

Basic first run:

```bash
wh send file.zip
```

If `wormhole` is missing, `wh` can suggest a likely install route and offer to run it for you.

#### Common Usage Examples

Send a file with a shorter generated code:

```bash
wh send file.zip
```

Receive using the normal prompt flow:

```bash
wh receive
```

Receive while allocating the code on this side:

```bash
wh receive --allocate
```

Pass through other `wormhole` commands:

```bash
wh help
```

#### Important Behavior / Defaults

- `wh` injects `--code-length=4` for `send` and `tx`.
- `wh` also injects `--code-length=4` for `receive --allocate` and receive aliases such as `rx`, `recv`, and `recieve`.
- `wh` does not inject another code-length flag if you already passed `--code-length`.
- `wh` leaves ordinary `receive` unchanged because the sender normally generates the code.
- Missing-`wormhole` install prompts use `Y/n`, where Enter means yes.

#### Notes / Caveats

- Package-manager support varies by system, so `wh` suggests the best install route it can find.

[↑ TOC](#table-of-contents)

### [`whisper`](./whisper)

`whisper` is a self-bootstrapping subtitle and transcription CLI.

#### What It Does

- accepts a media file or folder
- discovers supported audio/video files
- builds and manages its own Python runtime
- selects a backend based on the host, including MLX on Apple Silicon
- writes subtitles by default, can mux soft subtitle tracks into video containers, and can also write text output for MLX diagnostics

#### Supported Platforms

- macOS
- Linux
- Windows

MLX support is for Apple Silicon on macOS. Other environments use `faster-whisper`.

#### Dependencies

Shared prerequisites:

- [Python](#python)
- platform setup from [macOS](#python-on-macos), [Linux](#python-on-linux), or [Windows](#python-on-windows)

Useful system dependency:

- `ffmpeg` for media workflows, especially default speech-onset subtitle trimming, subtitle burn-in, and subtitle-track embedding

Script-specific note:

- On Apple Silicon, MLX runtimes can auto-select a more stable managed-runtime Python.

#### Install / First Run Summary

Basic first run:

```bash
whisper /path/to/file.mp4
```

Useful inspection/setup commands:

```bash
whisper --doctor
whisper --setup-only
```

On first run, `whisper` will:

- inspect the host
- choose a managed runtime
- install required Python packages into that runtime
- prompt before downloading packages unless `-y` / `--yes` is used

#### Common Usage Examples

Transcribe one file:

```bash
whisper /path/to/file.mp4
```

Choose a model explicitly:

```bash
whisper /path/to/file.mp4 --model=medium
```

Choose a language explicitly:

```bash
whisper /path/to/file.mp4 -l en
```

Write output to a chosen folder:

```bash
whisper /path/to/file.mp4 --outdir=/path/to/output
```

Embed a soft subtitle track into the output video:

```bash
whisper /path/to/file.mp4 --embed
```

Embed a soft subtitle track and replace the source video after muxing succeeds:

```bash
whisper /path/to/file.mp4 -e -i
```

Embed an edited matching sidecar subtitle file without retranscribing:

```bash
whisper /path/to/file.mp4 -f
whisper /path/to/file.mp4 -f /path/to/file.srt -i
```

Burn subtitles into a new video with an explicit AV1 encoder:

```bash
whisper /path/to/file.mp4 --burn --burn-vcodec=libsvtav1
```

Run MLX comparison diagnostics:

```bash
whisper /path/to/file.mp4 --mlx-word-timestamps=off
whisper /path/to/file.mp4 --mlx-output-format=text
whisper /path/to/file.mp4 --model=tiny --mlx-word-timestamps=off --mlx-output-format=text
```

#### Important Behavior / Defaults

- The script self-manages its runtime instead of requiring a manually prepared virtualenv.
- On Apple Silicon, MLX runtimes can auto-select a more stable managed-runtime Python.
- Default model selection is hardware-aware.
- Subtitle cue starts are speech-trimmed by default to avoid long lead-ins over music or ambient audio. Use `--no-speech-trim` to opt out.
- `--embed` keeps the original media streams and adds a soft subtitle track when the container supports it directly.
- `--embed-file` uses an existing `.srt` or `.ass` instead of retranscribing, and bare `-f` / `--embed-file` looks for a matching subtitle file next to the video. It runs directly in the launcher Python, skips backend loading, and reuses source audio language metadata when available.
- `--in-place` first writes to a temporary file, then replaces the original video only after a successful mux. The short alias is `-i`.
- `--font` sets the font family used for ASS and karaoke subtitle output. The short alias is `-F`.
- MP4 and MOV use `mov_text` for embedded text subtitles; ASS subtitles fall back to MKV so styling survives.
- `--burn` always re-encodes video because subtitle burn-in uses an `ffmpeg` video filter.
- `--burn-vcodec=auto` lets `ffmpeg` choose the video encoder, or you can pass a codec such as `libx264` or `libsvtav1`.
- MLX diagnostic flags are for comparison and investigation:
  - `--mlx-word-timestamps=auto|on|off`
  - `--mlx-output-format=auto|subtitle|text`
  - `--mlx-model-default=wrapper|official`
- The normal wrapper behavior stays subtitle-oriented unless you explicitly ask for a different comparison mode.

#### Notes / Caveats

- First-run setup can take longer because packages and models may need to be installed or downloaded.
- Soft subtitle embedding and burn-in both require `ffmpeg`, and the default speech-onset trim uses it when available.
- In-place embedding only works when the embedded output can stay in the same container; cases that need an MKV fallback still require plain `--embed`.
- MLX behavior can vary by machine, Python version, and model choice.

[↑ TOC](#table-of-contents)

## Platform Setup

Use this section for shared prerequisites. Script-specific notes can link back here instead of repeating the same setup steps everywhere.

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

Keep `Platform Setup` generic and reusable. Script-specific requirements, caveats, and quality-of-life notes should live in the relevant script section instead.

Detailed contributor and AI-agent rules live in [`AGENTS.md`](./AGENTS.md).

[↑ TOC](#table-of-contents)
