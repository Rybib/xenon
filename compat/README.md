# Compatibility profiles

Each `.toml` file describes known fixes for one Windows program. The
Xenon Windows Subsystem (XWS) matches the program being launched against
these profiles and silently applies the first match. Users never see this
unless they look in **Xenon Settings → Windows Compatibility → Known fixes**.

Profiles are installed to `/usr/share/xenon/compat/profiles/`. Local
overrides go in `/etc/xenon/compat/` (system) or `~/.config/xenon/compat/`
(user). A profile there with the same `id` replaces the shipped one.

## Schema

```toml
[app]
id = "ableton-live"            # unique, lowercase, [a-z0-9._-]
name = "Ableton Live"          # shown to users
rating = "untested"            # platinum | gold | silver | bronze | broken | untested
notes = "Free text shown in Xenon Settings."

[match]                        # at least one of exe / product
exe = ["Ableton Live*.exe"]    # file-name globs, case-insensitive
product = ["Ableton Live*"]    # globs on the PE ProductName version field
company = ["Ableton*"]         # optional: narrows `product` matches

[fix]                          # every key is optional
isolated = false               # true: own Windows environment for this app
runtimes = ["vcrun2022"]       # installed on first launch (see `xws runtime list`)
dll_overrides = { d3d9 = "n,b" }
env = { KEY = "value" }
windows_version = "win10"      # win11 | win10 | win81 | win7
graphics_driver = "x11"        # x11 | wayland
game = true                    # force game mode on/off (default: detected)
dxvk = true                    # override the DirectX 8-11 translation setting
vkd3d_proton = true            # override the DirectX 12 translation setting
args = ["-some-flag"]          # extra command-line arguments
```

## Ratings

| Rating | Meaning |
|---|---|
| platinum | Works perfectly out of the box |
| gold | Works perfectly with the fixes in this profile |
| silver | Works with minor issues |
| bronze | Runs, with significant issues |
| broken | Does not work; the notes say why |
| untested | Not yet verified on Xenon. The fixes are a starting point |

A rating may only move above `untested` after someone has run the app on
a Xenon release and filed a report (see `docs/TESTING.md`). The two
`platinum` entries (7-Zip, Notepad++) carry their long-standing WineHQ
AppDB ratings and still need confirming on Xenon.

## Testing a profile

```bash
xws inspect ~/Downloads/SomeSetup.exe   # which profile matches, runtimes, game/installer detection
xws profiles                            # all profiles
```

`make test` validates every profile in this directory.
