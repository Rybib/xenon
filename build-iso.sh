#!/bin/bash
# Build the Xenon live/install ISO.
#
# Run as root on Debian 13 (trixie), or anywhere with Docker via
# tools/build-in-docker.sh. The finished ISO lands in out/.
#
#   sudo ./build-iso.sh
#
# Environment:
#   XENON_VERSION   version string (default 1.0)
#   XENON_MIRROR    Debian mirror (default http://deb.debian.org/debian)
#   SKIP_DEPS=1     don't apt-get install build dependencies
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
WORK="$ROOT/build"
OUT="$ROOT/out"
export XENON_VERSION="${XENON_VERSION:-1.0}"

if [ "$(id -u)" -ne 0 ]; then
    echo "build-iso.sh must run as root (live-build creates a chroot)." >&2
    exit 1
fi
# shellcheck disable=SC1091
. /etc/os-release
if [ "${VERSION_CODENAME:-}" != "trixie" ] && [ -z "${XENON_ALLOW_ANY_HOST:-}" ]; then
    echo "Build on Debian 13 (trixie), or use tools/build-in-docker.sh." >&2
    echo "Set XENON_ALLOW_ANY_HOST=1 to try anyway." >&2
    exit 1
fi

if [ -z "${SKIP_DEPS:-}" ]; then
    echo "==> Installing build dependencies"
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        live-build build-essential debhelper dh-python python3 python3-pytest librsvg2-bin \
        dpkg-dev fakeroot curl zstd ca-certificates xorriso squashfs-tools \
        mtools dosfstools grub-efi-amd64-bin grub-pc-bin syslinux isolinux \
        syslinux-common shim-signed grub-efi-amd64-signed
fi

echo "==> Building packages"
rm -rf "${WORK:?}/debs"
"$ROOT/tools/build-packages.sh" "$WORK/debs"

echo "==> Preparing live-build tree"
LIVE="$WORK/live"
mkdir -p "$LIVE"
# Fresh configuration every time; keep live-build's package cache.
rm -rf "${LIVE:?}/config" "${LIVE:?}/auto"
cp -a "$ROOT/live/config" "$ROOT/live/auto" "$LIVE/"

STAGE="$LIVE/config/includes.chroot_after_packages"
mkdir -p "$STAGE/var/cache/xenon-debs" "$STAGE/etc/apt/keyrings"
cp "$WORK"/debs/*.deb "$STAGE/var/cache/xenon-debs/"
# The backports pin must be active while packages are installed.
cp "$ROOT/packages/xenon-system/apt/xenon-backports" "$LIVE/config/archives/backports.pref.chroot"
echo "==> Fetching the WineHQ repository key"
curl -fsSL --retry 4 https://dl.winehq.org/wine-builds/winehq.key \
    -o "$STAGE/etc/apt/keyrings/winehq-archive.key"

echo "==> Running live-build"
cd "$LIVE"
lb clean
lb config
lb build

mkdir -p "$OUT"
ISO_SRC="$(find "$LIVE" -maxdepth 1 -name '*.iso' | head -n 1)"
if [ -z "$ISO_SRC" ]; then
    echo "live-build did not produce an ISO; see $LIVE/build.log" >&2
    exit 1
fi
ISO="$OUT/xenon-${XENON_VERSION}-amd64.iso"
mv "$ISO_SRC" "$ISO"
(cd "$OUT" && sha256sum "$(basename "$ISO")" > "$(basename "$ISO").sha256")
cp "$LIVE/build.log" "$OUT/build.log" 2>/dev/null || true
echo "==> Done: $ISO ($(du -h "$ISO" | cut -f1))"
