"""Registry snapshots. Taken automatically before every installer runs, so
a bad install can be rolled back from Xenon Settings or `xws snapshot`."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import config
from .prefix import Prefix

FILES = ("system.reg", "user.reg", "userdef.reg")


def _dir(prefix: Prefix) -> Path:
    return config.SNAPSHOT_DIR / prefix.name


def create(prefix: Prefix, reason: str = "manual", keep: int = 10) -> Path | None:
    if not prefix.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = _dir(prefix) / stamp
    n = 1
    while dest.exists():
        n += 1
        dest = _dir(prefix) / f"{stamp}-{n}"
    dest.mkdir(parents=True)
    for name in FILES:
        src = prefix.path / name
        if src.exists():
            shutil.copy2(src, dest / name)
    (dest / "REASON").write_text(reason + "\n")
    prune(prefix, keep)
    return dest


def list_snapshots(prefix: Prefix) -> list[tuple[str, str]]:
    base = _dir(prefix)
    if not base.is_dir():
        return []
    out = []
    for d in sorted(base.iterdir(), reverse=True):
        if d.is_dir():
            try:
                reason = (d / "REASON").read_text().strip()
            except OSError:
                reason = ""
            out.append((d.name, reason))
    return out


def prune(prefix: Prefix, keep: int) -> None:
    snaps = list_snapshots(prefix)
    for name, _ in snaps[max(keep, 1):]:
        shutil.rmtree(_dir(prefix) / name, ignore_errors=True)


def restore(prefix: Prefix, name: str) -> None:
    src = _dir(prefix) / name
    if not src.is_dir() or "/" in name or name.startswith("."):
        raise FileNotFoundError(f"no snapshot {name!r} for {prefix.name}")
    prefix.kill()  # registry must not be in use
    create(prefix, reason=f"before restoring {name}")
    for fname in FILES:
        f = src / fname
        if f.exists():
            shutil.copy2(f, prefix.path / fname)
