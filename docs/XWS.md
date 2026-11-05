# Xenon Windows Subsystem (XWS)

XWS makes Windows programs part of Xenon. It is a small Python program
(standard library only) that drives Wine. It does not replace Wine. It
handles everything Wine leaves to the user: one managed environment, menus,
runtimes, per-app fixes and cleanup.

## Where things live

| Path | What |
|---|---|
| `~/.local/share/xenon/windows/` | The main Windows environment (`C:` is `drive_c/`) |
| `~/.local/share/xenon/isolated/<id>/` | Separate environments for apps whose profile asks for one (Steam, Epic, Adobe) |
| `~/.local/share/xenon/snapshots/` | Registry snapshots (last 10, taken before every install) |
| `~/.local/share/applications/xenon-windows/` | App grid entries for installed Windows programs |
| `~/.local/state/xenon/logs/` | One log per program, plus environment/runtime logs |
| `~/.config/xenon/xws.toml` | Per-user settings (written by Xenon Settings) |
| `/usr/lib/xenon/xws/` | XWS itself, DXVK, VKD3D-Proton, winetricks |

## Drives and folders

- `C:` is the managed Windows drive.
- `Z:` is the whole Linux filesystem (Wine needs it for Linux paths).
- `D:` to `Y:` are assigned automatically to USB drives and other media
  mounted under `/run/media/$USER`, and removed when they go away.
- `Documents`, `Downloads`, `Desktop`, `Music`, `Pictures`, `Videos` inside
  Windows are your real Xenon folders.

## The `xws` command

Most people never type these; the desktop and Settings use them.

```
xws run FILE [ARGS]       run a program, installer (.exe/.msi) or shortcut (.lnk)
xws apps [--json]         installed Windows apps (from the registry)
xws uninstall APP         uninstall by id or name
xws doctor [--json]       health check: Wine, NTSYNC, binfmt, Vulkan, DXVK, ...
xws inspect FILE          what XWS knows about a file (imports, profile, runtimes)
xws runtime list|install  Windows runtimes (vcrun2022, d3dx9, dotnet48, corefonts, ...)
xws profiles              compatibility profiles
xws snapshot create|list|restore NAME
xws config [KEY [VALUE]]  settings (dxvk, vkd3d_proton, gamemode, mangohud,
                          graphics_driver, windows_version, auto_runtimes, ...)
xws sync-menu             rebuild app grid entries
xws kill                  stop all Windows programs
xws reset --yes           delete the Windows environment
```

## Settings

`/usr/share/xenon/xws.toml` (defaults) < `/etc/xenon/xws.toml` <
`~/.config/xenon/xws.toml`.

| Key | Default | Meaning |
|---|---|---|
| `graphics_driver` | `x11` | `x11` (XWayland, most compatible) or `wayland` (Wine's native Wayland driver) |
| `window_frame` | `desktop` | Who draws title bars: `desktop` (GNOME, matching other apps) or `windows` (the program). Never both |
| `windows_theme` | `light` | `light` (Wine's flat modern theme) or `classic` |
| `windows_version` | `win10` | Version reported to programs |
| `dxvk` / `vkd3d_proton` | `true` | DirectX→Vulkan translation |
| `gamemode` | `true` | Run detected games under GameMode |
| `mangohud` | `false` | Performance overlay in games |
| `auto_runtimes` | `true` | Install runtimes a program imports |
| `compat_profiles` | `true` | Apply known fixes |
| `snapshot_keep` | `10` | Registry snapshots to keep |

## Integration points

- **Double-click**: `xenon-windows-app.desktop` is the default handler for
  `.exe`, `.msi` and `.lnk` (`/etc/xdg/mimeapps.list`).
- **Terminal**: `/usr/lib/binfmt.d/xenon-pe.conf` registers `MZ` executables
  with the kernel, so `./setup.exe` works (it needs the execute bit).
- **NTSYNC**: `/usr/lib/modules-load.d/xenon-ntsync.conf` loads the module
  and a udev rule gives the logged-in user access to `/dev/ntsync`. Wine 11
  uses it automatically.
- **One title bar per window**: many Windows programs draw their own title
  bar (Chromium/Electron apps, Steam, Discord, Spotify) but ask for a
  resizable frame; GNOME then adds a full title bar on top (two headers)
  and resizing jumps around. While Windows programs run, `xws frames`
  turns those requests into "no decorations" so only the program's own
  title bar shows and it moves/resizes itself, as on Windows. Normal
  windows keep GNOME's title bar. Tested by `tests/frames.sh` with GNOME's
  window manager and real mouse drags.
- **Login**: a systemd user service re-syncs app entries.
- **Wine Mono and Gecko**: `fetch-wine-addons` reads the exact versions the
  installed Wine expects from `appwiz.cpl` and installs them at image build
  time, so new environments never show download prompts.

## Known gaps (work items)

- Casefold: XWS tries `chattr +F` on `C:` (case-insensitive, faster). It
  only works if the filesystem was created with the `casefold` feature;
  the installer doesn't do that yet. Wine works either way.
- An ASIO bridge (WineASIO) for the lowest-latency Ableton setups.
- The Wayland driver is opt-in until clipboard, drag-and-drop and IME
  support are solid enough for everyday use.
- Per-app sandboxing for Windows programs (planned with Flatpak-style
  portals or bubblewrap).
