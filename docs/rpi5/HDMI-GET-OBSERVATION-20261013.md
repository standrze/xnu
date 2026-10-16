# Actual standalone firmware display query — 2026-10-13

The distinct GET-only package `display-query-7m77tyrn` passed on the Pi.
All 19 prechecks and the bounded mailbox transaction completed, followed by
automatic NVMe return, independent SSD Linux verification, original working
loader restoration and full byte-only chain replay. No framebuffer allocation,
SET request, mapping, drawing, XNU transfer or host serial input occurred.

## Observed reply

COUNT returns one display. The complete 16-word SETTINGS reply is:

```
00000000 00000780 00000438 00000010
00000f00 00000780 00000438 00000000
00000000 00000000 00000000 00000000
00000000 00000000 00000000 00000000
```

The leading values are consistent with the preserved Linux display-settings
fields: display0, width1920, height1080, depth16, pitch3840, virtual1920×1080,
zero offsets. Every later word is zero, including both plausible native-width
address positions. This is **not** a nonzero framebuffer descriptor or proof
of RGB565 layout, allocation extent, address conversion or scanout ownership.
No buffer address may be guessed from RAM gaps or Linux DRM state.

Actual fresh FDT binding resolves mailbox `[0x107c013880,0x107c0138c0)`,
firmware phandle26 and mailbox phandle34. Linked request pages are
`[0x9010000,0x9013000)`, within retained image `[0x9000000,0x913fc10)` and
outside the whole secure FDT mapping. Both requests have matching PEEK/POP
words and complete validated responses. Actual counts: two requests, two pops,
seven page-cache operations, 16 MMIO reads, four polls, 74 callbacks and zero
quarantine. The core elapsed interval is 100,573 microseconds, within its
1-second deadline; it is not a display timing or frequency measurement.

## Exact receipts

- Package manifest: `235386b7b60ee870d86becc1f922c9b0219781824ab0a7a1f49c2c935b84b2df`.
- Probe: 59,456 bytes, SHA `ccd94caac86ea0ef0696631795c2c0630b4df3d711cd2461bd60944f6f733916`.
- TAG: `34a3d8fd702141d992c4da5ab5ff1dc3`.
- Install `display-query-installed-20261013`: seal
  `c31e74c60c5f82e2c2db269895781bf2e0a0d397574b99690260651fe82e25c5`,
  plan `90f4b9754a836ceb8773ab926fba901387ff8b796114020ab833b80e65e27345`,
  result `555f5efe0d33b8847c3aef1e80a4aa2a65fcd2a5e2414b7b58a8bff5a7bd383a`.
- Capture `build/rpi5/display-query-capture-20261013`: 14,750 continuous bytes,
  zero TX, SHA `139a5ee1607deeaa18fd963d5a5e619bbdfd2bd4df738bf1f7c416122049db0f`,
  ended `2026-10-13T22:51:40.141171+00:00`. Full-capture fault checks include
  the complete received tail after STOP through normal NVMe selection.
- Host receive intervals: ARMED→BOOTSYS16.653s, SD→NVMe22.962s; not exact
  hardware watchdog expiry measurements.
- Independent SSD Linux boot `6cf18813-d9c9-471f-8584-fffd11358c0a`, root
  `/dev/nvme0n1p2`, UUID `04570742-280b-43cb-9564-73d454243b1c`.
- Restore `display-query-restored-20261013`: seal
  `890ce08b574326dfea18fcb43f3831c4146c60ed102676157f50c7797ac01d1a`,
  plan `7972663e087d115a1f02b20fa81fc3f0ca1fb4b2eb96ea3429f6ec26ff46756e`,
  result `e9a23ec85aba800a86d2eab3b6305685102301f1e269f47441c2e3b94fb3e427`.
- Normal firmware remains `413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46`;
  working zsh probe is restored to `f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536`.
- Catalog286→290→294; install/restore23.684/23.750s. Once-audit preparation
 12.207s; 28,228 files, 155 recorder sources and 4,859 package members.
  Main14 transport tests pass28.677s; independent byte-only admission passes
  with compiler/history/transport calls disabled. Full replay passes without
  compiler calls or historical archive rehashing.

Next: a distinct bounded firmware framebuffer allocation/mode transaction,
fresh returned address/extent/format checks, exclusion from all live allocations
and cache/lifetime handoff. Prefer a qualified32-bit console mode; no drawing
or Apple renderer activation until those requirements are met. Local USB
keyboard remains separate; serial input can continue to serve the shell.
