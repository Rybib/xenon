# Testing

## Automated (runs in CI)

| Test | Command | What it proves |
|---|---|---|
| Unit tests | `make test` | PE/LNK/registry parsers, profile matching, runtime detection, menu rewriting, settings, hardware detection |
| XWS end-to-end | `make e2e` | Against real Wine: environment setup, DXVK deployment, a 32-bit program, an installer (built with mingw) that writes Program Files, the registry and Start Menu shortcuts, app grid entry, launch from the entry, installed-apps list, uninstall, entry cleanup |
| Lint | `make lint` | shellcheck on every script, desktop entry validation |
| Packages | `tools/build-packages.sh` | All packages build on Debian 13; lintian; GNOME setting overrides checked against the real schemas with `glib-compile-schemas --strict` |
| ISO boot | `tools/test-iso.sh out/*.iso` | The ISO boots to the GNOME desktop (screenshot), and `vm-selftest` checks os-release, NTSYNC, binfmt, sysctl, zram, firewall, Plymouth, Calamares, Flathub, GNOME defaults, Wine ≥ 10, DXVK/VKD3D payloads, Wine Mono, then creates a Windows environment as the live user and runs a Windows program through XWS |

## In a VM by hand (installer)

The installer can't be fully automated yet. Test it in a VM before every
release.

```bash
qemu-img create -f qcow2 /tmp/xenon.qcow2 40G
# UEFI with Secure Boot (Debian/Ubuntu: apt install ovmf)
cp /usr/share/OVMF/OVMF_VARS_4M.ms.fd /tmp/vars.fd
qemu-system-x86_64 -enable-kvm -m 6G -smp 4 -machine q35,smm=on \
  -global driver=cfi.pflash01,property=secure,value=on \
  -drive if=pflash,format=raw,unit=0,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.ms.fd \
  -drive if=pflash,format=raw,unit=1,file=/tmp/vars.fd \
  -cdrom out/xenon-1.0-amd64.iso -drive file=/tmp/xenon.qcow2,if=virtio \
  -vga virtio -display gtk,gl=on -device virtio-net,netdev=n -netdev user,id=n
```

Checklist:

- [ ] Boots with Secure Boot **on**; Xenon splash shows
- [ ] "Try or Install" window appears; *Install Xenon* opens Calamares
- [ ] Erase-disk install, **with** encryption: asks for the passphrase at boot (Plymouth prompt), then boots
- [ ] Erase-disk install without encryption
- [ ] Legacy BIOS install (drop the pflash lines)
- [ ] Installed system: no "Install Xenon" icon; Welcome opens on first login
- [ ] Settings → About shows Xenon, kernel and Wine versions
- [ ] Download and install 7-Zip and Notepad++ from their websites by double-clicking; both appear in the app grid and start
- [ ] Uninstall both from Settings → Windows Apps

## On real hardware (Ryan)

Things only real hardware can show. Record results in `docs/HARDWARE.md`.

- [ ] AMD GPU machine: Vulkan works (`xws doctor`), a DX11 game and a DX12 game run
- [ ] NVIDIA GPU machine: choose the NVIDIA driver in the installer → driver installed on first boot → MOK enrollment with Secure Boot on → `nvidia-smi` works → DX11/DX12 games run
- [ ] Laptop: hybrid graphics ("Launch using Discrete Graphics Card" in the app menu), sleep/resume, touchpad gestures, battery
- [ ] Wi-Fi works in the live session and after install
- [ ] Bluetooth headphones, controller (Xbox/PlayStation), mouse
- [ ] USB audio interface + MIDI controller; latency feels right in a DAW
- [ ] Dual boot alongside Windows: both appear in the boot menu, both boot
- [ ] Printer (driverless) and scanner
- [ ] Priority apps: Steam (Windows), Epic, Photoshop, Premiere Pro, Illustrator, Ableton Live, Office, Discord. For each, record it in its `compat/profiles/*.toml` (rating + notes)

## Reporting a compatibility result

Run `xws inspect` on the installer, try the app, then update its profile
(or add one) with a rating and notes on what worked, what didn't, and
your hardware. `~/.local/state/xenon/logs/<program>.log` holds the details.
