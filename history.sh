#!/usr/bin/env bash
# Source this helper to also update the CURRENT Bash; execution affects new ones.
_keys_history_change() (
    set -eu
    state=${XDG_STATE_HOME:-"$HOME/.local/state"}/ahmadnish-keys
    target=${INPUTRC:-"$HOME/.inputrc"}
    if [ "${1:-}" = --undo ]; then
        [ -f "$state/target" ] || { printf '%s\n' 'No saved history setup to revert.'; exit 0; }
        target=$(cat "$state/target")
        # Never overwrite edits made after installation.
        if ! cmp -s "$target" "$state/installed"; then
            printf 'The file changed since setup: %s\nNo edits overwritten. Original: %s/original\nRemove the marked ahmadnish block manually, or reconcile changes first.\n' "$target" "$state" >&2
            exit 1
        fi
        if [ -f "$state/original" ]; then
            cp -p "$state/original" "$target"
        else
            rm -- "$target"
        fi
        printf 'Restored: %s\n' "$target"
        touch "$state/reverted"
        exit 0
    fi
    [ "${1:-}" = '' ] || { printf '%s\n' 'Usage: source history.sh [--undo]' >&2; exit 1; }
    if [ -r /etc/os-release ]; then
        . /etc/os-release
        printf 'Distribution: %s\n' "${PRETTY_NAME:-Linux}"
    else printf 'System: %s\n' "$(uname -s)"; fi
    printf 'Login shell: %s; Bash version: %s\n' "${SHELL:-unknown}" "$BASH_VERSION"
    printf 'Interactive Bash startup: %s\n' "$HOME/.bashrc"
    for profile in "$HOME/.bash_profile" "$HOME/.bash_login" "$HOME/.profile"; do
        if [ -f "$profile" ]; then printf 'First login startup file: %s\n' "$profile"; break; fi
    done
    if [ -L "$target" ]; then
        command -v realpath >/dev/null || { echo 'Need realpath to preserve the INPUTRC symlink.' >&2; exit 1; }
        target=$(realpath "$target")
    fi
    home_root=$(CDPATH= cd -- "$HOME" && pwd -P)
    case "$target" in "$HOME"/*|"$home_root"/*) ;; *) printf 'Refusing non-home INPUTRC: %s\n' "$target" >&2; exit 1 ;; esac
    [ ! -e "$target" ] || [ -f "$target" ] || { echo 'INPUTRC is not a regular file.' >&2; exit 1; }
    if [ -e "$state" ]; then
        if [ -f "$state/target" ] && [ "$(cat "$state/target")" = "$target" ] && cmp -s "$target" "$state/installed"; then
            printf 'History bindings already installed: %s\n' "$target"; exit 0
        fi
        echo "Saved state exists or the file changed: $state. Revert/reconcile it before installing again." >&2
        exit 1
    fi
    umask 077
    mkdir -p "$(dirname "$target")" "$(dirname "$state")"
    mkdir "$state"
    printf '%s\n' "$target" > "$state/target"
    if [ -f "$target" ]; then cp -p "$target" "$state/original"; fi
    # Snapshot only the four effective bindings, for immediate undo in Bash.
    # A fresh interactive Bash reads the original INPUTRC before it is changed.
    { case $- in *i*) bind -p ;; *) bash --noprofile --norc -ic 'bind -p' 2>/dev/null ;; esac; } |
        grep -F -e '"\e[A":' -e '"\e[B":' -e '"\eOA":' -e '"\eOB":' -e '"\M-[A":' -e '"\M-[B":' -e '"\M-OA":' -e '"\M-OB":' > "$state/bindings" || :
    temp=$(mktemp "${target}.tmp.XXXXXX")
    committed=no
    cleanup() {
        rm -f -- "$temp"
        if [ "$committed" = no ]; then rm -rf -- "$state"; fi
    }
    trap cleanup EXIT
    if [ -f "$target" ]; then
        cat "$target" > "$temp"
        printf '\n' >> "$temp"
    elif [ -r /etc/inputrc ]; then
        printf '%s\n' '$include /etc/inputrc' > "$temp"
    fi
    cat >> "$temp" <<'BINDINGS'
# BEGIN ahmadnish keys history
$if Bash
"\e[A": history-search-backward
"\e[B": history-search-forward
"\eOA": history-search-backward
"\eOB": history-search-forward
$endif
# END ahmadnish keys history
BINDINGS
    cp "$temp" "$state/installed"
    if [ -f "$target" ]; then chmod --reference="$target" "$temp" 2>/dev/null || :; fi
    mv -f -- "$temp" "$target"
    committed=yes
    printf 'Installed prefix search: %s\nUndo state: %s\n' "$target" "$state"
)
_keys_history_main() {
    local state=${XDG_STATE_HOME:-"$HOME/.local/state"}/ahmadnish-keys
    if ! _keys_history_change "${1:-}"; then return 1; fi
    if [ "${1:-}" = --undo ]; then
        if [ -f "$state/reverted" ]; then
            case $- in
                *i*)
                    local sequence binding
                    for sequence in '\e[A' '\e[B' '\eOA' '\eOB'; do bind -r "$sequence"; done
                    while IFS= read -r binding; do bind "$binding"; done < "$state/bindings"
                    printf '%s\n' 'Original bindings restored in this Bash.'
                    ;;
                *) printf '%s\n' 'Open a new Bash to use the restored settings; other already-open shells keep their current bindings.' ;;
            esac
            rm -rf -- "$state"
        fi
    else
        case $- in
            *i*)
                bind '"\e[A": history-search-backward'
                bind '"\e[B": history-search-forward'
                bind '"\eOA": history-search-backward'
                bind '"\eOB": history-search-forward'
                printf '%s\n' 'Active now: type a command prefix and press Up/Down.'
                ;;
            *) printf '%s\n' 'Saved for new Bash sessions. For immediate activation: source /path/to/keys/history.sh' ;;
        esac
    fi
}
if _keys_history_main "${1:-}"; then
    unset -f _keys_history_change _keys_history_main
else
    unset -f _keys_history_change _keys_history_main
    return 1 2>/dev/null || exit 1
fi
