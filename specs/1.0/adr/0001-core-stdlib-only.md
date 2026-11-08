# ADR-0001: The core depends only on the Python standard library

- Status: accepted (retroactive, project start)
- Requirements: R-003, R-027

## Context
lightmount is installed as a user service on many distributions, and reads/writes a USB HID device. Every dependency adds packaging work and a failure mode on the install matrix (R-030).

## Decision
The core requires Python 3.11 or newer and nothing else. Anything needing a library (GTK) goes in an optional package.

## Alternatives considered
- Depend on PyGObject/dbus-python in the core: richer but breaks the "works everywhere with Python" promise.
- `tomli-w` to write TOML: avoided, `save.py` rewrites only the managed tables itself (also preserves comments, which `tomli-w` does not).

## Consequences
TOML is read with `tomllib` (hence Python 3.11+: excludes Debian 11 and Ubuntu 22.04). D-Bus has no stdlib client, which weighs on ADR-0006.
