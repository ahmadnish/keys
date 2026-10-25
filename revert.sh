#!/usr/bin/env bash
# Source this file from Bash to revert both features, including this shell.
_keys_revert() {
    local base
    base=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd) || return 1
    "$base/shortcuts" stop || return 1
    source "$base/history.sh" --undo
}
if _keys_revert; then
    unset -f _keys_revert
else
    unset -f _keys_revert
    return 1 2>/dev/null || exit 1
fi
