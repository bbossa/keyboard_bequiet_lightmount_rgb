#!/bin/bash
# Install lightmount for the current user. Safe to run again: unchanged files are left alone.
#
# Usage:
#   install/install.sh [--dry-run]            user part, no sudo: command, config, service, shell hooks
#   sudo install/install.sh --udev [--dry-run]   udev rule giving the logged-in user access to the keyboard
#
# The command is a symlink to this checkout: keep the repository where it is
# (or run this script again after moving it).
set -euo pipefail

here=$(dirname "$(readlink -f "$0")")
repo=$(readlink -f "$here/..")
rule_name=70-bequiet-light-mount.rules
rule_dest=/etc/udev/rules.d/$rule_name

dry_run=0
udev=0
for arg in "$@"; do
    case $arg in
        --dry-run) dry_run=1 ;;
        --udev) udev=1 ;;
        -h | --help) sed -n '2,10s/^# \{0,1\}//p' "$0"; exit 0 ;;
        *) echo "unknown option: $arg (see --help)" >&2; exit 2 ;;
    esac
done

say() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# run CMD...: run it, or only show it with --dry-run
run() {
    if ((dry_run)); then
        say "  would run: $*"
    else
        "$@"
    fi
}

# put SRC DEST MODE: install a file if missing or different; sets $changed
put() {
    local src=$1 dest=$2 mode=$3
    changed=0
    if [ -f "$dest" ] && cmp -s "$src" "$dest"; then
        say "  unchanged  $dest"
        return
    fi
    changed=1
    if ((dry_run)); then
        say "  would $([ -e "$dest" ] && echo update || echo install)  $dest"
    else
        say "  $([ -e "$dest" ] && echo updated || echo installed)  $dest"
        install -D -m "$mode" "$src" "$dest"
    fi
}

# --- udev rule (root) -------------------------------------------------------

if ((udev)); then
    ((dry_run)) || [ "$(id -u)" -eq 0 ] || die "--udev needs root: sudo $0 --udev"
    say "udev rule ($rule_dest): lets the logged-in user open the keyboard's hidraw nodes"
    put "$here/$rule_name" "$rule_dest" 644
    if ((changed)); then
        run udevadm control --reload
        run udevadm trigger --action=change --subsystem-match=hidraw
    fi
    exit 0
fi

# --- user part --------------------------------------------------------------

[ "$(id -u)" -ne 0 ] || die "run the user part without sudo (only --udev needs root)"

say "checking dependencies"
command -v python3 >/dev/null || die "python3 not found"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
    || die "Python 3.11 or newer is needed (tomllib), found $(python3 -V 2>&1)"
command -v systemctl >/dev/null && systemctl --user show-environment >/dev/null 2>&1 \
    || die "no systemd user manager (systemctl --user): the daemon runs as a user service"
command -v udevadm >/dev/null || warn "udevadm not found: the zones will not be reapplied on replug"
command -v busctl >/dev/null || warn "busctl not found: no alert on desktop notifications"
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) warn "$HOME/.local/bin is not in PATH: the shell hooks and the 'lightmount' command need it" ;;
esac
((dry_run)) && say "dry run: nothing is changed"

say "command"
link=$HOME/.local/bin/lightmount
target=$repo/bin/lightmount
if [ "$(readlink "$link" 2>/dev/null)" = "$target" ]; then
    say "  unchanged  $link"
else
    [ -e "$link" ] && [ ! -L "$link" ] && die "$link exists and is not a symlink: remove it first"
    run mkdir -p "$HOME/.local/bin"
    run ln -sfn "$target" "$link"
    ((dry_run)) || say "  linked     $link -> $target"
fi

say "config"
config=$HOME/.config/lightmount/config.toml
if [ -e "$config" ]; then
    say "  kept       $config (existing file never replaced; example: $here/config.toml)"
else
    put "$here/config.toml" "$config" 644
fi

say "shell hooks"
if command -v fish >/dev/null; then
    put "$here/lightmount.fish" "$HOME/.config/fish/conf.d/lightmount.fish" 644
    ((changed)) && say "             (new fish sessions only: fish reads conf.d at startup)"
fi
for shell in bash zsh; do
    command -v "$shell" >/dev/null || continue
    hook=$HOME/.local/share/lightmount/lightmount.$shell
    put "$here/lightmount.$shell" "$hook" 644
    rc=$HOME/.${shell}rc
    grep -qs "lightmount/lightmount.$shell" "$rc" \
        || say "             to enable it, add to $rc:  source ~/.local/share/lightmount/lightmount.$shell"
done

say "service"
unit=$HOME/.config/systemd/user/lightmount.service
put "$here/lightmount.service" "$unit" 644
unit_changed=$changed
if ((unit_changed)); then
    run systemctl --user daemon-reload
fi
if systemctl --user is-enabled --quiet lightmount.service 2>/dev/null \
        && systemctl --user is-active --quiet lightmount.service; then
    if ((unit_changed)); then
        say "  restarting lightmount.service (unit changed; reapplies the zones)"
        run systemctl --user restart lightmount.service
    else
        say "  running    lightmount.service (restart it to load code changes)"
    fi
else
    run systemctl --user enable --now lightmount.service
    ((dry_run)) || say "  started    lightmount.service"
fi

say "checks"
if ((dry_run)); then
    say "  would run: lightmount check"
else
    "$link" check || warn "the config has errors: fix them, then systemctl --user restart lightmount"
fi
if [ ! -f "$rule_dest" ]; then
    say ""
    say "Next step, needs root once: the udev rule gives your session access to the keyboard."
    say "  sudo $0 --udev"
fi
say ""
say "Verify with: lightmount status"
