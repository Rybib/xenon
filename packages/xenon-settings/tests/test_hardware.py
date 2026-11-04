"""Hardware detection against a fake /sys tree. No GTK needed."""

import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def make_pci(root: Path, slot: str, cls: str, vendor: str, driver: str | None):
    dev = root / "bus" / "pci" / "devices" / slot
    dev.mkdir(parents=True)
    (dev / "class").write_text(cls + "\n")
    (dev / "vendor").write_text(vendor + "\n")
    if driver:
        drv = root / "bus" / "pci" / "drivers" / driver
        drv.mkdir(parents=True, exist_ok=True)
        (dev / "driver").symlink_to(drv)


def load(tmp_path, monkeypatch):
    monkeypatch.setenv("XENON_SYSFS", str(tmp_path / "sys"))
    monkeypatch.setenv("XENON_PROCFS", str(tmp_path / "proc"))
    monkeypatch.setenv("PATH", "/nonexistent")  # no lspci: generic names
    from xenon_settings import hardware
    return importlib.reload(hardware)


def test_nvidia_on_nouveau_offers_driver(tmp_path, monkeypatch):
    sys_ = tmp_path / "sys"
    make_pci(sys_, "0000:01:00.0", "0x030000", "0x10de", "nouveau")
    make_pci(sys_, "0000:00:02.0", "0x030000", "0x8086", "i915")
    make_pci(sys_, "0000:03:00.0", "0x028000", "0x8086", None)  # Wi-Fi, no driver
    hw = load(tmp_path, monkeypatch)
    gpus = {g.vendor: g for g in hw.gpus()}
    assert gpus["NVIDIA"].status == "warn" and gpus["NVIDIA"].actions
    assert gpus["Intel"].status == "ok"
    nets = hw.network()
    assert any(n.status == "fail" for n in nets)


def test_nvidia_recommendation():
    from xenon_settings import hardware as hw
    assert hw.nvidia_recommendation("NVIDIA Corporation GA104 [GeForce RTX 3070]") == "nvidia-open"
    assert hw.nvidia_recommendation("NVIDIA Corporation TU116 [GeForce GTX 1660 SUPER]") == "nvidia-open"
    assert hw.nvidia_recommendation("NVIDIA Corporation GP104 [GeForce GTX 1080]") == "nvidia"


def test_audio_and_memory(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    (proc / "asound").mkdir(parents=True)
    (proc / "asound" / "cards").write_text(
        " 0 [PCH            ]: HDA-Intel - HDA Intel PCH\n"
        "                      HDA Intel PCH at 0xf7f10000 irq 32\n"
        " 1 [Scarlett       ]: USB-Audio - Scarlett 2i2 USB\n")
    (proc / "meminfo").write_text("MemTotal:       16314444 kB\n")
    hw = load(tmp_path, monkeypatch)
    names = [a.name for a in hw.audio()]
    assert names == ["HDA Intel PCH", "Scarlett 2i2 USB"]
    assert 15.5 < hw.memory_gib() < 15.6
