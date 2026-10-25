# keys

Portable Caps Lock navigation and Bash history prefix search for Ahmad.

## Quick use on Linux

Remember **ahmadnish / keys / get**:

```sh
curl -fsSL https://ahmadnish.github.io/keys/get | sh
cd ~/keys
source history.sh
./shortcuts run
```

The downloader saves a kit and configures
history for future Bash sessions. `source history.sh` activates it in your current
Bash. Start keyboard remapping separately; it asks for sudo and runs until Ctrl+C.
Leave that terminal open and use any other terminals/apps normally.
The downloader refuses to overwrite an existing `~/keys`; run that copy directly.

## Your bindings

Hold Caps Lock with:

| Key | Result |
| --- | --- |
| I | Up |
| J | Left |
| K | Down |
| L | Right |
| H | Home (start of line in typical editors) |
| ' (apostrophe, two positions right of L on US keyboards) | End |
| N | Backspace |

Shift remains Shift, including for Home/End selection. Ctrl remains Ctrl, so
Ctrl+Caps+J/L usually moves by words. Both Shift keys retain their normal Shift behavior. There is no Shift chord
for toggling Caps Lock. Caps Lock alone has no typing/toggle action. Physical key positions are
used; the printed labels differ on some keyboard layouts.

Source: the selected `workRemote` profile in `~/.config/karabiner/karabiner.json`,
inspected 2026-10-25. macOS uses right Option as the intermediate modifier and
Command+Left/Right for line boundaries; Linux uses actual Home/End. This kit
ports navigation and N. The Mac profile's both-Shift Caps toggle is deliberately excluded. Other macOS application,
window, desktop and tab shortcuts are outside this kit. BetterTouchTool wasn't
needed; its data is under `~/Library/Application Support/BetterTouchTool`.

## History search and undo

In Bash:

```bash
source ~/keys/history.sh
```

Type `ssh ` (or any prefix), then Up/Down to cycle through matching commands.
This searches your shell history by prefix, not the filesystem. Ctrl+R remains
available for interactive history search. The main Readline settings are:

```inputrc
"\e[A": history-search-backward
"\e[B": history-search-forward
```

Application-mode Up/Down sequences are included too. Configuration is scoped to
Bash in your own `.inputrc` (or a user-owned `$INPUTRC`). If creating that file,
the helper includes `/etc/inputrc` to retain distribution defaults. It reports
the distribution from `/etc/os-release`, the login shell, and Bash startup files.
It does not edit `.bashrc`, login profiles, the login shell, or other users' files.
It snapshots the original file and four effective bindings under
`${XDG_STATE_HOME:-~/.local/state}/ahmadnish-keys`. Repeating setup makes no changes.

To stop keyboard remapping **and** revert history, in Bash:

```bash
source ~/keys/revert.sh
```

For history only, use `source ~/keys/history.sh --undo`.

This restores the original file (or removes it if it didn't exist), removes saved
state, and restores the four bindings in the current Bash. New terminals use the
restored settings too. For other already-open Bash sessions, open a new shell to
reload the restored settings. `./shortcuts undo` stops keyboard remapping and restores the file but cannot
change the bindings inside its parent shell. If the file changed after setup,
undo refuses to overwrite those edits and prints the original backup location.
This prevents accidental loss of later customizations.

## Keyboard scope and stopping

`keyd` uses Linux evdev/uinput, so navigation works with X11, Wayland and virtual
consoles. While active, it affects the machine's keyboards for all users; you
approved this temporary scope. It needs sudo/root on the host with the physical
keyboard. No reboot or login restart is needed. It does not install a service,
change existing keyd configs, or enable anything at boot.

Stop with **Ctrl+C in its original terminal**, or `./shortcuts stop` from another terminal. It stops its child daemon, removes
its own temporary `/etc/keyd/linux-shortcuts-session.conf`, and removes its private
`/run/linux-shortcuts-session` directory. Emergency keyd stop: hold **Backspace +
Escape + Enter** together. The runner then cleans up. Existing keyd daemons or
configuration cause a refusal; merge `caps.conf` manually in that situation.
Do not run another keyd service concurrently with the temporary session.

SIGKILL and power failure cannot run cleanup handlers. After confirming no keyd
process remains (`pgrep -x keyd`), remove **only** the kit's stale paths if present:

```sh
sudo rm -f /etc/keyd/linux-shortcuts-session.conf
sudo rm -rf /run/linux-shortcuts-session
```

Reboot clears `/run` but can leave the `/etc` file after a power failure.
A uinput module loaded on demand remains loaded; unloading a shared kernel
module is deliberately left to the administrator. Packages you explicitly
install are not automatically uninstalled. After undo and stopping navigation,
you can delete the downloaded kit directory to remove the remaining files.

Over SSH from your Mac, keep Karabiner on the Mac: remapping on the remote Linux
host cannot intercept your Mac's physical Caps Lock. Bash history and tmux work
on the SSH host. A machine without Bash needs Bash installed for the history
helper; navigation itself uses only POSIX sh and keyd.

## Offline / USB

Copy this entire directory to a USB stick. The pinned keyd **2.6.0 source is
already bundled** and checksum-verified; it requires no download to build.

The published Pages `keys.tar.gz` contains static Linux binaries for x86_64
and aarch64. Copy that extracted
kit to USB before going offline. A source-only Git checkout does not include binaries; use the published
archive or build them on Linux.

With a matching binary in `bin/`, no compiler or keyd package is needed:

```sh
cd /path/to/keys
source history.sh
./shortcuts run
```

The runner requires normal Linux host utilities (`sudo`, `pgrep`, and `modprobe`
if uinput is not loaded). A USB mounted `noexec` must be copied into your home
first. Root access and evdev/uinput availability are still required. Unusual CPU
architectures, containers, restrictive hosts, and non-Linux kernels are not
universally supported.

Without a bundled binary, use an installed **keyd 2.6+**, or build on Linux:

```sh
./shortcuts prepare
./shortcuts run
```

Build prerequisites, if missing (install while online):

- Debian/Ubuntu: `sudo apt install build-essential`
- Fedora: `sudo dnf install gcc make kernel-headers`
- Alpine: `sudo apk add build-base linux-headers bash procps`
- Arch: `sudo pacman -S --needed base-devel`

No package manager runs automatically. The source build installs nothing
system-wide. A normal dynamic binary may depend on that distribution's libc.
For a USB binary portable across distributions with the same architecture,
build statically, for example on Debian/Ubuntu:

```sh
sudo apt install musl-tools make linux-libc-dev
CFLAGS="-idirafter /usr/include -idirafter /usr/include/$(gcc -dumpmachine)" \
  CC=musl-gcc ./shortcuts prepare --static
```

Keep `bin/keyd-x86_64` and/or `bin/keyd-aarch64` in the USB kit. The GitHub workflow
performs these builds on native runners and includes both in the download.
Static linking avoids a libc dependency; it doesn't remove kernel/CPU constraints.

## Terminal selection

Navigation works; selection is controlled by the terminal application/shell.
Bash does not provide desktop-style Shift+arrow selection universally.

For terminal **output/scrollback**, install tmux if needed and run an isolated
server so your own tmux configuration remains untouched:

```sh
tmux -L keys -f ~/keys/tmux.conf new
```

Shift+arrows/Home/End (including the Caps equivalents) enter copy mode and select
output. Further movement extends the region until Enter copies to tmux's buffer
or Escape cancels. Ctrl+B then `]` pastes the buffer. This does not automatically
copy into the desktop clipboard. Detach with Ctrl+B then D; reattach using
`tmux -L keys attach`. Exit its shells when done; to discard only that server
and all its running sessions, use `tmux -L keys kill-server` after saving work.
These shortcuts select terminal output, rather than edit/select the Bash prompt.
The terminal must forward Shift+navigation sequences instead of consuming them.

For **zsh prompt text**, an optional current-session helper is available:

```zsh
source ~/keys/zsh-selection.zsh
```

Shift+arrows/Home/End select, and Ctrl+W cuts the selected region. This helper
changes current zsh bindings only; start a fresh zsh to revert. It is not sourced
or installed automatically. Terminal escape sequences vary; Linux live testing
of these terminal integrations is still needed.

## Publishing the memorable URL

Upload these files to a repository named **`keys`** under **`ahmadnish`**, with
`main` as its default branch. Include the hidden `.github` directory.
Under Settings → Pages, select **GitHub Actions** as the build source. Run the
included `Publish keys` workflow (or push to main). It builds/tests Linux binaries,
packages the kit, and publishes the downloader and USB archive at:

- `https://ahmadnish.github.io/keys/get`
- `https://ahmadnish.github.io/keys/keys.tar.gz`

For a free personal GitHub account, this repository should be public for Pages.
No private Mac settings or full Karabiner/BTT export are included. The downloader
checks the archive checksum from the same HTTPS site; that detects corruption,
not compromise of the hosting account.

## Validation and primary references

36 navigation/Shift event cases passed (including both Shift keys with no Caps toggle) against the unmodified keyd 2.6.0 engine
on macOS, with an empty Linux input header shim for the platform-independent
engine test only. This did not exercise Linux hardware devices. Bash tests cover
idempotency, original file absence, exact byte restoration, symlink preservation,
protection of later edits, and immediate activation/undo. GitHub Actions repeats
the tests natively on Linux before publishing. Native Linux builds and tests run in GitHub Actions. Live Linux hardware
keyboard/tmux behavior still needs testing on the target desktop.

- [keyd source and documentation](https://github.com/rvaiya/keyd)
- [GNU Readline configuration](https://www.gnu.org/software/bash/manual/html_node/Readline-Init-File-Syntax.html)
- [tmux manual](https://github.com/tmux/tmux/blob/master/tmux.1)
- [zsh line editor](https://zsh.sourceforge.io/Doc/Release/Zsh-Line-Editor.html)
- [GitHub Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
