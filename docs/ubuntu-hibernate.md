# `ubuntu-hibernate`

[← Back to README](../README.md#table-of-contents)

`ubuntu-hibernate` is a guided hibernate doctor and setup helper for Ubuntu 26.04.

## What It Does

- inspects whether the running kernel advertises hibernate support
- checks systemd-logind, `/sys/power/state`, `/sys/power/disk`, active swap, initramfs-tools resume support, kernel command line hints, encryption clues, and NVIDIA GPU caution signs
- explains what is ready, what is risky, and what needs manual work before setup
- writes a shareable Markdown or JSON diagnostic report
- applies a conservative setup only when it can select a persistent block-device swap target
- backs up touched system files before writing changes
- can restore those backups with `undo`
- prints a safe hibernate test checklist and only runs the real hibernate command when explicitly asked

## Supported Platforms

- Ubuntu 26.04 LTS is the supported setup target
- other Linux releases may run diagnostics, but setup requires `--allow-unsupported`

## Dependencies

Runtime:

- Python 3
- Linux with systemd
- `initramfs-tools`
- `update-initramfs` for setup and undo

Useful diagnostic tools:

- `busctl`
- `blkid`
- `lsblk`
- `lspci`
- `dmsetup` for some encrypted swap mapping checks

## Install / First Run Summary

Run the doctor first. It does not change the system:

```bash
./ubuntu-hibernate doctor
./ubuntu-hibernate doctor --json
```

Preview setup before writing anything:

```bash
sudo ./ubuntu-hibernate setup --dry-run
```

Apply only after reviewing the plan:

```bash
sudo ./ubuntu-hibernate setup
```

## Common Usage Examples

Write a Markdown report:

```bash
./ubuntu-hibernate report -o ubuntu-hibernate-report.md
```

Write a JSON report for issue reports or automation:

```bash
./ubuntu-hibernate report --json -o ubuntu-hibernate-report.json
```

Apply setup without an interactive prompt after reviewing `--dry-run`:

```bash
sudo ./ubuntu-hibernate setup --yes
```

List backups and restore one:

```bash
sudo ./ubuntu-hibernate undo --list
sudo ./ubuntu-hibernate undo 20260426T210000Z
```

Print the real-test checklist:

```bash
./ubuntu-hibernate test
```

Run the real hibernate test when you are ready:

```bash
sudo ./ubuntu-hibernate test --run
```

## Important Behavior / Defaults

- The default command is `doctor`.
- `doctor`, `report`, and `test` without `--run` do not change the system.
- `setup` refuses to continue when the running kernel does not expose `disk` hibernation, when no persistent block-device swap target is available, when swap is smaller than RAM, or when initramfs resume support is missing.
- The first setup release does not edit GRUB, systemd-boot, kernel command lines, or swap files. It reports swap-file systems and explains why they need bootloader `resume_offset` wiring.
- Setup writes `/etc/systemd/sleep.conf.d/90-ubuntu-hibernate.conf` and `/etc/initramfs-tools/conf.d/resume`, then runs `update-initramfs -u -k all` by default.
- Backups live under `/var/backups/ubuntu-hibernate/<timestamp>/`.
- `undo` restores the files recorded in the selected backup and refreshes initramfs unless `--skip-initramfs` is used.
- NVIDIA detection is a caution, not an automatic failure. Some systems hibernate cleanly with NVIDIA; others need driver, firmware, or graphics-mode work outside this tool.

## Notes / Caveats

- Hibernate setup crosses firmware, kernel, initramfs, swap, encryption, bootloader, desktop policy, and graphics drivers. A passing doctor means the standard pieces look ready; it is not a guarantee that every firmware and driver path will resume cleanly.
- Keep a known-good boot path and your disk unlock passphrase available before the first real test.
- The systemd sleep configuration behavior follows the Ubuntu 26.04 `systemd-sleep.conf` manpage.
- The block-device resume behavior follows Ubuntu 26.04 `initramfs-tools`, where `RESUME=` can be written in `/etc/initramfs-tools/conf.d/resume`; swap files also need a `resume_offset` boot parameter.
- GNOME or another desktop may decide whether to expose hibernate in visible menus after logind reports it as available.

[↑ Back to README TOC](../README.md#table-of-contents)
