"""On-demand Windows runtimes (Visual C++, DirectX extras, .NET, fonts).

Runtimes are installed with winetricks, which downloads the official
redistributables from Microsoft at install time. Xenon never bundles
Microsoft redistributables, which keeps it license-compliant.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from . import config
from .pe import PEInfo

# DLL import (lowercase, regex) -> winetricks verb
IMPORT_RULES: list[tuple[str, str]] = [
    (r"^(msvcp140(_\d|_atomic_wait|_codecvt_ids)?|vcruntime140(_1)?|concrt140|vcomp140|vccorlib140)\.dll$",
     "vcrun2022"),
    (r"^(msvcr|msvcp|vcomp)120\.dll$", "vcrun2013"),
    (r"^(msvcr|msvcp|vcomp)110\.dll$", "vcrun2012"),
    (r"^(msvcr|msvcp|vcomp)100\.dll$", "vcrun2010"),
    (r"^(msvcr|msvcp|vcomp)90\.dll$", "vcrun2008"),
    (r"^(msvcr|msvcp|vcomp)80\.dll$", "vcrun2005"),
    (r"^d3dx9_\d+\.dll$", "d3dx9"),
    (r"^d3dx10(_\d+)?\.dll$", "d3dx10"),
    (r"^d3dx11_\d+\.dll$", "d3dx11_43"),
    (r"^d3dcompiler_43\.dll$", "d3dcompiler_43"),
    (r"^d3dcompiler_47\.dll$", "d3dcompiler_47"),
    (r"^xact(engine)?\d.*\.dll$", "xact"),
    (r"^physxloader\.dll$", "physx"),
]

# Shown in Xenon Settings.
DESCRIPTIONS = {
    "vcrun2022": "Microsoft Visual C++ 2015-2022 runtime",
    "vcrun2013": "Microsoft Visual C++ 2013 runtime",
    "vcrun2012": "Microsoft Visual C++ 2012 runtime",
    "vcrun2010": "Microsoft Visual C++ 2010 runtime",
    "vcrun2008": "Microsoft Visual C++ 2008 runtime",
    "vcrun2005": "Microsoft Visual C++ 2005 runtime",
    "d3dx9": "DirectX 9 extension libraries (d3dx9)",
    "d3dx10": "DirectX 10 extension libraries",
    "d3dx11_43": "DirectX 11 extension libraries",
    "d3dcompiler_43": "DirectX shader compiler (v43)",
    "d3dcompiler_47": "DirectX shader compiler (v47)",
    "xact": "XACT audio (older games)",
    "physx": "NVIDIA PhysX legacy runtime",
    "dotnet48": "Microsoft .NET Framework 4.8",
    "dotnetdesktop8": "Microsoft .NET 8 Desktop Runtime",
    "corefonts": "Microsoft core fonts (Arial, Times New Roman, ...)",
    "allfonts": "All freely redistributable fonts",
    "msxml6": "Microsoft XML Core Services 6",
    "gdiplus": "Native GDI+",
}

KNOWN = set(DESCRIPTIONS)


def detect(pe: PEInfo | None) -> list[str]:
    """Runtimes a program needs, judged from its import table."""
    if pe is None:
        return []
    needed: list[str] = []
    for dll in pe.imports_lower:
        for pattern, verb in IMPORT_RULES:
            if re.match(pattern, dll) and verb not in needed:
                needed.append(verb)
    return needed


def winetricks_path() -> str | None:
    bundled = config.LIB_DIR / "winetricks"
    if os.access(bundled, os.X_OK):
        return str(bundled)
    return shutil.which("winetricks")


def install(prefix, verbs: list[str], env: dict[str, str], log: Path) -> list[str]:
    """Install runtimes into `prefix`. Returns the verbs that failed."""
    tool = winetricks_path()
    if not tool:
        return list(verbs)
    failed = []
    run_env = dict(env)
    wine = config.find_wine()
    if wine:
        run_env["WINE"] = wine
        server = config.wine_tool("wineserver")
        if server:
            run_env["WINESERVER"] = server
    run_env["WINETRICKS_LATEST_VERSION_CHECK"] = "disabled"
    run_env.setdefault("WINEDEBUG", "-all")
    log.parent.mkdir(parents=True, exist_ok=True)
    for verb in verbs:
        with open(log, "a") as fh:
            fh.write(f"\n=== winetricks {verb} ===\n")
            fh.flush()
            rc = subprocess.run([tool, "--unattended", verb], env=run_env,
                                stdout=fh, stderr=subprocess.STDOUT).returncode
        if rc == 0:
            prefix.mark_runtime(verb)
        else:
            failed.append(verb)
    return failed
