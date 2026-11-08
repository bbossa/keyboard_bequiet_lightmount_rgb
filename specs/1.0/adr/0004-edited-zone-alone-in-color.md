# ADR-0004: Show the edited zone alone in color, not IO Center-style layers

- Status: accepted 2026-10-28 (retroactive record); reconsider after real use
- Requirements: R-043

## Context
IO Center edits with layers. The editor needs to show which keys belong to the zone being edited without visual noise.

## Decision
Only the zone being edited is drawn in color; the others are muted.

## Alternatives considered
- Layers with per-layer visibility: more powerful, more UI and more model (z-order, blending) for a keyboard with a few zones.

## Consequences
Overlapping zones are not visualised as stacked. Listed as deferred in the requirements.
