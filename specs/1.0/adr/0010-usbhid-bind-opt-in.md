# ADR-0010: Opt-in udev + systemd template to bind USB interface 03 to `usbhid`

- Status: accepted 2026-11-27 (maintainer approved option 2, opt-in, outside the packages)
- Requirements: R-060 to R-066
- Source: issue #3 (Bazzite: interface 3 of `373f:0002` not bound to `usbhid` after boot or reconnect)

## Context

On some systems (reported on Bazzite), the keyboard's USB interface 3 — the LampArray lighting interface — is not bound to `usbhid` automatically, so no `hidraw` node appears for it and lightmount cannot reach the LEDs. The manual workaround writes the sysfs name to the driver's `bind` file:

```bash
echo '1-2:1.3' | sudo tee /sys/bus/usb/drivers/usbhid/bind
```

That sysfs name (`1-2:1.3`) changes with the USB topology, and the workaround must be repeated after every boot and every replug. Issue #3 asks for an optional, installed rule that matches the stable identifiers (VID/PID + interface number) and covers both startup and reconnects.

## Options

1. **udev rule alone**, with `RUN+="/bin/sh -c 'echo %k > /sys/bus/usb/drivers/usbhid/bind'"`. One file, but no journal logging and no retry if the bind fails; udev discourages non-trivial work in `RUN`.
2. **udev rule + systemd template unit** (the proposal of issue #3): the rule matches `idVendor`/`idProduct`/`bInterfaceNumber` and sets `TAG+="systemd"`, `ENV{SYSTEMD_WANTS}+="lightmount-usbhid-bind@.service"`; the template writes `%I` (the interface name) to the `bind` file. Logging via the journal, restartable, and udev coldplug replays `add` at boot, so both boot and replug are covered.
3. `echo "373f 0002" > /sys/bus/usb/drivers/usbhid/new_id`. Rejected: `new_id` matches VID/PID only, so it would bind **all** interfaces of the keyboard to `usbhid`, not just interface 03.
4. A polkit helper called by the user-level daemon. Rejected: the daemon runs as a user service and must stay rootless; a polkit agent is far heavier than the problem.

## Decision

Option 2, as an **opt-in** install step: `sudo install/install.sh --usbhid-bind` installs two system files:

- `/etc/udev/rules.d/71-bequiet-light-mount-usbhid-bind.rules` (named after the existing `70-bequiet-light-mount.rules`)
- `/etc/systemd/system/lightmount-usbhid-bind@.service` (prefixed with the project name to avoid collisions)

The packages (`Makefile`, PKGBUILD, `.deb`) do **not** install these files: binding a USB interface is a system-level change and stays an explicit choice of the user (R-065). `install/uninstall.sh` reports the two files and how to remove them (R-064).

## Consequences

- Two extra files under `install/`, installed only on explicit request; `--dry-run` previews them like any other step (R-063).
- The rule matches `373f:0002` + `bInterfaceNumber=="03"` only, never the changeable bus path (R-062); other devices are untouched.
- After install, already-present interfaces are triggered once so the bind applies immediately, without replug.
- lightmount itself is unchanged: once `usbhid` claims the interface, the existing `uaccess` rule gives the session access to the new `hidraw` node.
