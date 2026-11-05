"""One title bar per window on GNOME.

Many Windows programs draw their own title bar (Chromium/Electron apps,
Steam, Discord, Spotify, many media players) but keep a resizable frame.
Wine then asks the window manager, through _MOTIF_WM_HINTS, for
"border + resize handles" without a title. GNOME's Mutter only knows
"full decorations", "border only" and "none", so it draws a complete title
bar on top of the program's own: two headers.

This helper watches X11 windows that belong to Windows programs and turns
such title-less requests into "no decorations". Tested with GNOME's Mutter:
"border only" still gets a full title bar, while "none" leaves exactly the
program's own title bar, and the program keeps handling moving and
resizing itself (as on Windows), which also avoids the jumpy resizing
caused by GNOME's frame and Wine disagreeing about the window size. Windows that ask for a title (a normal
Windows caption) are left alone, so GNOME keeps drawing those.

It runs only while Windows programs are open: XWS starts it on demand
and it exits after a minute without Windows programs.
"""

from __future__ import annotations

import fcntl
import os
import select
import time
from pathlib import Path

MWM_HINTS_DECORATIONS = 1 << 1
MWM_DECOR_ALL = 1 << 0
MWM_DECOR_BORDER = 1 << 1
MWM_DECOR_TITLE = 1 << 3

WINDOWS_PROGRAM_SUFFIXES = (".exe", ".scr", ".com")


def corrected_hints(hints: list[int]) -> list[int] | None:
    """New _MOTIF_WM_HINTS value, or None if the window is fine as it is.

    Hints are [flags, functions, decorations, input_mode, status]."""
    if len(hints) < 3 or not hints[0] & MWM_HINTS_DECORATIONS:
        return None
    decorations = hints[2]
    if decorations == 0:
        return None  # already undecorated
    if decorations & (MWM_DECOR_TITLE | MWM_DECOR_ALL):
        return None  # a real caption: GNOME's title bar replaces it
    fixed = list(hints)
    fixed[2] = 0
    return fixed


def is_windows_program(wm_class: tuple[str, ...] | None) -> bool:
    if not wm_class:
        return False
    return any(part.lower().endswith(WINDOWS_PROGRAM_SUFFIXES) for part in wm_class)


def _lock(display_name: str):
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/xenon-{os.getuid()}")
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    safe = "".join(c if c.isalnum() else "_" for c in display_name)
    fh = open(runtime / f"xenon-xws-frames{safe}.lock", "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def run(idle_exit: float = 60.0) -> int:
    """Watch the X display until no Windows program has been open for
    `idle_exit` seconds. Returns 0, or 1 if X is unavailable."""
    try:
        from Xlib import X, display, error
    except ImportError:
        return 1
    display_name = os.environ.get("DISPLAY", "")
    if not display_name:
        return 1
    lock = _lock(display_name)
    if lock is None:
        return 0  # already running for this display
    try:
        d = display.Display()
    except Exception:  # noqa: BLE001 - no X server
        return 1
    root = d.screen().root
    mwm = d.intern_atom("_MOTIF_WM_HINTS")
    wm_class_atom = d.intern_atom("WM_CLASS")
    root.change_attributes(event_mask=X.SubstructureNotifyMask)
    tracked: set[int] = set()
    programs: set[int] = set()

    def check(win) -> None:
        try:
            cls = win.get_wm_class()
            if not is_windows_program(cls):
                return
            programs.add(win.id)
            prop = win.get_full_property(mwm, X.AnyPropertyType)
            if prop is None:
                return
            fixed = corrected_hints(list(prop.value))
            if fixed is not None:
                win.change_property(mwm, mwm, 32, fixed)
                d.flush()
        except error.XError:
            pass

    def watch(win) -> None:
        if win.id in tracked:
            return
        tracked.add(win.id)
        try:
            win.change_attributes(event_mask=X.PropertyChangeMask | X.StructureNotifyMask)
        except error.XError:
            return
        check(win)

    def scan(win, depth: int) -> None:
        try:
            children = win.query_tree().children
        except error.XError:
            return
        for child in children:
            watch(child)
            if depth > 0:
                scan(child, depth - 1)

    # Clients may already be reparented into window-manager frames.
    scan(root, 2)
    d.sync()
    idle_since = time.monotonic()
    while True:
        # Sleep until the X server has something for us (or once a second
        # to check the idle timer).
        select.select([d.fileno()], [], [], 1.0)
        while d.pending_events():
            ev = d.next_event()
            if ev.type == X.CreateNotify:
                watch(ev.window)
            elif ev.type == X.PropertyNotify and ev.atom in (mwm, wm_class_atom):
                check(ev.window)
            elif ev.type == X.DestroyNotify:
                tracked.discard(ev.window.id)
                programs.discard(ev.window.id)
        if programs:
            idle_since = time.monotonic()
        elif time.monotonic() - idle_since > idle_exit:
            return 0
