# `pdflat-single`

[← Back to README](../README.md#table-of-contents)

`pdflat-single` flattens exactly one named PDF in place, keeping a copy of the original.

## What It Does

- takes exactly one PDF path as its argument
- copies it into an `orig/` subfolder (created next to the file) before touching it
- flattens the file via Ghostscript (`-dPreserveAnnots=false`), overwriting it in place with the flattened version

See also [`pdflat`](pdflat.md) (interactive, multiple files) and [`pdflat-auto`](pdflat-auto.md) (no prompts, processes every PDF in the current directory).

## Supported Platforms

- macOS
- Linux

## Dependencies

- Ghostscript (`gs`)

## Install / First Run Summary

Install Ghostscript, then run it against a single file:

```bash
pdflat-single form.pdf
```

## Common Usage Examples

Flatten one file in place:

```bash
pdflat-single ~/Documents/form.pdf
```

## Important Behavior / Defaults

- Requires exactly one filename argument; exits immediately with no message if none is given.
- Always keeps a copy of the original in `<same-directory>/orig/` before overwriting the working copy.
- No confirmation prompt — running it processes the given file immediately.

## Notes / Caveats

- The `orig/` folder is created next to the input file, not in the current working directory, if you pass a path outside the current directory.

[↑ Back to README TOC](../README.md#table-of-contents)
