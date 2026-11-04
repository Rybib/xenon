# Roadmap

## Phase 1: Bootable Xenon (foundation)

- [x] Debian 13 + lightweight GNOME, Xenon branding (logo, wallpapers, Plymouth, GRUB, GDM, os-release)
- [x] Newer kernel and Mesa via Debian backports (signed, Secure Boot)
- [x] live-build configuration and build scripts (Docker + native)
- [x] Calamares installer: erase/manual/dual boot, LUKS, users, NVIDIA choice, UEFI + BIOS, Secure Boot fallback path
- [x] Firewall, auto security updates, zram, low-latency audio, controller rules, privacy defaults
- [x] CI: build the ISO, boot it in QEMU, screenshot, in-VM self-test
- [x] First green ISO build in CI: boots to the desktop, in-VM self-test passes (Linux 7.2, Wine 11.0, NTSYNC, a Windows program runs through XWS)
- [ ] Installer verified in a VM (UEFI + Secure Boot, BIOS, encrypted)
- [ ] Booted and installed on real hardware (AMD and NVIDIA)

## Phase 2: Windows apps just work

- [x] XWS: one managed environment per user, drive mapping, user folders
- [x] Double-click `.exe`/`.msi`/`.lnk`; `.exe` from the terminal via binfmt_misc
- [x] Start Menu → app grid entries with icons; file associations; uninstall from Settings; stale entry cleanup
- [x] Runtimes on demand from PE imports (VC++, d3dx, d3dcompiler, xact, physx) and profiles (.NET, fonts)
- [x] Wine Mono/Gecko pre-installed: no prompts
- [x] DXVK + VKD3D-Proton deployed into every environment
- [x] NTSYNC: module autoload, device permissions, health check
- [x] Registry snapshots before every install; restore
- [x] Compatibility profile format + first profiles (priority apps marked untested)
- [x] Tested end-to-end against real Wine in CI
- [ ] Test the priority apps on real hardware and fill in ratings
- [ ] Casefold-enabled root filesystem from the installer
- [ ] WineASIO for low-latency Ableton setups

## Phase 3: Polish and performance

- [x] Xenon Settings: Windows apps, compatibility, drivers, privacy, updates, about
- [x] First-boot Welcome with hardware check and NVIDIA driver offer
- [ ] Profile updates delivered independently of OS releases (signed profile bundle)
- [ ] Compatibility report flow from Settings (opt-in, no telemetry)
- [ ] Benchmarks against Windows on the same hardware (DX11, DX12, Vulkan titles)
- [ ] Evaluate sched_ext schedulers (scx_lavd, scx_bpfland) against EEVDF for frame-time consistency
- [ ] Wine Wayland driver as default once clipboard/DnD/IME are solid
- [ ] Optional sandboxing for Windows apps
- [ ] Kernel work in Rust guided by profiling (see `kernel/README.md`)

## Phase 4: Public release

- [ ] Xenon APT repository (signed) for xenon-* updates
- [ ] ISO hosting (GitHub release assets are limited to 2 GB; the ISO is larger)
- [ ] Website, documentation site, issue templates, community compatibility database
- [ ] Release cadence: point release each Debian point release; Wine/DXVK/VKD3D-Proton refreshed monthly
