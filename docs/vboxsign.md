# `vboxsign`

[← Back to README](../README.md#table-of-contents)

`vboxsign` signs and loads the VirtualBox kernel modules on a Linux host with Secure Boot enabled.

## What It Does

- signs the `vboxdrv`, `vboxnetflt`, `vboxnetadp`, and `vboxpci` kernel modules with a MOK (Machine Owner Key) keypair, skipping any module that's already signed
- loads each module with `modprobe` after signing
- re-execs itself with `sudo` automatically if not already run as root

## Supported Platforms

- Linux (with Secure Boot and a MOK keypair enrolled via `mokutil`)

## Dependencies

- a MOK keypair (`MOK.priv`, `MOK.der`) already generated and enrolled with `mokutil --import`
- matching `linux-headers-$(uname -r)` installed (for the kernel's `sign-file` tool)
- VirtualBox installed (for the kernel modules themselves)

## Install / First Run Summary

**Edit the script first** — `dir=/home/directory/of/keys` is a placeholder and must be changed to wherever your `MOK.priv`/`MOK.der` actually live before running this. Then:

```bash
sudo vboxsign
```

(or just `vboxsign` — it re-execs itself under `sudo` if needed)

## Common Usage Examples

Run after a kernel update, when Secure Boot is rejecting the unsigned VirtualBox modules:

```bash
vboxsign
```

## Important Behavior / Defaults

- Requires root; automatically re-runs itself via `sudo` if not already root.
- Skips signing (but still attempts to load) any module that's already signed.
- The commented-out block for an encrypted (GPG-protected) private key is inert by default — the script expects an unencrypted `MOK.priv` unless you uncomment and adapt that section yourself.
- The final `shred -vfuz MOK.priv` cleanup line is also commented out by default, so the private key is left in place after a run unless you opt in.

## Notes / Caveats

- The hardcoded key directory (`/home/directory/of/keys`) is a placeholder by design (this repo is public) — you must point it at your own key location before use.
- Designed to be re-run safely after every kernel update, since new kernel builds need the modules re-signed against the running kernel's headers.

[↑ Back to README TOC](../README.md#table-of-contents)
