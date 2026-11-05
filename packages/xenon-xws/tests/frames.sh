#!/bin/bash
# Regression test for "two title bars" and janky resizing of Windows
# programs on GNOME. Runs GNOME's window manager (Mutter, X11 mode) on a
# virtual screen, opens a Windows program that draws its own title bar and
# edges (like Chromium/Electron apps, Steam, Discord), and checks with real
# mouse drags that, with XWS's frame helper running:
#   - GNOME adds no title bar of its own (one title bar),
#   - dragging the app's title bar moves the window,
#   - dragging the right edge changes only the width.
#
# Needs: wine, mingw-w64, Xvfb, mutter, xdotool, x11-utils, python3-xlib.
# Usage: tests/frames.sh [workdir]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PKG="$(dirname "$HERE")"
WORK="${1:-$(mktemp -d)}"
mkdir -p "$WORK/home"
export HOME="$WORK/home" XWS_NO_GUI=1 PYTHONPATH="$PKG"
export XWS_LIB_DIR="$WORK/nolib" XWS_SHARE_DIR="$WORK/noshare"

make -s -C "$HERE/fixtures" OUT="$WORK/fx" "$WORK/fx/customframe.exe"

DISP=":$((RANDOM % 400 + 100))"
Xvfb "$DISP" -screen 0 1100x700x24 >/dev/null 2>&1 &
XVFB=$!
PIDS=("$XVFB")
# shellcheck disable=SC2317  # called via trap
cleanup() {
    WINEPREFIX="$HOME/.local/share/xenon/windows" wineserver -k 2>/dev/null || true
    kill "${PIDS[@]}" 2>/dev/null || true
}
trap cleanup EXIT
sleep 1
export DISPLAY="$DISP"
dbus-run-session -- mutter --x11 --replace >/dev/null 2>&1 &
PIDS+=($!)
sleep 3

python3 -m xws init >/dev/null 2>&1
python3 -m xws frames --idle-exit 60 &
PIDS+=($!)
sleep 1
WINEPREFIX="$HOME/.local/share/xenon/windows" wine "$WORK/fx/customframe.exe" >/dev/null 2>&1 &
sleep 6

WID=""
best=0
for w in $(xdotool search --classname customframe.exe); do
    area=$(xwininfo -id "$w" | awk '/Width:/{w=$2} /Height:/{h=$2} END{print w*h}')
    if [ "$area" -gt "$best" ]; then best=$area; WID=$w; fi
done
[ -n "$WID" ] || { echo "FAIL: test window not found"; exit 1; }

geo() { xwininfo -id "$WID" | awk '/Absolute upper-left X/{x=$4} /Absolute upper-left Y/{y=$4} /Width:/{w=$2} /Height:/{h=$2} END{print x, y, w, h}'; }
fail() { echo "FAIL: $1"; exit 1; }

decor=$(xprop -id "$WID" _MOTIF_WM_HINTS | awk -F', ' '{print $3}')
[ "$decor" = "0x0" ] || fail "GNOME still decorates the window (decorations=$decor)"
echo "PASS one title bar (GNOME adds none)"

read -r X Y _ _ < <(geo)
xdotool mousemove $((X + 200)) $((Y + 18)) mousedown 1
sleep 0.3
for _ in 1 2 3 4 5 6; do xdotool mousemove_relative -- 25 12; sleep 0.1; done
xdotool mouseup 1
sleep 1
read -r X2 Y2 W2 H2 < <(geo)
if [ $((X2 - X)) -lt 100 ] || [ $((Y2 - Y)) -lt 40 ]; then
    fail "drag by title bar: $X,$Y -> $X2,$Y2"
fi
echo "PASS drag by the app's title bar moves the window ($X,$Y -> $X2,$Y2)"

xdotool mousemove $((X2 + W2 - 3)) $((Y2 + H2 / 2)) mousedown 1
sleep 0.3
for _ in 1 2 3 4 5 6; do xdotool mousemove_relative -- 20 0; sleep 0.1; done
xdotool mouseup 1
sleep 1
read -r X3 Y3 W3 H3 < <(geo)
[ $((W3 - W2)) -ge 80 ] || fail "resize from right edge: width $W2 -> $W3"
if [ "$X3" != "$X2" ] || [ "$Y3" != "$Y2" ] || [ "$H3" != "$H2" ]; then
    fail "resize moved or stretched the window: $X2,$Y2 ${W2}x$H2 -> $X3,$Y3 ${W3}x$H3"
fi
echo "PASS right-edge resize changes only the width (${W2}x$H2 -> ${W3}x$H3)"
echo "== window frame checks passed"
