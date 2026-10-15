#!/bin/bash
# Remove lightmount for the current user. No sudo: the udev rule is only reported.
#
# Usage: install/uninstall.sh [--dry-run] [--purge-config]
#   --purge-config   also remove ~/.config/lightmount (kept by default)
#
# The keyboard keeps its last colors until it is unplugged; it then restarts
# with its stored effect.
set -euo pipefail

here=$(dirname "$(readlink -f "$0")")
repo=$(readlink -f "$here/..")
rule_dest=/etc/udev/rules.d/70-bequiet-light-mount.rules

dry_run=0
purge=0
for arg in "$@"; do
    case $arg in
        --dry-run) dry_run=1 ;;
        --purge-config) purge=1 ;;
        -h | --help) sed -n '2,9s/^# \{0,1\}//p' "$0"; exit 0 ;;
        *) echo "unknown option: $arg (see --help)" >&2; exit 2 ;;
    esac
done

say() { printf '%s\n' "$*"; }

run() {
    if ((dry_run)); then
        say "  would run: $*"
    else
        "$@"
    fi
}

# remove PATH: remove a file, symlink or directory if present
remove() {
    if [ -e "$1" ] || [ -L "$1" ]; then
        if ((dry_run)); then
            say "  would remove  $1"
        else
            rm -rf -- "$1"
            say "  removed  $1"
        fi
    fi
}

[ "$(id -u)" -ne 0 ] || { echo "error: run without sudo" >&2; exit 1; }
((dry_run)) && say "dry run: nothing is changed"

say "service"
unit=$HOME/.config/systemd/user/lightmount.service
if command -v systemctl >/dev/null && [ -e "$unit" ]; then
    run systemctl --user disable --now lightmount.service
    remove "$unit"
    run systemctl --user daemon-reload
    run systemctl --user reset-failed lightmount.service 2>/dev/null || true
fi
runtime=${XDG_RUNTIME_DIR:-/tmp}
remove "$runtime/lightmount.fifo"
remove "$runtime/lightmount.lock"

say "command"
link=$HOME/.local/bin/lightmount
case $(readlink "$link" 2>/dev/null) in  # bin/: current layout; tools/: before 0.1.0
    "$repo/bin/lightmount" | "$repo/tools/lightmount.py") ours=1 ;;
    *) ours=0 ;;
esac
if [ -L "$link" ] && ((ours)); then
    remove "$link"
elif [ -e "$link" ] || [ -L "$link" ]; then
    say "  kept     $link (does not point to this checkout)"
fi

say "shell hooks"
fish_hook=$HOME/.config/fish/conf.d/lightmount.fish
if grep -qs __lightmount_on_error "$fish_hook"; then
    remove "$fish_hook"
fi
remove "$HOME/.local/share/lightmount"
for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    grep -qs 'lightmount/lightmount\.' "$rc" && say "  remove the 'source ~/.local/share/lightmount/...' line from $rc"
done

say "config"
if ((purge)); then
    remove "$HOME/.config/lightmount"
elif [ -e "$HOME/.config/lightmount" ]; then
    say "  kept     $HOME/.config/lightmount (--purge-config to remove it)"
fi

if [ -e "$rule_dest" ]; then
    say ""
    say "The udev rule is left in place (it only grants access to this keyboard). To remove it:"
    say "  sudo rm $rule_dest && sudo udevadm control --reload"
fi
