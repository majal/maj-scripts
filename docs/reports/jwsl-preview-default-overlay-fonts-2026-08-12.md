---
name: jwsl-preview-default-overlay-fonts-2026-08-12
description: jwsl extract previews by default (-f/--write saves); delogo+drawtext overlay ported from ffv, skipped when SL equals source
metadata:
  type: project
  status: live
  updated: 2026-10-15
---

Same day as [[jwsl-rewrite-2026-08-12]], a second round of fixes landed
after the user actually ran the rewritten `jwsl`/`ffv` and hit several
regressions from the original SL/ffv bash script's behavior.

**`jwsl extract` now previews by default, matching old ffv exactly.**
Before this fix the rewrite always encoded and wrote an output file - the
opposite of old `SL/ffv`'s default (preview via ffplay/mpv, nothing
written; `-f`/`--ffmpeg` was the flag that wrote a file). This is now
restored: `-f`/`--write` on `jwsl extract` (and `ffv`) is required to
actually encode+save; without it, the verse plays live via `ffplay`
(fastest - filters applied directly on the stream, no encode at all) or,
with `-m`/`--play`, via `mpv` using a quick ultrafast temp clip (mpv can't
take `-vf` directly, same tradeoff the old script made). This also fixed
the "it redownloads every time" complaint: what looked like a redownload
was actually a full quality re-encode happening on every invocation
because there was no preview-only path at all.

**delogo+drawtext overlay was completely missing before this fix** - the
rewrite only ever drew a translated reference caption on top of the
source video's own burned-in caption, with no delogo to blur/remove the
original first, so two texts stacked visibly. Ported from old ffv's
`generate_filters()`: `build_overlay_filter()` in `jwsl` builds
delogo+drawtext+a small source-SL label (`drawtext_ll`), with `show=1`
(visible box outline, nothing actually blurred) for preview and `show=0`
(real removal) for `--write`. Box size is auto-measured via
`measure_text_size()` (shells out to `magick`+`identify`, like old ffv
did, with a character-count heuristic fallback if ImageMagick isn't
installed) instead of old ffv's manual `-w`/`-t` pixel offset flags.

**`default_target_lang` config key was already there but completely dead
code** - never read anywhere in the original rewrite. It's now wired in:
requesting the SL matching `default_target_lang` (e.g. this user's `FSL`)
skips delogo/drawtext entirely, since that language's own burned-in
caption is already correct and needs no relabeling - the direct analogue
of old ffv's hardcoded `lang_tr` comparison (`if [ "${ll}" = "${lang_tr}" ]`).

**Fonts auto-download via the Google Fonts CSS2 endpoint, not a
hardcoded repo path.** `google_fonts_ttf_url(family, weight)` in `jwsl`
reads `fonts.googleapis.com/css2?family=...&wght@N` with a plain
`Mozilla/5.0` UA (which gets served a `.ttf` instead of `.woff2`) and
regexes out the real `fonts.gstatic.com/.../*.ttf` URL - this resolves to
the family's *current* file rather than baking in one versioned CDN path
that Google rotates. `font_family` config (default `noto-sans-display`,
also `inter`/`google-sans-flex`) picks the family; `font_path` remains a
full manual override. Weights: 600 (SemiBold) for the main caption, 400
(Regular) for the delogo-sizing estimator - matches old ffv's
`fontfile`/`fontfile_estimator` split. All three families were pulled
into `~/.config/maj-scripts/jwsl/fonts/` and confirmed working through the
real `resolve_font_paths()` code path (not just downloaded standalone).
A frame-by-frame visual comparison against a real JW SL video's own
burned-in caption (Psalm 16:11, FSL - pulled via a single `-frames:v 1`
ffmpeg grab from the CDN URL) confirmed Noto Sans Display is a close
visual match, consistent with old ffv's original font choice - but this
is "close by eye," not a verified exact match against JW's actual
production source.

**RIFE auto-installer added** (`download_and_install_rife()`): fetches
the platform-matching zip from `nihui/rife-ncnn-vulkan`'s
`releases/latest` GitHub API, unzips into `CONFIG_DIR/bin/`, chmods the
binary executable, sets `rife_binary_path`. Wired into `jwsl setup`'s
interactive wizard (previously just printed manual-install instructions).
**Caveat found during this session: the actual multi-MB GitHub release
asset download stalls/times out inside this Claude Code sandbox's network
path** (confirmed via a standalone `curl -L` to the same release URL,
which also hung past 120s) even though `api.github.com` JSON calls and
small file downloads (fonts, a single video frame) worked fine. The
interactive prompt flow itself was verified correct (piped stdin answers
were consumed in the right order, reached the download call) - only the
large-binary transfer itself is affected. **How to apply:** don't trust
this sandbox to verify large-binary downloads end-to-end; the user needs
to run `jwsl setup` themselves in a real terminal to finish a RIFE
install. Small downloads (a `.ttf`, a single ffmpeg frame grab) are fine
to verify directly.

**`videotoolbox_quality_from_crf` formula was producing visibly bad
video.** The original rewrite's `100 - crf*3` put crf 20 (a fairly
high-quality x264 setting) at `q:v` 40, in videotoolbox's mediocre range.
Changed to `100 - crf`, putting crf 20 at `q:v` 80.

**Log readability**: blank lines now separate message groups in
`run_ffmpeg`/`interpolate_rife`/`cmd_extract`'s final summary, matching
old ffv's spacing. Also fixed a `Psalm 16:[11]` raw-list-repr bug in the
initial "Extracting..." print (`format_verses_label()`).

**How to apply:** if touching `jwsl`'s extract/overlay code further, keep
`build_overlay_filter()`/`preview_verse()`/`extract_verse()` in sync -
they share the same filter-building logic gated only by `show_box`.

## Follow-up round: perceived slowness, file size, outro, mpv focus (same day)

**"Videos look slower" was the RIFE-fallback framerate filter's motion-
blend artifact, not an actual speed/duration bug.** Measured directly
(Psalm 16:11 FSL, 31.2s verse): source segment duration 31.237s, our
30fps re-encode 31.231s, our 60fps `framerate`-filter output 31.233s - all
match within float noise, so wall-clock timing is NOT altered. What
changes is bitrate/frame count (30fps: 2.06 Mbps/936 frames; 60fps
blended: 4.65 Mbps/1874 frames) - the `framerate` filter (and
`minterpolate`) do motion-compensated *frame blending*, the same
technique behind the "soap opera effect" TVs are criticized for: motion
reads as artificially smooth/floaty/slow even though nothing about the
clip's actual duration changed. Real RIFE (AI frame synthesis) doesn't
have this problem, but silently substituting a blend filter whenever RIFE
isn't installed was giving people the artifact without realizing it.
Fixed: new `rife_fallback_engine` config (default `none`) - when
`interpolation_engine=rife` but no working `rife_binary_path`, default
behavior is now to just keep native fps with zero artifact instead of
auto-applying `framerate`; users who want the blended 60fps look anyway
despite the artifact can opt in with `rife_fallback_engine=framerate` (or
`minterpolate`).

**File size/quality data point** (same 31.2s clip, videotoolbox q:v 80
post-[[jwsl-preview-default-overlay-fonts-2026-08-12]] fix): raw source
~0.65 Mbps/2.9MB, our 30fps re-encode ~2.06 Mbps/8MB (~3.2x source
bitrate - intentional per [[jwsl-rewrite-2026-08-12]], re-encoding an
already-lossy source deliberately doesn't match its bitrate to avoid
compounding generation loss), 60fps-blended ~4.65 Mbps/18MB. Confirmed
`extract_mode=onthefly` (this user's actual configured default) really
does avoid downloading the whole chapter: the full chapter file is
11.7MB, the 31.2s verse-11 segment alone is ~2.9MB - proportional to its
share of the chapter's duration, not the whole thing.

**Outro/endscreen investigation for Psalm 16:11 (FSL): no evidence
found.** Checked three ways: (1) the per-verse marker JSON has an
`endTransitionDuration` field that sounded promising but was `0.000` for
every verse in this chapter, including the last one - metadata alone
doesn't flag a trailing bumper here; (2) compared the last verse's marked
end (109.509+31.231=140.740) against the container's real probed
duration (140.746) - a 6ms gap, i.e. essentially none, ruling out a
multi-second appended copyright card for *this* file; (3) frame-grabbed
every ~0.05s through the last 0.2s of the file - signer is still actively
mid-gesture in the very last decodable frame, no fade/black/card. **How
to apply:** if a specific book/chapter/language is found that *does* have
a trailing endscreen, the detection approach would be: ffprobe the real
container duration, compare to last-verse marker end, and if there's a
meaningful gap (or the marker's own tail overlaps a static/faded region),
corroborate with ffmpeg's `blackdetect`/`freezedetect` filters before
trimming - don't build this speculatively without a confirmed example to
calibrate against, since this specific NWT Bible-chapter SL video type
showed no evidence of it.

**mpv preview now takes window focus.** Old `subprocess.run(["mpv",
...])`/`subprocess.Popen(["mpv", ...])` call sites replaced with a shared
`launch_mpv()` helper: adds `--force-window=immediate` everywhere, and on
macOS specifically activates the launched process via `osascript`/System
Events (`set frontmost of (first process whose unix id is <pid>) to
true`), with a short retry loop since mpv needs a moment after Popen to
register its window. macOS needs this because mpv there is a bare CLI
binary (not a signed .app bundle), so a background-terminal-launched
process doesn't get the NSApplication activation a Dock/Finder launch
would. Linux/Windows rely on mpv's own `--focus-on=open` default (mpv
0.34+) plus `--force-window=immediate` - not independently verified on
those platforms in this session (no Linux/Windows environment available
here), only reasoned from mpv's documented behavior.

## Third round: CPU vs GPU benchmark, progress bars, black-screen non-finding

**Switched default `hardware_encoder` from `videotoolbox` to `cpu`
everywhere** (`detect_hardware_encoder()` in `jwsl`, plus this user's live
config) after directly benchmarking both on the same 31.2s/720p clip
(Psalm 16:11 FSL) at matched settings: libx264 crf20 preset slow produced
a 3.06MB file (SSIM 0.99752 vs the source) in 3.65s wall-clock; videotoolbox
at the quality setting mapped from the same crf20 produced an 8.05MB file
(SSIM 0.99786) in 3.05s. GPU's SSIM edge is imperceptible (+0.0003) for
2.6x the file size, and the 0.6s speed difference doesn't matter for
per-verse clips. Also tried matching bitrate explicitly instead of using
crf (700kbps VBR, close to this clip's ~650kbps source bitrate) on both
encoders: CPU still won on quality at the same size (SSIM 0.99723 vs
0.99633) - x264's rate-distortion efficiency beats videotoolbox's at a
fixed bitrate too, not just at matched perceptual-quality settings.
Conclusion: crf-based libx264 already lands close to source bitrate
naturally for this content (3.06MB output vs 2.9MB raw source) and beats
explicit bitrate-targeting on both encoders - no need for a
source-bitrate-matching mode, just default to CPU. GPU remains available
via `jwsl config set hardware_encoder videotoolbox` for anyone bulk-
processing many chapters where the small per-clip time cost compounds.

**"Black screen + copyright screen at the end of Psalm 16:11" - not found
in any file, needs more detail from the user to pin down.** Re-investigated
more rigorously than the first round (sparse manual frame sampling can
miss a short flash): ran ffmpeg's `blackdetect` filter over the *entire*
source chapter file (not just verse 11's window) and separately over three
different jwsl-produced output files (no-interpolation, framerate-blended,
and real-RIFE) - zero black segments detected anywhere, in any of them.
Whatever the user saw is not in the video file data itself (source or
ours) for this specific verse/language, at least not by blackdetect's
standard thresholds. Leading guess: mpv's post-playback idle/UI state, or
they watched via jw.org's own web/app player (which does have its own
copyright-bumper UI chrome, separate from the raw file) rather than a
jwsl-produced file. **How to apply:** don't build speculative outro-
trimming logic off this - if the user can pin down exactly which file and
which player showed it, re-run the same blackdetect check against that
specific combination before assuming it's a jwsl bug.

**Progress bars added for slow encode steps, threshold-gated at 4
seconds** so the common fast case (~3-4s per verse, per the benchmark
above) stays silent and only genuinely slow runs show anything.
`run_ffmpeg()` gained an optional `duration` param (the caller already
knows expected output seconds from the verse's start/end times) and, when
given, launches ffmpeg with `-progress pipe:1 -nostats`, parsing `out_time=`
lines via the existing `parse_hms()` helper to drive a `\r`-redrawn bar
(`print_time_progress()`). The RIFE binary itself has no built-in progress
output, so `run_rife()` polls the output PNG directory's file count
against the expected total (input frame count × 2, RIFE's own default)
instead (`print_count_progress()`) - this is the step that actually needs
it: measured at ~125-130s for this same 31.2s clip on the M3's GPU, by far
the slowest thing in the whole pipeline. Verified live end-to-end (not
just unit-tested): both the RIFE frame-count bar and the final PNG-merge
ffmpeg time bar rendered and redrew correctly through a real extract run.

**ffplay preview now gets the same focus treatment mpv already had.**
`launch_mpv()`'s macOS activation logic (see above) was mpv-specific;
factored the actual activation call out into `focus_process(pid)` and
added a parallel `launch_ffplay()` using it, since ffplay (the *default*
preview engine, not just the `-m`/mpv fallback) had the identical
bare-CLI-binary focus gap on macOS.

## Fourth round: RIFE extracted into its own tool, single-reencode achieved, ffslow gets real AI slow-mo

**RIFE interpolation moved out of `jwsl` into a new standalone `ffrife`
script** (`maj-scripts/ffrife`), per the user's own observation that
RIFE interpolation isn't Bible/JW-specific and has other uses. `ffrife`
is a self-contained CLI (`ffrife <input> -o <output> [--start S --end E]
[--vf FILTER] [--fps N]`, plus `ffrife setup`/`ffrife config`) with its
own config at `~/.config/maj-scripts/ffrife/config.toml` (this user's
existing RIFE install was *moved* there from `jwsl`'s old config dir, not
re-downloaded - `~/.config/maj-scripts/ffrife/bin/rife-ncnn-vulkan-20221029-macos/`).
`jwsl` now imports it as a sibling module via `importlib`/`SourceFileLoader`
(`load_ffrife()`, cached at module level) instead of carrying its own copy
of the PNG-extraction/RIFE-invocation/merge logic - `download_and_install_rife`,
`run_rife`, `interpolate_rife`, and the `rife_binary_path`/`rife_fallback_engine`
config keys are all gone from `jwsl` itself now. `jwsl`'s own encode-quality
settings (`hardware_encoder`/`video_crf`/etc.) still come from `jwsl`'s own
config, bridged into ffrife's config shape per-call via `ffrife_config_for()`
- avoids two separate config files needing to be kept in sync by hand.
`jwsl setup`'s rife flow now just delegates to `ffrife.cmd_setup()` instead
of duplicating the install wizard.

**This also answered the "dual re-encode" architecture question with a
real fix, not just an answer.** Before this round, EVERY interpolation
path (rife, framerate, minterpolate) worked by fully encoding to an
intermediate `tmp_out.mp4` first (trim + overlay baked in), then running
a *second* full encode pass just to add the fps filter - two lossy H.264
generations for a single verse. Now: `extract_verse()`'s framerate/
minterpolate paths fold the overlay filter and the fps filter into ONE
`-vf` chain in a single ffmpeg call, straight from the source - fully
single-pass, matching the "none" engine's cost exactly. The rife path
still has an unavoidable minimum of one lossy generation (ffrife's PNG
extraction and RIFE itself are lossless; only the final PNG→video merge
encodes) - `ffrife.interpolate()` takes the trim window and `-vf` chain
directly and extracts frames straight from the source too, so the
`tmp_out.mp4` intermediate is gone entirely, dropping rife from 2 lossy
generations to 1. Verified live end-to-end post-refactor: a real
extract with overlay+RIFE produced correct delogo/drawtext/label output
at 60fps with a single `Running: ... -vf delogo=...,drawtext=...,drawtext=...
in/%08d.png` line in the log (no intermediate encode step visible at all).

**`ffslow` (a general, non-JW slow-motion utility in `~/dig/bin/`, separate
repo from maj-scripts) gained an `--ai`/`-a` flag** using `ffrife` for real
AI slow-motion instead of naive `setpts=PTS/speedx` frame-holding. Plain
setpts stretching just holds existing frames longer - stretching 30fps
footage 2x effectively displays at 15fps-equivalent smoothness, choppy.
The fix: RIFE-interpolate the *slow* section(s) up to `source_fps/speedx`
first (so a 2x slowdown gets 60fps footage), then `setpts` stretch that
higher-frame-count footage - same technique commercial "AI slow-mo" tools
use. Normal-speed sections are just plain-cut, untouched.
**Regression hit and fixed during testing:** the first implementation
concatenated the per-section pieces via the concat *demuxer*
(`-f concat -i list.txt -c copy`) - since the RIFE'd pieces have a
different internal frame rate than the normal-speed pieces, stream-copy
concat doesn't reconcile the differing timebases and silently corrupts
the container's overall duration (measured: a piece set that should total
~34.5s came out declaring 68.97s, exactly ~2x). Fixed by switching to the
concat *filter* (`[0:v][1:v]...concat=n=N:v=1:a=0[out]`, operating on
decoded frames, one more re-encode generation but frame-rate-correct) -
matches how the original non-AI branch of this same script already did
concatenation. Verified with a real test render (2-section split, ~28s
normal + ~3.2s section stretched 2x with RIFE) after the fix: duration
34.5s, frame count internally consistent, no artifacts at the transition.
`fffast` (the fast-forward counterpart) was deliberately left unchanged -
speeding up footage means *dropping* frames, which doesn't benefit from
frame interpolation the way slow-motion does.

**How to apply:** any future RIFE-related work belongs in `ffrife`, not
back in `jwsl` - that separation is now load-bearing for `ffslow --ai`
too. Added `tests/test_ffrife.py` (config roundtrip, encode-arg parity
with jwsl, progress-bar math, CLI dispatch) and a
`JwslFfrifeIntegrationTest` class in `tests/test_jwsl.py` covering the
delegation - note that class uses per-test `setUp` (fresh module), not
shared `setUpClass`, because some of its tests monkeypatch
`jwsl.load_ffrife`/`build_overlay_filter` on the module object directly,
which would otherwise leak into later tests in the same class (hit this
exact bug while writing the tests - three unrelated-looking failures were
all one shared-state leak). Also added a proper README section for
`ffrife` (this repo's `test_readme.py` enforces a standard per-script
template for anything with a shebang at the repo root - a genuinely new
tool joining the pile of legacy scripts already documented as deferred in
`TODO.md` would have been the wrong call).
