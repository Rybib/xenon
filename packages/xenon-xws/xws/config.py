"""Paths and settings for XWS.

Settings come from (later wins):
  /usr/share/xenon/xws.toml   shipped defaults
  /etc/xenon/xws.toml         administrator overrides
  ~/.config/xenon/xws.toml    per-user overrides (written by Xenon Settings)
"""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def _xdg(var: str, default: str) -> Path:
    value = os.environ.get(var)
    if value and os.path.isabs(value):
        return Path(value)
    return Path.home() / default


DATA_HOME = _xdg("XDG_DATA_HOME", ".local/share")
CONFIG_HOME = _xdg("XDG_CONFIG_HOME", ".config")
STATE_HOME = _xdg("XDG_STATE_HOME", ".local/state")

# Everything XWS owns for a user lives below this directory.
XENON_DATA = Path(os.environ.get("XWS_DATA_DIR", DATA_HOME / "xenon"))
MAIN_PREFIX = XENON_DATA / "windows"
ISOLATED_DIR = XENON_DATA / "isolated"
SNAPSHOT_DIR = XENON_DATA / "snapshots"
LOG_DIR = STATE_HOME / "xenon" / "logs"
APPLICATIONS_DIR = DATA_HOME / "applications"

# Where the OS installs XWS's own payload (DXVK, VKD3D-Proton, winetricks).
LIB_DIR = Path(os.environ.get("XWS_LIB_DIR", "/usr/lib/xenon/xws"))
SHARE_DIR = Path(os.environ.get("XWS_SHARE_DIR", "/usr/share/xenon"))

SYSTEM_PROFILE_DIRS = [SHARE_DIR / "compat" / "profiles", Path("/etc/xenon/compat")]
USER_PROFILE_DIR = CONFIG_HOME / "xenon" / "compat"

CONFIG_FILES = [
    SHARE_DIR / "xws.toml",
    Path("/etc/xenon/xws.toml"),
    CONFIG_HOME / "xenon" / "xws.toml",
]


@dataclass
class Settings:
    # Which Wine graphics driver to use: "x11" (XWayland, the most
    # compatible today) or "wayland" (Wine's native Wayland driver).
    graphics_driver: str = "x11"
    # Windows version reported to programs.
    windows_version: str = "win10"
    # Translate DirectX 8-11 to Vulkan with DXVK, DirectX 12 with VKD3D-Proton.
    dxvk: bool = True
    vkd3d_proton: bool = True
    # Run games under Feral GameMode when it is installed.
    gamemode: bool = True
    # Show the MangoHud performance overlay in games.
    mangohud: bool = False
    # Install runtimes (VC++, .NET, d3dx...) automatically when a program needs them.
    auto_runtimes: bool = True
    # Snapshots of the Windows registry to keep.
    snapshot_keep: int = 10
    # Apply community compatibility profiles.
    compat_profiles: bool = True
    # Extra environment for every Windows program.
    env: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, files: list[Path] | None = None) -> "Settings":
        merged: dict = {}
        for path in files if files is not None else CONFIG_FILES:
            try:
                with open(path, "rb") as fh:
                    data = tomllib.load(fh)
            except FileNotFoundError:
                continue
            except (OSError, tomllib.TOMLDecodeError) as exc:
                print(f"xws: ignoring unreadable settings file {path}: {exc}")
                continue
            merged.update(data.get("xws", data))
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in merged.items() if k in known})


def user_settings_path() -> Path:
    return CONFIG_FILES[-1]


def write_user_setting(key: str, value) -> None:
    """Persist a single setting to the per-user settings file."""
    if key not in Settings.__dataclass_fields__ or key == "env":
        raise KeyError(key)
    path = user_settings_path()
    current: dict = {}
    if path.exists():
        with open(path, "rb") as fh:
            current = tomllib.load(fh).get("xws", {})
    current[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Written by Xenon. Edit freely.", "[xws]"]
    for k, v in sorted(current.items()):
        if k == "env":
            continue
        lines.append(f"{k} = {_toml_value(v)}")
    env = current.get("env")
    if env:
        lines.append("")
        lines.append("[xws.env]")
        for k, v in sorted(env.items()):
            lines.append(f"{k} = {_toml_value(str(v))}")
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    tmp.replace(path)


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def find_wine() -> str | None:
    """Locate the Wine loader. Xenon ships WineHQ's build in /opt/wine-stable."""
    override = os.environ.get("XWS_WINE")
    if override:
        return override
    for candidate in ("/opt/wine-stable/bin/wine", "/opt/wine-staging/bin/wine"):
        if os.access(candidate, os.X_OK):
            return candidate
    for name in ("wine", "wine-stable", "wine64"):
        found = shutil.which(name)
        if found:
            return found
    # Debian/Ubuntu's wine64 package without the "wine" front-end package.
    for candidate in ("/usr/lib/wine/wine", "/usr/lib/wine/wine64"):
        if os.access(candidate, os.X_OK):
            return candidate
    return None


def wine_tool(name: str) -> str | None:
    """Find a companion tool (wineserver, wineboot...) next to the loader."""
    wine = find_wine()
    if wine:
        sibling = Path(wine).with_name(name)
        if os.access(sibling, os.X_OK):
            return str(sibling)
    found = shutil.which(name)
    if found:
        return found
    # Debian/Ubuntu keep wineserver in /usr/lib/wine.
    for d in ("/usr/lib/wine", "/usr/lib/x86_64-linux-gnu/wine"):
        p = Path(d) / name
        if os.access(p, os.X_OK):
            return str(p)
    return None


def find_tool(name: str) -> str | None:
    """Find a helper program; Debian installs some games tools (gamemoderun)
    in /usr/games, which is not on every PATH (e.g. system services)."""
    found = shutil.which(name)
    if found:
        return found
    candidate = Path("/usr/games") / name
    return str(candidate) if os.access(candidate, os.X_OK) else None
