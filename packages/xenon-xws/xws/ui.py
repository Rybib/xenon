"""Tiny user-feedback layer: GTK dialogs via zenity when launched from the
desktop, plain text when launched from a terminal."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from contextlib import contextmanager

APP_TITLE = "Xenon"
_force_text = False


def set_text_mode(value: bool) -> None:
    global _force_text
    _force_text = value


def graphical() -> bool:
    if _force_text or os.environ.get("XWS_NO_GUI"):
        return False
    if sys.stdin is not None and sys.stdin.isatty():
        return False
    has_display = os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")
    return bool(has_display and shutil.which("zenity"))


def info(msg: str) -> None:
    print(f"xws: {msg}", file=sys.stderr)


class _Progress:
    def __init__(self, proc: subprocess.Popen | None):
        self.proc = proc

    def update(self, text: str) -> None:
        info(text)
        if self.proc and self.proc.stdin and self.proc.poll() is None:
            try:
                self.proc.stdin.write(f"# {text}\n")
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass


@contextmanager
def progress(title: str, text: str):
    proc = None
    if graphical():
        try:
            proc = subprocess.Popen(
                ["zenity", "--progress", "--pulsate", "--no-cancel", "--auto-close",
                 f"--title={APP_TITLE}", f"--text={text}", "--width=420"],
                stdin=subprocess.PIPE, text=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            proc = None
    p = _Progress(proc)
    info(text)
    try:
        yield p
    finally:
        if proc:
            try:
                proc.stdin.write("100\n")
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def error(title: str, text: str) -> None:
    print(f"xws: {title}: {text}", file=sys.stderr)
    if graphical():
        subprocess.run(["zenity", "--error", f"--title={APP_TITLE}",
                        f"--text=<b>{_escape(title)}</b>\n\n{_escape(text)}",
                        "--width=460"], check=False,
                       stderr=subprocess.DEVNULL)


def notify(title: str, body: str = "") -> None:
    info(f"{title} {body}".strip())
    if graphical() and shutil.which("notify-send"):
        subprocess.run(["notify-send", "--app-name=Xenon", "--icon=xenon-logo",
                        title, body], check=False, stderr=subprocess.DEVNULL)


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
