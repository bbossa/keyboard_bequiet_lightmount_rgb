# lightmount: flash the keyboard alert zone when a command fails (bash 4.4+).
# Add to ~/.bashrc:  source ~/.local/share/lightmount/lightmount.bash   (install.sh)
#               or:  source /usr/share/lightmount/lightmount.bash          (packages)
# 130 = Ctrl+C, ignored. PS0 is expanded just before a typed command runs (never
# for an empty line): the arithmetic in its substring offset marks that a command
# ran, and the whole expands to nothing (BASH_VERSION is never empty).
__lightmount_on_error() {
    local code=$?
    if [ -n "${__lightmount_ran-}" ]; then
        __lightmount_ran=
        if [ "$code" -ne 0 ] && [ "$code" -ne 130 ] && [ -p "${XDG_RUNTIME_DIR:-/tmp}/lightmount.fifo" ]; then
            (command lightmount alert error >/dev/null 2>&1 &)
        fi
    fi
    return "$code"
}
case ${PS0-} in
    *__lightmount_ran*) ;;
    *) PS0="${PS0-}"'${BASH_VERSION:$((__lightmount_ran=1, 0)):0}' ;;
esac
case ";${PROMPT_COMMAND-};" in
    *";__lightmount_on_error;"*) ;;
    *) PROMPT_COMMAND="__lightmount_on_error${PROMPT_COMMAND:+;$PROMPT_COMMAND}" ;;
esac
