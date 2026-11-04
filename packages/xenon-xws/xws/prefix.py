"""The managed Windows environment ("prefix").

Every user gets one main environment at ~/.local/share/xenon/windows.
Programs whose compatibility profile asks for isolation get their own
environment under ~/.local/share/xenon/isolated/<profile-id>.
"""

from __future__ import annotations

import getpass
import json
import os
import pwd
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import __version__, config, ui

# Bump when configure() changes, so existing environments get re-applied.
LAYOUT_VERSION = 3

DXVK_DLLS = ["d3d8", "d3d9", "d3d10core", "d3d11", "dxgi"]
VKD3D_DLLS = ["d3d12", "d3d12core"]

# Metric-compatible free fonts used in place of Microsoft's core fonts.
FONT_REPLACEMENTS = {
    "Arial": "Liberation Sans",
    "Arial Narrow": "Liberation Sans Narrow",
    "Times New Roman": "Liberation Serif",
    "Courier New": "Liberation Mono",
    "Calibri": "Carlito",
    "Cambria": "Caladea",
    "Segoe UI": "Noto Sans",
    "Tahoma": "DejaVu Sans",
    "Verdana": "DejaVu Sans",
    "MS Shell Dlg": "Noto Sans",
    "MS Shell Dlg 2": "Noto Sans",
}

USER_FOLDERS = {
    "Desktop": "DESKTOP",
    "Documents": "DOCUMENTS",
    "Downloads": "DOWNLOAD",
    "Music": "MUSIC",
    "Pictures": "PICTURES",
    "Videos": "VIDEOS",
}


class PrefixError(RuntimeError):
    pass


def _check_safe_id(name: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", name):
        raise PrefixError(f"invalid environment id {name!r}")
    return name


class Prefix:
    def __init__(self, path: Path, name: str):
        self.path = Path(path)
        self.name = name

    # ---- construction ---------------------------------------------------
    @classmethod
    def main(cls) -> "Prefix":
        return cls(config.MAIN_PREFIX, "main")

    @classmethod
    def isolated(cls, profile_id: str) -> "Prefix":
        return cls(config.ISOLATED_DIR / _check_safe_id(profile_id), profile_id)

    @classmethod
    def from_path(cls, path: str | Path) -> "Prefix":
        path = Path(path).resolve()
        if path == config.MAIN_PREFIX.resolve():
            return cls.main()
        if path.parent == config.ISOLATED_DIR.resolve():
            return cls(path, path.name)
        return cls(path, path.name)

    @classmethod
    def all(cls) -> list["Prefix"]:
        found = []
        main = cls.main()
        if main.exists():
            found.append(main)
        if config.ISOLATED_DIR.is_dir():
            for d in sorted(config.ISOLATED_DIR.iterdir()):
                p = cls(d, d.name)
                if p.exists():
                    found.append(p)
        return found

    # ---- state ------------------------------------------------------------
    @property
    def drive_c(self) -> Path:
        return self.path / "drive_c"

    @property
    def state_file(self) -> Path:
        return self.path / ".xenon-state.json"

    def exists(self) -> bool:
        return (self.path / "system.reg").exists()

    def state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text())
        except (OSError, ValueError):
            return {}

    def save_state(self, **updates) -> None:
        st = self.state()
        st.update(updates)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, indent=2, sort_keys=True))
        tmp.replace(self.state_file)

    def installed_runtimes(self) -> list[str]:
        return list(self.state().get("runtimes", []))

    def mark_runtime(self, verb: str) -> None:
        rts = self.installed_runtimes()
        if verb not in rts:
            rts.append(verb)
            self.save_state(runtimes=sorted(rts))

    # ---- environment --------------------------------------------------------
    def base_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["WINEPREFIX"] = str(self.path)
        env.setdefault("WINEDEBUG", "-all")
        # Keep DXVK/VKD3D-Proton from writing log files next to programs.
        env.setdefault("DXVK_LOG_LEVEL", "none")
        env.setdefault("DXVK_LOG_PATH", "none")
        env.setdefault("VKD3D_DEBUG", "none")
        env.setdefault("VKD3D_SHADER_DEBUG", "none")
        env.setdefault("WINE_LARGE_ADDRESS_AWARE", "1")
        # Shader caches go somewhere sensible instead of the program folder.
        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "xenon"
        env.setdefault("DXVK_STATE_CACHE_PATH", str(cache / "dxvk"))
        env.setdefault("VKD3D_SHADER_CACHE_PATH", str(cache / "vkd3d"))
        env.pop("WINEARCH", None)
        return env

    def wine(self, *args: str, env: dict | None = None, log: Path | None = None,
             check: bool = False, timeout: float | None = None) -> int:
        wine = config.find_wine()
        if not wine:
            raise PrefixError("Wine is not installed")
        run_env = env or self.base_env()
        out = open(log, "a") if log else subprocess.DEVNULL
        try:
            rc = subprocess.run([wine, *args], env=run_env, stdout=out,
                                stderr=subprocess.STDOUT, timeout=timeout).returncode
        finally:
            if log:
                out.close()
        if check and rc != 0:
            raise PrefixError(f"wine {' '.join(args)} failed ({rc})")
        return rc

    def wait_server(self, timeout: float = 120) -> None:
        server = config.wine_tool("wineserver")
        if server:
            try:
                subprocess.run([server, "-w"], env=self.base_env(), timeout=timeout,
                               check=False)
            except subprocess.TimeoutExpired:
                pass

    def kill(self) -> None:
        server = config.wine_tool("wineserver")
        if server and self.exists():
            subprocess.run([server, "-k"], env=self.base_env(), check=False,
                           stderr=subprocess.DEVNULL)

    # ---- lifecycle ----------------------------------------------------------
    def needs_setup(self) -> bool:
        if not self.exists():
            return True
        st = self.state()
        return (st.get("layout") != LAYOUT_VERSION
                or st.get("dxvk") != _payload_version("dxvk")
                or st.get("vkd3d_proton") != _payload_version("vkd3d-proton"))

    def ensure(self, settings: config.Settings) -> None:
        if not self.needs_setup():
            self.refresh(settings)
            return
        first = not self.exists()
        title = ("Setting up Windows support (first time only, about a minute)..."
                 if first else "Updating Windows support...")
        log = config.LOG_DIR / f"prefix-{self.name}.log"
        with ui.progress("Windows support", title) as p:
            if first:
                self.create(log)
            p.update("Configuring Windows environment...")
            self.configure(settings, log)
            p.update("Installing graphics translation (DirectX to Vulkan)...")
            self.deploy_graphics()
            self.save_state(layout=LAYOUT_VERSION, xws=__version__,
                            dxvk=_payload_version("dxvk"),
                            vkd3d_proton=_payload_version("vkd3d-proton"),
                            updated=int(time.time()))
        self.refresh(settings)

    def create(self, log: Path) -> None:
        log.parent.mkdir(parents=True, exist_ok=True)
        self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.drive_c.mkdir(exist_ok=True)
        self.enable_casefold(self.drive_c)
        env = self.base_env()
        overrides = ["winemenubuilder.exe=d"]  # avoid stray menu entries during boot
        if not _addon_available("mono"):
            overrides.append("mscoree=d")
        if not _addon_available("gecko"):
            overrides.append("mshtml=d")
        env["WINEDLLOVERRIDES"] = ";".join(overrides)
        rc = self.wine("wineboot", "--init", env=env, log=log, timeout=600)
        self.wait_server()
        if rc != 0 or not self.exists():
            raise PrefixError(f"Could not create the Windows environment (see {log})")
        self.save_state(created=int(time.time()), runtimes=[],
                        casefold=_has_casefold(self.drive_c))

    @staticmethod
    def enable_casefold(directory: Path) -> bool:
        """Make the directory case-insensitive like Windows (ext4 casefold).

        Only possible on an empty directory on a filesystem created with the
        casefold feature. Wine works without it; this is a speed-up."""
        if not shutil.which("chattr"):
            return False
        try:
            if any(directory.iterdir()):
                return False
        except OSError:
            return False
        rc = subprocess.run(["chattr", "+F", str(directory)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        return rc == 0

    def configure(self, settings: config.Settings, log: Path) -> None:
        reg = registry_defaults(settings)
        with tempfile.NamedTemporaryFile("w", suffix=".reg", delete=False,
                                         encoding="utf-16") as fh:
            fh.write(reg)
            reg_path = fh.name
        try:
            self.wine("regedit", "/S", reg_path, log=log, timeout=300)
        finally:
            os.unlink(reg_path)
        self.wine("winecfg", "-v", settings.windows_version, log=log, timeout=300)
        self.link_user_folders()
        self.map_drives()
        self.wait_server()

    def deploy_graphics(self) -> None:
        """Copy DXVK and VKD3D-Proton DLLs into the environment."""
        sys32 = self.drive_c / "windows" / "system32"
        wow = self.drive_c / "windows" / "syswow64"
        for payload, dlls, dirs in (
                ("dxvk", DXVK_DLLS, {"x64": sys32, "x32": wow}),
                ("vkd3d-proton", VKD3D_DLLS, {"x64": sys32, "x86": wow})):
            base = config.LIB_DIR / payload
            for arch, dest in dirs.items():
                if not dest.is_dir():
                    continue
                for dll in dlls:
                    src = base / arch / f"{dll}.dll"
                    if src.exists():
                        tmp = dest / f".{dll}.dll.xws"
                        shutil.copy2(src, tmp)
                        tmp.replace(dest / f"{dll}.dll")

    def refresh(self, settings: config.Settings) -> None:
        """Cheap per-launch upkeep: drive letters for USB sticks, DPI."""
        self.map_drives()
        dpi = current_dpi()
        if dpi and self.state().get("dpi") != dpi:
            self.wine("reg", "add", r"HKCU\Control Panel\Desktop", "/v", "LogPixels",
                      "/t", "REG_DWORD", "/d", str(dpi), "/f", timeout=120)
            self.save_state(dpi=dpi)

    # ---- integration ----------------------------------------------------------
    def windows_user_dir(self) -> Path:
        return self.drive_c / "users" / getpass.getuser()

    def link_user_folders(self) -> None:
        """Point Documents, Downloads, Desktop... at the real Xenon folders."""
        base = self.windows_user_dir()
        if not base.is_dir():
            return
        for win_name, xdg_name in USER_FOLDERS.items():
            target = xdg_user_dir(xdg_name)
            if not target or target == Path.home():
                continue
            target.mkdir(parents=True, exist_ok=True)
            link = base / win_name
            if link.is_symlink():
                if Path(os.readlink(link)) == target:
                    continue
                link.unlink()
            elif link.is_dir():
                try:
                    link.rmdir()  # only replace empty placeholder folders
                except OSError:
                    continue
            elif link.exists():
                continue
            link.symlink_to(target)

    def map_drives(self) -> None:
        """C: is the managed Windows drive, Z: is the whole Linux filesystem,
        and removable media get D:, E:, ... automatically."""
        dd = self.path / "dosdevices"
        if not dd.is_dir():
            return
        _set_link(dd / "c:", "../drive_c")
        _set_link(dd / "z:", "/")
        mounts = removable_mounts()
        managed_file = self.path / ".xenon-drives.json"
        try:
            managed = json.loads(managed_file.read_text())
        except (OSError, ValueError):
            managed = {}
        # Drop letters for media that went away.
        for letter, target in list(managed.items()):
            if target not in mounts:
                link = dd / f"{letter}:"
                if link.is_symlink():
                    link.unlink()
                del managed[letter]
        used = {e[0] for e in os.listdir(dd) if len(e) == 2 and e.endswith(":")}
        for mount in mounts:
            if mount in managed.values():
                continue
            letter = next((l for l in "defghijklmnopqrstuvwxy" if l not in used), None)
            if letter is None:
                break
            _set_link(dd / f"{letter}:", mount)
            managed[letter] = mount
            used.add(letter)
        managed_file.write_text(json.dumps(managed, indent=1, sort_keys=True))


def _set_link(link: Path, target: str) -> None:
    if link.is_symlink() and os.readlink(link) == target:
        return
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(target)


def removable_mounts() -> list[str]:
    user = pwd.getpwuid(os.getuid()).pw_name
    found = []
    for base in (Path("/run/media") / user, Path("/media") / user):
        if base.is_dir():
            for entry in sorted(base.iterdir()):
                if entry.is_dir() and os.path.ismount(entry):
                    found.append(str(entry))
    return found


def xdg_user_dir(name: str) -> Path | None:
    if shutil.which("xdg-user-dir"):
        out = subprocess.run(["xdg-user-dir", name], capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    defaults = {"DESKTOP": "Desktop", "DOCUMENTS": "Documents", "DOWNLOAD": "Downloads",
                "MUSIC": "Music", "PICTURES": "Pictures", "VIDEOS": "Videos"}
    return Path.home() / defaults[name]


def current_dpi() -> int | None:
    """DPI for Windows programs, following the desktop's scale factor.

    GNOME publishes the scale for X11 clients as Xft.dpi; with Mutter's
    xwayland-native-scaling this gives sharp Windows apps on HiDPI screens."""
    override = os.environ.get("XWS_DPI")
    if override and override.isdigit():
        return int(override)
    if not os.environ.get("DISPLAY") or not shutil.which("xrdb"):
        return None
    try:
        out = subprocess.run(["xrdb", "-query"], capture_output=True, text=True,
                             timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"^Xft\.dpi:\s*(\d+)", out, re.M)
    if m:
        dpi = int(m.group(1))
        if 72 <= dpi <= 480:
            return dpi
    return None


def _payload_version(name: str) -> str | None:
    try:
        return (config.LIB_DIR / name / "VERSION").read_text().strip()
    except OSError:
        return None


def _addon_available(kind: str) -> bool:
    """Is the Wine Mono / Gecko installer present so Wine installs it silently?"""
    wine = config.find_wine()
    dirs = [Path("/usr/share/wine") / kind, Path("/opt/wine/") / kind]
    if wine:
        dirs.append(Path(wine).resolve().parent.parent / "share" / "wine" / kind)
    return any(d.is_dir() and any(d.iterdir()) for d in dirs)


def _has_casefold(directory: Path) -> bool:
    if not shutil.which("lsattr"):
        return False
    out = subprocess.run(["lsattr", "-d", str(directory)], capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        return False
    return "F" in out.stdout.split()[0]


def _reg_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def registry_defaults(settings: config.Settings) -> str:
    """The registry settings that make Wine behave like part of Xenon."""
    lines = ["Windows Registry Editor Version 5.00", ""]

    def key(name: str, values: dict[str, str]) -> None:
        lines.append(f"[{name}]")
        for k, v in values.items():
            lines.append(f"{_reg_str(k)}={v}")
        lines.append("")

    graphics = "wayland,x11" if settings.graphics_driver == "wayland" else "x11"
    key(r"HKEY_CURRENT_USER\Software\Wine\Drivers", {"Graphics": _reg_str(graphics)})
    # No scary Wine crash dialogs; XWS reports failures itself.
    key(r"HKEY_CURRENT_USER\Software\Wine\WineDbg", {"ShowCrashDialog": "dword:00000000"})
    # Programs' own file types get desktop associations.
    key(r"HKEY_CURRENT_USER\Software\Wine\FileOpenAssociations", {"Enable": _reg_str("Y")})
    key(r"HKEY_CURRENT_USER\Control Panel\Desktop", {
        "FontSmoothing": _reg_str("2"),
        "FontSmoothingType": "dword:00000002",
        "FontSmoothingGamma": "dword:00000578",
        "FontSmoothingOrientation": "dword:00000001",
    })
    key(r"HKEY_CURRENT_USER\Software\Wine\Fonts\Replacements",
        {k: _reg_str(v) for k, v in FONT_REPLACEMENTS.items()})
    overrides = {}
    for dll in DXVK_DLLS:
        overrides[dll] = _reg_str("native,builtin" if settings.dxvk else "builtin")
    for dll in VKD3D_DLLS:
        overrides[dll] = _reg_str("native,builtin" if settings.vkd3d_proton else "builtin")
    key(r"HKEY_CURRENT_USER\Software\Wine\DllOverrides", overrides)
    try:
        full_name = pwd.getpwuid(os.getuid()).pw_gecos.split(",")[0] or getpass.getuser()
    except KeyError:
        full_name = getpass.getuser()
    key(r"HKEY_LOCAL_MACHINE\Software\Microsoft\Windows NT\CurrentVersion", {
        "RegisteredOwner": _reg_str(full_name),
        "RegisteredOrganization": _reg_str(""),
    })
    return "\r\n".join(lines) + "\r\n"
