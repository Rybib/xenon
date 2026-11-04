# Design decisions

Short records of choices that are easy to second-guess later.

### Debian's signed backports kernel instead of a custom "Xenon kernel" (for now)
Secure Boot is a hard requirement: Xenon must install on modern PCs with
Secure Boot left on. Debian's shim only trusts kernels signed by Debian, so
a self-built kernel would force users to disable Secure Boot or enroll a
key. Backports kernels are signed, new enough for NTSYNC (Linux ≥ 6.14)
and current hardware, and maintained by Debian's security team. Xenon's
kernel preferences that work as boot options (`preempt=full`) or sysctls
(`vm.max_map_count`, `split_lock_mitigate`) are applied without rebuilding.
`kernel/` keeps the custom build ready for features that do need one
(Rust modules, 1000 Hz, sched_ext experiments) once Xenon can sign its own
kernels with its own shim (that needs Microsoft shim review).

### EFI bootloader id stays `debian`
Debian's signed GRUB has its configuration path compiled in as
`EFI/debian`. A different id breaks Secure Boot boots. The firmware boot
menu shows "debian"; the GRUB menu itself says Xenon.

### WineHQ stable instead of Debian's wine package
Debian 13 ships Wine 10.0, which has no NTSYNC support. WineHQ's stable
branch (11.x) has it, plus a year of compatibility fixes. WineHQ
packages are LGPL builds from the official project with an apt repository,
so users get Wine updates without Xenon re-packaging them.

### XWS wraps Wine instead of forking it
Forking Wine would mean maintaining millions of lines. XWS does the
integration Wine leaves to the user (environment, menus, runtimes,
profiles, uninstall) and stays small and testable. Fixes to Wine itself
go upstream.

### One shared environment, isolation by profile
Windows itself has one shared system, and most apps expect shared
runtimes. Launchers that bundle their own runtimes and games (Steam, Epic)
and heavyweight suites (Adobe) get their own environments through their
profiles, so they can't break each other.

### winemenubuilder output is the source of truth for menus
Wine already extracts icons and writes freedesktop entries correctly. XWS
post-processes them (launch through XWS, hide clutter, remove stale
entries) instead of reimplementing icon extraction.

### XWS resolves `.lnk` shortcuts itself
Launching via Wine's `start.exe` returns misleading exit codes for
shortcuts, which would trigger false "app crashed" dialogs. Resolving the
target lets XWS apply the right profile and get real exit codes.

### XWayland by default for Windows apps
Wine's Wayland driver is promising but still missing pieces people use
daily. XWayland with Mutter's `xwayland-native-scaling` gives sharp HiDPI
rendering today. Users can switch per system in Settings.

### LUKS1 for automatic encryption
The encrypted root contains `/boot`, so GRUB has to unlock it, and GRUB
can't reliably unlock LUKS2 with Argon2. A separate unencrypted `/boot`
with LUKS2 is a candidate for later.

### No GeoIP lookup in the installer
Calamares normally asks a web service where you are to preselect the time
zone. Xenon's privacy promise wins: users pick their region.

### Microsoft runtimes are downloaded, never bundled
The VC++ / .NET / font redistributable licenses don't allow Xenon to ship
them. winetricks downloads them from Microsoft when a program needs them.
Wine's own replacements and metric-compatible free fonts (Liberation,
Carlito, Caladea) cover the offline case.

### NVIDIA via first boot, not inside the installer
Installing NVIDIA's DKMS module needs network access and kernel headers.
Doing it inside Calamares makes the install fragile. The installer records
the choice, and a first-boot service installs the driver when online and
handles Secure Boot key enrollment (MOK) with a one-time code shown to
the user.
