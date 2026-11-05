#!/bin/bash
# Build all Xenon .deb packages.
#
#   tools/build-packages.sh [OUTDIR]     (default: build/debs)
#
# Environment (set by CI):
#   XENON_VERSION_SUFFIX  appended to every package version, e.g. "+b42"
#                         (CI uses the workflow run number, so each build's
#                         packages are newer than the last and installed
#                         systems update to them)
#   XENON_REPO_KEY        the update signing key (armored private key).
#                         When set, xenon-archive-keyring is built with its
#                         public half; without it that package is skipped.
#   XENON_SKIP_THIRDPARTY=1  skip the DXVK/VKD3D-Proton package (offline dev)
#
# Needs a Debian/Ubuntu system with: debhelper dh-python python3-pytest
# librsvg2-bin curl zstd gnupg. The build happens in a copy of the tree, so
# the repository stays clean.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/build/debs}"
WORK="$ROOT/build/pkg"
SUFFIX="${XENON_VERSION_SUFFIX:-}"

echo "==> Preparing build tree in $WORK"
rm -rf "${WORK:?}"
mkdir -p "$WORK/src" "$OUT"
tar -C "$ROOT" --exclude=./.git --exclude=./build --exclude=./out -cf - . \
    | tar -C "$WORK/src" -xf -

stamp_version() { # debian/changelog: "pkg (0.1.0)" -> "pkg (0.1.0+b42)"
    if [ -n "$SUFFIX" ]; then
        sed -i "1s/(\([^)]*\))/(\1$SUFFIX)/" "$1/debian/changelog"
    fi
    head -n 1 "$1/debian/changelog"
}

echo "==> Building xenon packages"
stamp_version "$WORK/src"
(cd "$WORK/src" && dpkg-buildpackage -b -us -uc)

if [ -z "${XENON_SKIP_THIRDPARTY:-}" ]; then
    echo "==> Building xenon-xws-thirdparty (DXVK, VKD3D-Proton, winetricks)"
    stamp_version "$WORK/src/packages/xenon-xws-thirdparty"
    (cd "$WORK/src/packages/xenon-xws-thirdparty" && ./fetch.sh && dpkg-buildpackage -b -us -uc)
fi

if [ -n "${XENON_REPO_KEY:-}" ]; then
    echo "==> Building xenon-archive-keyring (update repository + signing key)"
    KR="$WORK/src/packages/xenon-archive-keyring"
    GNUPGHOME="$(mktemp -d)"
    export GNUPGHOME
    printf '%s\n' "$XENON_REPO_KEY" | gpg --batch --quiet --import
    gpg --batch --export > "$KR/xenon-archive-keyring.gpg"
    gpg --list-keys --with-colons | awk -F: '/^fpr/{print "    signing key " $10; exit}'
    rm -rf "$GNUPGHOME"
    unset GNUPGHOME
    stamp_version "$KR"
    (cd "$KR" && dpkg-buildpackage -b -us -uc)
else
    echo "==> XENON_REPO_KEY not set: skipping xenon-archive-keyring"
    echo "    (this build will not receive updates; see docs/UPDATES.md)"
fi

find "$WORK" -maxdepth 3 -name '*.deb' -exec cp {} "$OUT/" \;
echo "==> Packages in $OUT:"
ls -1 "$OUT"
