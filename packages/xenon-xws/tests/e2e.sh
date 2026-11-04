#!/bin/bash
# shellcheck disable=SC2015,SC2153  # "cond && pass || fail": pass() always succeeds
# End-to-end test of the Xenon Windows Subsystem against a real Wine.
#
# Builds a small Windows installer with mingw, then checks the full user
# journey: first-run setup -> install -> app grid entry -> launch from the
# entry -> listed in installed apps -> uninstall -> entry removed.
#
# Needs: wine (64-bit, with 32-bit support), mingw-w64, xvfb-run, python3.
# Usage: tests/e2e.sh [workdir]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PKG="$(dirname "$HERE")"
WORK="${1:-$(mktemp -d)}"
mkdir -p "$WORK"

export HOME="$WORK/home"
export XWS_LIB_DIR="$WORK/lib"
export XWS_SHARE_DIR="$PKG/../../compat-none"
export XWS_NO_GUI=1
export PYTHONPATH="$PKG"
mkdir -p "$HOME" "$XWS_LIB_DIR"

pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; exit 1; }
xws() { xvfb-run -a python3 -m xws "$@"; }

echo "== building fixtures"
make -s -C "$HERE/fixtures" OUT="$WORK/fx"

# Stand-in DXVK payload so deployment can be verified without a GPU.
mkdir -p "$XWS_LIB_DIR/dxvk/x64" "$XWS_LIB_DIR/dxvk/x32"
echo "test" > "$XWS_LIB_DIR/dxvk/VERSION"
cp "$WORK/fx/game64.exe" "$XWS_LIB_DIR/dxvk/x64/d3d11.dll"
cp "$WORK/fx/hello32.exe" "$XWS_LIB_DIR/dxvk/x32/d3d11.dll"

PFX="$HOME/.local/share/xenon/windows"
APPS="$HOME/.local/share/applications"

echo "== first-run setup"
xws init >/dev/null
[ -f "$PFX/system.reg" ] && pass "environment created" || fail "environment created"
[ "$(readlink "$PFX/dosdevices/c:")" = "../drive_c" ] && pass "C: mapped" || fail "C: mapped"
cmp -s "$PFX/drive_c/windows/system32/d3d11.dll" "$XWS_LIB_DIR/dxvk/x64/d3d11.dll" \
    && pass "DXVK deployed (64-bit)" || fail "DXVK deployed (64-bit)"
cmp -s "$PFX/drive_c/windows/syswow64/d3d11.dll" "$XWS_LIB_DIR/dxvk/x32/d3d11.dll" \
    && pass "DXVK deployed (32-bit)" || fail "DXVK deployed (32-bit)"
grep -q '"d3d11"="native,builtin"' "$PFX/user.reg" && pass "DLL overrides set" \
    || fail "DLL overrides set"

echo "== 32-bit program"
out="$(xws run "$WORK/fx/hello32.exe" 2>&1 || true)"
grep -q "hello from 32-bit" "$HOME/.local/state/xenon/logs/hello32.exe.log" \
    && pass "32-bit console program ran" || { echo "$out"; fail "32-bit program"; }

echo "== install"
cp "$WORK/fx/xenon-test-setup.exe" "$HOME/xenon-test-setup.exe"
xws run "$HOME/xenon-test-setup.exe"
[ -f "$PFX/drive_c/Program Files/XenonTest/XenonTestApp.exe" ] && pass "installer ran" \
    || fail "installer ran"
entry="$(grep -l '^Name=Xenon Test App$' "$APPS"/xenon-windows/*.desktop 2>/dev/null || true)"
[ -n "$entry" ] && pass "app grid entry created" || fail "app grid entry created"
grep -q '^Exec=xws exec ' "$entry" && pass "entry launches through xws" || fail "entry Exec"
if grep -l '^Name=Uninstall' "$APPS"/xenon-windows/*.desktop >/dev/null 2>&1; then
    fail "uninstaller shortcut hidden"
else
    pass "uninstaller shortcut hidden"
fi
grep -q '^NoDisplay=true' "$APPS/wine/Programs/Xenon Test/Xenon Test App.desktop" \
    && pass "raw Wine entry hidden" || fail "raw Wine entry hidden"
if command -v desktop-file-validate >/dev/null; then
    desktop-file-validate "$entry" | grep -v '^.*hint:' && fail "entry is valid" || pass "entry is valid"
fi
[ -n "$(python3 -m xws snapshot list)" ] && pass "registry snapshot taken" || fail "snapshot"

echo "== launch from the app grid"
rm -f "$PFX/drive_c/xenon-test-marker.txt"
exec_line="$(sed -n 's/^Exec=//p' "$entry")"
python3 - "$exec_line" <<'EOF'
import shlex, subprocess, sys
argv = shlex.split(sys.argv[1].replace("\\\\", "\\"))
assert argv[0] == "xws", argv
rc = subprocess.run(["xvfb-run", "-a", "python3", "-m", "xws", *argv[1:]]).returncode
sys.exit(rc)
EOF
[ -f "$PFX/drive_c/xenon-test-marker.txt" ] && pass "app ran from its entry (exit 0)" \
    || fail "app ran from its entry"

echo "== installed apps"
python3 -m xws apps --json > "$WORK/apps.json"
python3 - "$WORK/apps.json" <<'EOF'
import json, sys
apps = json.load(open(sys.argv[1]))
assert [a["name"] for a in apps] == ["Xenon Test App"], apps
a = apps[0]
assert a["publisher"] == "Xenon Project" and a["version"] == "1.0.0", a
assert a["icon"].endswith("XenonTestApp.exe"), a
EOF
pass "listed with publisher, version and icon"

echo "== uninstall"
xws uninstall "main:XenonTestApp"
[ "$(python3 -m xws apps --json)" = "[]" ] && pass "removed from installed apps" \
    || fail "removed from installed apps"
if ls "$APPS"/xenon-windows/*.desktop >/dev/null 2>&1; then
    fail "app grid entry removed"
else
    pass "app grid entry removed"
fi

echo "== all end-to-end checks passed"
