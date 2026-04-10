# AGENTS.md

Guidance for future contributors and AI agents working in this repo.

Repo name: `maj-scripts-vibe`

## Purpose

`maj-scripts-vibe` is expected to grow into a collection of unrelated or loosely related scripts.

The documentation model is:

- `README.md` is the user-facing index and navigation hub
- `AGENTS.md` defines how scripts and docs should be added in the future

Recommended top-level README order:

1. Title
2. Short description
3. Overview
4. Table of Contents
5. Scripts
6. Platform Setup
7. Contributing Docs

## README Rules

When adding a new top-level script to the repo:

1. Add or update the script file.
2. Add the script to the README table of contents.
3. Add a dedicated script subsection under `## Scripts` using the standard template.
4. Keep the `## Scripts` section above the shared Platform Setup section.
5. End each major section after the table of contents with `↑ TOC`.

Do not add a new script without updating the README.

## Script Section Template

Each script subsection under `## Scripts` in `README.md` should include:

1. Script name
   The subsection heading itself should link directly to the script file when the script lives in the repo root.
2. `#### What It Does`
3. `#### Supported Platforms`
4. `#### Dependencies`
5. `#### Install / first-run summary`
6. `#### Common usage examples`
7. `#### Important behavior / defaults`
8. `#### Notes / caveats`
9. `↑ TOC`

Keep examples short, practical, and copy-pasteable.

## Platform Setup Rules

Shared setup instructions belong in the shared Platform Setup section of `README.md`, not duplicated in every script section.

Prefer a hierarchy where the main setup topic is the visible README section and platform-specific variants live underneath it.

Examples of shared topics:

- Python installation
- package managers such as Homebrew, `winget`, and Chocolatey
- platform-level setup like `ffmpeg`

Script-specific setup may be documented in the script section, but it should link back to shared setup sections when possible instead of repeating the same instructions.

Keep Platform Setup generic and reusable across scripts. If a note only applies to one script, it belongs in that script's subsection, not in Platform Setup.

Package-manager subsections should describe the package manager itself and show broad reusable examples, not read like setup notes for one script or one dependency.

When a Platform Setup heading refers to a concrete tool or install target, prefer linking that heading to the official docs, homepage, or official repository.

## Tone Rules

The README should be lightly playful, not chaotic:

- a small number of useful emojis is fine
- headings and navigation can be friendlier than plain boilerplate
- body text should still stay practical, readable, and skimmable
- prefer active sentence structures over passive ones when the wording stays natural

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
- Prefer `## Platform Setup` over `Bootstrap / Platform Setup`.
- In the main README TOC, prefer top-level setup topics like `Python` and `Package Managers`, with platform-specific entries discoverable inside those sections instead of crowding the main TOC.
- The `## Scripts` section should appear before Platform Setup.
- Use `↑ TOC` for major sections and primary subsections, not every nested platform subsection.
- When a primary subsection contains nested subsections, place its `↑ TOC` at the end of the last nested subsection, not before the nested content starts.
- If a new shared subsection is added, it must also be added to the README TOC in the same order it appears in the file.

## Growth Rule

The repo should stay README-first for now.

If the repo grows large later:

- detailed docs may move into `docs/`
- the root `README.md` must still remain the canonical entry point and navigation page
- script entries in the README should link to any split-out detailed docs

## When Adding A Script Checklist

- add the script file
- update the README table of contents
- add the script subsection under `## Scripts`
- link the script subsection heading to the actual script file when possible
- use the standard script template inside that subsection
- keep `## Scripts` above Platform Setup
- keep the Overview above the table of contents
- add/update shared setup docs only if there is a new shared prerequisite
- keep Platform Setup generic; move script-specific notes into the script subsection
- use `↑ TOC` consistently
- keep examples concise and copy-pasteable
- keep links and headings stable
