#!/bin/bash
# Download the pinned DXVK, VKD3D-Proton and winetricks releases into
# payload/. Verifies SHA256 when pinned in versions.env; otherwise prints
# the hashes so they can be pinned.
set -euo pipefail
cd "$(dirname "$0")"
# shellcheck source=versions.env
. ./versions.env

mkdir -p payload downloads
fetch() { # url file sha
    local url=$1 out=downloads/$2 sha=${3:-}
    if [ ! -f "$out" ]; then
        if ! curl -fsSL --retry 4 -o "$out.part" "$url"; then
            echo "download failed: $url" >&2
            exit 1
        fi
        mv "$out.part" "$out"
    fi
    local got
    got=$(sha256sum "$out" | cut -d' ' -f1)
    if [ -n "$sha" ] && [ "$sha" != "$got" ]; then
        echo "SHA256 mismatch for $2: expected $sha got $got" >&2
        exit 1
    fi
    echo "$2 sha256=$got"
}

fetch "https://github.com/doitsujin/dxvk/releases/download/v${DXVK_VERSION}/dxvk-${DXVK_VERSION}.tar.gz" \
    "dxvk-${DXVK_VERSION}.tar.gz" "${DXVK_SHA256:-}"
fetch "https://github.com/HansKristian-Work/vkd3d-proton/releases/download/v${VKD3D_PROTON_VERSION}/vkd3d-proton-${VKD3D_PROTON_VERSION}.tar.zst" \
    "vkd3d-proton-${VKD3D_PROTON_VERSION}.tar.zst" "${VKD3D_PROTON_SHA256:-}"
fetch "https://raw.githubusercontent.com/Winetricks/winetricks/${WINETRICKS_VERSION}/src/winetricks" \
    "winetricks-${WINETRICKS_VERSION}" "${WINETRICKS_SHA256:-}"
fetch "https://raw.githubusercontent.com/doitsujin/dxvk/v${DXVK_VERSION}/LICENSE" \
    "dxvk-LICENSE"
fetch "https://raw.githubusercontent.com/HansKristian-Work/vkd3d-proton/v${VKD3D_PROTON_VERSION}/LICENSE" \
    "vkd3d-proton-LICENSE"
fetch "https://raw.githubusercontent.com/Winetricks/winetricks/${WINETRICKS_VERSION}/COPYING" \
    "winetricks-COPYING"

rm -rf payload/dxvk payload/vkd3d-proton
mkdir -p payload/dxvk payload/vkd3d-proton
tar -xzf "downloads/dxvk-${DXVK_VERSION}.tar.gz" -C payload/dxvk --strip-components=1
tar --zstd -xf "downloads/vkd3d-proton-${VKD3D_PROTON_VERSION}.tar.zst" -C payload/vkd3d-proton \
    --strip-components=1
rm -f payload/vkd3d-proton/setup_vkd3d_proton.sh payload/dxvk/setup_dxvk.sh
echo "${DXVK_VERSION}" > payload/dxvk/VERSION
echo "${VKD3D_PROTON_VERSION}" > payload/vkd3d-proton/VERSION
install -m 0755 "downloads/winetricks-${WINETRICKS_VERSION}" payload/winetricks
cp downloads/dxvk-LICENSE payload/dxvk/LICENSE
cp downloads/vkd3d-proton-LICENSE payload/vkd3d-proton/LICENSE
cp downloads/winetricks-COPYING payload/winetricks-COPYING

# Sanity: the DLLs XWS deploys must exist.
for f in dxvk/x64/d3d11.dll dxvk/x64/dxgi.dll dxvk/x32/d3d9.dll \
         vkd3d-proton/x64/d3d12.dll vkd3d-proton/x86/d3d12core.dll; do
    [ -f "payload/$f" ] || { echo "missing payload/$f" >&2; exit 1; }
done
echo "payload ready"
