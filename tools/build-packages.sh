#!/bin/bash
# Build all Xenon .deb packages.
#
#   tools/build-packages.sh [OUTDIR]     (default: build/debs)
#
# Needs a Debian/Ubuntu system with: debhelper dh-python python3-pytest
# librsvg2-bin curl zstd. The build happens in a copy of the tree, so the
# repository stays clean.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/build/debs}"
WORK="$ROOT/build/pkg"

echo "==> Preparing build tree in $WORK"
rm -rf "${WORK:?}"
mkdir -p "$WORK/src" "$OUT"
tar -C "$ROOT" --exclude=./.git --exclude=./build --exclude=./out -cf - . \
    | tar -C "$WORK/src" -xf -

echo "==> Building xenon packages"
(cd "$WORK/src" && dpkg-buildpackage -b -us -uc)

echo "==> Building xenon-xws-thirdparty (DXVK, VKD3D-Proton, winetricks)"
(cd "$WORK/src/packages/xenon-xws-thirdparty" && ./fetch.sh && dpkg-buildpackage -b -us -uc)

find "$WORK" -maxdepth 3 -name '*.deb' -exec cp {} "$OUT/" \;
echo "==> Packages in $OUT:"
ls -1 "$OUT"
