"""Turn Windows Start Menu shortcuts into normal Xenon app entries.

Wine's winemenubuilder already converts Start Menu shortcuts into
freedesktop .desktop files (with extracted icons) under
~/.local/share/applications/wine/. XWS takes those as the source of truth
and generates clean entries in ~/.local/share/applications/xenon-windows/
that launch through XWS (so profiles, runtimes and drive mapping apply)
and hides the raw Wine entries. Uninstallers, readmes and web links are
left out of the app grid; uninstalling is done from Xenon Settings.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from . import config, winpath

WINE_EXEC_RE = re.compile(
    # The loader may be "wine", "wine64", "wine-stable" or a full path.
    r'^env\s+WINEPREFIX=(?P<q>"?)(?P<prefix>.+?)(?P=q)\s+(?:\S*/)?wine[\w.-]*\s+(?P<rest>.*)$')

SKIP_NAME_RE = re.compile(
    r"(^|\b)(uninstall|uninst|deinstall|remove|readme|read me|release notes|"
    r"license|licence|eula|manual|documentation|user guide|help|website|"
    r"web site|homepage|on the web|support|register)(\b|$)", re.I)

GENERATED_DIRNAME = "xenon-windows"
MARK = "X-Xenon-Generated"


def parse_desktop(text: str) -> dict[str, str]:
    """Parse the [Desktop Entry] group, keeping raw (escaped) values."""
    entry: dict[str, str] = {}
    in_group = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            in_group = s == "[Desktop Entry]"
            continue
        if not in_group or not s or s.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        entry[k.strip()] = v.strip()
    return entry


def rewrite_exec(exec_line: str) -> str | None:
    """`env WINEPREFIX="/p" wine ARGS` -> `xws exec --prefix "/p" -- ARGS`."""
    m = WINE_EXEC_RE.match(exec_line.strip())
    if not m:
        return None
    return f'xws exec --prefix "{m.group("prefix")}" -- {m.group("rest")}'


def shortcut_of(exec_line: str) -> tuple[Path, str] | None:
    """(prefix, Windows path of the .lnk) that a Wine menu entry starts."""
    m = WINE_EXEC_RE.match(exec_line.strip())
    if not m:
        return None
    try:
        # Undo desktop-entry escaping (\\\\ -> \\), then shell-style quoting.
        args = shlex.split(m.group("rest").replace("\\\\", "\\"))
    except ValueError:
        return None
    if args and args[0].lower() == "start":
        args = [a for a in args[1:] if not a.startswith("/")]
    if not args or not args[0].lower().endswith(".lnk"):
        return None
    return Path(m.group("prefix")), args[0]


def is_stale(entry: dict[str, str]) -> bool:
    """Wine never deletes menu entries when an uninstaller removes the
    shortcut, so check that the shortcut still exists."""
    found = shortcut_of(entry.get("Exec", ""))
    if not found:
        return False
    prefix, win = found
    if not (prefix / "dosdevices").is_dir():
        return True  # environment was deleted
    unix = winpath.to_unix(prefix, win)
    return unix is not None and not unix.exists()


def should_skip(entry: dict[str, str]) -> bool:
    name = entry.get("Name", "")
    exec_line = entry.get("Exec", "")
    if SKIP_NAME_RE.search(name):
        return True
    low = exec_line.lower()
    if ".url" in low or "http://" in low or "https://" in low:
        return True
    return False


def _slug(rel: Path) -> str:
    s = "-".join(rel.with_suffix("").parts)
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_-.")
    return s[:120] or "app"


def _hide_original(path: Path, text: str) -> None:
    if re.search(r"^NoDisplay=true\s*$", text, re.M):
        return
    lines = text.splitlines()
    out = []
    inserted = False
    for line in lines:
        if line.strip().startswith("NoDisplay="):
            continue
        out.append(line)
        if line.strip() == "[Desktop Entry]" and not inserted:
            out.append("NoDisplay=true")
            inserted = True
    path.write_text("\n".join(out) + "\n")


def _rewrite_in_place(path: Path) -> bool:
    """For association/desktop-shortcut files: swap the Exec line only."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return False
    changed = False
    out = []
    for line in text.splitlines():
        if line.startswith("Exec="):
            new = rewrite_exec(line[5:])
            if new:
                line = "Exec=" + new
                changed = True
        out.append(line)
    if changed:
        path.write_text("\n".join(out) + "\n")
    return changed


def sync(apps_dir: Path | None = None, desktop_dir: Path | None = None) -> dict[str, int]:
    apps_dir = apps_dir or config.APPLICATIONS_DIR
    source_root = apps_dir / "wine"
    out_dir = apps_dir / GENERATED_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)
    stats = {"added": 0, "updated": 0, "removed": 0, "skipped": 0, "associations": 0}

    wanted: dict[str, str] = {}
    if source_root.is_dir():
        for src in sorted(source_root.rglob("*.desktop")):
            try:
                text = src.read_text(errors="replace")
            except OSError:
                continue
            entry = parse_desktop(text)
            if is_stale(entry):
                src.unlink()
                continue
            new_exec = rewrite_exec(entry.get("Exec", ""))
            _hide_original(src, text)
            if not new_exec or should_skip(entry):
                stats["skipped"] += 1
                continue
            m = WINE_EXEC_RE.match(entry["Exec"])
            lines = [
                "[Desktop Entry]",
                "Type=Application",
                f"Name={entry.get('Name', src.stem)}",
                f"Exec={new_exec}",
                f"Comment={entry.get('Comment', 'Windows application')}",
                "Categories=X-Windows-App;",
                "StartupNotify=true",
            ]
            for key in ("Icon", "StartupWMClass", "Path", "GenericName", "Keywords"):
                if entry.get(key):
                    lines.append(f"{key}={entry[key]}")
            lines += [
                f"{MARK}=true",
                f"X-Xenon-Source={src}",
                f"X-Xenon-Prefix={m.group('prefix') if m else ''}",
            ]
            wanted[_slug(src.relative_to(source_root)) + ".desktop"] = "\n".join(lines) + "\n"

    for name, content in wanted.items():
        target = out_dir / name
        old = target.read_text() if target.exists() else None
        if old != content:
            tmp = target.with_suffix(".tmp")
            tmp.write_text(content)
            tmp.replace(target)
            stats["updated" if old is not None else "added"] += 1

    for existing in out_dir.glob("*.desktop"):
        if existing.name not in wanted:
            existing.unlink()
            stats["removed"] += 1

    # File associations and URL handlers Wine registered for Windows programs.
    for path in list(apps_dir.glob("wine-extension-*.desktop")) + \
            list(apps_dir.glob("wine-protocol-*.desktop")):
        if _rewrite_in_place(path):
            stats["associations"] += 1

    # Shortcuts installers drop on the Windows desktop (= the Xenon Desktop).
    if desktop_dir and desktop_dir.is_dir():
        for path in desktop_dir.glob("*.desktop"):
            _rewrite_in_place(path)

    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", "-q", str(apps_dir)], check=False,
                       stderr=subprocess.DEVNULL)
    return stats


def entries_for_prefix(prefix_path: Path, apps_dir: Path | None = None) -> list[Path]:
    apps_dir = apps_dir or config.APPLICATIONS_DIR
    out = []
    want = os.path.realpath(prefix_path)
    for path in (apps_dir / GENERATED_DIRNAME).glob("*.desktop"):
        entry = parse_desktop(path.read_text(errors="replace"))
        if os.path.realpath(entry.get("X-Xenon-Prefix", "")) == want:
            out.append(path)
    return out
