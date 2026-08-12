# TODO

Tracked follow-ups that are intentionally deferred, not forgotten.

## Rewrite legacy scripts as cross-platform tools

`minterpolate`, `pdfcompress`, `pdfind`, and `pdflat`/`pdflat-auto`/`pdflat-single`
are legacy bash scripts migrated as-is from the pre-rename repo (`2afe1d5`).
They should eventually be upgraded to the same style as `jwsl`/`jwdl`/`wh`:
cross-platform (macOS/Linux/Windows), with a proper README section following
the standard template in `AGENTS.md`. Until then they're undocumented in
`README.md` and `test_readme.py` correctly flags them as such — this is
known, not a bug to fix by documenting the bash versions.

## Other repo-hygiene follow-ups

- `vboxsign` is kept in place deliberately (not archived) — see the commit
  message / conversation history around 2026-08-12: it's linked from the
  operator's own public GitHub Gist. That gist's URL is already broken
  today regardless (points at the old repo name's `master` branch, which
  no longer resolves after the GitHub rename-redirect expired) — the
  actual fix is updating the gist to point at `main` on the current repo,
  which is outside this repo's scope.
