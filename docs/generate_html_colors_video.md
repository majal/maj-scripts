# `generate_html_colors_video`

[← Back to README](../README.md#table-of-contents)

`generate_html_colors_video` renders a 12-hour 4K solid-color video for every named HTML/CSS color.

## What It Does

- generates one 4K (3840x2160) video per HTML/CSS named color (148 colors)
- each video is 12 hours long, a solid fill of that color
- names each output file `<hex>_<ColorName>.mp4`
- tags each video with title/artist/album/comment/copyright/description metadata built from the color name, hex, and RGB values

## Supported Platforms

- macOS
- Linux

## Dependencies

- `ffmpeg`
- optionally sources `${HOME}/bin/maj-source` if present (harmless if missing)

## Install / First Run Summary

No install step beyond having `ffmpeg` on `PATH`. Run it from an empty directory you're happy to fill with video files:

```bash
mkdir colors && cd colors
generate_html_colors_video
```

## Common Usage Examples

Generate the full set (run from a scratch directory):

```bash
generate_html_colors_video
```

There are no command-line options — every color is generated every run, in order.

## Important Behavior / Defaults

- Runs sequentially, one color at a time, and does not skip or resume — expect a very long total runtime (148 colors × up to 12 hours each if left to finish).
- Output is fixed at 4K; there's no flag to change resolution, duration, or color set.
- Existing output files with the same name are overwritten (`-y`).

## Notes / Caveats

- Each finished file is a full-length 12-hour render — expect large disk usage per color if you let it run to completion. Interrupt with Ctrl+C between colors if you only need a subset; the script has no built-in early-exit or color-selection flag.
- Displayed color may differ from the named value depending on your screen's color profile — the description text embedded in each file's metadata says as much.

[↑ Back to README TOC](../README.md#table-of-contents)
