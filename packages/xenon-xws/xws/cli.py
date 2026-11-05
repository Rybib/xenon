"""xws: the Xenon Windows Subsystem command-line tool.

Most people never type these commands: double-clicking a Windows program
runs `xws run`, and Xenon Settings uses `xws apps --json` and friends.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import (__version__, apps, compat, config, doctor, launcher, menu, pe,
               runtimes, snapshots, ui)
from .prefix import Prefix, PrefixError


def _prefix_arg(value: str | None) -> Prefix | None:
    if not value:
        return None
    if "/" in value:
        return Prefix.from_path(value)
    return Prefix.main() if value == "main" else Prefix.isolated(value)


def cmd_run(a) -> int:
    settings = config.Settings.load()
    if a.debug:
        import os
        os.environ["WINEDEBUG"] = "err+all,fixme-all"
    try:
        plan = launcher.plan_file(Path(a.file), a.args, settings, _prefix_arg(a.prefix))
    except FileNotFoundError:
        ui.error("File not found", a.file)
        return 2
    except ValueError as exc:
        ui.error("Can't open this file", str(exc))
        return 2
    return launcher.execute(plan, settings, wait=not a.no_wait)


def cmd_exec(a) -> int:
    settings = config.Settings.load()
    args = a.args[1:] if a.args and a.args[0] == "--" else a.args
    if not args:
        print("xws exec: nothing to run", file=sys.stderr)
        return 2
    plan = launcher.plan_raw(args, settings, _prefix_arg(a.prefix))
    return launcher.execute(plan, settings)


def cmd_init(a) -> int:
    settings = config.Settings.load()
    prefix = _prefix_arg(a.prefix) or Prefix.main()
    try:
        prefix.ensure(settings)
    except PrefixError as exc:
        print(f"xws: {exc}", file=sys.stderr)
        return 1
    print(f"Windows environment ready at {prefix.path}")
    return 0


def cmd_doctor(a) -> int:
    checks = doctor.run_checks()
    if a.json:
        print(json.dumps([c.to_dict() for c in checks], indent=2))
    else:
        icons = {"ok": "✔", "warn": "!", "fail": "✘"}
        for c in checks:
            print(f" {icons[c.status]} {c.title:<34} {c.detail}")
    return 1 if any(c.status == "fail" for c in checks) else 0


def cmd_apps(a) -> int:
    found = apps.list_apps(include_runtimes=a.all)
    if a.json:
        print(json.dumps([x.to_dict() for x in found], indent=2))
        return 0
    if not found:
        print("No Windows apps installed yet. Download an installer (.exe or .msi) "
              "and double-click it.")
        return 0
    for x in found:
        extra = f" [{x.environment}]" if x.environment != "main" else ""
        print(f"{x.name:<40} {x.version:<16} {x.publisher}{extra}")
        print(f"    id: {x.id}")
    return 0


def cmd_uninstall(a) -> int:
    hit = apps.find(a.app)
    if not hit:
        print(f"xws: no installed app {a.app!r} (see `xws apps`)", file=sys.stderr)
        return 1
    app, prefix = hit
    try:
        wine_args = apps.uninstall_command(app)
    except ValueError as exc:
        ui.error("Can't uninstall", str(exc))
        return 1
    settings = config.Settings.load()
    snapshots.create(prefix, reason=f"before uninstalling {app.name}",
                     keep=settings.snapshot_keep)
    plan = launcher.plan_raw(wine_args, settings, prefix)
    plan.installer = True  # wait for children, then refresh menus
    rc = launcher.execute(plan, settings)
    still = any(x.id == app.id for x in apps.list_apps([prefix], include_runtimes=True))
    if still:
        print(f"{app.name} is still installed (the uninstaller was cancelled or failed).")
        return 1 if rc == 0 else rc
    print(f"Uninstalled {app.name}.")
    if prefix.name != "main" and not apps.environment_in_use(prefix):
        print(f"The isolated environment '{prefix.name}' is now empty; remove it with "
              f"`xws reset --prefix {prefix.name}`.")
    return 0


def cmd_sync_menu(a) -> int:
    prefix = _prefix_arg(a.prefix)
    if a.wait and prefix:
        prefix.wait_server(timeout=24 * 3600)
    stats = menu.sync(desktop_dir=launcher._desktop_dir())
    if not a.quiet:
        print(", ".join(f"{k}: {v}" for k, v in stats.items()))
    return 0


def cmd_snapshot(a) -> int:
    prefix = _prefix_arg(a.prefix) or Prefix.main()
    if a.action == "create":
        dest = snapshots.create(prefix, reason="manual")
        print(dest or "No Windows environment yet.")
    elif a.action == "list":
        for name, reason in snapshots.list_snapshots(prefix):
            print(f"{name}  {reason}")
    elif a.action == "restore":
        if not a.name:
            print("xws snapshot restore NAME", file=sys.stderr)
            return 2
        snapshots.restore(prefix, a.name)
        print(f"Restored registry snapshot {a.name}.")
    return 0


def cmd_runtime(a) -> int:
    prefix = _prefix_arg(a.prefix) or Prefix.main()
    if a.action == "list":
        have = set(prefix.installed_runtimes())
        for verb, desc in sorted(runtimes.DESCRIPTIONS.items()):
            mark = "installed" if verb in have else ""
            print(f"{verb:<16} {desc:<52} {mark}")
        return 0
    settings = config.Settings.load()
    prefix.ensure(settings)
    bad = [v for v in a.verbs if v not in runtimes.KNOWN]
    if bad:
        print(f"xws: unknown runtime(s): {', '.join(bad)}", file=sys.stderr)
        return 2
    failed = runtimes.install(prefix, a.verbs, prefix.base_env(),
                              config.LOG_DIR / f"runtimes-{prefix.name}.log")
    if failed:
        print(f"Failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


def cmd_inspect(a) -> int:
    path = Path(a.file)
    kind = launcher.classify(path)
    out: dict = {"file": str(path), "kind": kind}
    info = None
    if kind == "exe":
        try:
            info = pe.parse(path)
            out.update(bits=info.bits, gui=info.is_gui, dotnet=info.is_dotnet,
                       imports=info.imports, version=info.version)
        except pe.PEError as exc:
            out["error"] = str(exc)
    prof = compat.find_profile(path, info)
    out["profile"] = prof.id if prof else None
    out["runtimes"] = runtimes.detect(info)
    out["installer"] = launcher.looks_like_installer(path, info, kind)
    out["game"] = launcher.looks_like_game(info)
    print(json.dumps(out, indent=2))
    return 0


def cmd_profiles(a) -> int:
    profiles = compat.load_profiles()
    if a.json:
        print(json.dumps([{"id": p.id, "name": p.name, "rating": p.rating,
                           "notes": p.notes, "isolated": p.isolated,
                           "runtimes": p.runtimes, "source": p.source}
                          for p in profiles], indent=2))
    else:
        for p in profiles:
            print(f"{p.name:<36} {p.rating:<9} {p.id}")
    return 0


def cmd_config(a) -> int:
    settings = config.Settings.load()
    if a.key is None:
        for k in settings.__dataclass_fields__:
            print(f"{k} = {getattr(settings, k)!r}")
        return 0
    if a.value is None:
        print(getattr(settings, a.key))
        return 0
    current = getattr(settings, a.key)
    value: object = a.value
    if isinstance(current, bool):
        value = a.value.lower() in ("1", "true", "yes", "on")
    elif isinstance(current, int):
        value = int(a.value)
    config.write_user_setting(a.key, value)
    # Settings that live in the registry are re-applied on next launch.
    for p in Prefix.all():
        p.save_state(layout=0)
    return 0


def cmd_frames(a) -> int:
    from . import frames
    return frames.run(idle_exit=a.idle_exit)


def cmd_kill(a) -> int:
    for p in Prefix.all():
        p.kill()
    return 0


def cmd_reset(a) -> int:
    import shutil
    prefix = _prefix_arg(a.prefix) or Prefix.main()
    if not a.yes:
        print(f"This deletes {prefix.path} and every Windows app installed in it. "
              "Re-run with --yes to confirm.")
        return 1
    prefix.kill()
    shutil.rmtree(prefix.path, ignore_errors=True)
    menu.sync()
    print(f"Removed {prefix.path}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="xws", description="Xenon Windows Subsystem")
    p.add_argument("--version", action="version", version=f"xws {__version__}")
    p.add_argument("--no-gui", action="store_true", help="never show dialogs")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("run", help="run a Windows program, installer or shortcut")
    s.add_argument("file")
    s.add_argument("args", nargs=argparse.REMAINDER)
    s.add_argument("--prefix", help="environment: main, an isolated id, or a path")
    s.add_argument("--no-wait", action="store_true")
    s.add_argument("--debug", action="store_true", help="verbose Wine logging")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("exec", help="run raw Wine arguments (used by app entries)")
    s.add_argument("--prefix")
    s.add_argument("args", nargs=argparse.REMAINDER)
    s.set_defaults(func=cmd_exec)

    s = sub.add_parser("init", help="create or update the Windows environment")
    s.add_argument("--prefix")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("doctor", help="check Windows support health")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("apps", help="list installed Windows apps")
    s.add_argument("--json", action="store_true")
    s.add_argument("--all", action="store_true", help="include runtimes")
    s.set_defaults(func=cmd_apps)

    s = sub.add_parser("uninstall", help="uninstall a Windows app")
    s.add_argument("app", help="app id or name from `xws apps`")
    s.set_defaults(func=cmd_uninstall)

    s = sub.add_parser("sync-menu", help="refresh app grid entries for Windows apps")
    s.add_argument("--prefix")
    s.add_argument("--wait", action="store_true", help="wait for programs to exit first")
    s.add_argument("--quiet", action="store_true")
    s.set_defaults(func=cmd_sync_menu)

    s = sub.add_parser("snapshot", help="registry snapshots")
    s.add_argument("action", choices=["create", "list", "restore"])
    s.add_argument("name", nargs="?")
    s.add_argument("--prefix")
    s.set_defaults(func=cmd_snapshot)

    s = sub.add_parser("runtime", help="list or install Windows runtimes")
    s.add_argument("action", choices=["list", "install"])
    s.add_argument("verbs", nargs="*")
    s.add_argument("--prefix")
    s.set_defaults(func=cmd_runtime)

    s = sub.add_parser("inspect", help="show what XWS knows about a Windows file")
    s.add_argument("file")
    s.set_defaults(func=cmd_inspect)

    s = sub.add_parser("profiles", help="list compatibility profiles")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_profiles)

    s = sub.add_parser("config", help="show or change XWS settings")
    s.add_argument("key", nargs="?", choices=list(config.Settings.__dataclass_fields__))
    s.add_argument("value", nargs="?")
    s.set_defaults(func=cmd_config)

    s = sub.add_parser("frames", help="keep one title bar per window on GNOME (helper)")
    s.add_argument("--idle-exit", type=float, default=60.0,
                   help="exit after this many seconds without Windows programs")
    s.set_defaults(func=cmd_frames)

    s = sub.add_parser("kill", help="stop all running Windows programs")
    s.set_defaults(func=cmd_kill)

    s = sub.add_parser("reset", help="delete a Windows environment")
    s.add_argument("--prefix")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_reset)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.no_gui:
        ui.set_text_mode(True)
    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        return 130
