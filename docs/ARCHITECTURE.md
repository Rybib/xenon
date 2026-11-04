# Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│ Apps:  Linux (Flatpak/Flathub, Debian)      Windows (.exe / .msi)      │
├──────────────────────────────────────────────────────────────────────┤
│ Desktop: GNOME + dock + tray │ Xenon Settings │ Welcome │ Software     │
├──────────────────────────────────────────────────────────────────────┤
│ Xenon Windows Subsystem (xws)                                          │
│   launcher ─ PE/LNK analysis ─ compat profiles ─ runtimes (winetricks) │
│   managed environment ─ drive mapping ─ menus ─ snapshots ─ doctor     │
│   Wine (WineHQ stable) + DXVK + VKD3D-Proton                           │
├──────────────────────────────────────────────────────────────────────┤
│ Graphics: Mesa (RADV, ANV, NVK) │ NVIDIA driver (optional) │ Vulkan     │
│ Audio: PipeWire (low latency) │ Network: NetworkManager │ zram          │
├──────────────────────────────────────────────────────────────────────┤
│ Debian 13 "trixie" base + backports (kernel, Mesa, firmware, NVIDIA)   │
├──────────────────────────────────────────────────────────────────────┤
│ Linux kernel (signed): NTSYNC, binfmt_misc, casefold, preempt=full     │
└──────────────────────────────────────────────────────────────────────┘
```

## Packages

| Package | Contents |
|---|---|
| `xenon-xws` | `xws` command and library (`/usr/lib/xenon/xws`), binfmt_misc registration, `.exe`/`.msi` handler, MIME defaults, NTSYNC udev rule and module autoload, compatibility profiles, login-time menu sync |
| `xenon-xws-thirdparty` | DXVK, VKD3D-Proton and winetricks, pinned upstream releases |
| `xenon-settings` | Xenon Settings, Welcome, live "Try or Install" prompt, `xenon-admin` (polkit), first-boot NVIDIA install service |
| `xenon-system` | sysctl tuning, zram, PipeWire low latency, realtime audio limits, controller udev rules, GNOME defaults, Firefox privacy policies, auto security updates, backports pinning, journald limits, VM self-test |
| `xenon-branding` | Icons, wallpapers, Plymouth theme, GRUB defaults, GDM logo, os-release |
| `xenon-installer` | Calamares configuration, branding, slideshow and target scripts (live ISO only) |
| `xenon-desktop` | Metapackage pulling in the whole desktop on any Debian 13 system |

## Boot and install flow

1. **ISO boot**: GRUB (UEFI, via signed shim) or ISOLINUX (BIOS) → kernel
   with `quiet splash` → Plymouth Xenon splash → live-boot → GDM
   autologin as `xenon`.
2. **Live session**: the "Try or Install" window appears and *Install
   Xenon* is first in the dock.
3. **Calamares**: welcome → location → keyboard → partitions
   (erase/manual/alongside, optional LUKS) → graphics driver choice →
   user → summary → install.
4. **Install steps**: unpack squashfs → configure → `target-setup`
   (installs the GRUB build for this firmware from an offline copy, purges
   live-only packages) → NVIDIA flag (if chosen) → initramfs → GRUB with
   shim (`EFI/debian`, Secure Boot) → `target-final` (removable-media
   fallback path).
5. **First boot**: `xenon-firstboot-drivers.service` installs the NVIDIA
   driver if it was chosen. The Welcome app covers privacy, the hardware
   check and a tour.

## What happens when you open a Windows program

`xws run setup.exe` (from a double-click, the terminal via binfmt_misc, or
Settings):

1. **Classify**: program, MSI package, shortcut (`.lnk`) or batch file, by
   magic bytes.
2. **Analyse**: the PE header gives 32/64-bit, GUI/console, the import
   table, .NET, and version info (ProductName/CompanyName). Shortcuts are
   resolved to their target program.
3. **Profile**: match `compat/profiles/*.toml` by exe name or product.
   This can request an isolated environment, runtimes, DLL overrides,
   environment variables or arguments.
4. **Environment**: create or update `~/.local/share/xenon/windows`
   (registry defaults, fonts, DPI, C:/Z:/removable drives, user folders,
   DXVK/VKD3D-Proton DLLs) behind a progress dialog the first time.
5. **Runtimes**: imports such as `MSVCP140.dll` or `d3dx9_43.dll` map to
   winetricks verbs, which download from Microsoft on first use.
6. **Snapshot**: installers get a registry snapshot first.
7. **Run**: Wine with `WINEDEBUG=-all`, under `gamemoderun` for games;
   output goes to `~/.local/state/xenon/logs/`.
8. **Integrate**: after installers, wait for Wine to finish, then turn the
   new Start Menu shortcuts into `~/.local/share/applications/xenon-windows/*.desktop`
   (skipping uninstallers/readmes/links) and notify the user. Stale entries
   for uninstalled apps are removed, which Wine itself never does.
9. **Report**: a quick crash shows a friendly dialog pointing at the log.

Uninstalling (`xws uninstall`, or the button in Settings) reads the
registry's Uninstall keys directly from `system.reg`/`user.reg` (no Wine
start-up), runs the app's uninstaller (or `msiexec /x`), then re-syncs the
app grid.
