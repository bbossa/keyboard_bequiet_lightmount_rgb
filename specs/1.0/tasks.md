# lightmount 1.0: tasks

Order: decisions first (they unblock code), then packaging, then editor, then VM validation, then release. `[ ]` todo, `[x]` done.

## 0. Decisions
- [x] ADR-0006 accepted 2026-11-08 (state file)
- [x] ADR-0007 accepted 2026-11-08 (ephemeral preview, documented)
- [x] ADR-0008 accepted 2026-11-08 (portable sh script)

## 1. Daemon (R-010 to R-013)
- [ ] Daemon writes version at startup (R-010)
- [ ] `status` and editor compare versions and warn (R-011)
- [ ] `reload` result readable by the sender (R-012)
- [ ] Document the ephemeral preview in README and editor (R-013)
- [ ] Tests citing R-010 to R-012

## 2. Packaging (R-020 to R-026)
- [ ] `make install-gui`: modules, launcher, `.desktop`, icon, metainfo (R-020)
- [ ] Arch split `pkgname=(lightmount lightmount-gui)` (R-021)
- [ ] `.deb` `lightmount-gui` in `build-deb.sh` (R-022)
- [ ] `install.sh --gui` (R-023)
- [ ] CI: build, install both, `lightmount-gui --version` (R-024)
- [ ] GTK minimum version check in the editor (R-026)
- [ ] Check `install.sh` is POSIX `sh` and runs on all three VMs; document it for Fedora (R-025)

## 3. Editor (R-005, R-040 to R-042, R-046)
- [ ] Start from commented example config (R-040)
- [ ] Undo/redo (R-041)
- [ ] Service state in the window (R-042)
- [ ] Short zone form kept on save (R-005)
- [ ] "Help wanted" issue for other layouts (R-046)

## 4. Stability and docs (R-001, R-002, R-006, R-050, R-051)
- [ ] README: config and CLI declared stable (R-006)
- [ ] Review config keys and CLI exit codes before freezing (R-001, R-002)

## 5. VM validation (R-030 to R-033)
- [ ] Prepare Arch, Ubuntu LTS, Fedora VMs (libvirt session) and keyboard USB passthrough
- [ ] Run the checklist on each, without then with the keyboard (R-031)
- [ ] Fix what the VMs reveal
- [ ] README "Tested on" and minimum GTK (R-032, R-033)

## 6. Release
- [ ] CHANGELOG 1.0.0 section, release notes (R-050, R-051)
- [ ] Tag v1.0.0
- [ ] AUR publication when registration reopens (R-028, optional)
