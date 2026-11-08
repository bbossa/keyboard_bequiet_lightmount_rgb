# ADR-0003: ISO French layout only at first

- Status: accepted 2026-10-24 (retroactive record)
- Requirements: R-045, R-046

## Context
Four product layouts exist (ISO FR, DE, UK, ANSI) sharing the vendor LED numbering, but only an ISO FR keyboard is available to verify the key map. `lightmount calibrate` confirmed 110 keys and the knob.

## Decision
Ship only the verified ISO FR layout. Others come from contributors who own one, through a "help wanted" issue and `calibrate --layout`.

## Alternatives considered
- Ship all four from the product images unverified: risk of wrong labels shown as fact.

## Consequences
Users with another layout see a labelled-wrong keyboard until a contributor verifies it. The ANSI/ISO differences (LED `62`, `77`, `7e`, `89`) stay a hypothesis in the notes.
