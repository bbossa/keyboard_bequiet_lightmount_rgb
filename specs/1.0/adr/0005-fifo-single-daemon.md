# ADR-0005: One daemon owns config and alert state; CLI and GUI talk to it through a one-way FIFO

- Status: accepted (retroactive record, state on 2026-10-28)
- Requirements: R-014; context for R-010 to R-013 and ADR-0006

## Context
Several processes write the keyboard: the daemon, the CLI, the editor. Writes must not interleave.

## Decision
A single daemon (`lightmount watch`) holds config and alert state. CLI and GUI import the core, send commands to the FIFO (one way) and write the keyboard under the shared lock `lightmount.lock`.

## Alternatives considered
See ADR-0006 for the replacements being weighed (socket, D-Bus).

## Consequences
Simple and stdlib-only, but the sender never learns the outcome of a command, and the daemon does not know about previews.
