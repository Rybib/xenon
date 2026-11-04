# Building Xenon

## The ISO

### Option A: Docker (any Linux host)

```bash
git clone https://github.com/Rybib/xenon.git
cd xenon
tools/build-in-docker.sh
```

The script runs `build-iso.sh` inside a privileged `debian:trixie`
container (live-build needs to mount `/proc` in its chroot). The result
is `out/xenon-1.0-amd64.iso` plus a `.sha256` file. Expect 30–60 minutes,
about 25 GB of free disk space, and a fast internet connection.

### Option B: a Debian 13 machine or VM

```bash
sudo ./build-iso.sh
```

It installs its own build dependencies with apt.

### Option C: GitHub Actions

Every push to `main` runs `.github/workflows/iso.yml`. It builds the ISO,
boots it in QEMU, and uploads three artifacts: the ISO, a desktop
screenshot, and the in-VM self-test report.

### What `build-iso.sh` does

1. `tools/build-packages.sh` builds the `xenon-*` packages from `debian/`
   and the third-party package (DXVK, VKD3D-Proton and winetricks,
   downloaded at the versions pinned in
   `packages/xenon-xws-thirdparty/versions.env`).
2. Copies `live/` to `build/live/`, stages the packages, the backports
   pin and the WineHQ key.
3. `lb config` + `lb build`. The chroot hooks in
   `live/config/hooks/normal/` run in order:
   - `0100` enables i386, installs WineHQ stable, 32-bit Mesa and the
     Xenon packages, and fetches Wine Mono/Gecko.
   - `0200` saves both GRUB platform packages for the offline installer.
   - `0300` sets the Plymouth theme, enables the firewall, adds Flathub,
     and hides Wine's own launchers.
   - `0900` verifies everything (NTSYNC, XWS, DXVK, branding) and fails
     the build if something essential is missing.

Useful environment variables: `XENON_VERSION`, `XENON_MIRROR` (for
example a local apt cache), `SKIP_DEPS=1`.

## Just the packages

```bash
sudo apt install debhelper dh-python python3-pytest librsvg2-bin curl zstd
tools/build-packages.sh            # → build/debs/*.deb
```

To turn an existing Debian 13 GNOME install into Xenon, add trixie-backports
and the WineHQ repository, then:

```bash
sudo apt install ./build/debs/*.deb
```

## Bumping DXVK / VKD3D-Proton / winetricks

1. Edit `packages/xenon-xws-thirdparty/versions.env`.
2. Run `packages/xenon-xws-thirdparty/fetch.sh`; it prints the SHA256 of
   each download.
3. Paste the hashes into `versions.env` so later builds verify them.
4. Add a `debian/changelog` entry in that package.

## Optional: a custom Xenon kernel

See `kernel/README.md`. The default ISO uses Debian's signed backports
kernel, so Secure Boot keeps working.
