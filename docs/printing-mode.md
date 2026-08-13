# `printing-mode`

[← Back to README](../README.md#table-of-contents)

`printing-mode` toggles the Linux printing and printer-discovery stack.

## What It Does

- shows the current state of common systemd printing units
- enables and starts local printing support through CUPS
- enables and starts printer discovery through `cups-browsed` and Avahi
- starts USB IPP support through `ipp-usb` when it exists on the machine
- disables and stops the same stack when printers are not needed
- supports dry-run output before changing system services

## Supported Platforms

- Linux systems using systemd

## Dependencies

System tools:

- `bash`
- `systemctl`
- `sudo` when you are not already running as root

Managed services, when installed:

- `cups.socket`
- `cups.path`
- `cups.service`
- `cups-browsed.service`
- `avahi-daemon.socket`
- `avahi-daemon.service`
- `ipp-usb.service`

## Install / First Run Summary

Make the script executable if your checkout did not preserve executable bits:

```bash
chmod +x printing-mode
```

Inspect the current machine first:

```bash
./printing-mode status
```

Preview changes before applying them:

```bash
./printing-mode disable --dry-run
./printing-mode enable --dry-run
```

## Common Usage Examples

Disable printing and printer discovery when this machine does not need printers:

```bash
./printing-mode disable
```

Enable the full local printing and discovery stack again:

```bash
./printing-mode enable
```

Disable the stack and mask enable-capable units so socket or path activation cannot restart it:

```bash
./printing-mode disable --mask
```

Check whether the relevant units are installed, enabled, and active:

```bash
./printing-mode status
```

## Important Behavior / Defaults

- The default action is `status`; it does not change the system.
- `enable` runs `systemctl enable --now` for enable-capable printing and discovery units.
- `disable` runs `systemctl disable --now` for enable-capable printing and discovery units.
- `ipp-usb.service` is commonly a static unit, so the script starts or stops it when present instead of trying to enable it.
- Missing units are skipped so the same script can run on machines with different printer packages installed.
- `enable` unmarks previously masked units by default; pass `--no-unmask` to skip that.
- `disable --mask` is stronger than normal disable and requires a later `enable` to unmask units.

## Notes / Caveats

- Disabling Avahi also disables general mDNS and `.local` discovery, not only printer discovery.
- Disabling CUPS removes local print-service availability until you run `printing-mode enable` or manage the units manually.
- Package names and unit names can vary across Linux distributions; this script targets the common Debian/Ubuntu systemd stack.

[↑ Back to README TOC](../README.md#table-of-contents)
