# `ffcut`

[← Back to README](../README.md#table-of-contents)

`ffcut` is a frame-accurate video cutter that uses only `ffmpeg`/`ffprobe`, stream-copying whatever GOPs it safely can and re-encoding just the partial edges.

## What It Does

- cuts `[START, END)` out of a video: the partial GOP at the start and the partial GOP at the end are re-encoded, everything fully inside that range is stream-copied untouched
- for H.264, H.265/HEVC, AV1, VP9, and VP8, it looks for real keyframes it can safely splice on; for H.265 specifically, only IDR/BLA (closed-GOP) keyframes count as safe — a CRA/open-GOP keyframe is deliberately rejected rather than risking a corrupt splice, and the whole requested segment is re-encoded instead
- for every other video codec ffmpeg can encode (MPEG-2, MPEG-4 part 2, ProRes, MJPEG, DNxHD, FFV1, Huffyuv, Theora), it re-encodes the exact requested segment - other streams are still copied
- carries over audio, subtitles, timed data streams, attached cover art, Matroska attachments, chapters (clipped and rebased to the new start), global metadata, and video rotation
- verifies its own output: re-decodes the spliced video before muxing (falling back to a full re-encode if a smart splice doesn't actually decode clean), then checks after the final mux that the video codec, audio/subtitle codec sets, cover art, and attachment counts all still match the source
- refuses to overwrite an existing output file unless you pass `--force`
- can open the result in `mpv` when it's done

## Supported Platforms

- macOS
- Linux
- Windows

## Dependencies

- [Python](../README.md#python)
- `ffmpeg` / `ffprobe` on `PATH`, with the encoders for whatever codec you're cutting (e.g. `libx264`, `libx265`, `libsvtav1`, `libvpx-vp9`)
- `mpv` (optional, only used for the auto-preview at the end)

## Install / First Run Summary

No install step beyond having `ffmpeg` on `PATH`. Basic run:

```bash
ffcut video.mp4 10.250 130.750
```

This writes `video - cut.mp4` next to the source and, if `mpv` is installed, opens it when done.

## Common Usage Examples

Cut using plain seconds:

```bash
ffcut video.mp4 10.250 130.750
```

Cut using `HH:MM:SS.mmm`:

```bash
ffcut video.mp4 00:10:23.456 00:12:34.567
```

Cut from a timestamp to the end of the file:

```bash
ffcut video.mkv 01:20 end
```

Cut using negative offsets from the end of the file:

```bash
ffcut video.mov -120 -10
```

Choose the output path explicitly and skip the `mpv` preview:

```bash
ffcut video.mp4 5 30 --no-play clip.mp4
```

Overwrite an existing output on purpose:

```bash
ffcut video.mp4 5 30 --force clip.mp4
```

Drop streams you don't want in the output, the same way `ffmpeg -an`/`-sn`/`-dn` would (short aliases work too):

```bash
ffcut video.mp4 10 60 -an -sn clip.mp4
```

Extract just the audio (and any subtitles/data you don't also drop) instead of cutting video at all:

```bash
ffcut video.mp4 10 60 --no-video audio-clip.m4a
```

## Important Behavior / Defaults

- default output path is `<name> - cut.<ext>` next to the source, unless a fourth argument is given
- `START`/`END` accept plain seconds, `HH:MM:SS(.mmm)`, `MM:SS(.mmm)`, the literal `start`/`end` (or `s`/`e`), or a negative number meaning "this many seconds before the end"
- if `END` lands within 250ms past the source's actual duration, it's silently snapped to the exact end instead of erroring
- `--no-verify` skips the post-splice decode check (faster, but a bad smart splice could slip through)
- `--keep-temp` keeps the working directory (created next to the output) instead of deleting it - useful for inspecting what a smart cut actually produced at each stage
- per-codec quality flags mirror the encoders used for re-encoded edges: `--h264-crf`/`--h264-preset`, `--hevc-crf`/`--hevc-preset`, `--av1-crf`/`--av1-preset`, `--vp9-crf`/`--vp9-cpu-used`, `--vp8-crf`/`--vp8-cpu-used`, and similar `--<codec>-q`/`--<codec>-profile` flags for the re-encode-only codecs; run `ffcut --help` for the full list and current defaults
- copied audio/subtitle packets can't be split mid-packet, so their boundaries can land up to a few tens of milliseconds off the requested cut point even when the video itself is frame-exact
- a timed data stream (e.g. GoPro telemetry, a timecode track) that has no packets at all inside the requested range is expected to disappear from the output - `ffcut` warns about it rather than treating it as a failure
- `--no-video`/`-vn`, `--no-audio`/`-an`, `--no-subs`/`-sn`, and `--no-data`/`-dn` mirror ffmpeg's own flags of the same name and drop those stream categories entirely from the output; `--no-cover` drops attached cover art, `--no-attachments` drops Matroska attachments (fonts, XML, etc.), and `--no-chapters` drops chapters
- `--no-video` skips the GOP-aware splice pipeline entirely (there's no video left to splice around) and just seeks and stream-copies whatever else you kept - it also implies dropping cover art, since that's a video stream too. Combining it with `--no-audio`, `--no-subs`, and `--no-data` all at once is rejected, since nothing would be left to write

## Notes / Caveats

- exactly one non-cover-art video stream is required; files with zero or multiple primary video streams are rejected
- H.265/HEVC content encoded with open GOPs (CRA keyframes) never gets a smart splice from this tool by design - LosslessCut and FFmpeg's own docs both note the same B-frame/reference-frame risk for arbitrary HEVC packet trimming, so the safer fallback is a full re-encode of the requested segment
- the working directory is created next to the output file (same filesystem, for a cheap final rename) and is cleaned up automatically unless `--keep-temp` is passed

[↑ Back to README TOC](../README.md#table-of-contents)
