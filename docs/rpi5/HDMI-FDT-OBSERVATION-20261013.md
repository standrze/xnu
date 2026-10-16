# Pi 5 standalone display handoff: physical observation

2026-10-13. The distinct `framebuffer-diagnostic-j0vcgsfv` loader passed all
19 prechecks, emitted a complete RC=0 inventory and STOP, and automatically
returned to SSD Linux. No XNU transfer, framebuffer access, property-mailbox
request, allocation, mapping, drawing or mirror enable occurred in this trial.

## Actual same-boot findings

Original FDT: 80,434 bytes at `0x0b000000`. No simple-framebuffer node was
reported. The one framebuffer-related node is `/soc@107c000000/fb`, a
`brcm,bcm2708-fb` service referencing firmware phandle `0x1a`. It supplies no
width, height, stride, format or register/address cells. This is not evidence
that scanout memory does not exist; it is not an allocation descriptor.

The original tree advertises three RAM banks: `[0,0x3f800000)`,
`[0x40000000,0x100000000)`, `[0x100000000,0x200000000)`. Fixed reservations
are `[0,0x80000)` and `[0x3fd23200,0x3fd23238)`. A 64-MiB dynamic reservation
requests a range below 1 GiB, alignment 1. It is not an allocated framebuffer,
and neither a RAM gap nor that request grants framebuffer address authority.

Next: a distinct bounded GET-only firmware display query to discover the
retained buffer facts. Do not use Linux DRM addresses, guess bus-address
conversion, infer allocation extent from visible geometry, or enable the
existing Apple renderer until format, ownership, lifetime, reservations and
cache behavior are qualified. Local keyboard support remains separate.

## Capture and recovery evidence

- Package manifest: `0e7310cd7aaa09e057e7d13538f1bb45b12e0bad11e39e8920f1c5bd94454169`.
- Probe SHA256: `4a6d4236e2ee0c13993450e77c6dcdacf6443a3b2bcaa949bcba5a7d80aa0449`.
- Installation seal: `f62b08cc1a1a0f353409f61ce09845f744d448875e14495af72ebdbcfc753339`.
- Installation plan: `c1aba19d0ecea891ae6e4ba233a189f093933938c620dab375a6fd661abc91ad`.
- Capture: `build/rpi5/framebuffer-diagnostic-serial-20261013`, 14,183 continuous
  bytes, zero host serial TX, SHA256
  `445adb23267cf9ad28eab32f4ecf63f2e7a953d3d7b801e2525579f69ca0f08b`.
- Complete observer and return-tail fault scans pass. Host receive intervals:
  ARMED to subsequent BOOTSYS 16.651 seconds; SD to NVMe selection 22.817 seconds.
  These are not exact hardware watchdog expiry measurements.
- Independent Linux boot: `0bd14821-0b05-4cde-b7ba-0216c00f7640`, root
  `/dev/nvme0n1p2`, UUID `04570742-280b-43cb-9564-73d454243b1c`.
- Original firmware/zsh restored by `framebuffer-diagnostic-restored-20261013`:
  seal `2188829311d54d1eafc36347e6a6dcb4bbb1a063ec773094949cb166af07681a`,
  plan `2856ce63dd79cf88a3d2feb43a3836f86949118f580966f0830fb4df32bb30de`,
  result `fb83d0a3ee4f9c4c70e8e7949dad1d403e3de4479b3a1dc33bde73689f31e98e`.
  Installation/restoration: 23.911 / 23.464 seconds; catalog 258 → 262 → 266.
- Full byte-only chain replay verifies capture, independent return and exact
  restoration without compiler calls or historical archive rehashing.

The earlier zero-byte observer attempt remains a failure. The later Linux
marker and this complete trial do not retroactively qualify that attempt.

## Later scanout checks

The Raspberry Pi firmware tracker documents a Pi 5 D0-specific alpha-handling
problem in an EDK2 framebuffer handoff and a subsequent bootloader correction.
That is a reason to test opaque foreground/background pixel behavior after
qualifying this board's actual format and firmware, not evidence that this Pi
is affected. Do not assume 32-bit RGB padding is ignored, or flash the old test
firmware attached to the issue. [Primary report and maintainer discussion](https://github.com/raspberrypi/firmware/issues/1971).
