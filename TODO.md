# TODO

Tracked follow-ups that are intentionally deferred, not forgotten.

## Rewrite legacy scripts as cross-platform tools

`minterpolate`, `pdfcompress`, `pdfind`, and `pdflat`/`pdflat-auto`/`pdflat-single`
are legacy bash scripts migrated as-is from the pre-rename repo (`2afe1d5`).
They should eventually be upgraded to the same style as `wh`/`whisper`:
cross-platform (macOS/Linux/Windows), with a proper `docs/<script>.md` page
following the template in `AGENTS.md`. Until then they're undocumented in
`README.md` and `test_readme.py` correctly flags them as such — this is
known, not a bug to fix by documenting the bash versions.

`generate_html_colors_video` and `maj-online` are in the same
undocumented/legacy bucket, not yet triaged into a specific follow-up.

`jwget` and `jwinbox` used to be in this bucket too — `jwget`'s periodicals
were absorbed into [`majal/jwkit`](https://github.com/majal/jwkit)'s `jwdl`
(as `jwdl periodicals`, via jw.org's modern checksummed API instead of the
old unauthenticated scrape) and the standalone script retired to
`bin-archive-2026/jwget/`, and `jwinbox` was retired there too (legacy
pre-2018 jw.org account watcher, plaintext password by default) — see
2026-08-13's commit history for details.

## Other repo-hygiene follow-ups

- `vboxsign` is kept in place deliberately (not archived) — see the commit
  message / conversation history around 2026-08-12: it's linked from the
  operator's own public GitHub Gist. That gist's URL is already broken
  today regardless (points at the old repo name's `master` branch, which
  no longer resolves after the GitHub rename-redirect expired) — the
  actual fix is updating the gist to point at `main` on the current repo,
  which is outside this repo's scope.
