# AGENTS.md

Guidance for future contributors and AI agents working in this repo.

Repo name: `maj-scripts-vibe`

## Purpose

`maj-scripts-vibe` is expected to grow into a collection of unrelated or loosely related scripts.

This repo is for public, user-facing utility scripts that can be tested and
documented as standalone tools. It is not the replacement home for private
`~/bin` operator scripts and it is not a system overlay repo.

Boundary rules:

- jw.org content tools (downloading/extracting/muxing jw.org videos, music,
  periodicals, or sign-language clips) belong in `jwkit`
  (https://github.com/majal/jwkit), not here — `ffrife`, `jwdl` (which also
  absorbed `jwget`'s periodicals as `jwdl periodicals`), `jwsl` (renamed
  `slverse`), and `jwvideo-mux`(-shortcuts.sh) moved there on 2026-08-13.
  Note `jwdl` has a live systemd caller on `emeth4`; see `jwkit`'s own
  `AGENTS.md` Operational Notes before touching its CLI surface.
- Private `~/bin` migrations, local ops helpers, systemd timer installers, and
  fleet maintenance scripts belong in `bin`.
- emeth4 workstation overlay files and reinstall policy belong in
  `maj-newemeth`.
- Cloud/VPS server bootstrap overlays belong in `maj-newserver`.
- If a script requires private local paths, tokens, machine-specific service
  files, or root-only config to make sense, stop and consider `bin` or an
  overlay repo before adding it here.
- Power, boot, and hibernate helpers may live here only when they are public
  diagnostic/setup tools with conservative safeguards, clear dry-run/report
  behavior, and no machine-specific bootloader policy. Durable workstation
  bootloader, crypttab, fstab, hibernate, and reinstall policy belongs in
  `maj-newemeth`; private operational recovery helpers belong in `bin`.
- Keep this repo suitable for public GitHub by default: examples should use
  placeholders and off-repo config paths, and tests should not depend on the
  operator's live machine state.

The documentation model is:

- `README.md` is the user-facing index and navigation hub
- `AGENTS.md` defines how scripts and docs should be added in the future

## Public Repo And Secrets

This repository is public. Treat anything committed here as readable by others.

Do not store secrets, OAuth client JSON files, token caches, API keys, private backup paths, or other sensitive local state in this repo.

Prefer OS-local config, environment variables, or user home paths outside the repo for secrets and machine-specific state. When documenting setup, show placeholder paths or explicitly off-repo locations.

## Agent Permission Rules

Normal file edits inside this repository checkout are pre-approved. Do not ask for user permission before creating or modifying files in this repo as part of the requested work.

If the agent workflow requires a brief note before editing, phrase it as a progress update, not as an approval request.

This repo guidance does not override Codex CLI runtime approval prompts. If normal in-repo edits still trigger approval UI, adjust the Codex CLI approval policy in the user-level config rather than adding more repo instructions.

Still ask for approval before escalated actions, including destructive commands, writes outside this repo or the configured writable roots, GUI/system-level actions, or network-dependent commands that the sandbox blocks.

Recommended top-level README order:

1. Title
2. Short description
3. Overview
4. Table of Contents
5. Scripts
6. Your Local Setup
7. Contributing Docs

## README Rules

When adding a new top-level script to the repo:

1. Add or update the script file.
2. Add the script to the README table of contents.
3. Add a dedicated script subsection under `## Scripts` using the standard template.
4. Keep the `## Scripts` section above the shared Your Local Setup section.
5. End each major section after the table of contents with `↑ TOC`.

Do not add a new script without updating the README.

## Test Rules

Run `python3 -m tests` before pushing changes that affect scripts, tests, or README/AGENTS documentation. On Windows, use `py -m tests`.

## Commit And Push Rules

When an agent completes requested repo changes and is confident the work is ready, commit and push them unless the user explicitly asks not to.

Do not push when there are unresolved errors, relevant verification has not passed, or the agent believes the change should wait for more work or be bundled with related follow-up changes. In those cases, leave a clear status note with the next step.

## Script Section Template

The full per-script template (see below) now lives in `docs/<script>.md`, not in `README.md` directly — see the Growth Rule. Each script subsection under `## Scripts` in `README.md` should instead include just:

1. Script name
   The subsection heading itself should link directly to the script file when the script lives in the repo root.
2. A short (1-3 sentence) description — what the script does and why it exists.
3. A `Full docs: [docs/<script>.md](docs/<script>.md)` link.
4. `↑ TOC`

The full template that used to live inline in `README.md` now lives in `docs/<script>.md`:

1. `# <script>` title, immediately followed by a `[← Back to README](../README.md#table-of-contents)` link.
2. The same short description as the README blurb (may repeat it verbatim).
3. `## What It Does`
4. `## Supported Platforms`
5. `## Dependencies`
6. `## Install / First Run Summary`
7. `## Common Usage Examples`
8. `## Important Behavior / Defaults`
9. `## Notes / Caveats`
10. `[↑ Back to README TOC](../README.md#table-of-contents)` at the end.

Doc filename: `docs/<script-name>.md`, stripping a trailing `.sh` if the script has one. Links from inside a doc file back into README anchors (e.g. `#python`, `#friendly-launchers`) should use `../README.md#anchor`, not a bare `#anchor`.

Keep examples short, practical, and copy-pasteable.

## Local Setup And Friendly Launcher Rules

Shared setup and friendly launcher instructions belong in the shared Your Local Setup section of `README.md`, not duplicated in every script section.

Prefer a hierarchy where the main setup topic is the visible README section and platform-specific variants live underneath it.

Examples of shared topics:

- friendly launcher patterns such as drag-and-drop wrappers, file picker wrappers, and context-menu actions
- Python installation
- Git setup and update basics
- package managers such as Homebrew, `winget`, and Chocolatey
- platform-level setup like `ffmpeg`

Script-specific setup may be documented in the script section, but it should link back to shared setup sections when possible instead of repeating the same instructions.

Keep Your Local Setup generic and reusable across scripts. If a note only applies to one script, it belongs in that script's subsection, not in Your Local Setup.

Package-manager subsections should describe the package manager itself and show broad reusable examples, not read like setup notes for one script or one dependency.

When a Your Local Setup heading refers to a concrete tool or install target, prefer linking that heading to the official docs, homepage, or official repository.

Friendly launcher guidance should make clear that launchers are thin wrappers around the scripts, should keep output or logs visible, and should not hide errors from non-terminal users.

## Tone Rules

The README should be lightly playful, not chaotic:

- a small number of useful emojis is fine
- headings and navigation can be friendlier than plain boilerplate
- body text should still stay practical, readable, and skimmable
- prefer active sentence structures over passive ones when the wording stays natural
- avoid phrasing that sounds like a cold computer status message when a warmer natural sentence would work just as well

Do not let “fun” make setup instructions vague.

User-facing script output should also feel warm, calm, and reassuring:

- prefer friendly and supportive wording for normal status messages
- for interruptions and recoverable errors, avoid cold or alarming phrasing
- make it clear when the user can safely try again
- a small amount of personality is welcome if it stays readable

Human-written copy in the README intro should be treated as protected by default:

- do not rewrite the README title unless explicitly asked
- do not rewrite the short description directly under the title unless explicitly asked
- do not rewrite the Overview description paragraph unless explicitly asked

Assume these are intentionally human-authored voice and branding choices. AI should preserve them rather than “improving” them.

## Heading And TOC Rules

- Keep README headings stable and predictable so future anchors remain valid.
- Keep the Overview above the table of contents.
- Prefer `## Scripts` as the parent section and `### <script-name>` for each script.
- Within each script subsection, use `####` headings for the internal template sections.
- Prefer script subsection headings in the form `### [<script-name>](./<script-file>)` when the script file lives at the repo root.
- Prefer `## Your Local Setup` over separate top-level setup and launcher sections.
- In the main README TOC, prefer top-level setup topics like `Friendly Launchers`, `Python`, `Git`, and `Package Managers`, with platform-specific entries discoverable inside those sections instead of crowding the main TOC.
- Script sections in `README.md` are short (blurb + doc link) now that the full template lives in `docs/<script>.md`, so a local mini TOC inside `README.md` is no longer needed there. Within a `docs/<script>.md` file itself, a short "Jump to" list is optional but not required — the file's own heading outline (rendered by GitHub) usually covers it.
- The `## Scripts` section should appear before Your Local Setup.
- Use `↑ TOC` for major sections and primary subsections, not every nested platform subsection.
- When a primary subsection contains nested subsections, place its `↑ TOC` at the end of the last nested subsection, not before the nested content starts.
- If a new shared subsection is added, it must also be added to the README TOC in the same order it appears in the file.

## Growth Rule

This rule has now fired: the repo outgrew a single-file README (10 scripts, ~2000 lines), so detailed per-script docs live in `docs/<script>.md` per the Script Section Template above, and `README.md` keeps only short blurbs plus links.

- `README.md` remains the canonical entry point and navigation page — it must always list every root script in the Table of Contents and `## Scripts`, even though the detail lives elsewhere.
- New scripts follow the split from the start: add the short blurb to `README.md` and the full template to `docs/<script>.md` in the same change, not as a later migration.
- Keep this rule's text in sync with what's actually true — do not let the README quietly grow back into one giant file.

## When Adding A Script Checklist

- add the script file
- update the README table of contents
- add the short script subsection (name, blurb, `Full docs:` link) under `## Scripts`
- link the script subsection heading to the actual script file when possible
- create `docs/<script>.md` with the full template (see Script Section Template) and a back-link to the README TOC
- keep `## Scripts` above Your Local Setup
- keep the Overview above the table of contents
- add/update shared setup docs only if there is a new shared prerequisite
- keep Your Local Setup generic; move script-specific notes into the script's `docs/<script>.md`
- use `↑ TOC` consistently in README, and the back-link in `docs/<script>.md`
- keep examples concise and copy-pasteable
- keep links and headings stable
