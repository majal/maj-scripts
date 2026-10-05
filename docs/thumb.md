# `thumb`

[← Back to README](../README.md#table-of-contents)

`thumb` batch-generates aspect-ratio-preserving thumbnails for images and videos, using embedded video artwork when present or an FFmpeg-chosen representative frame otherwise.

## What It Does

- scans a directory (default: the current one, optionally `-r` recursive) for images and videos
- writes thumbnails to `./thumbnails` (or `-o DIR`), keeping aspect ratio so neither side exceeds `--size` (default 256 px)
- images are auto-oriented from EXIF; videos prefer embedded artwork, otherwise FFmpeg picks a representative frame sampled across nearly the whole timeline and `thumb` compares it with fallback timestamps to avoid black/blank frames
- the original extension stays in the output name to avoid collisions (`photo.png` → `photo.png.jpg`)

## Supported Platforms

- macOS
- Linux
- Windows: not tested (no platform-specific handling or tests yet)

## Dependencies

- Python 3 (standard library only)
- `ffmpeg` and `ffprobe`
- ImageMagick

## Install / First Run Summary

Install the dependencies, then preview what would happen without writing anything:

```bash
thumb --dry-run -r ~/Pictures
```

## Common Usage Examples

Thumbnail the current directory:

```bash
thumb
```

Recursive, only some types, 4 parallel jobs:

```bash
thumb -r -j 4 --include '*.jpg' --include '*.mp4' ~/Media
```

Rebuild only thumbnails whose source changed:

```bash
thumb --mtime-only ~/Pictures
```

WebP output at quality 80:

```bash
thumb --format webp --quality 80 .
```

## Important Behavior / Defaults

- Existing thumbnails are skipped unless `--force` (recreate all) or `--mtime-only` (recreate when the source is newer) is given.
- `--no-artwork` ignores embedded video artwork; `--artwork-only` skips videos that have none. The two are mutually exclusive.
- `--exclude` overrides `--include`; patterns match the basename or the path relative to the scanned directory.
- `--quiet` hides per-file OK/SKIP lines; failures and the final summary still print.
- `--jobs 0` picks a parallelism automatically (default is 1).

## Notes / Caveats

- Relative `-o` paths are created inside the scanned directory, not the current working directory.
- Run `thumb --help` for the full option list.

[↑ Back to README TOC](../README.md#table-of-contents)
