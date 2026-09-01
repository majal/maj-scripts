# gmail-cleanup UNIX-philosophy/modularity split

**Date:** 2026-08-31 (session continued into 2026-09-01; GmailIndex
follow-up pass done 2026-09-01; naming/attachment-writers/message-rewrite/
pdf-processing/metadata follow-up pass also done 2026-09-01)
**Status:** Partial — 17 of an open-ended set of extractions applied; safe stopping point reached, remainder documented below.

## 2026-09-01 follow-up: GmailIndex subsystem extraction

The "best next candidate" flagged at the bottom of this report — the
`GmailIndex`/`IndexedGmailClient`/`IndexOnlyGmailClient` + index
build/analyze subsystem — was extracted in a dedicated follow-up pass,
using the exact same method (verbatim move, one coherent piece per commit,
`python3 -m tests` green before each push) documented below. Three commits:

| # | Module | Lines | Contents | Depends on |
|---|--------|------:|----------|------------|
| 10 | `gmail_cleanup/message_utils.py` | 179 | `parse_email_message`, `header_value`, `attachment_extension`, `sanitize_filename`, `is_ignored_sidecar_part`, `infer_attachment_mime_type`, `attachment_categories_for_part`, `derive_attachment_filename`, `human_size`, `message_filename_records` | constants |
| 11 | `gmail_cleanup/gmail_index.py` (part 1) | — | `GmailIndex`, `IndexedGmailClient`, `IndexOnlyGmailClient`, `run_index_build`, `render_index_build`, `render_index_stats`, plus the three tiny helpers only `GmailIndex` used (`iso_now`, `private_parent`, `all_header_records`) | constants, models, message_utils |
| 12 | `gmail_cleanup/gmail_index.py` (part 2, appended) | 834 total | `message_sender_domain`, `message_year`, `is_analyzable_attachment_part`, `counter_items`, `top_bytes_items`, `indexed_cleanup_suggestions`, `run_index_analyze`, `render_index_analyze` | constants, models, message_utils, (same module as part 1) |

The unplanned but necessary addition was module #10: this report's own
method rule 1 says a cluster must depend "only on the standard library plus
modules already extracted, never on code still living only in the
top-level script." `GmailIndex.upsert_message` and the index-analyze path
call straight into `parse_email_message`, `header_value`,
`derive_attachment_filename`, `infer_attachment_mime_type`,
`attachment_extension`, `attachment_categories_for_part`, `human_size`, and
`message_filename_records` — all still living in the "genuinely tangled"
email-parsing region this report explicitly declined to touch. Tracing each
one's own call graph showed they're actually pure leaves (stdlib +
constants only, never calling back into the tangled bidirectional cluster
around `collect_media_parts`/`plan_message`/etc.) — the tangle warning
applied to the region's *location* in the file, not to these particular
functions. They were pulled into their own `message_utils.py` module as a
prerequisite commit, with the main script importing them back for its many
other call sites (extract-media, PDF handling, reporting), exactly like the
existing `message_filename_records`-in-`run_report` pattern.

`gmail-cleanup` itself: **5,541 → 4,657 lines** this pass (another 884
lines moved out); **7,201 → 4,657 lines total** since the split began (35%
moved out). All three commits individually verified: `python3 -m unittest
tests.test_gmail_cleanup -v` — 75/75 passed every time; `python3 -m tests`
— 152/152 (full repo suite) every time; `./gmail-cleanup --help` / `index
--help` / `report --help` run clean; no PII (`majal`, `/Users/maj`) in
either new module. Commits, in order:

```
d8c648c Extract gmail-cleanup message/attachment leaf helpers into gmail_cleanup/message_utils.py
7e8f553 Extract gmail-cleanup SQLite index storage/client layer into gmail_cleanup/gmail_index.py
6e93ed1 Extract gmail-cleanup index-analyze command into gmail_cleanup/gmail_index.py
```

## 2026-09-01 follow-up: re-examining the four "genuinely tangled" clusters

This report's "What's still monolithic" section (below) named four clusters
as genuinely tangled, not just unattempted, and warned that a clean split
needed "its own dedicated pass rather than an opportunistic one." This pass
was exactly that dedicated pass: for each of the four, the actual call
graph was traced (via `grep` for every call site, and for the larger
clusters an AST walk collecting every name each function loads/calls)
rather than trusting the original categorization. Two clusters turned out
to be safely extractable once traced; one was extracted after the tracing
showed the original "these two call each other" description no longer held
at the direct-call level; one (metadata embedding) simply hadn't been
looked at closely before and traced clean on the first pass. A fifth,
smaller piece (naming/destination leaf helpers) was extracted first as a
prerequisite, following the exact precedent `message_utils.py` set in the
prior pass. One cluster (PDF password cracking, plus the write_pdf_outputs/
write_backup_files orchestration that threads it together with PDF
processing) was deliberately left alone -- not because a back-edge was
found, but for reasons explained in its own subsection below.

### What was extracted, in order

| # | Module | Lines | Contents | Depends on |
|---|--------|------:|----------|------------|
| 13 | `gmail_cleanup/naming.py` | 188 | `subject_slug`, `backup_folder_name_for_plan`, `build_search_token`, `build_saved_filename`, `photos_search_query`, `normalize_content_id`, `unique_destination`, `is_deterministic_backup_filename`, `matching_destination`, `guess_mime_type_from_filename`, `sniff_image_mime_type`, `extension_for_mime_type`, `normalize_image_destination`, `build_pdf_page_search_token`, `build_pdf_page_filename`, `build_embedded_image_filename`, `build_libreoffice_embedded_image_filename`, `build_audio_video_filename` | constants, message_utils, models |
| 14 | `gmail_cleanup/attachment_writers.py` | 438 | `write_bytes_attachment`, `find_soffice_executable`, `extract_zip_embedded_images_from_document`, `extract_libreoffice_embedded_images_from_document`, `extract_embedded_images_from_document`, `write_file_attachment`, `convert_audio_to_video_file`, `write_audio_video_attachment` | constants, models, message_utils, naming, tool_paths, config |
| 15 | `gmail_cleanup/message_rewrite.py` | 544 | `detect_unsupported_message`, `plan_message`, `gmail_thread_url`, `collect_media_parts`, `message_matches_before_year`, `should_extract_part`, `collect_buffered_media`, `prune_selected_parts`, `buffered_note_fragments`, `is_pdf_page_output`, `written_note_fragments`, `format_pdf_text_section_text`/`_html`, `build_note_text`/`_html`, `inject_backup_note`, `note_charset`, `prepend_note`, `inline_placeholder_text`/`_html`, `replace_inline_media_references`, `replace_cid_references_in_html`, `sanitize_message_for_insert`, `build_note_only_message`, `rewrite_message_for_backup` | constants, models, message_utils, naming, config |
| 16 | `gmail_cleanup/pdf_processing.py` | 452 | `pdf_password_args`, `pdf_page_count`, `parse_pdfimages_list_output`, `list_pdf_image_rows`, `is_probably_scanned_pdf`, `render_pdf_output_suffix`, `convert_image_file`, `choose_pdf_image_candidate`, `render_pdf_pages_to_images`, `extract_pdf_images_directly`, `extract_pdf_text`, `render_pdf_pages_for_ocr`, `ocr_image_with_tesseract`, `extract_pdf_ocr_text`, `build_pdf_text_blocks`, `html_to_text`, `extract_message_search_text` | constants, models, message_utils, naming, attachment_writers, tool_paths, config |
| 17 | `gmail_cleanup/metadata.py` | 337 | `metadata_marker_text`, `metadata_tags_for_attachment`, `read_existing_metadata_tags`, `merge_marker_value`, `contains_subject_token`, `subject_tokens_for_attachment`, `build_exiftool_write_command`, `read_existing_ffprobe_tags`, `get_existing_ffprobe_tag`, `build_ffmpeg_metadata_write_command`, `embed_marker_metadata_with_ffmpeg`/`_with_exiftool`, `embed_marker_metadata` | constants, models, naming, tool_paths, config |

`gmail-cleanup` itself: **4,657 → 3,008 lines** this pass (1,649 lines
moved out, plus net import-list trimming); **7,201 → 3,008 lines total**
since the split began (58% moved out). Every commit individually verified:
`python3 -m unittest tests.test_gmail_cleanup -v` — 75/75 passed after
every commit; `python3 -m tests` (full repo suite) — 152/152 after every
commit; `./gmail-cleanup --help` and every subcommand's `--help` run clean
after every commit; no PII (`majal`, `/Users/maj`) in any new module.
Commits, in order:

```
fe8eef4 Extract gmail-cleanup naming/destination leaf helpers into gmail_cleanup/naming.py
32ee431 Extract gmail-cleanup attachment-writing cluster into gmail_cleanup/attachment_writers.py
307054b Extract gmail-cleanup message-parsing/note-injection cluster into gmail_cleanup/message_rewrite.py
eafc8f8 Extract gmail-cleanup PDF rendering/extraction primitives into gmail_cleanup/pdf_processing.py
6500790 Extract gmail-cleanup marker-metadata embedding into gmail_cleanup/metadata.py
```

### Why the original "genuinely tangled" call was wrong for three of the four clusters

For attachment writing, message parsing/note injection, and PDF
processing, the original report's tangle description was about the
*region* of the file, not about the specific functions' own call graphs.
Tracing showed:

- **Attachment writing** (`write_bytes_attachment` through
  `write_audio_video_attachment`): the report's concern was that shared
  naming helpers (`matching_destination`, `build_saved_filename`,
  `sanitize_filename`, `attachment_extension`) were "referenced from three
  different places in the file." Two of those four were already extracted
  into `message_utils.py` in the prior pass; this pass extracted the other
  two (plus their own leaf dependents) into `naming.py` first, as a
  prerequisite -- once that was done, a full function-name cross-grep of
  the attachment-writing region against the message-parsing region came
  back with **zero** calls in either direction.
- **Message parsing / note injection** (`detect_unsupported_message`
  through `rewrite_message_for_backup`): an AST walk of every name each
  function in the region loads found a clean DAG with two independent
  entry points (`plan_message`, used while deciding what to extract, and
  `rewrite_message_for_backup`, used once bytes are already written) and
  no back-edges. The "shared local state" the original report described
  is per-call closures (e.g. `nonlocal counter` in `collect_media_parts`'s
  inner `visit`), not module-level mutable state read and written by
  multiple callers.
- **PDF processing** (`pdf_password_args` through
  `extract_message_search_text`): the report paired this with PDF
  password cracking as mutually tangled. Tracing found the dependency is
  one-directional: PDF processing calls nothing in the password-cracking
  cluster; the password-cracking cluster (`resolve_pdf_password`) and
  `write_pdf_outputs` call *into* PDF processing (e.g.
  `resolve_pdf_password` calls `pdf_page_count`). The "these two call each
  other" framing described data-flow influence (backend choice affecting
  which candidates get tried), not literal bidirectional function calls.
- **Metadata embedding** (`metadata_marker_text` through
  `embed_marker_metadata`): this one was never actually traced in the
  original pass -- it was left unattempted "simply on time/context budget,"
  per that pass's own note. Traced clean on the first look: a DAG rooted
  at `embed_marker_metadata`, all external dependencies already extracted.
  Its four tag-name constants (`IMAGE_METADATA_TAGS`, `PDF_METADATA_TAGS`,
  `VIDEO_METADATA_TAGS`, `QUICKTIME_MIME_TYPES`) were moved into
  `constants.py` as a small prerequisite, since they were still sitting at
  top-level-script scope.

### The recurring `mock.patch.object` gotcha, again

Every one of these five extractions hit the same gotcha this report
documented in the original pass: when a patched function and its caller
move into the *same* new submodule, `mock.patch.object(self.gmail_cleanup,
...)` stops having any effect on the internal call, because the caller
resolves the bare name from its own module's `__globals__`. Fixed the same
way each time -- `import gmail_cleanup.<name> as gmail_cleanup_<name>` in
the test file, then patch that module object instead. This hit:
`find_soffice_executable` (attachment_writers), `prune_selected_parts`
(message_rewrite), `extract_pdf_text`/`extract_pdf_ocr_text`
(pdf_processing), and `resolve_exiftool_path`/`read_existing_metadata_tags`/
`embed_marker_metadata_with_exiftool`/`embed_marker_metadata_with_ffmpeg`
(metadata, four names across five test methods).

One adjacent discovery while fixing the metadata-cluster patches: a test
for the audio-to-video path in `write_backup_files` patched
`self.gmail_cleanup.resolve_ffmpeg_path`, but the real call has been inside
`gmail_cleanup.attachment_writers.convert_audio_to_video_file` since the
attachment-writers extraction two commits earlier in this same pass. That
patch had been silently ineffective since then -- the test still passed
only because the mocked `subprocess.run` doesn't care what path string
`resolve_ffmpeg_path` actually returns. Retargeted to
`gmail_cleanup_attachment_writers` so the mock is load-bearing again. This
is a reminder that a test passing is not proof a given patch target is
correct; the gotcha can hide silently behind an unrelated assertion that
happens to still pass.

### What's still deliberately not extracted: PDF password cracking

`resolve_pdf_password` and its ~25 helpers (password-recipe fingerprinting
and learning, candidate generation from message text/dates/numeric tails,
`select_pdf_password_backend`, `pdfcrack`/`john` invocation and output
parsing) plus the `write_pdf_outputs`/`write_backup_files` orchestration
that threads PDF mode, password handling, rendering, and text extraction
together (`gmail-cleanup` lines 760–1572, ~813 lines) were traced the same
way as everything else. The direct-call graph **is** a clean DAG here too
-- no back-edges were found between the password-cracking functions
themselves, and their only outward dependency on PDF processing is
one-directional (`resolve_pdf_password` calls `pdf_page_count`). So this is
not a "found a tangle, backed off" case.

The reason it was left alone this pass is size and consequence, not
call-graph safety:

- It's the largest remaining single cluster (~813 lines, ~30 functions),
  more than any of the five extracted this pass.
- It runs real subprocesses (`pdfcrack`, `john`) against user PDF
  attachments and writes/reads persistent file-backed state
  (`password_stores.py`'s recipe/secret/failure JSON stores) with
  real security and correctness stakes if a transcription slip changed
  candidate-generation order, backend selection logic, or failure-count
  bookkeeping.
- `write_pdf_outputs` is a ~200-line orchestrator threading together PDF
  mode selection, password resolution, rendering, direct extraction, and
  text retention for every PDF attachment in a real backup run --
  exactly the function the original report called out as the reason this
  needs "its own dedicated pass."

Verbatim-move extraction the way the other five were done today is very
likely still safe here given the call-graph evidence above, but doing
~30 functions' worth of copy-diff-verify correctly, for a cluster whose
failure mode is silently cracking (or failing to crack) a user's real PDF
attachments, deserves a dedicated pass with a fresh context budget and
byte-for-byte diffing of every function, not one appended onto an
already-five-extraction session. Nothing here is unsafe to extract in
principle -- it just wasn't done today. A future pass can start directly
from the call-graph evidence above instead of re-deriving it.

Everything below this point is the original 2026-08-31 report, unedited.

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
