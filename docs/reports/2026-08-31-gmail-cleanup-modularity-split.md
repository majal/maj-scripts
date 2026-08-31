# gmail-cleanup UNIX-philosophy/modularity split

**Date:** 2026-08-31 (session continued into 2026-09-01)
**Status:** Partial — 9 of an open-ended set of extractions applied; safe stopping point reached, remainder documented below.

## Why

`gmail-cleanup` was flagged during a fleet-wide modularity/UNIX-philosophy
discovery pass as a monolithic 7,201-line single-file script worth
splitting, per item 10 of `bin/new-agent-repo.d/repo-template-standard.md`
("prefer small, single-purpose tools... shared logic in a reusable
lib/"). This is a real, working, public, well-tested tool — not a toy —
so the goal was a **pure refactor**: move code between files, fix
imports, change nothing about behavior, the documented CLI surface, or
existing test coverage.

A previous attempt at this same task was cut off by a session rate limit
before making any file edits (it was still in a "build careful extraction
tooling" planning phase). This attempt committed and pushed after every
single verified extraction step specifically so a repeat interruption
would leave a well-tested partial result rather than nothing.

## Method

For each extraction:

1. Identify a self-contained cluster of functions/classes/constants —
   ideally depending only on the standard library plus modules already
   extracted, never on code still living only in the top-level script
   (which the `gmail_cleanup/` package cannot import back, since the
   entrypoint file has no `.py` extension).
2. Copy the code **verbatim** into a new `gmail_cleanup/<name>.py` module,
   diff it byte-for-byte against the original block to catch any
   transcription slip.
3. Replace the original block in `gmail-cleanup` with a `from
   gmail_cleanup.<name> import (...)` block.
4. Run `uv run pytest tests/test_gmail_cleanup.py -q` (all 75 tests).
5. Run `./gmail-cleanup --help` and every subcommand's `--help`
   (`extract-media`, `report`, `index`, `doctor`), diffed byte-for-byte
   against a checked-out pre-split copy of the script under the same
   argv[0] (`gmail-cleanup`, to rule out prog-name-only diffs in
   argparse's usage wrapping).
6. Spot-check `./gmail-cleanup doctor`'s live output (real tool/config
   detection) against the pre-split script, since it's one of the few
   subcommands safe to actually run end-to-end without touching a live
   Gmail account.
7. `grep` the new module for PII (emails, `/Users/maj`, phone numbers) —
   none found in any step, consistent with the earlier fleet-wide audit.
8. Commit and push (this repo's `AGENTS.md` calls for "smart batched
   deploy": commit as you go, push once tests pass) before starting the
   next extraction.

### The recurring gotcha: `mock.patch.object(self.gmail_cleanup, ...)`

`tests/test_gmail_cleanup.py` loads the top-level `gmail-cleanup` file as
a dynamically-named module via `SourceFileLoader` (see
`tests/support.py`), then does `from gmail_cleanup.<name> import X` calls
exactly like the real script does. Many tests use
`mock.patch.object(self.gmail_cleanup, "some_name", ...)` to stub a
function's internal collaborator.

That works fine as long as **both the patched name and the function that
reads it as a bare global live in the same module**. The moment a
function moves to a `gmail_cleanup/` submodule, it starts resolving bare
names from *that submodule's own* `__globals__` (populated by its own
`from gmail_cleanup.constants import ...` etc., a separate binding from
whatever the top-level script imported). Patching
`self.gmail_cleanup.some_name` no longer has any effect on it.

This bit real tests five times across the nine extractions (`config.py`,
`trash.py`, `password_stores.py`, `gmail_client.py` — one test method
each, `password_stores.py` needed four). Each time the fix was the same
shape: import the actual submodule in the test file
(`import gmail_cleanup.config as gmail_cleanup_config`, etc.) and patch
*that* instead of `self.gmail_cleanup`. One instance
(`test_build_gmail_client_reauthorizes_after_invalid_scope_refresh`)
was caught by an actual test failure that attempted a live `pip install`
before the fix — good confirmation the test was doing real work, not
just changed to pass.

No test's assertions or behavior were altered — only which module object
a `mock.patch.object` call targets.

## What moved (9 modules, ~1,660 lines out of the original 7,201-line
script)

| # | Module | Lines | Contents | Depends on |
|---|--------|------:|----------|------------|
| 1 | `gmail_cleanup/models.py` | 218 | Dataclasses (`GmailMessageRecord`, `PlannedMessage`, `WrittenAttachment`, `ExtractionSettings`, etc.), exceptions (`GmailRateLimitError`, `SkippableMessageError`, ...), `GmailQuotaPacer`, `ProgressReporter` | stdlib only |
| 2 | `gmail_cleanup/constants.py` | 327 | All module-level constants, env-var names, `default_state_dir`/`default_config_path`/`legacy_*` path helpers | stdlib only |
| 3 | `gmail_cleanup/config.py` | 660 | CLI-arg / env-var / TOML-config precedence chains: 49 `resolve_*`/`config_*_value`/`load_config`/preset functions | constants, models |
| 4 | `gmail_cleanup/system_tools.py` | 177 | OS/package-manager detection, `optional_tool_path`, `confirm`, `ensure_system_tool` (the install-prompt gate every tool resolver uses) | stdlib only |
| 5 | `gmail_cleanup/trash.py` | 95 | Cross-platform send-to-trash (macOS Finder AppleScript, Windows Recycle Bin via PowerShell, Linux XDG trash spec) | system_tools |
| 6 | `gmail_cleanup/gmail_retry.py` | 133 | Gmail API error classification (`is_retryable_gmail_*`, `gmail_error_reason`) and retry-with-backoff (`execute_retryable_gmail_write`) | constants |
| 7 | `gmail_cleanup/tool_paths.py` | 94 | Thin `ensure_system_tool()`/`optional_tool_path()` wrappers for every external CLI dependency (pdfimages, pdftotext, qpdf, pdfcrack, john, ocrmypdf, tesseract, exiftool, ffmpeg, ffprobe) — previously scattered across two separate regions of the file | system_tools |
| 8 | `gmail_cleanup/password_stores.py` | 79 | JSON-file-backed PDF password learning: recipe store, secret store (chmod 0600), per-family failure/backoff store | constants |
| 9 | `gmail_cleanup/gmail_client.py` | 436 | `load_google_modules` (lazy Google API import + install prompt), `GmailApiClient` (list/get/insert/trash/label with quota pacing + retry), `build_gmail_client` (OAuth load/refresh/re-auth), raw-message base64 encode/decode | constants, models, system_tools, gmail_retry |

`gmail-cleanup` itself: **7,201 → 5,541 lines** (23% moved out).

Every module carries a docstring explaining what it holds, why it moved
where it did in the extraction order, and what it depends on — so a
future pass resuming this work doesn't need to re-derive the dependency
graph from scratch.

## Import surface preserved

`tests/support.py`'s `load_script_module("gmail-cleanup")` execs the
top-level script as a module and never touches `gmail_cleanup/` directly
except where a test needed the mock-patch fix above. The script imports
everything back with `from gmail_cleanup.<name> import (...)` blocks, so
every name the tests already reference as `self.gmail_cleanup.<name>`
continues to resolve exactly as before. No test needed an import-path
change beyond the five mock-patch-target fixes described above.

## What's still monolithic, and why it wasn't touched this pass

The remaining ~5,540 lines are the parts of the file that turned out to
be **genuinely tangled** rather than cleanly layered — per the task's own
safety note, extractions that weren't clearly safe were left alone rather
than forced:

- **Email message parsing / attachment collection / note injection**
  (`parse_email_message` through `rewrite_message_for_backup`, roughly
  400 lines) — deeply interleaved `EmailMessage` tree-walking, MIME part
  selection, HTML/text note construction, and CID rewriting that share a
  lot of local state and call each other in both directions.
- **Attachment writing** (`unique_destination` through
  `write_audio_video_attachment`, roughly 500 lines) — filename
  sanitization, MIME sniffing, and the actual write-to-disk logic for
  every attachment kind (plain, image, PDF page, embedded-office-image,
  audio-as-video) all share the same destination-naming helpers
  (`matching_destination`, `build_saved_filename`, `sanitize_filename`,
  `attachment_extension`) that are themselves referenced from three
  different places in the file (message collection, PDF output, and
  audio conversion). Pulling any one attachment-kind writer out cleanly
  would require also relocating those shared naming helpers, which in
  turn are referenced by code in the message-collection cluster above —
  this is exactly the "tangled shared state" case called out as a reason
  to stop rather than force it.
- **PDF processing** (page counting, rendering, direct image extraction,
  OCR, text extraction — roughly 250 lines) and **PDF password cracking**
  (recipe/candidate generation, pdfcrack/john backend selection and
  invocation — roughly 400 lines). These two clusters call each other
  (`resolve_pdf_password` drives page counting and backend selection;
  backend selection drives candidate generation) and both are threaded
  through `write_pdf_outputs`, the ~200-line orchestration function that
  ties PDF mode, password handling, rendering, and text extraction
  together for a single attachment. A clean split here needs its own
  dedicated pass rather than an opportunistic one.
- **Metadata embedding** (`metadata_marker_text` through
  `embed_marker_metadata`, roughly 300 lines) — exiftool/ffmpeg tag
  read/write, closely tied to `WrittenAttachment` construction.
- **Manifest / apply-queue JSONL persistence**
  (`append_manifest_record` through `queued_message_ids_for_resume`,
  roughly 220 lines) and **message plan execution**
  (`execute_message_plan`, `export_message_plan`, roughly 130 lines).
- **`GmailIndex` + `IndexedGmailClient` + `IndexOnlyGmailClient` + index
  build/analyze** (roughly 1,000 lines) — the local SQLite index
  subsystem. Large and reasonably self-contained conceptually, but not
  attempted this pass simply on time/context budget, not because it
  looked unsafe. This is the best next candidate for a follow-up pass.
- **Reporting/rendering** (`summarize_run`, `render_summary`,
  `run_report`, `render_report`, `render_index_*`) and the **`doctor`**
  subsystem (`doctor_row` through `render_doctor`) — mostly string
  formatting over data already produced elsewhere, lower priority.
- **`build_parser()`** (argparse wiring, ~500 lines), **`main()`**, and
  the two top-level orchestration functions `inspect_matching_messages`
  and `run_extract_media` — these are legitimately the CLI entrypoint and
  arguably belong in the top-level script regardless of how far the
  library-code split eventually goes.

None of the above were judged unsafe to ever extract — they just need
either (a) extracting several tangled clusters together in one step
(the attachment-writing + message-collection helpers), or (b) their own
focused pass with a fresh context budget (the GmailIndex subsystem is the
single largest remaining opportunity). No extraction was started and then
reverted mid-way this session; every attempted step reached a fully
tested, committed, pushed state before moving to the next.

## Verification summary

Every one of the 9 steps individually passed, in order:

1. `uv run pytest tests/test_gmail_cleanup.py -q` — **75/75 passed**, every
   time, including after the five mock-patch-target fixes.
2. `./gmail-cleanup --help` and all four subcommand `--help` outputs
   byte-identical to a pre-split checkout (compared under the same
   argv[0]/prog name to isolate real diffs from argparse's own usage-line
   wrapping).
3. `./gmail-cleanup doctor` live output byte-identical to the pre-split
   script, confirming config resolution, tool detection, and OAuth-scope
   inspection all still resolve to the same real paths/values on this
   machine.
4. No PII (emails, `/Users/maj` paths, phone numbers) introduced into any
   new module.

Final state: **9 commits**, each self-contained and independently
revertable, all pushed to `origin/main` per this repo's auto-batched
deploy cadence (`AGENTS.md`: commit as you go, push once tests pass).

```
57f0a36 Extract gmail-cleanup data models into gmail_cleanup/models.py
6b4ef1d Extract gmail-cleanup constants into gmail_cleanup/constants.py
a4e99be Extract gmail-cleanup config resolution into gmail_cleanup/config.py
75e261c Extract gmail-cleanup system-tool helpers into gmail_cleanup/system_tools.py
5f44d0e Extract gmail-cleanup trash helpers into gmail_cleanup/trash.py
da05aeb Extract gmail-cleanup retry/error classification into gmail_cleanup/gmail_retry.py
06bbe9a Extract gmail-cleanup tool-path resolvers into gmail_cleanup/tool_paths.py
2f5542d Extract gmail-cleanup password stores into gmail_cleanup/password_stores.py
e29f4ae Extract gmail-cleanup Gmail API client into gmail_cleanup/gmail_client.py
```

## Suggested next steps (not done this pass)

1. Extract the `GmailIndex`/`IndexedGmailClient`/`IndexOnlyGmailClient` +
   index build/analyze subsystem into `gmail_cleanup/index.py` — largest
   remaining self-contained opportunity (~1,000 lines), lowest coupling
   risk of what's left.
2. Extract metadata embedding (`gmail_cleanup/metadata.py`) — moderate
   size, moderate coupling (needs `WrittenAttachment` from models and
   `resolve_exiftool_path`/`resolve_ffmpeg_path`/`resolve_ffprobe_path`
   from tool_paths, both already extracted).
3. Tackle the attachment-writing + message-collection helper tangle as
   one combined extraction (shared filename/destination helpers need to
   move together) rather than trying to peel off one writer at a time.
4. PDF processing and PDF password cracking are the highest-effort,
   highest-value remaining targets, but need a dedicated pass — they're
   mutually referential and threaded through `write_pdf_outputs`.
