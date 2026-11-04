"""Helpers shared by Settings and Welcome."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import threading
from pathlib import Path

from gi.repository import GLib

ADMIN = "/usr/lib/xenon/xenon-admin"


def run_async(cmd: list[str], done, timeout: float | None = None) -> None:
    """Run a command in a thread; call done(returncode, stdout, stderr) on
    the GTK main loop."""
    def worker():
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            result = (p.returncode, p.stdout, p.stderr)
        except (OSError, subprocess.TimeoutExpired) as exc:
            result = (127, "", str(exc))
        GLib.idle_add(lambda: (done(*result), False)[1])
    threading.Thread(target=worker, daemon=True).start()


def call_async(func, done) -> None:
    """Run a Python function in a thread; deliver its result to done()."""
    def worker():
        try:
            value, error = func(), None
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            value, error = None, exc
        GLib.idle_add(lambda: (done(value, error), False)[1])
    threading.Thread(target=worker, daemon=True).start()


def xws_json(args: list[str], done) -> None:
    def finish(rc, out, err):
        try:
            done(json.loads(out) if out.strip() else None, None if rc == 0 else err)
        except ValueError:
            done(None, err or out)
    run_async(["xws", "--no-gui", *args], finish)


def admin(args: list[str], done) -> None:
    """Run a privileged action through polkit (asks for the password)."""
    run_async(["pkexec", ADMIN, *args], done)


def os_release() -> dict[str, str]:
    data = {}
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            for line in Path(path).read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    data[k] = shlex.split(v)[0] if v else ""
            break
        except (OSError, ValueError):
            continue
    return data


def kernel_release() -> str:
    try:
        return Path("/proc/sys/kernel/osrelease").read_text().strip()
    except OSError:
        return ""


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def open_uri(uri: str) -> None:
    subprocess.Popen(["xdg-open", uri], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def firewall_enabled() -> bool:
    try:
        text = Path("/etc/ufw/ufw.conf").read_text()
    except OSError:
        return False
    return any(l.strip().lower() == "enabled=yes" for l in text.splitlines())


AUTO_UPDATES_FILE = Path("/etc/apt/apt.conf.d/21xenon-auto-upgrades")


def auto_updates_enabled() -> bool:
    try:
        return 'Unattended-Upgrade "1"' in AUTO_UPDATES_FILE.read_text()
    except OSError:
        return False
