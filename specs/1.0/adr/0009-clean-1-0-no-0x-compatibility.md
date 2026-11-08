# ADR-0009: 1.0 favours clean code over compatibility with 0.x

- Status: accepted 2026-11-08 (maintainer: "better to write clean, maintainable code; we move to 1.x, so no backward compatibility with 0.x is guaranteed")
- Requirements: R-001, R-002, R-011, R-012

## Context
The compatibility promise of R-001 and R-002 starts at 1.0. Before that, the changelog already says a minor version may change the config or the commands. Some 1.0 choices are cleaner if 0.x behaviour is not preserved, for example the exit code of `reload` when the daemon does not answer (0 today).

## Decision
Where a 0.x behaviour is ambiguous or misleading, 1.0 picks the clean behaviour and does not keep the old one. Every such change is listed under a "Changed" or "Removed" heading of the 1.0.0 changelog section, with the migration step if any. From 1.0.0 on, R-001 and R-002 apply in full.

First application: `lightmount reload` exits 1 when the daemon gives no answer (timeout) or refuses the config; exit 0 only on confirmed success.

## Alternatives considered
- Keep exit 0 on timeout so that scripts written for 0.x keep working: hides the failure, and the 0.x user base is small (a handful of releases, one maintainer and a few readers of the public repository).

## Consequences
A script that ran `lightmount reload` against an old daemon now sees a failure, which is the point. Anyone upgrading from 0.x reads the 1.0.0 notes. Further breaking cleanups are allowed until the 1.0.0 tag, then none until 2.0.
