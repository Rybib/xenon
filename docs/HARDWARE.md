# Hardware compatibility

Xenon inherits Linux's hardware support: the backports kernel, the full
`firmware-*` set from Debian's non-free-firmware archive, Mesa from
backports, and NVIDIA's driver on request. Every release should be tested
on at least one AMD and one NVIDIA system.

Add a row when you test a machine (`xws doctor` output helps).

| Machine / part | Xenon version | GPU | Works | Issues |
|---|---|---|---|---|
| QEMU/KVM (virtio-gpu, CI) | 0.1 | virtio (llvmpipe) | Pending first CI ISO run | No GPU acceleration in CI (expected) |

## Expected to work out of the box

- **Graphics**: AMD (RADV), Intel (ANV/Iris), NVIDIA via the proprietary or open
  kernel modules (Turing and newer default to open), or NVK as the open fallback
- **Hybrid laptops**: switcheroo-control ("Launch using Discrete Graphics Card")
- **Network**: Intel, Realtek, Broadcom, Atheros, MediaTek Ethernet and Wi-Fi (firmware included)
- **Input**: USB/Bluetooth HID, gaming mice (Piper/ratbagd), Logitech receivers (Solaar)
- **Controllers**: Xbox, PlayStation (DS4/DualSense), Switch Pro, Steam, 8BitDo, wired and Bluetooth
- **Audio**: onboard HDA/SOF, USB audio interfaces, MIDI (PipeWire, low latency)
- **Printing/scanning**: driverless IPP Everywhere / IPP-over-USB, eSCL/WSD scanners (sane-airscan)
- **Firmware**: fwupd/LVFS through GNOME Software

## Known not to work

- Windows-only hardware drivers (Windows apps can't load kernel drivers)
- Kernel-level anti-cheat (Vanguard, some FACEIT/ESEA titles)
- RGB lighting control (OpenRGB) is not preinstalled; install it from Software (Flathub)
