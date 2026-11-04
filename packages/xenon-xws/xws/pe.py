"""Minimal, dependency-free reader for Windows executables.

XWS uses it to decide, before launching a program, what that program
needs: 32 vs 64 bit, GUI vs console, which DLLs it imports (to install
runtimes on demand), whether it is a .NET assembly, and its version info
(ProductName, CompanyName...) for matching compatibility profiles.

Only reads; never executes anything. Malformed files raise PEError.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # MSI / compound document

MACHINE_I386 = 0x14C
MACHINE_AMD64 = 0x8664
MACHINE_ARM64 = 0xAA64

SUBSYSTEM_GUI = 2
SUBSYSTEM_CONSOLE = 3

DIR_IMPORT = 1
DIR_RESOURCE = 2
DIR_CLR = 14

RT_VERSION = 16

MAX_READ = 512 * 1024 * 1024


class PEError(ValueError):
    pass


@dataclass
class Section:
    name: str
    vaddr: int
    vsize: int
    raw_ptr: int
    raw_size: int


@dataclass
class PEInfo:
    path: str
    machine: int
    subsystem: int
    is_dll: bool
    is_dotnet: bool
    imports: list[str] = field(default_factory=list)
    version: dict[str, str] = field(default_factory=dict)

    @property
    def bits(self) -> int:
        return 32 if self.machine == MACHINE_I386 else 64

    @property
    def is_gui(self) -> bool:
        return self.subsystem == SUBSYSTEM_GUI

    @property
    def imports_lower(self) -> set[str]:
        return {i.lower() for i in self.imports}


def file_kind(path: str | Path) -> str:
    """Classify a file by magic bytes: 'pe', 'msi', or 'unknown'."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return "unknown"
    if head[:2] == b"MZ":
        return "pe"
    if head == OLE_MAGIC:
        return "msi"
    return "unknown"


class _Reader:
    def __init__(self, data: bytes):
        self.data = data

    def u16(self, off: int) -> int:
        return self._unpack("<H", off)

    def u32(self, off: int) -> int:
        return self._unpack("<I", off)

    def _unpack(self, fmt: str, off: int) -> int:
        size = struct.calcsize(fmt)
        if off < 0 or off + size > len(self.data):
            raise PEError(f"read past end of file at {off:#x}")
        return struct.unpack_from(fmt, self.data, off)[0]

    def cstr(self, off: int, limit: int = 512) -> str:
        if off < 0 or off >= len(self.data):
            raise PEError("string offset out of range")
        end = self.data.find(b"\0", off, off + limit)
        if end < 0:
            end = min(off + limit, len(self.data))
        return self.data[off:end].decode("latin-1")


def parse(path: str | Path) -> PEInfo:
    path = Path(path)
    if path.stat().st_size > MAX_READ:
        # Huge self-extracting installers: only the headers matter and the
        # important tables sit near the front. Read a bounded prefix.
        with open(path, "rb") as fh:
            data = fh.read(MAX_READ)
    else:
        data = path.read_bytes()
    return parse_bytes(data, str(path))


def parse_bytes(data: bytes, name: str = "<memory>") -> PEInfo:
    r = _Reader(data)
    if data[:2] != b"MZ":
        raise PEError("not an MZ executable")
    pe_off = r.u32(0x3C)
    if data[pe_off:pe_off + 4] != b"PE\0\0":
        raise PEError("no PE header (plain DOS program?)")
    coff = pe_off + 4
    machine = r.u16(coff)
    nsections = r.u16(coff + 2)
    opt_size = r.u16(coff + 16)
    characteristics = r.u16(coff + 18)
    opt = coff + 20
    magic = r.u16(opt)
    if magic == 0x10B:  # PE32
        subsystem = r.u16(opt + 68)
        ndirs = r.u32(opt + 92)
        dirs = opt + 96
    elif magic == 0x20B:  # PE32+
        subsystem = r.u16(opt + 68)
        ndirs = r.u32(opt + 108)
        dirs = opt + 112
    else:
        raise PEError(f"unknown optional header magic {magic:#x}")

    sections = []
    sec = opt + opt_size
    for i in range(min(nsections, 96)):
        base = sec + i * 40
        raw_name = data[base:base + 8].rstrip(b"\0").decode("latin-1")
        sections.append(Section(raw_name, r.u32(base + 12), r.u32(base + 8),
                                r.u32(base + 20), r.u32(base + 16)))

    def rva_to_off(rva: int) -> int:
        for s in sections:
            size = max(s.vsize, s.raw_size)
            if s.vaddr <= rva < s.vaddr + size:
                return rva - s.vaddr + s.raw_ptr
        raise PEError(f"RVA {rva:#x} not in any section")

    def directory(index: int) -> tuple[int, int]:
        if index >= ndirs:
            return 0, 0
        return r.u32(dirs + index * 8), r.u32(dirs + index * 8 + 4)

    info = PEInfo(
        path=name,
        machine=machine,
        subsystem=subsystem,
        is_dll=bool(characteristics & 0x2000),
        is_dotnet=directory(DIR_CLR)[0] != 0,
    )

    imp_rva, _ = directory(DIR_IMPORT)
    if imp_rva:
        try:
            off = rva_to_off(imp_rva)
            for _ in range(4096):
                name_rva = r.u32(off + 12)
                if name_rva == 0 and r.u32(off) == 0:
                    break
                info.imports.append(r.cstr(rva_to_off(name_rva)))
                off += 20
        except PEError:
            pass  # damaged import table: keep what we have

    res_rva, _ = directory(DIR_RESOURCE)
    if res_rva:
        try:
            info.version = _read_version(r, rva_to_off, res_rva)
        except (PEError, UnicodeDecodeError, struct.error):
            pass
    return info


def _read_version(r: _Reader, rva_to_off, res_rva: int) -> dict[str, str]:
    root = rva_to_off(res_rva)

    def entries(dir_off: int):
        named = r.u16(dir_off + 12)
        ids = r.u16(dir_off + 14)
        for i in range(min(named + ids, 1024)):
            e = dir_off + 16 + i * 8
            yield r.u32(e), r.u32(e + 4)

    # Level 1: type == RT_VERSION
    for type_id, type_ptr in entries(root):
        if type_id != RT_VERSION or not type_ptr & 0x80000000:
            continue
        # Level 2: first name, level 3: first language
        for _, name_ptr in entries(root + (type_ptr & 0x7FFFFFFF)):
            if not name_ptr & 0x80000000:
                continue
            for _, lang_ptr in entries(root + (name_ptr & 0x7FFFFFFF)):
                if lang_ptr & 0x80000000:
                    continue
                leaf = root + lang_ptr
                data_rva, size = r.u32(leaf), r.u32(leaf + 4)
                off = rva_to_off(data_rva)
                return _parse_vs_versioninfo(r.data[off:off + size])
    return {}


def _parse_vs_versioninfo(blob: bytes) -> dict[str, str]:
    """Walk VS_VERSIONINFO and collect StringFileInfo key/value pairs.

    Tree: VS_VERSION_INFO (0) -> StringFileInfo (1) -> StringTable (2)
          -> String (3, the key/value pairs we want).
    """
    result: dict[str, str] = {}

    def align(n: int) -> int:
        return (n + 3) & ~3

    def walk(off: int, end: int, depth: int) -> None:
        while off + 6 <= end:
            length, value_len, vtype = struct.unpack_from("<HHH", blob, off)
            if length == 0:
                return
            node_end = min(off + length, end)
            key_start = off + 6
            key_end = key_start
            while key_end + 1 < node_end and blob[key_end:key_end + 2] != b"\0\0":
                key_end += 2
            key = blob[key_start:key_end].decode("utf-16-le", "replace")
            value_off = align(key_end + 2)
            if depth == 3:
                if vtype == 1 and value_len:
                    raw = blob[value_off:min(value_off + value_len * 2, node_end)]
                    text = raw.decode("utf-16-le", "replace").split("\0")[0].strip()
                    if text:
                        result[key] = text
            elif depth == 0 or key == "StringFileInfo" or depth == 2:
                child_off = align(value_off + (value_len if vtype == 0 else value_len * 2))
                walk(child_off, node_end, depth + 1)
            off = align(off + length)

    walk(0, len(blob), 0)
    return result
