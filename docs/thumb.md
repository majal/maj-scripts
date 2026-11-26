# `thumb`

[← Back to README](../README.md#table-of-contents)

`thumb` generates aspect-ratio-preserving thumbnails for whole folders or individual files, using embedded video artwork when present or an FFmpeg-chosen representative frame otherwise.

## What It Does

- folder scans cover images only by default (`--videos` adds videos); files you name directly are always processed
- takes any mix of directories and files (default: the current directory; `-r` scans folders recursively)
- for folders, writes thumbnails to `./thumbnails` inside the folder (or `-o DIR`); for files you name directly, writes the thumbnail next to the source (`--file-output DIR` or `-o DIR` to change that), keeping aspect ratio so neither side exceeds `--size` (default 256 px)
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

One file, or several (thumbnails land beside each source):

```bash
thumb photo.jpg clip.mp4
```

Individual file into a different folder:

```bash
thumb -o ~/thumbs photo.jpg
```

Include videos in a folder scan:

```bash
thumb -r --videos ~/Media
```

Recursive, only some types, 4 parallel jobs:

```bash
thumb -r -j 4 --include '*.jpg' --include '*.png' ~/Media
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
- Folder scans skip videos unless `--videos` (or `--artwork-only`, which implies it) is given, because automatic frame choice is best-effort. Set `videos = true` in the config to make it the default.
- `--no-artwork` ignores embedded video artwork; `--artwork-only` skips videos that have none. The two are mutually exclusive.
- `--exclude` overrides `--include`; patterns match the basename or the path relative to the scanned directory.
- `--include`/`--exclude` filter folder scans only; a file you name directly is always processed (unsupported types are skipped with a note).
- `--quiet` hides per-file OK/SKIP lines; failures and the final summary still print.
- `--jobs 0` picks a parallelism automatically (default is 1).

## Notes / Caveats

- Relative `-o` / `--file-output` paths are created inside the scanned directory (or beside the named file), not the current working directory; absolute paths are used as-is.
- Optional defaults live in `~/.config/maj-scripts/thumb/config.toml` (Python 3.11+). Keys match the long options: `output`, `file_output`, `size`, `quality`, `format`, `suffix`, `samples`, `jobs`, `recursive`, `quiet`, `mtime_only`, `no_artwork`, `videos`. CLI flags win. Example:

  ```toml
  size = 320
  file_output = "thumbs"   # put per-file thumbnails in a thumbs/ folder beside the source
  ```
- Run `thumb --help` for the full option list.

[↑ Back to README TOC](../README.md#table-of-contents)
