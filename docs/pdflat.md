# `pdflat`

[← Back to README](../README.md#table-of-contents)

`pdflat` flattens one or more named PDFs (removing form fields and annotations) and lets you choose whether to keep the originals.

## What It Does

- takes one or more PDF filenames as arguments
- shows the file list and a count, then waits for confirmation before doing anything
- flattens each PDF via Ghostscript (`-dPreserveAnnots=false`), replacing the original filename with the flattened output
- moves the pre-flatten originals into a temporary folder, then asks whether to keep that folder (moved into `orig/`) or leave it as-is

See also [`pdflat-auto`](pdflat-auto.md) (same flattening, no prompts, always processes every PDF in the directory) and [`pdflat-single`](pdflat-single.md) (flattens exactly one file, no prompts).

## Supported Platforms

- macOS
- Linux

## Dependencies

- Ghostscript (`gs`)

## Install / First Run Summary

Install Ghostscript first, then run against one or more files:

```bash
pdflat file1.pdf file2.pdf
```

## Common Usage Examples

Flatten every PDF in the current directory:

```bash
pdflat *.pdf
```

Flatten a single file:

```bash
pdflat form.pdf
```

## Important Behavior / Defaults

- Requires at least one filename argument.
- Prompts once with a file list and count, then waits for Enter (or Ctrl+C to cancel) before flattening.
- Originals are always moved out of the working directory into a temp folder first (named `pdflat.<random>`), regardless of what you answer next.
- After flattening, asks `y/N` whether to move that temp folder into `./orig/` — answering anything other than `y`/`yes` leaves the originals sitting in the temp folder (its path is printed) instead of `orig/`.

## Notes / Caveats

- If you decline the final prompt, remember the printed temp-folder path — that's where your originals are, not `orig/`.

[↑ Back to README TOC](../README.md#table-of-contents)
