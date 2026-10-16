# Gate 1 readiness audit

## Update — 2026-09-12: canonical toolchain mismatch removed

`tools/rpi5/inputs.lock.json` now matches the host Xcode/Mac SDK:
`26.6` (`17F113`), so canonical toolchain mismatch is no longer an active blocker
in this environment. `doctor` reports canonical toolchain state once run.

## Update — 2026-09-12: focused host-suite pass

Current state update: `python3 -m unittest discover -s tools/rpi5/tests -v` ran
cleanly with 177/177 tests passing. This confirms the documented host-side toolchain,
loader, and provider contracts still hold after the latest changes, with no new regressions.
No new hardware execution was performed in this checkpoint, and the retained Gate 1
requirement items (canonical Toolchain closure, signed ISA compatibility evidence, and
actual XNU transfer semantics) are still open.

Explicit-map combined board pass: `serial-capture-lwxg9a9y` verifies candidate
`bl33-probe-_nzk33nr` (probe SHA-256
`ad23fbc565ddca7b0c3f184243aa63fa9616edad0b0c69f0f1bdf697a50e9d5b`).
The unseeded tree is 1532 bytes; the seeded tree is 1824 bytes. Full kernel
materialization/readback, source/scratch erasure, boot-data publication/readback/
erasure, all three secondary OFF records and final `STOP BEFORE XNU LOADER`
complete. Linux login follows in the same capture; a subsequent SSH check
confirms root `/dev/nvme0n1p2`. Initial SSH timeout occurred during recovery,
not a failed boot. Capture 2026-09-11 04:03:54–04:05:35 UTC, 54495 bytes,
SHA-256 `ebe822bc2b7802a8ac26a3ce73a78db73ad77dec5f41ce664008bda660193e7f`.
The SD config hash remains `ff9141b6ddca6bc6138f74a26a17fa4064460a46c1ef1e714caeaf5a1fa12090`.
The embedded kernel includes the explicit-map consumer and managed-span guard,
but no XNU instruction executes in this diagnostic: this proves loader-side
publication, not runtime execution of the kernel consumer. Gate completion
still requires the final requirement-by-requirement audit.

Managed-span validation now precedes arm_vm_init: BCM2712 rejects empty,
unaligned, overflowing, out-of-40-bit or non-Normal managed extents. This
addresses arm_vm_init's direct Normal mappings, which bypass wimg_to_pte.
Tests compile the actual guard and cover the selected managed span, RAM-bank
boundaries, the low-memory hole, Device memory, misalignment and overflow.
Exploratory kernel build `run-e08yk7d9` succeeds. This does not validate the
earlier assembly bootstrap (covered separately by loader planning), confer
ownership, or qualify any Device pages. No new hardware pass has run.

Explicit memory-map consumer implementation is now present under BCM2712
guards: arm_init decodes the versioned chosen property before arm_vm_init,
checks Normal records against the accounting envelope, and publishes a
read-only-late map. is_dram_addr queries that map; pmap_map_bd_with_options
and wimg_to_pte reject unknown ranges rather than selecting Device attributes
by default. The parser and loader agree with the independent exhaustive
small-map oracle, including holes and adjacent intervals; 125 host tests pass.
Exploratory kernel build `run-d3himdrg` succeeds (the preceding sandboxed
`run-ruc9ftjc` stopped on denied sysctl reads). This is not yet deployed or
executed. Audit of remaining mapping paths and managed-memory coverage, explicit
device-page qualification, and updated board verification remain outstanding.
Gate 1 remains incomplete; the older no-consumer statement below is superseded
by this implementation, not by hardware proof.

Physical boot-data board pass: `serial-capture-ri8os98r` reports
`BOOT_DATA_PUBLISHED_VERIFIED_THEN_ERASED`, followed by all three secondary
OFF records and final diagnostic stop. Candidate `bl33-probe-8t8s6jks`, probe
SHA-256 `46b0414d517f1130598a25d39aa2a2ea89289aff85bcb134a883eeac4d5803e8`.
SSH verifies recovery to NVMe Linux root `/dev/nvme0n1p2`.
Capture: 2026-09-11 03:45:01–03:46:41 UTC, 54015 bytes, SHA-256
`407074513665fcbeb19190e8ba6f7057b18dfc788568ff599930cfe2318773d4`.

Completion audit still finds the DEVICE-TREE-CONTRACT.md memory-classification
issue unresolved: `osfmk/mach/arm/vm_param.h` defines is_dram_addr using the
single gDramBase/gDramSize envelope. The loader independently validates explicit
Normal-RAM ranges but does not yet communicate them to that XNU consumer.
Passing publication/readback cannot prove this semantic mismatch corrected.
Retain Gate 1 as incomplete pending that contract resolution; XNU has not run.

Boot-data publication is now connected to the guarded seed diagnostic. After
successful seeded encoding/erasure checks it copies the tree and 1152-byte
boot arguments to their resolver-approved physical destinations, performs
volatile full readback, then erases and checks both destinations because this
pass does not transfer to XNU. The source encoded buffer is also erased.
`boot_data.c` checks four-range disjointness and overflow before writing;
post-write readback mismatch clears both destinations. Host sanitizer tests
cover copy contents/canaries and invalid/alias inputs, not hardware bus faults.
124 tests pass; build succeeds. Physical boot-data board evidence is pending.

Real-seed board pass: `serial-capture-e_mscbxi` verifies candidate
`bl33-probe-iu8v67n3`, probe SHA-256
`cce4633bb66feee9492d282208f05c957ba9cda39437b4c95e21c80c07e1f324`.
Firmware version/selection guards passed, a 1684-byte seeded Apple tree was
encoded, source and isolated scratch erasure verified, and encoded tree erased.
Only status/length were logged, not seed values or hashes. Kernel readback,
three secondary OFF checks and final diagnostic stop completed in the same
boot; SSH confirms recovery to NVMe Linux root `/dev/nvme0n1p2`.

Capture: 2026-09-11 03:40:03–03:41:43 UTC, 54716 bytes, SHA-256
`e9665c5090bee5a9120fa9163791d15a067ceab328d539880ba91d5d2c552a3d`.
The approved firmware-trust/derived-entropy contract applies; this is not an
independent entropy-strength measurement. Final physical tree/boot-argument
publication and XNU transfer remain unverified. Gate 1 is not marked complete.

Real-seed diagnostic integration is now connected after successful runtime
ownership/planning, physical readback and synthetic stack self-test. It checks
the pinned firmware identity/timestamp, selects the exact 64-byte rng-seed,
preflights the seeded tree, and calls isolated consume-once through the tree
transaction. It verifies source/scratch erasure and clears the entire encoded
tree before logging status and length only. No seed bytes or hashes are logged.
This diagnostic does not write final boot arguments/tree or enter XNU. Updated
primary-stack checks include seeded-tree encoding and measurement. Not deployed;
hardware proof of actual firmware-seed consumption remains pending.

Synthetic seed-stack hardware pass: `serial-capture-d2b1lhci` verifies
`bl33-probe-urryvlpk` (probe SHA-256
`6c4cb146f5fc6ac3ec030247ee1709deae7a9185d0602e091de86b68c66a8dc7`).
`SEED_STACK_SELFTEST PASS SYNTHETIC_ONLY REAL_SEED_UNTOUCHED` is followed by
full kernel-envelope verification, all three secondary OFF records and the
final diagnostic stop. NVMe Linux recovery appears in the same capture.
Capture: 2026-09-11 03:31:32–03:33:13 UTC, 54325 bytes, SHA-256
`c77c8eb90a70ec663ebae2fcfc5379cd68402ff43c50e94906ad0096a306f2f0`.
This verifies the isolated-stack path with public test data, not real firmware
seed consumption or XNU handoff. Gate 1 remains open.

Combined hardware pass: `serial-capture-gwe10xtg`, candidate
`bl33-probe-55cst4r9` (probe SHA-256
`6e358fd3ce121f00be9ade414e352d7484f480c8564914aafba23cf1e18504a3`),
completes full kernel-envelope readback, three secondary IRQ/OFF checks,
primary IRQ check and `STOP BEFORE XNU LOADER` in one boot. Watchdog recovery
then returns to NVMe Linux, confirmed by SSH root `/dev/nvme0n1p2`.
This supersedes the preceding copy-pass timeout. The full 120-test host suite
also passes. No boot arguments/seeded tree were physically written, no entropy
provider is qualified, and no XNU instruction was executed: Gate 1 stays open.

Capture completed 2026-09-11 02:02:19–02:03:59 UTC, 54238 bytes, SHA-256
`7c152dc35aa3ab0badbf582d795adef3dd0cf293dc1fabe9d82dfece95fe396f`.
Receive-only capture started before the separately requested SSH reboot.

Copy/readback watchdog candidate `bl33-probe-55cst4r9` adds two ordered
checkpoints: after successful materialization/layout comparison/DSB, and after
successful full readback. They share the original pre-hash 60-second deadline
and can reload only the already-enabled full-reset watchdog; RSTC/RSTS and boot
order remain untouched. Completion clears checkpoint access. A stalled copy or
readback receives no periodic renewal. Total authorization is at most 128 hash
renewals plus two checkpoint renewals, with no renewal at/after the deadline.
The hardware's 15-second reload can extend recovery beyond that deadline.
Existing 119 tests and a new sanitizer test of the actual checkpoint function
pass; build passes. Not deployed. Full combined board pass remains pending.

Physical-copy board result: `serial-capture-cx4jeevy` reports successful full
17,252,352-byte materialization/readback for `bl33-probe-ek3gzf8i`, probe SHA-256
`b45dc1c53a2d48e5b288b9dfb481d35ba9ae42b93d8480b0941312cf11d26c50`.
Counter markers at 54 MHz give copy 7.080 s and readback 6.378 s. Readback
completion and `FULL_ENVELOPE_VERIFIED` were observed. Watchdog reset interrupts
the first secondary record afterward; no final diagnostic stop marker or
complete all-core results for this pass. Thus physical loading is verified,
but the combined pass is incomplete. NVMe boot and SSH root `/dev/nvme0n1p2`
confirm recovery. No seed, boot arguments, or XNU transfer occurred.

Capture completed 2026-09-11 01:57:14–01:58:54 UTC, 51338 bytes, SHA-256
`7fd5d53780c2dce389630f95ab8560a3ab50a30e3a09fb08df007499bb0ec599`.
Next: explicitly bounded watchdog servicing for materialization/readback;
retain failure recovery and do not infer a full pass from the earlier core run.

Physical-copy candidate `bl33-probe-ek3gzf8i` now invokes materialization only
after the resolver-backed plan succeeds. The exact kernel envelope is supplied
as destination, while source, scratch and result remain probe-owned. Copied
placement fields are compared with the plan before DSB and volatile full-envelope
readback. Serial counter markers bracket copy and readback. Boot arguments and
seeded tree are still not written and XNU is not entered. Failure stops the pass.
The existing watchdog is not serviced during copy/readback: board timing remains
unverified and a timeout is expected to recover to NVMe rather than claim success.
119 tests pass; the enforced stack review now includes materializer placement,
relocation-validation branches and readback. Build passes. Not yet deployed;
installed SD remains the successful planning-only candidate `bl33-probe-dftpdj6u`.

Physical-load preparation: `rpi5_macho_verify_materialized` now provides
read-only byte verification of the whole planned envelope: file bytes,
segment zero-fill, inter-segment gaps and rounded tail. Volatile destination
reads prevent replacing readback with assumptions about prior writes. It
rejects source/destination aliases and invalid placement before reading.
Targeted sanitizer tests cover copied-byte, zero-fill and tail corruption,
short destination, alias and invalid inputs. It does not synchronize caches,
validate entropy, prove ownership or transfer control. Runtime physical copy
and this verifier are not yet invoked by the probe; deployment remains pending
review of combined copy/readback stack and watchdog timing.

Runtime planner hardware result: `bl33-probe-dftpdj6u`, probe SHA-256
`1dbedc577603a5d40562bad9a619409508463fa9e10c15a6d665a55a265b534a`,
passes in `serial-capture-2nuk1g1k`. Observed kernel header/end
0x7004000/0x8078000, entry PA 0x74c8488, arguments 0x8078000, tree 0x807c000,
top 0xb014000, rounded mapping [0x6000000,0xe000000).
This is planning under the documented DTSpec firmware trust assumption, not
physical materialization or seeded handoff. All three secondary OFF checks and
the terminal diagnostic marker follow; SSH confirms automatic NVMe Linux
recovery at `/dev/nvme0n1p2`. Earlier candidate-only statements below are
superseded for this runtime planner. Gate 1 remains open.

Planner stack review: candidate `bl33-probe-dftpdj6u` adds an enforced build
check for the runtime planner's reviewed C paths, including its primary callers,
Mach-O placement/segments, maximum-depth tree measurement, boot arguments,
memory types and bootstrap checks. Maximum observed sum is 9680 bytes of a
16384-byte stack, leaving 6704 bytes; the check requires an additional 512-byte
margin. Missing/duplicate frame evidence and budget exhaustion fail the build.
118 host tests pass. This is not a whole-program stack proof, but closes the
specific new planner call-chain review. Candidate is not yet deployed.

Runtime planning candidate `bl33-probe-xr35gn3_` now passes the successful
runtime reservation result to the board-tree diagnostic and invokes
`rpi5_resolved_tree_handoff` using the validated embedded kernel. Normal RAM
comes from runtime memory-node ranges under the explicit DTSpec trust contract
in OWNERSHIP-LEDGER.md. Kernel header is 0x7004000, managed window
[0x6000000,0x10000000), boot arguments/tree follow the aligned kernel end.
Actual linker live extent and actual FDT extent are supplied to the planner.
Seeded-tree length is measured without collecting a seed. The candidate reports
destinations and mapping bounds but performs no physical destination writes.

117 host tests pass, including atomic reservation-result publication on
failure; the first build's post-CMA native/Python comparison passes. The final
candidate adds an explicit successful-payload prerequisite before planning.
This candidate is not deployed. The added runtime planner call chain still
needs early-stack review and actual board evidence. Installed SD remains the
previous CPU_OFF diagnostic `bl33-probe-q4xdz_el`.

Latest hardware update: secondary CPU_OFF and primary AFFINITY_INFO checks
pass for all three secondary cores in `serial-capture-fbjnq5um`, followed by
the primary IRQ test, diagnostic stop, and automatic NVMe Linux recovery.
See [transfer evidence](TRANSFER-CONTRACT.md). This closes the normal-path
parked-secondary issue, not restart verification, memory ownership, entropy,
physical materialization or XNU transfer. Gate 1 remains open.

Hardware update: [Apple-tree diagnostic](BOARD-TREE-DIAGNOSTIC.md) now confirms
the runtime builder/measurer/encoder produced 1392 unseeded bytes on the Pi,
followed by all four timer IRQ checks and automatic NVMe Linux recovery. This
supersedes the candidate-only status below, not the open seeded-handoff work.

Runtime tree integration candidate: `bl33-probe-17jfo5uh` adds a diagnostic
call to the actual board-tree builder, measurer and encoder using validated
four-core topology, boot affinity, counter frequency and UART profile. It
requires the observed 8 GiB envelope endpoints but explicitly does not infer
Normal-memory attributes from that envelope. Static tree/encoded buffers stay
inside the ELF live extent; no external physical handoff memory is written.
The tree has no seed and is never passed to XNU. Measured/encoded size agreement
is checked before reporting success. Build, 117 existing host tests and
post-CMA geometry cross-check passed; execution of this new diagnostic is
pending. The previous statement that no board-tree builder is called by the
probe is superseded only for this diagnostic, not for seeded runtime handoff.

Latest evidence: [hardware diagnostic milestone](BOARD-HARDWARE-PROBES-PASSED.md)
records payload validation, runtime reservation checks, EL1 on all four cores,
and timer IRQ delivery on every core, followed by recovery to Linux. This
supersedes the earlier UART/alignment/hash-timeout blockers below. Kernel
materialization/transfer, complete ownership and runtime Apple-tree/seed
integration remain open; Gate 1 is not complete.

Gate 1 is not passed. This is the current implementation/evidence split, not a
replacement for PLAN.md's full exit criteria.

## Current board checkpoint (supersedes historical access notes below)

The user authorized the 119.4 GiB SD card as disposable test media and authorized
SD-first boot with NVMe fallback. June 17 EEPROM is installed and entry placement
at 0x6000000 is observed. Four archived diagnostic runs exist; see
[board-run evidence](BOARD-RUN-2026-09-10.md). The latest run passes FDT framing
after the property-padding compatibility fix, then rejects the nominal UART
rate before reservation, payload, secondary CPU and timer IRQ evidence.

The next candidate is `build/rpi5/bl33-probe-bcb17vfe`, SHA-256
`71afd7f12eb08b55f07ca15e446f50e263fa33f77497f53fa80dfe61eabc0b86`
for probe.bin. It programs an exactly representable baud from the validated
FDT clock and retains strict readback validation; see
[UART correction and limitations](UART-CLOCK-INVESTIGATION.md).
Native embedded-image validation and host-buffer copy agree for all 18 segments
and 93292 relocations. This does not prove physical loading or execution.
Linux SSH is restored on 192.168.4.23, but the latest storage inventory lists
only the working NVMe: SD reinsertion is required before candidate deployment.
The candidate has not been deployed or board-tested.

## Historical implementation checkpoints

Latest kernel update (2026-09-10): BCM2712 DRAM property validation and zero-base
sentinel adaptation rebuilt successfully in `build/rpi5/run-7m63c16f` using the
already-prepared exploratory Xcode 26.6 toolchain (canonical lock remains 26.5).
New kernel SHA-256:
`17313a19494f3f247752a211ca01a97683b07543d42f1a645d47680a91c67a62`.
Native audit/copy cross-check passes: 18 segments, 93292 local relocations,
17252352 materialized host-buffer bytes; entry trampoline unchanged. Earlier
embedded probes contain the previous kernel and are historical evidence only.
The DRAM memory-type/hole contract is still unresolved; see DEVICE-TREE-CONTRACT.md.

Integration checkpoint, 2026-09-10 21:22 UTC: embedded probe
`build/rpi5/bl33-probe-2rycco5k` was re-audited against that new kernel and passed
the actual ELF/container/native-host-copy checks. Its full live extent is
[100663296,118168176), not just the raw binary length. It remains a diagnostic
image with `STOP BEFORE XNU LOADER`; no board execution is recorded.

The composed board tree, seed collector/serializer, exact-length handoff wrapper
and reservation-free-extent wrapper are implemented and host-tested, but not
called by probe_main. This distinction is the current integration boundary, not
an assertion that the wrappers alone close the remaining work below.

## Implemented but not board-verified

- Runtime FDT framing, CPU/PSCI, MMIO translations, fixed UART clocks, timer
  binding, phandle uniqueness and advertised/reserved memory parsing.
- Primary/secondary EL2-to-EL1 normalization, diagnostic vectors/stacks,
  serialized CPU_ON, banked GIC target discovery and one-shot virtual timer IRQs.
- Native Mach-O validation, zero-slide placement/copy/zero-fill, bootstrap
  arithmetic, Apple DT serialization, boot-argument encoding and combined plan.
- Terminal cache-disabled primary transfer assembly, linked but not called;
  see TRANSFER-CONTRACT.md for prerequisites and limits of host evidence.

Runtime inventory calls container integrity and Mach-O segment, symbol and local
relocation validators for an optionally embedded kernel. Materialization and
handoff helpers are NOT called by probe_main.c. Its terminal marker is
`STOP BEFORE XNU LOADER`. Host-buffer materialization and passing host tests
do not establish a bootable image or gate completion.

## Remaining implementation

Runtime reservation error propagation was corrected on 2026-09-10: malformed,
unsupported, capacity, initrd-conflict and no-fit paths now return failure after
printing, rather than returning successful console output as validation success.
The caller stops before subsequent payload/PSCI probes. A host-compiled test of
the actual function exercises seven injected error scenarios with both working
and failed console output; it does not emulate hardware or replace parser tests.

- Carry the implemented versioned, bounded, hash-checked embedded kernel container
  through runtime handoff with firmware provenance and complete ownership checks.
- A complete live-image/firmware ownership map. Resolve the pinned malformed CMA
  encoding without silently discarding it; observe the actual runtime FDT first.
- Pi Apple-tree properties from validated clocks/topology and a qualified fresh
  entropy provider. RNG200 is only an identified candidate.
- Connect complete ownership, tree/arguments and kernel materialization to one
  runtime flow, including cache/instruction visibility and transfer contract.
- Complete Gate 0 startup providers; a successful link does not supply crypto,
  PRNG and other required runtime services.

## Board-run inputs still needed

See [first-board-run procedure](FIRST-BOARD-RUN.md) for the fresh EEPROM/DTB
identity check and execution/recovery prerequisites. The observed boot order
`0xf146` prioritizes the working NVMe over USB and SD; test-media insertion alone
does not select the experiment. Boot selection needs an explicit approved choice.
No EEPROM setting, boot file, physical disk or power state was changed.

Update 2026-09-10: the official probe has arrived and readable stock-firmware
UART10 output was observed through the Ubuntu capture host at 192.168.4.76.
Capture-host permissions and Pi passwordless sudo are verified. See the
[new access/ownership baseline](BOARD-BASELINE-2026-09-10.md). The adapter/wiring
blocker below is historical and resolved; standalone BL33 evidence and designated
test media are still missing. No complete raw boot-log artifact was archived.

Update 2026-09-06: key-based SSH to the running Pi is verified. The user confirmed
the 8 GB SKU, and Linux model/memory observations agree. The official Debug Probe
is ordered but not yet available. See [Linux baseline](BOARD-BASELINE-2026-09-06.md)
for installed EEPROM identity, UART10 mapping and well-formed live CMA properties.
This does not establish standalone firmware FDT contents or serial probe evidence.

Still needed: pinned boot-chain artifacts and a designated disposable boot medium. The Pi's
current root and boot partitions are on NVMe; no SD device was listed in the
2026-09-06 SSH inventory. Do not treat the active NVMe as test media. Adapter,
wiring and the capture-host endpoint are now established as described above;
the earlier Mac inventory is superseded. SSH access alone is not a pre-Linux
serial capture channel.

Fresh Pi storage check at 21:22 UTC still lists only the active 238.5G NVMe
with mounted boot/root partitions, plus loop/zram devices. No removable medium
was present. User selection of disposable test media remains pending; no disk
write or reboot was performed. This blocks board execution, not all local work.

The probe preserves UART registers and prints raw divisors plus declared FDT
clock rates. It now rejects a configuration unless the declared clock and
standard PL011 divisors give exactly 115200 baud, with 8N1, transmitter enabled,
and no loopback or hardware flow control. This conservative exact-match policy
does not accept rounded/nearby rates. It neither programs baud nor verifies
actual clock frequency. The live Linux UART declaration is 44.2368 MHz versus 9.216 MHz in
the pinned fixture. A passing rate-decoding test proves neither effective baud
nor readable output under the selected standalone firmware. Keep this UART
verification requirement open until actual probe evidence is captured.

The nominal check uses `4 * clock / (64 * IBRD + FBRD)`, consistent with the
standard, non-oversampling path in Raspberry Pi Linux's
[PL011 driver](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/drivers/tty/serial/amba-pl011.c).
All arithmetic comparisons use 64-bit products, without rounded-baud acceptance.
The register-model test covers both declared board clocks, fractional divisors,
invalid widths/zero inputs, line format, enable state and flow-control rejection.
A fresh diagnostic BL33 build is `build/rpi5/bl33-probe-1yad0k9d` (2026-09-10);
its 0x200000 load address remains a host build input, not approved board placement.

Host regression check after the Linux-baseline additions: `python3 -m unittest
discover -s tools/rpi5/tests` passed 97 tests (2026-09-06). This covers host
contracts and emitted-code checks, not the hardware exit requirements below.

Before producing a runnable probe medium, review firmware load placement against
the full probe ELF memory extent (BSS and all stacks, not just binary length),
runtime FDT and all other live images. The repeated 0x200000 build address is a
host test input, not an approved physical placement.

## Evidence needed for the actual exit

Runtime diagnostic sequencing now stops on invalid primary EL1/cache/mask state,
unsupported PSCI version or required CPU_ON/AFFINITY_INFO features, secondary
probe failure, and an unverified primary timer IRQ. Unsupported PSCI previously
allowed secondary probing to be skipped while still reaching the terminal stop
marker. A host-compiled test of the actual PSCI orchestration covers version,
feature, console and secondary outcomes, including SMC32 low-word decoding.
This tests control flow, not execution of SMC or interrupt delivery on hardware.
The terminal marker remains diagnostic only, never a Gate 1 PASS marker.

The initial affinity inventory is now a required preflight: the boot CPU must
report ON, and every other enabled CPU must report OFF before any CPU_ON call.
Unknown boot identity, unexpected PSCI states and failed inventory output stop
the sequence. Each secondary still gets its immediate OFF/unused-slot check
before startup, so preflight does not replace the later check. The orchestration
test injects an inventory failure and verifies that no secondary startup occurs;
actual PSCI state reporting remains a board-test requirement.

The masked timer-poll diagnostic also returns a required result now. Invalid
frequency, counter wrap, timeout, inconsistent timer/counter status and failed
console output stop the primary sequence before its IRQ test. A host test
substitutes register accesses in the actual function and checks bounded polling,
deadline arithmetic, disable-before-output and failure propagation. This is a
register model, not hardware timing evidence; the IRQ test remains separately
required even after successful masked timer polling.

Local verification update (2026-09-10): all 109 host tests pass. The memory-type
classifier is checked against an independent page-label oracle for all 729
six-page unknown/normal/device assignments and 105 half-page-bounded queries
per assignment (76,545 comparisons), under address/undefined-behavior sanitizers.
This covers holes, adjacent unmerged ranges and mixed types; it supplies no
firmware provenance and does not integrate a memory-type map into XNU.

The native Mach-O audit also passes against `build/rpi5/bl33-probe-ji3x68h2`
and kernel SHA-256
`17313a19494f3f247752a211ca01a97683b07543d42f1a645d47680a91c67a62`:
18 segments, 93,292 local relocations and 17,252,352 host-materialized bytes.
The embedded container matches, and native/Python planning agrees for the
synthetic layout. These checks do not approve physical placement or establish
a board boot. No physical media, boot configuration or running Pi state was
changed for this checkpoint. Gate 1 remains open.

Archive exact artifact hashes and source/build manifests together with raw UART
logs showing CPU identity/features, EL1 state and timer IRQ delivery for every
enabled CPU, plus runtime firmware/RAM/reservations/clocks and loader handoff
checks. Capture failure cases and reset/recovery behavior. Never archive seed
contents. A partial diagnostic run is useful evidence, not a full Gate 1 pass.
