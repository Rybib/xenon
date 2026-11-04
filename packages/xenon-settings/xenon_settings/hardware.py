"""Hardware detection for the Welcome app's hardware check and the
Graphics page. Reads /sys and /proc directly; needs no root."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SYS = Path(os.environ.get("XENON_SYSFS", "/sys"))
PROC = Path(os.environ.get("XENON_PROCFS", "/proc"))

VENDORS = {"0x10de": "NVIDIA", "0x1002": "AMD", "0x1022": "AMD", "0x8086": "Intel",
           "0x1af4": "Virtio", "0x15ad": "VMware", "0x80ee": "VirtualBox",
           "0x1234": "QEMU", "0x1b36": "QEMU"}


@dataclass
class Device:
    kind: str           # gpu, network, audio, bluetooth
    name: str
    vendor: str
    driver: str | None
    slot: str = ""
    status: str = "ok"  # ok, warn, fail
    detail: str = ""
    actions: list[str] = field(default_factory=list)  # e.g. ["nvidia-open"]


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _lspci_names() -> dict[str, str]:
    if not shutil.which("lspci"):
        return {}
    try:
        out = subprocess.run(["lspci", "-mm"], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    names = {}
    for line in out.splitlines():
        parts = re.findall(r'"([^"]*)"|(\S+)', line)
        fields = [a or b for a, b in parts]
        if len(fields) >= 4:
            names[fields[0]] = f"{fields[2]} {fields[3]}".strip()
    return names


def pci_devices() -> list[tuple[str, str, str, str | None]]:
    """(slot, class, vendor_id, driver) for every PCI device."""
    out = []
    base = SYS / "bus" / "pci" / "devices"
    if not base.is_dir():
        return out
    for dev in sorted(base.iterdir()):
        drv = dev / "driver"
        driver = os.path.basename(os.readlink(drv)) if drv.is_symlink() else None
        out.append((dev.name, _read(dev / "class"), _read(dev / "vendor"), driver))
    return out


NVIDIA_OPEN_RE = re.compile(r"\b(RTX|GTX 16\d\d|MX[45]\d\d|T\d{3,4}|A\d{2,4}|L\d{1,2}|H\d{2,3})\b")


def nvidia_recommendation(name: str) -> str:
    """NVIDIA's open kernel modules support Turing (GTX 16xx/RTX 20xx) and
    newer; older cards need the proprietary module."""
    return "nvidia-open" if NVIDIA_OPEN_RE.search(name) else "nvidia"


def gpus() -> list[Device]:
    names = _lspci_names()
    found = []
    for slot, cls, vendor, driver in pci_devices():
        if not cls.startswith("0x03"):
            continue
        short = slot.split(":", 1)[1] if slot.count(":") == 2 else slot
        name = names.get(short, names.get(slot, "Graphics adapter"))
        vname = VENDORS.get(vendor, "Unknown")
        dev = Device("gpu", name, vname, driver, slot)
        if driver is None:
            dev.status, dev.detail = "fail", "No driver is loaded for this graphics card."
        elif vname == "NVIDIA" and driver == "nouveau":
            dev.status = "warn"
            dev.detail = ("Using the basic open-source driver. Install the NVIDIA "
                          "driver for full gaming performance.")
            dev.actions = [nvidia_recommendation(name)]
        elif vname == "NVIDIA" and driver == "nvidia":
            dev.detail = "NVIDIA driver installed."
        elif vname in ("AMD", "Intel"):
            dev.detail = f"Open-source {vname} driver ({driver}) with Vulkan via Mesa."
        else:
            dev.detail = f"Driver: {driver}"
        found.append(dev)
    return found


def network() -> list[Device]:
    found = []
    base = SYS / "class" / "net"
    names = _lspci_names()
    bound_slots = set()
    if base.is_dir():
        for iface in sorted(base.iterdir()):
            if iface.name == "lo" or not (iface / "device").exists():
                continue
            drv = iface / "device" / "driver"
            driver = os.path.basename(os.readlink(drv)) if drv.is_symlink() else None
            wireless = (iface / "wireless").exists() or (iface / "phy80211").exists()
            slot = os.path.basename(os.path.realpath(iface / "device"))
            bound_slots.add(slot)
            short = slot.split(":", 1)[1] if slot.count(":") == 2 else slot
            label = "Wi-Fi" if wireless else "Ethernet"
            found.append(Device("network", names.get(short, f"{label} ({iface.name})"),
                                label, driver, slot,
                                detail=f"{label} adapter {iface.name}, driver {driver}"))
    for slot, cls, vendor, driver in pci_devices():
        if cls.startswith("0x02") and driver is None and slot not in bound_slots:
            short = slot.split(":", 1)[1]
            found.append(Device("network", names.get(short, "Network controller"),
                                VENDORS.get(vendor, ""), None, slot, "fail",
                                "No driver or firmware for this network adapter."))
    return found


def audio() -> list[Device]:
    cards = _read(PROC / "asound" / "cards")
    found = []
    for m in re.finditer(r"^\s*\d+\s+\[[^\]]*\]:\s*(\S+)\s+-\s+(.+)$", cards, re.M):
        found.append(Device("audio", m.group(2).strip(), "", m.group(1),
                            detail=f"Driver {m.group(1)}"))
    return found


def bluetooth() -> list[Device]:
    base = SYS / "class" / "bluetooth"
    if not base.is_dir():
        return []
    return [Device("bluetooth", d.name, "", None, detail="Bluetooth adapter")
            for d in sorted(base.iterdir()) if re.fullmatch(r"hci\d+", d.name)]


def secure_boot() -> bool | None:
    efivars = SYS / "firmware" / "efi" / "efivars"
    if not efivars.is_dir():
        return None
    for f in efivars.glob("SecureBoot-*"):
        try:
            return f.read_bytes()[-1] == 1
        except OSError:
            return None
    return None


def memory_gib() -> float:
    m = re.search(r"MemTotal:\s+(\d+)", _read(PROC / "meminfo"))
    return int(m.group(1)) / 1048576 if m else 0.0


def cpu_name() -> str:
    m = re.search(r"model name\s*:\s*(.+)", _read(PROC / "cpuinfo"))
    return m.group(1).strip() if m else "Unknown processor"


def summary() -> dict[str, list[Device]]:
    return {"gpu": gpus(), "network": network(), "audio": audio(),
            "bluetooth": bluetooth()}
