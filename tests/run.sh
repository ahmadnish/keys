#!/bin/sh
set -eu
BASE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BUILD=$(mktemp -d)
trap 'rm -rf -- "$BUILD"' EXIT
sh -n "$BASE/shortcuts" "$BASE/get"
bash -n "$BASE/history.sh" "$BASE/revert.sh"
tar -xzf "$BASE/vendor/keyd-v2.6.0.tar.gz" -C "$BUILD"
cd "$BUILD/keyd-2.6.0"
# Native Linux compilation of upstream's standalone remapping engine harness.
cc '-DDATA_DIR=""' -o "$BUILD/test-io" t/test-io.c src/keyboard.c src/string.c src/macro.c src/config.c src/log.c src/ini.c src/keys.c src/unicode.c
"$BUILD/test-io" "$BASE/caps.conf" "$BASE"/tests/*.t
python3 "$BASE/tests/history.py"

python3 "$BASE/tests/x11.py"
