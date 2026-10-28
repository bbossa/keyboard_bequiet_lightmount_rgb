# Changelog

All notable changes to lightmount. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/) (before 1.0, a minor version may change the config or the commands).

The section of a version is used as the notes of its GitHub release.

## [Unreleased]

## [0.2.0] - 2026-10-28

### Added

- `lightmount reload`, also `systemctl --user reload lightmount` (`ExecReload`): the service rereads the config and reapplies the zones. The config is validated first, so errors show up in the terminal; an invalid config is refused and the service keeps the previous one. Without a running service, the zones are applied once.
- `lightmount calibrate [--start HEX]`: lights the keys one by one to check the key map. ISO French key map (`lightmount/keymap.py`), confirmed key by key (110 keys and the knob).
- The config can be written back (`lightmount/save.py`): only `[zones]` and `[alerts]` are replaced; the other tables, the comments above each table and the end-of-line comments of the keys still written are kept. Nothing is written unless the result is valid and leaves the rest of the file unchanged; the write is atomic and the previous file is kept as `config.toml.bak`.
- Preview of unsaved zones on the keyboard, without touching the file.
- Graphical editor (GTK4, preview): draws the keyboard, edits zones and alerts, live preview, save then reload. Run from a checkout with `python3 -m lightmount.gui`; not packaged yet.

### Changed

- The failed-command alert is amber (`e66100`) by default instead of blue: blue did not read as an error, and a redder orange was too close to the critical red on the LEDs.
- The service warns when `[daemon]` or `alerts.sources.notifications` change on reload: they are only read at startup and need `systemctl --user restart lightmount`.

## [0.1.1] - 2026-10-24

### Fixed

- The zones are reapplied on resume from suspend (logind `PrepareForSleep`): the USB controller is reset and the keyboard lost its colors while staying plugged in.

### Added

- Device report issue form.
- README: Arch install from the release, what to do after an IO Center session.

## [0.1.0] - 2026-10-15

First release.

- Fixed zones (top strip, knob, keys, side strips, or custom zones by LED index) in custom mode, applied by a systemd user service at startup and on replug.
- Short alerts on one zone: desktop notifications (green, red when critical) and failed shell commands (fish, bash, zsh hooks).
- Zones reapplied after the Fn+←/→ effect key.
- Commands: `check`, `apply`, `status`, `alert`, `watch`.
- Arch package and `.deb`, udev rule for access without root.

[Unreleased]: https://github.com/bbossa/keyboard_bequiet_lightmount_rgb/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/bbossa/keyboard_bequiet_lightmount_rgb/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/bbossa/keyboard_bequiet_lightmount_rgb/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/bbossa/keyboard_bequiet_lightmount_rgb/releases/tag/v0.1.0
