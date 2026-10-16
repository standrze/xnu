# Current: RAM zsh reverified; corrected USB-6 candidate ready — 2026-10-16

Gate 4 advanced offline without touching the Pi, SD card, network or serial
port. The bounded write policy is now media-profile driven: an admitted lease
retains its exact HFS start, length and maximum request size instead of using a
global range after authorization. `rpi5_sd_write_authorize_profile` checks the
sealed capacity, 15 identity CID bytes, complete CSD, MBR signature and both
partition entries, plus matching primary/alternate HFS allocation geometry.
Failure clears the lease geometry; quarantine remains irreversible.

`tools/rpi5/build_sd_write_profile.py` converts two complete, identical
read-only partition captures plus the qualified HFS fixture into a separately
compiled external profile. It rejects a changed read, geometry disagreement,
write-tainted reference or unqualified fixture. The preserved historical card
remains the default so old evidence does not change. Generated reference
`build/rpi5/sd-write-profile-20261016-v1/profile.json` has SHA-256
`c0d66d85f2fb925f45c4932ef1bc16c98c096594277b22452ad13005d2ff2c98`;
its C source SHA-256 is
`e3e971969921f9386edf6a74dc255b592f043363f68a1644f0ecb643c2ae8166`.
All 150 HFS tests and 26 focused storage build/profile/provider tests pass.
This removes the source-code hard-coding obstacle for a future disposable
card, but does not prove cache state, authorize a write or establish physical
durability. The existing card's cache-state hold remains fail-closed.

The existing XNU kernel, mockfs root, Apple zsh 5.9 and command payload are
RAM-resident after boot handoff. HDMI zsh remains proven; local input remains
UART until the new USB gates complete.

Fresh live Linux inspection on NVMe root found the real keyboard target:
Corsair K65 `1b1c:1baf`, controller 0/bus 1/port 2, with standard HID boot
keyboard interface `03/01/01`. RP1 BAR1 is `0x1f00000000..0x1f003fffff`;
the two DWC3/xHCI 1.1 windows are `0x1f00200000` and `0x1f00300000`.

USB-1 now passes on the physical Pi. The exact 55,074-byte, zero-transmit
capture SHA is
`d36f6d93bda13dcead442f04e3a52f4b91996abb1b79c4ce849128ec461f5ea2`:
16 stable reads from USB0 decode xHCI 1.1, 64 slots, four interrupters, three
ports and 64 scratchpad buffers. USB-2 also passes. Its exact 55,287-byte
capture SHA is
`c158a03c528b16c23cd06dd199b71542b36df900528a918aedd2c25218445968`:
controller 0 halted and reset with exactly two USBCMD writes, cleared HCRST/CNR
in 19 bounded polls and ended halted without a fatal status. There were no
USBSTS, port, doorbell, runtime, DMA-pointer, IRQ or BME writes. Both trials
returned automatically to NVMe, and the exact normal SD triple is restored.

`rp1_usb_xhci_caps.{h,c}`, `rp1_usb_device_handoff.{h,c}` and
`rp1_usb_xhci_lifecycle.{h,c}` implement those passed gates.
`usb_hid_boot_keyboard.{h,c}` atomically translates boot reports to terminal
bytes, including control keys, Caps Lock and ANSI arrows. It has now received
one physical interrupt-IN idle report. USB-3's retained
DCBAA/command/event/ERST/scratchpad memory and one polling command now pass on
the Pi. USB-4 has tested, freestanding software cores for a bounded
controller-0 port-2 reset, the exact K65 device/configuration GET_DESCRIPTOR
TRBs, bounded Enable Slot/Address Device contexts and completion parsing, and
strict selection of only interface `03/01/01`/endpoint `0x81`.
The physical v4 trial now passes: one port-status event, slot 1, four EP0
descriptor transfers and exact Corsair `1b1c:1baf` identity all validate while
interrupts stay disabled, BME is restored and the controller ends halted. The
37,972-byte zero-transmit capture SHA is
`22bc59d8f47d10d0bfa0542b50fd42c370c9690556c4327cc6802bdf4b4398d3`;
the strict parser report SHA is
`0d74f641f946186a1b662f265d30b1cc89df3d1a67bf3b589b98ff08760c0ee7`.
The board returned automatically to NVMe and the exact normal SD triple was
restored.

USB-5's first-report subgate now passes on the physical Pi. Package
`build/rpi5/usb-xhci-keyboard-candidate-20261015-v7` has manifest SHA
`4b73b5f4888665238fe9a4e2c666d5dc70f542ec42eda9b29ca3f960cca737fe`,
image SHA `1465c35d1aff61618009efb824a998ea7c5a9ea2d977460d9243bf673a9dbf11`
and kernel SHA
`fe24ee49b68a239305a9093dfbb55b98117ff70650665331c5dae9d27506961e`.
Its 38,442-byte zero-transmit capture SHA is
`8d87fd92e21062a82b5935540e62057a37b07f684282416b6b1f1093703444c2`;
the strict parser report SHA is
`bbeae295c258f1fe465c1354f51faac048fa62fc16f6e4abb3c7dfdcd0dc53da`.
All three HID setup transfers, Configure Endpoint and one 8-byte DCI-3
interrupt transfer completed. The periodic idle report was all zero and
decoded to zero bytes. The controller halted, BME was restored, Linux returned
and the normal triple was restored in
`usb-xhci-keyboard-restored-20261015-v5` with result SHA
`a1ee4d8b337aed0b0d5fe5db5c7ef78ac94528a47451c1c7616cab2791ef41a9`.

USB-6 is now the priority. Its software core uses SET_IDLE(0), 255 disjoint
report buffers, cyclic transfer and event rings, persistent HID decoder state
and an atomic decoded-byte callback into `cons_cinput`. The first v9 and v11
physical console attempts reached XNU but panicked before USB startup because
their inherited early IOKit dispatch raced platform-expert matching. Both
failed images remain evidence; the exact normal image was restored after each.
The corrected package
`build/rpi5/usb-xhci-keyboard-console-candidate-20261016-v13` restores the
physically proven `IOStartIOKit.cpo` and dispatches only from `IOKitBSDInit`,
after `IOBSD` publication. It passes its independent fail-closed checker:
manifest SHA
`8c5e9111a40399bdeb277663cda71206bd5ad5fa5ccb8c91b2917a988c0a8e3a`,
image SHA `d3b6b4736d61893fe6709fb81f6aecdd529087dae05bd18a9451d6672edc6a84`
and kernel SHA
`2d8886392d960cc62317abefacc8dba98357239deb4c1a34727c1a712dd7aa80`.
The focused nine-test startup/console/checker set passes. The v13 image is not
staged and has not run on the Pi. No repeated physical keypress, console
injection or keyboard-only HDMI/zsh session has passed yet.
Exact-hash guarded stage and restore wrappers are ready; both preserve full raw
SD backups and never reboot on their own.
The exact normal image was separately reverified on the Pi: all four CPUs came
online, the 32-node read-only RAM root mounted, and `RPI5XNU:SHELL:READY`
reached the HDMI/UART console. That root has no reboot utility, and XNU
correctly rejected a PID-1 signal attempt, so one physical return to NVMe Linux
is required before v13 can be staged.
The exact source boundary and six-gate board sequence are in
[USB-KEYBOARD.md](USB-KEYBOARD.md).

The USB-3 software core is now complete through a single polling command:
`BCM2712USBXHCIMemory` retains a private `0x50000` Apple
`IOBufferMemoryDescriptor`/`IODMACommand`, proves twenty Normal-NC pages and the
live preferred RP1 DMA route, and constructs the exact xHCI layout without
publishing it to hardware. `rp1_usb_xhci_noop` creates the DCBAA, 64 scratchpad
pointers, No-Op/Link TRBs, event ring and ERST. `rp1_usb_xhci_noop_run` programs
only the required pointer/runtime registers, starts with interrupts disabled,
rings doorbell zero, validates an exact Command Completion Event and halts.
`rp1_usb_bme` leases only RP1 PCI COMMAND bit 2 and restores the original
command word. Sanitizer fault matrices and A76 freestanding compilation pass.
The passing USB-3 board image is
`build/rpi5/usb-xhci-noop-candidate-20261015-v11`, manifest SHA
`044d6a63897f8318bbe403b2c55dd7a9836eab6b5383b4963238c0e3d5d2d6e5` and
image SHA `87443667ab25cc2a047e3b23a2719e6fc232bd67a7feff03ac3ad36b1973dcc5`.
The 37,546-byte zero-transmit capture SHA is
`aea25d42b2805659a6f2ab8c4acbb2d05cda64b9223a7118a48e6a850591cc8f`.
It proves 20 qualified pages, BME `0002 -> 0006 -> 0002`, one consumed Port
Status Change event, one successful No-Op completion (`CC=1 TYPE=33`), halted
controller state, complete decode teardown and `END OK=1`. Firmware/PM guards
completed at 17,103/68,420 checks within the unchanged 12-second deadline and
the trial-only finite 131,072-check ceiling. The board returned to NVMe and the
normal SD triple was restored in `usb-xhci-noop-restored-20261015-v7`.

The retained v6-v9 failed captures document the admission, asynchronous-event
and verifier-budget boundaries that led to v11. All register and PCI-write
allowlists remain unchanged; USB-3 does not write a port register or enable an
interrupt.

Apple-source audit correction: IOUSBFamily publishes useful headers and partial
queue code, but its essential XHCI/root-hub/hub/device/USB-HID implementation
files are empty in the pinned official release. IOHIDFamily is usable later for
full event publication. The first terminal input path will use XNU's existing
`cons_cinput` boundary and the bounded boot-keyboard decoder; it will not be
misrepresented as full IOHID support.

## Full CPU-owned GEM provider passes and baseline is restored — 2026-10-14

The exact final full-provider package
`build/rpi5/gem-full-provider-trial-20261014-v13` passes both software
qualification and one bounded Pi 5 board run.  Its manifest SHA is
`c91ed69c129103004ad92f2aa74424c8730203ea42040d697123ced46e88d402` and
image SHA is `1080346d6acad62784ce27d54b0130b0a56f94133bde49fcf8d42e9fde023a4f`.
The 54,530-byte receive-only capture has SHA
`ba231c633737c56853939895fd60a13f9b270fddb72a8565b8a8532a9f04c169`;
its parser report has SHA
`47646e3b2eb58cb50c71eceb546a3a7b1fd36e1482307f50f2b1ef209061514f`.
All 146 detailed evidence records validate: 18 ordered Normal-NC pages, two
retained ring pages, 128 ordered CPU-owned packet spans, and the exact
`0x48000` provider geometry.  The owner reaches `OSTEP=9 OERROR=0`.

Fresh GEM snapshots before and after observation are identical: NCR, RBQP,
TBQP, TBQPH and RBQPH are zero; IMR is `3fffffff`, the exact all-interrupts-
disabled value for this RP1 GEM instance.  Endpoint BME remains clear,
`END OK=1`, no DMA/IRQ/packet/queue publication occurs, serial TX is zero and
firmware returns to NVMe Linux.  The strict parser was corrected to reflect
Cadence's active-low IMR semantics, the intentionally enabled preferred-RAM
inbound decoder, and digit-bearing field names such as `RP1`.

The disposable SD is back on the exact normal probe/config/firmware baseline.
The next boundary is no longer provider mapping: it is a distinct queue-0
base-register save/write/readback/reverse-restore trial, still with BME clear,
NCR zero, IMR `3fffffff`, descriptors CPU-owned and no DMA or packets.  The
corrected software-only core is qualified at
`build/rpi5/gem-queue-admission-candidate-20261014-v5`, manifest SHA
`13384217e12e5bacd27300c34a4158fa52c380a3f824fd72b7d9f2fb815a7c6b`.
It pins the passed v13 provider manifest and exact capture/parser evidence, so
the former physical prerequisite is now closed.  The candidate itself remains
default-off, uncomposed and unexecuted on hardware.

## Previous: physical CPU-owned rings pass and exact baseline is restored — 2026-10-14

The catalog 524 physmap-enabled CPU-ring successor completed one bounded,
receive-only board run. The immutable serial stream is 36,518 bytes, SHA
`adb0cdd8d16da53fcf8951b0bf3004c6a4371cc9729cb965cadb3e31da64bd70`.
It contains exactly 53 ordered `PCIEID` records and one exact image marker.
The terminal rows report a 32-KiB preferred-RAM allocation, two 16-KiB ring
pages, 640 attempted/written/read descriptor words, 160 CPU-owned descriptors,
and zero packet spans. The endpoint command is restored to `0000`. The complete
tail records the watchdog reset and a normal NVMe boot, with no panic, XNU
fault, BL33 exception, abort or rejected-path marker. Serial transmitted zero
bytes.

The original v2 recorder retained `capture_valid=false` because its package
report omitted five inherited parser fields. Those historical bytes and the
return receipt remain unchanged. A separate source-pinned v3 adapter derives
the missing contracts and boot markers from the exact checked package, then
runs the unchanged strict 53-row parser against the original serial bytes. Its
8 mutation tests pass. The immutable board report is
`gem-cpu-ring-physmap-board-evidence-20261014-v1.json`, SHA
`050d50a2efd723ddd3bf37ad3b0f7753b4242396ee41d6271b5a5729e5d5b96f`.

The independent Linux return is boot
`d2fd08b0-1ff7-46ab-b237-e2e64f20446a`. Restoration then returned the exact
normal SD triple: config `aaccab184135aca272db4123fcba34e20874ae0959a90aed1ef6fd4d5e18ed28`,
firmware `413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46`,
and zsh loader `f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536`.
Those hashes were independently read from a temporary read-only mount, which
was removed afterward. The append-only chain is catalog 524→530→536. The
composite closure report is
`gem-cpu-ring-physmap-composite-closure-20261014-v1.json`, SHA
`7b6443bcd84190b6d1fee5408b4d808ba435a2c28455a95e62be1fb6b63f6be0`;
its 8 tests and direct CLI reproduction pass.

This proves only CPU-owned descriptor allocation, mapping and CPU
stores/readbacks. Bus mastering, queue publication, DMA, interrupt delivery,
packets, Ethernet and SSH remain false. The next network boundary is a fresh
full packet-span CPU-mapping proof, followed by a separate queue-0 base
write/readback/reverse-restore trial with BME kept zero, GEM RX/TX disabled and
IRQs masked. BME, polling DMA, one real IRQ, interface publication and SSH stay
separate later gates.

The full-provider prerequisite is now target-linked and software-qualified at
`build/rpi5/gem-full-provider-candidate-20261014-v1`. Its manifest SHA is
`a78512231a31a43d2810664610bc47a35c9b54bee086b66b0a224dcf66a3f4ef`,
linked-kernel SHA is
`b878c4e931a5352bb591b5b097cbfb5de5404e9f3b1ad49fbfdd50e99eca22a8`,
and reproduced qualification-report SHA is
`b1b751daa49e7d67af6ae7022b52c41f60bdd22d2e580d0c66b224d38818bc56`.
It retains two 16-KiB ring pages and 128 disjoint 2-KiB packet spans in one
`0x48000` Apple `IOBufferMemoryDescriptor`/`IODMACommand` allocation, keeps all
spans CPU-owned, and checks all 18 retained/static physmap pages for A76
read/write Normal-NC translations. Seven tests pass. It has no boot caller and
has not been staged or run on the board; live same-boot ownership and all 18
pages/128 spans remain the next physical proof.

The first transport draft was rejected before staging: its inherited ring
recipe pinned stale provider bytes and its aggregate rows could not establish
the live page/span geometry or fresh quiescence state. The fail-closed
assessment is
`gem-full-provider-board-transport-assessment-20261014-v1.json`, SHA
`de3c41b295ffe49a33397f565751c2b16962460585147823167daa7c29aec8a1`;
its three tests pass and `stageable=false`. A replacement must emit 18 ordered
page records, 128 ordered span records, distinct CPU-VA/physical/RP1-DMA
geometry, fresh BME/NCR/IMR/queue observations, zero-TX evidence, automatic
return and exact catalog/restoration closure. No board image was published.

The queue step is now implemented and independently reproducible as a
software-only, default-off A76 candidate at
`build/rpi5/gem-queue-admission-candidate-20261014-v3`. Its manifest SHA is
`795f6850a1136a1b73036710ffc023a42e2f5370d47f58ae4e81a2202e66e9b0` and
its self-contained object SHA is
`df428c9672539a289107609f28a7e10c60be7e5c0b40070d7c3854e17417f74f`.
It hard-requires the full `0x48000` provider and all 128 mapped, CPU-owned
packet spans; requires exact `NCR=0` and `IMR=0`; has no BME operation; writes
only queue-0 `TBQPH`, `RBQPH`, `TBQP`, `RBQP`, then restores them in reverse;
and is not wired into a production owner. Four tests and its clean-environment
direct checker pass. It has not been composed into a kernel, staged or run on
the Pi. The complete ordered rationale and later authorities are recorded in
[the Gate 5 wired review](GATE5-WIRED-NEXT-MILESTONE-20261014.md).

All twelve unchanged `IONetworkingFamily-186` implementation units now compile
against this exact XNU workspace and link into a distinct, uninstalled arm64
kernel with zero undefined symbols. The v3 default-off archive SHA is
`3004b8185acb562684b9d5f29051e35df2fdd2397e0e5cbc74a2ab0ab5a9a065` and
the linked-kernel SHA is
`c63ee521517abd91a51ab656e7ef27dc4b7eed015ec26a138194a43dd9493e4b`.
The immutable report
`build/rpi5/ionetworkingfamily-186-link-slice-20261014-v3-r5/report.json`, SHA
`f370952ca51f5e4e77ffd2a2d4fd0acbd55901e8227694be32d5e3b63575169f`,
binds the output-only compatibility preinclude and exact target-SDK
`TargetConditionals.h`; no Apple source was modified. Eight relevant tests
pass. This still is not production composition or interface registration; the
Apple-family admission bit, `en0`, IP and SSH remain false. See the
[Apple networking boundary](GEM-APPLE-NETWORK-ADAPTER.md).

# Previous: page-granular physmap mapping gate passes; CPU-owned-ring successor qualified — 2026-10-14

The corrected v10 image completed one bounded board run with the intended
mapping result. The raw serial evidence reports `DMA_PREP STEP=16 ERROR=0`,
`DMA_MAP REASON=41`, and exactly four ordered alias rows: both16-KiB pages,
both retained and static VAs, `CACHE=6`, exact physical addresses, valid read
and write translations, and `ATTR_R=68 ATTR_W=68` (`0x44`, Normal-NC).
Page-table accounting is
`PAGES=5 MAX=6 EDGE=2 UPPER=1 BYTES=81920 MAPPED=100597760`
with `RESERVATION_CLEAR=1`. The owner reaches terminal Discarded state8 before
route; route, descriptor stores/readbacks, BME, DMA, queues, IRQs, packets and
UART TX remain zero.

The historical v5 recorder still retains its failed classification because it
inherits an RP1 identity/link rule that rejects `END OK=1` when this
verification-only image intentionally leaves RP1 identity/link fields zero.
Those recorder and receipt bytes remain unchanged. The distinct post-capture
checker now passes the exact raw59-row stream and old receipt/source closure
under the image's narrower terminal authority. It verifies2,552 contiguous
receive events,1,742 source receipts and14,270 evidence receipts, the four
ordered Normal-NC aliases, bounded table allocation, Discarded-before-route,
zero activation/TX, automatic independent NVMe return and the complete
catalog512→518→524 restoration chain. This formally accepts the mapping-only
gate without manufacturing RP1/link success and without another board boot.

The immutable typed report is
`gem-physmap-mapping-board-evidence-20261014-v1.json`, SHA
`fca45a8a3c17d9d5d7ef9acbf2d879c6c8adf351f82465d75727b5789ff8b5f6`.
Checker SHA is
`1738aa2125294305dd234214c1c7379f73f40d27e77a67c6d08eb54004443bde`;
its3 mutation tests pass. This proves CPU-visible page-granular Normal-NC
mapping only. It does not prove Ethernet, RP1 link operation, bus mastering,
DMA, queues, interrupts or packets.

The capture is36,924bytes, SHA
`32af09d3ed9e5e6c456605507ae04994aee2ac8b5f725e1f2a9383a25731a12c`;
state SHA is
`38fc7afccaa5f6e53ca6bc67c2d2afcf41468f6cc8655404cdd4d9627e6c8d24`
and typed-failed return SHA is
`9970c36664f85d5e54361dc08e4a2f877e579c2e7c24708048f748cc959c0f2b`.
Automatic independent NVMe return is boot
`2d237d96-a323-4df7-a8b4-ad9b4eb5f477` on `/dev/nvme0n1p2`.

Exact restoration and replay pass, catalog512→518→524. Restoration
`gem-physmap-mapping-v5-restored` has seal
`91a00c05d5bee963e87e316a4748eeee4e38be706a8f6c6432238f3047180c00`,
plan `0192c6a07d6947c41443aa24b18f1432a867c9f8c9676773a29e7b6a097e5058`
and result SHA
`f379d91a3ebf20f3105b38a349980581e3c12bafab630c7503d690de7ad1d930`.
Catalog524 SHA is
`5aa6a9e2f2c94090e6ded0dfa27129d26924f8ea98479f6aebb61e97d4d54c20`.
Independent read-only verification confirms the exact original config,
normal firmware and known-good zsh loader.

The next distinct software-only CPU-owned-ring package is
`gem-cpu-ring-physmap-trial-20261014-v2`: manifest
`9cc31e53c773af491806b2cee60a794679034da042df4fd4a6c50ab1522b6b80`,
kernel `6afdabf0ca98b0e854f7ee27e29e9868ee31b60cf955899867eb39572a14d128`
and image
`fbfca7c3e40893ddd383b5183b5f5f3db9a52fbbfb3b87c749523c2d6a3fcbae`.
Its actual composed kernel links all three enabled VM objects and pins the
canonical lowercase `makedefs/MakeInc.def`. The contract allocates two
CPU-owned descriptor pages through the preferred RAM route with zero packet
spans; BME, queues, DMA, IRQ, packet mapping/submission and TX remain disabled.
Qualification SHA is
`509b8c60bd6a1f892b48a880f3cea34d8083f687f2e5250189058f02db9cb591`;
the strict checker and13 focused/regression tests pass. It is not yet hardware
evidence: a catalog524 transport must be independently qualified before a
single bounded board trial.

The Apple pthread prerequisite also now has the default-off target-linked
recursive-mutex candidate `apple-pthread-recursive-target-v1-vquibrum`,
manifest
`a3d2f7b5fa41778ac49a8584655351ae88581b64299eacc06f770967d75a5e3e`.
Its exact arm64 target SHA is
`7077df6eeeb9c6e9d4c6a2dd2be05f92ed79933e976ee94fd98c5469db196ada`;
10 tests cover depth3, foreign unlock rejection, retained-depth contention
and final release. Admission remains closed until that exact candidate runs on
the Pi with a bound serial receipt. Fork/atfork, genuine cancelable-variant and
coherent FILEX stream-lock evidence remain separate blockers.

The exact recursive candidate is also packaged offline for a future bounded
Pi run as `apple-pthread-recursive-serial-v1-at_40hw7`: manifest
`8ea50631c499b7d5e7e61ce3851c768d6f6ceddfe8e06854413a7fd038fd3d3d`,
image `599dab54c0974791c8255b2d81bf0c3825973b11bf8a902581ac508a1f71f276`
and transport qualification
`6cec1855b7f597fda82980681c9413ecdba554a7472bf4b1060f76b21cba4fe7`.
Six tests reject12 output/receipt mutations. It has not been staged or run;
the networking CPU-ring trial remains the next physical priority.

The coherent current-Apple FILEX candidate is
`apple-filex-stream-lock-3gixnms6`: manifest
`5500d7dc5f7e248b4c7e7a452e20d28d78dcfb2bcc18d0b537006e5f12924b1c`
and exact target
`ed7fb8abf9fbf11291172242097259060b17618f6e586f265536e682aacf50e3`.
It has zero undefined symbols and links unchanged current Apple `fwide.c` and
`_flock_stub.c`, coherent `FILE/__sFILEX`, and genuine Apple pthread mutex
owners without legacy Libc-167/private stdio. The host ASan/UBSan oracle and
six mutation tests pass, but the gate remains default-off until this exact
candidate executes on the Pi with bound evidence.

# Earlier current: first page-granular physmap trial fails closed; exact baseline restored — 2026-10-14

The first default-off page-granular physmap board image completed one bounded,
zero-input capture and returned automatically to fresh NVMe Linux boot
`5a1f5c04-c3d6-463a-8785-d737a3d59935` on `/dev/nvme0n1p2`. It is a real
failed diagnostic, not mapping or Ethernet evidence. The decisive rows are:

`DMA_PREP STEP=14 ERROR=-13 BYTES=32768 PACKETS=0`

`DMA_MAP REASON=26 PAGE=0 ATTR=0 VA=0 PA=184745984 PAR_R=184827904 PAR_W=81920`

`DMA_PGTABLE START=184745984 END=184827904 BYTES=81920 PAGES=5 MAX=4 PAGE_BYTES=16384 MAPPED=100597760 RESERVATION_CLEAR=0`

The runtime allocated five 16-KiB bootstrap table pages while the provisional
range-only estimate allowed four, so the provider rejected before examining
either DMA page alias. The four emitted alias rows are therefore intentionally
zero and invalid. Route, descriptor stores/readbacks, BME, DMA, queues, IRQs,
packets and UART transmission all remained zero.

The capture also exposed two software-qualification defects that must be fixed
before any retry. The exact image contains and emits its manifest
`trial_marker` tag `6db66759d35d47789e3dc1c21a3481f9`, while the v4 serial
case incorrectly expected the manifest-file SHA prefix `e8b65a...`. In
addition, the composed board kernel replaced the enabled `pmap.o` and
`arm_vm_init.o` but not the third affected unit, `loose_ends.o`; canonical
full-build qualification alone does not prove that the actual trial image
contains all three enabled objects. A successor must derive its marker from
the package manifest, account for the intervening boot-data mapping's ragged
L3 edges, and compile/link/pin all three affected VM units. Physmap upper-level
tables are preallocated before the measured interval and remain separate.

The failed capture is36,756bytes, SHA
`249d7f3209350db0c4aad78df0a7818c72ea59d160a38a049df34caeaa840005`;
state SHA is
`17b1f3916ce1cad528e3fc3add5cf58506ca5b0560e0e899414ec412529b0ecb`
and typed return SHA is
`dd5c43619c26d66111493a8646a13b8652edbd4371b627881ea2fcfe91889f83`.
Typed acceptance remains `capture_valid=false`, `ethernet_proven=false`, with
independent normal NVMe return verified.

Exact three-target restoration and replay pass, catalog500→506→512.
Restoration `gem-physmap-mapping-v4-restored` has seal
`6b55bf9cf939bb70a58e3781cf1f54eb0633167a95bde75db6bc663df6bdb2b3`,
plan `f77a4e94248d6df7b215086ff32aa18acf94ad570509e48a3d384b7cd9a0ce37`
and result SHA
`20345faa425243b43f1578aa30f1c0c3983192cd21fde92a9906ee2555f38298`.
Catalog512 SHA is
`8f7be2df370eb5a6951e645fca95d0609db141cf07ac53da020e7bcd26964566`.
Independent read-only media verification confirms original config
`aaccab184135aca272db4123fcba34e20874ae0959a90aed1ef6fd4d5e18ed28`,
normal firmware
`413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46`
and known-good zsh loader
`f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536`.

The corrected software-only successor is sealed as
`gem-physmap-mapping-verification-20261014-v10`: manifest
`a73188d0234348025b151bc66ee7f5cb7763efd867871d23a4c5379eba7df141`,
kernel `9a68743d5c5681623d06a0dcdde67dc82b584d03f94ac895ff0ac9bc669bdc96`
and image
`5fad73f69c09f05431ece249204c7ae52b07e2f6df45b12370019f26ed1a39df`.
It computes the measured bound from the target physmap span plus the
intervening mapping's distinct ragged L3 buckets, caps it at259 pages /
4,243,456bytes, and reports the one preallocated upper physmap table
separately. The actual composed kernel now compiles, links and pins enabled
`pmap.o`, `arm_vm_init.o` and `loose_ends.o`; the lowercase canonical
`makedefs/MakeInc.def` is also pinned. Its exact manifest tag
`96a5f52e3bd546fc8687f63e9b6459e9` occurs once in the image and is the serial
identity. A clean full BCM2712 DEVELOPMENT build/link, strict package checker,
13 boundary/mutation tests and the compact intake pass. This is not board
evidence; a distinct catalog512 transport must pass before one retry.

The Apple OpenSSH dependency track now has a default-off pthread/FILEX gate at
`apple-pthread-filex-gate-gj99o8li`, manifest
`9c0d30fe853dd864e78035293b74880b2fb1a2b63f60cdba551a9f5c1706bca3`.
Existing physical evidence narrowly credits target mutex contention and
errno/TLS isolation, but not recursive mutexes, real fork/atfork composition,
cancelable pthread variants or FILEX stream locking. The host sanitizer oracle
passes those behaviors but remains explicitly host-only. All17 gate/regression
tests pass and manufactured admission is rejected; therefore current Apple
`popen`/`pclose` remains unadmitted rather than risking mixed FILE ABI state.

# Earlier current: mapping diagnostic isolates conflicting static-alias attributes — 2026-10-14

The distinct mapping-predicate image and v3 transport pass their bounded board
trial.  The accepted zero-TX capture reports exactly one row:
`DMA_MAP REASON=36 PAGE=0 ATTR=6 VA=2 PA=185532416`
`PAR_R=18374686479857158912 PAR_W=18374686479857158912`.  In hexadecimal,
both PAR values are `0xff0000000b0f0b00`: translation succeeds and resolves the
correct physical page `0x0b0f0000`, but the static physmap alias has attribute
`0xff`, not the required Normal-NC `0x44`.  The retained IOBuffer VA, exact
32-KiB IOVM segment, DRAM identity and WCOMB metadata (`ATTR=6`) pass before
this check.  Physical-address agreement alone is not sufficient coherency
proof, so the alias invariant remains enforced and the provider cleanly
rejects at step14/-13.

No route, live RP1 callback, descriptor store/readback, BME, DMA, queue, IRQ,
packet or UART transmission occurred.  The capture is36,264bytes, SHA
`5a756eddc8ac171bc2066b658044798fc5af3709546a92d01cedc61f2caf9be4`;
state SHA is
`1d97cce16953d2bc52992b8919b09809502284d88cab7cd8823f16ee7fc1b37b`
and typed return SHA is
`79d461cb2d202c3735cca2f4bcf64ebc88b62fb4cb6088801f13d20e6e5bc084`.
Typed acceptance is `capture_valid=true`, `zero_serial_tx=true`, with automatic
independent NVMe return.

Exact restore and replay pass, catalog488→494→500.  Current Linux boot is
`a6c96368-1ef6-4c34-be8e-7efdd97a9395` on `/dev/nvme0n1p2`.
Restoration `gem-mapping-predicate-restored-20261014` has seal
`beb6c83c7a719a7bf140b5b48b32c9c4500b73ea4fbcffe7e84006cb0a204cc9`,
plan `da1df6b95c5251a23f18dc3e586a97cefc2b2448db40ce8f872ecbd4eabdbd63`
and result SHA
`539aa40fa080cca5973c99782a04f2d0129d181e9c8d38be630807f60cfa492b`.
The catalog500 SHA is
`3fb9b00235759812efa3627104c9dd5158551c3ea981d47b540d333fe0e02186`;
original config, normal firmware and known-good zsh loader are restored.

Next, preserve this accepted diagnostic and repair the cache/coherency strategy
using supported XNU mapping behavior.  Do not ignore the static alias, accept
`0xff`, or proceed to route/rings until both aliases prove one compatible
memory type for both read and write translations.

# Earlier current: 32-KiB provider reaches one IOVM segment, then fails mapping qualification — 2026-10-14

The distinct ring-only retry successor completed a raw, zero-input board capture
and returned automatically to NVMe Linux, but its diagnostic correctly remains
failed.  The decisive records are
`DMA_PREP STEP=14 ERROR=-13 BYTES=32768 PACKETS=0` and
`PREPARE=3 STATE=5 ATTEMPTED=0 ACTIVE=0 REVOKED=0 DISABLED=0 RECORD=1`.
`STATE=5` is the clean `Rejected` state, not quarantine.  Allocation,
`IODMACommand::setMemoryDescriptor()`/`prepare()`, the exact physical segment,
and one exact 32-KiB `gen64IOVMSegments()` result therefore complete.  The next
unchanged predicate, `BCM2712GEMDMABatch::mapping()`, returns false.  This does
not prove a DMA mapping or reachability: route, live RP1 callbacks, descriptor
stores/readbacks, BME, queues, interrupts and packets all remain zero.

The current capture cannot distinguish the retained-object and alignment
checks, descriptor length/capacity/VA and physical-segment identity, DRAM type,
per-page WCOMB attributes, or read/write AT Normal-NC/exact-PA checks for the
retained VA and static physmap alias.  Preserve this image and capture.  The
next board image must be a distinct, default-off diagnostic that records the
single-pass `mapping()` sub-boundary without bypassing a predicate, retrying an
AT operation, changing cache policy, writing the buffer or activating hardware.

`serial.bin` is36,139bytes, SHA
`05c5b35ebf7785a206717b66c3b73e59472c3863ddc215c5051029c5cb5e8330`;
`state.json` SHA is
`487ac1e001378877620b706a5e0a26d6501169d06908d5e95fef625fcb79abb6`.
The typed return deliberately reports `capture_valid=false` and
`ethernet_proven=false`; its SHA is
`0958c0f4b95ebdbae22b32601f1b509f27ecd74814f3c18bb68708c3eba4140f`.
Independent NVMe return is `42df0d0d-da35-442d-9514-d4f05bada5e7` on
`/dev/nvme0n1p2`.  Exact replay and restoration pass, catalog476→482→488.
Restoration `gem-cpu-ring-retry-successor-restored-20261014` has seal
`d3751ac4c8791613692471f7d65a0a9169a47a02d90d1cd15d4f5e7dd104f704`,
plan `15726c9e86af5347642a58b2c6c5469f8dadd49e884812a4a9cd7a5197fb7400`,
and result SHA
`aeba4a995433569b1dc0c32f5db40d96bec26251e06c38d19745ec22d0a9b1cb`.
Original config `aaccab184135aca272db4123fcba34e20874ae0959a90aed1ef6fd4d5e18ed28`,
normal firmware `413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46`
and known-good zsh loader
`f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536`
are restored.

The software-only mapping-predicate successor is sealed as
`gem-mapping-predicate-trial-20261014-v2`: manifest
`5183c60634238406a165ce9d4774fd2dd67df36f7792f410b670633b6d5c6b43`,
kernel `2a145a76842494f5d2f861e54e3e28ad387236be4da0e019ecabd76c50a3fd2f`
and image `5e9ecb82d44c923a2bf8559aa899759d9eca2d90af6bdd611fbb9dabc04d27c4`.
The strict report SHA is
`a8de403bd1599e0956411bb305d29f13bc0f1d29e5206f495deab31c0520d44b`;
main independently reruns its4 tests and strict checker successfully.  It
preserves the original AT/PAR/interrupt sequence and all mapping predicates,
records only bounded reason/page/attribute/VA/PA/PAR fields, and emits one
fixed row after `prepare()` returns.  No log, retry, copy, cache maintenance or
buffer write occurs inside `mapping()`; BME, DMA, IRQ, queues and packet spans
remain disabled.  This is software qualification only until the distinct
zero-TX board transport passes.

In parallel, the genuine Apple OpenSSH leaf chain now includes unchanged
Libc-167 `perror.c` and Apple's real `writev` syscall wrapper.  Sealed package
`apple-ssh-perror-fedl96a9`, manifest
`be08baf42a4708591d75e642b80daeb8936af8210ee6155f9951124a9dd55007`,
closes only `_perror` and reduces the exact full-client remainder35→34 with no
new imports or duplicate symbols.  Main reruns its5 sealed tests successfully.
The next sealed leaf `apple-ssh-sscanf-m4_xgkm2`, manifest
`114efe7a753f69e22548da8dca5c3e4f8e20faaec26a5b0232b23d263d742eed`,
uses unchanged complete Apple Libc-167 `sscanf.c`/`vfscanf.c`, closes only
`_sscanf`, and reduces34→33 with no new imports or duplicates; its nine
external parser dependencies keep their existing Apple runtime/locale owners.
The retained leaf-frontier report SHA
`f718b0bc03aee95586a70e67d27682176661ba8f9a06065d2c895e41466ea7ea`
keeps the count at33: historical Libc-167 `popen` would add `_vfork` and weaken
failure/concurrency semantics, while current Apple `popen` requires the modern
FILE, pthread, spawn, environment and private-libc tranche.  No unsafe leaf or
facade is admitted; main reruns the5 frontier tests successfully.
This is target-link/runtime-provider progress, not a claim that SSH can run
before Ethernet, sockets, resolver/notify services and persistent storage pass.

# Earlier current: clean XNU zsh/reboot path passes on Pi — 2026-10-14

The sealed `display-console-records-691ku6u6` successor passes its complete
strict board trial. All three PID1 readiness records and
`TERMINAL:WATCHDOG_READY` are intact; zsh5.9 version, builtin, external exec,
smoke, interactive exit and recovery-status checks pass. The recorder sends
568UART bytes, transmits the reboot command exactly once, observes the ordered
pthread/restart path and `PRE_SMC`, observes no returned-call or panic marker,
and records no PID1 SIGTERM stop. This closes the prior shared-UART corruption
and clean user-controlled reboot milestone without relaxing grammar or timing.

Capture41,297bytes, SHA
`97ba9ceb3153757d7e2d20ea816d7a5a66e05dbc3de997234abb0dffec6c66a1`;
typed return SHA
`cdd5e88cf9c9d0b1f5e0e224d3a84e84a0eb578647045d44519b8726d34c15b0`.
Independent NVMe Linux return is
`7a4004bf-b0eb-4b89-9b70-b8c9f1db12b6`; SD→NVMe is97.148s. Exact pair
restoration and full replay pass, catalog466→471→476. Current restoration
`console-records-restored-20261014` has seal
`17dfae2197f4c3a148b5685fb341a5fbb5c5ab8c9b54903005c21cdb644f847f`,
plan `0dcd6eced552fd60a53793117b742c40b22619db82398714c131b181a97a03b1`,
result SHA `9659258ab80063e2e8136c646cdfda79c908e1fc14f5ead1926bbc8fede0190e`.
Original config and known-good zsh loader are restored; normal firmware was
protected and unchanged. This proves serial-controlled XNU zsh and reboot, not
local keyboard input, Ethernet, SSH, unconditional PSCI causality or poweroff.

# Earlier current: CPU-ring board trial isolates provider-prepare rejection — 2026-10-14

The first actual combined CPU-owned-ring image v8 trial completed with a valid
zero-TX capture and automatic NVMe Linux return, but the ring result is a real
failure. XNU records the retained reservation (`RECORD=1`, `FIXED=2`,
`DYNAMIC=1`) and reports the prepared controller, then
`BCM2712GEMDMABatch::prepare()` returns false before the live RP1 lifecycle
path invokes any UBUS/link/config callback. The terminal record is
`PREPARE=3 STATE=5 ATTEMPTED=0`; BAR1/GEM/clock mappings, config reads, CPU
stores/readbacks, BME, queues, IRQs and packets all remain zero. Do not claim
DMA allocation or Ethernet from this capture. Provider `STATE=5` proves a clean
reject, not a quarantine: entry/context/page-size checks passed, ownership
remained active, and `IODMACommand::prepare()` did not take its quarantined
failure branch. Frozen telemetry cannot distinguish the remaining FDT/record,
allocation, descriptor, segment/mapping or software-route reject predicates.
A distinct diagnostic must expose that predicate before another functional
board image. The existing RAM-route successor changes only the later qualify
path and is not a demonstrated fix for this failure.

Capture36,071bytes/0TX, SHA
`0c701d6e34609fae3c174c1d62bfbcb4ff862c166b80eef5879b459f6802bb53`;
typed return SHA
`366c9bcbf0124c25c91530d1f4c6f161239a8749a725fe358d97d2f97034ab00`.
Independent SSD return is `1fd308fa-08e5-4aa1-9799-86939ac251aa` on
`/dev/nvme0n1p2`. Full replay verifies capture integrity, the failed diagnostic,
and restoration of original config, normal firmware and known-good zsh image,
catalog454→460→466. Restoration `gem-cpu-batch-restored-20261014` has
seal `cda1ffe9a482dcb8db9729025956c40fe81ae57ebf0276bfc1cdca90310b5af1`,
plan `87822332e49a0e76bfaff2d1b6dff8320942dd3f3e90a8bcb9297d1247e56690`,
result SHA `d1ec6d2601d408f4504ca8027b325275238e4c5f220f5b67dd53135d8a47a6ca`.

The shared-UART console successor is now sealed software-only as
`display-console-records-691ku6u6`: image SHA
`735f901b07895e1cbf6460c0657d46268e77871683d1f90d882efccf2d19316b`,
manifest SHA
`f32e6b5a155d1869b51511db4993d3298765914bba2cf59784108922d38b6cb1`.
Main independently reruns all five native concurrency/IRQ/reentry/callout/A76
groups and all three sealed package/admission/mutation groups successfully.
Review found and fixed an additional real ordering race: armed state is now
release-published before the one-second callout can run synchronously. Raw
panic/IRQ/early/debugger and post-halt `PRE_SMC` paths remain unchanged. This
is not yet a Pi result; a distinct catalog466 transport is being qualified
before one hardware reboot. No timing relaxation or damaged-line
reconstruction is accepted.

# Earlier current: shared-UART console race isolated; CPU-ring image qualified — 2026-10-14

The distinct `display-restart-late-framed-tquvyn12` boots XNU/root33 and
publishes all three exact, freshly signal-mask-checked PID1 readiness lines.
The strict trial still FAILS with0TX: `WATCHDOG_READY` is garbled where kernel
`kprintf` overlaps userspace console output. Shared-UART source review finds
independent kprintf/console-ring locks and an unprotected FIFO-ready/DR-write
pair. Do not reconstruct the damaged line, weaken admission, or claim a
reboot syscall ran. A real safe-context record-output fix is next; raw panic
and post-halt restart paths must retain their nonblocking behavior.

Capture42,040bytes/0TX, SHA
`7d15f3ca75701ef908716c70b305ce62d68b5ec6c1e18d8cc7886bd825468fde`.
Independent SSD return is `6c1570a1-1b07-478c-a4c4-a450f58a77ee`.
Original config/normal firmware/working-image restoration passes24.315s;
full failed-trial replay verifies catalog444→449→454. Current typed
`stage_restart_late_trial.restoration` is `restart-late-restored-20261014`,
seal `f7decdec8fd2bf39ffb1a9dd73ec8c6887f4a4330aba1a7b34432a4db00e26e7`,
plan `345770f28b86be318f8535254af28a85b4fc62c0f8c268b9d3e049f0dc77023a`,
result SHA `b592db47e4ac646bbe0dfec4a5f30327bb6eb42e112c81ed646cf5f10eb1fa94`.

Ethernet's actual combined CPU-owned-ring image v8 remains frozen and software
qualified; the board result is now the failed provider-prepare trial documented
above. Its separate preferred-RAM-route component remains offline work for a
later combined packet/IRQ trial, not an extra mandatory observer boot.

The genuine Apple-distributed OpenSSH `bsd-asprintf.c` fallback is now sealed
as `apple-ssh-asprintf-ewo2v725`. It closes `_asprintf` and `_vasprintf`, moving
the unchanged full client39→37 unresolved imports with no new imports,
duplicates, stubs or feature changes. Main independently reruns all four
retained source/closure/forced-A76/native-ASan+UBSan tests successfully. The
private `bootstrap_parent` XPC boundary, SSH transport, daemon services and
target execution remain unfinished.

# Earlier: shutdown image boots; early UART readiness is garbled — 2026-10-14

The distinct PID1-only `display-restart-init-xw9wi1um` boots XNU and root33,
then reaches the shell. Its new once-only shutdown-readiness line is lost
inside simultaneous secondary-CPU/kernel console output. The strict recorder
correctly sends zero bytes: no zsh commands or reboot syscall are claimed.
Preserve this failed trial. Capture41,681bytes/0TX, SHA
`e2d89873cb76701c12e23c1b51d78b486d8a3ab950e13edd184745034d32e31c`.
The existing bounded watchdog returns to SSD Linux automatically; no manual
power cycle or soak is added. A distinct late, bounded readiness publication
is being implemented without relaxing the required actual signal-mask proof.

Independent Linux boot is `2a46da4b-72b7-4145-b5f3-d84a05d64b91`.
Original config/working zsh/normal firmware restoration passes24.765s;
full failed-trial replay verifies catalog434→439→444. Current restoration:
`restart-init-restored-20261014`, seal
`373c070c66e6b4efba6030b61d80b356ed86a3a4bfe06714820a8d1b6fb14273`,
plan `0efb9d6b74c809663f4291df02743c0fedecf72be8d4535943ff2cc44e79f4e4`,
result SHA `734f13c2da629416c74506ff3e3675b46eb6631686102a54a59bc24858834250`.

Ethernet's combined software candidate now includes the exact six RP1 Device
pages and the actual target nullable-allocation branch. Main byte replay of
finite successful-owned stack paths peaks11,728/16,384bytes, leaving4,656
before unclosed standard-kernel helper assumptions; it is not a whole-kernel
allocator/scheduler/panic/IRQ stack proof. Package/protocol qualification is
in progress, with no DMA activation, packets or network interface claim.
Apple DNS wire-parser review plus six main tests pass2.102s, reducing the full
SSH client40→39 unresolved imports. SSH/DNS services are still unavailable.

# Earlier: loader copy fix passes; clean reboot needs PID1 shutdown policy — 2026-10-14

The distinct `display-restart-copy-sgf9_m1d` completes physical kernel copying
and readback on the Pi, boots XNU, and passes all four real zsh checks.
Nonce `Dc230eeb2a7ee6700` identifies version5.9, builtin/external/smoke and
recovery0 results. The actual `/sbin/reboot` starts, but this trial FAILS:
unchanged `proc_shutdown()` sends SIGTERM to PID1; the project init has no
shutdown signal policy, exits, and triggers the original critical-init panic.
The subsequent PRE_SMC marker comes through panic recovery, not clean reboot.
Do not turn it into a successful reboot or remove the fault filter.

Full capture51,072bytes/568TX, SHA
`9ce3cd63b0e581438689a48e4c67a7182e9027edee23c3b34e8debb959eb0993`.
Independent SSD Linux return is `2a3ae56f-82b9-44eb-a300-6fed62839224`.
Original config/working zsh/normal firmware restoration completes24.518s,
catalog434. Current restoration `restart-copy-restored-20261014`, seal
`a1829bedad203cc6a4f1b10037358309792a46a0d3941daee20887d1cb8a0c4c`,
plan `9aa6aefa7c32f74999417067cd46d612028cfc54c085508193983941d441bb52`,
result SHA `5f80ce6ae68b31e8517c36a9badd85867af2c8c89fe5a17cdb5aa2ab51bf6b1f`.
A distinct PID1-only stop-respawn/non-exiting policy is being implemented;
kernel panic behavior, watchdog limits and accepted images remain unchanged.

Ethernet's real combined controller/provider/batched CPU-owned-ring harness
now runs in software, with640 writes/readbacks and164 fresh owner checkpoints.
Native PM64940/FW16233 stay within unchanged limits. These are explicit native
doubles, not board DMA, active inbound routing, packets or interrupt proof.
Real-caller faults, final stack/composition checks and hardware admission remain.

# Earlier: visible XNU/zsh confirmed; PHY reset/C22 hardware trial passes — 2026-10-14

The user photographs readable full-height XNU boot text and zsh5.9 on HDMI.
The visible nonce `Dadf6658340d35c45` exactly matches the repeat's real serial
command results, including builtins/external exec/smoke and exit/recovery0.
Complete repeat39,905bytes/442TX passes; SHA
`8bdf19c3814083c5f4ca8dedfed090df3af54d91567a0dfbfc38282ed6fe29a6`.
Independent SSD return and original config/zsh restoration pass, catalog404.
Photo evidence is separate from unchanged machine-only visibility fields.
Input remains serial; local keyboard, networking and permanent operation are
not implied. [Console evidence](HDMI-ALLOCATION-OBSERVATION-20261013.md).

The actual bounded GPIO32-reset/C22 trial now also passes all59 diagnostic
records: PHY1 ID600d84a2, BMCR1140, BMSR7949 twice; original GPIO fields,
maps, root/endpoint command/window and BARs restore. PM64420/FW16103 stay
within unchanged limits. Link/autoneg are0; no IRQ/DMA/packets are proven.
Independent SSD Linux return is `5893543b-80df-4594-bef7-9e6c4833a8b4`.
Original firmware/working-image restoration passes24.084s, catalog414; this
is not a new soak.
[PHY evidence](GATE5-PCIE-IRQ-TRANSPORT.md).

Parallel software:64TX/64RX CPU-owned GEM ring construction passes fault
tests. An inactive genuine Apple IOBuffer/IODMA mapping provider passes four
main test groups (1.907s), but a same-boot resolved-reservation handoff is still
needed: the original FDT's unresolved CMA allocation window conservatively
excludes the current managed RAM. Loader/kernel handoff and ring-owning
integration are in progress; the exclusion is not bypassed.
A fully linked restart-only HDMI/root33 candidate adds real `/sbin/reboot`,
but physical reset causality still needs a distinct instrumented trial.
Current Apple daemon provider is qualified; full SSH still has40 unresolved
imports because real bootstrap_parent is newly exposed. None of those software
results is a networking, DMA or physical reset claim.

The distinct restart diagnostic image was staged with original firmware
unchanged, catalog419. Installation seal
`c60850eccfb96d7427da7e481489e9648ba8dfe0ec4752d706555d09a0ad2ef2`,
plan `7f36b928660d34773e65de43b3034e56df59d52400073fe46ddb7e4adcbb0ab5`.
Its first host launch fails before any reboot: the recorder emits
`RESTART_DIAGNOSTIC_ARMED`, but the inherited launcher recognizes only
`CAPTURE_ARMED`. No reboot intent exists; the unused recorder is gracefully
interrupted after exact PID/device verification. Final capture has0 bytes/0TX,
and fresh SSH confirms the unchanged SSD Linux boot above. Preserve this failed
attempt. The separately pinned launcher-only correction passes six main groups
(26.580s), arms the unchanged recorder and makes one verified Linux reboot.
The actual target trial then fails before XNU: last loader record is
`PHYSICAL_COPY_BEGIN`, followed by firmware reset/NVMe return. Complete capture
23,422bytes/0TX, SHA
`1d05df4905c84b49cdb7681e8a5f1d320120db8ea3071546421b73697f8340f8`.
No shell, restart syscall or reset-path diagnostic has executed in this image.

Independent SSD return is `6b0cf970-cefc-4a08-8c79-41e4bff6bf05`.
Original config/working zsh/normal firmware restoration and failed-trial replay
pass, catalog414→419→424. Current restoration is
`restart-diagnostic-restored-20261014`, seal
`b1b6c43f05c6d8a351eb337820bfe8aebcbeeffbf273e38e30d09aeed5dd4ed0`,
plan `ff5928dc9430564f8a219152d9894517b569612cd9926170e3e9968953f4da43`,
result SHA `5885e0aa2d3651c8adf3604419ee51d75f995fb80c44774234cef52126276f6e`.
Source/timing review identifies a watchdog-service gap: root hashing cannot
renew the kernel-only hash owner, and the first copy checkpoint arrives near
the15s countdown. A distinct verified-phase checkpoint correction is being
implemented, preserving the two-renewal count and existing timeout limits.
The failed target image/capture stay failed; this diagnosis is not a reboot pass.

# Earlier: corrected XNU/zsh trial passes end to end — 2026-10-13 EDT

The distinct host-window-v2 trial passes all four actual zsh5.9 command
exchanges and its complete serial return. Capture39,938bytes/442TX, SHA
`23326aadf529a8c53150e5d60fd42a119cdbd7e1b023b4106f611a555468a19b`;
SD→NVMe245.465s, watchdog-ready→BOOTSYS186.862s. Only the host capture window
changes to300s; target180s service/15s countdown and120s TX remain unchanged.
The original incomplete240s capture below stays failed.

Independent SSD Linux return and original config/zsh restoration pass,
catalog384→389→394, Linux `8f1e79b1-12c6-4f74-b233-f3aa60d71990`.
The user was away from the monitor, so physical readability is not yet proven.
They subsequently return and explicitly request a visible repeat; the same
frozen image is staged from typed394 restoration, without a soak or new kernel.
The repeat is in progress. Ethernet reset-v2 transport is independently reviewed
and software-qualified; hardware follows the user's visible test.

# Earlier: XNU console boots and zsh commands pass; capture incomplete — 2026-10-13 EDT

The full-height XNU console candidate now boots on the Pi. Its same-boot
allocation/retained backing and Normal-NC/NX mirror initialize; the existing
32-node RAM root mounts. All four guarded interactive zsh5.9 exchanges pass:
version, array/arithmetic, external exec, smoke script, exit and recovery
status0. Main independently replays each actual response from37,590 raw bytes,
442 UART TX bytes. This is actual command execution, not a physical visibility
claim. The user's full-height monitor observation remains pending.

The complete trial remains FAILED: the recorder's SD→NVMe240s budget expires
at01:51:05.967UTC, before Linux boots at01:51:16UTC. SD→kernel commit itself
takes about49s; the unchanged180s service plus15s watchdog and return startup
require a longer host capture window. Silence after logged kick24 is expected
because logs occur only at1 and multiples12. This is not evidence of a hang.
Preserve the original failed capture; a distinct300s host-capture successor
keeps all target/TX deadlines unchanged and does not retroactively pass v1.

Independent SSD return, original config/zsh restoration and normal firmware
preservation pass, catalog374→379→384. Fresh Linux boot is
`35f6ae79-87c2-48d4-ba11-14a75b1ebf00`, root `/dev/nvme0n1p2`.
[Exact partial command and recovery evidence](HDMI-ALLOCATION-OBSERVATION-20261013.md).

# Earlier: compact HDMI pattern observed; working boot restored — 2026-10-13 EDT

The distinct compact diagnostic completes all768 stores/8 rows within its
unchanged500ms deadline, including the one replay explicitly requested by the
user. The user confirms seeing the upper-left text/colour pattern and supplies
two photos. Its deliberately downsampled8-pixel-high glyphs look squashed;
this is not a legible full-height text-console or HDMI zsh pass. Separate photo
observations do not rewrite machine receipts' physical-visibility fields.
[Exact compact and visual evidence](HDMI-ALLOCATION-OBSERVATION-20261013.md).

Replay full capture, independent SSD Linux return and original config/zsh
restoration pass; catalog364→369→374. Fresh Linux boot is
`388349d4-3664-4ac1-9488-7d59cc4f6566`, root `/dev/nvme0n1p2`.
The frozen same-boot XNU console candidate `display-xnu-console-5cd94fg_`
preserves the existing32-node root and uses Apple's full-height renderer with
UART-first mirroring and verified Normal-NC/NX backing. Fifteen focused main
tests pass. Its distinct guarded four-exchange zsh transport is being qualified;
the candidate had not yet executed at this stage. No new soak is required.

# Earlier: bounded draw times out; working boot restored — 2026-10-13 EDT

The first standalone visible trial performs2880 aligned stores and9 row
barriers, then correctly fails its500ms draw deadline. Allocation still passes
at0x3f400000, but drawing is incomplete; no visible-output or HDMI zsh pass is
claimed. The full20,657-byte zero-TX capture is retained with SHA
`bbf6f3ff63e79d60ca1b4088c73ae6d6f0bfdfe607c7596331cf51d40394c889`.
Independent SSD return, original config/zsh restoration and failure/recovery
replay pass, catalog334→339→344. Linux boot is
`b4fffdef-827e-4013-8bd6-94bff7039d36`, root `/dev/nvme0n1p2`.
The failed candidate is immutable. Distinct compact visible proof and actual
same-boot XNU mapping/renderer integration continue; neither is yet bootable.

The read-only GPIO32 observer now passes on the actual Pi:53 records/60 reads,
both raw snapshots agree, all5 maps revoke and root/window/COMMAND/BARs restore.
CTRL9f/PADd6/RIO OUT1/OE1/IN3 differ from Linux's owned reset-output setup.
Full34899-byte zero-TX capture, independent SSD return and exact original pair
restoration/replay pass, catalog354. Current Linux boot is
`47392e3e-8254-4780-ae41-82ecd22f67ef`. No GPIO/reset writes or PHY/networking
readiness are admitted. [Exact hardware evidence](GATE5-PCIE-IRQ-TRANSPORT.md).

The main six-group directory-family rerun passes4.691s. The complete original
SSH client now has40 unresolved imports, no new imports or duplicate owners;
it still does not link or run. [Userland evidence](GATE6-USERLAND.md).

# Earlier: PHY replies are all ones; working boot restored — 2026-10-13 EDT

The first bounded PHY trial reads five0xffff responses and rejects them. Its
temporary NCR.MPE settings restore to zero and NCFGR remains00540000, but the
failed overall transaction does not prove maps/BAR/root runtime restoration.
The frozen serial parser additionally rejects propagated RC=-6; its complete
34,808-byte zero-TX capture remains invalid, never relabelled as a pass.
Independent SSD recovery and exact original firmware/zsh restoration pass,
catalog324→329→334. Current boot is
`1bef80be-d4c1-4f98-b333-8062bb6a9103`, root `/dev/nvme0n1p2`.
[Actual PHY failure and recovery](GATE5-PCIE-IRQ-TRANSPORT.md).

Source review identifies a plausible missing PHY prerequisite: active-low
Ethernet reset on RP1 GPIO32. Linux reports that line owned by phy-reset,
output-high/deasserted; that does not establish its standalone XNU state.
A distinct read-only GPIO32 observer and reset-ownership design are underway.
Its loader must declare only the three additional exact Device pages, not an
entire RP1 BAR. The visible display patch now passes main native22/package9/
transport27 software invocations and independent byte-only preparation
admission. Prepared seal is
`f06383041d80c3ca2baebe0fe9a72eeb595d94e2bcf45d15959b65e613f22729`;
it is not installed or executed. No framebuffer store or on-screen text has
yet run. Same-boot XNU retained backing/mapping work proceeds separately.
The passed allocation milestone below is retained.

Fresh SSH verification confirms the same SSD boot and HDMI-A-1 connected.
Original Apple RW-lock, environment and collection prerequisites pass the main
13-test rerun, but the better-qualified SSH composition remains41 unresolved
imports. [Userland evidence and limits](GATE6-USERLAND.md).

# Earlier: framebuffer allocation checks pass; working boot restored — 2026-10-13 EDT

The distinct zero-prefix allocation-only trial passes on the Pi. Four matched
exchanges and fresh FDT/extent/format checks admit address0x3f400000,
8,294,400 bytes,1920×1080×32, pitch7680, BGR0, alpha2; rounded reservation is
[0x3f400000,0x3fbec000). No framebuffer read/store, drawing or XNU handoff
occurred. Full20,368-byte zero-TX capture, independent SSD Linux return,
original config/zsh restoration and byte-only chain replay pass, catalog
314→319→324. Current Linux boot is
`52bd6236-b9af-4c66-a4b3-3177a179a575`, root `/dev/nvme0n1p2`.
[Exact physical results](HDMI-ALLOCATION-OBSERVATION-20261013.md).

Next is a bounded standalone visible pixel/text proof using Apple's font,
then exact same-boot retained backing and consistent noncached XNU video
mapping. A successful serial record is not on-screen output. Ethernet's
bounded PHY-management kernel/package is built and tested, with a distinct
masked floating-ID correction; controller review remains before hardware.
Original/explicitly derived Apple runtime providers now close the full SSH
client47→46→42→41 with no new imports in those accepted compositions. A later
stdtime inventory exposes real additional dependencies and is unqualified;
it does not replace the41-import composition. Ethernet packets and SSH remain
unfinished. All three workstreams continue toward an operational system.

# Earlier: display allocation reaches verification; address admission rejects — 2026-10-13

The distinct config32/allocation trial completed all four matched exchanges.
Preflight, SET and independent GET agree on 1920×1080, depth32 and pitch7680;
the returned allocation is address `0x3f400000`, size8,294,400 bytes. The frozen
candidate required a C-prefixed representation and correctly rejected this
reply with RC=-8 before any framebuffer memory access. This is a failed trial,
not framebuffer ownership or visible output. Full 19,993-byte zero-TX capture
and the failed result are retained. Independent SSD Linux return, original
config/zsh restoration and byte-only chain replay pass, catalog304→309→314.
Current Linux boot is `806018a2-252e-43d9-aa88-bac89efcf55f`.
[Actual display evidence and next correction](HDMI-ALLOCATION-OBSERVATION-20261013.md).

Reference code clears an alias mask without requiring the incoming C-prefix;
the old predicate was a stricter project assumption. A separate allocation-only
zero-prefix revision is in progress, retaining every other fresh admission and
no-access guard. Ethernet PHY-management software passes six main-rerun groups,
including 1,458 pure faults, 192 actual transport faults and the full worst-poll
model at PM65420 under the unchanged65536 limit. No MDIO hardware has run.

# Earlier: GEM capabilities pass; working image restored — 2026-10-13

The distinct GEM capability trial passes all 47 records on the Pi. Two reads
of each design word agree: one queue, a 128-bit internal bus and the 64-bit
descriptor feature. These are hardware capability reports, not qualified DMA
addressability. No DMA, IRQ delivery, PHY access or packets occurred. The
complete 34,496-byte zero-TX capture, independent SSD Linux return, exact
original firmware/zsh restoration and byte-only chain replay pass, catalog
294 → 299 → 304. Current Linux boot is
`2ada421c-8073-4006-b3ef-a5a9e458054a`, root `/dev/nvme0n1p2`.
[Actual capability evidence](GATE5-PCIE-IRQ-TRANSPORT.md).

Parallel work continues on a bounded PHY-management implementation and the
distinct HDMI allocation trial. The latter requires a temporary, checked
`framebuffer_depth=32` config/loader pair; no allocation trial has booted yet.
The new config/loader transport and Apple TTY/temp provider groups pass the
main rerun (27 invocations, including three repeated formatter tests).
Original Apple providers close the full SSH client from 46 to 42 unresolved
imports with no new imports or duplicates. Native and forced static contracts
pass, but neither these providers nor SSH have run on the Pi.

# Earlier: firmware display query passes; working image restored — 2026-10-13

The standalone GET-only display query now passes on the Pi: one display and
raw settings consistent with1920×1080,16-bit depth,pitch3840; all later words
are zero, so no usable nonzero framebuffer address is established. Two matched
requests complete with no quarantine, no allocation/SET/drawing and zero host
serial input. Full14,750-byte capture, independent SSD Linux return, original
working zsh restoration and full replay pass, catalog294. Current boot is
`6cf18813-d9c9-471f-8584-fffd11358c0a`, root `/dev/nvme0n1p2`.
[Actual replies and receipts](HDMI-GET-OBSERVATION-20261013.md).

Next display implementation is a checked firmware allocation/mode transaction
and actual buffer reservation/cache/lifetime handoff, then Apple console output.
The new GEM capability kernel/package is also built:47 rows and48 bounded
endpoint reads, with six kernel/protocol groups passing in the main rerun.
That capability image has not booted; networking/IRQ/DMA/SSH remain unfinished.
The derived Apple clock read provider closes another SSH import (47→46) and
passes four main software/static-contract groups, but has not run on the Pi.

# Earlier: GEM identity and complete restoration pass on the Pi — 2026-10-13

The distinct selected-source clock trial `pcie-id-trial-vf78_802` passes all
42 records on the Pi. Both GEM MID reads return `00070109`; all 15 clock
register words match before and after. The admitted register profile decodes
SYS 200 MHz / ETH 125 MHz / TSU 50 MHz; this is not independent physical
frequency or gate measurement. Root memory COMMAND/window, endpoint COMMAND,
all six BARs and both Device mappings restore successfully. Actual PM checks
are 62,940 within the unchanged 65,536 limit. No BME, DMA, IRQ delivery,
clock/reset/PHY writes or packets occurred.

The complete 34,072-byte zero-TX capture is valid and fault-free. Independent
SSD Linux return is boot `deb8426f-ab2f-497f-bddd-0cca0984c0d3`, root
`/dev/nvme0n1p2`. The original firmware/zsh pair is restored and hash-verified;
catalog 276 → 281 → 286. [Physical evidence](GATE5-PCIE-IRQ-TRANSPORT.md).
Next implement source-backed MAC/PHY capability/management, then IRQ delivery,
DMA rings and packets. XNU Ethernet and SSH are not yet working.

The distinct bounded capability reader now executes 16 additional design-word
reads inside the existing clock bracket in the full software transport model;
six groups pass independently and in the main-agent rerun. Modeled PM checks
are 63,628 below the unchanged 65,536 limit. No capability package has booted.

The derived Apple clock read provider now closes 47 → 46 full SSH client
imports, zero new/duplicate imports. Native original/derived error tests and
36,936 scale cases pass; a forced read-only target contract links with zero
undefined symbols and verified actual providers. The separately forced setter
still lacks `_settimeofday`. Neither the new clock provider nor SSH has run on
the Pi. [Userland evidence and limits](GATE6-USERLAND.md).

For HDMI, GET framing, original-FDT mailbox resolution and a pure bounded
transaction core now pass 15 combined software groups; the transaction core
also passes an independent review and main-agent six-group rerun. No actual
mailbox request, firmware framebuffer mapping or HDMI text has run. The next
implementation must establish linked buffer ownership/address/cache and actual
ordered mailbox access, not infer framebuffer authority from Linux's display.
An actual standalone query adapter now passes five software groups including
original-FDT/real transaction composition and every fresh register-admission
checkpoint, with explicit native architecture/FIFO doubles. The linked query
package and guarded trial transport remain under review; software tests do not
prove a firmware response.

# Earlier: standalone HDMI handoff observed; working image restored — 2026-10-13

The distinct diagnostic observer passed on the Pi: all 19 prechecks, complete
FDT inventory and RC=0, full fault-checked 14,183-byte zero-TX capture, automatic
NVMe return, independent Linux verification and exact original firmware/zsh
restoration. That display cycle ended at catalog 266. The original tree supplies no simple framebuffer
descriptor, only the firmware framebuffer service; its memory address/geometry
must be queried and qualified before XNU can draw. No framebuffer mapping or
HDMI zsh is claimed. [Physical findings and receipt pins](HDMI-FDT-OBSERVATION-20261013.md).

The subsequent root-forward trial returned actual non-all-ones clock values,
but rejected SYS CTRL=2 before MID because the prior profile required ENABLE11.
All 42 rows and complete 33,945-byte zero-TX capture are valid; the hardware
trial remains failed and its partial state quarantined until reset. Independent
SSD Linux return, exact original firmware/zsh restoration and full chain replay
pass, catalog 276. The Pi is safely in Linux, boot
`d2af120f-0361-43af-a909-c1674e7a3030`, root `/dev/nvme0n1p2`.
[Register observations and recovery](GATE5-PCIE-IRQ-TRANSPORT.md).

Next display work is a GET-only firmware query; pure message/FDT helpers pass
nine focused groups but no mailbox transaction has run. A distinct narrowly
revised selected-source clock candidate is built/tested, not installed or run.
It does not claim independent physical clock/gate measurement.
Original Apple case-search/comparison and minimally corrected signal providers
reduce the full SSH client link from 49 to 47 missing imports, zero duplicates;
four focused groups pass, including actual complete static provider ownership.
This remains a failed full-client link, not working XNU SSH.

# Earlier: UART recovery and initial observer failure — 2026-10-13

Real XNU/zsh over serial remains physically demonstrated. HDMI text/zsh is the
next user-facing milestone. The checked boot-video encoder and inactive
UART-first Apple-renderer mirror now compile and link into the complete target
kernel; eight software groups pass, including 12,288 guarded-RAM glyph cases.
No scanout, framebuffer mapping or active mirror has run on the Pi. The first
distinct FDT-only observation attempt captured zero bytes; it does not prove
observer execution or framebuffer absence. Independent SSH verified a fresh
SSD Linux return, and the original firmware/zsh pair was restored in
`framebuffer-observation-restored-20261013`. After the user reseated the UART
lead, a bounded Linux-only diagnostic received the exact 67-byte marker on the
Mac at 115200 baud, with zero host serial TX, no reboot and no SD writes.
DTR/RTS were asserted before and after raw configuration; the earlier failure's
cause is not established. That Linux boot was
`f98df7b0-184d-4ff9-a2aa-5f710501dd4e`, root `/dev/nvme0n1p2`.
A distinct early-stage diagnostic observer passes package checks but has not
been installed or executed. After the user connected
the monitor, initial checks reported no detection. A fresh check at
2026-10-13 16:46:12 EDT now reports HDMI-A-1 connected/enabled, 256 EDID bytes
and 3840×2160 modes. Linux's active `vc4drmfb` is 3840×2160; this does not
establish a standalone firmware framebuffer or an XNU mapping.

The first live clock/MID trial (`pcie-id-trial-yjofwwhc`) made 15 clock-register
read attempts, all returning `ffffffff`, and stopped before either MID read.
It quarantined the retained maps and partial decode/assignment state without
unsafe compensation. This is a failed hardware trial, not a valid clock result
or successful device access. All 35 diagnostic rows and the full 31,751-byte
zero-TX capture are valid and fault-free. Watchdog recovery, independent SSD
Linux boot `2c770b9b-58b5-4f22-86ed-7e42f18151ed`, and restoration of the original
firmware/zsh pair pass; full byte-only chain replay verifies those receipts.
That restoration ended at catalog 250; the subsequent failed observer attempt
and verified restoration advanced that catalog to 258. Byte-only replay
confirms failed observation, independent Linux return and restored working
loader as separate results. Exact pins and observations are in
[Gate 5 transport evidence](GATE5-PCIE-IRQ-TRANSPORT.md).

The next Ethernet correction qualifies the root bridge's memory-forwarding
COMMAND/window under the existing live owner. Source review shows that this
prerequisite was not configured by the current path. It is a concrete candidate
cause of all-ones reads, not yet a physically proven diagnosis. IRQ, DMA,
Ethernet traffic and SSH remain unfinished.

Real file-backed Apple Libinfo and checked C runtime providers now compose into
the original full SSH client build, exposing genuine additional dependencies.
The latest composed link has 50 unresolved imports, zero duplicates; it still
does not link or run. Different dependency profiles/counts are not interchangeable.
Original Apple stpcpy and a selected genuine dispatch_once/lock slice close the
latest two imports without new dependencies; neither has run on the Pi.
Original strnstr/generated initgroups then close 54 → 52; whole original
if_indextoname, if_nametoindex and ether_addr helpers close three imports and
newly expose ___strncpy_chk, giving 52 → 50. Eight focused predecessor/helper
tests pass, including native ASan/UBSan and actual A76 relocation/layout checks;
this is not target interface enumeration or working networking.

# RP1 Device maps and full restoration pass on the Pi — 2026-10-13

The distinct `pcie-id-trial-omaujuxp` image passes all 25 records on the Pi.
It repeats the accepted same-boot BAR assignment, changes only COMMAND.MEM
through two 16-bit writes, creates the exact private GEM and clock mappings,
unmaps them in reverse order, restores COMMAND to zero, and restores all six
original BAR values. The decode cycle uses 34 config transfers, two writes,
two maps and two unmaps. Actual PM checks are 61,092 within the unchanged
65,536 bound. No endpoint register read, interrupt, DMA or packet transfer
has been performed.

Capture `pcie-decode-cycle-serial-20261013` is 31,039 continuous bytes / zero
TX, SHA `cec5472b643d5a979d12c59cab52d0d70cde7a3e5fef0303e25a6090c3b5bbcf`.
Complete capture health, independent SSD Linux boot
`8f2b1d32-7ea5-4a6c-8856-13126de4f14b`, and original firmware/zsh restoration
pass. Restore `pcie-decode-cycle-restored-20261013`, catalog 230 → 235 → 240;
install/restore 23.433 / 24.128 seconds. Full chain replay passes, verifying
capture, independent return, all publication receipts and the restored pair.

Next user-facing priority: HDMI boot text and the existing zsh shell. A separate
Pi 5 framebuffer parser/reservation helper passes four native/A76 tests;
actual scanout is still untested and both HDMI connectors report disconnected.
Ethernet continues with fresh clock validation and documented GEM identity
reads; full SSH runtime closure continues in parallel (54 imports remain in
the verified combined client link).

# RP1 BAR address assignment and restoration pass on the Pi — 2026-10-13

The distinct `pcie-id-trial-_w3ajzlm` image passes all 23 records. After
same-boot sizing, BAR0/1/2 read back as `00410000/00000000/00400000`, then
restore exactly to `ffffc000/ffc00000/ffff0000`. BAR3–5 stay zero. Assignment
and restoration take 58 config transactions and six writes; COMMAND stays
zero. PM checks total 55,020 within the unchanged 65,536 bound.

Capture `pcie-bars-assignment-serial-20261013` preserves 30,800 continuous
bytes with zero TX, SHA
`9ecc711558219b6b948181506c8f858baa56992f17d2b19a889ee436373384ff`.
Whole-capture fault checks, independent SSD Linux return
`34e1027f-f0fc-42c7-b70e-f4a224e59e7b`, original firmware/zsh restoration and
full chain replay pass. Restore `pcie-bars-assignment-restored-20261013`,
catalog 220 → 225 → 230; install/restore 24.044 / 24.988 seconds.

Next Ethernet work enables memory decoding and maps the exact GEM/clock pages
under the live owner. Device register access, IRQ, DMA and Ethernet traffic
remain unfinished. In parallel, all 176 original OpenSSH client source units
compile; real Apple leaf and socket providers reduce unresolved link imports
from 108 to 90. The full client still does not link or run.

The next user-facing milestone is HDMI boot text and the existing zsh shell,
using a checked framebuffer handoff and Apple's text-console renderer. That
work proceeds alongside Ethernet/SSH. The loader currently supplies no video
buffer, and the latest SSD Linux query reports both HDMI connectors disconnected.

# Twelve-command root and kernel-backed RAND APIs pass on the Pi — 2026-10-13

The distinct `root45-entropy-mob0oyvx` image passes the complete mounted
45-node / 33-file identity, all twelve command outputs/statuses, and the
separate actual zero zsh exit. Existing shell, utilities, pthread and real
packet-crypto tests still pass. Both new diagnostics now execute on the Pi:
original getentropy accepts/rejects the tested requests correctly, and original
LibreSSL RAND delegates successfully through the project stateless adapter.

The kernel reports startup_done=1, zero repetition/adaptive-proportion failure
counts, and 2,958 total / 2,160 accepted / 798 rejected samples. These are
separate observed counters, not an atomic snapshot or entropy qualification.
No random bytes, seeds, hashes of random output or live keys are published.

`root45-entropy-serial-20261013`: 53,324 continuous bytes / 821 TX, SHA
`588dca26f0b1b0c5c141b7251c47ac5160aaa4e27cc887cf6046a64673da9abb`.
Complete fault-checked capture, independent SSD Linux return
`b4facb5d-241b-411f-82a3-5990b2a455ac`, original working-loader restoration
and full chain replay pass; firmware is unchanged. Restore
`root45-entropy-restored-20261013`, catalog 212 → 216 → 220;
install/restore 23.711 / 23.781 seconds. No manual restart or extra soak.

Next: the separately linked bounded BAR assignment/restoration candidate.
Full OpenSSH executable dependencies are being audited in parallel; neither
working Ethernet nor an SSH client/server is claimed by these diagnostics.

# RP1 BAR sizing and exact restoration pass on the Pi — 2026-10-13

The new guard-composition image completes all six BAR slots: 49 config
transactions, 12 writes, three implemented MEM32 BARs, and exact restoration
of every original value. BAR0 is 16 KiB, BAR1 is 4 MiB and BAR2 is 64 KiB;
BAR3–5 are unimplemented. COMMAND remains zero. This proves size/restoration,
not address assignment, device MMIO, interrupt delivery, DMA or Ethernet.

Removing redundant outer checks, while retaining the fresh nested checks,
reduces PM-check cost from 14 to 8 per transport guard. Actual PM count is
44,748, matching `12 + 8 * ((11185 - 1) / 2)`; existing 65,536 limits and
deadlines are unchanged. No cached authority or new MMIO permission is used.

`pcie-guard-composition-serial-20261013`: 30,318 continuous bytes, zero TX,
SHA `ac9bd1f0afe358112eb7056a4a65bdd706db3ea0188dbda8b5cf42eee9b8d7db`.
Full fault-checked capture, independent SSD Linux return
`29cdf7ca-e495-4659-a46e-1eb3f8f8e0b0`, original firmware/zsh restoration and
read-only chain replay pass. Restore `pcie-guard-composition-restored-20261013`,
catalog 202 → 207 → 212; install/restore 22.993 / 23.238 seconds.

Parallel next work: bounded BAR assignment/readback/restoration, and one
12-command userland batch adding entropy API/counter and original LibreSSL
RAND diagnostics. The project-owned stateless getentropy adapter passes host
and linked-target checks; its Pi execution and entropy quality remain unproven.

# Real packet crypto and complete ten-command Pi batch pass — 2026-10-13

`root43-packet-vqgxaczi` physically passes its complete 43-node / 31-file
mounted identity and ten commands. The real OpenSSH/LibreSSL packet workload
passes 48 valid cases and 5,036 rejections through genuine Apple startup,
constructors and pthread services. All command statuses and the separately
queried actual zsh exit are zero. This proves that exact public-data workload,
not live SSH, key exchange, secure-key generation or a working network driver.

`root43-packet-serial-20261013`: 51,397 continuous bytes / 726 TX, SHA
`d96dd7b995555f71150a079e31a6d19afd1c91e375ffd024a749ea2f1bb48fa9`.
Whole-capture fault rejection and normal NVMe selection pass. Independent
Linux boot `3e8c66ce-fdcb-4170-a3a7-4a8d3f07ddc8`, original firmware/zsh
restoration and full read-only chain replay all pass. Restore:
`root43-packet-restored-20261013`, catalog 194 → 198 → 202; installation and
restoration 23.693 / 23.725 seconds. No manual restart or extra soak.

The Ethernet budget correction is separately reviewed offline and being built;
it preserves the existing access boundaries and limits. A future real
getentropy/health-counter diagnostic is also built but not installed or run.
Neither it nor successful packet crypto qualifies the entropy source.

# Ethernet guard failure localized to exhausted PM-check budget — 2026-10-13

The passive owner trace physically reports `PM CHECKS=65536 RC=-1 STATE=4`,
`RPC STAGE=5`, `IRQ STAGE=8`, and firmware sequence 9361. Both clock deadlines
remain in the future; the failed RPC never reaches SMC. The existing PM-check
limit, not elapsed timeout, blocks BAR transaction 9 before any BAR write.
RP1 identification/root routing still succeed; BAR sizing, assignment, IRQ,
DMA and Ethernet remain unproven. Limits and guards were unchanged in this run.

`pcie-owner-trace-serial-20261013`: 30,248 continuous bytes, zero TX, SHA
`ddfe62de09bb44e99afd7b8f20f391ca5f26e637a11c5bcdd41b20f091a29af2`.
Full capture/fault validation, independent SSD Linux return
`4394f030-8e3b-4f58-92a4-bba03a824616`, exact original firmware/zsh restoration
and full read-only replay pass. Restore: `pcie-owner-trace-restored-20261013`,
catalog 184 → 189 → 194; install/restore 22.994 / 24.955 seconds. Diagnostic
failure stays recorded as failure. Next audit full-path check multiplicity and
any redundant nesting without caching authority or loosening finite limits.
The separate 43-node packet-crypto batch is next for physical validation.

# Genuine Apple pthreads and nine-command Pi batch pass — 2026-10-13

The corrected `root42-ready-4h4evl7f` image physically passes mounted identity
for all 42 nodes / 30 files, nine command outputs/statuses, and the separate
actual zsh process-exit query. Genuine Apple startup, four created/joined
threads, 2,048 mutex/allocator operations, four thread-local destructors,
one-time initialization and isolated `errno` all pass on the Pi. Existing
zsh, OpenSSH buffer/primitive diagnostics, real Apple pwd, canonical recovery
utilities and metadata tests also pass. This is not full LibSystem, entropy,
packet-cipher, network or SSH server acceptance.

`root42-ready-serial-20261013` preserves 50,724 continuous bytes, 678 TX bytes,
SHA `7a2ef85150596963423e32d32d3362f076b53887360664b57255e8bf57f5e46e`.
The complete capture passes fault checks through normal NVMe selection.
Independent SSH verifies SSD Linux boot `df0601fc-f5a8-48d6-84e4-cb0a302d7f23`.
The original firmware and working zsh are restored in
`root42-ready-restored-20261013`; full read-only chain replay passes, catalog
176 → 180 → 184. Install/restore took 23.189 / 23.615 seconds.

The late root confirmation reports actual installed read-only mount state
after successful existing watchdog reloads; admission still requires all
identity and fresh-boot checks. No manual restart or extra soak was needed.
Next: a distinct ten-command root adds real packet crypto; a parallel passive
Ethernet diagnostic identifies the owner guard that blocked BAR access.

# Bounded PCIe logging survives; guard blocks first BAR write — 2026-10-13

The new 14-record PCIe diagnostic completes without the earlier log-encoding
panic. RP1 identification and the corrected root route still succeed, but the
BAR caller stops at transaction 9: `CALL=1 RC=-4 STATE=6 WRITES=0`, with
transport `GUARD=4` before the selector write. No BAR sizing, assignment,
device MMIO, IRQ, DMA or network traffic is established. Diagnose the exact
guard/lifetime failure before changing its policy.

`rp1-bars-root-serial-20261013`: 29,772 continuous bytes, zero TX, SHA
`f4dd88808efec1cf692f879cf1c65886f527e4af3c9eb07acf42049258549611`.
Full capture validation rejects faults through normal NVMe selection; this
capture is valid with a failed BAR diagnostic. Independent SSD Linux boot
`761222f1-d187-4eba-bd97-531330b3c848` is verified. Original firmware and zsh
are restored in `rp1-bars-root-restored-20261013`; archive catalog
166 → 171 → 176, install/restore 22.805 / 22.879 seconds.

In parallel the state-confirmed root kernel and new retained-FDT loader are
built. Three actual loader/native geometry tests, nine protocol/kernel tests,
and two actual service-body/compiled-atomic tests pass independently. Corrected
root42 command execution still requires a fresh Pi trial; no pthread runtime
or SSH success is claimed from those host checks.

# Root42 boots; interleaved mount telemetry blocks commands — 2026-10-13

The distinct 42-node/30-file pthread image reaches XNU and the recovery shell.
Its delayed watchdog-readiness marker is intact, but concurrent CPU startup
corrupts the early `RAMROOT:MOUNT` record. Strict admission therefore sends
**zero serial bytes**; none of the nine commands runs. This is a boot-reporting
failure, not evidence that the genuine pthread executable passed or failed.

`root42-pthread-serial-20261013` preserves 39,436 bytes, SHA
`cdd6cd59d5f43ba969ce52fddaa44bc8e6615966e05302ae5aee93372d51af66`.
The recorder rejects the returning boot before its complete NVMe selection
line; independent SSH separately verifies fresh SSD Linux boot
`fb11a075-583a-481f-bbc8-6552336d50c8`. The original firmware and working zsh
loader are restored in `root42-pthread-restored-20261013`, catalog
158 → 162 → 166. Install/restore publication took 23.225 / 23.508 seconds.
No manual power action or additional soak was requested.

Two agents are implementing and independently checking bounded, late reporting
of the actual installed read-only root state, without weakening fresh-image,
FDT, watchdog or complete mounted-file identity checks. The Ethernet agent
has packaged guarded six-BAR sizing/restoration with bounded log records;
hardware acceptance remains pending. Original failed receipts stay unchanged.

# RP1 identified on Pi; post-output logging panic blocks clean acceptance — 2026-10-13

The distinct root-route image physically returns `OK=1 ID=00011de4`, PCIe
Gen 2 ×4, with endpoint `COMMAND=0000`. The root bus register was actually
zero; the guarded single write changes it to `00010100` and all immediate,
final and post-link readbacks agree. Both endpoint header passes succeed.
The missing route explains the prior all-ones reads on this hardware.

**This is RP1 identification evidence, not a clean whole trial.** Immediately
after END, the kernel panics at `log_encode.c:120` (`log_fits_cmd`). The long
diagnostic is printed to serial before its log-encoding path overflows the
256-byte metadata buffer. The prior config trace has the same post-END panic,
previously missed because its protocol checked faults only through END. Neither
run proves clean watchdog-only recovery. Original captures/receipts stay
unchanged; separately hashed health supplements flag both faults. Five new
regressions pass, including both actual traces and post-END failures.

`root-route-serial-20261013` contains 30,080 continuous bytes, zero TX, SHA
`cd2027571ae6b55d64b77772a6ec0d5c6af4248d5ba2d3b0807093dbc192f1b9`.
Automatic f6/NVMe return and fresh SSD Linux boot
`ee1f125a-112c-4da6-9f06-635451451e94` are verified. The original firmware
and working zsh pair are restored in `root-route-restored-20261013`; the
original full receipt replay passes for its narrower ID/return/restoration
scope, catalog 148 → 153 → 158. Install/restore took 22.461 / 22.890 seconds.

Next split diagnostic logging into bounded records without weakening XNU
assertions, and require fault-free output through recovery. Assess the next
guarded BAR sizing/restore step separately; no BAR mapping, interrupt delivery,
DMA, Ethernet traffic or SSH is established. The 42-node pthread/utility image
is independently checked and its single-loader trial tooling is being finished.
No user power action or soak is needed.

# RP1 config trace isolates all-ones reads; baseline restored — 2026-10-13

The distinct config-trace image completes all 32 guarded endpoint reads, but
both 16-dword snapshots contain only `ffffffff`. Link/clock setup, selector
`00100000`, and transfer callbacks succeed; the snapshot correctly rejects
the invalid RP1 profile (`RP1_RC=-4`, `OK=0`). No RP1 identity, BAR access,
IRQ, DMA or Ethernet success is claimed.

The checked root-complex source omits PCI bridge bus-number setup. Fresh
read-only SSD Linux observation confirms this Pi's RP1 bridge routes primary
0 / secondary 1 / subordinate 1 (`0x18=00010100`). The next distinct correction
will program only that route under the existing held-reset/ownership guards,
with immediate/final readbacks. This is a verified source gap and a plausible
cause, not yet a physically proven fix. BAR work stays offline until RP1 ID.

`rp1-config-v3-serial-20261013` retains 29,893 continuous bytes, zero TX, SHA
`9e89d72db9a4d7d77707ad16ad03f6fc84d8a1f42e9032d814f4bcab839738f7`.
Automatic normal NVMe return (after a post-END logging panic, identified above)
and fresh independent Linux boot
`804c0ee2-a4a2-4db8-acc5-08857c983181` pass. Original firmware `413a050e…`
and working zsh `f2aee33a…` are restored in `rp1-config-v3-restored-20261013`.
Full read-only chain replay passes, preserves the failed diagnostic and records
archive catalog 138 → 143 → 148. Install/restore publication took 22.470 /
22.160 seconds. No manual power cycle or soak.

A local replay API omission was fixed with a separately hashed compatibility
adapter exposing one inherited marker constant. Frozen recorder, protocol,
raw capture and original admission seal were not changed; supplemental
provenance enters the restoration seal explicitly. Four actual-capture/negative
regressions pass. [Exact result and hashes](GATE5-PCIE-IRQ-TRANSPORT.md).

In parallel, a distinct genuine Apple pthread startup/create/join diagnostic
now links without undefined or duplicate symbols. Five focused tests pass
independently (0.618 seconds), including actual entry/constructor/symbol ownership
and native host workload checks. Target execution is not yet proven; review
and a useful combined root trial remain ahead of any SSH claim.

# PCIe link and clock setup pass on Pi; RP1 discovery is next — 2026-10-13

The distinct elapsed-time image `pcie-id-trial-y60h5lfb` now completes real
PCIe link training: `LINK_CALL=5 LINK_STEP=14 LINK_RC=0 LINK_CB=41`, measured
reset settling **100,623 us**, one successful status poll in **540 us**.
The overall RP1-ID trial remains failed (`OK=0 LAST=14`): exact phase 14 is
RP1 configuration inspection, **not** clock finishing (phase 13). Controller
and post-link clock setup have returned successfully. The generic last-read
field `0x4068=0x0003e0b0` is stale controller telemetry because the separate
configuration callbacks do not update it. RP1 identification, endpoint writes,
IRQ, DMA and Ethernet are not established. Diagnose that config path, preserving
the accepted elapsed correction and all recovery/permission bounds.

`rp1-link-v2-serial-20261013` contains 28,543 continuous bytes, zero TX, SHA
`792676e8312e1153a05672d916abd925ffd6b38d768561aa056afc5dec0c531d`.
Automatic normal NVMe return and independent SSD Linux boot
`dc5737b5-2559-4830-b4bd-d406c7a77522` are verified. Original firmware
`413a050e…` and working zsh `f2aee33a…` are restored in
`rp1-link-v2-restored-20261013`; full read-only v2 chain replay passes without
reclassifying the failed diagnostic. The preserved archive catalog advances
128 → 133 → 138. Historical archive payloads were **not** all rehashed: the
two selected known-good baseline files and all fresh/current rollback data
were verified, with the full historical metadata retained and no deletion.

Measured publication/validation took **22.634 seconds to install** and
**22.493 seconds to restore**. The previous installation's remote phase alone
took about 105.7 seconds, before another 38.4 seconds of local validation;
these are observed individual runs, not a controlled benchmark. The new
workflow seals one full audit, then checks unchanged bytes without repeatedly
compiling packages or rereading the full archive history. Exact card/root,
current image, fresh rollback, exclusive serial and single-reboot guards remain.
No manual power cycle or soak was requested.

# AXI correction passes on Pi; next failure is link settling — 2026-10-13

The corrected single-CPU `pcie-id-trial-v5t00fib` image physically passes
UBUS configuration (`STEP=5`, `RC=0`, 23 callbacks), QoS, prelink clock and root
complex setup. It reaches link training and releases PERST: the last guarded
read is `0x4064=4`, lifecycle RELEASED, with no recorded guard failure. The
overall RP1-ID diagnostic still fails before identifying RP1 (`LAST=12`).
The actual linked path next measures its guarded 100-ms settling delay;
minimum/110-ms-upper checks are a plausible failure location, not yet a
measured cause. Add passive link return/step/elapsed telemetry without changing
the deadline or issuing additional MMIO.

`rp1-axi-serial-20261013` contains 28,414 continuous bytes, zero TX, SHA
`358c100ab8e668f9bbbccc21aadad79c62747decf372bd53df546618ef600fe9`.
Automatic f6/NVMe recovery is captured. Independent read-only SSH verifies
fresh SSD Linux boot `64659855-bf91-4aeb-a8b6-f5cf196c9bc1`. Original firmware
`413a050e…` and working zsh `f2aee33a…` are explicitly restored in
`rp1-axi-restored-20261013`. Full `pcie_axi_evidence.py` replay passes for
capture/return/restoration, retaining the failed RP1-ID result and 128 inherited
SSD artifacts. Restore plan/result SHA:
`390c73e43cf8b231ebe07b63160c4390178c82e11ed60180016fb507a7bc4d8b` /
`d89c6f95984e3d99e1ed80e27f6842b25587dd954e2fb7463aa2becf7b7cd7ab`.
No endpoint config writes, DMA, IRQ delivery, Ethernet or manual power action
occurred.

Three parallel tracks remain active: precise link-failure diagnosis, genuine
Apple pthread/libkernel startup, and a separately reviewed faster trial path.
The latter removes repeated full build-audits/historical archive reads, not
fresh card/root/image/rollback guards. Its helper tests pass; actual staging
integration and a measured hardware timing result remain pending.

# Expanded root executes eight commands; output oracle needs correction — 2026-10-13

The real `root96-batch-amkl_cna` image boots all four CPUs, mounts the exact
41-node root and passes complete 29-file/self-hash identity. Its single zsh
batch emits zero-status frames for all eight commands and `END:0`: real zsh
smoke, OpenSSH buffer/reset, original ChaCha/Poly1305 public vectors, current
Apple `/bin/pwd -P`, canonical compatibility uname/wc/hexdump, and metadata.

The recorder then correctly stops at its overly strict pwd output oracle:
the actual body is `DARWIN:ZSH:ENTRY`, `DARWIN:ZSH:TSD`, `DARWIN:ZSH:ENTROPY`,
`DARWIN:ZSH:MAIN`, then `/`. Those are the accepted shared startup's messages;
the oracle expected only `/`. All original evidence remains unchanged. This
trial is **incomplete/failed**, not full acceptance: only 585 bytes were sent,
and the third exchange measuring the batch process's actual exit status and
recovery liveness never ran. No SSH server, entropy or Ethernet claim follows.

Evidence: `root41-serial-20261013`, 47,381 bytes, SHA
`50265fdfb7805cc81d225ecf67ac4242df3cfd2d07043cb628716b9d70c37005`;
state SHA `01ac5f495f39432163eb0d0090a31170218ed85462d8b8600a83be11da3a096d`.
Install plan/result hashes are
`26b881944a1199cc0875592ac984ecae1f50eaf6a832b70ea4911ae186eb6fa5` /
`ba9655296e198bb3c8cb3cb612edc25354101f93b8d45c23de2b44d890b85e33`.
The delayed readiness marker worked. A distinct strict v2 oracle now validates
all eight output bodies/statuses from these exact raw bytes; four tests were
independently repeated in 0.131 seconds, including malformed-prefix negatives
and the separate v2 recorder binding.
It still reports `batch_process_exit_verified=false` and does not rewrite the
failed state. A later v2 recorder can retain the original deadline/three-exchange
contract; there is no need to repeat the same hardware run just to diagnose
the oracle.

Independent read-only SSH confirms normal SSD Linux return
`773656c9-3ac7-499e-9a48-3206dd34d80f`; explicit baseline restoration completed
in `root41-restored-20261013`, with original firmware `413a050e…`, known-good
zsh `f2aee33a…` and 118 inherited SSD artifacts. Restore plan/result SHA:
`40c53c882e3edf27dd25b93eb55140b2405d460fb2915e9fe547c3e84b57a0eb` /
`1a18c7b5fdf380ed4d1594c9f8045e3b1b2759790b6c40d227aa48a2778c618e`.
The failed recorder stopped before capturing recovery, so this is
independent Linux-return evidence, not continuous serial proof of the reset.
No manual power action or extra soak was requested.

# PCIe trace identifies reserved-zero AXI mismatch — 2026-10-13

The distinct passive trace completed on the Pi with 28,307 receive-only bytes.
The failing operation is a successful guarded read of controller register
`0x416c`, returning `0x60` after the workaround-bit write: `UBUS_STEP=3`,
`UBUS_RC=-5`, `UBUS_CB=16`, `GUARD=0`, `IO_STAGE=4`. Our readback predicate
requires bits this controller reads as zero and rejects the value before its
outstanding-request fallback. This is not a failed access or demonstrated
lease expiry. Raspberry Pi's controller driver explicitly supports a reserved
timing-fix bit by selecting 15 outstanding requests. A private correction is
being tested consistently across UBUS, QoS and clock consumers; frozen original
sources and all accepted images remain unchanged.

Automatic f6/NVMe recovery and independent SSD Linux boot
`386225a6-2f95-4b53-a0e5-f6f6c56327f7` are verified. Full
`pcie_trace_evidence.py` replay passes against `rp1-trace-installed-20261013`,
`rp1-trace-serial-20261013` and `rp1-trace-restored-20261013`. Original firmware
`413a050e…` and working zsh `f2aee33a…` are explicitly restored; the next
inherited SSD artifact chain has 110 entries. The diagnostic itself remains
failed: no RP1 identity, Ethernet, IRQ or DMA result is claimed.
[Exact trace, hashes and primary reference](GATE5-PCIE-IRQ-TRANSPORT.md).

The next userland pass batches eight utility/shell/SSH-dependency checks into
one zsh invocation, after exact image/root identity and delayed watchdog
readiness. The package and strict three-exchange serial protocol are being
independently checked. No extra soak or manual restart is requested.

# Corrected RAM root boots; multicore telemetry blocked commands — 2026-10-13

The retained-FDT correction reaches XNU, mounts the exact 33-node/2,031,616-byte
read-only RAM root, and presents the recovery shell. In the fresh complete
`root96-fdt-serial-retry-20261013` capture, concurrent CPU startup output damages
the mandatory watchdog marker (`SECONDkS=180` instead of `SECONDS=180`). The
guarded recorder therefore sends **zero bytes** and rejects the later recovery
boot. Neither zsh smoke nor the SSH-buffer executable ran in this attempt.
This is a telemetry/admission failure, not evidence those executables failed.

An earlier recorder window expired before reboot and recorded zero bytes;
`root96-fdt-late-recovery-20261013` separately contains 34,399 receive-only bytes,
late shell readiness and f6/NVMe Linux recovery. It lacks fresh startup identity
and is not substituted for successful command evidence. The fresh retry first
reverified the exact entire FAT/HFS hashes and used a newly armed capture.

Independent SSH confirms subsequent SSD Linux boot
`cd2e8f6a-a853-49ea-bcf3-dfc0a3e6c831`. Explicit restoration completed in
`root96-fdt-restored-20261013`: normal firmware `413a050e…`, known-good zsh
`f2aee33a…`, 96 inherited SSD artifacts plus this receipt's own backups.
Plan/result SHAs:
`22d40c0f1ec56a2f5fc611a7692198c893859f2691d5bb0962244e02c7de9a8b`,
`173938cb4c8025bafc9d1f2ebc2ce26386d8a51ed502d04cd75dd15a2f00f9dd`.
No manual power cycle, storage durability claim, or repeated soak.

A distinct offline kernel moves one-shot watchdog readiness telemetry to the
first actual successful terminal reload, away from immediate SMP startup.
The 180-second deadline and 15-second hardware reload value are unchanged.
It does not claim arbitrary console serialization. Two focused tests pass,
including actual modified C bodies under ASan/UBSan with explicit clock/MMIO
doubles. Package integration and a fresh strict marker parser remain required.
Independent PCIe failure telemetry, Apple utility/PATH root and genuine SSH
crypto/platform providers continue in parallel. Full objective remains active.

# Physical PCIe provider reached; UBUS interval failed safely — 2026-10-13

The distinct single-CPU identification image `pcie-id-trial-wpo7wy6_`
(`69e0839c…`) and secure firmware `dc8dcbd3…` were installed and booted once.
XNU passed the retained-FDT/VM boundary and reached the real IOKit caller:

```
RPI5XNU:PCIEID:PREPARED OK=1 CPUS=1
RPI5XNU:PCIEID:END OK=0 PHASE=6 LAST=7 LIFE=1 FLAGS=1f ID=00000000 COMMAND=0000 BAR1=00000000 GEN=0 LANES=0
```

The 28,202-byte continuous capture is receive-only. Phase 7 follows a successful
initial PHY sequence; the failure is now narrowed to the UBUS configuration/
guard interval, not RP1 identification or Ethernet traffic. A roughly 5.35 ms
host receive interval from PREPARED to END is not evidence of lease expiry.
Do not relax the register readback rules from this observation. Prepare a
distinct passive diagnostic carrying the failing callback/register/result.

Watchdog recovery selected f6/NVMe. Independent SSH confirms normal SSD Linux
boot `9dc47716-f98b-44d5-9d23-35f1f5c6b169`. Both original firmware `413a050e…`
and known-good zsh `f2aee33a…` were explicitly restored, with 92 preserved SSD
artifacts. `rp1-id-restored-20261013` plan/result SHAs:
`4af93755cb3dbfc4d51b777b64819a9a604ac1cca71040d20ee0c03147dccfa3`,
`667b44eb067fac81de833ad6427f8c40650ddcaf7a3b3c6248a93dcc7a6ee850`.
Capture SHA `4bbd4d0e9df087f275c35d9094e8fb8a0609ff6cd3bfbc291115b2121113abdf`.
The failed diagnostic remains failed; no RP1 ID, IRQ delivery, DMA, packets or
usable Ethernet is claimed. No manual power action or soak was required.

Next independently run the corrected 33-node shell/SSH-buffer package while
Ethernet failure telemetry and the separate 41-node Apple-command/PATH root
continue offline. Full objective and Gate 4 hold remain active.

# Combined RAM-root boot failed safely; handoff mismatch identified — 2026-10-13

The distinct 180-second candidate `bl33-probe-gm1ci0lg` (SHA
`0a9593c91d52dca88e587c155dd3fe53b89cf7d8100faf815c0ddd118348ad91`)
was installed and tried once. The 26,606-byte capture ends kernel progress at
`XDAZPMVCISTBDELHK`, followed by watchdog recovery. **Zero serial bytes were
sent; no expanded-root, zsh or SSH-buffer runtime test ran.** The recorder
correctly rejected the second boot before admitting commands.

The linked `firmware-fdt-handoff-20261012-final/arm_init.c.o` requires the
`/chosen/rpi5-firmware-fdt` descriptor between checkpoints K and W. The ordinary
loader used for this composition omitted that descriptor. This is a concrete
loader/kernel integration mismatch, not evidence of a defective SD card or
failed SSH buffer implementation. Preserve the failed image and capture; build
a distinct corrected loader with the retained-FDT and Device-range handoff.

Independent read-only SSH verifies normal NVMe Linux boot
`6879aaf3-a600-4bd8-9f42-1e5cfbfbad35`, root `/dev/nvme0n1p2`, and the exact card.
`root96-restored-20261013` restored known-good zsh `f2aee33a…`, kept original
firmware `413a050e…`, and preserved 82 inherited SSD artifacts. Restoration
plan/result SHAs are `6f93cfabf3be62b5e88eeea4de3998ff22e00ae5f31bccda34290e581674e79a`
and `2595017f3040639f4d1268b2a55cb66702f11548ef57caf825afda9cfb5b59b0`.
The failed candidate remains recoverable on SSD. Earlier reclaim removed only
the hash-verified redundant SD file `probe.socket-identity-passed-20261012.bin`,
after archiving it; another exact known-good SD backup remains.

Evidence is in `root96-serial-20261013/{armed.json,state.json,serial.bin,failed-linux-return.json}`
and the reclaim/install/restore receipts. Recovery is independently verified,
**not** a successful combined-root trial. No manual restart or soak was needed.
PCIe single-CPU ID discovery and current Apple utility/runtime work continue
in parallel. The complete objective and separate Gate 4 hold remain active.

# Physical firmware ABI and autonomous recovery passed — 2026-10-13

The Mac again has a direct Pi-LAN route. Fresh SSH verified the Pi on
`/dev/nvme0n1p2` before one guarded trial. The original installer refused the
nearly full FAT partition before any write; a distinct tested profile reused
the existing exact zsh backup, without deleting a file. Seven focused reuse/
failure/receipt tests pass. Both firmware and BL33 were then installed,
captured with zero serial TX, tested once, and explicitly restored.

Real-board results: all 19 ABI markers, five SMC calls, RC 0, sequence 4/facts
0x1f, 485 PM checks, one watchdog reload and three selective GIC disable writes.
The continuous 45,071-byte capture shows watchdog recovery and actual f6/NVMe
selection; the host ARM-to-BOOTSYS interval is 16.633365 seconds. Independent
SSH verifies normal Linux boot `54e0eebb-058e-4954-91b1-b1fed9aa37bd`, exact
NVMe root/card and unmounted SD partitions. Full evidence replay passes after
restoring firmware `413a050e…` and zsh `f2aee33a…`; inherited SSD backup count
is now 70. No controller writes, DMA, new XNU PE execution, Ethernet or Gate 4
durability result is inferred. [Exact evidence](GATE5-PCIE-IRQ-TRANSPORT.md).

Parallel builds now include a genuine static OpenSSH buffer executable, an
expanded 96-entry RAM-root kernel, a 33-node/22-file root with regenerated
identity catalogue, and corrected RP1 configuration reads. Combined image
`build/rpi5/bl33-probe-ke8q4far/probe.bin` is 20,138,176 bytes, SHA
`b9186a1e864878fbc211566296b13a3dde0d93e0ab70476a1209a9d204a53990`.
Its hardware trial and concrete PCIe provider/caller remain next. Full objective
and separate Gate 4 hold remain active; no manual restart or soak was requested.

# OpenSSH reset invariant corrected in separate archive — 2026-10-13

One documented source overlay clamps reset allocation to the retained maximum;
the original Apple checkout/archive/failing reproducer remain pristine. All
bytes outside `sshbuf_reset` are identical; production global definition and
external dependency sets are unchanged. No stub or fatal-check bypass.
Distinct Cortex-A76 archive: 105,472 bytes, SHA 51596ace…; 1,587 pins match.
Three focused tests pass (2.559s): 514 capacities/three rounds, zeroization,
read-only/parent behavior, ordinary original buffer tests and an extra native
host-only allocation-failure interposition. Same original reproducer now reaches
its intentional return-7 sentinel rather than SIGSEGV; dedicated new reset
tests return zero. **Native host/compile evidence, not Pi runtime or SSH.**
[Exact correction, immutable baseline and limits](GATE6-USERLAND.md).
Next real reachable target dependency closure, crypto/entropy and complete
SSH process/auth/privsep/session/PTY integration, plus independent Ethernet.
No VM/Pi root/kernel/image/firmware, board/SD/serial/network/reboot change or
broad suite rerun. Prior 16 firmware-tooling source pins match unchanged.
Current Pi OS/boot was not re-observed during this offline step. Full objective
and the separate Gate 4 durability hold remain active.

# Original Apple OpenSSH dependency archive built offline — 2026-10-13

Pinned pristine Apple OpenSSH snapshot f386b2e9… / OpenSSH_10.0p2 in a new
Pi-only checkout. Twelve unchanged buffer/error/compat/signal/log/allocator/
pattern/fatal support units compile for Cortex-A76 into a 105,456-byte archive,
SHA de8d5003…; 1,461 unique source/header/output pins match. Original config
retains crypto/PAM/sandbox declarations; public OpenSSL 3.6.5 headers are only
compile inputs, no crypto runtime or full Apple Xcode integration is supplied.
No replacement stubs. Three focused tests pass (2.148s) with actual source and
native libSystem/ASan/UBSan, **not Pi static linkage or execution**.
A separate original-code low-max/reset SIGSEGV is preserved and unfixed; it is
not waived by normal buffer-test success or assigned a security severity.
Conservative name inventory finds 100 external names, 35 in three archives,
65 absent there; excludes separate syscall/startup objects and unused-function
reachability, so **not 65 missing Pi APIs**. Full SSH/crypto/privsep/runtime and
real Ethernet remain incomplete. [Detailed source, artifact and next steps](GATE6-USERLAND.md).
Existing VM work, Pi root/kernel/images and prior 16 firmware-tooling pins are
unchanged. No board/SD/serial/firmware/reboot action or broad suite rerun. Last
network finding remains historical; Pi OS/boot was not re-observed this step.
Full objective and separate Gate 4 hold remain active.

# Recovery evidence/return collector ready; Pi LAN route unavailable — 2026-10-13

Added strict full installed-pair/capture/new-Linux/dual-restoration replay and a
single-attempt read-only Linux-return collector. Full zero-TX tagged ABI bytes,
armed snapshot, receive coverage/times, actual f6/NVMe selection, independent
new exact SSD/card identity and both restored original hashes are separately
required. No controller/power/DMA/XNU PE/Ethernet/durability permission follows
from consistency alone. **Nine new focused tests pass (23.591s)** with explicit
synthetic serial/receipt/SSH fixtures; no broad suite or physical trial.
Prior 16 installer/recorder source pins still match unchanged.
[Implementation and validation limits](GATE5-PCIE-IRQ-TRANSPORT.md).
Fresh SSH timed out. Mac route lookup for 192.168.4.23 returns **default gateway
10.0.0.1 on en0**, not a direct/specific Pi-LAN route; known mDNS name did not
resolve and no ARP entry exists. Current Pi OS/boot remains unverified, not
assumed powered off or XNU. No SD/firmware/serial/power/reboot action occurred.
Next network reachability, fresh SSD/card/sole-owner verification, then the
single prepared guarded ABI/recovery/restore trial. No Pi power cycle is called
for by this network finding. Offline scope and separate Gate 4 hold remain.

# Dual firmware/loader tooling ready; live Pi state unverified — 2026-10-13

Implemented distinct guarded `bl31.bin` + `probe.bin` publication/explicit
restore, complete raw/file backups, pair staging/readback and durable SSD
publication journal. Exact latest FAT/60-artifact ancestry, typed receipts,
owned mounts and config/MBR/HFS protections; no two-file/FAT power-loss atomicity,
automatic retry or implicit rollback. Receive-only installation-bound recorder
has source/pair/tag checks, existing-port refusal, exclusive serial access and
a cooperating local OS board lease. No TX/reboot/reopen on disconnect. Full ABI
trace alone is not autonomous SSD-return or XNU PE/IOKit execution evidence.
All **17 focused tooling tests pass (43.927s)**, including copy/rename/journal
failure boundaries, mixed-pair preservation, restore, typed ancestry/chain,
zero-TX/fault/disconnect and actual OS lease exclusion. No broad suite rerun.
[Implementation, exact plan-only artifact and next live step](GATE5-PCIE-IRQ-TRANSPORT.md).
Local plan-only output `fwabi-pair-plan-20261013` has 16 verified source/archive
pins and no remote run. Last verified boot ID is not current authority: both
fresh SSH attempts to 192.168.4.23 timed out. Mac probe exists, no open reader
or other trial coordinator observed. **Current Pi OS/boot unverified.** No SD
mount/write, serial open, firmware install, reboot/power or new board execution.
Next fresh SSD Linux/card/sole-owner verification, guarded dual staging, armed
continuous receive-only capture, one bounded ABI/recovery boot, new normal NVMe
return and explicit pair restoration. Controller writes remain independently
held; full objective and Gate 4 durability hold are unchanged.

# Standalone firmware ABI/recovery caller built — 2026-10-13

Distinct 55,552-byte BL33 now executes the actual one-shot PM/IRQ/firmware-client
cores and real SMC leaf. Original-FDT/CPU/entry validation; one watchdog reload,
three selective GIC-disable writes, QUERY/CLAIM/three CHECKs, terminal park.
No controller/reset/calibration/endpoint/DMA writes, XNU transfer or full
ownership claim. Package `pcie-fwabi-y_995zop`, image SHA 3cd15bad…; 9,088 pins,
17 package/11 emitted-leaf checks and zero undefined symbols. Strict 19-line
tagged ABI replay validates exact sequence, owner, counters and write/check
budgets; does not itself prove installed identity or autonomous reset return.
All **101 focused regressions pass (40.210 seconds)**, including actual protocol/
cores/firmware service under explicit leaf doubles, all 982 PM-read failures,
15 record failures, 20 ABI mutations and saved physical evidence replay.
Prior complete kernel's 11,505 pins reverify unchanged.
[Exact package, validation limits and next board step](GATE5-PCIE-IRQ-TRANSPORT.md).
Fresh SSH verifies SSD Linux boot 3977a538… and both SD partitions unmounted.
No serial/media/firmware/power/reboot operation or new board execution. Next
guarded dual `bl31.bin`/`probe.bin` installer+restore against current FAT/60
artifacts, then continuous receive-only ABI/recovery trial before controller
writes. Full Ethernet/zsh/TTY/SSH/Apple userland and separate Gate 4 remain.

# Actual XNU firmware client wired / full kernel linked — 2026-10-13

Actual controller startup now claims PM once, NS IRQ, then the real EL3
QUERY/CLAIM before reset/calibration. Actual guards bracket the independent
provider with fresh IRQ/firmware checks; remaining power/source/endpoint/DMA
contract stays required. New PE owner permanently binds/retains the real thread;
real SMCCC64 leaf zeros reserved arguments and returns four exact registers.
Missing/error firmware refuses controller access. Failed claim is terminal with
local interrupts masked; future caller must park for owned watchdog recovery.
Distinct complete kernel: 17,973,584 bytes, SHA 59f76af5…; 11,505 pins match,
zero undefined symbols/new warnings, 25 actual selected entries/seven original
initializers retained and native loader host-buffer checks agree. All 94 focused
regressions pass in 34.200 seconds, including saved physical evidence replay.
[Full artifact, sequencing, explicit doubles and next board step](GATE5-PCIE-IRQ-TRANSPORT.md).
Fresh SSH remains SSD Linux boot 3977a538… with SD unmounted; no install,
serial/media write/mount, firmware/power/reboot or new XNU execution. Next
firmware-ABI caller/package and guarded dual firmware/loader trial against the
current restored FAT and 60 artifacts; then complete domain/endpoint/DMA owner
and actual controller/RP1/IRQ/GEM progression. Full objective and Gate 4 remain.

# Actual EL3 controller-verification service built — 2026-10-13

New real TF-A fast-SiP producer reads the secure GIC view, selected mask/active
state, controller-1 reset/RESCAL accessibility and existing PM countdown. One
trusted-NS owner, irreversible claim, fresh checks, ten-second/check-cap bounds,
one-attempt lock, quarantine/atomic output; no controller/PM/IRQ/clock writes,
DMA grant, release or retry. Distinct full firmware image builds/audits with
9,024 matching pins and 336 bytes of added C frames. All 91 focused tests pass
(25.379 seconds), including saved physical access/recovery/zsh/socket replay.
[Exact firmware artifact, ABI and remaining integration](GATE5-PCIE-IRQ-TRANSPORT.md).
Not installed or board-tested; does not finish power/shared-domain/source/
endpoint/DMA ownership. Existing firmware, zsh and kernel images are preserved.
Fresh SSH still verifies SSD Linux boot `3977a538-fae5-434d-a94f-50c9422fea84`
and unmounted SD. Next real XNU SMC consumer/owner/startup/terminal park and
dual firmware/loader ABI/recovery trial, preserving both old firmware and zsh
against the current restored baseline/60 inherited artifacts. Full objective
and separate Gate 4 remain active. No serial/media/firmware/power/reboot action.

# Physical read-only PCIe access passed / zsh restored — 2026-10-12

All 30 exact read pairs physically complete, including true halfword loads,
in 578,620 us, RC 0 / 184 callbacks. Both snapshots agree; status 0x1e080 meets
the project's RC-down predicate, not link-up. No PCIe/config/RP1/IRQ/DMA write
or Ethernet claim. Continuous 45,200-byte zero-TX capture then shows autonomous
reset/bootloader, actual 0xf6 override and NVMe boot. Independent SSH confirms
new SSD Linux boot `3977a538-fae5-434d-a94f-50c9422fea84` and unmounted SD.
Guarded restoration rechecks all 56 inherited artifacts plus fresh complete
raw snapshots and restores working zsh hash f2aee33a…; current FAT fd2d2072… .
[Exact artifacts, replay, limitations and next controller steps](GATE5-ACCESS.md).
Next installation must inherit **60 artifacts** from this restored receipt.
Full objective stays active. Next concrete owner/admission + actual controller
caller and RP1/config/BAR/IRQ/DMA/GEM, not a read-only marker promoted to driver
success. No manual power cycle, repeat/soak, firmware/config/HFS change or new
XNU userland trial. Gate 4 durability remains separately held.

# Physical autonomous watchdog recovery passed / zsh restored — 2026-10-12

Exact watchdog-only image/tag executes the real PM lease on the board:
54 MHz counter, route 0x222, one reload, armed 983,040→checked 981,157,
108,173-tick wait, RC 0, 12 callbacks and no-servicing stop. One uninterrupted
44,111-byte zero-TX capture then records BOOTSYS, bootloader, actual 0xf6
override and NVMe selection. Independent SSH confirms new SSD Linux boot
`2407dd80-a11d-47f0-9ae0-57f5c47345ef`; both SD partitions are unmounted.
Explicit guarded restoration verifies all 48 prior artifacts, full fresh raw
snapshots and restored working zsh hash f2aee33a…; new FAT hash 0999f771… .
[Physical receipts, aggregate replay and initial cleanup diagnosis](GATE5-WATCHDOG-PHYSICAL.md).
No repeated install/boot, manual power cycle, soak, config/firmware/HFS change,
new XNU userland execution or PCIe diagnostic access. Earlier source/build
artifacts retain their historical claims. Next guarded read-only PCIe trial
must use the restored receipt and 52 inherited artifacts, not the old FAT.
Full objective and separate Gate 4 remain active; Ethernet is not yet running.

# Watchdog-only candidate built and tested — 2026-10-12

Distinct `pm-recovery-bro7oklj/probe.bin` (38,592 bytes) links the actual
unchanged PM lease and new primary-only/fatal-vector entry. Fixed-address PM
read/countdown-write leaves, one reload, finite two-ms counter wait with every
regression boundary checked, tagged/drained observations and no-servicing park.
No XNU, PCIe/GIC/reset/calibration/RP1/DMA access or reset-route write.
All 61 focused tests pass (17.097 seconds), all 16 local emitted-image checks
pass, accepted 2,435/2,411 kernel pins match, and the unchanged physical zsh/
socket package retains all 35 checks. [Evidence and remaining physical gate](GATE5-WATCHDOG-ONLY.md).
Fresh SSH confirms the same SSD boot/root and both SD partitions unmounted.
No image installed, SD block write/mount, serial open/input, reboot/power or
firmware/config change. No new physical reset-return or Ethernet claim.
Next guarded 44-artifact/current-image preservation and installer/rollback,
then continuous image-bound capture around one watchdog-only software SD boot.
The full objective and separate Gate 4 hold remain active; no extra soak.

# Fresh installed boot/recovery reference — 2026-10-12

The Pi is freshly verified on SSD Linux, same boot
`8512e93e-ec70-4715-bb02-d118afe393ed`; bootloader mode 6/partition 1/tryboot 0.
Exact-card RO capture verifies the installed physical zsh/socket image, every
protected file and whole MBR/FAT hashes against the accepted install, equal
before/after the owned RO FAT mount. Both SD partitions are unmounted afterward.
SD `set_reboot_order=0xf6` is now a fresh observed configuration, not an old
assumption; EEPROM remains SD-first `0xf461`. The firmware watchdog request is
**60 seconds**, not the standalone diagnostic's planned 15-second reload.
These are distinct controls; no config change is implied by the difference.
[Immutable evidence and reset-trial sequence](GATE5-PCIE-RECOVERY-REFERENCE.md).
All **48 selected tests pass** in 10.452 seconds, including 12 new guarded
reference tests and preserved physical zsh/socket replay. Accepted 2,435/2,411
kernel pins and 35 unchanged zsh/socket checks also pass. Current/exact archived
source hashes agree. No SD write, HFS mount, serial, reboot/power, firmware/
config or accepted image/root change; HFS data and the NVMe backup chain were
not rehashed by this reader. Prior 286-test kernel results remain separate.
Next prepare one watchdog-only trial with current-image/44-artifact protection
and uninterrupted capture, prove actual reset plus a new SSD boot, then bounded
PCIe access and concrete shared-domain/endpoint/DMA/controller/RP1/GEM bring-up.
Configured order is NOT a latched-register, running-watchdog, physical return
or PCIe admission proof. Full objective and separate Gate 4 remain active.

# Actual controller / IRQ lease wiring — 2026-10-12

A distinct complete kernel now wires one real watchdog claim, then the actual
selective IRQ lease, before reset44/RESCAL/SerDes. XNU's interrupt API handles
the local mask/state accounting; failed IRQ claim is terminal and does not
restore local interrupts. The real guard brackets the independent provider
with fresh same-owner IRQ checks and rechecks thread/singleton/open provider/
phase after the callback. PRECLAIM no longer implies a lease already exists.
Four focused actual-body/model/real-build tests pass, including all 92/15
modeled watchdog/provider failures and both prior interrupt states. The new
unit is warning-free, linkage has no undefined symbols/new warnings, all 18
controller/IRQ definitions and seven original initializers are retained, and
native loader host-buffer validation plus all 2,435 pins pass.
All **286 selected regressions pass** in 172.591 seconds with localhost socket
access; all 35 checks on the unchanged tested zsh/socket package pass.
[Exact artifact, behavior and verification boundaries](GATE5-PCIE-IRQ-TRANSPORT.md).
No concrete power/shared-domain/firmware/source/endpoint/DMA/recovery provider,
boot caller, combined package, installation, board trial or Ethernet proof.
Next close those physical prerequisites, then guarded controller/RP1/config/
BAR/IRQ/DMA/GEM and wire validation. Full goal and separate Gate 4 remain
active; accepted images/root, Pi, serial, media, power, firmware, reboot and
soak are untouched. No fresh external OS/root observation is claimed.

# Concrete selective non-secure SPI mask lease — 2026-10-12

A distinct complete kernel now compiles/links actual PE claim/check functions
over the existing GIC Device mapping and PM lease. It writes only PCIe2's
three exact ICENABLER masks, retains/binds the owning thread until reset,
rechecks selected enable/active state, records pending without clearing it,
and quarantines failures with atomic output. All 106/61 core callback failure
points and the actual PE body pass native host models; actual units are warning-
free, complete linkage has no undefined symbols/new warnings, 2,411 pins and
native-loader host-buffer checks pass. [Artifact and important sequencing/security boundaries](GATE5-PCIE-IRQ-MASK.md).
All **282 selected regressions pass** in 150.979 seconds, including localhost
socket checks; the unchanged physically tested zsh/socket package retains all
35 passing checks.
This is not secure-firmware ownership, full power/shared-domain/endpoint/DMA
admission or interrupt delivery. No boot caller/controller wiring, combined
image, install, board trial or Ethernet claim. Next wire this lease after the
existing single PM claim and before reset MMIO, then fresh same-owner checks;
do not call it from PRECLAIM or claim the watchdog twice. Full objective and
separate Gate 4 remain active; accepted images/root, Pi, serial, media, power,
firmware, reboot and soak state are unchanged.

# Fresh Linux PCIe lifecycle reference — 2026-10-12

SSH now verifies SSD Linux on boot `8512e93e-ec70-4715-bb02-d118afe393ed`.
A new read-only, default-plan collector captured two stable PCIe1/2 power,
clock, IRQ and MSI metadata snapshots, with independent final root/boot checks.
It derives PCIe2 GIC bank masks 5/6=`0xffffffff`, 8=`0x000007e0`, explicitly
excluding NVMe direct/MSI routes. GEM's live Linux clocks are 200/200/50/125 MHz.
PCI devices report active, but host runtime-power interfaces report unsupported;
clock-property absence/framework state is not XNU power or accessibility proof.
All 26 selected tests, prior accepted kernel pin sets and 35 unchanged zsh/socket
checks pass. [Evidence, precise exclusions and provider next steps](GATE5-PCIE-LIFECYCLE-REFERENCE.md).
No reboot, serial operation, driver/power change, mount, SD block access/write,
firmware edit, new image or soak. Current SD image/config bytes and autonomous
reset/SSD return remain unverified; full Ethernet/SSH/TTY and separate Gate 4
remain open. The earlier OS-unverified statements below are historical.

# Actual RC/windows/link/clock composition — 2026-10-12

The real IOKit owner now has one entry composing the actual prior chain,
RC/window setup, bounded link training and post-link CLKREQ on the same
sessions/maps/single watchdog claim. It adds emitted true LE16 accesses,
guarded one-ms delay chunks and fresh unused-window inspections before each
RC/window/pre-release check. Five focused tests pass with 12,806 modeled
owner-guard failures and 12,810 provider failures across all clock modes;
missing callbacks refuse before claiming. Three actual units compile warning-
free; a separate complete kernel links without undefined symbols or new linker
warnings. Native real-loader host-buffer validation and all 2,380 pins pass.
[Artifact, exact integration and provider boundary](GATE5-PCIE-CONTROLLER.md).
All **268 selected regressions pass** in 137.465 seconds with localhost UDP/TCP
access. Prior pin sets and 35 unchanged tested zsh/socket checks revalidate.
This connects controller operations, not the missing concrete inherited-domain/
shared lifecycle, IRQ/endpoint/DMA-quiescence or physical recovery provider.
No provider personality/boot caller, combined package/install/board trial or
trained physical link/RP1/packet/Ethernet claim. Next concrete provider and
access/recovery evidence, combined package/preflight, then actual RP1 config/
BAR discovery, IRQ/DMA/GEM and wire validation. Full zsh/TTY, SSH/sockets,
Apple CLI tools/Darwin layout and recovery plus separate Gate 4 hold stay
active. Accepted source/image/root and Pi/serial/SD/power/firmware/reboot/soak
state are untouched; no fresh OS/root observation is claimed.

# Clock policy and pre-link L0s advertisement — 2026-10-12

The actual owner now honors original-FDT `aspm-no-l0s` after its real prior
chain, without releasing PERST. A new core also implements all post-link
CLKREQ modes; absent explicitly resolves to default, safe/no-l1ss remove L1SS
advertisement before their mode write. Root ASPM/clock-PM remain disabled.
Five focused tests pass with 1,124 callback-failure and 1,124 dependency-loss
positions, 280 all-ones reads, exact phase permissions and actual compilation/
complete linkage. Both new units are warning-free; no undefined symbols or
new linker warnings. Native loader host-buffer checks, all 2,343 new pins and
all prior accepted pin sets plus 35 unchanged zsh/socket checks pass.
[Artifact, controller semantics and integration limit](GATE5-PCIE-CLOCK.md).
All **263 selected regressions pass** in 116.236 seconds with localhost access
for native UDP/TCP tests; no physical network or whole-repository claim.
Post-link CLKREQ is compiled, not transport-wired: concrete power/clock/shared
ownership, IRQ/endpoint/DMA quiescence and recovery still precede real RC/
windows/link and post-link programming, then config/BAR/IRQ/DMA/GEM. No provider/
boot caller, package/install/physical activation or Ethernet claim. Full zsh/
TTY, SSH/sockets, Apple CLI tools/Darwin layout and recovery stay in scope;
Gate 4 and accepted images/sources/root remain unchanged. No Pi, serial, SD,
power, firmware, reboot, soak or fresh OS/root observation occurred.

# Original-FDT options and actual QoS continuation — 2026-10-12

Real controller preparation now validates the full original firmware options
before provider/map ownership. The pinned stock DTB passes unchanged, including
its VDM priority map; unsupported/malformed requests reject instead of being
silently ignored. A new actual IOKit continuation applies FIFO/VDM maps through
the same sessions, Device mapping and watchdog claim after the prior real chain.
Six focused tests pass, including 425 callback-failure/425 dependency-loss
positions, immediate/final readbacks, exact old/new access permissions and real
warning-free compilation. A distinct complete kernel links without undefined
symbols or new warnings; native loader host-buffer checks and all 2,312 pins
pass. The tested unchanged zsh/socket package retains all 35 passing checks.
[Artifact, option semantics and limits](GATE5-PCIE-PROFILE-QOS.md).
All **258 selected regressions pass** in 108.009 seconds with local-loopback
access for the native socket cases.
CLKREQ/ASPM are decoded, not programmed. Concrete inherited-domain/shared
ownership, IRQ/endpoint/DMA quiescence and recovery remain required before
RC/windows/link/config/BAR/IRQ/DMA/GEM activation. No provider/boot caller,
physical acceptance or Ethernet claim. Full zsh/TTY, SSH, Apple userland/layout
and recovery scope plus Gate 4 hold stay intact. No accepted source/image/root
change, Pi/serial/media/power/firmware/reboot/soak action or current-root claim.

# Read-only unused-window continuation — 2026-10-12

The actual IOKit PHY/UBUS owner now calls a read-only unused-window inspector
on the same sessions, mapping and watchdog claim. Its new phase admits exactly
23 reads and no writes; two snapshots check inactive inbound slots 4–10 and
outbound slots 2–3, including high address bytes and stable tuples. Six focused
tests pass with failure/drift/ownership models, exact permissions and real
warning-free kernel compilation. A distinct complete kernel links with zero
undefined symbols or new linker warnings; native actual-loader host-buffer
validation passes. All 2,272 pins and 35 unchanged tested zsh/socket checks pass.
All **252 selected regressions pass** in 97.751 seconds with localhost access;
the initial sandbox denied two native UDP-bind cases, resolved on full rerun.
[Exact artifact, semantics and limits](GATE5-PCIE-UNUSED-WINDOWS.md).
Not installed/booted or physical admission. The prior initial PHY/UBUS sequence
still writes; only the added inspection is read-only. Genuine power/clocks,
shared lifecycle, endpoint/IRQ/DMA quiescence and recovery remain required;
this is not the whole active-window `check_quiescent` provider. Next full FDT
profile/concrete provider and RC/windows/link, then config/BAR/IRQ/DMA/GEM.
Full zsh/TTY, Ethernet, SSH, Apple userland/layout and recovery scope stays
active; accepted images/sources/root and Gate 4 hold are unchanged. No Pi,
serial/SD/power/firmware/reboot/soak action or current-OS/root claim.

# Complete PCI/FDT kernel linkage — 2026-10-12

A distinct **17,936,240-byte complete kernel** now links the original Apple PCI
family, real PHY/UBUS transport, watchdog owner and actual retained-FDT kernel
path with the original source-built crypto/pthread/HFS providers. Zero undefined
symbols; no new linker warnings. Baseline replay matches all bytes except the
exact 16-byte build UUID. The final link replaces old arm_init/pe_fiq objects
and uses pinned constituents to preserve the private reset entry. All seven
added initializers have unique executable targets and genuine loader fixups
in the existing read-only table. Five focused tests pass; native real-loader
copy/rebase checks agree for all 105,819 relocations.
[Artifact, replay details and limits](GATE5-PCIE-KERNEL-LINK.md).
All **246 selected regressions pass** in 85.373 seconds with localhost test
access. All 2,241 complete-kernel pins and preceding accepted component pins
revalidate; the unchanged tested zsh/socket package passes its 35 checks.
Not installed/booted or packaged with the new loader; constructor execution,
provider/boot caller, power/clock/shared ownership, quiescence/recovery and
actual PCIe/RP1/IRQ/DMA/GEM remain unproven. No Ethernet claim. Accepted
zsh/socket/source/image/root bytes and Gate 4 hold are unchanged. No Pi,
serial/SD/power/firmware/reboot/soak operation or current-OS observation.

# Retained firmware tree → kernel PCIe preparation — 2026-10-12

A separate loader/kernel-component build now publishes only a retained-FDT
descriptor, validates its Normal-RAM/post-kernel lifetime in the real early
kernel, creates a private Apple OSData copy with seed values erased, and feeds
the actual PCIe owner's strict decoder via `prepareBoot`. Four focused tests
pass, including real resolver/handoff/seed/Apple-tree serialization and actual
kernel compilation/partial linkage. New loader bound leaves 4,032 stack bytes;
opt-out recompilation of both patched loader units reproduces the prior image.
[Exact artifact and limits](GATE5-FIRMWARE-FDT-HANDOFF.md).
All **241 selected regressions pass** in 82.286 seconds. Final artifact pins
and the unchanged tested zsh/socket package's 35 host checks revalidate.
No boot caller, activation, complete-kernel/physical acceptance or Ethernet
claim. Power/clock/shared ownership, quiescence/recovery and intentional final
kernel/provider integration remain next, followed by RC/windows/link/IRQ/DMA.
Accepted zsh/socket images/sources/root and Gate 4 hold are unchanged. No Pi,
serial/media/power/firmware/reboot/soak operation or current-OS observation.

# Actual kernel PHY-to-UBUS continuation — 2026-10-12

A distinct IOKit build now connects the real UBUS/AXI core to the same actual
reset44/RESCAL/SerDes sessions, Device mappings and single watchdog claim.
Four focused tests pass, including both AXI paths, all 502 modeled guard
failures, exhaustive phase permissions and real warning-free kernel compilation/
partial linkage with original Apple PCI code. All 732 input and 17 generated
hash entries revalidate (747 unique files). All **211 selected regressions
pass** in 76.392 seconds.
[Artifact and limits](GATE5-PCIE-UBUS-TRANSPORT.md).
Not installed, full-kernel linked, registered or Pi-executed; no power/clock/
shared-ownership/recovery admission or Ethernet claim. Next retained firmware
resources/raw-FDT/provider integration and unused-window/RC/windows/link wiring,
then actual config/BAR/IRQ/DMA/GEM. Accepted source/image/root bytes and Gate 4
hold are unchanged. No serial/media/power/firmware/reboot/soak action occurred;
no current OS/root observation is claimed. zsh/socket/SSH/userland stay in scope.

# Exact PCIe Device-handoff candidate — 2026-10-12

A separate declaration-only loader candidate now publishes only the three
rounded PCIe2/reset/RESCAL extents (five Device pages), while preserving every
existing memory-type record and the tested kernel/zsh/socket payload. Both the
original-object replay and patch-disabled rebuild reproduce the entire tested
boot binary exactly. Four focused tests pass, including actual Apple-tree
encoding and the kernel memory-map decoder, boundaries/overlap/capacity and
profile rejection. New call-path bound: 12,256 bytes, 4,128 bytes remaining;
no stack margin was relaxed. [Artifact/evidence](GATE5-PCIE-DEVICE-HANDOFF.md).
All **207 selected regressions pass** in 79.855 seconds; 190 candidate and 716
preceding PHY pins revalidate. Not installed or Pi-executed, and the PHY
transport is not registered/enabled.
Device typing does not prove power/clocks/exclusive ownership/recovery or admit
register access. Next close those conditions plus provider/FDT/constructor/
full-kernel integration, then actual UBUS/RC/windows/link/config/BAR/IRQ/DMA.
No serial/media/power/firmware/reboot/soak action; accepted images/sources and
Gate 4 remain unchanged. No new current-OS observation is claimed.

# Actual IOKit PCIe PHY transport — 2026-10-12

A distinct uninstalled kernel transport now maps the exact PCIe2/reset/RESCAL
resources, requires immutable Device classification for every rounded page,
and wires the real reset44 -> shared calibration -> SerDes/MDIO cores to
ordered volatile access and the genuine watchdog claim/check API. It pins
owner/provider/maps after any claim attempt, enforces phase-specific offsets,
and performs no cleanup MMIO/retry/power-off. Four focused tests pass, including
the actual C-core chain under all 206 modeled guard-failure positions; all
eight new units compile warning-free and partially link with the original PCI
family/PM owner. All **193 selected regressions pass** in 59.604 seconds.
[Evidence and limitations](GATE5-PCIE-PHY-TRANSPORT.md).
Not installed, full-kernel linked or Pi-executed; not a complete PCI bridge
owner or Ethernet. Current loader lacks these Device declarations, so the
transport intentionally rejects that handoff. Next close genuine power/clock/
shared lifecycle/recovery admission and opt-in handoff, then wire UBUS/RC/
windows/link and live config/BAR/IRQ/DMA ownership. Fresh SSH returned No route
to host: current OS/root remains unverified. No serial/media/power/firmware/
reboot/soak action; tested zsh/socket image and Gate 4 hold are unchanged.

# PCIe diagnostic watchdog ownership — 2026-10-12

A distinct opt-in pexpert build now supplies actual PM claim/check callbacks
and a shared nonblocking ownership gate. Ordinary timer/callout servicing
cannot keep feeding after the diagnostic claim. The lease writes WDOG once
for 15 seconds, admits access only before a 12-second counter deadline with
>2-second hardware margin, and cannot be renewed/cancelled/released. Real
kernel compilation/partial linkage and all **189 selected regressions pass**,
including atomic interleaving, all 12 callback failures and the finite check
budget. [Evidence and limits](GATE5-PCIE-WATCHDOG-OWNER.md).
This closes a software prerequisite, not physical reset timing/destination,
the concrete PCIe owner, final kernel link or Ethernet. Fresh SSH timed out;
current OS/root is unverified. No SD/serial/power/firmware/reboot/soak action
occurred; accepted images/sources and Gate 4 are unchanged. Next connect this
lease to the real Device/power/clock/shared-lifecycle PCIe owner, phase-specific
config policy, final registration and independently admitted physical trial.

# Apple PCI resource integration — 2026-10-12

The original-family abstract resource bridge now keeps allocator ranges in PCI
bus space and publishes CPU-translated, host-only/inhibited-cache descriptors
only after mandatory live-owner admission. A distinct BCM-only configurator
adaptation preserves allocated base-zero BARs and original Bar64 tags; pristine
and accepted sources/objects are unchanged. Real A76/XNU-header compilation,
family relocatable linkage, 16,384 native original-type translations and all
**161 selected regressions pass**. [Evidence and limitations](GATE5-APPLE-PCI-RESOURCES.md).
No concrete owner, final kernel link, MMIO/attachment, BAR hardware readback,
IRQ, DMA or Ethernet acceptance is claimed. No Pi/serial/SD/power/firmware/boot
change or soak occurred. Next implement genuine Device/power/clock/shared
lifecycle/recovery ownership and phase-specific config-write/resource policy,
then opt-in registration and admitted physical RP1 bring-up. The proven
zsh/socket image and Gate 4 hold remain unchanged.

# Socket runtime-identity continuation — 2026-10-12

**21:53 UTC physical trial passed and independently replayed.** Mounted-root
geometry, all 21 file hashes and devfs overlay match; original zsh smoke passes;
Unix sockets and IPv4 loopback UDP/TCP transfer/peer/half-close checks pass
(26/62 operations), followed by live recovery. One Linux software reboot, no
manual cold cycle or soak. Serial is released; last proven OS is XNU. Ethernet,
Wi-Fi, SSH and Gate 4 remain unproven. [Physical evidence](GATE6-SOCKET-IDENTITY.md#physical-result--2153-utc).

The distinct v2 package passes 35 local checks; all **157 selected regression
tests pass**. Protected installation verified 40 prior artifacts and retained
fresh snapshots/current image, with unchanged MBR/HFS and no shared frozen
installer-map edit. Next concrete PCIe/RP1 provider and original SSH dependency
work can continue without an immediate manual restart.

# Gate 4 durability held; independent Gates 5/6 active — 2026-10-12 UTC

PCI configuration continuation: serialized root/RP1 4-KiB config access and
an abstract subclass of ORIGINAL IOPCIBridge implement all six width-specific
methods. A76 strict compilation/family relocatable linkage pass; all 140
selected regressions pass, including 132 failure positions, W1C subwords,
real mutex concurrency and original-type address-helper execution. **No
concrete provider, MMIO/driver attachment, XNU BAR assignment, DMA or NIC claim.**
[Implementation, limits and next owner work](GATE5-APPLE-PCI-CONFIG.md).
Fresh SSH verifies SSD Linux boot `d5c3e702...`; allowlisted two-pass Linux RP1
reference and native resource reconciliation pass. Known SD identity/geometry
is present/unmounted, not fresh FAT/probe/preservation admission. No SD
mount/write, serial/power/firmware/reboot action or soak; socket package still
passes 34 checks. Prepare its protected installer/framing fix while Linux is up.

Apple PCI family integration: all eleven original kext source entries now
compile against actual Pi XNU headers using a separately copied BCM2712
adaptation (Apple-only DART calls excluded; two return-type corrections).
Real IIG generation and family relocatable linkage pass; 527 of 528 undefined
names exist in the accepted reference kernel, with `___dso_handle` still a
final-link/lifetime requirement. All 135 selected regressions pass. **Not a
final kernel link, driver attachment, RP1 enumeration, DMA or Ethernet.**
[Build evidence and next backend sequence](GATE5-APPLE-PCI-BUILD.md).
Pristine sources/accepted images remain unchanged. Fresh SSH timed out; no
serial/media/power/reboot/firmware action or extra soak occurred.

Apple PCI reuse continuation: unmodified `IOPCIRange.cpp` and its original
declarations now link freestanding for A76 with the RP1 BAR-candidate policy.
The original allocator passes 4,096 sanitized fragmentation cases; all 130
selected regressions pass. This is an unwired allocator subset, **not** actual
BAR assignment, complete IOPCIFamily integration, link/NIC or SSH acceptance.
[Evidence and next provider work](GATE5-APPLE-RANGES.md). SSH has No route to host;
the Pi's OS is unverified and no serial/media/power/firmware changes occurred.

Socket data-path continuation: a new local helper at
`/usr/local/libexec/xnu/socketprobe` implements Unix sockets and literal-loopback
UDP/TCP transfers, partial I/O and half-close checks. Native Darwin tests exercise
actual Mac data paths and 448 injected failure positions. All 127 selected
regressions pass; the separate A76 boot image passes 34 package checks.
Root has 32 nodes, preserving every recovery/zsh/Apple command byte and mode.
**Unstaged, not Pi-executed, not Ethernet/SSH acceptance.** Fresh SSH timed out;
serial/media/power and installed `b67b8013...` are untouched.
[Implementation, limits and next trial](GATE6-SOCKET-DIAGNOSTIC.md).

20:20 UTC: original Apple `/sbin/ifconfig -l` physically lists `lo0`, exit zero;
`/sbin/route -n` reaches usage after PF_ROUTE socket open, expected exit 64.
Original zsh smoke and live recovery pass. This is a separate same-boot
diagnosis: the strict fresh-mount trial timed out with zero TX due to SMP mount
log corruption and remains failed. No Ethernet packets, SSH, durability or
full gate exit is claimed. Image `b67b8013...` is installed; accepted image and
full backup chain preserved. Serial released; last proven state XNU recovery.
[Physical evidence and limits](GATE6-APPLE-NETWORK-PHYSICAL.md).

Darwin filesystem requirement: new Apple ifconfig/route packaging now uses
the upstream `/sbin` locations, in a distinct unstaged root (`0fdb9540...`).
The earlier `/bin` package and physically accepted Pi image are preserved.
[Filesystem contract](FILESYSTEM-CONVENTIONS.md) records remaining bootstrap
exceptions, `/private` aliases and writable-state migration requirements.
Directory layout is not APFS or macOS-service acceptance.

Apple-source reuse continuation: original source-built Apple `ifconfig` and
`route` are now in a distinct unstaged 27-node Pi RAM root, preserving every
accepted recovery/zsh/statprobe file and mode. Exact binary/build/source/archive
pins, pristine checkouts and nine original constructors verify; the existing
instruction auditor is reused. Not Pi-executed or network/ABI accepted.
[Apple tools and reuse-first policy](GATE6-APPLE-TOOLS.md).

RC integration continuation: the missing burst/class/endian/halfword power-
management setup now calls the real window programmer; link startup requires
the same completed RC owner. Sanitized tests compose actual RC/windows/UBUS/
link cores and inject all 146 RC/window callback failures. A76 combined linkage
has no undefined symbols. Not in boot builds or hardware-proven.
[RC checkpoint](GATE5-RC.md). Proven zsh remains unchanged and passes 37 checks;
read-only access candidate passes 15 checks without install admission. Fresh
SSH timed out; no serial/media/power/firmware/reboot/soak operation occurred.

Actual-access continuation: a distinct 53,376-byte A76 standalone image now
contains real ordered word/halfword register loads, a two-pass 15-register
allowlist, primary/FDT/PM admission, fatal vectors and one non-reloading
watchdog window. Candidate `pcie-access-vo0exx93` passes all 15 local checks;
all 92 selected regressions pass. **Not installed/Pi-executed or recovery-admitted.**
The next boot destination is not proven: recorded `0xf461` is SD-first, so a
watchdog reset is not SSD rollback. [Access implementation and admission boundary](GATE5-ACCESS.md).
Known-good zsh remains unchanged and passes all 37 checks. Fresh SSH returned
No route to host; no serial/media/power/firmware/reboot/soak operation occurred.

PCIe link continuation: the fixed Gen2/x4 one-shot link-start component is now
implemented, with true halfword link-control access, RC/profile prerequisites,
ordered PERST release, measured reset wait, bounded link polling, negotiated
speed/width and final-state checks. Sanitized models cover all 21 arrival paths
and 1,701 callback-failure positions; freestanding A76 checks and all 90 selected
regressions pass. This remains **unwired local work**, not a trained link/NIC.
Actual Device/power/clock/fault ownership, unused-window safety and RC setup are
the integration boundary. [Link checkpoint](GATE5-LINK.md). Known-good package
`35260343...` is unchanged and passes all 37 checks. Fresh SSH timed out; no
serial/media/power/firmware operation, reboot or soak occurred.

19:03 UTC: **physical corrective zsh trial passed and independently replayed**.
Verified SSD Linux allowed exact-card staging with all 32 historical NVMe backups,
fresh full snapshots and preserved old images. One armed software SD reboot
passed strict copy/mount admission, actual stat/lstat/fstat types/sizes/read/errno
checks, the original zsh script with exit zero, interactive zsh 5.9 builtins/
external exec and live recovery. Serial is released. Current image `35260343...`,
full FAT `18b6fdf8...`; protected MBR/HFS unchanged. [Physical evidence](GATE6-METADATA-PHYSICAL.md).
No cold cycle/soak, HFS mount, firmware edit, kernel/VM build or frozen-zsh change.
This resolves this script trial, not full Gate 6, Ethernet/SSH or Gate 4 durability.
Last proven OS is XNU recovery; do not assume SSD return or rerun old installers.
All 88 selected host regressions pass, including hash-pinned physical replay;
the 24 metadata-specific tests also pass independently.

PCIe2 inbound/outbound window encoding and one-shot programming are implemented,
with explicit four-byte decode-padding acknowledgement and an independent final
readback pass. Sanitized models cover all 112 callback-failure positions; actual
decoder composition and freestanding A76 checks pass. All 87 selected regressions
pass. This is unwired host work, not a trained link/NIC. Actual MMIO/fault,
power/clock/shared ownership and unused-window safety remain provider work.
[Window checkpoint](GATE5-WINDOWS.md). SSH timed out; no board/media operation.
The prepared metadata package is unchanged and still passes all 37 checks.

Metadata offline byte replay is implemented and mutation-tested, including
actual package/receipt rebinding. It does not trust recorder status alone or
promote synthetic tests into Pi acceptance. Networking also gains a one-shot
UBUS/AXI defaults core: normal and Reserved-0 fallback paths, ordered target
readbacks and quarantine, with all 43 callback-failure positions modeled and
freestanding Cortex-A76 compilation. No hardware integration/PCIe link/NIC is
claimed. [UBUS checkpoint](GATE5-UBUS.md),
[metadata checkpoint](GATE6-METADATA-CORRECTION.md). Fresh SSH timed out; no
serial, SD, power, firmware, kernel or VM operation was made. Prepared image
remains unchanged and passes all 37 checks; Gate 4 stays held independently.

The metadata correction now has a distinct baseline-aware installer and combined
raw-metadata/original-script/interactive-zsh recorder. The installer carries all
32 historical NVMe artifacts forward; the recorder rejects old/wrong/torn boots
before TX and actual metadata errors before zsh. Eleven additional local tests
cover preservation, receipt drift and failure/success sequencing. Independent
offline transcript audit remains next before physical acceptance. Fresh SSH
still times out; no staging, serial access, reboot or card/firmware change was
made. See [correction checkpoint](GATE6-METADATA-CORRECTION.md).

Corrective metadata package `bl33-probe-wdmzdtem` is now built and passes all
37 host preflight checks. It preserves the diagnostic RAM root and frozen zsh,
uses the existing kernel with the actual VFS getter wired, and binds the linked
SD-start opt-in rejection path with storage disabled. Seven new focused tests
pass. It is not installed/Pi-tested; the current image and physical script
failure remain unchanged. SSH timed out; no serial/media/power operation or
kernel/VM edit/build. [Correction checkpoint](GATE6-METADATA-CORRECTION.md).

18:02 UTC physical raw-file diagnosis completed after one software SD boot.
All 28 historical backups and fresh protection checks passed; working zsh and
earlier images are preserved. Strict root-marker trial timed out with **zero TX**
after a torn SMP mount line and remains failed. A separate same-boot read-only
diagnosis captured ENOTSUP from stat/lstat/fstat, untouched buffers, successful
plain/NOCTTY opens, descriptor duplication and exact shared-offset reads. Live
recovery returned; serial is released. Old linked kernel lacks the VFS statistics
getter; the preserved corrective kernel has it. Review/package it storage-off
before original script acceptance; no fix/full-gate claim yet. Current installed
image is `822e52de...`, full FAT `60b6ed08...`, SSD run
`/home/sandrzej/xnu-gate6-statprobe-gjy3szzg`.
[Evidence and next correction](GATE6-STAT-PHYSICAL.md). No shared kernel/VM edit or
build, extra cold restart, soak, HFS mount or firmware configuration write.

SerDes continuation: bounded port-0 MDIO and fixed 54-MHz BCM2712 setup are
implemented and host-tested together with prerequisite calibration/reset states.
All 27 focused tests pass, including every MDIO/SerDes callback failure on
the modeled paths. No hardware integration or trained link yet. The existing
stat-diagnostic package is unchanged, unstaged and still passes 29 checks;
its guard now explicitly excludes the hardware-writing components. No Pi,
serial, media, kernel build or VM operation. [SerDes details](GATE5-SERDES.md).

Gate 5 continuation: shared RESCAL initial calibration now has an implemented
one-shot core, sanitized host tests for every failure on all bounded poll paths,
and a freestanding Cortex-A76 compile. It is not wired to hardware. Actual
shared power/clock/Device-access ownership and SerDes/link bring-up remain next;
no trained link or Ethernet claim. See [bridge lifecycle](GATE5-BRIDGE-LIFECYCLE.md).
Fresh SSH retries timed out, including after the existing watchdog interval.
The OS is unverified; serial/media/power and the installed zsh image are untouched.

File-ABI continuation: separate raw stat/lstat/fstat/open/F_DUPFD diagnostic,
immutable recovery/zsh-root extension and distinct boot package are prepared.
Twenty-nine package checks pass; seven focused tests cover host fault models,
actual static linkage, preservation and rejected pins. No Pi execution/staging,
script fix, networking or durability claim is added. Fresh SSH timed out;
serial/media/power remain untouched. See [diagnostic checkpoint](GATE6-STAT-DIAGNOSTIC.md).
Installed image remains the physically tested zsh package `bl33-probe-_qoqmu9u`.

16:40 UTC: **interactive zsh 5.9 physically executed on the Pi**. It computed
version and array/arithmetic output, executed external `/bin/echo` with a fresh
nonce, returned zsh prompts and exited to a live recovery shell. The original
script-file trial failed and is preserved; the interactive subset does not
waive that failure or complete Gate 6. Same-boot diagnosis confirms the file
exists/is readable but zsh's regular-file test is false; raw stat/open/F_DUPFD
diagnosis is next, not an assumed cause or fabricated metadata workaround.
[Full evidence and current recovery baseline](GATE6-PHYSICAL-ZSH.md).
All recorder handles finished/released serial. One software SD boot, no manual
cycle or soak; full backups/protected MBR/HFS/firmware remain preserved. No
kernel or VM source/capsule change. All 42 selected focused host regressions pass.
Ethernet and Gate 4 durability remain incomplete, independently of this result.

15:39 UTC: networking continues independently of the blocked write-durability
goal. Implemented/tested the one-shot reset-44 helper and documented the
[bridge lifecycle](GATE5-BRIDGE-LIFECYCLE.md); no hardware caller/reset yet.
Also inventoried the pinned zsh's 69 traps/143,591 instruction words and prepared
an unstaged 24-node Pi RAM root preserving the original init/recovery shell and
all utilities. [Gate 6 details](GATE6-USERLAND.md) retain ISA/ABI/runtime limits.
All 73 selected host tests pass (4.913 seconds). No board, serial, media, reboot,
kernel or VM operation occurred. Neither Ethernet nor Pi zsh execution is
claimed. Current hardware is not re-observed; the 15:05 result below is the
last physical acceptance, not a guarantee of the Pi's current OS/state.

15:05 UTC: **physical Gate 5 full-FDT declaration boot passed**. New package
`bl33-probe-28ubwa1k` embeds the unchanged proven shell kernel and RAM root,
with the topology hook enabled and every storage trial disabled. Image SHA256
`038c2b9bd0b55fa35496632fad7a96e8ffff1f2a7b64006e5709757bd895b895`.
The exact SSD/card/full-MBR/FAT/HFS baseline and all 20 historical NVMe backups
verified before staging; complete fresh partition backups and W3 rollback image
were preserved on SSD, W3 also on SD. Protected MBR/HFS/boot files verified after.
No HFS mount/write, firmware edit or EEPROM edit. Installer evidence is
`pcie-topology-installed-20261012`; SSD run `xnu-gate5-topology-z4ll1si5`.

The Mac RX-only recorder was armed at 15:02:11 UTC before the guarded software
reboot at 15:02:18 UTC. Firmware selected SD and entry `0x9000000`; the loader
decoded the full firmware FDT and logged the expected bridge/MIP/GEM/windows,
then `PASS PCIE_MMIO=0 CONFIG_ACCESS=0 DMA=0 NIC_READY=0`. It subsequently
transferred to XNU, mounted the 19-node RAM root and reached repeated shell
readiness plus prompt. No panic, second boot or storage startup is present.
Capture finished at 15:03:41 UTC, 32866 bytes, zero TX; raw SHA256
`74453addcae85eded5b397d3a8dd737d923c615055b3ae48441f2beae8133a07`.
Offline audit: `mac-pcie-topology-trial-20261012/validation.json`, SHA256
`7be8fe76ccdf43e72ee9f76ba764905da2fc4fb21f5bb8e00ae3e6b8b72df00e`.
This proves runtime declarations and shell readiness, not new shell-command,
PCIe bring-up, IRQ/DMA, Ethernet or durability acceptance. Recorder is finished
and serial is released; Pi is in XNU with its existing one-hour watchdog, not
Linux SSH. No further restart/soak is requested. Next is bridge accessibility,
clock/reset/mapping lifecycle closure, then the separate config observer.
Gate 4 is unchanged. VM files/shared kernel/zsh capsule were not edited or built.
All 46 focused topology/capture/staging/install/profile/PCIe/GEM/package checks
pass (4.145 seconds); this host regression result is separate from the physical
boot acceptance above. `git diff --check` also passes.

14:35 UTC Gate 5 progressed beyond the earlier observer/preflight checkpoint.
One actual, read-only Linux capture now contains the decoder's 12-node parent/
reset/interrupt/PHY topology dependency subset, bound to the exact SSD Linux
root and stable boot `36ac234c-2a31-4b30-bb5d-de87fa5bd8e2`. The sanitized native
C decoder accepted it; the resource planner independently agreed with Linux's
BAR1 bus base zero, 4-MiB size and CPU base `0x1f00000000`, deriving GEM at
`0x1f00100000`. Evidence: `rp1-topology-live-20261012`; result SHA256
`9669fdf6ae12c595a2a272a3f9c5830ad722c52f0c92b94e18f8a4ddf59f6be3`.
This is Linux topology/resource evidence, not standalone XNU PCIe access.

The loader now has a separate default-off `--gate5-pcie-topology` integration.
It logs FDT declarations only, after the large runtime framing call returns;
it never calls the MMIO observer and rejects all storage-trial combinations.
A fresh host-only BL33 build `bl33-probe-fqg0m3ec` passed, with unchanged hashes
of all 374 Pi source files around the build and a 10,000-byte conservative
C-frame bound in the 16-KiB early stack. Raw SHA256
`05d74ef66481a2faab89b80d616bfd0568d15f1c5d500fa73d85b61a7a429e10`.
No kernel is embedded, placement is unverified, and it is not staged/booted or
approved for installation. The next hardware trial requires a distinct,
recovery-backed package; no manual restart is requested at this checkpoint.
Gate 4 admission/durability remains held and unchanged. VM networking files and
frozen zsh capsule were not edited; no kernel build, SD/serial access, network
change or reboot occurred. See [Gate 5 details](GATE5-NETWORK.md).
All 28 focused capture/topology/build-profile/PCIe/GEM checks pass. Linked ELF
inspection confirms the topology logger/decoder are present, the MMIO observer
is absent, and no undefined symbols remain. This is host link evidence only.

13:40 UTC the user requested continued networking and other gates. The hold is
narrow: cache support is advertised but disabled/absent state cannot be proven;
actual write/persistence acceptance remains incomplete. No prior shell or RO
storage result is revoked, and no gate exit requirement is waived.

Implemented `loader/rpi5/pcie_observe.{h,c}` and its callback/fault model. It
checks root-complex/link state, selects only RP1's config header, compares two
passes of stable fields, and reports the BAR's PCI bus base without inventing
assignment or size. It is host-only for now: no boot/kernel caller or actual
MMIO. All 10 focused PCIe FDT/planner/observer/GEM DMA tests pass, including
ASan/UBSan models and freestanding A76 checks. This does not establish Ethernet,
interrupt delivery, DMA coherency or wire traffic.

Implemented `check_zsh_ramroot.py`; 17 focused RAM-root/static-executable/preflight
tests pass. The exact preserved VM capsule passes the new checker: 1,163,264-byte
`RPI5RFS1`, 18 nodes, pinned static arm64 `/bin/zsh` matches the capsule executable.
Report: `build/rpi5/zsh-ramroot-preflight-20261012.json`. This is format compatibility,
not a new VM run, source-license audit or Pi zsh execution. [Gate 6 worklist](GATE6-USERLAND.md)
retains the remaining startup/ABI/ISA/console and board-trial checks.

Fresh SSH confirmed hostname `kamidana`, exact `/dev/nvme0n1p2` ext4 UUID and
unchanged boot `36ac234c-2a31-4b30-bb5d-de87fa5bd8e2`; neither SD partition is
mounted. No SD/media write, mount, serial access, network change or reboot was
performed. The following entries are historical checkpoints, not live handles.

13:18 UTC independent protocol check: official SD6 section 4.17 and
PERFORMANCE_ENHANCE table define SD Status bit 330 as cache-support indication.
Reading existing Linux sysfs SSR (no new card command) produced 64 bytes,
SHA256 `428a89044a9dd1126cd15f64fcbca7a9690c33643df8f10f375c9fe818f8b6c6`;
byte 22 is `fc`, so cache support bit 330 is **1**, not 0. This rules out an
absent-cache shortcut from that independent field; it does not reveal enabled
state under XNU. Preserve `sd-extension-linux-control-20261012/sd-status-operator-note.json`.
The card reports January 2022; the reviewed Raspberry Pi Linux Samsung cache
quirk applies to 2023 cards and cannot justify a bypass here. No shared kernel
change/build, new ioctl, SD write, mount, reset, serial input or reboot.
The next practical hardware option is inspecting another disposable SD card;
its identity/capabilities must be captured before any preparation, and all
original write/persistence/protection requirements still apply. The current
card stays preserved/unmounted in SSD Linux; ask once about spare availability.

13:12 UTC physical Linux control completed; supersedes the pending/live-handle
statements below. The existing waiter **23351** exited ready at 13:08:02 UTC:
fresh SSH independently confirmed exact SSD root and new boot
`36ac234c-2a31-4b30-bb5d-de87fa5bd8e2`, exact CID/CSD/SCR and both SD partitions
unmounted. No manual restart. RX-only handle **14191** was deliberately stopped
with SIGINT only afterward (PID 49836); original raw/state and an operator note
are preserved. Its `failed`/null-error report is the recorder's KeyboardInterrupt
behavior, not a demonstrated hardware failure. It captured 94181 bytes, zero TX;
raw SHA256 `cc05eda193df4b40602e3cad4902934581101677c4b8811b79e48012dbcf14cf`.
Neither old handle is live now.

`sd-extension-linux-control-plan-20261012` passed local validation, then the
distinct `sd-extension-linux-control-20261012` executed once and exited 0.
Result SHA256 `15f963e70a6b29085e6c88a59345c09d4a8e727d7a5ca02763ac7cc63974debe`;
plan SHA256 `b88bb6aefd5ae6e6b53b4dd7e8a99b9fd07bdf2f6bade042e421f14ad78243f7`.
One userspace CMD48 read returned R1 `0x900` and exactly the same 512 zero bytes
as W3 (SHA256 `076a27c79e5ace2a3d47f9dd2e83e4ff6ea8872b3c2218f66c92b89b55f36560`),
replacing the `0xa5` sentinel. All 20 NVMe backups and complete MBR/FAT/HFS bytes
were verified before and after; no SD write, mount, reset or reboot occurred.
This makes an XNU-only transport explanation less likely, not impossible;
it still does not establish absent/disabled cache or authorize a write batch.

Existing Linux metadata reports kernel `6.18.34+rpt-rpi-2712`, card `GD2S5`,
`ext_perf=00`, `ext_power=00`; boot logs show SDR104/ADMA. These are observations
of Linux state, not XNU cache admission. Primary Raspberry Pi Linux 6.18 branch
source permits a zero extension count to skip feature parsing, explaining why
zero feature metadata is not independent absence proof. No second CMD48 read
was issued. Next: independent protocol/card evidence to resolve the malformed
zero General Information response; do not rerun W3, weaken decoding or repeat
completed shell/RO tests. Gate 4's actual admitted write/persistence chain remains
incomplete. The Pi is left in SSD Linux with the SD unmounted and probe released.

12:26 UTC offline continuation: W3 is still running; existing RX/SSD handles
**14191 / 23351** were freshly polled live. Fresh SSH timed out, consistent with
serial XNU output but not independently diagnostic. No SD access, serial input,
manual restart, new trial or soak. Wait for the existing automatic SSD return.

`capture_sd_extension_reference.py` now supplies the complete guarded controller
for the prepared Linux control. It pins actual W3 plan/result/state/raw hashes,
requires a fresh exact SSD/new-boot readiness report, verifies all 20 preserved
NVMe records and full MBR/FAT/HFS bytes before/after the single fixed CMD48 read,
binds unchanged source/evidence and preserves unknown outcomes without retry.
The complete HFS hash must match the original clean fixture before the ioctl;
Linux data never changes XNU cache admission. Default is local-plan-only.
The actual W3 pins/raw payload and 20 local-image/backup records were revalidated;
12 focused controller/ioctl tests pass, including fixed remote sequencing,
wrong/stale/same-boot rejection, full protected-byte checks, source drift and
timeout/no-retry behavior. The actual waiting Linux report was rejected before
output/network/device access (`sd-extension-waiting-guard-MUST-NOT-EXIST-*`
does not exist). No physical Linux CMD48 control result exists yet.
Only Pi tooling/docs changed; no shared kernel files/build snapshot or excluded
experiment folders were touched. Next finite action/commands are in
[the Linux control sequence](GATE4-WRITE-TRIAL.md#linux-control-after-w3--completed-comparison).

12:13 UTC W3 trial outcome: **failed, zero TX/batch/HFS mount**, at 12:07:00 UTC.
The actual new trace is intact:
`CACHE_PROBE_FAIL STAGE=7 RC=-5 SPEC=6 FUNCTION=0 ADDRESS=0x0 SCR=0205848700000000 BYTES=512`.
Stage 7 is General Information decoding, after completed ACMD51/CMD48 and their
CMD13 status checks. All 32 ordered intact hex rows reconstruct exactly 512
zero bytes (SHA256 `076a27c79e5ace2a3d47f9dd2e83e4ff6ea8872b3c2218f66c92b89b55f36560`).
SCR is valid SD6; the all-zero extension header is not accepted as absent cache.
This narrows the fault but does not distinguish card behavior from XNU transport.

Preserve `mac-hfs-cache-diagnostic-trial-20261012/{state.json,serial.bin}` and
its operator note. State SHA256 is
`09e287eed22d657f4ea0822070bcef6c05ae19b2bb8037b8631120722638ccb1`;
35538-byte raw SHA256
`7588028a78b77b05209484c44f05e2febfcaab6d97a42f039e4d5e36ca638453`.
Do not rerun W3 or send serial input to it. New RX-only handle **14191**
(`mac-hfs-cache-diagnostic-to-linux-20261012`) and exact SSD-root waiter **23351**
(`wait-nvme-after-hfs-cache-diagnostic-20261012`) are freshly polled live.
Observe its existing one-hour watchdog fallback, approximately 13:07 UTC;
verify actual new boot/root before any SD access. No manual restart/new soak.

The actual SCR/zero-buffer case is now reproduced by the sanitized C model,
which verifies unchanged cache output, invalidated card and six original
commands rather than inventing an absent-cache result. The fixed Linux control
core `sd_extension_reference_core.py` is prepared/tested but **not executed**.
It opens only the exact whole SD descriptor read-only, checks block capacity,
issues one userspace CMD48/FNO0/page0/offset0/LEN511 read ioctl and preserves
complete bytes/R1. Exact new-SSD/card/unmounted identity must be checked before
and after. It never toggles/flushes cache, retries, writes, mounts or reboots;
Linux's internal transport commands and cache state are not XNU admission proof.
The six focused C/control tests pass. Next: verified SSD return, fresh complete
clean HFS reference/protection checks, then one Linux control read to distinguish
card-level zero response from XNU behavior. No speculative parser relaxation.

12:06 UTC resumed hardware checkpoint: prior wait/capture handles 58883/78529
are gone; their preserved reports show SSD return at 06:49:42 UTC and normal
RX completion at 06:54:09 UTC, respectively, with zero TX. Do not reuse them.
Fresh SSH again verified exact SSD root, hostname/card/unmounted SD and boot
`8aeee895-7393-4bb8-bc00-a0ff23a54c8f`; fresh readiness report is
`wait-nvme-before-hfs-cache-diagnostic-20261012/state.json`. Two complete clean
HFS reads in `hfs-linux-reference-xk6euh6j/reference.json` still hash to the
original fixture. All 29 actual W3 package checks were rerun and matched.

W3 is now installed using `hfs-cache-diagnostic-installed-20261012` and fresh
outer/current bundles without rewriting any older artifacts. NVMe run is
`/home/sandrzej/xnu-gate4-hfs-write-9hn29muu`; W2 is preserved as
`hfs-write-cache-probe-failed.bin` and SD
`probe.hfs-write-cache-probe-failed-20261012.bin`, with W1/RO/full backups retained.
Complete MBR/HFS remained unchanged; new installed full FAT baseline is
`4876d430491b7999d36f7fbf94843c90f43dc24d0792d9fcdaafbb2cfbf49c68`.
Actual installation plan/result SHA256:
`f26e245b905aa5b70cd330eed61a477b9cf97ca0d353072d8c67ead52798bb51` /
`a87c38afb168c0470c99c1d4995088b22bd59fe0862c19d1e05d9142e7cd95ba`.
Recorder handle **77623** was confirmed armed before the one software SD reboot
request at 12:06:03 UTC. The distinct write loader/hash progress is captured;
cache admission and the trial outcome remain pending. No manual power cycle,
new soak or durability claim. Preserve `reboot-request.json` and original raw.

06:15 UTC guard review: the cache-successor installer now independently rehashes
the original W2 serial file again after all other plan validation, rejecting a
change after its first pinned failure check. The new race regression plus
recorder/capture checks pass (37 tests). An actual local-only CLI attempt using
the real W3 preflight but the expired W2 Linux reference was rejected with
`Linux physical reference is stale; recapture before arming`, before output,
network or SD access. The deliberately stale bundles are labeled `stale-*` and
must never be used for installation; the `MUST-NOT-EXIST` output does not exist.
The next hardware step still requires the pending new exact SSD boot and new
complete clean HFS reference. W3 remains unstaged; no hardware/input change.

06:10 UTC offline progress: successor W3's fresh build `run-xce7gcel` exited 0
with unchanged source; kernel `fresh-5lhxkium/.../kernel.development.bcm2712`
SHA256 is `c1884450d6b775a6c38cc033bf894fd07d539d0a772c2d6650a54e0ac84e8c16`.
Distinct package `bl33-probe-ra00dsr1/probe.bin` SHA256 is
`79d5b90aa9821c639e6f9476bd3c7dfd2727d26c4c551b8072dd06570ded0ec3`;
all 29 actual linked/source checks pass, preflight SHA256
`824f534b23f08d5fe18f4685959f831f98551dad8f20ad8cf409280cfba25896`.
This adds diagnostics only, not a demonstrated decoder fix. W3 is **not staged**.
`stage_hfs_cache_diagnostic.py` pins W2's original zero-TX failure/installation,
requires new SSD Linux and fresh clean HFS evidence, preserves W2 under distinct
fixed filenames and rechecks W1/RO/all full snapshots. Its recorder and future
persistence capture use the complete successor chain, including 20 NVMe backup
records. New focused model/native regular-file guards cover changed history,
admission/input/mount contamination, same-boot/reused images, missing linked
diagnostics, evidence drift, fixed publication and retained backup generations.
The actual W2 raw/state independently passed the new historical failure check.
The final focused run passed 124 tests in 3.638 seconds; the actual 29-check W3
inspection was rerun afterward and exactly matched its preserved preflight.
Existing handles **78529 / 58883** remain live, freshly polled; captured watchdog
progress reached `RELOADS=216`. No new SD operation, serial input or reboot.

06:00 UTC checkpoint supersedes the older unstaged/live-handle statements below.
W2 was installed from verified SSD Linux boot
`920d20af-a50c-46c1-baa6-fda846f07820`, preserving W1 and all older images/full
backups. Installation evidence is `hfs-write-diagnostic-installed-20261012`;
the complete new installed FAT baseline is
`f9e89a9531b749c949c22cf3c57948735322dd05cf9df45e64f76cd461325dc8`.
The armed recorder observed the actual diagnostic image boot and failed closed
at 05:48:36 UTC: `CACHE_PROBE RC=-5 CMD=13 STATUS=0x1 CACHE=0 SPEC=0`.
`-5` means unsupported protocol/decoding, not a proven CMD13 transport failure;
CMD13 follows each read, and the cache/spec fields remain untouched on failure.
There was zero serial TX, no batch and no HFS mount. Preserve
`mac-hfs-write-diagnostic-trial-20261012` (including its operator note): state
SHA256 `8dc8c2e4e122c314999f488200da0946ab419abd7141bbc238b97afb661c9c6d`;
33150-byte raw SHA256
`f7decb76a3a6b654b6e27cfc2908766504b6b1606459a9a9de39399c155c778d`.

Existing RX-only handle **78529** and SSD-root SSH waiter **58883** were freshly
polled live. They observe W2's existing automatic fallback, expected near
06:49 UTC subject to actual new-boot/root verification. Old handles 28350/51018
are terminal; the original W1 RX was deliberately stopped only after verified
SSD return and complete clean HFS reference `hfs-linux-reference-je5hflxu`.
No manual restart, extra soak or SD/serial input is needed while W2 runs.

Offline successor code now has separate diagnostic-only stage/full-read-buffer
storage, never used by admission. It preserves atomic cache output and the
same bounded command path. Host models compare all 512 PEF alignments and
transport faults with/without tracing, including MMIO counts/command arguments;
decoder failures retain only completed buffers. Provider log formatting is
tested separately using explicit transport doubles. This code is not yet built
or staged and is not a parser fix or a hardware cache observation. The official
SDA archive is browser-visible but its download requires legal agreement;
no agreement was accepted. Gate 4 still requires actual admitted writes and the
complete independent reboot/fsck/RO-remount/persistence/protection chain.

05:35 UTC checkpoint: the original RX-only/SSD waiter handles **28350 / 51018**
remain live, freshly polled; actual XNU watchdog kicks reached `RELOADS=624`.
No new SD access, serial input, reboot, physical action or soak. Continue using
those same handles until actual SSD root/new boot is verified (ETA ~05:42 UTC).

The final `check_hfs_persistence.py` now binds the actual admitted one-batch
transcript to its new-Linux-boot capture and subsequent Mac no-repair fsck/RO
full-ten-file audit. It rechecks all 15 command logs/flags/attachment snapshots,
complete protected bytes, source/hash bindings and chronology, and hashes all
evidence before/after validation. The capturer rejects trial/raw drift during
validation. All 36 focused persistence tests pass. The actual synthetic Mac
smoke logs were independently revalidated, remaining explicitly not durability;
combining them with the actual failed W1 is rejected before output/external
access. No physical persistence acceptance report exists. W2 remains unstaged.
See [final chain check](GATE4-WRITE-TRIAL.md#final-evidence-chain-check).

05:25 UTC offline-progress checkpoint: both existing RX-only/SSH wait handles
**28350 / 51018** are still live, freshly polled; XNU serial watchdog kicks
continue through `RELOADS=516`. No additional serial input, SD operation,
reboot or physical action was requested. The same automatic SSD return remains
expected around 05:42 UTC, subject to actual new boot/root verification.

Independent post-batch tools now exist: `hfs_write_acceptance.py` re-parses
the complete one-batch raw serial proof; `capture_hfs_persistence.py` and its
fixed read-only core require the actual passed write, intervening new exact
SSD Linux boot, full protected MBR/FAT equality, all NVMe backup hashes and
three stable complete HFS reads with fsynced/readback-verified NVMe/local copy.
`audit_hfs_persistence_image.py` performs no-repair fsck and independently
read-only remount of only that local regular image, full two-pass checks of
all ten files, exact attachment ownership/detach and unchanged image/source
hashes. These tools do not stage, repair, reboot or claim durability on their
own. The actual failed W1 is rejected locally before any external access.
The new 27-test host group passes; the focused storage/provider/installer run
also passed 123 tests. Native Mac synthetic HFS smoke
`hfs-persistence-audit-smoke-xp2vaz9x` passed fsck/remount/full-file/detach/image
checks; audit result SHA256
`626fe06d143c22c1a454864bee53654e479f80c266a2eeb7fee388f42953f8b1`.
This synthetic image is not a Pi-written partition or durability evidence.
All 29 actual W2 package checks still exactly match the saved preflight;
W2 remains unstaged/unbooted. See [write/persistence sequence](GATE4-WRITE-TRIAL.md).
Actual admitted writes and the full physical persistence exit remain unproven.

05:00 UTC current checkpoint: the first write trial ended **failed/zero input**
at 04:50:15 UTC. It captured the distinct write loader, intact HFS registration
and 258 repeated shell-readiness prefixes, but **no write-admission prefix**.
The bounded recorder therefore sent zero bytes, ran no batch and mounted no
HFS filesystem. This does not identify the failing startup stage or independently
count SD wire writes. Preserve `mac-hfs-write-trial-20261012/{state.json,serial.bin}`:
state SHA256 `151c45f7f699e5ff131ee5dab8cf2727a30287495ed08ac31d7a7b9ef3d96dda`;
41332-byte raw SHA256
`7439b383feaa7c0869daaf1abac99d8e2266ece80fce161f3fe83f238e7fb4bb`.
An explicit operator note and independent pinned raw/state validation remain.
Do not restart that trial, reinterpret it as a pass or send shell input to it.

The Pi remains on the installed `dd8eecb8...` XNU image. A separate receive-only
capture `mac-hfs-write-no-admission-to-linux-20261012` (live handle **28350**)
and exact-root SSH waiter `wait-nvme-after-hfs-write-no-admission-20261012`
(live handle **51018**) observe the existing one-hour watchdog fallback. Both
handles were freshly polled live at 05:00 UTC. This is not another stability
run/soak and no physical action has been requested. Expect SSD return around
05:42 UTC from the captured watchdog start, but verify actual new boot/root.
Only then stop/preserve RX, recapture both complete HFS reads and proceed.

The write provider now has first-failed-stage startup diagnostics, without
changing admission/cache/range rules or adding card commands. Its actual
`initialize()` control flow is exercised with explicit transport doubles for
handoff, identification, allocation, cache observation/refusal, each header
read and identity/geometry authorization failures, plus successful model
admission. These are not hardware initializer or cache proof.
Fresh build `run-ifzych4q` exited 0 with unchanged source; linked kernel
`fresh-gfkbx6c6/.../kernel.development.bcm2712` has SHA256
`89ac846de1a7560b87ab883962af5334827b4fe765d90126ccc825c6af8e9862`.
Separate package `bl33-probe-p8k9tahf/probe.bin` has SHA256
`65347b15c3852991556b6f324ff7b9fc77ccb00552fc2b17431d46b0946e70ed`
and all 29 actual package checks pass. Its preflight SHA256 is
`784e5e98be6cdbfbd66a216f18bf04c8313383ae1b0bcfd2f433c64f8e21f5ff`;
build-manifest SHA256
`41061f178997df5439aa5565899cec71e39ac6ef9c61d33b0e4863bd62e6d603`.
Actual linked bytes contain each new diagnostic marker. This image is **not
staged or booted**; it is prepared for diagnosis, not a demonstrated fix.

The first diagnostic build attempt stopped before compilation on an unrelated
directory symlink. `source_entry_digest()` now hashes the Git-selected link's
target text instead of trying to open its directory; no path exclusions were
added and strict before/after source equality remains mandatory. Retargeted,
dangling and directory links plus changed regular bytes are tested. The full
successor installer/recorder/source-guard/initializer focused run passed
95 tests (1.403 s), separate from the earlier native storage/HFS run.
The distinct diagnostic installer preserves the failed write image under new
fixed names, verifies the full prior installed FAT baseline, retains all RO
and older backups, and requires fresh exact SSD/card/HFS evidence plus the
new actual package screen. It has not executed or generated a fresh device
plan yet. See [write-trial recovery](GATE4-WRITE-TRIAL.md) for the next sequence.
Gate 4 remains incomplete: actual admitted writes, successful batch/unmount,
intervening reboot/fsck/read-only remount/full-file persistence and protected
boot-media proof are still required. Do not repeat the passed RO cycles/soak.

04:40 UTC write installation/trial checkpoint: the distinct guarded installer
executed successfully from exact SSD Linux boot
`54b2ad20-73c0-4dc2-a6b7-c96506b04a0a`. The disposable SD now contains
`bl33-probe-ybis0sa6/probe.bin` (`dd8eecb8...` below). The physically passed RO
image is preserved as `probe.hfs-read-passed-20261012.bin` on SD and
`hfs-read-passed.bin` in NVMe run `/home/sandrzej/xnu-gate4-hfs-write-qvwac13_`.
That run also contains fsynced/readback-verified full 512-byte MBR, 512-MiB FAT
and 128-MiB HFS backups. MBR and HFS hashes remained unchanged. The complete
post-install FAT baseline is
`012f02a8f4759038a93f92551e98d5705fdba84166cd4a6b4206044bce9e0f77`.
Evidence: `build/rpi5/hfs-write-installed-20261012/{plan,result}.json`, with
SHA256 `d02f05628fb93717bb4391fa2cb9974b3701dfbde008cdfd31763e71191f23b6`
and `f32cdc1db19f0703bc6fdc5dc1819da62516158927c6fa4b421f2c18c7c18ba0`.
The new installer/recorder/backup guards and existing installer/file regressions
passed 71 focused host tests (0.205 s); a separate native storage/HFS regression
passed 41 tests (4.898 s). These are not physical write or full-suite results.

The exclusive `mac-hfs-write-trial-20261012` recorder is armed (handle 11863)
before the one-shot software SD reboot requested at 04:40:50 UTC. Firmware and
the distinct write-loader marker are captured; no write acceptance is claimed.
The recorder requires intact fresh loader, exact extent/nonzero epoch/cache-off
admission, HFS registration and subsequent shell readiness before any TX.
It then runs only one five-file batch, full serial byte hashes and non-forced
unmount. IOKit HFS/storage readiness can arrive in either order; both are needed.
Failure never sends cleanup/retry. Success remains explicitly not durability:
intervening reboot, independent fsck/read-only remount/full-file readback and
unchanged protected boot media are still required. No manual reboot/soak asked.

04:17 UTC build checkpoint: the final distinct write kernel/package now passes
the strict source-stability guard and all **29 actual package checks**.
Fresh build `run-93r3j3i2/manifest.json` exited 0 with unchanged source; kernel
`fresh-gaz84zwu/.../kernel.development.bcm2712` has SHA256
`a8e48db21e7c3d931fed4800de9ad67def3d7a7bbac01e8433a506314c3981ea`.
Package `bl33-probe-ybis0sa6/probe.bin` has SHA256
`dd8eecb8f6fd989d8d29ce8c5b2837a3c6c49dd67a62bb0b40bec67f90397506`.
Its `write-preflight.json` SHA256 is
`ba75506dd525aed6be80fa4e639a2302f52d50de9ec2e9c3d500035e1addb263`.
Actual linked configuration contains only the write adapter, both HFS services
and their all-of encoding dependency; linked mockfs statistics wiring and the
embedded write utilities pass. The earlier rejected builds remain rejected.
Existing loader/read-only package regressions separately passed 15 tests
(0.302 s); this is not a full-suite or hardware-write result. No new image has
been installed, booted or given serial input. Linux and the passed RO SD image
remain the current hardware state. Next: implement/test the distinct guarded
write installer and marker-guarded batch recorder before staging, then prove
real reboot/fsck/remount/full-file persistence. Gate 4 remains active.

04:12 UTC checkpoint: automatic SSD Linux return was verified with new boot ID
`54b2ad20-73c0-4dc2-a6b7-c96506b04a0a` and the exact `/dev/nvme0n1p2` root UUID.
Both SD partitions are unmounted. Two complete fresh HFS partition reads still
match the original clean 128-MiB fixture, SHA256
`168c89cb97645ba07b353b3584087e5770d9c2793c6e86b7a8bc3471cbb477e1`.
Evidence: `hfs-linux-reference-r8fozzfh/reference.json`, captured 04:12:23 UTC,
SHA256 `304fe2eb022ef1594006c3b825197635e5cbeb442c0def5e4712322654519f1e`.
The existing SSH waiter completed ready, and the exclusive RX recorder was
deliberately stopped (exit 130, zero TX); original state/raw bytes and an
explicit `operator-stop.json` remain. Capture: 36419 bytes, SHA256
`7a95985775c4897de788bae298d4ec4d9bd9c4ac97ae9e8eaf3ae0d0cc16bfca`.
No manual power action, new soak, SD write or new XNU trial was performed.
The full original FAT backup and preserved shell, SD-read and failed-HFS
recovery image hashes were freshly rechecked on NVMe and match their records.

Offline write preparation now includes actual CMD2/CMD9 CID/CSD capture,
read-only SCR/extension-register cache observation, the distinct single-worker
`BCM2712SDWriteStorage`, serialized sync with cache-off admission, and opt-in
`hfsrw`/`hfswrite` userland/loader profiles. A combined 56-test focused run
passed (19.094 s), including actual-source worker failure/cancellation models,
cache register models, native ABI/static archive builds and profile guards.
The separate userland is `hfs-write-userland-v1-20261012`; the passed RO image
and all existing baseline packages remain untouched.

Full write kernels link successfully, but concurrent changes in the unrelated
Darwin-container experiment made the whole-worktree source-stability guards
reject the first three completed builds (`run-p7awm7r9`, `run-evyjrmc2`,
`run-2x8fo5p_`). One intervening attempt failed before compilation while that
experiment temporarily exposed a nested repository directory. None was staged.
The distinct write-package screen actually rejected `bl33-probe-wym312s8`
on source stability, while its other 28 checks passed. Keep this rejected
preflight as evidence; do not override or reinterpret it as a pass.
Next: a fresh source-stable write build/package, guarded installer and serial
batch, then independent reboot/fsck/remount/full-file readback. Gate 4 is not
complete; physical write/cache acceptance and durability remain unproven.

Current physical checkpoint, 03:12:40 UTC: the corrected read-only HFS trial
**passed on the Pi** in one fresh boot. Both complete mount/read/exec/unmount
cycles passed: ten full-file serial reconstructions (five files twice,
134590 bytes), matching the fixture SHA256 values; both recovery scripts and
HFS-resident binaries executed; missing-file recovery and non-forced unmounts
succeeded; final shell nonce returned. An independent raw-capture recheck
reconstructed every file again and verified mount/status/unmount ordering.

Evidence: `build/rpi5/mac-hfs-stats-corrected-trial-20261012/state.json`
(SHA256 `d3e54daa6223a663010f71f9d9ff33b164347a2c08e73acdfc6771d5d026cd21`)
and its 460386-byte `serial.bin`
(SHA256 `9c276399b75fa03d4d3058cd3dada12e73ff82787ee264ff215929e41f4aa315`).
The installed/passed package is `bl33-probe-a5wng87t/probe.bin`, SHA256
`9defaf57a932aca9dfca06ad928eca4fe3e9bbd07fb5c7562b1b80c4df28222a`.
No data-write commands or DMA were enabled. This is repeatability within one
boot, not two cold boots, write durability or full Gate 4 exit.

The Pi was left at the live XNU RAM-root shell with HFS unmounted. A new
receive-only fallback capture (`mac-hfs-passed-to-linux-20261012`, handle 80689)
and separate exact-root SSH waiter (`wait-nvme-after-hfs-pass-20261012`, handle
67840) are live observations for the existing automatic SSD return, not a soak.
No user power cycle is needed. Next: finish the separately gated write-provider,
cache/synchronization and writable-HFS utility integration, preserve this passed
image, then batch writes in a distinct image and independently verify persistence
after reboot/remount/fsck. Gate 4 remains active/incomplete.

03:22 UTC offline follow-on: the separate `hfsrw` utility is now implemented
and passes seven sanitized syscall-model/native Darwin ABI tests. It permits
only the fixed disposable partition/mountpoint, checks writable geometry and
actual mount identity, and requires non-forced unmount/root restoration. Failed
sync/unmount produces no success marker. Its explicit compile-time gate is off
and it is absent from current dispatcher/build/image; every future marker says
`DURABILITY_VERIFIED=0`. No Pi command, SD write or mounted filesystem was used
by these tests. Real writable-provider/cache-sync integration remains next.
The combined focused HFS utility regression passed 20 tests (6.287 s); this
is separate from the earlier 185-test run, not a new full-suite claim. Passed
HFS, shell and Gate 3 package hashes were reverified unchanged. Independent
raw rechecking also verified both script/binary nonces and both removed-mount
responses, not just their command echoes or the saved trial status.

Earlier installation checkpoint, 03:10 UTC: automatic SSD Linux return was verified
on the exact NVMe root with new boot ID
`eab1bae1-ee62-4ee7-a437-17e39fc11bcc`. The exact-root waiter completed ready.
Two complete HFS reads in `hfs-linux-reference-fdlatk62/reference.json` match
the original fixture, captured 03:06:48 UTC. The exclusive receive-only fallback
recorder was deliberately stopped after Linux verification (zero TX, 36886
bytes, SHA256 `12d4a24126cc4c8483ded156451bbfd5a56edbcae3d5e2fbd65dcad2d4c55bd8`);
its original state/capture and explicit `operator-stop.json` are preserved.

All 29 corrective package checks were freshly rerun and matched the saved
preflight exactly. `hfs-stats-correction-installed-20261012/result.json` now
confirms **actual successful installation** of `9defaf57...`, preserving the
failed `38c4f0e...` image as `probe.hfs-statfs-failed-20261012.bin` and in NVMe
run `/home/sandrzej/xnu-gate4-hfs-stats-qq37ry97/hfs-statfs-failed.bin`.
Complete HFS bytes and protected boot files remain unchanged; FAT is unmounted.
No partition/config/firmware change or installer reboot occurred.

The fresh `mac-hfs-stats-corrected-trial-20261012` recorder was armed before
the 03:10 UTC one-shot SD reboot. The remote script rechecked the exact same
Linux root/boot ID, received successful mailbox acknowledgement, synced and
requested reboot once. SSH closure afterward is expected, not a failed/retried
staging operation. At this checkpoint fresh loader bytes were being captured;
the trial subsequently completed successfully as recorded above.
Writes/DMA remain disabled, and Gate 4 stays active/incomplete.

Earlier build checkpoint, 02:40 UTC: the corrected kernel and separate HFS package
have built successfully. Build `run-obi6gw3d` records fresh outputs and unchanged
source during compilation. Kernel SHA256 is
`674e6a763a01a7e4becf0399d03641aa4e43ec1c1d995d67623546b9d64f5aad`;
package `bl33-probe-a5wng87t/probe.bin` SHA256 is
`9defaf57a932aca9dfca06ad928eca4fe3e9bbd07fb5c7562b1b80c4df28222a`.
All 29 package checks pass in `hfs-stats-preflight.json`, including the actual
mockfs VFS getter slot (offset 40) pointing to the corrective handler. The
actual failed kernel is rejected by that additional screen. This remains host
linked-byte proof, not successful physical statfs/HFS dispatch.

The distinct `stage_hfs_stats_correction.py` installer now binds the original
fixture/boot installation, complete prior physical captures, exact pre-mount
failure, new linked getter and a fresh full Linux reference. It preserves the
failed image under `probe.hfs-statfs-failed-20261012.bin` on SD and
`hfs-statfs-failed.bin` in a fresh NVMe run, retaining all earlier backups. Its
host tests cover fixed distinct filenames, partial/symlink rejection, exact
failure/prefix binding, shared remote workflow ordering and unknown outcomes.
An offline historical-reference replay accepts the real evidence chain; the
same current-time invocation correctly rejects the stale Linux reference.
At that earlier checkpoint the corrected image had not been staged or booted.
The expanded focused
regression passed all 177 tests before the subsequent write-path preparation.

03:01 UTC preparation checkpoint: all **185 focused tests** now pass in one
run (32.104 s). The actual IOMemoryDescriptor bridge, bounded fixed-file write
exercise and read-only persistence-vector verifier are implemented separately.
The bridge compiles against real pinned Apple headers, and the isolated write
foundations partial-link with no unresolved SD dependencies. None is linked
into the current provider/kernel/package; no SD write or durability is claimed.
The batch deliberately emits `DURABILITY_VERIFIED=0`. Actual cache-state/sync,
the writable-provider worker integration, a separately gated writable mount
utility and physical reboot/remount/fsck/readback remain required. See
[write-path evidence and limitations](GATE4-WRITE-POLICY.md). The corrected
HFS read-only image and both preserved local baselines were rehashed unchanged.

SSH still timed out at 02:28 UTC; the exclusive receive-only recorder and
SSH-only root waiter were polled live, and serial watchdog output continued
through 02:37 UTC. Keep the existing automatic fallback; no manual restart is
required. Next: verify a new SSD Linux boot ID, recapture the complete HFS
reference, execute the distinct correction installer, release the RX recorder,
arm a fresh guarded HFS trial, then request one software SD reboot. No new soak.

Earlier 02:19 checkpoint: the first physical HFS trial stopped **before
mounting**. The exact HFS read-only image booted, HFS registered and the real
BSD `/dev/disk0s2` partition appeared. `hfsro mount` returned `statfs64: errno 45`
while inspecting the covered RAM root. `mockfs_vfsops` has no `.vfs_getattr`;
`statfs64 -> vfs_update_vfsstat -> VFS_GETATTR` therefore returns ENOTSUP. No HFS
mount, file read, executable load or XNU data write is accepted by this trial.
The archive-only mockfs statistics fix now passes focused native tests; the
expanded host regression passed **167 tests** before the subsequent build.
See [the failure and correction](GATE4-MOCKFS-STATFS.md).

SSD Linux returned automatically at 02:00:38, root/boot ID verified. A fresh
one-partition capture `sd-linux-reference-ii63u6la` matched the original eight
sector hashes and complete identity. The guarded fixture stager then actually
created the disposable 128-MiB HFS partition, after full FAT/MBR backups on NVMe
and two full data readbacks. Evidence: `hfs-stage-executed-20261012`; backup
directory `/home/sandrzej/xnu-gate4-hfs-stage-ivwj0uyh`. The independent full
Linux reference is `hfs-linux-reference-lzloo4fh`. `hfs-boot-installed-20261012`
preserved the passed SD image and installed `38c4f0e1...` without changing HFS,
configuration or protected boot files. Its backup directory is
`/home/sandrzej/xnu-gate4-hfs-boot-m9rz7hn4`. The one-shot SD reboot followed
the armed recorder at about 02:04:36; SSH closure was expected, not a retry.

The initial `mac-hfs-read-trial-20261012` was deliberately interrupted with
zero transmitted bytes because concurrent CPU startup logs tore the encoder
banner. Its bytes remain unchanged. The revised guard requires the actual
linked all-of encoding dependency plus the intact HFS REGISTERED marker, not
reconstruction of torn text. A tightly bound recent zero-TX continuation
requires fresh repeated shell readiness and nonce before commands. Evidence:
`mac-hfs-read-continuation-20261012`, explicitly two capture segments with an
unobserved closed-port gap and no observed intact encoder banner. It failed
on the real pre-mount statfs error, not on the startup banner.

The Pi remains in that read-only XNU image. Existing automatic fallback is
expected around 03:05 UTC, not another soak. Receive-only capture
`mac-hfs-statfs-to-linux-20261012` and SSH-only exact-root waiter
`wait-nvme-after-hfs-statfs-20261012` were freshly polled live. No manual action
is required. **Do not rerun the initial fixture/boot stagers**: the card now has
two partitions and its current image is HFS, not the old SD-only image. A
corrective installer must preserve these actual prior backups and failed
capture, require a new read-only package and fresh full Linux HFS readbacks.
Writes and DMA remain disabled; Gate 4 is active/incomplete.

Earlier checkpoints follow (historical state, not instructions to repeat).

Physical XNU SD reads passed at 2026-10-12 01:04:33 UTC. All eight selected
sectors were read twice through `/dev/rdisk0`; all sixteen complete byte/hash
records match independent Linux reads. Bounds rejection and the live shell
also passed. DMA and writes remain disabled. This is not full Gate 4 exit:
repeated HFS mount/read/exec and separate write durability are still required.

The user-confirmed U-to-UART link first passed a fresh Linux marker. Exact
card/reference/image/backups and all 22 package checks passed before the armed
recorder and 00:59:12 UTC one-shot SD reboot. XNU handoff returned RC=0 STAGE=7
and published the exact 250347520-sector read-only disk. The original recorder
hit a host chunk-boundary bug after three completed reads, not a device error.
Its raw capture remains unchanged. The fixed runner continued only the thirteen
remaining reads in the same running shell, after a fresh nonce. The successful
run preserves the entire earlier capture byte-for-byte and explicitly records
two capture segments and an unobserved closed-port gap; it is not a continuous
capture or repeated-boot qualification. All 155 focused Gate 4 host tests pass.

Successful evidence: `mac-sd-read-link-restored-continuation-20261012/state.json`
and `serial.bin`; original failed recorder: `mac-sd-read-link-restored-20261012`;
Linux baseline: `sd-linux-reference-99_23_zu/reference.json`.
The HFS stager accepts this independently reconstructed SD evidence and has
generated only `hfs-stage-plan-after-sd-pass-20261012/plan.json` locally.
No HFS partition or boot-image rewrite occurred. The SD trial released serial;
the receive-only fallback capture below now owns it. The Pi was last observed
at the live XNU shell. HFS staging requires fresh SSD Linux
and exact card verification, not another soak or repeated shell milestone.

The separate HFS package freshly passes all 28 checks. While waiting for the
existing one-hour watchdog fallback, a receive-only recorder is live in
`mac-sd-to-linux-fallback-20261012`; readable watchdog reloads through 204 were
observed. This is an observation wait, not new qualification/soak evidence.
The new `stage_hfs_boot.py`/`probe_install_core.py` installer and twelve focused
host tests are prepared; neither it nor the fixture stager has executed on the
Pi. See [the HFS execution sequence](GATE4-HFS-EXECUTION.md) for exact inputs,
backup/publication guards and the arm-before-reboot ordering.

An offline [write admission policy](GATE4-WRITE-POLICY.md) now passes two
additional sanitized/native/freestanding tests. It rejects writes outside the
disposable HFS span, wrong card/layout/header observations and stale epochs,
and permanently quarantines an ambiguous-I/O instance. It has no transport
commands and is not linked into either current read-only image. HFS hardware
acceptance remains the next step; writes and durability remain unproven.

Offline update, 2026-10-12 01:42 UTC: the separate single-sector PIO write
engine now passes sanitized register fault models and freestanding Cortex-A76
compilation. The expanded focused regression passes **159 tests**, including
the two quiet-SSH-wait identity tests. The new engine/admission modules are not
listed in either kernel/provider build; neither current image was rebuilt or
installed. This is not physical write acceptance. The existing receive-only
capture and exact-root SSH waiter remain live; XNU watchdog reloads through
480 were observed and Linux has not yet answered. The original one-hour
watchdog deadline is around 02:00 UTC; verify actual SSD Linux before staging,
do not infer readiness from that estimate or start another soak.

Offline update, 2026-10-12 01:52 UTC: `rpi5_sd_transfer.{h,c}` now models
prepare/complete pairing, a complete owned write snapshot before transport,
per-sector admission/cancellation, partial failures and write quarantine on
read transport errors. It is not a real IOMemoryDescriptor adapter and remains
unlinked. All **161** expanded focused host tests pass on the current source;
actual HFS mounting and writes are still unproven. Both prior image hashes are
unchanged. The receive-only capture and exact-root SSH waiter were freshly
polled live, with watchdog reloads through 624 and no Linux response yet.

Earlier diagnostic checkpoint, 2026-10-12: SSH is back in verified NVMe Linux at
`sandrzej@192.168.4.23`, root UUID `04570742-280b-43cb-9564-73d454243b1c`.
The card identity/eight sector hashes match the original reference, the SD
still contains the exact `82fcac33...` candidate, and both proven-shell backups
retain `bf01b0ee...`. FAT was inspected read-only and unmounted, not rewritten.
The restarted empty recorder was deliberately stopped after Linux was verified
to diagnose the serial link, not because its observation window expired.
Linux's physical debug-UART TX counter increases for explicit test markers,
but the Mac receives zero bytes, including after reopening and explicit DTR
assertion/rearming. DTR was already set. No agent reboot was requested.
This narrows the current observation failure beyond XNU; cable/connector/probe
state needs inspection before another boot trial. Ports are released and the
Pi is left in Linux. Evidence: `linux-uart-diag-20261012/observations.json`.

The SD protocol parser accepts only known complete line endings and rejects
embedded carriage-return repair/interleaving inside frames. Torn unrelated SMP
startup chatter outside frames is preserved, not repaired into evidence. HFS staging independently
reconstructs and verifies all sixteen ordered sector records from the raw SD
capture; a rehashed readiness-only capture cannot authorize staging.
The focused Gate 4 regression passes **155 tests**. This is host evidence,
not actual SD reads, HFS mounting or durability.

Earlier checkpoints follow.

The guarded future HFS fixture stager is implemented but has not been executed.
Eighteen focused host fault tests pass; the expanded focused regression passes
130 tests. It preserves/readback-verifies the full
FAT boot partition and publishes the new MBR entry only after two complete HFS
data readbacks. Physical SD-read success remains a prerequisite, not bypassed.
SSD/NVMe Linux returned at 23:49:42 UTC and exact root/card identity was verified.
The corrected SD-only image `bl33-probe-unsh3788` passes 22 fresh checks and was
staged with both working-shell backups preserved. Independent before/after
captures match identity and all eight sector hashes. The guarded recorder was
armed before the one-shot SD software reboot at 23:51:19 UTC; its outcome is
inconclusive. It exited at 2026-10-12 00:00:43 UTC after a boot-marker timeout:
zero received bytes, zero transmitted bytes and no reads. The port was released.
This does not prove that XNU booted or that the corrected SD driver failed.
The latest SSH check reports no route to host. The UART-lead check and a
physical restart were requested, but neither has been confirmed; no automatic
recorder retry, card change or further restart was performed after timeout.
No HFS partition, mount or durable write is claimed.

At the earlier restarted-recorder checkpoint, the user confirmed another restart
and reported an SD-card boot. The guarded recorder was armed at
`build/rpi5/mac-sd-read-powerbit-restart-20261012/`; it had received zero bytes
and transmitted nothing. USB serial enumeration was present, but SSH still
timed out. The report was not an observed XNU startup or SD-read result.
The later Linux/diagnostic outcome is recorded above.

Separate offline Ethernet ownership groundwork now passes two focused tests
(sanitized native fault models and a dependency-free Cortex-A76 compile).
It is not wired into the kernel or hardware; see [GEM DMA boundary](GATE5-GEM-DMA.md).

The repeatable serial-shell milestone below remains achieved. Gate 4 targets
real SD storage, pinned IOStorageFamily and HFS+, then separately verified
write durability. The serialized, read-only `BCM2712SDStorage` adapter now
builds and links against the real kernel/storage interfaces. All 61 integration
units compile; the fresh kernel has no unresolved symbols. The physical trial
reached the SD adapter's start path; media/partition/BSD publication is not yet
runtime-proven.

The first physical trial reached XNU, then panicked in IOCatalogue because
unquoted partition-content strings containing underscores violate the actual
OSUnserialize lexer. It sent **zero serial bytes**, performed no SD driver
reads, and automatically fell back to verified NVMe Linux. The fix now passes
a host syntax test using XNU's unchanged grammar/lexer, and preflight resolves
the actual linked kernel configuration pointer/string. It rejects that failed
kernel and passes the corrected one. A separate model assumption about CQHCI
version was corrected to the captured BCM2712 value `0x510` before retrying.

The corrected read-only package boots XNU and reaches the RAM shell. Its SD
adapter fails closed with readback error `RC=-4 STAGE=2` (clock stopped, before
card initialization); no physical card read is demonstrated. The recorder sent
zero bytes and exited. Working-shell backups on both SD and NVMe retain the
exact proven hash. No partition/firmware changes or manual power cycles were
needed. The subsequent register-diagnostic candidate passed 22 preflight
checks and was staged/software-booted after Linux returned and exact root,
card, backup and before/after sector checks passed. It identified the first
mismatch: `BANK=0 REG=0x28 MASK=0xff00 WANT=0 GOT=0xe00`. The bus-power-enable
bit cleared; voltage-selection bits remained. The recorder failed closed,
sent zero bytes and released the serial port. The guard is now corrected in
source to clear/check only the actual power-enable bit while preserving the
voltage selection; external GPIO power-off/timing/readback checks remain.
Native retained-voltage and stuck-power fault models pass. The fresh corrected
kernel builds/links with source unchanged during the build:
`build/rpi5-xcode27/run-orwggdmn/manifest.json`, kernel SHA256
`8055890c1fb379cb618b0dfddf046edc686e86525eb3fa93b4847405d58159ce`.
The next SD-only package `build/rpi5/bl33-probe-unsh3788/` passes all 22
preflight checks, probe SHA256
`82fcac33c8cc25e79aad1d8af1c0759d165b72ca8bc7fc63e82d9bc1780519dd`.
At that build checkpoint it was not staged or booted. The later staged trial
at 23:51 UTC is recorded above; actual boot/read validation remains unconfirmed.
Focused regression checks now total 71 tests; the SD diagnostic still passes 22
preflight checks. Neither is physical storage acceptance.
While SSH remained unavailable, HFS and encoding-service matching were added
offline with explicit converter-ready ordering, one-time initialization,
zones prepared before VFS registration and permanent built-in lifetime.
Both require a separate `bcm2712_hfs=1` boot argument; no automatic mount or
write is introduced. A separate fresh kernel links successfully with these
changes: `build/rpi5-xcode27/run-0ix3pyum/manifest.json` (source unchanged,
exit 0), kernel SHA256
`5dfe83c8a69349224c2362ec883664eae7a9aed887c4b09f131528d22f329e57`.
Its actual linked configuration parses and both service classes are present,
with no unresolved symbols. It is now packaged separately with the read-only
HFS mount utility at `build/rpi5/bl33-probe-ckh5_4dt/`, probe SHA256
`c320892dfbec6b40f0a907710851f2a9619a28785a90ce6cabb92c14db5ec209`;
all 28 host identity checks pass. It is **not staged or booted**. No HFS data
partition has been created. The original SD-only diagnostic remains the next
physical trial and the proven shell image retains its exact hash. The expanded
host regression now passes 89 tests, including fixture-header/device guards.
A clean 128-MiB standalone HFS+ data fixture is prepared locally at
`build/rpi5/hfs-read-fixture-h9wpku5p/`. Native Mac fsck (no repairs) and
read-only mounted hashes of five files pass; both virtual attachments are
detached and the image hash is unchanged. Raw image SHA256:
`168c89cb97645ba07b353b3584087e5770d9c2793c6e86b7a8bc3471cbb477e1`.
This is independent Mac fixture evidence, not Pi mount/read acceptance.
The Pi remains unreachable by SSH in the latest check; its SD, serial port
and power were not touched. No HFS data partition has been created on the SD.
See [Gate 4 current evidence and next work](GATE4-STORAGE.md) for provenance,
configuration adaptations, package identity and remaining hardware checks.
Actual SD reads, HFS mounts and durable writes remain unproven.

Read-only HFS verification tooling now includes bounded complete-file serial
hex parsing and a separate two-partition Linux reference capture. Larger dumps
explicitly opt into a 256-KiB capture limit; existing shell/SD trials retain
their 64-KiB default. Exact nonce frames, byte counts and full SHA256 checks
reject truncated/interleaved/corrupt responses. The actual compiled hexdump
utility is checked against that parser on the host, including the cross-page
fixture. The Linux tool requires the original card identity, unchanged FAT
partition, exact future 128-MiB HFS partition and verified NVMe root. It opens
only that unmounted partition read-only and requires two complete image hashes
to match the Mac fixture. Local fixture headers/hash were reverified; no
physical two-partition reference has been captured. These are verification
components, not Pi acceptance. The separate HFS recorder is now implemented
and host-tested: it requires prior physical SD-read success, a fresh bound
Linux partition reference, distinct HFS package and fresh service/SD/shell
markers before any serial input. It batches two mount/read/unmount cycles,
ten complete file hashes, script loading and execution from HFS in one boot.
It is not armed; no successful SD read or two-partition reference exists.
Expanded host regression: 112 tests pass. The later SD diagnostic trial above
is the only new physical boot; no HFS test partition or mount was attempted.
The same corrected kernel is separately packaged for HFS at
`build/rpi5/bl33-probe-qxmk1ban/`, probe SHA256
`38c4f0e1bf927f4960a85493429a24be1119b9c00e94b29e2a2974b0e3c8d832`;
all 28 preflight checks pass. It remains unstaged/unbooted and must not replace
the isolated SD-only trial. The serial parser now handles the observed Pi
userspace CR-CR-LF line endings without accepting embedded/torn carriage returns.

# Pi 5 port status — serial-shell result 2026-10-11

The actual bounded static shell/init/utility payload **passed all twelve
checks on the physical Pi** at 19:39:40 UTC on 2026-10-11; see
[shell trial](SHELL-TRIAL.md). SSH returned, NVMe Linux and the exact SD were
verified, working-image backups were preserved, and the shell was staged and
software-booted once. External commands, quotes, pipelines, scripts, cwd,
exit status and error recovery work. Evidence:
`build/rpi5/mac-shell-trial-20261011/{serial.bin,state.json}`, raw serial SHA
`f01903ca37c5e31fc14883a739f42d8ba9c0488d0a12be83f58929393d9a78fc`.
Fourteen focused host tests and fourteen package checks also pass; those
are separate from the hardware result. The first true power-off/on cold start
also passed all twelve checks at 20:00:21 UTC, with firmware reporting
`power-on-reset 1`. Evidence: `build/rpi5/mac-shell-cold1-20261011/`, serial
SHA `c60c8cf768b68802b1d1db87a760f886434426d1426d1ac92ff2c2f6c1027e93`.
The final cold start also passed all twelve checks at 20:15:24 UTC, again
with `power-on-reset 1` and a fresh complete boot capture. Evidence:
`build/rpi5/mac-shell-cold2-20261011/`, serial SHA
`698fbaf107b2b403051a25a70324fe9547b8a56d6f6eb0d804da2a4ec4cbf468`.
The repeatable cold-boot serial-shell milestone is achieved. Both recorders
have exited, the serial port is free, and the Pi is left at the usable shell.
No further restart or soak is required. The root is read-only, networking/SSH
are absent, and the development watchdog service window remains one hour.
This does not pass formal Gate 3 or complete the broader Darwin port roadmap.

The existing DEVELOPMENT kernel boots on the physical 8-GB Pi 5 with four
cores online and a static RAM-backed PID 1. The latest guarded hardware run
passed eleven polling-console checks, including command recovery and an echo
180 seconds after initial acceptance. Evidence:
`build/rpi5/mac-terminal-v231-longwait-20261011/{state.json,serial.bin}`;
serial SHA-256 `f83420c5aa17df11770b814e7062fa90c305c5a7b9941f251a799dd44cdcfc74`.
This proves a four-command interpreter, not a general BSD shell, UART RX IRQs,
an entire one-hour run, or formal Gate 3 qualification. No QEMU result is used
as evidence for this physical-board milestone.

The userspace `fork`/`execve`/`wait4` and copy-on-write trial now **passes on
the physical Pi**. The corrected image was staged and software-rebooted once
at 17:41:38 UTC. Its generic keyboard-start log was torn by concurrent UART
writes, so the first recorder sent zero bytes. Explicit same-boot recovery
verified that recent capture's hash, device, single loader and repeated process
readiness, then required two fresh process-specific readiness/prompt pairs.
No reboot or kernel rebuild was needed for this host-side recovery.

At 17:44:00 UTC, child PID 2 had forked, exec'd with the expected arguments
and zero-filled BSS, exited normally with status 42, and been reaped by PID 1.
The parent's COW cookie was intact and `status` recovered the PID 1 prompt.
All six focused hardware checks passed with 15 transmitted bytes. Evidence:
`build/rpi5/mac-process-literals-resume-20261011/{state.json,serial.bin}`;
serial SHA-256 `56ba2971c946c933bdb30a7d868bced5ac091f121c37fab84204cbb34eba806d`.
The complete boot capture is `build/rpi5/mac-process-literals-20261011/serial.bin`,
SHA-256 `7c71de7977085c3fa3f535a2319d589f318dd8b1e98f67fb2bcd3fb7b789b4cd`;
its firmware log explicitly identifies SD boot. The capture is split across
two recorder sessions on the same boot, not a cold-boot repeatability test.

The bounded read-only multi-file RAM root also **passed on the physical Pi**
at 18:20 UTC. One SD software boot mounted ten nodes; same-boot recovery from
a torn startup result and a truncated long echo produced all seven checks,
including cross-page/EOF/read-only/directory IO and exec from a separate file.
Successful serial SHA-256:
`32c97a8998fc175ade4953ee561fd0e1cb24b60c831e9f4516cbc526f7aebe75`.
See [RAM-root trial and evidence](RAMROOT-TRIAL.md). Next dependency: the
actual static shell/utility payload. General shell and repeatable cold boot
remain unproven. Long automated input should be paced, not burst-written.
The Pi is left running the successful RAM-root XNU image; no serial
recorder remains active. Before another staging operation, verify fresh
NVMe Linux state rather than assuming SSH is available.

### Process-trial implementation and earlier attempts

The trial reused the exact working kernel and polling input. SSH was restored
and NVMe Linux plus the exact XNU_PROBE SD identity were verified. Working
polling and Gate 3 images were preserved before staging the process payload.
One controlled SD boot reached XNU userspace, but SMP UART writes garbled the
one-time process readiness marker. The receiver correctly transmitted zero
bytes; fork/exec/wait **remain untested**, not failed or passed. Raw capture:
`build/rpi5/mac-process-trial-20261011/serial.bin`, SHA-256
`ca94e6a08332d08eaaeb93092a40244f64493e65c18b82717b83ee5685a72658`.

A revised process-only payload repeated readiness until the first input.
Its one physical boot proved that handshake, but `process` returned
`Unknown command` before fork. Linked-binary inspection identified a concrete
cstring defect: unterminated newline constants were combined with the process
command, making its symbol point to leading newline bytes. Raw capture:
`build/rpi5/mac-process-handshake-20261011/serial.bin`, SHA-256
`3c84babbe5c54c557ec310cd2e743e16a7f16ec1c9b4e46fc9545ebaddf00591`.

Both newline literals are now terminated. The builder and preflight verify
bytes addressed by linked command/argument symbols; substring presence alone
missed this failure. Seven focused tests pass; the verifier rejects the actual
faulty package and passes all 14 checks on the corrected package. One payload
and loader build produced `build/rpi5/bl33-probe-w7agabax/probe.bin`, SHA-256
`043eeb43dc55aeb520be7cd5c4541ad39b222b120a6ddf166f809ea834a20341`.
The corrected image subsequently passed the physical trial above. Exact
staging, commands and provenance:
`build/rpi5/shell-process-literals-20261011/README.md`. Seven focused host
protocol checks passed after adding same-boot recovery; these are not CPU
emulation. No new kernel build, full suite, unchanged-image rerun, or soak
was performed. See also
[the audit and process trial history](PROCESS-TRIAL.md).

Kernel provenance: existing Xcode 27 exploratory build
`build/rpi5-xcode27/run-glrazu5x/manifest.json`; kernel SHA-256
`a0c1a934b795c9f7e1f1c4e4c888d31327069023e1c74024b76fe4717bbbc741`.
Base commit is `ac9718fb1af618d5ce8678d0dc6e8a58f252216f` with substantial
uncommitted port work. A bare checkout of that commit is **not** this port;
preserve manifests, source hashes and the dirty checkout. No new commit or
full kernel rebuild was made for the userspace-only trial.

## Superseded summary — 2026-09-25

The following records the situation at that date, not the current port state.

Gate 2 implementation has started: the loader emits Pi root identity and CPU
device types, and a Pi-only IOKit platform expert is in source. Host tooling
tests pass 185/185. The Pi mockfs path now uses ordinary RAM-device paging,
with widened range/EOF arithmetic. These sources have isolated object compiles,
but the platform expert has not been linked into a kernel or tested on hardware
because the current Xcode 27.0 installation does not match the preserved 26.6
prepared SDK. See
[Gate 2 audit](GATE2-AUDIT.md).

Actual XNU executes on the 8-GB Pi 5 through memory/allocator initialization
and into IOKit initialization. This is an experimental kernel boot, not a usable
Darwin system. The reproducible kernel with the Pi-only FP/SIMD synchronization
fix was physically booted on 2026-09-25, reaching crypto/PRNG registration and
the known missing `device-tree` platform-driver panic. All four standalone
EL1/virtual timer IRQ probes passed; the watchdog returned to Linux on NVMe.
The Gate 1 host suite passed 180/180 tests at sign-off. Gate 0 and Gate 1 are
signed off for this exact DEVELOPMENT image and recorded board, with
artifact-specific limits in
[the completion audit](GATE1-AUDIT.md).
The proven build manifests and lock use Xcode 26.6 (`17F113`) and macOS SDK
26.5. The currently installed Xcode.app is 27.0/SDK 27.0, so a new canonical
build currently fails `doctor` until the pinned toolchain is restored or a new
one is deliberately qualified.

The loader supplies checked boot data and fresh firmware-derived seed material,
and standalone CPU/timer/interrupt probes pass on all four CPUs. Experimental
boots automatically recover to the preserved NVMe Linux installation. XNU's
own interrupt-controller integration, storage and PID 1 are not yet delivered.

## Historical checkpoints

The entries below retain their original observations and limitations; their
"no XNU execution" statements are superseded by the current summary and audit.

Actual entry ABI checkpoint: the host comparison now verifies __start against
the Mach-O entry and decodes its direct B target to the named start_first_cpu
symbol. The built kernel passes (0xfffffe00074c8488 -> 0xfffffe00074ca05c),
alongside existing native validation and host-buffer materialization. New tests
cover signed branch offsets, wrong targets/opcodes, missing symbols and truncated
instruction backing; all 96 tests pass. This validates the trampoline contract,
not kernel startup execution. Runtime handoff/entropy/ownership and board evidence
remain outstanding.

Terminal transfer prerequisite: added a stackless, nonreturning EL1 entry routine
with local state/address checks, terminal vectors, timer/private-register cleanup
and instruction/TLB synchronization before branching with boot_args PA in x0.
It is linked but deliberately uncalled: see TRANSFER-CONTRACT.md for complete
caller obligations, including cache-disabled writes and inherited clean memory.
Probe build bl33-probe-ngd15tx8 succeeds; emitted assembly was inspected and all
95 host tests pass, including a structural instruction-order test. No system
instruction was executed on the Pi and no XNU transfer or gate pass is claimed.

Firmware initrd range validation: before reserving a supplied initrd, runtime
planning now checks advertised RAM coverage and disjointness from ATF, probe
code/data/stacks and runtime FDT. Conflicts stop allocation planning; no initrd
contents are read. Added range fixtures for probe/FDT overlap and RAM overrun.
All 94 host tests pass; probe build bl33-probe-sx01fdea succeeds. This remains
diagnostic planning, not a completed ownership map or hardware-verified handoff.

Firmware live-input checkpoint: bounded native parsing now recognizes the chosen
Linux initrd address pair and diagnostic reservation planning preserves a present
range in fixed exclusions, without reading it or claiming it is Darwin userspace.
Malformed/partial pairs and full reservation tables stop planning. New sanitizer
fixtures cover widths, duplicates, bounds and atomic output; all 94 tests pass.
Probe build bl33-probe-c4p4rpl5 succeeds. Pinned TF-A source review confirms its
mailboxes are already covered by the ATF exclusion; complete firmware ownership
and runtime handoff remain unfinished. No hardware evidence was obtained.

Firmware exclusion integration: runtime reservation planning now adds the pinned
ATF [0, 0x80000) range as a fixed reservation, not a loader-owned live buffer.
It therefore stays outside both unallocated and reservation-free views. A full
fixed table stops planning without dropping any FDT reservation. Tests cover
separate live probe/FDT buffers and overlapping fixed firmware reservations;
all 93 tests pass. Probe build bl33-probe-jb8aj7b0 succeeds. This does not close
the complete firmware ownership inventory or supply actual board evidence.

Reservation/handoff integration prerequisite: the native reservation resolver
now distinguishes unallocated RAM from reservation-free RAM retaining live
buffers. Both exclude fixed and proposed dynamic reservations; only the former
is suitable for candidate writes. Sanitizer tests verify the distinction and
atomic failure. All 93 tests pass and probe build bl33-probe-wwyphr3y succeeds.
The new view is not consumed by runtime handoff: complete firmware exclusions,
ownership, tree/entropy and board evidence remain required. See
RESERVATION-POLICY.md for the current ATF live-versus-fixed limitation.

Entry-instruction boundary check: native and host Mach-O validators now require
all four entry instruction bytes to be file-backed and executable. The native
sanitizer fixture accepts the last complete instruction and rejects each one-,
two- and three-byte tail without publishing output. All 93 host tests pass;
the actual kernel still passes container/native validation and host-buffer copy.
Updated GATE1-READINESS.md to distinguish runtime validators already wired in
from materialization/handoff helpers still unwired. No board evidence added.

Embedded relocation-validation checkpoint: runtime payload inventory now checks
local relocation records with build-sized, bounded scratch inside the probe BSS
and reports the count before NOT_LOADED. Fresh embedded build
bl33-probe-f3kl6jnq reserves 1,048,576 scratch bytes; ordinary build
bl33-probe-fy1uazfa reserves 8 bytes. Both produced audited ELF/raw images and
manifests; all 93 host tests pass. These are host builds at an example load
address, not approved firmware placement or board execution. Gate 1 still needs
runtime handoff integration, qualified fresh entropy and actual Pi serial evidence.

Embedded payload integration: build_probe.py now optionally embeds a host-audited
kernel in the checked container, records its input audit and raw-image physical
range, and includes the entire payload in the probe linker extent. Runtime
inventory verifies hashes plus kernel segments/symbols and explicitly stops
short of loading (relocation validation added in the checkpoint above). Both embedded and ordinary builds
succeed; all 93 host tests pass. The larger image still needs actual firmware
placement review, and no board boot or XNU transfer occurred.

Actual-kernel container integration evidence: compare_native_macho.py now wraps
the built kernel in a 16,207,576-byte integrity container, validates it natively,
then uses the in-container kernel pointer for symbols/relocations/segments,
combined handoff planning and the 17,252,352-byte host-buffer materialization.
All comparisons pass. Container tests now recompute table hashes after malformed
kind/flags/offset/length/reserved-field mutations to exercise structural rejection
independently of checksums. This runs entirely in host memory; runtime container
location and complete source-buffer lifetime reservation remain unimplemented.

Versioned payload-container checkpoint: native parser and host encoder now share
a bounded kernel/optional-init envelope with checked canonical offsets, zero
padding, exact lengths, table SHA-256 and payload SHA-256. Validation publishes
no partial offsets. Fresh probe build bl33-probe-f0d6gfvu succeeds; host fixtures
exercise one/two payloads, every small-fixture truncation and metadata/data
mutations. See PAYLOAD-CONTAINER.md. This is integrity, not authenticity, and
the envelope is not yet located/loaded by the runtime probe or boot firmware.

Payload-hash prerequisite: the freestanding probe now links the unmodified
pinned BearSSL SHA-256 subset (sha2small/dec32be/enc32be) through a small loader
wrapper. Build checks the exact clean candidate revision and hashes its headers,
sources and MIT license into the manifest; no dummy verifier is used. Fresh
build bl33-probe-u4dh9hg1 links with no undefined symbols. Host tests compare
263 lengths, including padding boundaries and a million-byte input, against
hashlib. This is unkeyed integrity only, not signature authentication, kernel
crypto-provider registration or entropy. Container parsing remains unfinished.

Gate 1 readiness audit: GATE1-READINESS.md consolidates implemented helpers,
unwired runtime paths, remaining ownership/entropy/container/provider work and
board evidence requirements. Current local serial inventory does not identify
a Pi adapter; hardware/RAM/connection details have been requested. Corrected
stale loader README statements about FDT and CPU_ON support. No device was
opened, boot medium written or gate marked complete.

Freestanding stack checkpoint: build_probe.py now emits/hashes compiler .su
reports for every C source, records sorted frame sizes in the manifest and
rejects dynamic frames or any individual frame reaching the 16 KiB stack limit.
Build bl33-probe-t75n4kb9 reports 4,704 bytes for phandle validation (largest),
2,224 for handoff planning and 64 per recursive Apple-DT node. The reviewed
primary/FDT/phandle/structure/layout chain sums to 5,408 bytes; a handoff/placement/
segment chain is about 6.4 KiB before small callees. This is compiler frame
evidence, not automatic whole-call-graph/assembly/IRQ or runtime overflow proof.
The recursive serializer's bounded depth must remain part of stack review.

Combined native handoff planning checkpoint: handoff.c now composes kernel
placement, explicit live/tree/argument non-overlap, topOfKernelData, bootstrap
coverage and boot-argument serialization. It requires one caller-proven usable
extent and complete live allocations; it does not discover ownership or validate
tree semantics/entropy. On the actual kernel with synthetic addresses, boot-arg
bytes, top and entry match prepare_handoff.py; live/kernel overlap rejects with
unchanged output. Fresh build bl33-probe-6arpplh0 succeeds. Relocation validation
still occurs separately in materialization; no physical handoff is enabled.

Runtime RNG candidate inventory: the probe now validates the enabled RNG200
binding and translated extent and reports either a candidate or unsupported
binding. Both paths explicitly state no entropy provider; neither reads RNG
registers nor blocks independent CPU/timer diagnostics. The pinned span passes;
changed length rejects without publishing output. Fresh probe build
bl33-probe-aulnlgit succeeds. Acquisition/health/ownership work in ENTROPY-SOURCE.md
remains required, and no seed or hardware behavior was observed.

Entropy-source investigation: the pinned tree declares RNG200 at 0x107d208000.
The pinned TF-A legacy Pi RNG source uses a different register layout and must
not be reused blindly; Pi 5 leaves its stack-protector path disabled. A separate
BSD Broadcom driver is a review candidate, not a qualified provider. See
ENTROPY-SOURCE.md for source evidence and required initialization/failure/health
work. No RNG registers or seed bytes were accessed; runtime entropy remains open.

Global phandle checkpoint: runtime inventory now rejects invalid/duplicate
phandles before resolving MMIO/timer/clock bindings. phandle and linux,phandle
can coexist only if equal on one node; repeated properties or cross-node reuse
reject. Validation is bounded to 1024 unique handles and uses about 4.5 KiB of
local bookkeeping, with bounded pairwise comparisons. The pinned tree passes;
cross-provider duplicate mutation rejects. Fresh build bl33-probe-wk3q3euw
succeeds. This closes reference-identity ambiguity, not clock correctness or
device accessibility; alias/capacity edge fixtures still need broader coverage.

Runtime UART clock checkpoint: the native probe now validates its two named
clock references against the supported /clocks/clk-uart and clk-vpu fixed-clock
providers, explicit zero argument cells, enabled paths and nonzero rates. It
prints the runtime-declared rates, not measured frequencies, and rejects an
unsupported graph before PSCI/GIC tests. Pinned rates resolve to 9,216,000 and
750,000,000 Hz; zero-rate mutation fails with unchanged output. Fresh build
bl33-probe-c0stpr36 succeeds. Global phandle uniqueness, hardware clock verification
and baud interpretation remain separate work; this is not a general clock driver.

Runtime timer-binding checkpoint: before PSCI/GIC work, the probe now requires
the supported enabled armv8 timer, GIC three-cell interrupt-controller binding,
matching explicit/inherited parent phandle and the pinned four PPI tuples.
The third tuple must describe virtual PPI 11 (INTID 27); named/extended variants
are rejected rather than guessed. The pinned tree passes and a mutated virtual
PPI rejects. Fresh build bl33-probe-gpzluwap succeeds. This is a narrow binding
check, not global phandle uniqueness, clock correctness or interrupt delivery.

Runtime MMIO contract integration: before PSCI/GIC probe operations, runtime FDT
validation now requires PL011/GIC-400 compatibility and exact UART10 plus four
GIC translated extents from the supported profile. A mismatch parks via the
existing contract-rejection path; no new address is blindly dereferenced.
The pinned blob passes and corrupted ranges reject. Fresh build
bl33-probe-bxw0wgem succeeds. Earliest UART logging still precedes FDT validation
and relies on the pinned firmware/MMIO contract. Matching addresses do not prove
clock state, interrupt wiring, accessibility or hardware behavior.

Native MMIO translation checkpoint: fdt_reg.c resolves exact-path reg extents
through ancestor ranges with explicit 1/2-cell widths, enabled status checks,
overflow/straddle/ambiguous-match rejection and a final 40-bit limit. Empty
ranges means identity; absent ranges is rejected. It supports at most eight
reg extents and 32 mapping tuples per bus, not PCI formats or aliases. The
pinned board fixture resolves UART10 to 0x107d001000 and GICD/GICC to
0x107fff9000/0x107fffa000; corrupt ranges reject with unchanged output. Fresh
build bl33-probe-5zskzqxt and all 92 host tests pass. Probe MMIO integration and
runtime clock discovery remain unfinished; no hardware access was performed.

Native runtime lookup prerequisite: fdt.c now supports exact absolute-path
property lookup returning bounded offsets into the validated stable FDT. It
rejects duplicate matching path components/properties and malformed paths;
absence is distinct from malformed input and neither publishes output. It does
not resolve aliases/phandles, translate ranges or interpret clocks. Sanitizer
fixtures cover successful lookup, missing paths/properties and ambiguities.
Fresh probe build bl33-probe-c1j_8p1h succeeds. Runtime UART/GIC addresses still
use the pinned contract until binding/translation integration is complete.

CPU indexing review: BCM2712 already preserves Aff1 using four logical cluster
slots. A native regression compiles the actual MPIDR macros and cluster-offset
loop and checks all 15 nonempty subsets of Pi affinities for distinct bounded
indices. All 90 host tests pass. This removes an index-capacity uncertainty but
does not establish correct shared-cache/scheduler topology or hardware reset.
The tree must mark exactly the actual boot CPU running; see APPLE-DT-CONTRACT.md.

Apple tree consumer review: APPLE-DT-CONTRACT.md now records explicit early
clock/topology/seed requirements from current XNU source. A running CPU node
without bus-frequency can leave the legacy clock ratio divisor zero; the seed
consumer erases tree bytes in place. These require validated clock inputs and
writable reserved tree storage, not merely successful serialization. Runtime
clock/entropy acquisition and XNU affinity interpretation remain open. No kernel
code or hardware state was changed by this review.

Loader policy parity correction: reviewing prepare_handoff.py exposed missing
native exclusions for kernel-collection flags and nonempty __thread_starts.
Placement now rejects the former and native segment validation rejects the
latter, so materialization cannot silently ignore threaded fixups. In-memory
mutations of the real kernel exercise both rejections and require unchanged
destination/output. These are unsupported formats, not optional fixups.
Fresh probe build bl33-probe-2ppp4qqr succeeds. Device-tree semantics/integration
remain unfinished; this correction does not advance any hardware exit evidence.

Native Apple DT serialization checkpoint: apple_dt.c implements bounded two-pass
encoding, explicit property bytes, automatic name properties and four-byte padding.
It validates the stable input graph before output writes, rejecting cycles,
duplicate property/child names, invalid names and insufficient capacity. Limits
are 256 nodes, depth 64, 128 properties/children per node and 16 MiB; output/input
must not alias. A sanitizer fixture matches the host encoder byte-for-byte and
checks cycle/name/capacity rejection without output mutation. Fresh build
bl33-probe-owoxo11g succeeds. This is a serializer, not the Pi hardware tree:
runtime property semantics, fresh entropy and physical handoff remain unfinished.

Native boot-argument checkpoint: boot_args.c serializes the pinned 1,152-byte
headless revision/version-2 ABI, derives initial tree KVA from a physical tree
allocation, and checks that the tree follows the kernel inside topOfKernelData.
Counted ASCII command lines must leave a terminator; all padding/video/flags are
zero. Output is unchanged on invalid input. Host equivalence fixtures compare
every byte for empty, ordinary and maximum-length command lines, with placement,
overflow and malformed-command rejection cases. Fresh probe build
bl33-probe-kwc40n8o succeeds. Apple DT construction, physical ownership/bootstrap
coverage of these arguments and real handoff integration remain unfinished.

Native materialization checkpoint: the routine validates symbols, relocation
sites, segments and physical destinations before writing a caller-owned arena.
It rejects buffer aliases before modifying scratch, clears the reserved envelope
and copies file bytes without rebasing (zero virtual slide). On the actual kernel,
17,252,352 host-buffer bytes match the reference, including gaps/zero-fill/page
tail; the trailing canary is intact. Undersized/overlapping destinations reject.
Fresh probe build bl33-probe-fgsmqnho succeeds. This is not wired to physical RAM:
ownership/reservations, bootstrap mapping, cache visibility, boot-data construction
and transfer remain open. Invalid memory mappings can still fault during a copy;
the caller must establish exclusive writable memory first.

Native bootstrap arithmetic checkpoint: bootstrap.c models the current 16 KiB
start.s mapping from explicit boot bases, memory size, a single caller-proven
reservation-free extent and required early-boot ranges. It rejects incongruence,
zero mapping count, rounded mappings outside the extent, uncovered boot data and
more than four table pages. Sanitizer fixtures include the unmapped advertised
tail and crossing a 64 GiB root slot. This does not construct page tables or
discover free RAM; runtime integration remains open. Fresh probe build
bl33-probe-gy_q33xu succeeds.

Native physical-placement checkpoint: the planner translates zero-slide segments
from link base 0xfffffe0007004000 to a supplied physical header, enforcing 16 KiB
alignment, 32 MiB congruence, a file-backed header/commands, 40-bit bounds and
containment including page-rounded tail in one caller-proven free extent.
The actual kernel's destinations and entry agree with host arithmetic in a
synthetic interval; incongruence, insufficient tail space and out-of-extent
header mutations fail without changing output. The synthetic header 0x3004000
is NOT an approved board placement. Bootstrap mapping/table capacity, complete
ownership, copy and boot-data integration remain separate unfinished work.
Fresh probe build bl33-probe-pn37g636 succeeds.

Native local relocation checkpoint: all 93,292 records in the actual stripped
kernel pass the native unsigned-64-bit-absolute encoding, unique-site and
file-backing checks. The first segment defines the relocation address base,
matching the host audit. Caller-provided hash scratch detects duplicate sites
without quadratic pairwise comparisons; the actual image uses 262,144 uint32
slots (1 MiB), which must be reserved before runtime integration. Scratch is
mutable on failure, output count is not. In-memory duplicate/encoding mutations
are rejected with unchanged output count. Fresh build bl33-probe-0r041q4d and
all 86 host tests pass. This does not adjust pointer values, validate a nonzero
virtual slide, provide authenticated loading or prove boot. The zero-slide
loader still needs placement, copying and boot-data integration.

Native symbol checkpoint: macho.c now requires SYMTAB/DYSYMTAB, checks table and
index bounds, bounded NUL-terminated symbol names, absence of undefined symbols,
unsupported auxiliary tables and external relocations. Local relocation table
bounds are checked, but records still need semantic validation. String checks
scan the table once to avoid repeated suffix scans. The actual stripped kernel
passes this native check through compare_native_macho.py; all 18 segment records
still agree with the host audit. Fresh probe build bl33-probe-iw6g1kru succeeds.
Sanitizer cases cover undefined symbols, bad string indexes, missing terminators,
undefined counts, external relocations and oversized symbol counts. This remains
validation work, not a native loading/relocation or hardware result.

Actual-kernel native/host comparison: compare_native_macho.py compiles the
production native parser into a temporary host library and compares its output
with audit_macho.py on an explicit image. The built stripped kernel with SHA256
920d7b7a0270b99272d16f51059ed0de6c808d80c615dacad288c6dad2ebc3a8 passes:
all 18 segment names/VM extents/file extents/initial protections and entry
0xfffffe00074c8488 agree. The host audit also runs its stronger symbol/relocation
checks, but this does not imply those checks exist in the native parser.
Reproduce with `python3 tools/rpi5/compare_native_macho.py
build/rpi5/obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712`.
No physical placement, memory writes, relocation application or boot was tested.

Native Mach-O segment checkpoint: the new segment inventory validates at most
32 segments, VM/file overflow and overlaps, duplicate names, protection subsets,
section membership/alignment/file bounds, relocation-table bounds and an aligned
LC_UNIXTHREAD entry in executable file-backed bytes. Output is atomic. It still
does not validate symbol/relocation contents or authorize placement/copying.
The sanitizer fixture checks a valid image and rejects bad entry, non-executable
entry, oversized file data and VM wraparound; broader section/overlap cases and
comparison against the built kernel remain needed. Fresh build
bl33-probe-2rlqi7mc and all 86 host tests pass. No hardware execution occurred.

Native Mach-O input checkpoint: macho.c now validates thin ARM64/ALL MH_EXECUTE
header and load-command framing with unaligned-safe little-endian reads, bounded
lengths, the host audit's command allowlist, singleton uniqueness and command
shapes. This is deliberately a framing API, NOT permission to load an image:
segment/section semantics, symbol/relocation validation, placement and copying
remain unimplemented in native code. No runtime transfer path calls it yet.
Sanitizer tests exercise every prefix truncation, invalid section count, unsupported
commands, oversized lengths, wrong subtype and duplicate singleton commands.
Fresh probe build bl33-probe-i7cwiyod succeeds.

UART diagnostic checkpoint: before its entry report, the primary now takes a
read-only snapshot of UART10 CR/FR/IBRD/FBRD/LCRH and prints those raw values.
The snapshot does not change baud, clock, pinmux or line format and is explicitly
labeled clock-unverified. It depends on the same trusted MMIO/exclusive-access
contract as transmission; a disabled or misconfigured UART may still produce no
readable report. Host register-model coverage checks captured fields, preservation,
invalid pointers and unchanged output on rejection. Fresh probe build
bl33-probe-fwzfutqw succeeds; runtime clock discovery/baud verification remain open.

Secondary feature checkpoint: every started CPU now captures the same nine raw
feature registers before publishing its record. The primary prints indexed
values (PFR0, PFR1, MMFR0, MMFR1, MMFR2, ISAR0, ISAR1, CTR, DCZID) and stops
starting CPUs on any exact mismatch. This conservative homogeneous-board check
does not interpret capabilities or prove XNU compatibility. The dispatch model
now exercises a feature mismatch and confirms no later CPU is started; all 85
host tests pass. Final fresh build bl33-probe-kbn740i6 succeeds. Actual multicore
register reads, publication and UART evidence remain hardware work.

Primary CPU feature diagnostic checkpoint: the EL1 probe now prints raw
PFR0/PFR1, MMFR0/MMFR1/MMFR2, ISAR0/ISAR1, CTR and DCZID registers before PSCI
operations. Optional SVE identification registers are not read. This supplies
fields for eventual ISA/page-granule/cache review, not an automatic compatibility
verdict or evidence that every CPU matches. Fresh build bl33-probe-hrys2wyj and
all 85 host tests pass. Actual register reads and serial output remain untested
on the Pi; secondary feature comparison is still outstanding.

Pre-write FDT guard checkpoint: primary assembly now validates the pinned
32-bit/aligned FDT pointer and bounded total length, and rejects header/full-tree
overlap with the complete probe image before setting SP or clearing BSS. Probe
placement below the pinned ATF end is also rejected. Early rejection parks
silently using the early vectors; it does not attempt unsafe UART reporting.
This prevents the probe's own initialization from overwriting an overlapping
FDT, but cannot undo corruption by firmware's earlier image load. Readability
still depends on the trusted firmware contract. Fresh probe build
bl33-probe-703kl4mo succeeds; instruction behavior requires hardware validation.

Live-range validation checkpoint: before any PSCI query/CPU_ON, runtime inventory
now requires the full probe image/stacks and FDT to be disjoint and wholly covered
by advertised RAM, and the probe to lie above the pinned ATF reservation. Adjacent
RAM banks can jointly cover an image; holes, overlapping images, malformed extents
and out-of-RAM tails fail closed. The sanitizer harness covers those cases.
This check occurs after firmware loading and primary BSS/stack use, so cannot
prevent prior loader corruption or establish complete firmware ownership.
Fresh probe build bl33-probe-tifhop39 and all 85 host tests pass. Hardware
execution is still unverified; Gate 1 has not passed.

Runtime diagnostic integration checkpoint: the probe now decodes and resolves
well-formed reservations for logging, excluding pinned ATF, its complete linker
image/BSS/all-stack extent, and the runtime FDT. Proposed dynamic ranges are
explicitly NOT_COMMITTED; remaining candidates are marked live-inventory
incomplete and NOT_ALLOCATOR_INPUT. Malformed, unsupported and no-fit cases have
distinct diagnostics and never publish a partial proposal. These errors still
permit independent CPU/timer diagnostics; no XNU loader uses the result.
Fresh build bl33-probe-74v5mcnf and 85 host tests pass; an additional runtime-style
ATF/probe/FDT exclusion case passes in the resolver sanitizer test. Hardware
execution and completeness of firmware/live-image ownership remain unverified.

Dynamic reservation resolution checkpoint: reservations.c now plans requests
against RAM minus fixed exclusions and caller-supplied live extents. Each chosen
range is excluded before the next request; failure leaves the caller's output
unchanged. This is deterministic input-order first-fit, not an optimal packing
algorithm or a committed allocation. Fresh probe build bl33-probe-pmwu2a49 and
all 85 host tests pass, including sanitizer-backed sequential/atomicity tests.
Runtime integration and complete live-image ownership remain open; the malformed
pinned CMA encoding remains rejected. No hardware gate evidence was obtained.

Dynamic request decoding checkpoint: the native reservation plan now separates
fixed exclusions from up to eight bounded size/alignment/window requests.
Widths follow parent size/address cells, alignment must be a power of two,
and absent alloc-ranges means the physical profile before RAM intersection.
Static reg still overrides dynamic fields. Tests cover valid constrained requests,
short size encoding, bad alignment and static precedence. Fresh build and all
84 tests pass. The pinned CMA blob now reports malformed input (-1), not merely
unsupported dynamics (-2); no implicit encoding repair or allocation occurs.

Dynamic-placement prerequisite: ranges_find now chooses the lowest aligned
fit within available RAM intersected with explicit allowed windows. It validates
power-of-two alignment, 40-bit bounds and sorted RAM; failure leaves output
unchanged. A sanitizer-backed exhaustive-address oracle checks 1,000 generated
placement cases, with additional window/alignment/no-fit/boundary tests. Fresh
build and all 83 tests pass. This is a pure placement primitive, not a completed
dynamic-reservation policy or committed allocation; CMA decoding remains open.

Reservation-policy investigation: official binding/Linux source distinguish
dynamic CMA requests from existing physical reservations. Fixed reg must take
precedence over size; corrected both parsers and added a host regression test.
The pinned blob's four-byte CMA size conflicts with its two size cells, whereas
the inspected Pi source branch uses eight bytes. No blob replacement or silent
compatibility correction was made. See RESERVATION-POLICY.md for sources and
remaining resolution work. Fresh build and all 83 tests pass.

Native reservation discovery checkpoint: fdt.c now inventories header reservations
and static reserved-memory reg ranges, retaining reusable pools as exclusions.
Unsupported dynamic/IOMMU/nested policies return a separate error without partial
output. Runtime logs unresolved reservations explicitly and still exposes no
allocator. Tests verify empty/header reservations and the pinned Pi tree's
dynamic-CMA rejection; broader static-binding tests remain required. Fresh build
and all 82 tests pass. Dynamic reservation policy remains a loader-placement
blocker, not a reason to silently reuse the requested memory.

Native range-exclusion checkpoint: ranges.c subtracts up to 64 unordered or
overlapping exclusions from sorted RAM, producing at most 32 final fragments.
It validates 40-bit half-open inputs and preserves output on failure. A
sanitizer-backed byte oracle checks 1,000 generated exclusion sets plus capacity,
invalid-input and 40-bit-boundary cases. Added compiler-required freestanding
memset; fresh build and all 82 tests pass. This is not yet wired as allocator
input: complete native reservation discovery/live-image exclusions remain open.

RAM-boundary validation checkpoint: fifteen sanitizer-backed native cases now
cover one-cell ranges, sorted holes/above-4-GiB addresses, adjacent extents,
the exact 40-bit endpoint, zero sizes, overflow, overlap/duplicates, duplicate
reg properties, disabled/failed memory and the eight-range capacity boundary.
Failure cases verify output remains unchanged. All 81 host tests pass. This
validates advertised-range extraction only; reservation subtraction and actual
board memory/placement evidence remain open.

Native RAM inventory checkpoint: runtime FDT handling now extracts and reports
up to eight advertised RAM extents using explicit root cell widths, preserving
holes and addresses above 4 GiB within the 40-bit profile. Zero/overflowing or
overlapping active ranges are rejected and output is sorted. Reservations are
not subtracted, so logs explicitly say NOT_ALLOCATOR_INPUT. The pinned-DTB
sanitizer test returns its static [0,0x28000000) range, not the user's RAM SKU.
A compiler-generated struct copy required memcpy; added a freestanding byte-copy
implementation and restored successful linking. All 80 host tests pass; expanded
RAM edge-case tests and physical memory/placement verification remain required.

Runtime PSCI conduit checkpoint: before any SMC, the probe now requires one
enabled /psci node, a supported 0.2/1.0 compatible string and method=smc.
Duplicate consumed properties/nodes and unsupported status/method are rejected.
CPU extraction and conduit validation both precede PSCI_VERSION. Native tests
accept the pinned Pi tree, reject missing PSCI and reject an HVC-mutated tree.
Fresh build and the 80-test suite pass; hardware validation remains absent.

Per-CPU GIC identity checkpoint: each secondary now records its banked target
mask, and primary validates a nonzero one-hot mask distinct from its own and
previously accepted CPUs. Primary inventory and secondary extraction share one
register-reading helper. The dispatch model uses deliberately permuted target
bits and rejects zero, multi-bit and duplicate-primary masks. Fresh builds and
all 80 host tests pass. The mapping has not been observed on actual hardware.

Secondary fault-channel checkpoint: each secondary now tags its record slot in
TPIDRRO_EL0. The fatal handler publishes slot/EL/ESR/ELR/raw FAR/SPSR to that
record with ready=2 and no UART access. Primary recognizes this terminal state,
prints the fault and stops further startup. Primary retains direct fault output.
Early faults before slot/vector initialization, or nested reporting faults, may
still appear as timeout. Fresh build and 80 host tests pass, including modeled
primary handling of ready=2. Physical fault injection remains unperformed.

Per-secondary IRQ wiring checkpoint: each secondary now runs the same bounded
timer/GIC test before ready publication, then records its verified flag, raw
acknowledgment, count and timer status. Primary validation rejects failed cleanup,
wrong ID/count/status or invalid EL1 state before starting another CPU. Normal
and fault UART writes are restricted to the primary affinity; a secondary fault
therefore manifests as timeout until a separate fault-record channel is added.
IRQ scratch state is shared only under this serialized test protocol, not SMP
kernel-safe. Fresh build and all 80 tests pass, including four new modeled
secondary IRQ rejection cases. No physical all-CPU IRQ result exists yet.

Secondary dispatch validation checkpoint: a sanitizer-backed native host model
now executes the production start_secondaries control flow. It verifies slot/
affinity arguments, nonzero primary affinity, disabled targets, already-on or
pending targets, CPU_ON errors, counter and iteration timeouts, used slots and
invalid returned EL/affinity/cache/mask/frequency/ready fields. Failure prevents
subsequent starts; a stalled counter hits the iteration cap. All 80 host tests
pass. The model injects publication and does not prove real SMC, cache visibility,
secondary assembly execution or hardware timing.

CPU_ON dispatch checkpoint: when runtime CPU extraction and PSCI feature checks
succeed, the probe now starts enabled non-primary CPUs serially. Each must be
OFF with an unused record slot; CPU_ON64 receives the dedicated entry and slot.
Waiting is bounded by one reported-counter second and a ten-million-iteration
cap. Failure stops further starts without retry/reuse. Published records are
checked for target affinity, EL1, disabled MMU/caches, masked exceptions and
matching CNTFRQ. Fresh build, SMC argument disassembly and 79 existing tests
pass; this new orchestration has not run on hardware or in a behavioral model.
Secondaries park after reporting and do not yet run timer IRQ tests.

Secondary entry checkpoint: added a separate PSCI entry with bounded slot
context, four dedicated normal/fault stacks, no BSS clearing and shared EL2→EL1
normalization. Fault-stack pointers now live in per-CPU TPIDR_EL1/EL2 registers.
The secondary records its EL1 state and publishes a ready flag before parking;
it does not use the normal UART path or run IRQ tests. Fresh build, secondary
entry disassembly and all 79 host tests pass. No CPU_ON is issued yet; record
consumption, timeout/ownership checks and per-secondary timer proof remain open.

Runtime topology integration checkpoint: PSCI affinity inventory now consumes
the native extractor's enabled CPU list instead of hard-coded affinities. The
wrapper requires an aligned 32-bit firmware pointer above the ATF reservation
and bounds totalsize to pinned TF-A's 4 MiB DT mapping window, clipped at 4 GiB.
This explicitly trusts firmware to supply readable, stable RAM; it is not a
fault-safe pointer validator. Physical read faults remain fatal diagnostics.
Fresh build and all 79 tests pass, but this new physical-access wrapper has
not executed on the Pi. No CPU_ON call is issued.

CPU-binding adversarial checkpoint: 14 synthetic native cases now exercise
one/two-cell affinities, disabled CPUs, duplicate affinities/names/consumed
properties, reserved affinity bits, unsupported node names/status, mismatched
cell widths and excess CPUs. Failure cases verify unchanged output. Address
and undefined-behavior sanitizers pass; all 79 host tests pass. These fixtures
validate extraction policy, not runtime firmware access or secondary execution.

Native CPU extraction checkpoint: rpi5_fdt_cpus now extracts up to four CPU
affinities and enabled-state bits after structural validation. It requires
explicit 1/2 address cells, zero size cells, exact Cortex-A76/PSCI bindings,
valid affinity bits, unique CPU names/affinities and unique consumed fields.
Sanitizer testing verifies the pinned tree yields 0/0x100/0x200/0x300 and rejects
an altered CPU type without modifying output. Fresh build and all 78 tests pass.
This is a narrow Pi binding, not general FDT semantic validation; runtime buffer
mapping and use by secondary startup remain unfinished.

Native FDT token checkpoint: allocation-free structure validation now checks
bounded nesting (64 levels), one empty-name root, balanced nodes, properties
before children, property/string bounds, zero padding and exact final END.
Native sanitizer tests cover minimal/property fixtures, malformed tokens and
the pinned Pi DTB; fresh build and all 78 host tests pass. Duplicate names,
binding semantics and CPU extraction remain unimplemented, so this is not yet
trusted topology input or runtime firmware-pointer validation.

Native FDT framing checkpoint: loader/rpi5/fdt.c now provides an allocation-free
bounded header/block/reservation-terminator validator, with unchanged output on
failure. The native sanitizer harness covers every truncation of a synthetic
fixture, malformed offsets/lengths/alignment/overlap and the pinned Pi DTB.
Fresh probe build and all 78 host tests pass. This component is linked but not
called on the unvalidated firmware pointer: establishing readable physical
extent, token parsing, topology extraction and reservation policy remain open.

Secondary preflight checkpoint: after successful AFFINITY_INFO64 feature query,
the probe now reads power state for pinned-DTB affinities 0/0x100/0x200/0x300 at
level 0. It preserves Aff1, identifies the boot CPU via MPIDR affinity fields,
and skips the inventory if that CPU is outside the candidate set. OFF, ON,
ON_PENDING and unknown/error are distinguished without starting any CPU.
Pinned TF-A's MT-aware topology validation was inspected. Fresh build and
77 host tests pass; these new SMC results have not been observed on hardware.
Runtime CPU enumeration and independent secondary entry/stacks remain required.

IRQ acknowledgment validation checkpoint: the production C handler now uses
the existing MMIO accessors, allowing a sanitizer-backed host harness to check
its actual control flow. Cases verify timer quiescence before EOI, combined and
split completion, the non-secure bit-9 selection rather than bit 10, preservation
of the full acknowledgment value, and no EOI for special IDs 1020–1023.
Fresh probe build succeeds. This adds handler-model evidence, not exception
entry, architectural barrier or physical interrupt-delivery proof.

IRQ control-flow validation checkpoint: a native host harness now executes the
extracted production timer_irq_probe body with explicit system-register/MMIO
substitutes. Eleven cases cover observed interrupt, timeout, unexpected ID,
refused enablement, failed cleanup, counter overflow, invalid frequency,
enabled SPI, pending/active interrupts and wrong timer trigger mode. Address
and undefined-behavior sanitizers pass. This models setup/result/cleanup logic,
not real GIC security, exception entry, timing or MMIO ordering; Pi proof remains
missing. New assembly in the extracted function requires an explicit model.

Single-core IRQ wiring checkpoint: the probe now checks the GICv2/security
profile, requires no enabled PPIs/SPIs or pending/active interrupts, and requires
level-configured timer 27 before configuring its priority/Group 1 delivery.
It enables an approximately 1 ms CNTV deadline, unmasks IRQs for a bounded
iteration loop, then quiesces the source and restores saved GIC controls/priority.
Cleanup readback is part of the diagnostic result. Fresh build and all 75
existing host tests pass; generated IRQ-mask/timer instructions were inspected.
The new MMIO/IRQ path has no hardware or behavioral host-test proof yet.
All-CPU Gate 1 remains open; no board was booted or media written.

IRQ entry checkpoint: added a separate EL1 vector table and one-shot IRQ entry
preserving x0–x30/ELR/SPSR, with forced IRQ masking on return. The C handler
records IAR, quiesces timer 27 and completes ordinary GIC IDs according to the
non-secure EOImodeNS bit; special IDs are not EOI'd. Pinned TF-A Group 1 setup
and Arm's non-secure register view were checked. Fresh build, targeted frame
disassembly and all 75 existing host tests pass. Controller enablement is not
implemented, and the handler has not executed on hardware. No gate is passed.

GIC inventory checkpoint: verified pinned-DTB distributor/CPU-interface address
translation and added read-only native ID/type/CPU-target-mask reporting. The
target mask is folded from banked SGI/PPI target registers, not MPIDR.Aff0.
The probe does not acknowledge or configure interrupts. Fresh build and all
75 existing host tests pass; no hardware MMIO execution is verified. See
GIC-CONTRACT.md for extents, register provenance and the remaining IRQ work.

Masked virtual-timer checkpoint: the EL1 diagnostic now programs CNTV_CVAL
approximately 1 ms ahead using CNTFRQ, enables CNTV with IMASK set, polls its
condition with a one-million-iteration cap, and disables it before reporting.
It records begin/deadline/end/status and rejects invalid frequency or arithmetic
wrap. A condition observation is explicitly not IRQ proof. Fresh build and
75 existing host tests pass; disassembly confirms timer register operations.
This new hardware path has not executed and is not covered by the host tests.
GIC delivery, timer timing accuracy and secondary-CPU behavior remain unverified.

PSCI query checkpoint: the EL1 probe now issues PSCI_VERSION and, for a
non-error version >=1.0, PSCI_FEATURES for CPU_ON64 and AFFINITY_INFO64.
Results are logged as low-32-bit raw values, not interpreted as successful
secondary startup. IDs match pinned TF-A psci.h; the pinned Pi DTB declares
method=smc. Fresh build, SMC-wrapper disassembly and all 75 existing host tests
pass. No SMC has executed on hardware, runtime conduit discovery is pending,
and CPU_ON itself is not called. This does not close the PSCI hardware gate.

Single-primary EL1 checkpoint: BL33 now establishes explicit non-VHE EL2 trap,
timer-offset/access and EL1 control/stack/vector state, then ERETs to masked
EL1h. The EL1 routine reports control state and CNTVCT before parking; fatal
diagnostics now support both levels. Fresh build and all 75 host tests pass.
Targeted disassembly confirms the register writes and ERET. No Pi execution
has validated this transition. Timer IRQs, PSCI secondaries, runtime tree/loader
integration, entropy and Gate 0 providers remain open. See TF-A-CONTRACT.md.

EL2 diagnostic checkpoint: the native probe now switches from early parking
vectors to 16 slot-labelled fatal-reporting vectors after initialization.
The handler captures ESR/ELR/raw FAR/SPSR, switches to a dedicated 16 KiB stack,
and restores parking vectors before calling the bounded UART logger to contain
nested faults. Fresh ELF/raw build and 75 host tests pass; targeted disassembly
confirms register capture, stack switch and logger call. Hardware fault injection
is still required; this does not prove serial reporting or pass Gate 1.

Repeatable BL33 build checkpoint: `tools/rpi5/build_probe.py --load-address
0x200000` compiles every object afresh and records source/artifact hashes,
commands and compiler/linker versions. Two fresh directories produced identical
ELF and raw binaries; raw SHA-256 is
09c0f7266d20ef36d1fd8fcfbcac3d9525a51f553e4c48a45db7b2aef8693abe.
Artifact checks cover static AArch64 executable identity, entry, LOAD extents,
W^X, remaining relocations, undefined symbols and raw/ELF byte agreement.
All 75 host tests pass. The manifest explicitly does not approve board placement.
This is same-host repeatability, not independent toolchain reproducibility or
hardware proof. Gate 0 provider closure and Gate 1 hardware probes remain open.

The checkpoints below are historical; later entries above supersede earlier
statements about components or tools that were then unavailable.

BL33 entry checkpoint: a limited native diagnostic probe now links to ELF/raw
binary. It checks EL2 and disabled MMU/caches, preserves FDT PA, installs parking
vectors, initializes its stack/BSS and reports basic CPU/FDT state through the
bounded UART routine before stopping. Disassembly and LOAD extents inspected;
no Pi execution or media writes. EL1 normalization, fault reporting, timer/PSCI
probes and native XNU loading remain unimplemented. This is not a passed gate.

BL31 build checkpoint: pinned Pi TF-A builds successfully using project-local
tool wrappers. bl31.bin is 45,174 bytes, SHA-256
413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46.
ELF inspection finds no undefined symbols/dynamic section and LOAD extents
within the observed firmware reservation. No media was written or hardware
booted; native BL33 entry/probes and kernel runtime providers remain unfinished.

TF-A source checkpoint: pinned Raspberry Pi fork commit
332b62e0443b004287d2cfc032a70bba6fb86f35 and verified the Pi 5 BL33 path selects
non-secure EL2h, masked exceptions, x0=physical FDT and x1–x3=0. Recorded explicit
runtime-UART disablement because source and documentation defaults differ.
No BL31 build or board execution was performed. See TF-A-CONTRACT.md.

ELF linker prerequisite resolved locally: downloaded Zig 0.16.0, verified its
archive SHA-256 against official metadata and pinned it in the loader toolchain
lock. The link driver successfully links the existing AArch64 UART object to
a static ELF executable (probe SHA-256
4de397e392b0416c8fa15d9b39ffcb4f5230a03a61f644876092f49b37fbf747).
This probe deliberately has no boot initialization and must not be booted.
The tool/cache stay in project build output; no system toolchain was changed.

Loader toolchain checkpoint: Apple clang can compile the native UART component
to ELF64 little-endian AArch64 ET_REL, now checked in the host suite. No ELF
linker was found in PATH or standard Xcode/Homebrew LLVM/LLD locations, so a
standalone loader image cannot yet be linked with the discovered tools. This
is a build prerequisite, not evidence of a runtime failure or a completed gate.

Native loader component checkpoint: loader/rpi5/uart.c now implements bounded
firmware-preserving PL011 transmit/drain. It rejects disabled/invalid inputs and
returns timeout for a full FIFO or busy transmitter. Cortex-A76 freestanding
compilation has no undefined symbols; all 72 host tests pass. Register-array
tests are not actual MMIO, baud or serial evidence. No boot entry/EL transition
or native loader image exists yet.

UART clock checkpoint: fixed-clock phandle resolution reads uartclk=9,216,000 Hz
and apb_pclk=750,000,000 Hz from the pinned Pi firmware DTB. All 71 host tests
pass, including missing/extra references and unsupported-provider rejection.
These are declared rates, not measured hardware state; current divisors, firmware
clock changes and actual serial output remain unverified.

UART address checkpoint: added simple-bus reg/ranges translation with explicit
cell widths, extent containment, overflow and ambiguous-match checks. The pinned
official DTB resolves serial10's node to [0x107d001000, 0x107d001200), rather than
its untranslated 0x7d001000 reg value. All 70 host tests pass. PCI encodings,
runtime firmware changes, UART clocks and actual MMIO operation remain unverified.

Official Pi DTB checkpoint: structure parsing succeeds for firmware revision
2768f6105ab38838934f9cfb3c5e5c16326d8a01. All 69 local tests pass, including the
optional pinned-blob regression. Its no-map ATF reservation [0, 0x80000) makes
the previous zero-prefix synthetic placement unsuitable for actual Pi use.
The dynamic CMA request is rejected pending policy/implementation. Runtime FDT,
RAM SKU and UART hardware evidence are still missing; this blob is not runtime
memory evidence. See DEVICE-TREE-CONTRACT.md for provenance and details.

Reservation checkpoint: host FDT memory discovery now subtracts static reserved
nodes, header reservations and explicit additional live ranges. Reusable pools
stay excluded; unresolved dynamic/IOMMU bindings fail closed. All 68 host tests
pass. Actual-board DTB validation and native allocator integration remain open;
this does not establish that all firmware-owned memory has been identified.

FDT RAM checkpoint: root memory tuples now decode with explicit cell widths,
preserving holes and addresses above 4 GiB. All 67 host tests pass. Overlaps,
malformed tuples and ranges outside 40 bits are rejected. This is advertised
RAM inventory only; reserved-memory children and subtraction remain unfinished,
so these ranges must not yet be used as allocator input.

FDT input checkpoint: added a bounded host reader for headers, reservation pairs,
tree tokens and raw property bytes. All 66 host tests pass, including every
truncation of the synthetic fixture and malformed offsets/tokens/lengths.
This is not the native loader parser or full RAM/address translation; actual
firmware DTB validation and reserved-memory semantics remain open.

Device-tree semantic audit: recorded early consumers in DEVICE-TREE-CONTRACT.md.
Confirmed mandatory chosen DRAM fields, in-place consumption/clearing of the
random seed, CPU reg/state interpretation and native-width arm-io ranges access.
The translator must not copy Linux FDT cells verbatim. This turn adds source
requirements, not a board tree or further runtime evidence; gates remain open.

Tree/handoff integration checkpoint: `prepare_with_tree` now derives the tree
length and allocation from the actual encoder output and returns matching
tree/boot_args write plans. All 63 host tests pass, including rejection of an
independent length and tree growth overlapping the loader stack. This closes
the byte-length consistency gap, not the missing board description, native
loader, runtime entropy or providers. Neither gate has passed.

Apple DT consumer checkpoint: compiled the exact next_prop_region and
SecureDTGetPropertyInternal bodies with upstream node/property declarations
against encoder output. Native lookup successfully reads odd-length and 64-bit
payloads across padding and returns an error for a missing property. All 62
host tests pass. The harness substitutes host bounds assertions and overflow
intrinsics; this is not the complete SecureDT parser or malformed-input audit.
Tree traversal and actual Pi property semantics remain unverified.

Apple DT encoding checkpoint: added a bounded encoder using the pinned XNU
node/property layout and parser alignment rules. All 61 host tests pass,
including exact wire bytes, nested nodes, duplicate names, cycle and size-limit
rejection. This supplies encoding only, not a hardware description or Linux FDT
translation. Native SecureDT compatibility and runtime tree semantics remain open.

Composed handoff checkpoint: `prepare_handoff.py` connects image inspection,
copy/zero ranges, allocation conflict checks, mapping validation and argument
serialization. All 59 host tests pass. The current kernel produces ten copies
and two zero ranges in the synthetic layout, fitting four bootstrap-table pages.
No physical writes, firmware handoff or board execution occurred. A native
loader, real FDT/AppleDT, fresh entropy and runtime-provider closure remain open.

Device-tree handoff checkpoint: traced start.s -> arm_init -> PE_init_platform
and the later PE_slide_devicetree transition. The serialized tree pointer must
be initial linear KVA, unlike the physical pointer to boot_args at entry.
Added `encode_with_physical_tree` to derive that KVA and reject allocations
before kernel end, beyond topOfKernelData, unaligned or outside 40-bit RAM.
All 57 host tests pass. Full allocation/mapping integration and runtime handoff
remain unverified; this does not clear Gate 0 or Gate 1.

Boot-argument ABI checkpoint: added the headless arm64 binary serializer and
checked all field offsets plus the 1152-byte size with native arm64 static
assertions against the pinned header's exact C declarations. All 56 host tests
pass, including representation bounds and command-line termination checks.
This does not establish address-space correctness, boot version acceptance or
reservation coverage, and it is not yet wired into an executable loader.

Bootstrap host-model checkpoint: `bootstrap_layout.py` enforces zero-slide base
congruence, 40-bit bounds, nonzero block count, four-page initialization limit,
rounded-prefix reservation checks and required-range mapping coverage. All 53
host tests pass. Current kernel SHA-256
`920d7b7a0270b99272d16f51059ed0de6c808d80c615dacad288c6dad2ebc3a8`
fits the documented synthetic layout; real RAM reservations and all non-kernel
boot allocations remain unvalidated. This model is not a runnable loader.

Bootstrap checkpoint `run-aw4h7myy`: make all passes after correcting the
arm_vm_init.c capacity check to compare pages with pages, rather than bytes.
All 50 host tests pass, including exact capacity and one-page-overflow cases.
The loader contract now records the assembly mapping's truncated block count,
unsafe zero-count case, mapped prefix and initial four-page clearing limit.
These require loader-side validation before entry; the later C capacity check
cannot make an invalid assembly mapping safe. No hardware boot is claimed.

Feature-read checkpoint `run-oqop8gl5`: make all passes, source unchanged during
build. The Pi commpage no longer unconditionally reads ID_AA64ZFR0_EL1; its SVE
capability flags remain zero. Non-Pi detection is unchanged. All 49 host tests
pass, including both branches, and rebuilt disassembly confirms removal of
`S3_0_C0_C4_4`. This is explicit no-SVE board behavior, not a demonstrated
hardware fault fix. The remaining `S3_0_C0_C4_5` is ID_AA64SMFR0_EL1 and is
behind `arm_sme_version() != 0`; sme.c initializes the version to zero and only
probes it under HAS_ARM_FEAT_SME. Full instruction/runtime reachability auditing
remains open. Architecture reference inspected:
[Cortex-A76 TRM](https://documentation-service.arm.com/static/5f562083235b3560a01e03bc).

ISA checkpoint `run-aul5wpxy`: full incremental make all succeeds, exit 0,
source unchanged during build. Disassembly identified Apple AWL watchdog
diagnostic-register accesses (`S3_5_C15_C2_6`) in debug.c. BCM2712 now excludes
those accesses and cannot enable the AWL capability through device-tree data;
Apple-target behavior is preserved. Rebuilt disassembly contains zero accesses
to that register. All 48 host tests pass. Remaining generic register spellings
`S3_0_C0_C4_4` and `S3_0_C0_C4_5` in commpage feature detection still need review.
Raw disassembler unknowns include embedded data and are not by themselves proof
of unsupported executed instructions. The complete ISA audit remains open.

Relocation follow-up: all 93,292 local fixup sites fit file-backed segments, are
unique, and contain pointers into nonempty mapped segments. The current threaded
starts section is empty. The [initial loader contract](LOADER-CONTRACT.md)
records why zero virtual slide preserves these pointer values and must not be
confused with physical relocation. Startup source was inspected; no hardware
execution is implied. All 47 host tests pass, including invalid relocation
encodings, out-of-bounds sites and duplicate-site rejection.

Loader inventory checkpoint: `tools/rpi5/audit_macho.py` accepts the current
stripped kernel, SHA-256
`eb6cee20eb0ec2a254aab3487e6279d2e0cba7d3f52e45bb472de6fd8c75957a`.
It checks bounded load commands, segment/section extents, symbol tables and the
file-backed executable entry. The image has 93,292 local relocations, all
non-PC-relative, non-external, type 0, eight-byte entries; their application and
target semantics are not yet validated. Nonempty VM base is
`0xfffffe0007004000`, entry `0xfffffe00074c8488`; an L2-congruent physical mapping
of that base needs residue `0x1004000` modulo 32 MiB. The auditor is an inventory,
not a boot loader or ISA certification. All 46 host tests pass, including every
truncation of the synthetic image and malformed command/extent/thread cases.

Candidate SHA-512 wrapper checkpoint `bearssl-probe-wi0hiwkc`: the host probe
compiles the exact SHA512_Init/Update/Final bodies extracted from XNU, with the
real SHA512_CTX and crypto_functions declarations. All 1,290 length/chunk cases
pass, with context canaries unchanged and ten boundary digests independently
checked against Python hashlib. The candidate subset still has only memcpy and
memset as undefined dependencies. All 43 existing host tests also pass. The
partial table is a host-only fixture, not registered or linked into the kernel.
This does not validate entropy quality, provider concurrency or kernel startup;
Gate 0 remains open and Gate 1 still requires actual Pi serial evidence.

Crypto registration checkpoint `run-tcvxehnj`: make all passes; Pi now rejects
a null crypto table without setting crypto_init or changing the provider pointer.
Duplicate registration still fails and preserves the first provider. All 43
host tests pass. This checks publication state only, not table completeness:
legacy digest/cipher descriptors and newer random/digest/HMAC interfaces still
need a compatible implementation and startup registration.

PRNG contract checkpoint `run-377xc79v`: incremental make all passes after adding
Pi-only registration validation. A null context/table or missing required init,
per-CPU init, reseed, refresh or generate callback causes an explicit panic before
entropy/state mutation. The unused legacy init callback is not required. All 42
host tests pass, including all 32 required-callback presence combinations. This
does not supply a PRNG implementation or startup caller; both remain absent.

**Fresh kernel-output build passes:** `run-rrmkdwf5`, exit 0, source unchanged
during the build. Outputs are under `build/rpi5/fresh-q1zamcjl`; previous outputs
are preserved. The generated export policy and build ordering work without old
kernel objects. The prepared SDK/libfirehose are reused, so this is not a fully
independent dependency rebuild or bit-for-bit reproducibility claim. The fresh
kernel is ARM64/ALL MH_EXECUTE with no undefined symbols. SHA-256:
`5f520b2fa8196aa1b7c65f26d06b3af13c36460273df16f70e565877b61586ff`.
Next: runtime PRNG/crypto/security registration and full loader/ISA validation.
Gate 1 still has no serial hardware evidence.

**First successful incremental `make all`: `run-3wcan521`, exit 0.** Kernel
linking, export validation and all symbol sets complete. The final eight
trust-cache exports now match the existing BCM2712 exclusion of that provider;
PMAP trust lookups still fail closed. This does not install AMFI/Image4 or a
trust-cache service. All 41 host tests pass. A clean build, complete ISA/loader
audit and runtime PRNG/crypto/security-provider closure are still required for
Gate 0. The build uses the explicitly noncanonical installed Xcode toolchain.

Newest checkpoint `run-um1jyhcq`: 19 exact IOUnifiedAddressTranslator class
exports are excluded for Pi. This checkout contains a compiler-flag reference
but no class implementation; other IOMemoryDescriptor APIs remain advertised.
The kernel links, all 41 tests pass, and only eight trust-cache export errors
remain. Resolving those exports will not itself close runtime security providers.

Latest checkpoint `run-1adin7j0`: the Pi-only policy excludes 30 exact Apple
DART/SPTM, SART, NVMe-PPL and UAT descriptor APIs. These device/monitor extensions
are not the BCM2712 hardware ABI. No wildcard removal or validation bypass is
used. The kernel links; 27 export errors remain (IOUnifiedAddressTranslator and
trust-cache APIs). All 41 tests pass. Pi PCIe/DMA implementation remains deferred
to its planned gate, not supplied by these excluded Apple interfaces.

Newest checkpoint `run-2dk3jv01`: 16 private IOMMU-extension APIs are explicitly
excluded on Pi because the selected legacy ARM pmap_iommu.c is only an upstream
placeholder. General pmap exports remain. The kernel links and export validation
now reports 57 remaining errors. All 41 host tests pass. This does not implement
Pi DMA mapping or change the Gate 5 PCIe/RP1 requirements.

Latest checkpoint `run-tdujp3qi`: pmap_cs_configuration now delegates to the
existing shared code_signing_configuration provider and preserves its bitfield.
It does not return a hard-coded security state or install AMFI. The kernel links;
73 export-validation errors remain. All 41 host tests pass, including per-bit
forwarding of configuration values. Runtime policy/provider closure is still open.

Newest checkpoint `run-jnl5f_vw`: the Pi legacy pmap now implements
pmap_has_iofilter_protected_write as false, matching its documented capability
query and the existing panic-on-use write function. The kernel links; export
validation has 74 remaining errors. All 40 tests pass. The first edit misplaced
the existing noreturn annotation; compilation caught it and the corrected build
reached linking. This does not implement a guarded-I/O service.

Build-policy integration checkpoint `run-41ij5p7s`: generated Pi Private export
files now feed linker export/alias generation, symbol sets and export validation.
The kernel links; full build still fails on 75 unreviewed provider exports.
The 40 reviewed feature exclusions no longer appear as validation failures.
All 39 tests pass. This is an incremental-build verification; clean-build
dependency ordering is not yet verified. Public supported-KPI lists are unchanged
because the policy only modifies Private lists.

Newest kernel checkpoint `run-gwr8qbwc`: the 24 absolute-zero compression
aliases are removed for BCM2712 only. The kernel relinks with zero undefined
symbols and zero global absolute-zero definitions. Thus the selected linked
code does not require those aliases; external consumers remain unsupported.
The overall build still fails export validation because those unavailable APIs
remain advertised by upstream lists. All 34 host tests pass, including compilation
of the disabled-compression branch for Pi and the unchanged legacy behavior.

Provider audit found 24 upstream absolute-zero compression symbols in the
linked artifact (`!FS_COMPRESSION` in decmpfs.c). They must not be treated as
implemented APIs despite matching export names. The export audit now reports
these separately with optional `--kernel` inspection. Pi API policy must cover
both absent names and non-callable definitions; this remains unresolved.

Export-policy checkpoint `run-kpb_djd0`: BCM2712 now selects its own platform
export suffix instead of inheriting `MacOSX` from the host SDK. No macOS-only
KPI contract is advertised solely because of build inputs. Common and arm64
export lists, including their validation, remain unchanged. The build still
fails on Private exports for unavailable providers. All 32 host tests pass;
a make-fragment test checks Pi selection and preservation of MacOSX selection
for other boards. Remaining work is explicit Private API/provider policy and
the runtime/loader closure below, not a hardware-ready image.

Newest checkpoint: `run-js8t2wr1` produces the first linked stripped and
unstripped kernel plus dSYM, with **zero undefined symbols** (`nm -u`). The
manifest records unchanged source during that build. The overall `make all`
still exits 2: post-link symbol-set validation expects unavailable Apple and
disabled-feature exports. This is not a completed build or Gate 0 pass.
Firehose was rebuilt for the current configuration (`firehose-yhykn_e9`).
All 29 host tests pass after correcting the new harness's missing stdbool header.

MPTCP-only cache state and advice now follow the MPTCP provider. Without that
provider, TFO/ECN retain ordinary loss accounting, not fabricated Wi-Fi advice.
On BCM2712, profile extraction returns ENOTSUP and zone reachability scanning
returns KERN_NOT_SUPPORTED without touching output buffers or reporting success.
Other targets retain their original implementations. These diagnostics are
unsupported, not implemented; their absent providers are no longer link inputs.

Initial artifact inspection: thin ARM64/ALL MH_EXECUTE, LC_UNIXTHREAD entry
`0xfffffe00074c8488`, zero undefined symbols, 93,292 local relocations and split
segment information. No LC_LOAD_DYLIB or LC_LOAD_DYLINKER was observed. The loader
must honor zero-fill and virtual layout rather than copying the file verbatim.
Instruction compatibility and relocation handling remain unaudited. Runtime
PRNG/crypto/AMFI/Image4 integration, export policy and loader contracts remain
open before Gate 1. No board probes or boot-media writes have occurred.

Earlier observed link: `run-gg1_nx7w`, **6 unresolved symbols**. The real shared
packet-buffer implementation is selected for networking. Three mbuf metadata
helpers and their declarations moved out of PF-only source/header scope; their
bodies were compared with HEAD and are unchanged. The config test requires the
packet-buffer object once. A declaration cleanup occurred during the rebuild,
so this checkpoint is not a final unchanged-source artifact verification.
Remaining symbols: two LLVM profiling serializers, two MPTCP globals, Wi-Fi
symptoms query and zone scanning. Runtime/provider and hardware gates remain open.

Newest link: `run-ohkh8hid`, **14 unresolved symbols**. Socket-flow statistics
registration, callbacks and the associated retained reference now require the
Skywalk provider, matching its implementation. Ordinary flow tracking remains.
All 27 existing host tests pass; they do not validate flow-reference concurrency.

Current link: `run-ppiv3ohq`, **16 unresolved symbols**. IPsec-only ESP MTU and
keepalive references are now conditional. Ordinary MTU and non-IPsec keepalive
collection remain; a new MTU fallback test brings the suite to 27 passing tests.
Runtime and full-provider closure remain open.

Latest verified checkpoint: `run-t1nnmd_m` reaches kernel linking with **24
unresolved symbols**. Its manifest records unchanged source during the build.
Follow-up `run-gkpznj4_` reduces that to **22 unresolved symbols** by selecting
the real shared network-logging implementation for NETWORKING instead of IPsec.
The config-generation test now requires that object exactly once. All 26 tests
pass. The packet-buffer source also depends on PF fragment-tag helpers, so its
eight missing symbols require more than adding the source file alone.
Newest link `run-q5px3ttl` has **18 unresolved symbols**: bridge and content-filter
references are now absent when those features are disabled. Bridge helper/call
sites follow IF_BRIDGE. NECP qualification and its sole lookup helper follow
their content-filter caller; TCP listener setup treats absent filtering as absent.
The 26 host tests pass, but these feature boundaries lack runtime validation.
The socket options now return ENOPROTOOPT for unavailable Skywalk statistics
override and retain ordinary IP client-UUID retrieval without MPTCP. All 26 host
tests pass. The linker inventory is in [GATE0-CLOSURE.md](GATE0-CLOSURE.md).
Firehose must still be rebuilt for the final generated configuration, and runtime
crypto/PRNG/AMFI/Image4 integration remains open even after symbols are resolved.

## Implemented and verified

- Imported the pinned Apple Git history and checked out `codex/rpi5-bringup`.
  Baseline: `ac9718fb1af618d5ce8678d0dc6e8a58f252216f`.
- Saved Astra's revised sequence: build closure -> standalone hardware probes ->
  single-core PID 1 -> SMP -> SD -> RP1 Ethernet -> Darwin distribution.
- Added the experimental BCM2712 board, dedicated MASTER configuration, header
  export, Cortex-A76 cache-line definitions and plain-arm64 build selection.
- Excluded private Apple platform SDK search roots and the KDK platform archive
  from the Pi target. RELEASE is explicitly rejected during bring-up.
- Added locked dependency archives, host/toolchain checks, project SDK preparation
  and a build runner preserving logs, source state and toolchain provenance.
- Prepared the project SDK and AvailabilityVersions without changing Xcode's SDK.
- Twenty-seven automated tests pass: SHA validation, hostile archive rejection, valid
  extraction/no overwrite, independent SDK copying, board feature contract, and
  actual XNU MASTER configuration generation, 40-bit cache callback addresses,
  panic-region offset bounds, opaque entitlement contexts, and untrusted results
  when no trust-cache provider exists, public platform object selection, and
  commpage TLB invalidation/barrier ordering for range and non-range CPUs.
  Further tests cover socket/FIFO and IP/NECP source selection and
  SYN-cookie policy with and without multipath fields.
  Domain-registration tests check both networking modes. Stack-probe tests
  verify the compiler ABI and execute the real assembly against guard pages.
  Hardware-assist selection is tested with and without Skywalk.
  Further native tests cover nexus detection, receive-strategy selection in
  both Skywalk/development modes, and the Pi browser-role denial with the
  existing privileged-delegation check retained.
  Queue dispatch tests execute the shared dequeue path without Skywalk and
  verify the adapter callback receives its result when Skywalk is enabled.
  CoDel conversion tests compare the explicit float conversions with upstream
  arithmetic for representative counts, including the float precision boundary.
  TCP retransmit-reset tests verify the ordinary retry fields are cleared in
  both MPTCP modes and the multipath callback runs only when configured.
  Native fragment tests are not boot tests.
- XNU's `exporthdrs` target passes, including setup tools, IIG and MIG generation.
  Evidence: `build/rpi5/run-s1upbged/manifest.json` and adjacent `build.log`.
  Final header-export recheck also passed: `build/rpi5/run-45mh3yd2/manifest.json`.
- Full builds reach real kernel compilation. Generated flags select
  `-arch arm64 -mcpu=cortex-a76`, the Pi config and disabled branch-target
  identification. This is not yet proof of a compatible complete instruction set.

## Current build failures and next work

The initial missing CoreEntitlements V2 and TrustCache headers are now separated
from the BCM2712 DEVELOPMENT interface. Contexts are opaque; V2 registration
panics, trust-cache lookup reports untrusted, and Apple browser-entitlement roles
are not claimed. These are explicit unsupported features, not compatible Apple
security services. The modified AMFI interface is not a binary Apple ABI.

Cache callbacks preserve full pointer/40-bit addresses on the Pi target. Panic
offset arithmetic is checked before narrowing. The mockfs node allocation now
allocates the structure rather than its pointer typedef. Its zero-copy memory
mapping contract is still unresolved and must not be considered safe for boot.

The minimal configuration now includes telemetry, service-port information,
memory status, deferred reclamation, named streams and zone leak diagnostics required by code
in this snapshot. Disabled networking, KPERF, sleep and crypto paths received
scoped compilation fixes. Integer-valued callback cookies now cast through
uintptr_t. Exploratory toolchain builds retain warnings but relax error status
only for unused-but-set variables and GNU constant folding.

The real libfirehose_kernel archive builds from the matching libdispatch's single
kernel source, with input hashes and compiler command recorded in
`build/rpi5/firehose-kxzmtqma/manifest.json`. Its exported header uses upstream's
unifdef settings. Rebuild this archive after changing generated kernel config.

The first selected-component build reached final link and reported 303 undefined
symbols (`build/rpi5/run-5p99p5xy`). Public bootstrap/pmap sources were missing from
the source selection; they are now selected and pmap compiles. A subsequent link
reported 46 unresolved symbols (`build/rpi5/run-luci0a8r`). The count is not a
final provider inventory. Remaining runtime requirements and follow-up source
fixes are in [the closure worklist](GATE0-CLOSURE.md).

The subsequent local-socket/FIFO and diagnostic-source experiment compiles but
does not link (`build/rpi5/run-b2iqspqs`): socket code still depends on IP,
NECP and network statistics even with NETWORKING disabled. Resolving this
boundary is the current source-selection issue; the older 33-symbol checkpoint
does not describe the expanded configuration.

The domain-registration guards and real stack-probe implementation bring the
latest observed link to 84 unresolved symbols (`build/rpi5/run-i1i0ru4x`). The
Darwin stack-probe symbol is now resolved. Remaining socket/network and diagnostic
runtime dependencies still prevent a complete kernel image.

The revised baseline now selects the public IP, NECP and traffic-management core:
local sockets are too tightly coupled to those sources for a small isolated port.
This does not provide Pi network hardware drivers or move Ethernet out of Gate 5.
The configuration passes the host tests. The first expanded build stopped in
BPF's ESP declarations; forward declaration, Skywalk-only packet declarations,
and BPF's explicit platform-expert include correct those compilation failures.
The non-Skywalk hardware-assist path now returns the interface's actual flags;
its regression test also preserves the Skywalk adapter path.

The DLIL failures in `run-b74ux8s2` are corrected: Skywalk-only lock/state,
packet cases, synchronous receive marker and sysctls are conditional. The
ordinary mbuf strategy remains selected; the packet scheduler's shared
start-ignore-delay prototype is available outside Skywalk. Routing uses its
existing failed-lookup fallback when Nexus traffic rules are unavailable.
Receive-steering queries validate arguments, clear the output count and return
ENOTSUP without Skywalk. No successful replacement providers were added.

The earlier build `build/rpi5/run-fct2ea0m` stopped in `necp_client.c` on Skywalk-only
client state, route-resolution types and timer references, and in `droptap.c`
on Skywalk packet APIs. NECP/trie pointer traces now use full-width permuted
addresses. Pi NECP does not grant the unsupported Apple browser role; the
existing separate privileged-delegation check remains unchanged.
These boundaries are now corrected for NECP offload timers, connection statistics,
offload cleanup and drop-tap packet functions. The ordinary mbuf drop-tap path
remains compiled. Channel congestion reporting and adapter queue callbacks are
conditional; shared queue scheduling remains enabled. Queue tracing explicitly
includes its kernel-debug declarations.

The earlier build `build/rpi5/run-tmx38p64` stopped on remaining Skywalk packet paths in
`classq_fq_codel.c` and `pktsched.c`, four implicit integer-to-float conversions
in CoDel, and two now-unused NECP helpers. Those arithmetic conversions require
review of the intended scheduler calculation, not a blanket warning suppression.
Those packet cases are now conditional, and CoDel's existing single-precision
calculation uses explicit casts (not a changed algorithm or relaxed warning).
NECP statistics access and route-monitor registration/callback now follow their
Skywalk-only callers. The scheduler explicitly includes kernel debug declarations
and excludes its Skywalk-only trace instrumentation when unavailable.

The earlier build `build/rpi5/run-aly5tzss` stopped in `pktsched_fq_codel.c`: a missing
shared DLIL declaration, Skywalk dynamic diagnostics (`skoid_*`), and a channel
flow-advisory call. The previous NECP and scheduler arithmetic errors are absent.
Those scheduler errors are now corrected: DLIL is explicitly included and
dynamic diagnostics/channel notification are conditional on Skywalk. IPv4 input
includes its shared flow argument types, with dummynet-only copy helpers guarded.
IPv4 output explicitly includes IPv6 wire types and retains the NECP jump target
when IPsec is absent. Raw connected sockets use their peer address without content
filtering; socket reporting accesses the content-filter field only when enabled.

The earlier build `build/rpi5/run-y09movaa` stopped in TCP cache/input/output on unguarded
MPTCP calls and fields. The multipath control-block accessor is now conditional
on MPTCP rather than referring to a nonexistent field; its unguarded callers
still require review. The shared retransmit-reset macro now retains its two
ordinary TCP resets without calling absent MPTCP code. Window-update and
keepalive multipath callbacks are conditional. Latest build `run-9caclcwh`
confirms those errors are cleared, but remaining TCP cache/input/output paths
still assume multipath state (plus an unused TCP option-parser variable).
Latest build `run-63hdzi60` compiles TCP input with multipath receive/shutdown
paths conditional and ordinary read-wakeup calls retained. TCP cache/output
still fail on multipath references. A fragment test checks exactly one packet
free in the non-MPTCP no-data branch.

Latest build `run-6n7621_x` compiles TCP cache and output. Output's three receive
window branches retain ordinary TCP calculations without multipath state; the
two cache routines called only by MPTCP are conditional on MPTCP. The build now
stops in `tcp_subr.c` and `tcp_timer.c` on further multipath assumptions and an
unused SYN-cookie parameter. All 25 host tests pass; these do not execute the
receive-window or timer algorithms. No fresh final link inventory is
available from those checkpoints.

Latest build `run-7_50pglj` clears the SYN-cookie parameter diagnostic and TCP
lock/unlock/getlock multipath references. Ordinary inpcb mutex operations remain;
parent-socket locking and lock-transition retry are MPTCP-only. Remaining errors
are in socket-buffer space, timer garbage collection and keepalive option paths.
The subsequent `run-zrs_cyn7` compiles those buffer-space, timer and option
paths after making multipath-specific cleanup and callbacks conditional. Ordinary
inpcb disposal and TCP keepalive resets remain. A new test exercises read-probe
keepalive conditions with and without MPTCP; all 26 host tests pass, but they do
not validate the modified lock or garbage-collection paths at runtime.
TCP Prague now compiles with explicit casts preserving its previous float
evaluation. UDP's filter-only locals are conditional on CONTENT_FILTER, and its
NECP multicast-policy variable is declared in the NECP block rather than IPsec.
IPv6 fragment context recovery casts through uintptr_t, matching the save helper.
Latest build `run-5xw31p20` compiles UDP and fragment handling and stops on an
unused `sent` label in `ip6_forward.c`. All 26 existing host tests pass; no
transport/runtime validation or complete kernel link is claimed.

Latest checkpoint `run-7wtr8udq` compiles IPv6 forwarding/output/raw/UDP paths.
The forwarding label follows PF, NECP's skip-IPsec target remains available
without IPsec, and IPsec state cleanup/locals are conditional. Raw IPv6 scope
tracking is independent of content filtering. UDP6's NECP decision variable
is local to its policy check. Compilation now stops in `uipc_socket.c` on
Skywalk statistics override and MPTCP client-UUID helpers. No complete image or
hardware gate is demonstrated; the existing 26 host tests remain narrow checks.
No complete link inventory is
available. Next: review the TCP/MPTCP boundary, then the link/provider audit;
rebuild firehose for final config.

Kernel compilation remains incomplete; the complete artifact, undefined-symbol
inventory, compiler runtime and PRNG/crypto/provider startup closure remain open.
No loader, GICv2/PSCI driver, SD/Ethernet driver or hardware boot is demonstrated.
Gate 1 has not started.

## Reproducibility limits

The installed toolchain is **Xcode 26.6 / 17F113**, SDK 26.5, Apple clang 21.
The accepted canonical pin is Xcode 26.5 / 17F42. All current build evidence is
explicitly marked noncanonical. Tooling rejects that mismatch unless
`--allow-toolchain-mismatch` is supplied and records it when allowed.

The initial sandboxed build could not perform Xcode/host queries. Subsequent
builds used approved host access. The first SDK metadata lookup failure was fixed
by supplying the copied SDK's recorded version and original platform explicitly.

Generated SDKs, sources, objects and run evidence live under ignored `build/rpi5`.
No SD card, Pi firmware, remote repository or installed Xcode SDK was modified.
No downstream Git remote has been supplied, and no changes have been pushed.
