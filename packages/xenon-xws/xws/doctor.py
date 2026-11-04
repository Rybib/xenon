"""`xws doctor`: checks that every layer of Windows support is healthy."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from . import config, runtimes
from .prefix import Prefix, _payload_version

OK, WARN, FAIL = "ok", "warn", "fail"


@dataclass
class Check:
    id: str
    title: str
    status: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def _run(cmd: list[str], timeout: float = 15) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def wine_version() -> str | None:
    wine = config.find_wine()
    if not wine:
        return None
    out = _run([wine, "--version"]).strip()
    return out or None


def run_checks() -> list[Check]:
    checks: list[Check] = []

    ver = wine_version()
    if ver:
        m = re.search(r"wine-(\d+)\.(\d+)", ver)
        major = int(m.group(1)) if m else 0
        status = OK if major >= 10 else WARN
        detail = ver if status == OK else f"{ver} (Xenon expects Wine 10 or newer)"
        checks.append(Check("wine", "Windows runtime (Wine)", status, detail))
    else:
        checks.append(Check("wine", "Windows runtime (Wine)", FAIL, "Wine is not installed"))

    if os.path.exists("/dev/ntsync"):
        if os.access("/dev/ntsync", os.R_OK | os.W_OK):
            checks.append(Check("ntsync", "NT synchronization (NTSYNC)", OK,
                                "/dev/ntsync available: fast, accurate Windows sync"))
        else:
            checks.append(Check("ntsync", "NT synchronization (NTSYNC)", WARN,
                                "/dev/ntsync exists but is not accessible to you"))
    else:
        checks.append(Check("ntsync", "NT synchronization (NTSYNC)", WARN,
                            "kernel module not loaded (sudo modprobe ntsync); games "
                            "will fall back to slower synchronization"))

    binfmt = Path("/proc/sys/fs/binfmt_misc/xenon-pe")
    if binfmt.exists() and "enabled" in binfmt.read_text():
        checks.append(Check("binfmt", "Run .exe files directly", OK,
                            "registered with the kernel (binfmt_misc)"))
    else:
        checks.append(Check("binfmt", "Run .exe files directly", WARN,
                            "binfmt_misc handler not registered; double-click still works"))

    vk = _run(["vulkaninfo", "--summary"], timeout=20) if shutil.which("vulkaninfo") else ""
    gpus = re.findall(r"deviceName\s*=\s*(.+)", vk)
    if gpus:
        real = [g.strip() for g in gpus if "llvmpipe" not in g.lower()]
        if real:
            checks.append(Check("vulkan", "Vulkan graphics", OK, ", ".join(real)))
        else:
            checks.append(Check("vulkan", "Vulkan graphics", WARN,
                                "only software rendering (llvmpipe) found; "
                                "install your GPU driver in Xenon Settings"))
    else:
        checks.append(Check("vulkan", "Vulkan graphics", WARN if not vk else FAIL,
                            "could not query Vulkan (vulkan-tools missing or no GPU driver)"))

    for payload, title in (("dxvk", "DirectX 8-11 (DXVK)"),
                           ("vkd3d-proton", "DirectX 12 (VKD3D-Proton)")):
        v = _payload_version(payload)
        checks.append(Check(payload, title, OK if v else FAIL,
                            f"version {v}" if v else f"{config.LIB_DIR / payload} missing"))

    try:
        mmc = int(Path("/proc/sys/vm/max_map_count").read_text())
    except (OSError, ValueError):
        mmc = 0
    checks.append(Check("max_map_count", "Memory maps for large games",
                        OK if mmc >= 1048576 else WARN, f"vm.max_map_count = {mmc}"))

    checks.append(Check("winetricks", "Runtime installer",
                        OK if runtimes.winetricks_path() else WARN,
                        runtimes.winetricks_path() or "winetricks not found"))

    gm = shutil.which("gamemoderun")
    checks.append(Check("gamemode", "GameMode", OK if gm else WARN,
                        "available" if gm else "not installed"))

    main = Prefix.main()
    if main.exists():
        st = main.state()
        cf = "case-insensitive (casefold)" if st.get("casefold") else "standard"
        checks.append(Check("prefix", "Windows environment", OK,
                            f"{main.path} ({cf} C: drive, "
                            f"runtimes: {', '.join(st.get('runtimes', [])) or 'none yet'})"))
    else:
        checks.append(Check("prefix", "Windows environment", OK,
                            "not created yet; it is set up the first time you open a "
                            "Windows program"))
    return checks
