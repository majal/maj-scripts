# `pdflat-auto`

[← Back to README](../README.md#table-of-contents)

`pdflat-auto` flattens every PDF in the current directory with no prompts.

## What It Does

- flattens every `*.pdf` in the current working directory via Ghostscript (`-dPreserveAnnots=false`)
- always moves the pre-flatten originals into `orig/`, with no confirmation step

See also [`pdflat`](pdflat.md) (same flattening, but interactive and takes explicit filenames) and [`pdflat-single`](pdflat-single.md) (flattens exactly one file).

## Supported Platforms

- macOS
- Linux

## Dependencies

- Ghostscript (`gs`)

## Install / First Run Summary

Install Ghostscript, then run it from the directory containing the PDFs you want flattened:

```bash
cd ~/Documents/forms
pdflat-auto
```

## Common Usage Examples

Flatten everything in the current directory:

```bash
pdflat-auto
```

## Important Behavior / Defaults

- Takes no arguments and no confirmation prompt — running it processes every `*.pdf` in the current directory immediately.
- Originals always end up in `./orig/` (created if it doesn't exist).

## Notes / Caveats

- Because there's no confirmation step, only run this from a directory where "flatten everything here" is actually what you want — use [`pdflat`](pdflat.md) if you want to review the file list first.

[↑ Back to README TOC](../README.md#table-of-contents)
