# Gate 2 bring-up audit — 2026-09-25

## PID 1 hardware milestone — 2026-09-26

The Pi 5 (8 GiB) has booted the single-core XNU kernel through BSD root
mount, devfs, and freestanding `/sbin/launchd` as PID 1. Receive-only UART
capture `build/rpi5/serial-capture-pztcbncq/serial.bin` contains
`XNU-RPI5 USERSPACE PID1 OK` and 105 one-second `PID1 TICK` messages.
The subsequent 75-second capture `serial-capture-j7u6bbm2/serial.bin`
contains eight more ticks and the expected diagnostic-watchdog reboot to
NVMe Linux, with no XNU panic. Each tick follows a successful timed `select`
syscall and `/dev/console` write. A repeat boot of the identical SD image in
`serial-capture-kg4s73m6/serial.bin` reached the same marker and recorded 88
ticks with no panic; the Pi again returned to NVMe Linux after the capture.

The working SD image is `build/rpi5/bl33-probe-lpaapfr8/probe.bin` (SHA-256
`78b118f2f1f18f7dd4aaa7dab27166b363b2ef34df4eeab0bebe0edd54f15e4b`).
The linked kernel SHA-256 is
`712117292160413a01cbc6eda7e555325f19adf6451767dcee56177b6ae0053c`.
Three fresh Xcode 27 builds produced that exact kernel hash. The final build
manifest `build/rpi5-xcode27/run-9_m8gs9j/manifest.json` records unchanged
source and its per-file hashes against Git base revision
`ac9718fb1af618d5ce8678d0dc6e8a58f252216f`; it is an explicitly dirty
downstream source tree, not a committed upstream revision. The final kernel,
matching dSYM, and link map are under
`build/rpi5-xcode27/fresh-gu8trr0r/obj/DEVELOPMENT_ARM64_BCM2712/`.
The kernel and dSYM UUID both equal
`19B26FBB-973F-334B-B8A8-043932553FAC`; the link map SHA-256 is
`58e3bfb9430e70f4213f269ab1bf475841d4c33d9d2dfcf437f2586e3b4236ea`.
Host tests pass 210/210.

The final faults on this path were missing IOMedia class registration on a
RAMDisk-only boot and a null AMFI entitlement provider. BCM2712-only IOKit
guards permit the no-media-parent case, and the absent-AMFI entitlement
queries fail closed. These are DEVELOPMENT bring-up policies, not production
security. The Gate 2 functional exit is met twice on hardware: reproducible
one-core XNU boot, working console/syscalls/timers, and live PID 1. The finite
120-second diagnostic watchdog intentionally returns the test board to NVMe
Linux; removing that test limit, qualifying the pinned Xcode 26.6 toolchain,
and building a durable headless installation remain later work.

## Earlier hardware checkpoint — 2026-09-26

Gate 2 is still open: no PID 1 marker or timed userspace survival has been
observed. The pinned libpthread source is now linked, and the Pi boot trace
`build/rpi5/serial-capture-bpdb3g9t/serial.bin` proves registration before
IOKit lockdown, successful `pthread_init`, repeated timer interrupts, BSD
network setup, and `BSD root: md0, major 1, minor 0`. An earlier trace
`serial-capture-4l0lhcez` caught a late permanent-sysctl registration panic;
the provider adaptation now relies on XNU's automatic registration instead.

The current stop is `IOService::setRootMedia` asserting that the
`IOBlockStorageDriver` metaclass exists, even though the explicitly selected
RAMDisk root has no IOService media object. A BCM2712-only assertion guard now
allows the null-root RAMDisk case but still requires that class for a real
media service. Fresh kernel build
`build/rpi5-xcode27/run-jlxfzq5g/manifest.json` passed with source unchanged;
its kernel SHA-256 is
`15ac50aec6b0d300c975ecf2978f4713f4dc16856fd2488d4e6e0ad6c81ea1bb`.
The packaged image is `build/rpi5/bl33-probe-6_sf43_l/probe.bin`, and host
Mach-O/container validation passes (18 segments, 93,934 relocations). That
assertion guard was hardware-validated by
`build/rpi5/serial-capture-m45dvtri/serial.bin`: it reached the next
assumption, `publishHiddenMedia` asserting that the `IOMedia` metaclass
exists. The Pi-only RAMDisk path now also tolerates that missing class when
there is no media parent, while clearing the hidden-media state. A fresh
build `run-nctgqo0m/manifest.json` (kernel SHA-256
`72555c6b1d7616fcce0de48230b403d30865b0bb2becc239351d7b2073591018`)
and container `bl33-probe-f68d4qdi/probe.bin` pass host validation. That
second guard has not yet been hardware-validated. The Pi returned to NVMe
Linux after the previous panic; the full host suite passes 209/209.

## Host checkpoint — watchdog and pthread source

The first combined pthread/watchdog SD run is
`build/rpi5/serial-capture-sm3ppzqg/serial.bin`. The loader reached the
new Apple tree but rejected it before XNU: the three Device ranges were
encoded as UART, GIC, watchdog rather than ascending UART, watchdog, GIC.
Linux fallback booted. The range order is corrected in `probe_main.c`, and
the exact three-range ordering now has a compiled regression test. This run
does not validate pthread registration or watchdog servicing on hardware.

The Pi-only diagnostic watchdog takeover now carries an exact runtime-FDT
watchdog range into the Apple DT, validates it in XNU, and services an
already-armed full-reset watchdog only on verified CPU 0 timer IRQ 27. It
reloads no more often than every five seconds and stops after 120 seconds or
24 writes; it never changes reset routing. A fresh Xcode 27 kernel build
passed with unchanged source: `build/rpi5-xcode27/run-6x5sugk1/manifest.json`
and kernel SHA-256
`257742a97b6279752bbc2779cb5d7e042caa942d34f3173e5a4f9ed8c0c63d06`.
The corresponding `build/rpi5/bl33-probe-9zybltbq` kernel/PID1 container
passes the native Mach-O/materialization comparison (18 segments and 93,867
local relocations). The 200 host tooling tests passed at that checkpoint.
The watchdog image was then installed for the combined run, but loader
rejection prevented XNU from exercising it.

An isolated source adaptation of the pinned libpthread kernel provider has
compiled all three arm64 objects with `-Werror` and no diagnostics; see
`build/rpi5-xcode27/pthread-gate2/manifest.json`. A crucial ABI adjustment
removes the old source's 56-byte `ksyn_waitq_element` use in favor of XNU's
48-byte slot; the old cached uthread is derived from the retained thread at
its three read sites. The adapted object has no duplicate defined globals
against the latest kernel. That scratch checkpoint was compile evidence only.
Subsequently, the checked-in provider builder and explicit link path produced
a fresh kernel with `_pthread_start`, `_pthread_internal_functions`, and a
separate `_rpi5_pthread_kern` callback pointer; BSD's linked instructions call
`_pthread_start` immediately before `_pthread_init`. The fresh build manifest
is `build/rpi5-xcode27/run-oq9sgnl6/manifest.json`. Pi runtime validation is
still absent because the first combined SD run failed in the loader as above.

## Hardware update — 2026-09-25/26

Gate 2 remains open. The Pi 5 (8 GiB) now reaches BSD initialization with
working repeated GICv2 virtual-timer interrupts; it has not mounted md0 or
started PID 1. The latest raw receive-only serial capture is
`build/rpi5/serial-capture-x_ayz9u8/serial.bin`. Its Pi-only markers show
`BCM2712 MAX_CPUS READY count=4`, `START BSD_INIT`, `IORTC wait deferred`,
and BSD progress through `aio_init`. It then panics at
`bsd/pthread/pthread_shims.c:319`: the pthread-kext function table is NULL.
The expected `XNU-RPI5 USERSPACE PID1 OK` marker is absent. The 8 GiB board
returned to the NVMe Linux fallback after each watchdog/reboot run.

Two concrete startup stalls were resolved in DEVELOPMENT-only Pi paths:
`kperf_init_early()` previously slept in `ml_wait_max_cpus()` because this
single-core port does not yet instantiate the normal IOCPU interrupt
controller; `startup.c` now publishes the already-fixed topology count before
that wait. `IOKitInitializeTime()` previously waited up to 30 seconds for an
unimplemented IORTC service, longer than the board's recovery watchdog; it
now defers that wait for BCM2712 DEVELOPMENT while still initializing calendar
time. `DEBUG_BSDINIT` is enabled only for that target to locate subsequent
boundaries. These are bring-up adaptations, not completed CPU/RTC drivers.

The latest linked kernel is
`build/rpi5-xcode27/fresh-z68qzrp8/obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712`
(SHA-256 `b8359814bfd74601a7141cffd160eb4b710252ad2e20d71d59ef1b4a80658ad8`),
with build manifest `build/rpi5-xcode27/run-t_bm0vdz/manifest.json`.
The packaged SD probe is `build/rpi5/bl33-probe-z3q0lvao/probe.bin`
(SHA-256 `3d87a6ccfcc1f9a7f8fbddddac62d81bab8bad2f8aa14e2979fd846e3b77c720`).
The native Mach-O/container comparison passes (18 segments, 93,867 local
relocations). The earlier 199 host tooling tests passed after the RTC-wait
change; the current suite has 200 passing tests after watchdog work.
The next gate task is to integrate the matching public libpthread kernel
provider and verify its complete function table and startup order, without
masking the panic with no-op callbacks. Apple's macOS 26.5 source release
pairs XNU 12377.121.6 with libpthread 539.100.4. That tag is pinned for
Gate 2 separately in `tools/rpi5/gate2-pthread.lock.json` at commit
`1f4f5265b319111142f1bf3a27d4484ef5a98314`; its source archive SHA-256
is `c815492b81044b1cf8d53b124a9ac9503697439e96325daac982adad934d7cd4`.
Inspection of its `kern/kern_init.c` shows a real registration table; its
default version 0 matches the older `bsdthread_register` entry it supplies,
while XNU's version-1 path requires `bsdthread_register2`. No kernel build has
yet linked this source, and the provider remains unvalidated on hardware.
Isolated Xcode 27 compile probes of all three `libpthread/kern/*.c` files
currently fail before producing objects: a private-header guard collides with
XNU's header, one include order exposes an unresolved `thread_t` parse error,
and a VM unslide helper's argument type has changed. These require an explicit
compatibility layer or source adaptation before link and startup work. The
version-0 function table must remain version 0 unless the version-1
`bsdthread_register2` callback is actually implemented.
The pinned source's v0 `bsdthread_register` expects legacy arguments, while
current XNU's syscall has a newer seven-argument shape. Gate 2's static PID 1
does not use libpthread, but later Darwin userspace needs an explicit ABI
decision rather than assuming the matched source tag is drop-in compatible.

Gate 2 remains open. The proven Gate 1 kernel reaches
`Unable to find driver for this platform: "device-tree"` in
`IOPanicPlatform::start`. The fallback personality is in
`iokit/KernelConfigTables.cpp`; the tree comes from the loader's
`rpi5_board_tree_init`.

## First implementation checkpoint

The loader's Apple tree now identifies the Pi 5/BCM2712 at the root and marks
each CPU node `device_type=cpu`, preserving its physical MPIDR affinity in
`reg`. A BCM2712 DEVELOPMENT-only `IODTPlatformExpert` subclass and higher-score
personality require that exact root identity. It publishes CPU and `arm-io`
platform nubs without inventing `/options` or a persistent NVRAM controller.
The ordinary `IODTPlatformExpert::processTopLevel` requires an NVRAM entry, so
the Pi subclass deliberately avoids that call and retains `not ready` NVRAM
behavior. Non-Pi personality selection remains the existing fallback.

Host tooling tests pass 185/185, including compiled personality selection in
Pi DEVELOPMENT, Pi RELEASE, and non-Pi configurations. A new terminal-transfer
BL33 probe built from the updated tree source in
`build/rpi5/bl33-probe-jcf49v7q`; its embedded Gate 1
kernel passes the native Mach-O/materialization comparison (18 segments,
93,496 relocations, 17,416,192 copied bytes). This is source/host evidence,
not a new Pi boot. An isolated compile of `BCM2712PlatformExpert.cpp` using the
recorded Gate 1 IOKit compile arguments, current Clang 27, and the preserved
SDK 26.5 completed without diagnostics. This checks source compatibility only;
it is not a canonical kernel link or hardware result. The SD card and Pi were
not changed for this checkpoint.

The BCM2712 DEVELOPMENT mockfs mount now chooses ordinary md0 read/pagein
instead of its direct contiguous pager mapping. That mapping used a truncated
base and mixed 4-KiB device units with 16-KiB VM pages; merely skipping the
mapping without clearing the mount flag would have caused mockfs's pagein
panic. The RAM device now widens page counts before byte conversion, checks
block-offset/EOF arithmetic, bounds character reads, and preserves exact-EOF
behavior. These changes have focused compiled host tests. Isolated object
compiles of `mockfs_vfsops.c` and `memdev.c` using the recorded Gate 1 flags,
Clang 27, and SDK 26.5 also pass. They have not been linked into XNU or
exercised with a real `/chosen/memory-map/RAMDisk`; no PID 1 result is claimed.

## Build and runtime blockers

The pinned kernel toolchain is Xcode 26.6 (`17F113`) with SDK 26.5, and the
project-owned prepared SDK records that provenance. The installed Xcode.app is
now 27.0 (`27A266a`) with SDK 27.0. `rpi5.py doctor` rejects it, and the
opt-in exploratory build also stops at the prepared SDK provenance check.
Do not overwrite the retained 26.6 SDK/manifest or relabel it as a 27.0 build.
Restore the pinned toolchain or separately prepare and qualify 27.0 before
claiming a kernel compile or installing a new SD probe.

Once built, the platform expert still needs a serial-captured hardware run.
The next likely boundaries are XNU's actual CPU-device service, GICv2 Group 1
IRQ path, and virtual timer INTID 27; the standalone loader probe does not
provide those as XNU drivers. On this BCM2712 configuration
`USE_APPLEARMSMP` is off, so the active CPU lifecycle is `IOCPU.cpp`'s
non-AppleARMSMP path. A separate RAM-backed PID 1 depends on the timer,
console, and mockfs work in `PLAN.md`; no userspace boot is claimed.
The `DKIOCGETMEMDEVINFO` base field is still 32-bit; the Pi development path
does not use it for direct paging. Full-width md0 ownership and virtual mapping
still require hardware validation.
