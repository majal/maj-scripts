# `wh`

[← Back to README](../README.md#table-of-contents)

`wh` is a convenience wrapper for `magic-wormhole`.

## What It Does

- wraps the `wormhole` CLI
- auto-adds `--code-length=4` for code-generating flows
- passes all other commands through normally
- can help install `wormhole` when it is missing

## Supported Platforms

- macOS
- Linux
- Windows

## Dependencies

Shared prerequisites:

- [Python](../README.md#python)
- shared setup from [macOS](../README.md#python-on-macos), [Linux](../README.md#python-on-linux), or [Windows](../README.md#python-on-windows)

Primary external tool:

- `wormhole`

## Install / First Run Summary

Basic first run:

```bash
wh send file.zip
```

If `wormhole` is missing, `wh` can suggest a likely install route and offer to run it for you.

## Common Usage Examples

Send a file with a shorter generated code:

```bash
wh send file.zip
```

Receive using the normal prompt flow:

```bash
wh receive
```

Receive while allocating the code on this side:

```bash
wh receive --allocate
```

Pass through other `wormhole` commands:

```bash
wh help
```

## Important Behavior / Defaults

- `wh` injects `--code-length=4` for `send` and `tx`.
- `wh` also injects `--code-length=4` for `receive --allocate` and receive aliases such as `rx`, `recv`, and `recieve`.
- `wh` does not inject another code-length flag if you already passed `--code-length`.
- `wh` leaves ordinary `receive` unchanged because the sender normally generates the code.
- Missing-`wormhole` install prompts use `Y/n`, where Enter means yes.

## Notes / Caveats

- Package-manager support varies by system, so `wh` suggests the best install route it can find.

[↑ Back to README TOC](../README.md#table-of-contents)
