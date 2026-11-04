#!/bin/bash
# Build an optional "Xenon kernel" .deb from a kernel.org stable release,
# using Debian's configuration plus xenon.config.
#
#   ./build-kernel.sh 6.17.7            # version from kernel.org
#   ./build-kernel.sh 6.17.7 --rust     # also enable Rust support
#
# Xenon ships Debian's signed backports kernel by default, because it boots
# with Secure Boot on. A self-built kernel is unsigned: Secure Boot must be
# off, or you must sign it with your own enrolled key (MOK).
#
# Needs: build-essential bc bison flex libssl-dev libelf-dev dwarves
#        debhelper rsync cpio kmod curl gnupg (and rustc/bindgen for --rust)
set -euo pipefail

VER="${1:?usage: build-kernel.sh VERSION [--rust]}"
RUST="${2:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$HERE/build"
MAJOR="${VER%%.*}"
mkdir -p "$WORK"
cd "$WORK"

TARBALL="linux-$VER.tar.xz"
BASE="https://cdn.kernel.org/pub/linux/kernel/v${MAJOR}.x"
if [ ! -f "$TARBALL" ]; then
    curl -fL --retry 4 -o "$TARBALL" "$BASE/$TARBALL"
fi
curl -fsSL "$BASE/sha256sums.asc" -o sha256sums.asc
grep " $TARBALL\$" sha256sums.asc | sha256sum -c -

rm -rf "linux-$VER"
tar -xf "$TARBALL"
cd "linux-$VER"

# Start from the running Debian kernel's config (or DEBIAN_CONFIG=path).
BASECONFIG="${DEBIAN_CONFIG:-/boot/config-$(uname -r)}"
cp "$BASECONFIG" .config
# Debian's config references Debian's signing keys; build without them.
scripts/config --set-str SYSTEM_TRUSTED_KEYS "" --set-str SYSTEM_REVOCATION_KEYS ""
scripts/kconfig/merge_config.sh -m .config "$HERE/xenon.config"
if [ "$RUST" = "--rust" ]; then
    scripts/config --enable RUST
fi
make olddefconfig

# Report what the fragment asked for but did not get.
while read -r line; do
    case "$line" in CONFIG_*=*) ;; *) continue ;; esac
    grep -qx "$line" .config || echo "note: $line not applied ($(grep "^${line%%=*}=" .config || echo unset))"
done < "$HERE/xenon.config"

make -j"$(nproc)" bindeb-pkg LOCALVERSION=-xenon KDEB_PKGVERSION="$VER-1xenon"
echo "Packages:"
ls -1 "$WORK"/*.deb
