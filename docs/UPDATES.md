# How Xenon updates

**Push to `main` → tests pass → every Xenon computer updates itself.**
Users never reinstall and never have to click anything.

## What happens on a push to `main`

```
git push origin main
   │
   ▼
GitHub Actions ─ ISO workflow (.github/workflows/iso.yml)
   1. build   all packages, versioned 0.1.0+b<run number>, plus the ISO
   2. test    boot the ISO in a VM: desktop, self-test, a Windows program
              runs through XWS, Windows apps on the desktop
   3. publish ONLY if 1 and 2 passed: sign a Debian package repository
              with the Xenon key and deploy it to GitHub Pages
              https://rybib.github.io/xenon/apt
   │
   ▼
Every Xenon computer, once a day (apt-daily / apt-daily-upgrade timers):
   APT downloads the repository, checks its signature against the Xenon
   key, and unattended-upgrades installs the newer xenon-* packages in the
   background. Changes take effect the next time a program starts (XWS and
   Settings), at next login (desktop defaults) or next boot (boot splash).
```

A push that fails any test publishes nothing, so users keep the last
version that passed. Pushes that only change documentation don't trigger a
build. Separately, the CI workflow's `tools/test-updates.sh` checks the
mechanism itself on every push: it publishes a signed repository, installs
from it, publishes a newer build, confirms unattended-upgrades installs it
on its own, and confirms APT rejects a tampered repository.

## What updates where

| What | Comes from | How it updates |
|---|---|---|
| **Xenon**: XWS, Settings, branding, defaults, compatibility profiles, DXVK/VKD3D-Proton | Xenon repository (this repo's CI) | automatically, as above |
| Debian base system, security fixes, kernel, Mesa | Debian (stable + backports) | automatically (security) and in Software |
| Wine | WineHQ's repository | in Software |
| Linux apps | Flathub | in Software |
| Firmware/BIOS | LVFS (fwupd) | in Software |
| New installs | the ISO from the latest ISO workflow run | download |

Users can turn automatic updates off in **Xenon Settings → Updates**.
**Settings → About → Xenon build** shows the installed build (`+b<number>`).

## Pieces

| File | Role |
|---|---|
| `tools/build-packages.sh` | stamps `XENON_VERSION_SUFFIX` into every package version; builds `xenon-archive-keyring` from the signing key |
| `packages/xenon-archive-keyring/` | installs the public key, `/etc/apt/sources.list.d/xenon.sources` and the unattended-upgrades rule for `origin=Xenon` |
| `tools/build-apt-repo.sh` | builds and signs the repository (InRelease, Release.gpg) |
| `.github/workflows/iso.yml` → `publish` | deploys it to GitHub Pages after the tests |
| `live/config/hooks/normal/0950-xenon-updates.hook.chroot` | in the very first ISO (before anything was published) disables the not-yet-existing repository |
| `tools/setup-updates.sh` | one-time setup: key + secret + Pages |
| `tools/test-updates.sh` | end-to-end test of the mechanism (CI) |

## One-time setup (Ryan, on your own computer)

The signing key proves updates really come from you, so it must be made on
your computer, not by an automated session. With the GitHub CLI logged in
(`gh auth login`) and GnuPG installed (macOS: `brew install gh gnupg`):

```bash
git clone https://github.com/Rybib/xenon.git && cd xenon
tools/setup-updates.sh
```

It creates the key, stores it as the repository secret `XENON_REPO_KEY`,
turns on GitHub Pages (source: GitHub Actions), and leaves a backup file
`xenon-update-key-PRIVATE-….asc`. **Put that backup in a password manager
and delete the file.** If the key is lost, installed systems can't be
updated by a new key without a manual step; if it leaks, someone could
publish updates. The script refuses to replace an existing key for that
reason.

After that, the next push to `main` publishes the first update, and ISOs
built from then on update themselves.

## Limits and later improvements

- The repository holds only the newest build. Rolling back means pushing a
  fix (a revert is also a new, higher build).
- One channel for everyone. A `testing` channel (every push) and `stable`
  (tags only) can be added later by publishing two suites.
- Debian's next major release (14, ~2027) will be a guided upgrade, not an
  automatic one.
- Btrfs snapshots before updates (undo from the boot menu) are a candidate
  for later.
