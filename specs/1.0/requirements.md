# lightmount 1.0: requirements

Status: **draft** (2026-11-08). Notation: [EARS](https://alistairmavin.com/ears/). Each requirement has an ID cited by the design, the tasks, the ADRs and the tests.
Priority: M = must for 1.0, S = should, C = could. Status: `done` (already in 0.2.0, to be kept), `todo`, `blocked`.

Goal of 1.0: a promise of stability (config format, CLI), an installation that is documented and tested on common distributions, and the graphical editor packaged like the rest.

Source: `PLAN-1.0.md` and `PLAN-GUI.md` (private notes), `README.md`, `CHANGELOG.md`.

## 1. Stability

| ID | Requirement | Pri | Status |
|---|---|---|---|
| R-001 | Throughout the 1.x series, the system shall keep the documented config tables (`[device]`, `[daemon]`, `[zones]`, `[alerts]`, `[alerts.sources]`) and their keys backward compatible. | M | todo |
| R-002 | Throughout the 1.x series, the system shall keep the commands `check`, `apply`, `reload`, `status`, `alert`, `calibrate` and their exit codes backward compatible. | M | todo |
| R-003 | The core (`lightmount`, without the GUI) shall depend only on Python 3.11 or newer and the standard library. | M | done |
| R-004 | When the editor saves the config, the system shall replace only `[zones]` and `[alerts]`, keep the other tables and comments, write atomically and keep the previous file as `config.toml.bak`. | M | done |
| R-005 | Where a zone has only a LED list and a color, the editor shall write it in the short form already used in the example config. | S | todo |
| R-006 | The system shall document the config format and the CLI as stable in the README. | M | todo |

## 2. Daemon

| ID | Requirement | Pri | Status |
|---|---|---|---|
| R-010 | When the daemon starts, it shall publish its version where `status` and the editor can read it. | M | todo |
| R-011 | If the version of the daemon differs from the version of the command or editor, then `status` and the editor shall tell the user to restart the service. | M | todo |
| R-012 | When the daemon handles `reload`, it shall make available whether the new config was applied or refused, and why. | M | todo |
| R-013 | The README and the editor shall state that a preview is ephemeral: when the daemon reapplies the saved zones (resume, replug, effect key), the preview is cleared (ADR-0007). | S | todo |
| R-014 | The daemon shall keep writing to the keyboard under the shared lock, as the CLI and the editor do. | M | done |
| R-015 | If the state file is missing, unreadable, of an unknown format or left by a dead process, then `status` and the editor shall treat the daemon version as unknown and shall not fail. | M | todo |

## 3. Packaging

| ID | Requirement | Pri | Status |
|---|---|---|---|
| R-020 | The system shall provide an install target for the editor: modules, `lightmount-gui` launcher, `.desktop` file, icon, AppStream metainfo. | M | todo |
| R-021 | The Arch package shall be split: `lightmount-gui` depends on `lightmount`, `python-gobject` and `gtk4`. | M | todo |
| R-022 | The Debian/Ubuntu build shall produce a `lightmount-gui` package depending on `python3-gi` and `gir1.2-gtk-4.0`. | M | todo |
| R-023 | Where the user passes `--gui`, `install/install.sh` shall also install the editor. | M | todo |
| R-024 | When CI runs, it shall build and install both packages and run `lightmount-gui --version`. | S | todo |
| R-025 | The system shall document one supported install method for Fedora: the portable `install/install.sh` (POSIX `sh`). | M | todo |
| R-026 | If the installed GTK is older than the documented minimum, then the editor shall exit with a message naming the required version. | S | todo |
| R-027 | While the editor package is not installed, the core shall work unchanged. | M | done |
| R-028 | The system shall publish `lightmount` (and `lightmount-gui`) on the AUR. | C | blocked (AUR registration closed) |

## 4. Install validation

| ID | Requirement | Pri | Status |
|---|---|---|---|
| R-030 | Before the 1.0 release, the maintainer shall validate the install on a fresh VM of Arch, the current Ubuntu LTS and the current Fedora, first without the keyboard, then with the keyboard passed to the VM. | M | todo |
| R-031 | On each VM, the validation shall cover: `check`, `status`, user service state, one alert, `reload`, the editor (open, preview, save) and a clean uninstall. | M | todo |
| R-032 | The README shall list the validated distributions and versions ("Tested on"). | M | todo |
| R-033 | The README shall state the minimum GTK version of the editor. | M | todo |

## 5. Graphical editor

| ID | Requirement | Pri | Status |
|---|---|---|---|
| R-040 | When no config file exists, the editor shall start from the commented example config. | S | todo |
| R-041 | While the user edits, the editor shall offer undo and redo. | S | todo |
| R-042 | The editor shall show the state of the service (active or not, version). | S | todo |
| R-043 | While a zone is edited, the editor shall show that zone alone in color on the drawn keyboard. | M | done |
| R-044 | When the keyboard is absent or `hidraw` access is denied, the editor shall display a banner explaining it. | M | done |
| R-045 | The editor shall support the ISO French layout; other layouts are added only after verification by someone owning that layout. | M | done |
| R-046 | The project shall offer a "help wanted" issue for other layouts (ISO DE/UK, ANSI). | S | done |
| R-048 | Where `[device] layout` is `ansi-us`, the key map, the predefined `keys` zone and the editor shall follow the ANSI US layout (experimental until verified on a keyboard). | S | done |
| R-047 | The editor shall display its texts in French and English. | M | done |

## 6. Project hygiene

| ID | Requirement | Pri | Status |
|---|---|---|---|
| R-050 | When a notable change is made, the maintainer shall add a line to `## [Unreleased]` in `CHANGELOG.md`. | M | ongoing |
| R-051 | When 1.0.0 is released, the GitHub release notes shall be the 1.0.0 section of the changelog. | M | todo |

## Out of scope for 1.0 (deferred)

- Layers mode like IO Center (rejected 2026-10-28, see ADR-0004; reconsider after use).
- Stored firmware effects (`10:06`): needs a vendor capture first.
- Idle shutoff of the lighting (logind `IdleHint`).
- Flatpak (`--device=all` for `hidraw`).
- Layouts other than ISO French (R-046).
