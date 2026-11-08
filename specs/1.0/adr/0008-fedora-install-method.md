# ADR-0008: Install method for Fedora

- Status: accepted 2026-11-08 (decided by the maintainer: a portable `sh` script, no RPM for 1.0)
- Requirements: R-025, R-030

## Context
Arch has a `PKGBUILD`, Debian/Ubuntu a `.deb`; Fedora has nothing, and the validation matrix (R-030) includes it.

## Options
1. `install/install.sh` from the repository, documented and tested on Fedora (SELinux and `hidraw`, `systemctl --user`).
2. A `.spec` file and RPM in the release.
3. A Copr repository.

## Decision
Option 1: `install/install.sh` stays a portable POSIX `sh` script that works on any distribution, not only Fedora. The Fedora VM test is the proof. RPM/Copr after 1.0 only if there is demand.

## Consequences
No distribution-specific code in the script. Fedora users keep the checkout in place (`install.sh` links to it); the README says so.
