# `jwvideo-mux` adaptive-video pilot

Status: design evidence only. No production code has been added to
`jwvideo-mux` yet.

## Goal

Avoid storing a complete video stream per language when the visual programme
is either identical or differs only in short localized sections (for example,
titles or name cards). Keep one ordinary, portable MKV mode as the safe
default, and add an optional space-saving library mode for mpv.

## Pilot results

A 1280x720, 23.976 fps, 198.615-second four-language clip was used as an
isolated test fixture.

- The Tagalog and Hiligaynon H.264 elementary-video payloads had the same
  SHA-256 hash. A normal MKV with one copied video stream and two copied audio
  streams played successfully in mpv. This is the simplest consolidation case.
- English and Tagalog had different encoded video payloads after 180.180
  seconds, but operator review found no meaningful visual-language difference.
  This was an encoding-only false positive, not evidence for a localized-video
  replacement. The clip therefore qualifies only for the exact-reuse analysis
  path where applicable.
- An mpv EDL with a shared video-only segment and a separately stored tail
  opened and decoded both before and after the transition. This proves EDL
  mechanics only; it does **not** prove that the selected fixture has a
  language-specific visual tail. An English SRT external stream was selected
  successfully with `--slang=tgl,eng` fallback.

The experiment used copied packets only for the source segments. The 180.180
second split was already a keyframe, so it did not require a boundary
re-encode. Future runs must not assume this: a non-keyframe split needs a
nearby safe keyframe or a narrowly re-encoded boundary.

## Proposed modes

### 1. Ordinary multi-track MKV

Keep the present behavior for maximum portability. It contains one complete
video track per selected video language and independently selectable audio and
subtitle tracks.

### 2. Exact shared-video MKV

When the *elementary video-stream* hashes are equal, retain a single copied
video stream and add all language audio/subtitle tracks. Label the video as
shared rather than pretending it has every language tag. This is a conventional
MKV and needs no mpv-specific feature.

### 3. Adaptive mpv library

For partially localized programmes, emit a small directory rather than trying
to make one magical MKV:

```text
programme/
  common-001.mkv
  tg-002.mkv
  hv-002.mkv
  audio-tg.mka
  audio-hv.mka
  subtitles-eng.srt
  subtitles-tg.srt
  presentation-tg.edl
  presentation-hv.edl
  manifest.json
```

Each language EDL is a virtual presentation: common segments interleaved with
only that language's replacement segments. It exposes the full language audio
and subtitle streams using EDL `new_stream` partitions. A small optional mpv
launcher or Lua script can choose the appropriate EDL and set `alang`/`slang`
with English as the subtitle fallback.

This is deliberately an mpv-oriented library, not a single-file archival
format. mpv documents EDL format v0 as changeable, so generated libraries
must record the mpv version and be smoke-tested when mpv is upgraded.

## Detection and safety contract

1. Probe every input and reject incompatible duration, resolution, pixel
   format, frame-rate, or timestamp layouts unless a later alignment feature
   explicitly handles them.
2. First hash copied elementary video streams. Equal hashes mean exact reuse;
   do not decode or re-encode merely to prove it again.
3. For unequal streams, compare normalized decoded frames. Exact `framemd5`
   equality is strong evidence for a shared range. SSIM/PSNR and perceptual
   fingerprints may nominate candidates, but every proposed localized range
   must include reviewable side-by-side frames/difference previews and require
   explicit operator approval before export or cleanup. Different encodes of
   the same image are not localized content.
4. Coalesce matching frames into sufficiently long ranges, then move cuts to
   safe keyframes. Record both the analytical and actual cut times in the
   manifest.
5. Extract video-only common/localized segments and audio-only MKA files with
   stream copy where possible. Preserve subtitles as external SRT/ASS or
   copied Matroska subtitle streams with correct BCP-47/ISO language tags.
6. Generate every language EDL, plus `manifest.json` containing source hashes,
   language-to-EDL mapping, cuts, stream metadata, tool versions, and expected
   durations.
7. Validate every presentation at the first frame, every splice boundary, and
   the final frame with mpv headless decoding. Validate language preference and
   English subtitle fallback explicitly.
8. Never delete source downloads in the adaptive mode. Write to a new output
   directory and require an explicit, separately implemented cleanup step only
   after manifest and playback verification.

## Important non-goals

- Matroska's ordinary tracks do not couple audio-language selection to a
  time-varying video choice. A full multi-video MKV remains independent tracks.
- mpv does not perform that coupling automatically. It can select tracks by
  language, while a dedicated launcher/Lua script can choose a language EDL.
- Matroska ordered chapters/linked segments are not the preferred solution:
  they are more complex, have uneven player support, and still do not provide
  the desired audio-to-localized-video binding.

## Implementation order

1. Add a read-only `--analyze-video-variants` report mode to `jwvideo-mux`.
2. Add tests with synthetic short clips covering exact equality, one localized
   interval, non-keyframe cuts, missing local subtitles, and incompatible
   sources.
3. Add an explicit `--adaptive-mpv-library` export mode behind a confirmation
   flag; do not alter the existing default MKV behavior.
4. Add an optional mpv helper only after the artifact and manifest contract are
   stable.
