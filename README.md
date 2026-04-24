# Maj Scripts, vibe version

LLMs have changed the way the programming world works. Welcome to the machine-made code era! 🤖

[![Tests](https://github.com/majal/maj-scripts-vibe/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/majal/maj-scripts-vibe/actions/workflows/tests.yml)

## Overview

`maj-scripts-vibe` is a home for utility scripts, all vibe-coded. 😎

If you're just here to use a script, start here. This README is the friendly map:

- Each script section tells you what the script does, what it needs, and the safest first commands to try.
- Use [Your Local Setup](#your-local-setup) when Python, Git, `ffmpeg`, or package managers need a little help.
- Use [Friendly Launchers](#friendly-launchers) if you prefer double-clicks, drag-and-drop, file pickers, or right-click actions.

## Table of Contents

- [Overview](#overview)
- [Scripts](#scripts)
  - [`gmail-cleanup`](#gmail-cleanup)
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

#### What It Does

- searches Gmail with a normal Gmail query
- inspects matching messages for image and video attachments by default
- can optionally process PDF attachments too
- can use named presets for repeatable cleanup jobs, such as `pdf-archive`
- backs up selected attachments to a local folder you choose
- saves each removed file with deterministic recovery markers in filenames and metadata
- inserts a modified copy of the email back into Gmail with a visible backup note
- replaces HTML inline media references with visible placeholders that show the saved filename and search token
- can apply optional Gmail audit labels to cleaned copies and skipped originals
- can report remaining Gmail matches as actionable, false positives, or skipped before you apply changes
- can run a local `doctor` check for OAuth, Python modules, PDF tools, OCR tools, and password backends
- moves the original message to Gmail Trash after the modified copy is inserted

#### Supported Platforms

- macOS
- Linux
- Windows

OAuth sign-in opens a local browser flow.

#### Dependencies

Shared prerequisites:

- [Python](#python)
- shared setup from [macOS](#python-on-macos), [Linux](#python-on-linux), or [Windows](#python-on-windows)

Python packages:

- `google-api-python-client`
- `google-auth-oauthlib`
- `google-auth-httplib2`

System tools used on demand:

- a Google desktop OAuth client secret JSON stored outside this public repo
- `exiftool` for embedding the recovery marker into saved files during `--apply`
- `ffmpeg` and `ffprobe` for video metadata fallback and some image conversions
- Poppler tools (`pdfimages`, `pdfinfo`, `pdftocairo`, `pdftotext`) when you include PDFs
- `ocrmypdf` is preferred for PDF OCR sidecar text when you enable OCR modes; `tesseract` is the fallback OCR engine
- for passworded PDFs, `gmail-cleanup` will scan for external recovery tools and prefer `john` plus a `pdf2john` helper, then `pdfcrack`, then `qpdf`
- on Linux, `--pdf-original trash` uses the freedesktop/XDG Trash layout directly under `~/.local/share/Trash`

When a required dependency is missing, `gmail-cleanup` can suggest an install command and offer to run it. Use `-y` to auto-accept those prompts.

#### Install / First Run Summary

1. Create or reuse a Google Cloud project for this tool.
2. Enable the Gmail API in that project.
3. Configure the Google Auth Platform branding, audience, and data access for your own account.
4. Add these Gmail scopes:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.modify`
   - `https://www.googleapis.com/auth/gmail.insert`
5. Create a `Desktop app` OAuth client.
6. Download the OAuth client JSON and store it outside this repo.
7. Run a dry run once to approve access and create the token cache.

The script can offer to install missing Python packages when you first run it, but the manual command is:

```bash
python3 -m pip install --user google-api-python-client google-auth-oauthlib google-auth-httplib2
```

Point the script at the downloaded desktop OAuth client JSON:

```bash
export GMAIL_CLEANUP_OAUTH_CLIENT_SECRET=/path/to/client-secret.json
```

#### Personal OAuth Setup, Step by Step

This script is built for local, personal use. It is not trying to be a public SaaS. For that use case, the most practical Google setup is:

- `User type`: `External`
- `Publishing status`: `In production`
- expect the unverified-app warning for restricted Gmail scopes unless you go through Google verification

Use `In production`, not `Testing`, for your real personal setup. Google documents that test-user authorizations expire after 7 days in `Testing`, and refresh tokens issued with offline access expire too. `In production` removes that 7-day testing expiry, even though the app can still remain unverified for a small personal-use workflow.

Do this:

1. Go to the Google Cloud Console and create or select a project for this tool.
2. In that project, enable the Gmail API.
3. Open `Google Auth Platform`.
4. In `Branding`, set an app name, support email, and developer contact email.
5. In `Audience`, choose `External`.
6. Still in `Audience`, set the publishing status to `In production`.
7. In `Data Access`, add:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.modify`
   - `https://www.googleapis.com/auth/gmail.insert`
8. In `Clients`, create a new OAuth client with application type `Desktop app`.
9. Download the client JSON.
10. Store that JSON outside this repo, in an OS-local config path you control.
11. Point `gmail-cleanup` at that file with `--credentials`, `GMAIL_CLEANUP_OAUTH_CLIENT_SECRET`, or local config.
12. Run a dry run once so the browser approval flow can create the token cache.

Recommended Linux storage:

```bash
mkdir -p ~/.config/maj-scripts/gmail-cleanup
chmod 700 ~/.config/maj-scripts ~/.config/maj-scripts/gmail-cleanup
mv ~/Downloads/client_secret*.json ~/.config/maj-scripts/gmail-cleanup/client-secret.json
chmod 600 ~/.config/maj-scripts/gmail-cleanup/client-secret.json
```

The OAuth token cache should also stay outside this repo. By default the script uses an OS-local state path such as:

```text
~/.local/state/maj-scripts/gmail-cleanup/token.json
```

If you move it manually, keep its parent directory private and the token file readable only by your user.

If you ever want to rotate or revoke access:

- delete the local token cache file
- remove the app from your Google Account third-party access page
- rerun a dry run to approve access again

#### Advanced Protection Note

If your Google account uses Advanced Protection, Google may block the initial OAuth approval or later scope-change approvals with `400 policy_enforced`.

For this local tool, the practical sequence is:

1. keep Advanced Protection enabled normally
2. temporarily turn it off only right before the OAuth approval screen if Google blocks the request
3. complete the approval flow and let `gmail-cleanup` write the token cache
4. re-enable Advanced Protection afterward if you want to keep it

In local testing, once the broader token had already been granted and cached, `gmail-cleanup` continued working after Advanced Protection was turned back on.

Optional local-only config file outside the repo:

```toml
# ~/.config/maj-scripts/gmail-cleanup/config.toml
backup_dir = "/path/to/local-backup"
credentials = "/path/to/client-secret.json"
types = ["image", "video"]
# pdf_mode = "auto"
# pdf_original = "trash"
# pdf_password_mode = "skip"
# pdf_password_failure_action = "skip"
# pdf_password_date_range = "1930-2035"
# pdf_password_family_fail_limit = 3
# pdf_render_format = "auto"
# pdf_render_dpi = 300
# pdf_text_mode = "none"
# empty_after_removal = "skip"
# request_profile = "moderate"
# quota_units_per_second = 125
# progress_format = "text"
# audit_labels = false
# label_processed = "gmail-cleanup/processed"
# label_review = "gmail-cleanup/review"
# token_cache = "/path/to/private-state/token.json"
# gmail_user = "me"
# max_results = 50
```

Start with a dry run. The first successful sign-in will open a local browser OAuth flow and create the token cache:

```bash
gmail-cleanup extract-media --query 'has:attachment' --backup-dir /path/to/local-backup
```

#### Common Usage Examples

Preview which image and video attachments would be extracted:

```bash
gmail-cleanup extract-media --query 'has:attachment older_than:365d' --backup-dir /path/to/local-backup
```

Actually back up media files, rewrite the kept Gmail copy, and trash the original:

```bash
gmail-cleanup extract-media --query 'has:attachment larger:5M' --backup-dir /path/to/local-backup --apply
```

Include PDFs and turn them into page images, preferring direct page-image extraction for scanned PDFs and trashing the staged local PDF afterward:

```bash
gmail-cleanup extract-media --query 'has:attachment older_than:365d larger:5M' --types image,video,pdf --pdf-mode auto --pdf-original trash --apply -v
```

Include PDFs, delegate low-hanging weak password recovery to any detected external backend, keep native PDF text in the cleaned email, and record unresolved passworded PDFs for manual review:

```bash
gmail-cleanup extract-media --query 'filename:pdf' --types pdf --pdf-mode auto --pdf-original trash --pdf-password-mode low-hanging --pdf-password-date-range 1930-2035 --pdf-text-mode native --max-results 5000 --apply -v
```

Run the full PDF archive cycle against non-Trash/non-Spam mail: convert or extract PDF pages to images, retain searchable text when possible, remove the Gmail PDF attachments, move staged local originals to OS Trash, and remove unopened passworded PDFs too after leaving a note:

```bash
gmail-cleanup extract-media \
  --query 'filename:pdf -in:trash -in:spam' \
  --backup-dir /path/to/local-backup \
  --max-results 5000 \
  --types pdf \
  --pdf-mode auto \
  --pdf-original trash \
  --pdf-password-mode low-hanging \
  --pdf-password-failure-action trash-original \
  --pdf-password-date-range 1930-2035 \
  --pdf-text-mode auto \
  --empty-after-removal note-only \
  --request-profile conservative \
  --quota-units-per-second 80 \
  --apply \
  -v
```

The same PDF archive cycle is available as a preset so humans and agents do not need to retype the long option list:

```bash
gmail-cleanup extract-media --preset pdf-archive --backup-dir /path/to/local-backup --apply -v
```

Apply Gmail audit labels while running the preset. Cleaned replacement messages get the processed label; skipped originals get the review label:

```bash
gmail-cleanup extract-media --preset pdf-archive --backup-dir /path/to/local-backup --audit-labels --apply -v
```

Use custom audit label names:

```bash
gmail-cleanup extract-media --preset pdf-archive --backup-dir /path/to/local-backup --label-processed 'gmail-cleanup/done' --label-review 'gmail-cleanup/manual-review' --apply
```

Report what still matches the PDF preset without changing Gmail:

```bash
gmail-cleanup report --preset pdf-archive
```

Run a local setup check:

```bash
gmail-cleanup doctor
```

Use the same cycle from an agent or unattended runner, with structured progress on stderr and a JSON final summary on stdout:

```bash
gmail-cleanup extract-media --preset pdf-archive --backup-dir /path/to/local-backup --progress-format jsonl --json --apply
```

Ask an agent for a machine-readable remaining-work report:

```bash
gmail-cleanup report --preset pdf-archive --json
```

Ask an agent for machine-readable local setup diagnostics:

```bash
gmail-cleanup doctor --json
```

Include PDFs but keep the original PDF as the backup artifact instead of deriving page images:

```bash
gmail-cleanup extract-media --query 'filename:pdf older_than:365d' --types pdf --pdf-mode backup --apply
```

Force rendered PDF pages as PNG at 300 DPI:

```bash
gmail-cleanup extract-media --query 'filename:pdf' --types pdf --pdf-mode render-pages --pdf-render-format png --pdf-render-dpi 300 --apply
```

When removing attachments would otherwise leave an empty email, keep a searchable note-only replacement instead of skipping it:

```bash
gmail-cleanup extract-media --query 'filename:pdf' --types pdf --empty-after-removal note-only --apply
```

Show per-message progress during a long apply run:

```bash
gmail-cleanup extract-media --query 'has:attachment larger:5M' --backup-dir /path/to/local-backup --apply -v
```

Inspect more than 500 matches by giving a larger limit; the Gmail API paging is handled for you:

```bash
gmail-cleanup extract-media --query 'filename:pdf' --types pdf --max-results 5000
```

Increase detail for file-level and inspection-level progress:

```bash
gmail-cleanup extract-media --query 'has:attachment larger:5M' --backup-dir /path/to/local-backup --apply -vv
gmail-cleanup extract-media --query 'has:attachment larger:5M' --backup-dir /path/to/local-backup --apply -vvv
```

Emit structured JSONL progress on stderr for agents or unattended runs:

```bash
gmail-cleanup extract-media --query 'filename:pdf' --types pdf --progress-format jsonl --json
```

Use a different inspection profile when you want to trade speed for fewer Gmail concurrency errors:

```bash
gmail-cleanup extract-media --query 'filename:pdf' --types pdf --request-profile conservative --max-results 5000
gmail-cleanup extract-media --query 'filename:pdf' --types pdf --request-profile aggressive --quota-units-per-second 175 --max-results 5000
```

Auto-accept dependency install prompts during a local run:

```bash
gmail-cleanup extract-media --query 'has:attachment' --apply -y
```

Limit the inspection pass while you test a query:

```bash
gmail-cleanup extract-media --query 'label:inbox has:attachment' --backup-dir /path/to/local-backup --max-results 10
```

Write the final summary as JSON:

```bash
gmail-cleanup extract-media --query 'has:attachment filename:jpg' --backup-dir /path/to/local-backup --json
```

Agent-friendly review artifacts are written as JSONL too:

- `manifest.jsonl` for applied messages
- `apply-queue.jsonl` for the planned apply queue, so interrupted runs can resume without listing the whole Gmail query again
- `passworded-pdfs.jsonl` for passworded PDFs that were left unchanged for manual review

#### Important Behavior / Defaults

- The default mode is a dry run. Nothing in Gmail or on disk changes unless you pass `--apply`.
- `--preset pdf-archive` expands to `filename:pdf -in:trash -in:spam`, `--types pdf`, `--pdf-mode auto`, `--pdf-original trash`, `--pdf-password-mode low-hanging`, `--pdf-password-failure-action trash-original`, `--pdf-text-mode auto`, `--empty-after-removal note-only`, conservative request pacing, and `--max-results 5000`. You can still override individual options on the same command.
- The default attachment types are `image,video`. PDFs are opt-in with `--types image,video,pdf` or `--types pdf`.
- `gmail-cleanup report` uses the same query, preset, and extraction settings as `extract-media`, but only lists and classifies matched messages. It is useful after a run to separate real remaining work from Gmail search false positives.
- `gmail-cleanup doctor` does not call Gmail. It checks local config paths, token scopes, Python imports, external tools, and trash support so humans and agents can see what is ready before a long run.
- `--audit-labels` creates or reuses `gmail-cleanup/processed` and `gmail-cleanup/review`. `--label-processed` and `--label-review` let you set explicit labels without enabling both defaults.
- Current PDF modes are `auto`, `render-pages`, `extract-images`, and `backup`.
- PDFs are selected by MIME type when Gmail reports `application/pdf`, and by `.pdf` filename when Gmail reports a generic type such as `application/octet-stream`.
- `--pdf-mode auto` prefers direct page-image extraction for scanned/image-heavy PDFs when possible, and otherwise renders every page to images.
- `--pdf-password-mode skip` leaves passworded PDFs untouched and records them for manual review; `infer` tries email/body-derived hints; `low-hanging` builds a bounded candidate set such as `last4`, `last6`, and `ddmmmyyyy` within `--pdf-password-date-range` and hands those candidates to an external backend when one is available.
- `--pdf-password-failure-action skip` leaves unopened passworded PDFs unchanged. `trash-original` removes the PDF attachment from Gmail, stamps the downloaded original PDF with the cleanup marker when possible, moves that local original PDF to the OS Trash, and leaves a note in the cleaned email. The same fallback is used for unreadable or corrupt PDFs that cannot be converted.
- Successful PDF passwords are cached in OS-local state outside the repo with user-only permissions and are retried before any new cracking attempt. Recipe-family learning still tracks sender/file fingerprints separately so future guesses can be ordered better even when the exact password is not yet cached.
- Failed PDF password attempts are also tracked by sender domain plus digit-normalized filename pattern. After `--pdf-password-family-fail-limit` misses for the same family, future files in that family skip cracking attempts and go straight to manual review. Use `--pdf-password-family-fail-limit 0` or `--no-pdf-password-family-backoff` to disable that behavior.
- `--pdf-text-mode native` retains searchable native PDF text in the cleaned email when Poppler can extract it. `ocr` uses OCR text, and `auto` prefers native text and falls back to OCR.
- Extracted files are written under `<backup-dir>/<gmail-message-id>/`, with a `manifest.jsonl` audit log at the backup root.
- Passworded PDFs that could not be opened are recorded in `<backup-dir>/passworded-pdfs.jsonl`.
- Saved filenames are prefixed with a deterministic token like `gcm-<message-id>-<index>__original.jpg`; Google Photos supports exact-text filename search when you use quotation marks.
- Existing deterministic `gcm-*` backup files are reused on reruns, even if metadata stamping changed their bytes after the original extraction. This keeps interrupted runs from creating `__2` duplicates.
- During `--apply`, the same marker is embedded into saved file metadata too. For images the script stamps XMP/IPTC/EXIF description fields; for QuickTime-family videos it stamps comment/description fields plus XMP. When `exiftool` cannot write a video container directly, `gmail-cleanup` falls back to `ffmpeg` container metadata. Backup-mode PDFs are stamped too.
- The modified Gmail copy keeps the thread ID and existing labels except `TRASH`, `SPAM`, and `DRAFT`.
- The original message is moved to Gmail Trash after the modified copy is inserted. It is not permanently deleted by this workflow.
- Gmail Trash and Spam are not included by default because the Gmail API list call is made without `includeSpamTrash=true`.
- If your Gmail query matches `SENT` mail, those messages are processed too; `gmail-cleanup` does not exclude sent mail on its own.
- OAuth token cache defaults to an OS-local state directory outside the repo. Resolved PDF password and failed-family caches live there too so future runs can reuse known statement passwords and avoid repeated misses without storing anything in this public repo.
- `--pdf-original keep` keeps the staged local PDF, `trash` moves it to the OS trash after derived outputs succeed, and `discard` deletes the staged local PDF. `--pdf-mode backup` keeps the original PDF regardless.
- `--empty-after-removal skip` leaves attachment-only mail unchanged; `note-only` inserts a cleaned replacement that keeps the backup note and retained text so the thread stays searchable.
- Google publishes a Gmail API per-user limit of 15,000 quota units per minute, or 250 units per second. Relevant method costs are `messages.get` 5 units, `messages.list` 5 units, `threads.get` 10 units, `messages.insert` 25 units, and `messages.trash` 5 units. `gmail-cleanup` paces requests below that with `--quota-units-per-second`.
- Gmail also has an unpublished per-user concurrent request limit. Batches count as their inner requests and large or parallel batches can still trigger `429 Too many concurrent requests for user`, so every request profile keeps same-user Gmail API calls serialized.
- `--request-profile moderate` is the default. `conservative` uses smaller inspection batches and lower quota pacing; `aggressive` uses larger batches and a higher quota target, but still leaves room below Google's published per-user limit. If Gmail returns `403 rateLimitExceeded`, `403 userRateLimitExceeded`, `429`, or transient read failures, the run backs off and retries; rate-limit responses also downgrade the profile automatically.
- `--progress-format jsonl` writes machine-readable progress events to stderr while keeping the final summary behavior unchanged.
- `--apply` resumes from `<backup-dir>/apply-queue.jsonl` and `<backup-dir>/manifest.jsonl` by default. If the queued work matches the same query, max-results, and extraction settings, the script skips the initial Gmail list call and fetches only pending queued IDs. Use `--no-resume` only when you intentionally want to ignore local resume state.
- `-v` reports per-message progress, `-vv` adds file/metadata steps, and `-vvv` adds message inspection detail.
- `-y` auto-accepts dependency install prompts.
- Local-only defaults can live in `~/.config/maj-scripts/gmail-cleanup/config.toml` on Linux, with equivalent OS-local paths on macOS and Windows.
- External password backend preference order is: `john` plus `pdf2john`, then `pdfcrack`, then `qpdf`, then the built-in fallback checker.

#### Notes / Caveats

- `gmail.readonly`, `gmail.modify`, and `gmail.insert` are restricted Gmail scopes, so this script is intended for local/operator use rather than a public SaaS.
- Keep the OAuth client secret JSON and token cache outside this repo. Use `--credentials` or `GMAIL_CLEANUP_OAUTH_CLIENT_SECRET`, and prefer OS-local config/state directories with user-only permissions.
- On Linux, PDF trashing uses the freedesktop/XDG Trash layout directly instead of relying on `gio`. That works more predictably for backup folders that sit on other mounts or btrfs subvolumes.
- Gmail API calls now use an explicit HTTP timeout so a slow mailbox scan is less likely to hang forever on one request.
- Large inspection runs are now done with Gmail batch requests. You will see the exact Gmail match count immediately after the initial `messages.list` step, before the script starts fetching raw messages.
- During `--apply`, inspection and apply now overlap through a bounded in-memory queue, so the run can start rewriting early without waiting for the entire mailbox plan. Gmail writes still stay serialized.
- Gmail insert/trash writes retry transient transport failures such as socket timeouts, connection resets, and TLS EOFs. If a connection drops during insert and the local backup folder already existed, the script checks the Gmail thread for an already-inserted cleanup copy before inserting again.
- Dependency auto-install is best-effort. Review the suggested command before you allow it to run, especially on systems where package names differ.
- Signed or encrypted messages are skipped because rewriting them would invalidate the original protections.
- Password-protected or encrypted PDFs are skipped at apply time instead of aborting the whole batch unless `--pdf-password-mode infer` or `low-hanging` can open them from bounded guesses. `gmail-cleanup` is not meant to be a general cracking tool; it generates candidate passwords from email context and hands them to external tools when available. Unresolved passworded PDFs are logged for manual review with the attempted recipe families.
- Some systems ship `john` without the `pdf2john` helper. In that case the John backend is considered unavailable and the script falls back to the next available tool.
- OCR uses `ocrmypdf` when available for sidecar text extraction and falls back to rendered-page OCR with `tesseract` when needed or when the PDF is already password-opened in-process.
- PDF thumbnail generation and compression are still not implemented. The current PDF controls cover backup, page rendering, direct page-image extraction, native text retention, and OCR text retention.

[↑ TOC](#table-of-contents)

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
- shared setup from [macOS](#python-on-macos), [Linux](#python-on-linux), or [Windows](#python-on-windows)

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
- normalizes common Bible-reference formatting mistakes by default, such as `Psalm 83 18` to `Psalm 83:18`
- writes subtitles by default, can also write plain-text transcripts, and can mux soft subtitle tracks into video containers

#### Supported Platforms

- macOS
- Linux
- Windows

MLX support is for Apple Silicon on macOS. Other environments use `faster-whisper`.

#### Dependencies

Shared prerequisites:

- [Python](#python)
- shared setup from [macOS](#python-on-macos), [Linux](#python-on-linux), or [Windows](#python-on-windows)

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
whisper --doctor --json
whisper --doctor --deep
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
whisper /path/to/file.mp4 -t
whisper /path/to/file.mp4 --transcript
whisper /path/to/file.mp4 -t --paragraphs
```

Write only the transcript:

```bash
whisper /path/to/file.mp4 -T
whisper /path/to/file.mp4 --transcript-only
```

Write a speaker-labeled transcript:

```bash
whisper /path/to/file.mp4 -T --speaker-labels --paragraphs
whisper /path/to/file.mp4 -T --diarize
```

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
whisper /path/to/file.mp4 --model=tiny --mlx-word-timestamps=off --mlx-output-format=text
```

#### Important Behavior / Defaults

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

#### Notes / Caveats

- First-run setup can take longer because packages and models may need to be installed or downloaded.
- Speaker labels depend on pyannote and may require accepting model terms on Hugging Face plus setting `HF_TOKEN` or `HUGGINGFACE_TOKEN`.
- Soft subtitle embedding and burn-in both require `ffmpeg`, and the default speech-onset trim uses it when available.
- In-place embedding only works when the embedded output can stay in the same container; cases that need an MKV fallback still require plain `--embed`.
- MLX behavior can vary by machine, Python version, model choice, and the host Metal stack. If MLX fails or macOS reports that Python closed unexpectedly, try `--backend=faster-whisper` and use `--doctor --deep` only when you want an explicit native import check.

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
