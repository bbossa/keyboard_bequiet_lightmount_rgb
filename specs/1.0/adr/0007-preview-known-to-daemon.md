# ADR-0007: Preview and daemon reapplication

- Status: accepted 2026-11-08 (maintainer: a preview is ephemeral by definition, short-lived, no persistence)
- Requirements: R-013

## Context
The preview writes colors under the lock without touching the config. A resume, a replug or an effect key makes the daemon reapply the saved config and erase it.

## Options
1. Daemon receives a `preview` command (and a `preview-off`), keeps the preview as an overlay until cleared or timed out.
2. The editor listens for those events and resends the preview.
3. Accept the behaviour and document it (the preview is a short-lived visual aid).

## Decision
Option 3: the limitation is accepted and documented (README and editor help): a resume, replug or effect key clears the preview. Options 1 and 2 are not pursued.

## Consequences
R-013 is satisfied by documentation, not by code: the requirement is reworded to "shall document that the preview is cleared".
