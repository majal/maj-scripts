# `whisper`

[← Back to README](../README.md#table-of-contents)

`whisper` is a self-bootstrapping subtitle and transcription CLI.

## What It Does

- accepts a media file or folder
- discovers supported audio/video files
- builds and manages its own Python runtime
- selects a backend based on the host, including MLX on Apple Silicon
- normalizes common Bible-reference formatting mistakes by default, such as `Psalm 83 18` to `Psalm 83:18`
- writes subtitles by default, can also write plain-text transcripts, and can mux soft subtitle tracks into video containers

## Supported Platforms

- macOS
- Linux
- Windows

MLX support is for Apple Silicon on macOS. Other environments use `faster-whisper`.

## Dependencies

Shared prerequisites:

- [Python](../README.md#python)
- shared setup from [macOS](../README.md#python-on-macos), [Linux](../README.md#python-on-linux), or [Windows](../README.md#python-on-windows)

Useful system dependency:

- `ffmpeg` for media workflows, especially default speech-onset subtitle trimming, subtitle burn-in, and subtitle-track embedding

Script-specific note:

- MLX setup is managed by the script on Apple Silicon. Other machines use the managed `faster-whisper` runtime.

## Install / First Run Summary

Basic first run:

```bash
whisper /path/to/file.mp4
```

Useful inspection/setup commands:

```bash
whisper --doctor
whisper --doctor --json
whisper --doctor --deep
whisper --setup-only
```

On first run, `whisper` will:

- inspect the host
- choose a managed runtime
- install required Python packages into that runtime
- prompt before downloading packages unless `-y` / `--yes` is used

## Common Usage Examples

Transcribe one file:

```bash
whisper /path/to/file.mp4
```

Transcribe multiple explicit files from shell expansion:

```bash
whisper *.mkv
whisper *.mp3 *.mp4
```

Opt in to spoken Bible-reference parsing:

```bash
whisper /path/to/file.mp4 --bible-reference-phrases
```

Use a stricter subtitle readability profile:

```bash
whisper /path/to/file.mp4 --subtitle-style=strict
```

Layer in a custom glossary and review what postprocessing still looks suspicious:

```bash
whisper /path/to/file.mp4 --glossary=/path/to/whisper-glossary.txt --review-postprocessing
```

Suppress a known intro or outro from a shared phrase list:

```bash
whisper /path/to/file.mp4 --suppress-phrases=/path/to/whisper-suppress.txt
```

Write a plain-text transcript next to the normal subtitle output:

```bash
whisper /path/to/file.mp4 -t --paragraphs
```

Write only the transcript:

```bash
whisper /path/to/file.mp4 -T
```

Long option names are available too, such as `--transcript` and `--transcript-only`.

Write a speaker-labeled transcript:

```bash
whisper /path/to/file.mp4 -T --speaker-labels --paragraphs
```

`--diarize` is kept as a technical alias for `--speaker-labels`.

Preview the work plan without setup, installs, or transcription:

```bash
whisper /path/to/file.mp4 --plan
whisper /path/to/folder --recursive --plan --json
```

Create a tiny video plus matching subtitle sidecar for manual embed checks:

```bash
whisper --make-sample-media=/tmp/whisper-sample.mp4
whisper /tmp/whisper-sample.mp4 --embed-file
```

Retranscribe even when the expected subtitle or video output already exists:

```bash
whisper /path/to/file.mp4 --force
```

Keep repeated defaults in a project-local TOML config:

```toml
# .maj-scripts-whisper.toml
lang = "en"
subtitle_style = "strict"
speaker_labels = false
glossary = ["./whisper-glossary.txt"]
suppress_phrases = ["./whisper-suppress.txt"]
```

Transcribe recursive matches in batches instead of starting one `whisper` process per file:

```bash
find . -type f -name '*.mp4' -exec whisper '{}' +
find . -type f -name '*.mp4' -print0 | xargs -0 whisper
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
```

## Important Behavior / Defaults

- The script self-manages its runtime instead of requiring a manually prepared virtualenv.
- On Apple Silicon, MLX runtimes can auto-select a more stable managed-runtime Python.
- Default model selection is hardware-aware.
- `--plan` / `--dry-run` shows discovered files, selected backend/model, output paths, configured glossary and suppression files, speaker-label status, embed/burn actions, and whether `ffmpeg` is required without installing packages or transcribing.
- Normal `--doctor` checks installed runtime modules without importing native backends, which keeps routine diagnostics calmer around MLX/Metal crashes.
- `--doctor --json` prints machine-readable diagnostics for scripts, CI, and support notes.
- `--doctor --deep` explicitly imports installed runtime backends for deeper diagnostics. Use it when you want to isolate backend import failures and are comfortable with native packages being loaded.
- `--make-sample-media=PATH` creates a tiny video and matching `.srt` sidecar so you can test `--embed-file` without hunting for a media fixture.
- Existing expected outputs are skipped by default, so reruns resume safely instead of retranscribing finished files. Use `--force` to overwrite that skip behavior.
- `-t` / `--transcript` writes a `.txt` transcript alongside normal `.srt`/`.ass` output. If the expected sidecar subtitle already exists, it builds the transcript from that file instead of retranscribing unless `--force` is set.
- `-T` / `--transcript-only` writes only the `.txt` file and skips subtitle/video outputs.
- `--paragraphs` formats transcript text with blank lines between likely paragraphs, based on timing gaps and sentence boundaries. It does not affect subtitle output.
- `--speaker-labels` adds anonymous `Speaker 1`, `Speaker 2`, and similar labels to transcript output. It implies transcript output, leaves subtitles unlabeled, and has `--diarize` as a technical alias.
- Speaker labels are fully optional. They install larger ML packages only when requested, show a size warning first, reuse an existing global Hugging Face speaker model cache when one is already present, and otherwise keep speaker model files in the managed runtime area.
- `--clean-speaker-labels` removes optional speaker-label packages and the app-owned speaker-label model cache. It does not touch global Hugging Face caches.
- You can pass multiple explicit files and folders in one command, and duplicate matches are skipped after the first one.
- If you're using `find`, prefer batched forms such as `-exec whisper '{}' +` or `xargs -0 whisper`; plain `-exec whisper '{}' \;` launches a fresh `whisper` process for every file.
- Reusable CLI defaults can live in `~/.config/maj-scripts/whisper/config.toml` globally or `.maj-scripts-whisper.toml` in a project. Precedence is built-in defaults, global config, nearest project config, then CLI flags.
- Config files use TOML. Use `glossary = [...]` or `suppress_phrases = [...]` to replace earlier config-layer lists, and `extra_glossary = [...]` or `extra_suppress_phrases = [...]` to append to them.
- Common JW/Bible and general capitalization such as `Jehovah`, `Governing Body`, `Kingdom Hall`, `Bible`, `jw.org`, `OpenAI`, `ChatGPT`, `YouTube`, and `Wi-Fi` is normalized by default.
- Project glossary files named `.whisper-glossary.json`, `.whisper-glossary.txt`, `whisper-glossary.json`, or `whisper-glossary.txt` are auto-loaded from parent folders when present. You can stack extra glossary files explicitly with repeated `--glossary=PATH`.
- Text glossary files use `source => Replacement` lines, while JSON glossary files can be a plain object of string replacements. Suppression text files accept optional `start:`, `end:`, or `any:` prefixes per line, and JSON suppression files can use matching `start`, `end`, and `any` keys.
- Bible references such as `Psalm 83 18`, `Psalm 83-18`, `Psalm 83.18`, `Psalm 8318`, and range forms like `Psalm 83 18 19` are normalized by default. Use `--no-bible-reference-normalization` to opt out.
- Spoken forms such as `Psalm 83 verse 18`, `Psalm chapter 83 verse 18`, and `1 John chapter 4 verse 8` are available as an opt-in with `--bible-reference-phrases`.
- Subtitle cue starts and ends are speech-trimmed by default to avoid long lead-ins and long tails over music or ambient audio. Timed-word edges that sit outside detected speech are also pruned conservatively, cue timing is smoothed for readability, and obvious repeated-word glitches are collapsed conservatively when timed words are available. Use `--no-speech-trim` to opt out of the speech-aware cleanup pass.
- `--subtitle-style=balanced|strict` lets you keep the current balanced defaults or switch to a stricter readability profile with tighter line width and lower chars-per-second targets.
- Known boilerplate intros and outros can be suppressed with `--suppress-phrases=PATH`, and project suppression files named `.whisper-suppress.json`, `.whisper-suppress.txt`, `whisper-suppress.json`, or `whisper-suppress.txt` are auto-loaded from parent folders when present.
- `--review-postprocessing` / `--lint` does not rewrite extra text on its own; it reports leftover spoken Bible-reference phrases, dense subtitle cues, and other postprocessing things you may want to inspect.
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

## Notes / Caveats

- First-run setup can take longer because packages and models may need to be installed or downloaded.
- Speaker labels depend on pyannote and may require accepting model terms on Hugging Face plus setting `HF_TOKEN` or `HUGGINGFACE_TOKEN`.
- Soft subtitle embedding and burn-in both require `ffmpeg`, and the default speech-onset trim uses it when available.
- In-place embedding only works when the embedded output can stay in the same container; cases that need an MKV fallback still require plain `--embed`.
- MLX behavior can vary by machine, Python version, model choice, and the host Metal stack. If MLX fails or macOS reports that Python closed unexpectedly, try `--backend=faster-whisper` and use `--doctor --deep` only when you want an explicit native import check.

[↑ Back to README TOC](../README.md#table-of-contents)
