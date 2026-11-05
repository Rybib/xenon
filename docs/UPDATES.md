# How Xenon updates (design)

Status: **proposed**. Nothing here is built yet except the parts marked ✅.

## The short version

- Users never reinstall to get updates. Xenon updates like Debian and
  Ubuntu do: through **APT**, shown in **Software**, installed automatically
  in the background where safe.
- Xenon's own packages come from a **Xenon APT repository** that GitHub
  Actions builds and signs, hosted for free on **GitHub Pages** from this
  repository.
- **Pushing to `main` does not update anyone.** `main` feeds a *testing*
  channel for you and testers. Users get an update when you **tag a
  release** (`v0.2.0`), after all the automated tests have passed.

## What updates where

| What | Comes from | Who builds it | How users get it |
|---|---|---|---|
| Debian base system, security fixes, kernel, Mesa | Debian (stable + backports) | Debian | ✅ automatically (unattended-upgrades) and in Software |
| Wine | WineHQ's APT repository | WineHQ | ✅ in Software |
| Linux apps | Flathub | app developers | ✅ in Software |
| Firmware/BIOS | LVFS (fwupd) | hardware vendors | ✅ in Software |
| **Xenon itself**: XWS, Settings, branding, defaults, compatibility profiles, DXVK/VKD3D-Proton | **Xenon APT repository** | **this repo's GitHub Actions** | in Software, plus automatic install (new) |
| New installs | ISO | GitHub Actions | download (hosting still to choose) |

So only one new piece is needed: the Xenon APT repository. Everything on
users' machines that checks for and installs updates already exists in
Debian/GNOME.

## The release flow

```
 you push to main ──► CI (unit + Wine end-to-end + packages + ISO boot test)
                         │ green
                         ▼
                 "testing" channel  ◄── opt-in (you, testers)
                         │
 you: git tag v0.2.0 ──► same tests again, then
                         ▼
                 "stable" channel   ◄── every Xenon user
                         │
                         ▼
     users' PCs: APT/PackageKit notices → Software shows the update,
     or unattended-upgrades installs it quietly (Xenon packages only)
```

To ship an update you would only run:

```bash
git tag v0.2.0 && git push origin v0.2.0
```

CI stamps the version into the packages (`0.2.0`; testing builds become
`0.2.0~git20261105.abc1234`, which APT correctly treats as older than
`0.2.0`), builds them, signs the repository, publishes it, and attaches the
notes to a GitHub Release.

## The repository

- URL: `https://rybib.github.io/xenon/apt` (GitHub Pages, from the
  `gh-pages` branch that CI maintains). Pages allows 1 GB per site and
  100 MB per file; Xenon's packages total about 50 MB per release.
- Layout: a standard Debian repository with suites `stable` and `testing`,
  built with `reprepro`, keeping the last few versions so people can roll
  back.
- Signing: a dedicated GPG key. The **private key lives only in a GitHub
  Actions secret**; the public key ships in a new `xenon-archive-keyring`
  package that's on every ISO, with
  `/etc/apt/sources.list.d/xenon.sources` pointing at the stable suite.
  APT refuses anything not signed by that key.

## On users' computers

- `xenon-archive-keyring` + `xenon.sources`: APT knows where to look.
- unattended-upgrades gets one more allowed origin (`o=Xenon,a=stable`),
  so Xenon fixes install quietly, like Debian security fixes. That can be
  turned off in Xenon Settings → Updates.
- Software (PackageKit) shows Xenon updates next to app updates with no
  extra work.
- Testers can switch to `testing` with one line, or a future switch in
  Settings.

## Safety

- A tag only publishes if every test passes, including booting the new ISO
  and running a Windows program inside it.
- Packages never break user data. XWS upgrades the Windows environment
  through its layout version, as it does today.
- A bad release is fixed by releasing a higher version. The repository
  keeps older versions for manual rollback.
- Later: Btrfs snapshots before upgrades (like openSUSE) so any update can
  be undone from the boot menu.

## What it needs from you (one time)

1. **Create the signing key** on your own computer with
   `tools/make-signing-key.sh` (to be written). Add the two values it prints
   as repository secrets: Settings → Secrets and variables → Actions.
2. **Turn on GitHub Pages**: Settings → Pages → Deploy from branch →
   `gh-pages`.

The key must be created by you: automated sessions can't add secrets to the
repository, and a release key should never pass through a chat.

## Bigger upgrades

Debian's next stable release (14, "forky", expected around mid-2027)
becomes a major Xenon release. It ships as a new ISO and an in-place upgrade
that Xenon Settings guides, after it has been tested the same way.
