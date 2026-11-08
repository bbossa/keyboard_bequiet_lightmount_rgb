# ADR-0006: How the daemon reports results (version, reload outcome)

- Status: accepted 2026-11-08 (maintainer: the most universal option, easy to maintain, costs the system nothing)
- Requirements: R-010, R-011, R-012, R-013

## Context
Lived case: a 0.1.1 daemon silently ignored `reload`. The FIFO is one way, so the command and the editor cannot tell whether the daemon applied, refused, or does not know the command.

## Options
1. **State file** in `$XDG_RUNTIME_DIR/lightmount/` written by the daemon (version at startup, last reload result with timestamp and error). The sender polls it after sending.
2. **Unix socket** replacing the FIFO: request/response, stdlib, but a new protocol to maintain and secure.
3. **D-Bus session service** (`Reload`, `Preview`, `Status`, `Version`): the desktop-native choice, but no stdlib client (would need `busctl` calls or a dependency), against ADR-0001.

## Decision
Option 1: smallest change, stdlib, covers R-010 to R-012. Keep the FIFO as the command path. Revisit a socket or D-Bus after 1.0 if the interface needs more than version and last result.

## Consequences
The file format becomes part of the 1.x compatibility promise only if documented: keep it internal and undocumented, accessed through `status`.
