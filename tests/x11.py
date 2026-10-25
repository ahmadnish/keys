"""Exercise real XKB mappings and modifier actions on an isolated Xvfb server."""
import ctypes as C
import ctypes.util
import importlib.util
import os
from pathlib import Path
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time

BASE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('keys_x11', BASE / 'x11.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)

class State(C.Structure):
    _fields_ = [('group', C.c_ubyte), ('locked_group', C.c_ubyte),
                ('base_group', C.c_ushort), ('latched_group', C.c_ushort)] + [
                (name, C.c_ubyte) for name in ['mods', 'base_mods', 'latched_mods',
                'locked_mods', 'compat_state', 'grab_mods', 'compat_grab_mods',
                'lookup_mods', 'compat_lookup_mods']] + [('ptr_buttons', C.c_ushort)]

def library(name):
    path = ctypes.util.find_library(name)
    if not path and sys.platform == 'darwin':
        path = '/opt/X11/lib/lib' + name + '.6.dylib'
    return C.CDLL(path)

lib = library('X11')
lib.XOpenDisplay.argtypes = [C.c_char_p]; lib.XOpenDisplay.restype = C.c_void_p
lib.XCloseDisplay.argtypes = [C.c_void_p]
lib.XSync.argtypes = [C.c_void_p, C.c_int]
lib.XkbLockGroup.argtypes = [C.c_void_p, C.c_uint, C.c_uint]
lib.XkbGetState.argtypes = [C.c_void_p, C.c_uint, C.POINTER(State)]
lib.XkbLookupKeySym.argtypes = [C.c_void_p, C.c_ubyte, C.c_uint, C.POINTER(C.c_uint), C.POINTER(C.c_ulong)]
lib.XStringToKeysym.argtypes = [C.c_char_p]; lib.XStringToKeysym.restype = C.c_ulong
xtst = library('Xtst')
xtst.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]

def call(args, env, good=True):
    r = subprocess.run([str(x) for x in args], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert (r.returncode == 0) == good, r.stdout
    return r

def dump(env):
    return call(['xkbcomp', '-w', '0', '-xkb', env['DISPLAY'], '-'], env).stdout

def canonical(text):
    # xkbcomp normalizes component labels and drops explicit default-Level1
    # entries on reload. Neither changes symbols, modifiers, or actions.
    text = re.sub(r'(xkb_(?:keycodes|types|compatibility|symbols|geometry))\s+"[^"]*"', r'\1 ""', text)
    return re.sub(r'^\s*map\[[^]]+\]\s*=\s*Level1;\s*\n', '', text, flags=re.M)

def lookup(display, code, state):
    consumed, symbol = C.c_uint(), C.c_ulong()
    assert lib.XkbLookupKeySym(display, code, state, C.byref(consumed), C.byref(symbol))
    return symbol.value, state & ~consumed.value

def start(env, mode=None):
    args = [str(BASE / 'shortcuts'), 'run'] + ([mode] if mode else [])
    proc = subprocess.Popen(args, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 15
    lines = []
    while time.monotonic() < deadline:
        if select.select([proc.stdout], [], [], 0.1)[0]:
            line = proc.stdout.readline()
            lines.append(line)
            if 'Caps navigation active in your X11 session' in line:
                return proc
        if proc.poll() is not None:
            break
    proc.kill(); rest = proc.communicate()[0]
    raise AssertionError('Could not start X11 fallback: ' + ''.join(lines) + rest)

def test_layout(env, display, layout, variant):
    call(['setxkbmap', '-layout', layout, '-variant', variant, '-option', ''], env)
    original = dump(env)
    codes = {key: int(re.search('<' + key + r'>\s*=\s*(\d+)', original).group(1))
             for key in list(backend.NAV) + ['CAPS', 'LFSH', 'RTSH']}
    groups = len(layout.split(','))
    baseline_client = lib.XOpenDisplay(env['DISPLAY'].encode())
    baseline = {(key, group, mask): lookup(baseline_client, code, mask | (group << 13))
                for key, code in codes.items() if key in backend.NAV
                for group in range(groups) for mask in range(256) if not mask & 32}
    assert lib.XkbLockGroup(baseline_client, 0x100, groups - 1)
    lib.XSync(baseline_client, 0)
    lib.XCloseDisplay(baseline_client)
    proc = start(env)  # Auto selection must not attempt sudo.
    try:
        lib.XSync(display, 0)
        # Refresh the client's cached map after changing the server mapping.
        client = lib.XOpenDisplay(env['DISPLAY'].encode())
        try:
            state = State(); lib.XkbGetState(client, 0x100, C.byref(state))
            assert state.group == groups - 1, 'Starting the fallback changed the active layout group'
            for (key, group, mask), before in baseline.items():
                after = lookup(client, codes[key], mask | (group << 13))
                assert after == before, (layout, key, group, mask, before, after)
                symbol, remaining = lookup(client, codes[key], mask | 32 | (group << 13))
                assert symbol == lib.XStringToKeysym(backend.NAV[key].encode()), (layout, key, group, mask, symbol)
                assert remaining & (1 | 4 | 8 | 64) == mask & (1 | 4 | 8 | 64), (layout, key, group, mask, remaining)
            def press(key, down):
                assert xtst.XTestFakeKeyEvent(client, codes[key], down, 0)
                lib.XSync(client, 0)
            for key in backend.NAV:
                for shift in [None, 'LFSH', 'RTSH']:
                    for reverse in ([False, True] if shift else [False]):
                        modifiers = ['CAPS'] + ([shift] if shift else [])
                        if reverse:
                            modifiers.reverse()
                        for mod in modifiers:
                            press(mod, 1)
                        state = State()
                        assert lib.XkbGetState(client, 0x100, C.byref(state)) == 0
                        assert state.mods & 32, (key, modifiers, state.mods)
                        symbol, remaining = lookup(client, codes[key], state.mods | (state.group << 13))
                        assert symbol == lib.XStringToKeysym(backend.NAV[key].encode())
                        assert bool(remaining & 1) == bool(shift), (key, modifiers, remaining)
                        for mod in reversed(modifiers):
                            press(mod, 0)
            press('LFSH', 1); press('RTSH', 1)
            state = State(); lib.XkbGetState(client, 0x100, C.byref(state))
            assert not state.locked_mods & 2, 'Both Shift keys unexpectedly enabled Caps Lock'
            press('RTSH', 0); press('LFSH', 0)
        finally:
            lib.XCloseDisplay(client)
        call([BASE / 'shortcuts', 'stop'], env)
        output = proc.communicate(timeout=10)[0]
        assert proc.returncode == 0, output
        restored = dump(env)
        if canonical(restored) != canonical(original):
            import difflib
            raise AssertionError('Original map not restored exactly:\n' + ''.join(difflib.unified_diff(original.splitlines(True), restored.splitlines(True)))[:6000])
        state = State(); lib.XkbGetState(display, 0x100, C.byref(state))
        assert state.group == groups - 1, 'Stopping the fallback changed the active layout group'
        assert backend.PREFIX not in restored, 'Temporary XKB definitions remained after undo'
        print('PASS: ' + layout + '/' + variant + ': preserved base symbols, AltGr/groups, navigation modifiers, both Shift orders, exact restoration')
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT); proc.communicate(timeout=10)
    return original

with tempfile.TemporaryDirectory(prefix='keys-x11-test-') as temp:
    root = Path(temp)
    log = (root / 'xvfb.log').open('w+')
    server = subprocess.Popen(['Xvfb', '-displayfd', '1', '-screen', '0', '800x600x24', '-nolisten', 'tcp'], stdout=subprocess.PIPE, stderr=log, text=True)
    display = None
    try:
        assert select.select([server.stdout], [], [], 10)[0], 'Xvfb did not start'
        number = server.stdout.readline().strip()
        assert number.isdigit(), 'Xvfb did not return a display number'
        env = dict(os.environ, DISPLAY=':' + number, XDG_SESSION_TYPE='x11', HOME=str(root / 'home'), XDG_STATE_HOME=str(root / 'state'))
        for key in ['WAYLAND_DISPLAY', 'SSH_CONNECTION', 'SSH_TTY', 'INPUTRC']:
            env.pop(key, None)
        Path(env['HOME']).mkdir()
        tools = root / 'tools'; tools.mkdir()
        # Simulate Linux for wrapper tests on macOS; never elevate in tests.
        uname = tools / 'uname'; uname.write_text('#!/bin/sh\ncase "$1" in -s) echo Linux ;; *) exec /usr/bin/uname "$@" ;; esac\n'); uname.chmod(0o755)
        sudo = tools / 'sudo'; sudo.write_text('#!/bin/sh\necho called > "' + str(root / 'sudo-called') + '"\nexit 99\n'); sudo.chmod(0o755)
        env['PATH'] = str(tools) + ':' + env['PATH']
        # Keep a client connected so Xvfb doesn't reset between utility calls.
        display = lib.XOpenDisplay(env['DISPLAY'].encode())
        assert display
        original = test_layout(env, display, 'us', '')
        original = test_layout(env, display, 'us,de', 'intl,')
        # SIGINT cleanup and SIGKILL recovery must also restore the full map.
        for sig in [signal.SIGINT, signal.SIGKILL]:
            proc = start(env, '--no-sudo')
            proc.send_signal(sig); proc.communicate(timeout=10)
            if sig == signal.SIGKILL:
                call([BASE / 'shortcuts', 'stop', '--no-sudo'], env)
            assert canonical(dump(env)) == canonical(original)
        print('PASS: explicit --no-sudo, signal cleanup and stale-session recovery')
        # The combined public revert helper must work without sudo as well.
        call(['bash', BASE / 'history.sh'], env)
        proc = start(env, '--no-sudo')
        call(['bash', '--noprofile', '--norc', '-ic', 'source "' + str(BASE / 'revert.sh') + '"'], env)
        proc.communicate(timeout=10)
        assert proc.returncode == 0 and not (Path(env['HOME']) / '.inputrc').exists()
        assert canonical(dump(env)) == canonical(original)
        print('PASS: one-command revert restores both the X11 map and Bash history without sudo')
        # Do not overwrite a layout edit made after setup.
        proc = start(env, '--no-sudo')
        current = dump(env)
        a, ka, kb = backend.block(current, r'\bkey\s*<AD01>')
        body = re.sub(r'\bq\b', 'a', current[ka:kb], count=1)
        assert body != current[ka:kb]
        changed_file = root / 'user-edited.xkb'
        changed_file.write_text(current[:ka] + body + current[kb:])
        call(['xkbcomp', '-w', '0', changed_file, env['DISPLAY']], env)
        edited = dump(env)
        proc.send_signal(signal.SIGINT)
        output = proc.communicate(timeout=10)[0]
        assert proc.returncode != 0 and 'not overwriting later changes' in output
        assert canonical(dump(env)) == canonical(edited)
        saved = next((Path(env['XDG_STATE_HOME']) / 'ahmadnish-keys-x11').glob('*/original.xkb')).parent
        assert (saved / 'original.xkb').exists()
        # Explicit recovery of this isolated test display using its backup.
        call(['xkbcomp', '-w', '0', saved / 'bridge.xkb', env['DISPLAY']], env)
        call(['xkbcomp', '-w', '0', saved / 'original.xkb', env['DISPLAY']], env)
        shutil.rmtree(saved)
        assert canonical(dump(env)) == canonical(original)
        print('PASS: later layout edits are preserved and the original backup is retained')
        bad = dict(env, XDG_SESSION_TYPE='wayland', WAYLAND_DISPLAY='wayland-0')
        r = call([BASE / 'shortcuts', 'run', '--no-sudo'], bad, False)
        assert 'Wayland' in r.stdout and canonical(dump(env)) == canonical(original)
        bad = dict(env); bad.pop('DISPLAY')
        r = call([BASE / 'shortcuts', 'run', '--no-sudo'], bad, False)
        assert 'DISPLAY' in r.stdout
        bad = dict(env, SSH_CONNECTION='test')
        r = call([BASE / 'shortcuts', 'run', '--no-sudo'], bad, False)
        assert 'SSH' in r.stdout and canonical(dump(env)) == canonical(original)
        # A real occupied Mod3 must be rejected before installing a map.
        occupied = re.sub(r'modifier_map Mod3\s*\{[^}]+\}', 'modifier_map Mod3 { <LVL5>, <RALT> }', original)
        assert occupied != original
        try:
            backend.build_map(occupied)
            raise AssertionError('Occupied Mod3 was accepted')
        except backend.Error as error:
            assert 'Mod3' in str(error)
        assert not (root / 'sudo-called').exists(), 'Fallback attempted sudo'
        print('PASS: Wayland/SSH/missing DISPLAY/occupied modifier guards; sudo was never called')
    finally:
        if display:
            lib.XCloseDisplay(display)
        server.terminate(); server.wait(timeout=10)
        log.close()
