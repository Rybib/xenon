#!/bin/bash
# Build and sign the Xenon APT repository from a directory of .debs.
#
#   tools/build-apt-repo.sh DEB_DIR OUT_DIR KEY_ID
#
# OUT_DIR becomes the web root published on GitHub Pages:
#   OUT_DIR/apt/dists/stable/{InRelease,Release,Release.gpg,main/...}
#   OUT_DIR/apt/pool/main/*.deb
#   OUT_DIR/xenon-archive-keyring.asc   (the public key, for reference)
# The signing key must already be in the gpg keyring (KEY_ID = fingerprint).
# Needs: apt-utils (apt-ftparchive), gnupg, xz-utils.
set -euo pipefail

DEBS="$(realpath "$1")"
OUT="$(realpath -m "$2")"
KEY="$3"
SUITE=stable

REPO="$OUT/apt"
mkdir -p "$REPO/pool/main" "$REPO/dists/$SUITE/main/binary-amd64"
cp "$DEBS"/*.deb "$REPO/pool/main/"

cd "$REPO"
apt-ftparchive packages pool/main > "dists/$SUITE/main/binary-amd64/Packages"
gzip -9nk "dists/$SUITE/main/binary-amd64/Packages"
xz -9k "dists/$SUITE/main/binary-amd64/Packages"

apt-ftparchive \
    -o APT::FTPArchive::Release::Origin=Xenon \
    -o APT::FTPArchive::Release::Label=Xenon \
    -o APT::FTPArchive::Release::Suite="$SUITE" \
    -o APT::FTPArchive::Release::Codename="$SUITE" \
    -o APT::FTPArchive::Release::Architectures=amd64 \
    -o APT::FTPArchive::Release::Components=main \
    -o APT::FTPArchive::Release::Description="Xenon updates" \
    release "dists/$SUITE" > "dists/$SUITE/Release"

gpg --batch --yes --local-user "$KEY" --clearsign \
    -o "dists/$SUITE/InRelease" "dists/$SUITE/Release"
gpg --batch --yes --local-user "$KEY" --armor --detach-sign \
    -o "dists/$SUITE/Release.gpg" "dists/$SUITE/Release"

gpg --armor --export "$KEY" > "$OUT/xenon-archive-keyring.asc"
cat > "$OUT/index.html" <<EOF
<!DOCTYPE html>
<html lang="en"><meta charset="utf-8"><title>Xenon updates</title>
<body style="font-family:system-ui;max-width:40rem;margin:3rem auto;padding:0 1rem">
<h1>Xenon update repository</h1>
<p>Xenon installs receive updates from here automatically.
Source code: <a href="https://github.com/Rybib/xenon">github.com/Rybib/xenon</a>.</p>
<p>Signing key: <a href="xenon-archive-keyring.asc">xenon-archive-keyring.asc</a>
(fingerprint <code>$KEY</code>).</p>
<p>Packages in this build:</p>
<pre>$(find "$REPO/pool/main" -name '*.deb' -printf '%f\n' | sort)</pre>
</body></html>
EOF
touch "$OUT/.nojekyll"
echo "Repository ready in $OUT"
