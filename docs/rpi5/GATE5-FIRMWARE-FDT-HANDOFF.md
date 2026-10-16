# Retained firmware FDT → actual kernel PCIe preparation — 2026-10-12

A distinct loader/kernel-component build now connects the original firmware
FDT to the **actual PCIe transport's preparation path**. It does not activate
that path, install an image or constitute an Ethernet milestone. The tested
zsh/socket kernel/root/image and every accepted component remain unchanged.
No Pi, serial, SD, firmware, power, reboot or soak operation occurred. No
current boot/root observation is inferred. Gate 4 remains held separately;
zsh/TTY, Ethernet, SSH, original Apple utilities and recovery stay in scope.

## Loader publication and retention

The existing loader includes the firmware FDT as a live allocation in the real
reservation resolver and handoff planner. All live allocations must be in
reservation-free, mapped Normal RAM, disjoint from the kernel, args, tree and
each other; the greatest live end contributes to `topOfKernelData`. This is
existing planner behavior, not a new allocator claim made by a descriptor.

`firmware_fdt_tree.{h,c}` adds a **32-byte descriptor only** to `/chosen`:
`rpi5-firmware-fdt`. It encodes version magic, original physical address, exact
length and zero reserved flags. It requires exact valid FDT framing/structure,
an initialized three-property chosen node and explicit Normal-RAM coverage.
It uses independent stable property storage, preserving the original three
properties. Invalid geometry/framing/types or a duplicate attachment reject.
No raw FDT, firmware seed value or seed-derived hash is published in this
property. The seeded Apple tree still intentionally receives its existing
separately derived `random-seed`, through the unchanged consume-once callback.

The build patches **copies** of `probe_main.c` and `firmware_seed_tree.c`.
The new flag is default-off and requires the distinct Device-declaration/
terminal transfer profile, excluding storage. Attachment precedes the actual
tree measurement and resolved plan. The copied seed encoder accepts the fourth
property, adds the existing derived seed using a five-element local array and
restores the original property pointer/count. It preserves original source
erasure, scratch clearing and error cleanup. Both copied units are recompiled
with the new flag disabled, and the entire resulting boot binary must equal
the preceding Device-handoff candidate exactly.

The new fixed loader marker is:

```text
RPI5XNU:BL33:FIRMWARE_FDT RETAINED_DESCRIPTOR_ONLY NO_RAW_TREE_OR_SEED_PUBLISHED PCIE_MMIO=0
```

It is not proof of kernel execution, seed qualification, physical retention,
power/clocks, exclusive ownership or PCIe access. The accepted original kernel
and root remain embedded byte-for-byte in this **uninstalled loader candidate**;
that old kernel does not consume the new descriptor. The new kernel component
below must be intentionally integrated into a separate complete kernel before
the end-to-end connection can be physically accepted.

## Actual kernel consumer and private copy

A patched **copy** of real `osfmk/arm/arm_init.c` includes
`rpi5_firmware_fdt.inc`. Before `arm_vm_init`, it reads the chosen descriptor,
decodes it with the same byte-oriented record helper, rejects malformed/version/
flag/length/alignment/overflow cases, and requires the full extent inside the
managed Normal-RAM span and below the retained high-water mark. No source byte
is accessed while interpreting an unchecked descriptor.

After `arm_vm_init`, it independently requires the FDT to start at or after the
**complete kernelcache end**, not merely after `physBase`. This matters because
`arm_vm_prot_finalize` releases pre-kernel and boot-segment memory later. The
loader also rejects an FDT preceding its actual placed kernel end. These checks
keep this view in the retained post-kernel tail, not in reclaimable memory.
Only then is its address translated through XNU's existing **Normal-RAM
physical aperture** with `phystokv`; there is no Device/uncached alias, new
physical descriptor or speculative peripheral read. Metadata and the resulting
view are read-only-late globals, initialized before later IOKit consumers.

`rpi5_firmware_fdt_view` is a built-in private ABI with no registry/syscall/
userland export. It returns a view only after VM setup; invalid outputs or an
absent view leave caller output unchanged. This is a trusted-loader lifetime
contract, not independent firmware attestation or protection from arbitrary
external physical writers.

`BCM2712FirmwareFDT.cpp` then uses **Apple OSData** to make an independent
kernel-owned copy. The actual `fdt_sanitize.c` validates complete framing and
unique chosen seed properties before modifying anything; it requires the
qualified 64-byte `rng-seed` declaration and erases copied `rng-seed`,
`kaslr-seed` and `random-seed` values without changing any resource/property
layout. The original firmware source is never changed by this copy operation.
Parse failure wipes the whole private copy before release. No raw copy or
seed-bearing value is attached to the public IORegistry.

The separately patched real transport adds `prepareBoot(provider)`. It calls
that OSData copy function and passes the result to its **actual existing strict
PCIe/RP1 decoder and Device-mapping preparation**, retaining the sanitized full
tree for later original-option checks. The original atomic preparing-thread/
singleton/provider rules remain. Failed preparation releases the temporary
copy; successful preparation retains it with the owner, with normal pre-claim
cleanup and permanent retention after any watchdog claim attempt. It neither
sets synthetic COMPLETE states nor invokes reset/PHY/UBUS hardware activity.
There is still no boot caller, registration or physical ownership admission.

## Verification and exact artifacts

```sh
python3 -m tools.rpi5.build_firmware_fdt_handoff \
  --output-dir build/rpi5/firmware-fdt-handoff-20261012-final
PYTHONPATH=tools/rpi5/tests:tools/rpi5 python3 -m unittest \
  tools.rpi5.tests.test_firmware_fdt_handoff
```

All **four focused tests pass**. The ASan/UBSan native test executes the actual
record encoder/decoder, tree attachment, reservation resolver, Mach-O/handoff
planner, copied seed transaction and Apple serialization. It checks the exact
descriptor survives encoding, the live source raises the retained high-water
mark, and raw FDT bytes are not embedded in the public Apple tree. It runs the
actual seed sanitizer and strict PCIe decoder, proving unchanged decoded
resources and source bytes, with only the three known copied seed values
changed. It covers all-three versus rng-only seeds, malformed/truncated input,
missing/short rng-seed and duplicate chosen nodes. Record tests cover unaligned
serialization, flags/magic, overflow/size/alignment, bad retention and the
post-kernel tail boundary. These are synthetic native-memory tests, not a Pi
or IOKit-lifetime execution receipt.

Actual A76/XNU-header builds compile the copied early kernel consumer, original
OSData API, copied real transport and sanitizer, then partially link with the
original Apple PCI/resource code, genuine watchdog owner and real PHY/UBUS cores.
The three new/specialized units are warning-free. The copied `arm_init` has one
**existing** `dyld_kernel_fixups.h` unused-`cnt` warning; an independent compile
of the unchanged original source reproduces it, and other warnings reject.
The partial-link undefined comparison admits only the pre-existing family
`___dso_handle` requirement and two `__TEXT,__thread_starts` linker-section
boundary references also present in that independently compiled original
`arm_init.o`. Final kernel linkage still must resolve those normally; no
ignore-undefined/duplicate-symbol option or fake implementation is supplied.

The new loader's reviewed conservative C-frame bound is **12,352 / 16,384
bytes**, leaving **4,032 bytes** without changing the existing reserve. Tree
and runtime-plan stack checks also pass. This is a listed-chain bound, not a
whole-program/interrupt stack proof. Kernel compilation and host models are
distinct from physical execution and recovery acceptance.

All **241 selected regressions pass in 82.286 seconds**, including the new
connection, original seed/reservation/bootstrap/handoff tests, preceding PCIe/
Apple-family/kernel transport work, zsh/socket/root/metadata staging and
recovery guards, and GIC/SGI/topology checks. Final input/output pins and the
tested zsh/socket package's 35-check preflight are independently revalidated.

- Directory: `build/rpi5/firmware-fdt-handoff-20261012-final`.
- Loader: `firmware-fdt.bin`, **19,385,344 bytes**.
- Loader SHA256: `030ebcfd8f108b10d2518349c75fe2f477b911aa6233ddc2a0ac482dd4cd2da3`.
- Kernel component: `apple-bcm2712-firmware-fdt.o`, **884,520 bytes**.
- Kernel-component SHA256: `50f10b890e6f84e74adf7ac8de17b1250b9fbe1548f4625ba6cc6e98424e19e6`.
- Manifest SHA256: `eed613aaa91207b3c6db298fe811e4400bb4dca2d1a7ec8858243f817561b301`.
- **1,245 input + 54 generated hash entries**, 1,294 unique files.
- Preserved kernel/root SHA256s remain `674e6a763a01a7e4becf0399d03641aa4e43ec1c1d995d67623546b9d64f5aad`
  and `3fa5ed9f501cedd744b0d6d75cc0886837db562f3bd42282284d82e2798d9a27`.
- Exact accepted payload is unique and aligned at byte offset `133312`.

Earlier numbered directories preserve development attempts (copy-patch
placement, baseline compiler argument selection, C++ byte-pointer conversion,
and original linker-boundary accounting). Native fixture wiring and negative
profile selection were repaired before the passing tests. No accepted source
or artifact was modified to make those attempts pass. `final` is authoritative.

## Next work

This closes the **implemented raw-FDT-to-prepareBoot connection**, not its
complete-kernel/physical acceptance. Final integration must replace the old
`arm_init.o` and `pe_fiq.o`, intentionally link the family/constructors and wire
an admitted provider/caller, rather than add duplicate old/new definitions.
Genuine power/clock/shared-RESCAL ownership, RP1/DMA quiescence and autonomous
reset/SSD-return admission remain mandatory before destructive operations.
Then connect unused-window checks, RC/windows/PERST/link, original-family
config/BAR/readback, interrupts, DMA and GEM traffic. Working SSH, broader
userland/TTY and durable history are not claimed by this checkpoint.
