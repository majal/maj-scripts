# Config-first / CLI flag parity audit

**Date:** 2026-08-31
**Status:** Applied

## Why

Part of the fleet-wide config-first + CLI-flag-parity rollout (P1 of
`ags/docs/reports/2026-08-31-cross-repo-standards-rollout-handoff.md`),
auditing `maj-scripts` against `repo-template-standard.md` v1.2.0 item 9.
This is the public, tested, user-facing scripts repo, so the bar here is
the highest of the three repos in this rollout: every flag needs help
text, and docs/tests must stay in sync with any behavior change.

**Note on method:** partway through this pass, testing a `vboxsign` edit
by running `bash vboxsign --help` (bare name, not `./vboxsign`) caused its
internal `exec sudo -E "$0" "$@"` re-exec to resolve `$0` via `$PATH`,
which picked up a *different*, real, already-installed `vboxsign` at
`/Users/maj/dig/bin/vboxsign` instead of the file under test. That live
script ran under `sudo`. Verified after the fact: no lasting effect (its
Linux-specific paths don't exist on this Mac, so it failed early; the one
side effect, an empty `k.x` file created by a redirect and then shredded,
was never a real file that existed before the command and left no trace).
For the remainder of this pass, no script containing `sudo` or a
self-re-exec was executed — those were reviewed by static read only, and
that's noted per-file below.

## Audited

| File | Config consumed | Flag parity |
| --- | --- | --- |
| `gmail-cleanup` | TOML config (`~/.config/maj-scripts/gmail-cleanup/config.toml`, `GMAIL_CLEANUP_CONFIG` env), ~25 `resolve_*()` settings | Already fully compliant — every config key has a matching CLI flag (`--query`, `--max-results`, `--config`, `--credentials`, `--token-cache`, `--gmail-user`, `--index-db`, `--types`, `--before-year`, `--pdf-mode`, `--pdf-password-mode`, `--request-profile`, `--quota-units-per-second`, `--progress-format`, `--readable-folders`, etc.), documented precedence (CLI > env > config > default) in every `--help`. No gap found. |
| `whisper` | TOML config (global `~/.config/maj-scripts/whisper/config.toml` + project `.maj-scripts-whisper.toml`), `CONFIG_VALUE_TYPES` dict (29 keys) | Already fully compliant — every config key (`lang`, `model`, `backend`, `device`, `compute_type`, `jobs`, `outdir`, `subtitle_style`, `glossary`, `state_dir`, `mlx_*`, etc.) has a same-named CLI flag. `extra_glossary`/`extra_suppress_phrases` are project-config-only additive-merge keys, not separate operator actions — the existing `--glossary`/`--suppress-phrases` (`action="append"`) flags already give equivalent one-run control. No gap found. |
| `ubuntu-hibernate` | `--root` env-backed override (`UBUNTU_HIBERNATE_ROOT`) for reading live system files during `doctor`/`report` | Compliant by design — `--root` is deliberately the only override, used solely for the read-only diagnostic path. `setup`/`undo` always require real root and always write real absolute system paths (by design, verified in source), so `BACKUP_ROOT` (`/var/backups/ubuntu-hibernate`, a standard Debian backup-tree location) isn't wired to `--root`. Reviewed and left as-is: this is a fixed, conventional location for a privileged, always-real-system operation, not a per-run tunable in the same sense as the diagnostic settings. |
| `wh` | none (thin `wormhole` passthrough wrapper) | Compliant — the one injected default (`--code-length=4`) is skipped automatically whenever the user passes `--code-length` or `--code` explicitly; the override path already exists via straight passthrough. |
| `minterpolate` | none (getopts flags only) | Already fully compliant — every default (`ff`, `fps`, `dur`, `enc`, `task`, `m_args`, `ff_args_enc`) has a matching `-b/-r/-d/-e/-p/-m/-f` getopts flag, documented in its own `-h` usage text. |
| `printing-mode` | none (fixed unit-name arrays) | No gap — `ENABLED_UNITS`/`STATIC_UNITS` are a fixed, well-known set of systemd unit names the tool exists specifically to manage, not an operator-tunable threshold; already has `--dry-run`, `--mask`, `--no-unmask`. |
| `generate_html_colors_video` | none — hardcoded `3840x2160` resolution, `12:00:00` duration, output to cwd | **Fixed this pass** — added `-r/--resolution`, `-d/--duration`, `-o/--outdir` flags (defaults unchanged: `3840x2160`, `12:00:00`, `.`). Previously had *no* CLI options at all, and its own docs explicitly called that out ("there are no command-line options... no flag to change resolution, duration"). Updated `docs/generate_html_colors_video.md` (Common Usage Examples, Important Behavior) to match. |
| `vboxsign` | none — hardcoded placeholder key directory (`/home/directory/of/keys`), documented as "edit the script yourself" | **Fixed this pass** — added `-k/--keys-dir DIR` flag and `VBOXSIGN_KEYS_DIR` env var (precedence: flag > env > in-script default), and switched the internal `sudo` re-exec to `sudo -E` so the env var survives it. Default behavior unchanged when neither is set. Updated `docs/vboxsign.md`. **Not executed** (contains `sudo`/self-re-exec) — verified with `bash -n` (syntax) only, per the strict no-live-execution rule for anything touching `sudo` (see "Why" above). |
| `pdfcompress`, `pdfind`, `pdflat`, `pdflat-auto`, `pdflat-single` | none (positional filename args only) | No persisted config exists for any of these to check flag parity against; each is a small, single-purpose tool that already takes its one tunable (filenames) as arguments. No gap under this audit's definition. |
| `maj-source` | `MAJ_WORKSTATION_BEEP` env var (0/1/auto) in `workstation_beep()` | Already compliant — this is a sourced shared-function library, not an independent CLI entrypoint, and its one configurable behavior already has a documented env-var override with a sensible `auto` default. |
| `scripts/install-john-jumbo-local.sh` | none (getopts-style flags only) | Already fully compliant — `--src-dir`, `--bin-dir`, `--keep-build-deps`, `--no-link-local-bin` cover every tunable default, with full `--help` text. Contains `sudo apt-get` calls — reviewed by static read only, not executed. |
| `s76/s76-power-autoprofile`, `dup/dup1-daily`, `dup/dup1-hourly`, `dup/install-dup`, `dup/maj-online` | various hardcoded values; `s76/...` also does a `sudo tee` UDEV-rules install | **Out of scope, flagged separately** — these appear to be stale, unreferenced (zero mentions in README.md/AGENTS.md/TODO.md) duplicates of content that already lives, in more current form, in `maj-newemeth` (the `s76-power-autoprofile` fixed earlier this same audit pass) and `maj-newserver` (the `dup1-*` cron scripts, as `.disabled`). This looks like a repo-boundary violation of `maj-scripts`' own AGENTS.md rules, not a flag-parity gap — spawned as a separate background task (`task_d8818cdf`) rather than fixed inline here, since deciding delete-vs-migrate needs its own investigation. Not executed (the `s76/` script contains `sudo`). |

## Not yet fixed — real gaps left, with reason

None beyond the `s76/`/`dup/` repo-boundary finding above, which is tracked
as a separate spawned task rather than fixed here (it's a dead-code/repo-
hygiene question, not a config/flag gap — see AGENTS.md's own scope notes
for what belongs in this repo vs. `maj-newemeth`/`maj-newserver`).

## Applied

- `generate_html_colors_video` — added `--resolution`/`--duration`/`--outdir` flags (short aliases `-r`/`-d`/`-o`), `mkdir -p` for a custom outdir, description metadata now reflects the actual resolution/duration used. `docs/generate_html_colors_video.md` updated to match.
- `vboxsign` — added `--keys-dir`/`VBOXSIGN_KEYS_DIR` override with documented precedence, `sudo -E` re-exec so the env var survives privilege escalation. `docs/vboxsign.md` updated to match.
- Full test suite (`python3 -m tests`, 152 tests) passes after both changes.
- Commit: see `git log` this date in this repo.
