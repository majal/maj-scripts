# AGENTS.md

Guidance for future contributors and AI agents working in this repo.

Repo name: `maj-scripts-vibe`

## Purpose

`maj-scripts-vibe` is expected to grow into a collection of unrelated or loosely related scripts.

The documentation model is:

- `README.md` is the user-facing index and navigation hub
- `AGENTS.md` defines how scripts and docs should be added in the future

## README Rules

When adding a new top-level script to the repo:

1. Add or update the script file.
2. Add the script to the README table of contents.
3. Add the script to the README Scripts index.
4. Add a dedicated script section to the README using the standard template.
5. End the script section with a `Back to TOC` link.

Do not add a new script without updating the README.

## Script Section Template

Each script section in `README.md` should include:

1. Script name
2. What it does
3. Supported platforms
4. Dependencies
5. Install / first-run summary
6. Common usage examples
7. Important behavior / defaults
8. Notes / caveats
9. Back to TOC link

Keep examples short, practical, and copy-pasteable.

## Bootstrap Rules

Shared bootstrap/setup instructions belong in the shared Bootstrap section of `README.md`, not duplicated in every script section.

Examples of shared topics:

- Python installation
- Homebrew installation
- platform-level setup like `ffmpeg`

Script-specific setup may be documented in the script section, but it should link back to shared bootstrap sections when possible instead of repeating the same instructions.

## Heading And TOC Rules

- Keep README headings stable and predictable so future anchors remain valid.
- Prefer simple headings like `Script: <name>` and `Bootstrap / Platform Setup`.
- Every major script or setup section should end with a `Back to TOC` link.
- If a new shared subsection is added, it must also be added to the README TOC.

## Growth Rule

The repo should stay README-first for now.

If the repo grows large later:

- detailed docs may move into `docs/`
- the root `README.md` must still remain the canonical entry point and navigation page
- script entries in the README should link to any split-out detailed docs

## When Adding A Script Checklist

- add the script file
- update the README table of contents
- update the README Scripts index
- add the script section using the standard template
- add/update bootstrap docs only if there is a new shared prerequisite
- keep examples concise and copy-pasteable
- keep links and headings stable
