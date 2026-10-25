# Optional: source this file from an interactive zsh (emacs or vi insert mode).
# Select command-line text using Shift+arrows/Home/End. Ctrl+W cuts the region.
# Key sequences are the common xterm forms; terminals must forward them.
_keys_select() {
    (( REGION_ACTIVE )) || MARK=$CURSOR
    case $WIDGET in
        keys-select-left) zle .backward-char ;;
        keys-select-right) zle .forward-char ;;
        keys-select-up) zle .up-line ;;
        keys-select-down) zle .down-line ;;
        keys-select-home) zle .beginning-of-line ;;
        keys-select-end) zle .end-of-line ;;
    esac
    REGION_ACTIVE=1
}
_keys_cut_selection() {
    if (( REGION_ACTIVE )); then zle .kill-region; else zle .backward-kill-word; fi
}
zle -N keys-cut-selection _keys_cut_selection
for direction in left right up down home end; do
    zle -N keys-select-$direction _keys_select
done
for keymap in emacs viins; do
    bindkey -M $keymap '^[[1;2D' keys-select-left
    bindkey -M $keymap '^[[1;2C' keys-select-right
    bindkey -M $keymap '^[[1;2A' keys-select-up
    bindkey -M $keymap '^[[1;2B' keys-select-down
    bindkey -M $keymap '^[[1;2H' keys-select-home
    bindkey -M $keymap '^[[1;2F' keys-select-end
    bindkey -M $keymap '^[[1;2~' keys-select-home
    bindkey -M $keymap '^[[4;2~' keys-select-end
    bindkey -M $keymap '^W' keys-cut-selection
done
unset direction keymap
