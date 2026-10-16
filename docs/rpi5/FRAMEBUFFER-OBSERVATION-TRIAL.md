# Same-boot framebuffer observation — no display writes

2026-10-13. This is a distinct, small BL33 diagnostic, not an XNU or HDMI
acceptance image. It uses the original firmware-provided FDT and never imports
Linux DRM addresses into another boot. The firmware remains unchanged.

## Frozen package

`build/rpi5/framebuffer-observe-9dayrxtr`

- Manifest SHA256: `686936c9106618352ce51248af0c46248ada22ad43b506d3bd9527cd9f09d964`
- `probe.bin`: 49,472 bytes; SHA256 `8b4da467e8b95d19a7479303d03cdcf5b2e3c300dec7a6a66f0a33508567b616`
- Exact tag: `4b316bd6039d4e6f8f52df866a38414a`
- Original entry assembly and EL2→EL1 transition; primary CPU only, secondary
  affinity queries but no CPU_ON call. No kernel or root payload.
- Actual A76 freestanding link, no undefined symbols or dynamic loader. Every
  compiler's pre-scan and actual `.d` headers, tools, sources and generated
  outputs are recorded and byte-checked.
- All linked C stack frames conservatively summed: 14,208 bytes, plus a
  512-byte assembly/alignment margin, within the unchanged 16 KiB stack.
  Caller-supplied non-aliasing scratch preserves atomic public output without
  placing the complete inventory on the EL1 stack.

Only UART normalization and one countdown write to an **already active**
supported watchdog are permitted. Reset routing/RSTS are unchanged. Countdown
is shortened once to 15 seconds; the output path has an 8-second software
deadline, 32 KiB byte cap and finite UART polling budget. There is no later
watchdog reload. Physical recovery and its destination are not proved by a
successful build.

## What the records mean

The bounded `RPI5XNU:FBOBS:` records inventory RAM and fixed/dynamic reservation
declarations, exact live loader/FDT extents, selected framebuffer-related
properties, raw `reg` cells, and actual EL1 SCTLR/DAIF facts. Unknown FDT payloads
such as boot arguments or RNG seeds are not printed.

The official Pi5 DTS declares a firmware framebuffer provider. In the pinned
compiled DTB its path is `/soc@107c000000/fb`, compatible with
`brcm,bcm2708-fb`, referencing the firmware service. This is **not** a physical
framebuffer allocation. See the [official BCM2712 source](https://github.com/raspberrypi/linux/blob/43c132e8863c3bff3647033b6a7d2bf87b15501c/arch/arm64/boot/dts/broadcom/bcm2712-rpi.dtsi).
The pinned DTB fixture contains one such provider and no simplefb descriptor;
that offline fixture is not the user's current boot.

An actual `simple-framebuffer` declaration is independently parsed by the
frozen narrow geometry helper. Its rejection does not suppress bounded raw
width/height/pitch/format/reg facts. For example, a 3840×2160 descriptor exceeds
the initial 1920×1080 drawing limit and remains **unsupported**, not silently
accepted. ARGB is not labeled Apple-renderer-compatible. Fixed reservation
overlap may be the firmware's own reservation, so it is reported rather than
misclassified as free memory.

Every output explicitly keeps framebuffer ownership and scanout cache contract
unproved. CPU MMU/cache-off state does not establish the later Apple mapping
or display coherence. No mailbox request, allocation, framebuffer load/store,
mode change, mapping, drawing, or console mirror enable occurs.

## Separate publication and evidence contract

`stage_framebuffer_observation_trial_v2.py` reuses the unchanged generic
`active_archive_loader_v2` publisher: fresh exact SSD boot/root/card identity,
unmounted target, original normal firmware, protected files, raw snapshot,
current rollback and known-good rollback checks remain mandatory. Only
`probe.bin` is replaced. The new fixed controller accepts only this exact
manifest/image/tag, not a dynamic checker or arbitrary observer descriptor.

`serial_framebuffer_observation_trial_v2.py` owns one exclusively opened UART
session, records every RX byte with a gap-free timestamp journal, and never
transmits. `arm_framebuffer_observation_reboot_v2.py` starts that exact recorder,
requires its still-live ARMED receipt, persists one-shot intent, then verifies
the exact SSD boot/root and invokes one reboot in the same SSH process. An
unknown outcome is never a reason to retry.

The dedicated evidence oracle requires a fresh SD boot, the exact tagged
ENTRY/ARMED/EL1/LIVE/inventory/RESULT/STOP sequence, then the firmware's f6
override and normal NVMe selection. It checks the complete runtime interval
through the final captured RX chunk, including faults after STOP, after the
next BOOTSYS, and after NVMe selection within that final chunk. Return-firmware
faults are labeled separately but also fail the trial. Host RX bounds are
ARMED→BOOTSYS under 30 seconds and SD→NVMe under 150 seconds, not claims about
exact electrical reset expiry. An incomplete or faulted observation remains
failed even if independent Linux recovery succeeds.

Independent SSH subsequently verifies a different Linux boot UUID, exact
NVMe root and card, normal boot properties, and unmounted SD partitions. Only
then is an explicit restoration prepared. All capture bytes, timestamps,
receipts, source pins and the explicit restoration are retained. No old
PCIe/XNU marker is invented or reused as FBOBS acceptance.

## Offline validation

```
python3 -m unittest tools.rpi5.tests.test_framebuffer_observation \
  tools.rpi5.tests.test_framebuffer_observation_guard \
  tools.rpi5.tests.test_framebuffer_observation_serial -v

RPI5_FB_OBSERVATION_PACKAGE=build/rpi5/framebuffer-observe-9dayrxtr \
  python3 -m unittest tools.rpi5.tests.test_framebuffer_observation_package -v

python3 -m unittest tools.rpi5.tests.test_framebuffer_observation_transport_v2 \
  tools.rpi5.tests.test_arm_pcie_trace_reboot -v
```

Seven helper/guard/protocol groups passed in 3.441 seconds; four package and
actual-report/native-record groups passed in 2.898 seconds. Fourteen combined
v2 transport and one-shot reboot groups passed in 12.244 seconds, including the
actual 250-artifact prior restoration intake, real receive-only body under
explicit UART/clock doubles, complete RX journal, post-STOP and four return-tail
panic/FAULT cases, independent
Linux witness, and no-retry/wrong-root/wrong-boot controls. These are software
tests, not physical scanout or display ownership evidence. The first v1
integration/seal is retained unused; only v2 includes the complete return-tail
fault qualification. The v2 once-audited preparation is
`build/rpi5/framebuffer-observation-prepared-v2-20261013`, canonical checkpoint
`97c63c8f76c7515fc960bb8dc1b1d0afd0abd57986944aa9c0d0571535f8cdb0`.

Next physical evidence must determine whether a usable retained descriptor is
actually supplied. Any mapping/drawing package then needs independently
checked ownership/reservation/cache handoff and visible confirmation before
the already-tested, default-off Apple renderer mirror can be published.
