#!/bin/bash
# Boot-test a Xenon ISO in QEMU, headless.
#
#   tools/test-iso.sh out/xenon-1.0-amd64.iso [results-dir]
#
# 1. Boots the live system to the GNOME desktop and saves a screenshot.
# 2. Boots again running tools/vm-selftest.sh inside the live system
#    (checks kernel features, Wine, XWS, branding) and collects its report.
#
# Uses KVM when /dev/kvm is available (much faster). Needs:
# qemu-system-x86 xorriso socat imagemagick (for PNG conversion).
set -euo pipefail

ISO="$(realpath "$1")"
RES="$(realpath -m "${2:-out/test-results}")"
TIMEOUT="${BOOT_TIMEOUT:-900}"
mkdir -p "$RES"
TMP="$(mktemp -d)"
QPID=""
# shellcheck disable=SC2317  # called via trap
cleanup() {
    local rc=$?
    if [ -n "$QPID" ]; then kill "$QPID" 2>/dev/null || true; fi
    rm -rf "$TMP"
    exit "$rc"
}
trap cleanup EXIT

echo "==> Extracting kernel and initrd"
KERNEL_PATH="$(xorriso -indev "$ISO" -find /live -name 'vmlinuz*' 2>/dev/null \
    | tr -d "'" | head -n 1)"
INITRD_PATH="$(xorriso -indev "$ISO" -find /live -name 'initrd*' 2>/dev/null \
    | tr -d "'" | head -n 1)"
xorriso -osirrox on -indev "$ISO" -extract "$KERNEL_PATH" "$TMP/vmlinuz" \
    -extract "$INITRD_PATH" "$TMP/initrd" >/dev/null 2>&1
echo "    kernel: $KERNEL_PATH  initrd: $INITRD_PATH"

ACCEL=(-accel tcg)
if [ -w /dev/kvm ]; then ACCEL=(-enable-kvm -cpu host); echo "    using KVM"; fi

boot() { # name, extra kernel args; sets QPID
    local name=$1 args=$2
    qemu-system-x86_64 "${ACCEL[@]}" -m 6144 -smp 4 -machine q35 \
        -vga virtio -display none \
        -cdrom "$ISO" -kernel "$TMP/vmlinuz" -initrd "$TMP/initrd" \
        -append "boot=live components username=xenon hostname=xenon console=ttyS0,115200 systemd.show_status=1 $args" \
        -serial "file:$RES/$name-serial.log" \
        -monitor "unix:$TMP/$name.mon,server,nowait" \
        -netdev user,id=n0 -device virtio-net-pci,netdev=n0 \
        >"$RES/$name-qemu.log" 2>&1 &
    QPID=$!
}

wait_for() { # file, regex, timeout
    local file=$1 re=$2 t=$3 i=0
    while [ $i -lt "$t" ]; do
        if grep -qE "$re" "$file" 2>/dev/null; then return 0; fi
        sleep 5; i=$((i + 5))
    done
    return 1
}

echo "==> Boot 1: desktop"
boot desktop ""
if wait_for "$RES/desktop-serial.log" "Started gdm.service|Started .*GNOME Display Manager" "$TIMEOUT"; then
    echo "    GDM started; waiting for the desktop session"
    sleep 90
    echo "screendump $TMP/desktop.ppm" | socat - "UNIX-CONNECT:$TMP/desktop.mon" >/dev/null
    sleep 3
    if command -v convert >/dev/null; then
        convert "$TMP/desktop.ppm" "$RES/desktop.png"
    else
        cp "$TMP/desktop.ppm" "$RES/desktop.ppm"
    fi
    echo "    screenshot saved"
    DESKTOP_OK=1
else
    echo "    desktop did not start within ${TIMEOUT}s"
    DESKTOP_OK=0
fi
kill "$QPID" 2>/dev/null || true
wait "$QPID" 2>/dev/null || true

echo "==> Boot 2: self-test"
boot selftest "systemd.run=/usr/lib/xenon/vm-selftest systemd.run_success_action=poweroff systemd.run_failure_action=poweroff"
if wait_for "$RES/selftest-serial.log" "XENON-SELFTEST-(PASS|FAIL)" "$TIMEOUT"; then
    sed -n '/XENON-SELFTEST-BEGIN/,/XENON-SELFTEST-\(PASS\|FAIL\)/p' "$RES/selftest-serial.log" \
        | tee "$RES/selftest.txt"
else
    echo "    self-test did not report within ${TIMEOUT}s"
fi
kill "$QPID" 2>/dev/null || true
wait "$QPID" 2>/dev/null || true

# Boots 3-5: how Windows programs (Notepad, VLC) look on the desktop in each
# window mode. Visual only: screenshots plus window details in the log.
for mode in ${GUI_MODES:-desktop windows wayland}; do
    echo "==> Boot: Windows apps on the desktop ($mode)"
    boot "gui-$mode" "xenon.selftest-gui=$mode systemd.journald.forward_to_console=1"
    if wait_for "$RES/gui-$mode-serial.log" "Started gdm.service|Started .*GNOME Display Manager" "$TIMEOUT"; then
        wait_for "$RES/gui-$mode-serial.log" "xenon-gui-selftest.*== done" 400 || true
        sleep 5
        echo "screendump $TMP/gui.ppm" | socat - "UNIX-CONNECT:$TMP/gui-$mode.mon" >/dev/null
        sleep 3
        convert "$TMP/gui.ppm" "$RES/gui-$mode.png" 2>/dev/null || cp "$TMP/gui.ppm" "$RES/gui-$mode.ppm"
        grep "xenon-gui-selftest" "$RES/gui-$mode-serial.log" | sed 's/^.*xenon-gui-selftest\[[0-9]*\]: //' \
            > "$RES/gui-$mode.txt" || true
        echo "    screenshot saved"
    else
        echo "    desktop did not start"
    fi
    kill "$QPID" 2>/dev/null || true
    wait "$QPID" 2>/dev/null || true
done

if [ "$DESKTOP_OK" = 1 ] && grep -q "XENON-SELFTEST-PASS" "$RES/selftest-serial.log"; then
    echo "==> ISO test PASSED"
    exit 0
fi
echo "==> ISO test FAILED (see $RES)"
exit 1
