"""Reader for Wine's on-disk registry files (system.reg, user.reg).

Reading the files directly is instant and does not need to start Wine,
which keeps `xws apps` and the Settings app snappy.

Format reference: Wine's server/registry.c (save_subkeys / dump_value).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_KEY_RE = re.compile(r"^\[(.*)\](?:\s+\d+)?\s*$")


@dataclass
class RegValue:
    type: str  # "sz", "expand_sz", "multi_sz", "dword", "binary"
    data: object


def unescape(s: str) -> str:
    """Undo Wine's C-style string escaping."""
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c != "\\" or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        nxt = s[i + 1]
        if nxt == "x":
            j = i + 2
            while j < n and j < i + 6 and s[j] in "0123456789abcdefABCDEF":
                j += 1
            if j > i + 2:
                out.append(chr(int(s[i + 2:j], 16)))
                i = j
                continue
            out.append("x")
            i += 2
            continue
        if nxt in "01234567":
            j = i + 1
            while j < n and j < i + 4 and s[j] in "01234567":
                j += 1
            out.append(chr(int(s[i + 1:j], 8)))
            i = j
            continue
        out.append({"n": "\n", "r": "\r", "t": "\t", "a": "\a", "b": "\b",
                    "f": "\f", "v": "\v", "e": "\x1b"}.get(nxt, nxt))
        i += 2
    return "".join(out)


def _read_quoted(line: str, start: int) -> tuple[str, int]:
    """Read a "..." token starting at line[start] == '"'. Returns (raw, end_index)."""
    i = start + 1
    while i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == '"':
            return line[start + 1:i], i + 1
        i += 1
    raise ValueError("unterminated string")


def _parse_hex(text: str) -> bytes:
    text = text.replace("\\", "").replace(" ", "").replace("\n", "")
    return bytes(int(b, 16) for b in text.split(",") if b)


def _utf16(raw: bytes) -> str:
    return raw.decode("utf-16-le", "replace").rstrip("\0")


def _parse_value(data: str) -> RegValue:
    if data.startswith('"'):
        raw, _ = _read_quoted(data, 0)
        return RegValue("sz", unescape(raw))
    m = re.match(r"str\((\d+)\):(.*)$", data, re.S)
    if m:
        raw, _ = _read_quoted(m.group(2), 0)
        val = unescape(raw)
        kind = {"2": "expand_sz", "7": "multi_sz"}.get(m.group(1), "sz")
        if kind == "multi_sz":
            return RegValue(kind, [p for p in val.split("\0") if p])
        return RegValue(kind, val)
    if data.startswith("dword:"):
        return RegValue("dword", int(data[6:14], 16))
    m = re.match(r"hex(?:\(([0-9a-fA-F]+)\))?:(.*)$", data, re.S)
    if m:
        raw = _parse_hex(m.group(2))
        t = int(m.group(1), 16) if m.group(1) else 3
        if t in (1, 2):
            return RegValue("sz" if t == 1 else "expand_sz", _utf16(raw))
        if t == 7:
            return RegValue("multi_sz", [p for p in _utf16(raw).split("\0") if p])
        if t == 4 and len(raw) >= 4:
            return RegValue("dword", int.from_bytes(raw[:4], "little"))
        return RegValue("binary", raw)
    return RegValue("binary", data)


def parse_reg(text: str) -> dict[str, dict[str, RegValue]]:
    """Parse a Wine .reg file into {key_path: {value_name: RegValue}}.

    Key paths use single backslashes, e.g. 'Software\\Microsoft\\...'.
    The default value is stored under the name '@'.
    """
    keys: dict[str, dict[str, RegValue]] = {}
    current: dict[str, RegValue] | None = None
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        # Long hex values continue on the next line with a trailing backslash.
        # (Quoted strings always end in '"', so a trailing '\' is unambiguous.)
        while line.endswith("\\") and i < len(lines):
            line = line[:-1] + lines[i].strip()
            i += 1
        if not line or line[0] in ";#":
            continue
        m = _KEY_RE.match(line)
        if m:
            name = unescape(m.group(1))
            current = keys.setdefault(name, {})
            continue
        if current is None:
            continue
        try:
            if line.startswith("@="):
                current["@"] = _parse_value(line[2:])
            elif line.startswith('"'):
                raw_name, end = _read_quoted(line, 0)
                if end < len(line) and line[end] == "=":
                    current[unescape(raw_name)] = _parse_value(line[end + 1:])
        except (ValueError, IndexError):
            continue
    return keys


def load(path: Path) -> dict[str, dict[str, RegValue]]:
    try:
        return parse_reg(path.read_text(encoding="utf-8", errors="replace"))
    except FileNotFoundError:
        return {}


def subkeys(reg: dict[str, dict[str, RegValue]], parent: str) -> dict[str, dict[str, RegValue]]:
    """Immediate children of `parent` (case-insensitive, like Windows)."""
    prefix = parent.lower().rstrip("\\") + "\\"
    out = {}
    for key, values in reg.items():
        lk = key.lower()
        if lk.startswith(prefix) and "\\" not in key[len(prefix):]:
            out[key[len(prefix):]] = values
    return out


def get_str(values: dict[str, RegValue], name: str) -> str:
    for k, v in values.items():
        if k.lower() == name.lower() and isinstance(v.data, str):
            return v.data
    return ""


def get_dword(values: dict[str, RegValue], name: str) -> int | None:
    for k, v in values.items():
        if k.lower() == name.lower() and isinstance(v.data, int):
            return v.data
    return None
