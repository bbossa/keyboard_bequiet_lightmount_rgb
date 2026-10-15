# lightmount: flash the keyboard alert zone when a command fails (fish, loaded from conf.d).
# 130 = Ctrl+C, ignored.
function __lightmount_on_error --on-event fish_postexec
    set -l code $status
    if test $code -ne 0 -a $code -ne 130 -a -p "$XDG_RUNTIME_DIR/lightmount.fifo"
        command lightmount alert error &
        disown
    end
end
