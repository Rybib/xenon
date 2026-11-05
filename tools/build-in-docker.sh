#!/bin/bash
# Build the Xenon ISO inside a Debian 13 container, from any Linux host
# with Docker (or Podman with `alias docker=podman`).
#
#   tools/build-in-docker.sh
#
# live-build needs to mount /proc etc. inside its chroot, hence --privileged.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec docker run --rm --privileged \
    -e XENON_VERSION="${XENON_VERSION:-1.0}" \
    -e XENON_MIRROR="${XENON_MIRROR:-http://deb.debian.org/debian}" \
    -e XENON_VERSION_SUFFIX \
    -e XENON_REPO_KEY \
    -v "$ROOT:/xenon" -w /xenon \
    debian:trixie ./build-iso.sh
