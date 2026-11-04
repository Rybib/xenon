"""Installed Windows programs, read from the registry's Uninstall keys —
the same list Windows shows in "Apps & features"."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

from . import registry, winpath
from .prefix import Prefix

UNINSTALL_KEYS_MACHINE = [
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
    r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
]
UNINSTALL_KEY_USER = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"

# Components Wine itself installs; shown as runtimes, not apps.
RUNTIME_NAMES = ("wine mono", "wine gecko", "microsoft visual c++", "microsoft .net",
                 "directx", "microsoft xml", "microsoft windows desktop runtime",
                 "microsoft asp.net")


@dataclass
class InstalledApp:
    id: str             # "<environment>:<key>"
    environment: str
    key: str
    name: str
    publisher: str
    version: str
    install_location: str
    uninstall_string: str
    quiet_uninstall_string: str
    icon: str           # Linux path to the program's icon file, if found
    size_kb: int
    is_runtime: bool
    scope: str          # "machine" or "user"

    def to_dict(self) -> dict:
        return asdict(self)


def list_apps(prefixes: list[Prefix] | None = None, include_runtimes: bool = False
              ) -> list[InstalledApp]:
    prefixes = Prefix.all() if prefixes is None else prefixes
    found: list[InstalledApp] = []
    for prefix in prefixes:
        found.extend(_apps_in(prefix))
    if not include_runtimes:
        found = [a for a in found if not a.is_runtime]
    found.sort(key=lambda a: a.name.lower())
    return found


def _apps_in(prefix: Prefix) -> list[InstalledApp]:
    out: list[InstalledApp] = []
    seen: set[str] = set()
    machine = registry.load(prefix.path / "system.reg")
    user = registry.load(prefix.path / "user.reg")
    sources = [(machine, k, "machine") for k in UNINSTALL_KEYS_MACHINE]
    sources.append((user, UNINSTALL_KEY_USER, "user"))
    for reg, parent, scope in sources:
        for key, values in registry.subkeys(reg, parent).items():
            name = registry.get_str(values, "DisplayName")
            if not name:
                continue
            if registry.get_dword(values, "SystemComponent") == 1:
                continue
            if registry.get_str(values, "ParentKeyName"):  # updates/patches
                continue
            ident = f"{prefix.name}:{key}"
            if ident in seen:
                continue
            seen.add(ident)
            icon = _icon_path(prefix, registry.get_str(values, "DisplayIcon"))
            size = registry.get_dword(values, "EstimatedSize") or 0
            out.append(InstalledApp(
                id=ident, environment=prefix.name, key=key, name=name,
                publisher=registry.get_str(values, "Publisher"),
                version=registry.get_str(values, "DisplayVersion"),
                install_location=registry.get_str(values, "InstallLocation"),
                uninstall_string=registry.get_str(values, "UninstallString"),
                quiet_uninstall_string=registry.get_str(values, "QuietUninstallString"),
                icon=icon, size_kb=size,
                is_runtime=name.lower().startswith(RUNTIME_NAMES),
                scope=scope,
            ))
    return out


def _icon_path(prefix: Prefix, display_icon: str) -> str:
    if not display_icon:
        return ""
    path = display_icon.split(",")[0].strip().strip('"')
    unix = winpath.to_unix(prefix.path, path)
    return str(unix) if unix and os.path.exists(unix) else ""


def find(app_id: str) -> tuple[InstalledApp, Prefix] | None:
    env, _, _ = app_id.partition(":")
    for prefix in Prefix.all():
        if prefix.name != env:
            continue
        for app in _apps_in(prefix):
            if app.id == app_id:
                return app, prefix
    # Allow matching by display name for convenience on the command line.
    for prefix in Prefix.all():
        for app in _apps_in(prefix):
            if app.name.lower() == app_id.lower():
                return app, prefix
    return None


def uninstall_command(app: InstalledApp) -> list[str]:
    """The Wine argument list that runs the program's uninstaller."""
    cmd = app.uninstall_string.strip()
    if not cmd:
        raise ValueError(f"{app.name} has no uninstaller registered")
    parts = winpath.split_uninstall_string(cmd)
    exe = parts[0].lower().replace("/", "\\").rsplit("\\", 1)[-1]
    if exe in ("msiexec", "msiexec.exe"):
        # "MsiExec.exe /I{GUID}" or "/X{GUID}" -> always uninstall.
        guid = next((p[2:] if p[:2].lower() in ("/i", "/x") and len(p) > 2 else p
                     for p in parts[1:] if "{" in p), None)
        if guid is None:
            guid = app.key
        return ["msiexec", "/x", guid]
    return parts


def environment_in_use(prefix: Prefix, exclude_id: str | None = None) -> bool:
    return any(a.id != exclude_id for a in _apps_in(prefix) if not a.is_runtime)


def size_human(kb: int) -> str:
    if kb <= 0:
        return ""
    size = float(kb)
    for unit in ("KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def location_unix(prefix: Prefix, app: InstalledApp) -> Path | None:
    if not app.install_location:
        return None
    return winpath.to_unix(prefix.path, app.install_location)
