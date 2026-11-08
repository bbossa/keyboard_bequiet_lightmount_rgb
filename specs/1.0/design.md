# lightmount 1.0: design

Status: draft (2026-11-08). Requirements: `requirements.md`.

## Current architecture (0.2.0)

- `lightmount/` core, stdlib only (R-003): `protocol.py` (frames, no I/O), `hid.py`/`device.py` (hidraw), `config.py`, `save.py` (write `[zones]`/`[alerts]` back), `daemon.py`, `cli.py`, `keymap.py` (ISO FR), `layout.py`.
- `lightmount watch`: single daemon, owns config and alert state ([ADR-0005](adr/0005-fifo-single-daemon.md)). CLI and editor send commands through a one-way FIFO and write the keyboard under the shared lock `lightmount.lock`.
- `lightmount/gui/`: GTK4 editor ([ADR-0002](adr/0002-gtk4-without-libadwaita-optional-package.md)); `geometry.py` and `model.py` do not import GTK and are tested with the core.
- Packaging: `packaging/arch` (PKGBUILD), `packaging/debian` (`build-deb.sh`), `install/install.sh`.

## Changes for 1.0

| Area | Change | Requirements | ADR |
|---|---|---|---|
| Daemon | Publish version and last reload result; `status` and the editor read and compare them | R-010 to R-012 | [0006](adr/0006-daemon-feedback-channel.md) |
| Docs | Preview is ephemeral (documented limitation) | R-013 | [0007](adr/0007-preview-known-to-daemon.md) |
| Packaging | Split Arch package, `.deb` for the editor, `make install-gui`, `install.sh --gui`, CI | R-020 to R-024 | 0002 |
| Packaging | Fedora via `install.sh` | R-025 | [0008](adr/0008-fedora-install-method.md) |
| Editor | Start from example config, undo/redo, service state, GTK minimum check | R-026, R-040 to R-042 | n/a |
| Stability | Document stable config and CLI; keep short zone form on save | R-001, R-002, R-005, R-006 | n/a |

## ADR index

| ADR | Title | Status |
|---|---|---|
| 0001 | Core depends only on the standard library | accepted |
| 0002 | GTK4 without libadwaita, optional package | accepted |
| 0003 | ISO French layout first | accepted |
| 0004 | Edited zone alone in color | accepted |
| 0005 | Single daemon, one-way FIFO | accepted |
| 0006 | Daemon feedback channel (state file) | accepted |
| 0007 | Preview is ephemeral, documented | accepted |
| 0008 | Fedora install method (portable sh script) | accepted |

## Verification

Tests cite requirement IDs (comment or docstring `R-0xx`). Hardware- and distribution-dependent requirements (R-030 to R-032) are verified by the VM checklist, results recorded in the README. No Gherkin (decision 2026-11-08).
