# ADR-0002: GTK4 without libadwaita, as an optional `lightmount-gui` package

- Status: accepted 2026-10-24 (retroactive record)
- Requirements: R-020 to R-023, R-027

## Context
The tool is built for the maintainer's own use but shared publicly. The maintainer uses KDE and Hyprland and dislikes GNOME styling.

## Decision
The editor is written with PyGObject and plain GTK4 (no libadwaita), shipped as a separate optional package.

## Alternatives considered
- PyQt6 (as the sibling project iocenter-linux): fits KDE, but a heavier dependency and a GPL-3-only neighbour to stay clear of.
- libadwaita: GNOME look, rejected by preference; "not closed" if the project grows.
- A local web page: rejected, fine for personal use, unusual for a shared project.
- Quickshell-only: ties the tool to one setup.

## Consequences
The GTK minimum version becomes a packaging constraint (`Gtk.ColorDialog` and `Gtk.AlertDialog` need GTK 4.10; Ubuntu LTS is the limit case, see R-026, R-033).
