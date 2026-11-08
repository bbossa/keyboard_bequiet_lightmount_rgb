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
| Daemon | Publish version and last reload result in the state file (below); `status` and the editor read and compare them | R-010 to R-012, R-015 | [0006](adr/0006-daemon-feedback-channel.md) |
| Docs | Preview is ephemeral (documented limitation) | R-013 | [0007](adr/0007-preview-known-to-daemon.md) |
| Packaging | Split Arch package, `.deb` for the editor, `make install-gui`, `install.sh --gui`, CI | R-020 to R-024 | 0002 |
| Packaging | Fedora via `install.sh` | R-025 | [0008](adr/0008-fedora-install-method.md) |
| Editor | Start from example config, undo/redo, service state, GTK minimum check | R-026, R-040 to R-042 | n/a |
| Stability | Document stable config and CLI; keep short zone form on save | R-001, R-002, R-005, R-006 | n/a |

## State file (R-010 to R-012, R-015; ADR-0006)

**Location.** `$XDG_RUNTIME_DIR/lightmount.state`, next to `lightmount.fifo` and `lightmount.lock` (same `RUNTIME` constant in `daemon.py`). It lives on tmpfs, so it disappears at logout or reboot. Mode `0600`.

**Format.** One JSON object (stdlib `json`, extensible, readable with `cat`). Internal: not documented as a public interface, not covered by the 1.x promise; users go through `lightmount status`.

```json
{
  "format": 1,
  "version": "1.0.0",
  "pid": 4242,
  "started": 1793000000.0,
  "reload": {"seq": 3, "time": 1793000100.0, "ok": true, "error": null, "warnings": []}
}
```

| Field | Meaning |
|---|---|
| `format` | Layout version of this file. A reader that does not know it treats the daemon as unknown (below). |
| `version` | `lightmount.__version__` of the running daemon. |
| `pid` | Daemon process id, to detect a stale file. |
| `started` | Start time (epoch seconds). |
| `reload.seq` | Counter of reload attempts since the daemon started (0 at start). |
| `reload.time` | When the last attempt finished. |
| `reload.ok` | `true` if the new config was applied, `false` if refused (the previous one is kept). |
| `reload.error` | Error text when refused, otherwise `null`. |
| `reload.warnings` | Config warnings, plus "restart needed" when `[daemon]` or `alerts.sources.notifications` changed. |

**Writer (daemon).** Atomic: write `lightmount.state.tmp` then `os.replace`. Written once before the event loop (`reload.seq` = 0, `reload` otherwise empty), and after every reload attempt, accepted or refused (`Daemon.reload()`). Removed on a clean exit (SIGTERM). A write failure is logged and never stops the daemon.

**Reader (CLI and editor).** Valid only if the file parses, `format` is known and `pid` is alive. Otherwise the daemon version is **unknown**.

| Situation | `status` and editor show |
|---|---|
| Valid, same `version` | `daemon: active (1.0.0)` |
| Valid, other `version` | `daemon: active (0.2.0, command is 1.0.0): restart the service` (R-011) |
| No valid file, service reported active by systemd | `daemon: active (version unknown, older than 1.0?): restart the service` (the lived 0.1.1 case) |
| No valid file, service not active | no daemon, unchanged behaviour |

**Reload result (R-012).** The FIFO stays one way and its message does not change. The sender reads `reload.seq` (or 0 if no file), sends `reload`, then polls the file (every 50 ms, up to 3 s) until `seq` increases, and reports `ok` or `error`. Timeout: "no answer from the daemon (older version? see `lightmount status`)". Two simultaneous reloads may not be told apart; accepted, since the file always shows the latest result.

**Exit codes of `reload`** ([ADR-0009](adr/0009-clean-1-0-no-0x-compatibility.md)). Config invalid (validated by the sender first) = exit 1. Daemon refused after that (race) = exit 1. No answer from the daemon within the timeout = exit 1 with the message above on stderr: nothing was confirmed, so the command does not claim success. Exit 0 only when the daemon reports `ok`. Without a running daemon, behaviour is unchanged (the zones are applied once, exit 0).

**Not stored.** No alert history, no notification content, no keyboard state: the file is only version and last reload result.

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
| 0009 | Clean 1.0: no compatibility with 0.x | accepted |

## Verification

Tests cite requirement IDs (comment or docstring `R-0xx`). Hardware- and distribution-dependent requirements (R-030 to R-032) are verified by the VM checklist, results recorded in the README. No Gherkin (decision 2026-11-08).
