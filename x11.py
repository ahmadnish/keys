#!/usr/bin/env python3
"""Temporary XKB navigation for a user's X11 display; no privileged devices."""
import ctypes
import ctypes.util
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

NAV = {'AD08': 'Up', 'AC07': 'Left', 'AC08': 'Down', 'AC09': 'Right',
       'AC06': 'Home', 'AC11': 'End', 'AB06': 'BackSpace'}
PREFIX = 'AHMAD_KEYS_'

class Error(Exception):
    pass

def block(text, pattern):
    match = re.search(pattern + r'\s*\{', text)
    if not match:
        raise Error('Unsupported XKB map: missing ' + pattern)
    start = match.end()
    depth, quoted, escaped = 1, False, False
    for i in range(start, len(text)):
        c = text[i]
        if escaped:
            escaped = False
        elif quoted and c == '\\':
            escaped = True
        elif c == '"':
            quoted = not quoted
        elif not quoted:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return match.start(), start, i
    raise Error('Unbalanced XKB map')

def modifiers(value):
    return frozenset(x.strip() for x in value.split('+') if x.strip().lower() != 'none' and x.strip())

def expression(items):
    return '+'.join(sorted(items)) or 'None'

def build_map(original):
    """Keep existing groups/types, adding one navigation level per target group."""
    if PREFIX in original:
        raise Error('A keys X11 map is already loaded. Use ./shortcuts stop to restore it first.')
    _, types_start, types_end = block(original, r'xkb_types(?:\s+"[^"]*")?')
    _, symbols_start, symbols_end = block(original, r'xkb_symbols(?:\s+"[^"]*")?')
    types_text = original[types_start:types_end]
    symbols_text = original[symbols_start:symbols_end]
    # Mod3 is conventionally reserved for LevelFive. The synthetic <LVL5> key
    # alone is harmless, but never take it away from a real modifier key or an
    # actively used LevelFive type.
    for match in re.finditer(r'modifier_map\s+Mod3\s*\{([^}]+)\}', symbols_text):
        if set(re.findall(r'<([^>]+)>', match.group(1))) - {'LVL5'}:
            raise Error('Mod3 is already used by this keyboard. Use --system if administrator access is available.')
    for name in set(re.findall(r'\btype(?:\[[Gg]roup\d+\])?\s*=\s*"([^"]+)"', symbols_text)):
        _, a, b = block(types_text, r'\btype\s+"' + re.escape(name) + '"')
        used = re.search(r'\bmodifiers\s*=\s*([^;]+)', types_text[a:b])
        if used and modifiers(used.group(1)) & {'Mod3', 'LevelFive'}:
            raise Error('This layout already uses Mod3/LevelFive. No keyboard changes made; use --system instead.')
    used_types = set(re.findall(r'\btype(?:\[[Gg]roup\d+\])?\s*=\s*"([^"]+)"', symbols_text)) | {'ONE_LEVEL', 'TWO_LEVEL', 'ALPHABETIC', 'KEYPAD', 'FOUR_LEVEL', 'FOUR_LEVEL_ALPHABETIC', 'FOUR_LEVEL_SEMIALPHABETIC', 'FOUR_LEVEL_KEYPAD', 'EIGHT_LEVEL', 'EIGHT_LEVEL_ALPHABETIC', 'EIGHT_LEVEL_SEMIALPHABETIC'}
    spare_types = [name for name in re.findall(r'\btype\s+"([^"]+)"', types_text) if name not in used_types]
    allocated = {}
    additions, replacements = [], []
    for key, destination in NAV.items():
        start, a, b = block(symbols_text, r'\bkey\s*<' + key + '>')
        body = symbols_text[a:b]
        if re.search(r'\b(actions|overlay\d|behavior)\b', body):
            raise Error('Target key <' + key + '> has custom actions; refusing to overwrite them.')
        groups = re.findall(r'\bsymbols\s*\[[Gg]roup(\d+)\]\s*=\s*\[([^]]*)\]', body)
        if not groups:
            bare = re.fullmatch(r'\s*\[([^]]*)\]\s*', body)
            if not bare:
                raise Error('Unsupported symbol definition for <' + key + '>')
            groups = [('1', bare.group(1))]
        global_type = re.search(r'\btype\s*=\s*"([^"]+)"', body)
        attributes = []
        for group, values in groups:
            syms = [x.strip() for x in values.split(',') if x.strip()]
            specific = re.search(r'\btype\s*\[[Gg]roup' + group + r'\]\s*=\s*"([^"]+)"', body)
            if not specific and not global_type and len(syms) > 2:
                raise Error('A multi-level key has no explicit type; refusing to guess its behavior.')
            kind = specific.group(1) if specific else global_type.group(1) if global_type else ('ONE_LEVEL' if len(syms) == 1 else 'TWO_LEVEL')
            _, ta, tb = block(types_text, r'\btype\s+"' + re.escape(kind) + '"')
            old = types_text[ta:tb]
            m = re.search(r'\bmodifiers\s*=\s*([^;]+)', old)
            old_mods = modifiers(m.group(1)) if m else frozenset()
            if old_mods & {'Mod3', 'LevelFive'}:
                raise Error('Target key type already uses the navigation modifier.')
            base_mods = old_mods | {'Shift'}
            if len(base_mods) > 5:
                raise Error('Target key type uses too many modifiers for a safe temporary map.')
            maps = {modifiers(k): int(v) for k, v in re.findall(r'\bmap\[([^]]+)\]\s*=\s*Level(\d+)', old)}
            keeps = {modifiers(k): modifiers(v) for k, v in re.findall(r'\bpreserve\[([^]]+)\]\s*=\s*([^;]+)', old)}
            width = max([len(syms), 1] + [int(v) for v in re.findall(r'Level(\d+)', old)])
            signature = (kind, width)
            if signature not in allocated:
                if not spare_types:
                    raise Error('No unused XKB type slots are available. No settings changed; use --system instead.')
                allocated[signature] = spare_types.pop(0)
            name = allocated[signature]
            lines = ['type "' + name + '" {', 'modifiers = ' + expression(base_mods | {'Mod3'}) + ';']
            mods = sorted(base_mods)
            for bits in itertools.product((False, True), repeat=len(mods)):
                selected = frozenset(m for m, bit in zip(mods, bits) if bit)
                query = selected & old_mods
                keep = keeps.get(query, frozenset()) | (selected - old_mods)
                lines += ['map[' + expression(selected) + '] = Level' + str(maps.get(query, 1)) + ';',
                          'preserve[' + expression(selected) + '] = ' + expression(keep) + ';',
                          'map[' + expression(selected | {'Mod3'}) + '] = Level' + str(width + 1) + ';',
                          'preserve[' + expression(selected | {'Mod3'}) + '] = ' + expression(selected) + ';']
            lines += ['level_name[Level' + str(i) + '] = \"Level' + str(i) + '\";' for i in range(1, width + 2)]
            lines += ['};']
            if not any(item[0] == name for item in additions):
                additions.append((name, '\n'.join(lines)))
            syms += ['NoSymbol'] * (width - len(syms)) + [destination]
            attributes += ['type[Group' + group + '] = "' + name + '"',
                           'symbols[Group' + group + '] = [ ' + ', '.join(syms) + ' ]']
        # Retain the original non-symbol attributes where possible.
        rest = re.sub(r'\bsymbols\s*\[[Gg]roup\d+\]\s*=\s*\[[^]]*\]', '', body)
        rest = re.sub(r'\btype(?:\[[Gg]roup\d+\])?\s*=\s*"[^"]+"', '', rest)
        if not re.search(r'\bsymbols\s*\[', body):
            rest = ''
        rest = rest.strip().strip(',').strip()
        attributes += [part.strip() for part in rest.split(',') if part.strip()]
        replacements.append((start, b + 1, 'key <' + key + '> {\n' + ',\n'.join(attributes) + '\n}'))
    # A standard modifier keysym keeps toolkits from treating Caps as text.
    # Explicit SetMods makes it momentary, overriding the old locking action.
    start, _, b = block(symbols_text, r'\bkey\s*<CAPS>')
    replacements.append((start, b + 1, 'key <CAPS> { type="ONE_LEVEL", symbols[Group1]=[ ISO_Level5_Shift ], actions[Group1]=[ SetMods(modifiers=Mod3) ] }'))
    for a, b, replacement in sorted(replacements, reverse=True):
        symbols_text = symbols_text[:a] + replacement + symbols_text[b:]
    # Remove CAPS from its original real-modifier map before assigning Mod3.
    def unmap(match):
        body = re.sub(r'<CAPS>\s*,?\s*|,\s*<CAPS>', '', match.group(2)).strip().strip(',')
        return 'modifier_map ' + match.group(1) + ' { ' + body + ' };' if body else ''
    symbols_text = re.sub(r'modifier_map\s+(\w+)\s*\{([^}]+)\}\s*;', unmap, symbols_text)
    symbols_text += '\nmodifier_map Mod3 { <CAPS> };\n'
    type_replacements = []
    for name, declaration in additions:
        a, _, b = block(types_text, r'\btype\s+"' + re.escape(name) + '"')
        type_replacements.append((a, b + 1, declaration[:-1]))
    for a, b, declaration in sorted(type_replacements, reverse=True):
        types_text = types_text[:a] + declaration + types_text[b:]
    # Only borrow unused existing slots, preserving the server's type count.
    result = original[:symbols_start] + symbols_text + original[symbols_end:]
    result = result[:types_start] + types_text + result[types_end:]
    return re.sub(r'xkb_symbols\s+"[^"]*"', 'xkb_symbols "AHMAD_KEYS_NAV"', result, count=1)

def xkb(*args):
    try:
        result = subprocess.run(['xkbcomp', '-w', '0'] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        raise Error('Need xkbcomp (usually x11-xkb-utils / xorg-xkbcomp / xorg-x11-xkb-utils). No packages were installed.')
    if result.returncode:
        raise Error('xkbcomp failed: ' + result.stderr.strip())
    return result.stdout

def state_path():
    display = os.environ.get('DISPLAY', '')
    if not display:
        return None
    # :0 and :0.0 identify the same server; other screens share its keyboard.
    server = re.sub(r'\.\d+$', '', display)
    root = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state')))
    return root / 'ahmadnish-keys-x11' / hashlib.sha256(server.encode()).hexdigest()[:20]

def check_session():
    if os.getuid() == 0:
        raise Error('Run the X11 fallback as your normal desktop user, without sudo.')
    if os.environ.get('XDG_SESSION_TYPE', '').lower() == 'wayland' or os.environ.get('WAYLAND_DISPLAY'):
        raise Error('No sudo-free keyboard fallback on this Wayland desktop. Bash history still works: source ~/keys/history.sh')
    if os.environ.get('SSH_CONNECTION') or os.environ.get('SSH_TTY'):
        raise Error('Start the X11 fallback locally in your desktop session, not over SSH.')
    if not os.environ.get('DISPLAY'):
        raise Error('No X11 DISPLAY found. Bash history still works without sudo.')
    library = ctypes.util.find_library('X11')
    if not library and sys.platform == 'darwin':
        library = '/opt/X11/lib/libX11.6.dylib'
    if not library:
        raise Error('libX11 is unavailable in this session.')
    lib = ctypes.CDLL(library)
    lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    lib.XOpenDisplay.restype = ctypes.c_void_p
    lib.XQueryExtension.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    dpy = lib.XOpenDisplay(None)
    if not dpy:
        raise Error('Cannot open your X11 display; no keyboard settings changed.')
    try:
        a, b, c = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
        if lib.XQueryExtension(dpy, b'XWAYLAND', ctypes.byref(a), ctypes.byref(b), ctypes.byref(c)):
            raise Error('DISPLAY belongs to Xwayland. A session-wide sudo-free mapping is unavailable; Bash history still works.')
    except BaseException:
        lib.XCloseDisplay(dpy)
        raise
    return lib, dpy

def process_start(pid):
    try:
        stat = Path('/proc/' + str(pid) + '/stat')
        if stat.exists():
            return stat.read_text().rsplit(')', 1)[1].split()[19]
        # Supports isolated Xvfb testing on macOS; Linux uses /proc above.
        return subprocess.check_output(['ps', '-p', str(pid), '-o', 'lstart='], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return ''

def restore(state):
    meta = json.loads((state / 'session.json').read_text())
    if (state / 'applied.xkb').exists():
        current = xkb('-xkb', meta['display'], '-')
        if current != (state / 'applied.xkb').read_text():
            raise Error('The X11 map changed after setup; not overwriting later changes. Original map saved at ' + str(state / 'original.xkb'))
    # Reset key references before restoring borrowed type slots, avoiding
    # incompatible level widths while the server processes the map update.
    if (state / 'bridge.xkb').exists():
        xkb(str(state / 'bridge.xkb'), meta['display'])
    xkb(str(state / 'original.xkb'), meta['display'])
    shutil.rmtree(str(state))
    try:
        state.parent.rmdir()
    except OSError:
        pass
    print('Original X11 keyboard map restored; no sudo used.', flush=True)

def stop():
    state = state_path()
    if state is None or not state.exists():
        return 3  # Caller may have an unrelated keyd session to stop instead.
    record = state / 'session.json'
    if not record.exists():
        raise Error('An incomplete X11 session record exists at ' + str(state))
    meta = json.loads(record.read_text())
    start = process_start(meta['pid'])
    if start and start == meta['start']:
        os.kill(meta['pid'], signal.SIGTERM)
        for _ in range(100):
            if not state.exists():
                print('X11 keyboard session stopped.', flush=True)
                return 0
            time.sleep(0.05)
        raise Error('The session did not finish restoring. Check its original terminal and backup: ' + str(state))
    # SIGKILL cannot run a handler. Restore its saved map if it still matches.
    restore(state)
    return 0

def run():
    lib, display_connection = check_session()
    if Path('/run/linux-shortcuts-session').exists():
        raise Error('A keyd session is already active. Stop it before starting the X11 fallback.')
    state = state_path()
    state.parent.mkdir(parents=True, exist_ok=True)
    try:
        state.mkdir(mode=0o700)
    except FileExistsError:
        raise Error('An X11 session or backup already exists. Run ./shortcuts stop first: ' + str(state))
    changed = False
    finished = False
    def finish(signum=None, frame=None):
        nonlocal finished
        if finished:
            return
        finished = True
        # Avoid reentrant cleanup if a terminal sends both HUP and TERM.
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
        if changed:
            restore(state)
        elif state.exists():
            shutil.rmtree(str(state))
    try:
        original = xkb('-xkb', os.environ['DISPLAY'], '-')
        (state / 'original.xkb').write_text(original)
        patched = build_map(original)
        (state / 'navigation.xkb').write_text(patched)
        _, oa, ob = block(original, r'xkb_types(?:\s+"[^"]*")?')
        _, pa, pb = block(patched, r'xkb_types(?:\s+"[^"]*")?')
        (state / 'bridge.xkb').write_text(original[:oa] + patched[pa:pb] + original[ob:])
        meta = {'pid': os.getpid(), 'start': process_start(os.getpid()), 'display': os.environ['DISPLAY']}
        (state / 'session.json').write_text(json.dumps(meta))
        xkb(str(state / 'navigation.xkb'), str(state / 'navigation.xkm'))
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, lambda signum, frame: (_ for _ in ()).throw(KeyboardInterrupt()))
        # Set before loading so an interrupted/partial apply still restores.
        changed = True
        xkb(str(state / 'navigation.xkb'), os.environ['DISPLAY'])
        (state / 'applied.xkb').write_text(xkb('-xkb', os.environ['DISPLAY'], '-'))
        print('Caps navigation active in your X11 session; no sudo used.\nStop with Ctrl+C here, ./shortcuts stop, or source ~/keys/revert.sh.', flush=True)
        while True:
            signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            finish()
        finally:
            lib.XCloseDisplay(display_connection)
    return 0

def main():
    try:
        action = sys.argv[1] if len(sys.argv) > 1 else 'run'
        if action == 'run':
            return run()
        if action == 'stop':
            return stop()
        raise Error('Usage: x11.py run|stop')
    except (Error, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
