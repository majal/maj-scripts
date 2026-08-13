# `gmail-cleanup`

[← Back to README](../README.md#table-of-contents)

`gmail-cleanup` is a local-first Gmail attachment cleanup CLI.

## What It Does

- searches Gmail with a normal Gmail query
- inspects matching messages for image and video attachments by default
- can optionally process PDF attachments too
- can use named presets for repeatable cleanup jobs, such as `large-media`, `office-docs`, `archives`, `audio-archive`, `old-media`, and `pdf-archive`
- backs up selected attachments to a local folder you choose
- saves each removed file with deterministic recovery markers in filenames and metadata
- inserts a modified copy of the email back into Gmail with a visible backup note
- replaces HTML inline media references with visible placeholders that show the saved filename and search token
- can apply optional Gmail audit labels to cleaned copies and skipped originals
- can build a private local SQLite Gmail index so repeated cleanup passes do not re-download the same raw messages
- can report remaining Gmail matches as actionable, false positives, or skipped before you apply changes
- can run a local `doctor` check for OAuth, Python modules, PDF tools, OCR tools, and password backends
- moves the original message to Gmail Trash after the modified copy is inserted

## Supported Platforms

- macOS
- Linux
- Windows

OAuth sign-in opens a local browser flow.

## Dependencies

Shared prerequisites:

- [Python](../README.md#python)
- shared setup from [macOS](../README.md#python-on-macos), [Linux](../README.md#python-on-linux), or [Windows](../README.md#python-on-windows)

Python packages:

- `google-api-python-client`
- `google-auth-oauthlib`
- `google-auth-httplib2`

System tools used on demand:

- a Google desktop OAuth client secret JSON stored outside this public repo
- `exiftool` for embedding the recovery marker into saved files during `--apply`
- `ffmpeg` and `ffprobe` for video metadata fallback and some image conversions
- LibreOffice (`soffice`) for best-effort embedded image extraction from legacy Office files such as `.doc`, `.xls`, and `.ppt`
- Poppler tools (`pdfimages`, `pdfinfo`, `pdftocairo`, `pdftotext`) when you include PDFs
- `ocrmypdf` is preferred for PDF OCR sidecar text when you enable OCR modes; `tesseract` is the fallback OCR engine
- for passworded PDFs, `gmail-cleanup` will scan for external recovery tools and prefer `john` plus a `pdf2john` helper, then `pdfcrack`, then `qpdf`
- on Linux, `--pdf-original trash` uses the freedesktop/XDG Trash layout directly under `~/.local/share/Trash`

When a required dependency is missing, `gmail-cleanup` can suggest an install command and offer to run it. Use `-y` to auto-accept those prompts.

## Install / First Run Summary

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

### Personal OAuth Setup, Step by Step

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

### Advanced Protection Note

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
# audio_mode = "copy"
# empty_after_removal = "skip"
# request_profile = "moderate"
# quota_units_per_second = 125
# progress_format = "text"
# before_year = 2018
# min_message_bytes = 1000000
# min_part_bytes = 0
# audit_labels = false
# label_processed = "gmail-cleanup/processed"
# label_review = "gmail-cleanup/review"
# index_db = "/path/to/private-state/gmail-index.sqlite"
# embedded_image_dir = "/path/to/photos-dropzone"
# readable_folders = true
# soffice = "/usr/bin/soffice"
# token_cache = "/path/to/private-state/token.json"
# gmail_user = "me"
# gmail_web_account = "0"
# max_results = 50
```

Start with a dry run. The first successful sign-in will open a local browser OAuth flow and create the token cache:

```bash
gmail-cleanup extract-media --query 'has:attachment' --backup-dir /path/to/local-backup
```

## Common Usage Examples

Preview and then apply media cleanup:

```bash
gmail-cleanup extract-media --query 'has:attachment older_than:365d' --backup-dir /path/to/local-backup
gmail-cleanup extract-media --query 'has:attachment larger:5M' --backup-dir /path/to/local-backup --apply
```

Run the PDF archive preset. The preset expands to the longer PDF options listed under [Important behavior / defaults](#important-behavior--defaults):

```bash
gmail-cleanup report --preset pdf-archive
gmail-cleanup extract-media --preset pdf-archive --backup-dir /path/to/local-backup --apply -v
gmail-cleanup extract-media --preset pdf-archive --backup-dir /path/to/local-backup --audit-labels --apply -v
```

Build and reuse a private local index so repeated reports read cached messages locally:

```bash
gmail-cleanup index build --preset pdf-archive -v
gmail-cleanup index stats
gmail-cleanup index analyze --query 'has:attachment -in:trash -in:spam'
gmail-cleanup report --preset pdf-archive --use-index
```

Try the non-PDF cleanup presets from the local index:

```bash
gmail-cleanup report --preset large-media --use-index
gmail-cleanup report --preset office-docs --use-index
gmail-cleanup report --preset archives --use-index
gmail-cleanup report --preset audio-archive --use-index
gmail-cleanup report --preset old-media --use-index
```

Add Gmail web links to a report when you want to manually review the matched threads:

```bash
gmail-cleanup report --preset pdf-archive --use-index --offline --gmail-links
gmail-cleanup report --preset office-docs --use-index --gmail-links --gmail-web-account 1
```

Export audio attachments as MP4 videos without changing Gmail, then report local manifest status offline:

```bash
gmail-cleanup extract-media --preset audio-archive --backup-dir /path/to/local-backup --use-index --export-only -v
gmail-cleanup report --preset audio-archive --backup-dir /path/to/local-backup --use-index --offline
```

Use the index during apply. Gmail writes still go to Gmail, but cached message reads come from the local index when present:

```bash
gmail-cleanup extract-media --preset pdf-archive --backup-dir /path/to/local-backup --use-index --audit-labels --apply -v
gmail-cleanup extract-media --preset large-media --backup-dir /path/to/local-backup --use-index --audit-labels --apply -v
```

Keep document exports readable and send embedded Office images to a separate Photos-style drop folder:

```bash
gmail-cleanup extract-media --preset office-docs --backup-dir /path/to/docs-bucket --embedded-image-dir /path/to/photos-dropzone --readable-folders --use-index --apply -v
```

Use PDF variants when you need a one-off behavior instead of the preset default:

```bash
gmail-cleanup extract-media --query 'filename:pdf older_than:365d' --types pdf --pdf-mode backup --apply
gmail-cleanup extract-media --query 'filename:pdf' --types pdf --pdf-mode render-pages --pdf-render-format png --pdf-render-dpi 300 --apply
gmail-cleanup extract-media --query 'filename:pdf' --types pdf --empty-after-removal note-only --apply
```

Run setup diagnostics and machine-readable agent flows:

```bash
gmail-cleanup doctor
gmail-cleanup doctor --json
gmail-cleanup report --preset pdf-archive --json
gmail-cleanup extract-media --preset pdf-archive --backup-dir /path/to/local-backup --progress-format jsonl --json --apply
```

Tune long or experimental runs:

```bash
gmail-cleanup extract-media --query 'label:inbox has:attachment' --backup-dir /path/to/local-backup --max-results 10
gmail-cleanup extract-media --query 'filename:pdf' --types pdf --max-results 5000 --request-profile conservative
gmail-cleanup extract-media --query 'has:attachment larger:5M' --backup-dir /path/to/local-backup --apply -vv
gmail-cleanup extract-media --query 'has:attachment' --apply -y
```

Agent-friendly review artifacts are written as JSONL too:

- `manifest.jsonl` for applied messages
- `apply-queue.jsonl` for the planned apply queue, so interrupted runs can resume without listing the whole Gmail query again
- `passworded-pdfs.jsonl` for passworded PDFs that were left unchanged for manual review

## Important Behavior / Defaults

- The default mode is a dry run. Nothing in Gmail or on disk changes unless you pass `--apply` or `--export-only`.
- `--export-only` writes selected files and manifest records to the backup folder but leaves Gmail unchanged.
- `report --backup-dir ...` annotates each match with local migration status from `manifest.jsonl`: `pending`, `exported_pending_gmail_sync`, or `completed`. This is useful when a cached index still contains messages that have already been processed in Gmail.
- `report --use-index --offline` reads only from the local SQLite index and manifest. It does not refresh OAuth tokens or contact Gmail.
- `report --gmail-links` adds Gmail web URLs for manual review. The links use account slot `0` by default; pass `--gmail-web-account 1`, set `GMAIL_CLEANUP_GMAIL_WEB_ACCOUNT`, or add `gmail_web_account` to local config if Gmail opens the wrong signed-in account.
- `--preset pdf-archive` expands to `filename:pdf -in:trash -in:spam`, `--types pdf`, `--pdf-mode auto`, `--pdf-original trash`, `--pdf-password-mode low-hanging`, `--pdf-password-failure-action trash-original`, `--pdf-text-mode auto`, `--empty-after-removal note-only`, conservative request pacing, and `--max-results 5000`. You can still override individual options on the same command.
- Cleanup presets also exist for `large-media`, `office-docs`, `archives`, `audio-archive`, and `old-media`. These use `has:attachment -in:trash -in:spam`, `--max-results 50000`, conservative request pacing, and selector-specific filters. `audio-archive` also sets `--audio-mode video`.
- The default attachment selectors are `image,video`. Other selectors are `pdf`, `media`, `large-media`, `office`, `archive`, `audio`, `legacy`, `code`, `calendar`, and `other`.
- Detached signature/key sidecars with `.sig` or `.asc` filenames are ignored by cleanup selectors, including `other`, so report leftovers do not look like real PDF/media work.
- `--readable-folders` keeps the message ID in each backup folder and appends a short sanitized subject snippet for easier local scanning.
- `--embedded-image-dir` writes images found inside Office/OpenDocument files into a second local drop folder while the original document stays in `--backup-dir`. Zip-based files such as `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, and `.odp` are scanned directly. For legacy formats such as `.doc`, `.xls`, and `.ppt`, the script falls back to LibreOffice when `soffice` is available; override the executable with `--soffice`, `GMAIL_CLEANUP_SOFFICE`, or `soffice` in local config.
- `--before-year`, `--min-message-bytes`, and `--min-part-bytes` are local filters applied after messages are inspected or loaded from the index. They are useful when you want repeated cleanup passes without changing the Gmail query.
- `--audio-mode copy` keeps original audio files. `video` writes an MP4 with a still black frame and AAC audio for Google Photos-style video backup flows. `video-plus-original` writes both.
- `gmail-cleanup report` uses the same query, preset, and extraction settings as `extract-media`, but only lists and classifies matched messages. It is useful after a run to separate real remaining work from Gmail search false positives.
- `gmail-cleanup doctor` does not call Gmail. It checks local config paths, token scopes, Python imports, external tools, and trash support so humans and agents can see what is ready before a long run.
- `--audit-labels` creates or reuses `gmail-cleanup/processed` and `gmail-cleanup/review`. `--label-processed` and `--label-review` let you set explicit labels without enabling both defaults.
- `gmail-cleanup index build` creates a private SQLite index at `~/.local/state/maj-scripts/gmail-cleanup/gmail-index.sqlite` on Linux, with equivalent OS-local state paths on macOS and Windows. Override it with `--index-db`, `GMAIL_CLEANUP_INDEX_DB`, or `index_db` in local config.
- `gmail-cleanup index analyze` does not call Gmail. It reads the local index and summarizes attachment selectors, extensions, MIME types, duplicate payload groups, sender domains, years, and suggested report commands.
- The index stores personal email metadata and compressed raw MIME for cached messages. Keep it outside this public repo, protect it like the token cache, and delete it when you no longer need the faster repeated passes.
- `--use-index` is read-through: if the requested query and messages are already cached, reports and inspection read locally; missing records are fetched from Gmail and added to the index. Gmail insert/trash/label writes are never simulated locally.
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
- During `--apply`, the same marker is embedded into saved file metadata too. For images the script stamps XMP/IPTC/EXIF description fields; for QuickTime-family videos it stamps comment/description fields plus XMP. When `exiftool` cannot write a video container directly, `gmail-cleanup` falls back to `ffmpeg` container metadata. Backup-mode PDFs are stamped too. Office, archive, audio, and other non-media formats use best-effort XMP metadata; if the container cannot be written, the deterministic filename, Gmail note, and manifest remain the recovery markers.
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

## Notes / Caveats

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

[↑ Back to README TOC](../README.md#table-of-contents)
