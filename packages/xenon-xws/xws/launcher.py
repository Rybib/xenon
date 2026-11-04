"""Launching Windows programs: what happens when you double-click an .exe.

1. Work out what the file is (program, installer, MSI package, shortcut).
2. Read its headers: architecture, imported DLLs, version info.
3. Look up a compatibility profile; pick the main or an isolated environment.
4. Create/update the environment if needed; install missing runtimes.
5. Snapshot the registry if it is an installer.
6. Run it (under GameMode for games), log output, and report failures.
7. After installers finish, refresh the app grid from the Start Menu.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import compat, config, lnk, menu, pe, runtimes, snapshots, ui, winpath
from .prefix import DXVK_DLLS, VKD3D_DLLS, Prefix, PrefixError

GAME_DLLS = {"d3d8.dll", "d3d9.dll", "d3d10.dll", "d3d10_1.dll", "d3d10core.dll",
             "d3d11.dll", "d3d12.dll", "dxgi.dll", "ddraw.dll", "vulkan-1.dll",
             "xinput1_3.dll", "xinput1_4.dll", "xinput9_1_0.dll", "steam_api.dll",
             "steam_api64.dll", "eossdk-win64-shipping.dll", "eossdk-win32-shipping.dll"}
INSTALLER_HINTS = re.compile(r"(setup|install|installer|unins|update|patch|"
                             r"redist|vc_?redist|bootstrap)", re.I)
INSTALLER_VERSION_HINTS = re.compile(r"(setup|install|installer|nullsoft|inno)", re.I)


@dataclass
class LaunchPlan:
    target: Path | None             # Linux path of the file being started, if known
    wine_args: list[str]
    kind: str                       # exe, msi, lnk, bat, raw
    pe: pe.PEInfo | None = None
    profile: compat.Profile | None = None
    prefix: Prefix | None = None
    installer: bool = False
    game: bool = False
    runtimes: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    wrappers: list[str] = field(default_factory=list)
    cwd: str | None = None


def classify(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".lnk":
        return "lnk"
    if suffix in (".bat", ".cmd"):
        return "bat"
    kind = pe.file_kind(path)
    if kind == "msi" or suffix in (".msi", ".msp"):
        return "msi"
    if kind == "pe":
        return "exe"
    return "unknown"


def looks_like_installer(path: Path, info: pe.PEInfo | None, kind: str) -> bool:
    if kind == "msi":
        return True
    if INSTALLER_HINTS.search(path.stem):
        return True
    if info and info.version:
        text = " ".join(info.version.get(k, "") for k in
                        ("FileDescription", "ProductName", "Comments", "InternalName"))
        if INSTALLER_VERSION_HINTS.search(text):
            return True
    return False


def looks_like_game(info: pe.PEInfo | None) -> bool:
    return bool(info and info.imports_lower & GAME_DLLS)


def plan_file(path: Path, args: list[str], settings: config.Settings,
              prefix: Prefix | None = None) -> LaunchPlan:
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    kind = classify(path)
    analysis_target = path
    cwd = None
    if kind == "lnk":
        wine_args = ["start", "/wait", "/unix", str(path), *args]
        resolved = resolve_shortcut(path, prefix.path if prefix else config.MAIN_PREFIX)
        if resolved:
            analysis_target, wine_args, cwd = resolved
            wine_args = wine_args + list(args)
    elif kind == "msi":
        wine_args = ["msiexec", "/i", str(path), *args]
    elif kind == "bat":
        wine_args = ["cmd", "/c", str(path), *args]
    elif kind == "exe":
        wine_args = [str(path), *args]
    else:
        raise ValueError(f"{path.name} is not a Windows program")
    plan = _finish_plan(analysis_target, wine_args, kind, settings, prefix)
    plan.cwd = cwd
    return plan


def resolve_shortcut(path: Path, prefix_path: Path
                     ) -> tuple[Path, list[str], str | None] | None:
    """Open a .lnk ourselves: run its target directly with its arguments and
    working folder. (Wine's start.exe returns misleading exit codes for
    shortcuts, and resolving here lets profiles match the real program.)"""
    try:
        link = lnk.parse(path)
    except (lnk.LnkError, OSError):
        return None
    if not link.target:
        return None
    target = winpath.to_unix(prefix_path, link.target)
    if not target or not target.is_file():
        return None
    cwd = None
    if link.working_dir:
        wd = winpath.to_unix(prefix_path, link.working_dir)
        cwd = str(wd) if wd and wd.is_dir() else None
    args = winpath.split_command_line(link.arguments) if link.arguments else []
    return target, [str(target), *args], cwd or str(target.parent)


def plan_raw(wine_args: list[str], settings: config.Settings,
             prefix: Prefix | None) -> LaunchPlan:
    """`xws exec`: Wine-style arguments from menu entries and associations,
    e.g. ['C:\\\\ProgramData\\\\...\\\\App.lnk'] or ['start', '/ProgIDOpen', ...]."""
    base = prefix or Prefix.main()
    target = None
    cwd = None
    if wine_args and not wine_args[0].startswith("/") and wine_args[0].lower() != "start":
        target = winpath.to_unix(base.path, wine_args[0])
    if target and target.suffix.lower() == ".lnk" and target.exists():
        resolved = resolve_shortcut(target, base.path)
        if resolved:
            target, new_args, cwd = resolved
            wine_args = new_args + wine_args[1:]
    plan = _finish_plan(target if target and target.exists() else None,
                        wine_args, "raw", settings, prefix)
    plan.cwd = cwd
    return plan


def _finish_plan(target: Path | None, wine_args: list[str], kind: str,
                 settings: config.Settings, prefix: Prefix | None) -> LaunchPlan:
    info = None
    if target is not None and target.suffix.lower() not in (".msi", ".lnk", ".bat", ".cmd"):
        try:
            info = pe.parse(target)
        except (pe.PEError, OSError):
            info = None
    profile = None
    if settings.compat_profiles and target is not None:
        profile = compat.find_profile(target, info)

    if prefix is None:
        prefix = Prefix.isolated(profile.id) if profile and profile.isolated else Prefix.main()

    plan = LaunchPlan(target=target, wine_args=wine_args, kind=kind, pe=info,
                      profile=profile, prefix=prefix)
    plan.installer = kind != "raw" and target is not None and \
        looks_like_installer(target, info, kind)
    plan.game = profile.game if profile and profile.game is not None else looks_like_game(info)

    needed = []
    if settings.auto_runtimes:
        needed += runtimes.detect(info)
    if profile:
        needed += [r for r in profile.runtimes if r not in needed]
    plan.runtimes = needed

    env = prefix.base_env()
    env.update(settings.env)
    overrides = []
    use_dxvk = profile.dxvk if profile and profile.dxvk is not None else settings.dxvk
    use_vkd3d = (profile.vkd3d_proton if profile and profile.vkd3d_proton is not None
                 else settings.vkd3d_proton)
    if not use_dxvk:
        overrides.append(",".join(DXVK_DLLS) + "=b")
    if not use_vkd3d:
        overrides.append(",".join(VKD3D_DLLS) + "=b")
    if profile:
        env.update(profile.env)
        overrides += [f"{dll}={mode}" for dll, mode in profile.dll_overrides.items()]
        if profile.args and kind in ("exe", "lnk"):
            plan.wine_args = plan.wine_args + list(profile.args)
    if overrides:
        existing = env.get("WINEDLLOVERRIDES")
        env["WINEDLLOVERRIDES"] = ";".join(([existing] if existing else []) + overrides)
    if plan.game and settings.mangohud:
        env["MANGOHUD"] = "1"
    plan.env = env
    if plan.game and settings.gamemode and shutil.which("gamemoderun"):
        plan.wrappers = ["gamemoderun"]
    return plan


def execute(plan: LaunchPlan, settings: config.Settings, wait: bool = True) -> int:
    prefix = plan.prefix
    assert prefix is not None
    wine = config.find_wine()
    if not wine:
        ui.error("Windows support is not installed",
                 "The Xenon Windows Subsystem could not find Wine. Reinstall the "
                 "'xenon-xws' package from Software.")
        return 127
    try:
        prefix.ensure(settings)
    except PrefixError as exc:
        ui.error("Windows support could not be set up", str(exc))
        return 1

    if plan.profile and plan.profile.windows_version:
        prefix.wine("winecfg", "-v", plan.profile.windows_version, env=plan.env, timeout=120)

    missing = [r for r in plan.runtimes if r not in prefix.installed_runtimes()]
    if missing:
        log = config.LOG_DIR / f"runtimes-{prefix.name}.log"
        names = ", ".join(runtimes.DESCRIPTIONS.get(r, r) for r in missing)
        with ui.progress("Installing components", f"Installing {names}..."):
            failed = runtimes.install(prefix, missing, plan.env, log)
        if failed:
            ui.notify("Some components could not be installed",
                      f"{', '.join(failed)} (offline?). The program will start anyway.")

    if plan.installer:
        snapshots.create(prefix, reason=f"before {plan.target.name if plan.target else 'install'}",
                         keep=settings.snapshot_keep)

    name = plan.target.name if plan.target else "program"
    log_path = config.LOG_DIR / f"{_safe(name)}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [*plan.wrappers, wine, *plan.wine_args]
    cwd = plan.cwd or (str(plan.target.parent)
                       if plan.target and plan.target.parent.is_dir() else None)

    started = time.monotonic()
    with open(log_path, "w") as log:
        log.write(f"$ {winpath.shell_quote(cmd)}\n")
        if plan.profile:
            log.write(f"# compatibility profile: {plan.profile.id} ({plan.profile.source})\n")
        log.flush()
        proc = subprocess.Popen(cmd, env=plan.env, cwd=cwd, stdout=log,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        if not wait:
            return 0
        rc = proc.wait()
    elapsed = time.monotonic() - started

    if plan.installer or plan.kind == "msi":
        # Installers often hand off to child processes; let them finish,
        # then publish the new Start Menu entries.
        prefix.wait_server(timeout=600)
        stats = menu.sync(desktop_dir=_desktop_dir())
        if stats["added"]:
            ui.notify("App installed",
                      f"{stats['added']} new app{'s' if stats['added'] != 1 else ''} "
                      "added to your app grid.")
    else:
        # Programs can install shortcuts too (e.g. Steam games); refresh in
        # the background without blocking.
        _spawn_background_sync(prefix)

    if rc not in (0,) and elapsed < 10 and not plan.installer:
        ui.error(f"{name} stopped unexpectedly",
                 f"It exited with code {rc}. Details were saved to:\n{log_path}\n\n"
                 "Check the Xenon compatibility list for known fixes.")
    return rc


def _desktop_dir() -> Path | None:
    from .prefix import xdg_user_dir
    d = xdg_user_dir("DESKTOP")
    return d if d and d != Path.home() else None


def _spawn_background_sync(prefix: Prefix) -> None:
    try:
        subprocess.Popen([sys.executable, "-m", "xws", "sync-menu", "--wait",
                          "--prefix", str(prefix.path)],
                         env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent)},
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:80] or "program"
