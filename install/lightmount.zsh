# lightmount: flash the keyboard alert zone when a command fails (zsh).
# Add to ~/.zshrc:  source ~/.local/share/lightmount/lightmount.zsh   (install.sh)
#              or:  source /usr/share/lightmount/lightmount.zsh          (packages)
# 130 = Ctrl+C, ignored. Only after a command actually ran (not on an empty line).
__lightmount_preexec() { __lightmount_ran=1 }
__lightmount_precmd() {
    local code=$?
    [[ -n ${__lightmount_ran-} ]] || return
    unset __lightmount_ran
    if (( code != 0 && code != 130 )) && [[ -p ${XDG_RUNTIME_DIR:-/tmp}/lightmount.fifo ]]; then
        (command lightmount alert error >/dev/null 2>&1 &)
    fi
}
autoload -Uz add-zsh-hook
add-zsh-hook preexec __lightmount_preexec
add-zsh-hook precmd __lightmount_precmd
