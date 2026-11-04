"""Per-app compatibility profiles.

A profile is a small TOML file describing known fixes for one program.
XWS matches the program being launched against all profiles and silently
applies the first match. See compat/README.md for the schema.

Example:

    [app]
    id = "notepad-plus-plus"
    name = "Notepad++"
    rating = "platinum"

    [match]
    exe = ["notepad++.exe", "npp.*.installer*.exe"]
    product = ["Notepad++"]

    [fix]
    runtimes = []
    dll_overrides = { }
    env = { }
"""

from __future__ import annotations

import fnmatch
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .pe import PEInfo

RATINGS = ("platinum", "gold", "silver", "bronze", "broken", "untested")
GRAPHICS = ("x11", "wayland")


@dataclass
class Profile:
    id: str
    name: str
    rating: str = "untested"
    notes: str = ""
    source: str = ""
    # match
    exe: list[str] = field(default_factory=list)
    product: list[str] = field(default_factory=list)
    company: list[str] = field(default_factory=list)
    # fix
    runtimes: list[str] = field(default_factory=list)
    dll_overrides: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    windows_version: str | None = None
    graphics_driver: str | None = None
    isolated: bool = False
    game: bool | None = None
    dxvk: bool | None = None
    vkd3d_proton: bool | None = None
    args: list[str] = field(default_factory=list)

    def matches(self, exe_name: str, pe: PEInfo | None) -> bool:
        name = exe_name.lower()
        if any(fnmatch.fnmatchcase(name, pat.lower()) for pat in self.exe):
            return True
        if pe and pe.version:
            product = pe.version.get("ProductName", "").lower()
            company = pe.version.get("CompanyName", "").lower()
            if self.product and product and any(
                    fnmatch.fnmatchcase(product, p.lower()) for p in self.product):
                if not self.company or any(
                        fnmatch.fnmatchcase(company, c.lower()) for c in self.company):
                    return True
        return False


class ProfileError(ValueError):
    pass


def from_dict(data: dict, source: str = "") -> Profile:
    app = data.get("app", {})
    match = data.get("match", {})
    fix = data.get("fix", {})
    if not app.get("id") or not app.get("name"):
        raise ProfileError(f"{source}: [app] needs id and name")
    if not (match.get("exe") or match.get("product")):
        raise ProfileError(f"{source}: [match] needs exe or product patterns")
    rating = app.get("rating", "untested")
    if rating not in RATINGS:
        raise ProfileError(f"{source}: rating must be one of {RATINGS}")
    graphics = fix.get("graphics_driver")
    if graphics is not None and graphics not in GRAPHICS:
        raise ProfileError(f"{source}: graphics_driver must be one of {GRAPHICS}")
    for key in ("exe", "product", "company"):
        if not isinstance(match.get(key, []), list):
            raise ProfileError(f"{source}: match.{key} must be a list")
    return Profile(
        id=app["id"], name=app["name"], rating=rating, notes=app.get("notes", ""),
        source=source,
        exe=match.get("exe", []), product=match.get("product", []),
        company=match.get("company", []),
        runtimes=fix.get("runtimes", []),
        dll_overrides={str(k): str(v) for k, v in fix.get("dll_overrides", {}).items()},
        env={str(k): str(v) for k, v in fix.get("env", {}).items()},
        windows_version=fix.get("windows_version"),
        graphics_driver=graphics,
        isolated=bool(fix.get("isolated", False)),
        game=fix.get("game"),
        dxvk=fix.get("dxvk"),
        vkd3d_proton=fix.get("vkd3d_proton"),
        args=fix.get("args", []),
    )


def load_profiles(dirs: list[Path] | None = None) -> list[Profile]:
    """Load profiles; user profiles come first so they override system ones."""
    if dirs is None:
        dirs = [config.USER_PROFILE_DIR, *config.SYSTEM_PROFILE_DIRS]
    seen: set[str] = set()
    profiles = []
    for d in dirs:
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.toml")):
            try:
                with open(path, "rb") as fh:
                    prof = from_dict(tomllib.load(fh), str(path))
            except (OSError, tomllib.TOMLDecodeError, ProfileError) as exc:
                print(f"xws: skipping profile {path}: {exc}")
                continue
            if prof.id in seen:
                continue
            seen.add(prof.id)
            profiles.append(prof)
    return profiles


def find_profile(exe_path: str | Path, pe: PEInfo | None,
                 profiles: list[Profile] | None = None) -> Profile | None:
    if profiles is None:
        profiles = load_profiles()
    name = Path(exe_path).name
    for prof in profiles:
        if prof.matches(name, pe):
            return prof
    return None
