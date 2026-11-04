# Xenon kernel

## Today: Debian's signed backports kernel

The ISO installs `linux-image-amd64` from `trixie-backports`, pinned in
`/etc/apt/preferences.d/xenon-backports`. It is signed for Secure Boot,
includes NTSYNC (Linux ≥ 6.14), binfmt_misc, ext4 casefold and
`PREEMPT_DYNAMIC`, and Debian maintains it. Xenon adds:

| Setting | Where |
|---|---|
| `preempt=full` (low latency) | `/etc/default/grub.d/xenon.cfg` |
| `ntsync` loaded at boot, `/dev/ntsync` for the logged-in user | `xenon-xws` |
| `vm.max_map_count`, `kernel.split_lock_mitigate`, zram tuning | `/usr/lib/sysctl.d/90-xenon.conf` |

See `docs/DECISIONS.md` for why this is the default.

## Optional: build a Xenon kernel

`xenon.config` is a fragment applied on top of Debian's configuration
(1000 Hz tick, sched_ext, BTF, and optionally Rust).

```bash
sudo apt install build-essential bc bison flex libssl-dev libelf-dev dwarves \
  debhelper rsync cpio kmod curl
./build-kernel.sh 6.17.7          # any kernel.org stable version
sudo apt install ./build/linux-image-*-xenon_*.deb
```

The script verifies the tarball against kernel.org's `sha256sums.asc` and
reports any fragment option the kernel didn't accept. Self-built kernels
are **unsigned**: turn Secure Boot off or sign the kernel with an enrolled
MOK.

## Phase 3+: kernel work in Rust

Kernel work only happens when profiling shows a real bottleneck. Candidates:

1. **Measure first.** `perf` and `bpftrace` on Wine games, looking at
   wineserver round-trips, NTSYNC calls, futex waits and page faults.
2. **NT-style fast paths.** If profiling shows syscall-heavy Windows APIs
   that Wine routes through wineserver, investigate a Rust kernel module
   exposing them directly. That's the same approach NTSYNC took, and it
   should be designed with Wine upstream so it gets used.
3. **sched_ext.** Evaluate `scx_lavd` / `scx_bpfland` for frame-time
   consistency against EEVDF. If one wins, ship it as an optional
   userspace scheduler service (no custom kernel needed).

All kernel code is GPL-2.0 and should be upstreamed where possible.
