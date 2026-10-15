# AGENTS.md

Guidance for contributors and AI agents. Repo: `maj-scripts`.

Template compliance: repo-template-standard.md v1.3.0 (reviewed 2026-10-10: item 11 n/a). Config-first and modularity
retrofits tracked in `ags/docs/reports/2026-08-31-cross-repo-standards-rollout-handoff.md`. Spec:
`~/dig/bin/new-agent-repo.d/repo-template-standard.md`. README structure/templates, tone, heading/TOC rules, installer
notes and growth rule: `docs/contributor-reference.md`.

## Purpose and boundaries
Public, user-facing utility scripts that can be tested and documented as standalone tools; a growing collection of loosely
related scripts. `README.md` is the user-facing index; this file defines how scripts/docs are added.
- jw.org content tools (videos, music, periodicals, sign-language clips) belong in `jwkit` (`ffrife`, `jwdl`, `slverse`,
  `jwvideo-mux` moved there 2026-08-13); `jwdl` has a live systemd caller on emeth4 (see jwkit's AGENTS.md).
- Private `~/bin` migrations, ops helpers, timer installers, fleet scripts -> `bin`. emeth4 workstation overlays ->
  `maj-newemeth`. VPS bootstrap overlays -> `maj-newserver`. A script needing private paths, tokens, machine-specific
  service files or root-only config belongs in `bin` or an overlay, not here.
- Power/boot/hibernate helpers only if public diagnostic/setup tools with conservative safeguards and dry-run/report
  behavior; durable bootloader/crypttab/fstab/hibernate policy -> `maj-newemeth`.
- Keep the repo suitable for public GitHub: placeholder examples, off-repo config paths, tests independent of the
  operator's live machine.

## Agent Working Rules
- CLI/API tools before GUI/browser automation.
- **Artifacts stay local.** The repo is public: work product touching real operational/personal detail goes in
  `docs/reports/private/` (untracked, see `.gitignore`), never a hosted `claude.ai` artifact, gist or pastebin unless the
  operator explicitly asks for a shareable link.
- **Public repo and secrets:** anything committed is world-readable. Never store secrets, OAuth client JSON, token caches,
  API keys, private backup paths or sensitive local state; use OS-local config/env vars/home paths and show placeholders.
- **Permissions:** normal file edits inside this checkout are pre-approved (a pre-edit note is a progress update, not an
  approval request); this doesn't override Codex runtime approval prompts (adjust the user-level policy instead). Still ask
  before escalated actions: destructive commands, writes outside the repo/writable roots, GUI/system-level actions,
  sandbox-blocked network commands.
- **Bash scripts use `#!/usr/bin/env bash`**, not `#!/bin/bash` (macOS `/bin/bash` is 3.2: no `${var,,}`, `echo -e "\e[..."`
  breaks; confirmed 2026-09-20 via `pdflat`).
- Run `python3 -m tests` (Windows: `py -m tests`) before pushing changes to scripts, tests or README/AGENTS docs.
- **Commit and push** once requested changes are complete and verified (push is the deploy step; "smart batched deploy"),
  unless asked not to. Don't push with unresolved errors, unpassed verification, or work that should be bundled with
  imminent follow-ups: leave a status note with the next step.
- Installers (`install.sh`/`uninstall.sh`, `install.ps1`/`uninstall.ps1`) are adapted from `jwkit`'s; keep the two repos
  aligned. `install.sh` `TOOLS` lists every root script; `$Tools` in the `.ps1` files lists only Python scripts (alphabetical
  both). `install.ps1` is unverified on real Windows; test `install.sh` with `HOME=/tmp/scratch bash install.sh`.

## README and docs (templates in `docs/contributor-reference.md`)
- Never add a script without updating the README. Short blurb under `## Scripts` (heading links to the script file, 1-3
  sentences, `Full docs:` link, `↑ TOC`); full template in `docs/<script>.md` (strip trailing `.sh`) with a back-link.
  Same change, not a later migration; don't let the README regrow into one giant file.
- Human-authored README intro (title, short description, Overview paragraph) is protected: don't rewrite unless asked.
- Tone: warm, practical, skimmable README; calm, reassuring script output (say when it is safe to retry); never let
  playfulness make setup vague.
- Keep `## Scripts` above Your Local Setup and the Overview above the TOC; keep headings stable; shared setup lives in
  Your Local Setup (generic), script-specific notes in `docs/<script>.md`.

## When Adding A Script Checklist
- add the script file; README table of contents entry; short `## Scripts` subsection (heading links to the script file);
  `docs/<script>.md` with full template and back-link; keep `## Scripts` above Your Local Setup and Overview above TOC
- add/update shared setup docs only for a new shared prerequisite; keep examples concise and copy-pasteable; keep links
  and headings stable; `↑ TOC` consistently
- add the script to `TOOLS` in `install.sh` (and `$Tools` in `install.ps1`/`uninstall.ps1` if it's a Python script that
  runs on Windows)
