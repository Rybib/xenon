"""Translate between Windows paths and Linux paths inside a Wine prefix."""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

_DRIVE_RE = re.compile(r"^([A-Za-z]):[\\/]?(.*)$", re.S)


def drive_root(prefix: Path, letter: str) -> Path | None:
    link = prefix / "dosdevices" / f"{letter.lower()}:"
    if not link.exists():
        return None
    return Path(os.path.realpath(link))


def _resolve_case_insensitive(base: Path, parts: list[str]) -> Path:
    """Follow `parts` below `base`, matching each component case-insensitively."""
    cur = base
    for i, part in enumerate(parts):
        if part in ("", "."):
            continue
        cand = cur / part
        if cand.exists():
            cur = cand
            continue
        try:
            lowered = part.lower()
            match = next((e for e in os.listdir(cur) if e.lower() == lowered), None)
        except OSError:
            match = None
        if match is None:
            return cur.joinpath(*parts[i:])
        cur = cur / match
    return cur


def to_unix(prefix: Path, winpath: str) -> Path | None:
    """C:\\Program Files\\Foo\\foo.exe -> /home/u/.../drive_c/Program Files/Foo/foo.exe"""
    winpath = winpath.strip().strip('"')
    m = _DRIVE_RE.match(winpath)
    if not m:
        return None
    root = drive_root(prefix, m.group(1))
    if root is None:
        return None
    parts = [p for p in re.split(r"[\\/]+", m.group(2)) if p]
    return _resolve_case_insensitive(root, parts)


def to_windows(prefix: Path, unixpath: str | Path) -> str:
    """Best-effort Linux -> Windows path using the prefix's drive mappings."""
    target = os.path.realpath(unixpath)
    best: tuple[int, str, str] | None = None
    dosdevices = prefix / "dosdevices"
    if dosdevices.is_dir():
        for entry in os.listdir(dosdevices):
            if len(entry) != 2 or not entry.endswith(":"):
                continue
            root = os.path.realpath(dosdevices / entry)
            if target == root or target.startswith(root.rstrip("/") + "/"):
                if best is None or len(root) > best[0]:
                    best = (len(root), entry.upper(), root)
    if best is None:
        return target
    rest = target[len(best[2]):].lstrip("/")
    return best[1] + "\\" + rest.replace("/", "\\")


def split_command_line(cmdline: str) -> list[str]:
    """Split a Windows command line like CommandLineToArgvW does."""
    args: list[str] = []
    cur: list[str] = []
    in_quotes = False
    have_arg = False
    i = 0
    n = len(cmdline)
    while i < n:
        c = cmdline[i]
        if c == "\\":
            j = i
            while j < n and cmdline[j] == "\\":
                j += 1
            count = j - i
            if j < n and cmdline[j] == '"':
                cur.append("\\" * (count // 2))
                if count % 2:
                    cur.append('"')
                    i = j + 1
                else:
                    i = j
                have_arg = True
                continue
            cur.append("\\" * count)
            i = j
            have_arg = True
            continue
        if c == '"':
            if in_quotes and i + 1 < n and cmdline[i + 1] == '"':
                cur.append('"')
                i += 2
                continue
            in_quotes = not in_quotes
            have_arg = True
            i += 1
            continue
        if c in " \t" and not in_quotes:
            if have_arg:
                args.append("".join(cur))
                cur = []
                have_arg = False
            i += 1
            continue
        cur.append(c)
        have_arg = True
        i += 1
    if have_arg:
        args.append("".join(cur))
    return args


def split_uninstall_string(cmdline: str) -> list[str]:
    """Uninstall strings are often unquoted paths with spaces, e.g.
    C:\\Program Files\\Foo\\uninst.exe /S. Recover the program path by
    finding the first token ending in .exe."""
    stripped = cmdline.strip()
    if stripped.startswith('"'):
        return split_command_line(stripped)
    m = re.match(r"^(.+?\.(?:exe|com|bat|cmd))(?:\s+(.*))?$", stripped, re.I | re.S)
    if m:
        rest = m.group(2) or ""
        return [m.group(1)] + split_command_line(rest)
    return split_command_line(stripped)


def shell_quote(args: list[str]) -> str:
    return " ".join(shlex.quote(a) for a in args)
