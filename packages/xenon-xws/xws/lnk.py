"""Reader for Windows shell link (.lnk) files, per [MS-SHLLINK].

Used to find the real program behind a Start Menu shortcut so XWS can
apply compatibility profiles and install runtimes before launching it.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

LNK_CLSID = bytes.fromhex("0114020000000000c000000000000046")

HAS_ID_LIST = 0x1
HAS_LINK_INFO = 0x2
HAS_NAME = 0x4
HAS_RELATIVE_PATH = 0x8
HAS_WORKING_DIR = 0x10
HAS_ARGUMENTS = 0x20
HAS_ICON_LOCATION = 0x40
IS_UNICODE = 0x80


@dataclass
class ShellLink:
    target: str = ""          # Windows path, e.g. C:\Program Files\Foo\foo.exe
    arguments: str = ""
    working_dir: str = ""
    description: str = ""
    icon_location: str = ""
    relative_path: str = ""


class LnkError(ValueError):
    pass


def parse(path: str | Path) -> ShellLink:
    data = Path(path).read_bytes()
    return parse_bytes(data)


def parse_bytes(data: bytes) -> ShellLink:
    if len(data) < 76 or struct.unpack_from("<I", data, 0)[0] != 0x4C \
            or data[4:20] != LNK_CLSID:
        raise LnkError("not a shell link")
    flags = struct.unpack_from("<I", data, 0x14)[0]
    off = 76
    link = ShellLink()
    try:
        if flags & HAS_ID_LIST:
            (size,) = struct.unpack_from("<H", data, off)
            off += 2 + size
        if flags & HAS_LINK_INFO:
            (li_size, li_hdr, li_flags, _vol, base_off, _net, suffix_off) = \
                struct.unpack_from("<7I", data, off)
            base = suffix = ""
            if li_hdr >= 0x24:
                ubase, usuffix = struct.unpack_from("<2I", data, off + 28)
                if li_flags & 1 and ubase:
                    base = _wstr(data, off + ubase)
                if usuffix:
                    suffix = _wstr(data, off + usuffix)
            if not base and li_flags & 1 and base_off:
                base = _cstr(data, off + base_off)
            if not suffix and suffix_off:
                suffix = _cstr(data, off + suffix_off)
            if base:
                link.target = base + suffix
            off += li_size
        unicode = bool(flags & IS_UNICODE)
        for flag, attr in ((HAS_NAME, "description"),
                           (HAS_RELATIVE_PATH, "relative_path"),
                           (HAS_WORKING_DIR, "working_dir"),
                           (HAS_ARGUMENTS, "arguments"),
                           (HAS_ICON_LOCATION, "icon_location")):
            if flags & flag:
                (count,) = struct.unpack_from("<H", data, off)
                off += 2
                nbytes = count * 2 if unicode else count
                raw = data[off:off + nbytes]
                off += nbytes
                text = raw.decode("utf-16-le" if unicode else "cp1252", "replace")
                # Wine counts the terminating NUL; Windows does not.
                setattr(link, attr, text.split("\0", 1)[0])
    except struct.error as exc:
        raise LnkError(f"truncated shell link: {exc}") from exc
    return link


def _cstr(data: bytes, off: int) -> str:
    end = data.find(b"\0", off)
    return data[off:end if end >= 0 else len(data)].decode("cp1252", "replace")


def _wstr(data: bytes, off: int) -> str:
    end = off
    while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
        end += 2
    return data[off:end].decode("utf-16-le", "replace")
