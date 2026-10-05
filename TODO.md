# TODO

Tracked follow-ups that are intentionally deferred, not forgotten.

## Rewrite legacy scripts as cross-platform tools

`pdflat`/`pdflat-auto`/`pdflat-single` are legacy bash scripts migrated as-is
from the pre-rename repo (`2afe1d5`). They should eventually be upgraded to the
same style as `wh`/`whisper`: cross-platform (macOS/Linux/Windows), with a
proper `docs/<script>.md` page following the template in `AGENTS.md`.

`minterpolate`, `pdfcompress`, `pdfind`, `generate_html_colors_video`,
`maj-online` and `vboxsign` were archived to `maj-scripts-archive-2026/`
(commit `a4028b1`, 2026-09-22); their README sections were pruned and their
docs moved to `maj-scripts-archive-2026/docs/`. `thumb` has no tests yet.

`jwget` and `jwinbox` used to be in this bucket too — `jwget`'s periodicals
were absorbed into [`majal/jwkit`](https://github.com/majal/jwkit)'s `jwdl`
(as `jwdl periodicals`, via jw.org's modern checksummed API instead of the
old unauthenticated scrape) and the standalone script retired to
`bin-archive-2026/jwget/`, and `jwinbox` was retired there too (legacy
pre-2018 jw.org account watcher, plaintext password by default) — see
2026-08-13's commit history for details.

## Other repo-hygiene follow-ups

- `vboxsign` was archived (see above). The operator's public GitHub Gist
  that linked to it already pointed at a dead URL (old repo name's `master`);
  updating or retiring that gist is outside this repo's scope.
