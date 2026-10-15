# lightmount

Lighting control for the **be quiet! Light Mount** keyboard (USB `373f:0002`) on Linux, without the vendor's IO Center.

- **Fixed color zones**: top strip, knob, keys, left and right side strips, or your own zones down to single keys.
- **Reapplied automatically** at login, when the keyboard is replugged, and after the Fn+←/→ effect keys (which clear the custom colors).
- **Short alerts** on one zone: desktop notifications (green, red when critical) and failed shell commands (blue).
- Runs as a **systemd user service**. No root needed once the udev rule is installed.

Not affiliated with or endorsed by be quiet!. Use at your own risk; see [Safety](#safety).

## Requirements

- The be quiet! Light Mount keyboard. Tested with the version reported as `02 00 01 01 00 00 03 02` by `lightmount status`; other versions are read-only unless you allow them (see [Configuration](#configuration)).
- Linux with systemd (user services, `udevadm`, `busctl`).
- Python 3.11 or newer. No other dependency.

## Install

Pick one of the three methods.

### From the repository (any distribution)

```sh
git clone https://github.com/bbossa/keyboard_bequiet_lightmount_rgb.git
cd keyboard_bequiet_lightmount_rgb
install/install.sh --dry-run    # shows what would be done
install/install.sh              # user part: command, config, service, shell hooks (no sudo)
sudo install/install.sh --udev  # once: lets your session access the keyboard
```

`install.sh` links `~/.local/bin/lightmount` to the checkout: keep the repository where it is. Running it again only updates what changed; an existing config is never replaced.

### Arch Linux (PKGBUILD)

```sh
cd packaging/arch
makepkg -si
systemctl --user enable --now lightmount.service
```

### Debian / Ubuntu (.deb)

Needs Python 3.11 or newer (Debian 12, Ubuntu 23.04 and later).

```sh
make deb                                  # builds dist/lightmount_<version>-1_all.deb
sudo apt install ./dist/lightmount_*_all.deb
systemctl --user enable --now lightmount.service
```

The packages install the command in `/usr/bin`, the udev rule, the user service, the fish hook and, in `/usr/share/lightmount/`, the example config and the bash/zsh hooks. Do not mix a package with `install.sh`: uninstall one before installing the other.

After installing the udev rule, replug the keyboard (or log in again) so that your session gets access to it.

## Usage

```sh
lightmount check     # validate the config, without touching the keyboard
lightmount apply     # apply the zones once
lightmount status    # device, version, lighting mode, daemon state
lightmount alert normal|critical|error   # test an alert
```

The service (`lightmount watch`) applies the zones at startup. After editing the config, run `lightmount check`, then `systemctl --user restart lightmount`.

## Configuration

`~/.config/lightmount/config.toml`. The fully commented example is [`install/config.toml`](install/config.toml) (`/usr/share/lightmount/config.toml` with a package). Without a config file, built-in defaults are used.

```toml
[zones.top]
leds = ["00-2c"]      # vendor LED indexes, hex, single or ranges
color = "f4dbae"
dim = 0.3             # custom mode has no brightness: colors are scaled

[zones.keys]
leds = ["2e-9d"]
color = "ff2a00"

[alerts]
zone = "top"          # or "knob" for a discreet alert
duration = 1.25
normal = "00ff00"
critical = "ff0000"
error = "0000ff"
```

| LED indexes | Zone |
| --- | --- |
| `00-2c` | top strip |
| `2d` | knob |
| `2e-9d` | keys, row by row, left to right (`62` and `89` do not exist) |
| `9e-a2` | left side strip |
| `a3-a7` | right side strip |

Other sections:

- `[device]`: `usb_path` picks one keyboard when several are plugged in; `allow_unknown_firmware = true` allows writing to a version that was never tested.
- `[daemon]`: `reapply_on_effect_key` (default `true`) reapplies the zones after Fn+←/→; `poll_interval` (seconds, default `0` = off) rereads the lighting mode periodically.
- `[alerts.sources]`: `notifications` and `shell` turn each alert source on or off.

Rendering tip: too much green turns yellow (`ff6a00` looks yellow, `ff2a00` looks orange), and pure white is harsh on the strips.

## Shell alerts

A failed command (exit status other than 0 and 130 = Ctrl+C) flashes the alert zone in the `error` color.

- **fish**: loaded automatically, in new fish sessions.
- **bash** (4.4+): add `source ~/.local/share/lightmount/lightmount.bash` to `~/.bashrc` (`/usr/share/lightmount/lightmount.bash` with a package).
- **zsh**: add `source ~/.local/share/lightmount/lightmount.zsh` to `~/.zshrc` (`/usr/share/lightmount/lightmount.zsh` with a package).

Only the exit status is used. Notifications are matched on their urgency only; their content is never read or logged.

## Troubleshooting

| Message | Cause and fix |
| --- | --- |
| `Light Mount not found` | Keyboard unplugged, or a different model. Check `lsusb -d 373f:0002`. |
| `/dev/hidrawN: permission denied` | The udev rule is missing: `sudo install/install.sh --udev`, then replug the keyboard. |
| `unknown version …, nothing written` | Untested version. Please open an issue with the `lightmount status` output; `allow_unknown_firmware = true` forces writing. |
| `several Light Mount keyboards` | Set `usb_path` in `[device]` to one of the listed paths. |
| Colors change by themselves | An open IO Center (web) tab reapplies its own settings: close it while lightmount runs. |
| Colors gone or back to the factory effect after using IO Center | An IO Center session clears the custom colors or switches the keyboard to effects mode, which lightmount does not detect (so that a firmware effect can be chosen on purpose). Close the IO Center tab, then run `lightmount apply`. |
| M1–M5 (or other remapped keys) back to their factory functions | Key assignments are stored in the keyboard; lightmount never changes them. Some IO Center sessions (for example in a Windows VM) restore the defaults: reassign the keys in IO Center, then close it and run `lightmount apply`. |
| Win key does nothing | Game mode (Fn+Pause) disables it; press Fn+Pause again. |

Logs: `journalctl --user -u lightmount`. Add `Environment=LIGHTMOUNT_DEBUG=1` to the service for debug messages.

## Uninstall

- `install.sh` setup: `install/uninstall.sh` (`--dry-run` to preview, `--purge-config` to remove the config too). The udev rule is reported, not removed.
- Packages: `systemctl --user disable --now lightmount.service`, then `sudo pacman -R lightmount` or `sudo apt remove lightmount`.

The keyboard keeps its last colors until it is unplugged, then restarts with its stored effect.

## Safety

- Only two kinds of frames are written: standard HID LampArray reports, and vendor frames that are reproduced byte for byte from captures of the vendor software (`make check`).
- No firmware update is ever sent, and no firmware-related frame is replayed.
- Custom colors are volatile (lost on unplug): alerts do not wear the keyboard's flash memory.

## Development

```sh
make check      # unit tests, no keyboard needed (plus capture checks when captures/ is present)
```

`lightmount/` is the package (`protocol.py` has no I/O and documents the frame format); `bin/lightmount` runs it from a checkout. The tests use reference frames extracted from captures of the vendor software (`tests/fixtures/`).

## License

GPL-2.0-or-later, see [LICENSE](LICENSE).
