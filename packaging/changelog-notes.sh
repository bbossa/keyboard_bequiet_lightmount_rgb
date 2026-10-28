#!/bin/sh
# Print the CHANGELOG.md section of a version (release notes): packaging/changelog-notes.sh 0.2.0
# Empty output if the version has no section.
set -eu
here=$(dirname "$0")
awk -v head="## [$1]" '
    index($0, head) == 1 { found = 1; next }
    found && (/^## \[/ || /^\[[^]]*\]: /) { exit }
    found
' "$here/../CHANGELOG.md" | sed -e '/./,$!d' | sed -e ':a' -e '/^\n*$/{$d;N;ba' -e '}'
