# PCIe Device-memory handoff candidate — 2026-10-12

A separate **bootable but uninstalled declaration-only candidate** now adds the
exact Device pages required by the [real kernel PHY transport](GATE5-PCIE-PHY-TRANSPORT.md).
It reuses the physically tested kernel and zsh/socket RAM root byte-for-byte.
It does **not** include/register the new PHY transport, claim its watchdog
lease, touch PCIe registers or establish controller ownership. No Pi, serial,
media, firmware, power, reboot or soak operation occurred for this checkpoint.
Gate 4 durability/history remain held separately.

## Actual loader change

`loader/rpi5/pcie_device_handoff.{h,c}` strictly decodes the full raw Pi 5
PCIe/RP1 profile, then inserts only three ranges into a valid memory-type map:

| Resource | New Device declaration |
| --- | --- |
| Shared RESCAL | `[0x1000118000,0x100011c000)` |
| PCIe2 bridge | `[0x1000120000,0x100012c000)` |
| Reset bank | `[0x1001504000,0x1001508000)` |

These are **five 16-KiB pages**, calculated with the same pure geometry helper
used by the real kernel transport. Logical register offsets remain restricted
by that transport; page typing does not authorize neighboring registers.
Existing Normal and Device records are preserved, without coalescing or
broadening them. Additions reject duplicate/partial overlap, Normal-memory
overlap, bad input maps/FDT, in-place output and insufficient record capacity.
Output is committed only after the expanded map validates completely.

No MIP, RP1 BAR, outbound aperture, DMA RAM, other PCIe controller or blanket
peripheral-bus region is added. No address number or Device type is treated as
power, clock, ownership, bus-master or physical-access permission.

The build applies `tools/rpi5/patches/pcie-device-handoff.patch` to a **copy** of
`probe_main.c`. Its new macro is default-off and is accepted only with the
distinct topology/serial-terminal transfer profile, excluding storage. The
runtime hook runs after the existing Normal/Device map has been filled, before
Apple-tree memory-map encoding and the existing handoff/reservation checks.
The expanded map is used for both Apple-tree publication and the resolved
handoff planner. The candidate emits:

```text
RPI5XNU:BL33:PCIE_DEVICE_HANDOFF RANGES=3 PAGES=5 DECLARATIONS_ONLY PCIE_MMIO=0 IRQ=0 DMA=0
```

This marker alone is **not** successful kernel transfer, actual page mapping,
register accessibility or a physical acceptance receipt. The existing loader
still performs its ordinary UART/PM/GIC/CPU work; “no MMIO” here always means
**no new PCIe/PHY MMIO**, not a globally hardware-free bootloader.

## Build provenance and baseline preservation

`tools/rpi5/build_pcie_device_handoff.py` first reruns the accepted zsh/socket
package's host preflight and verifies its exact manifest/source/output hashes.
The old loader receipt did not hash each object separately, so the new tool
does not simply trust those intermediate objects:

1. Re-link the recorded original objects and reconstruct the entire pinned
   accepted `probe.bin` exactly before reusing them; capture each object hash.
2. Compile the copied main with the patch **disabled**, then re-link/reconstruct
   the entire accepted boot binary exactly again. This is byte equivalence,
   not an inferred source-token equivalence.
3. Compile the enabled main plus the actual new helper, reusing other objects.
4. Audit final ELF/raw ABI, entry, LOAD protections/extents and absence of
   undefined symbols/relocations. Confirm the exact accepted payload occurs
   once at a 64-byte-aligned position and the new declaration marker once.
5. Verify all inputs stayed unchanged; record input/output/log hashes.

The builder never changes the original source, original builder, accepted
objects, package, kernel or RAM root. A new directory is required, and source/
accepted locations are refused. The artifact is named **`handoff.bin`**, with
a deliberately separate manifest schema; the existing socket-package inspector
rejects it. It cannot masquerade as the accepted package for an old installer.
There is **no new staging/reboot command** in this tool.

The accepted source hashes remain:

- `loader/rpi5/probe_main.c`: `018590131f38b7c6397f9518118bdd527f537d920134c1256c5dec9e8daa8861`.
- `tools/rpi5/build_probe.py`: `e8f96974a5c161bbf8d0fb3eb67af272f00268de374980f08d72a1b3c02d019e`.
- Tested zsh/socket `probe.bin`: `f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536`.

## Verification and artifact

```sh
python3 -m tools.rpi5.build_pcie_device_handoff \
  --output-dir build/rpi5/pcie-device-handoff-20261012-final
PYTHONPATH=tools/rpi5/tests:tools/rpi5 python3 -m unittest \
  tools.rpi5.tests.test_pcie_device_handoff
```

All **four focused tests pass**. The ASan/UBSan native test executes the actual
FDT decoder, declaration helper, memory-type encoder, board-tree attachment
and Apple-tree serializer. It locates the exact serialized record and decodes
it through the **real kernel memory-map helper**, then verifies the five pages
are Device, existing RAM stays Normal and neighboring/MIP/RP1-BAR intervals
remain Unknown. The FDT is intentionally four-byte, not eight-byte, aligned.

Negative cases include wrong-lane and malformed/truncated FDT, unchanged output
on failure, invalid maps, overlapping Normal/Device extents, duplicate/partial
additions, in-place output and the 29-versus-30 existing-Device-record capacity
boundary. Actual freestanding builds verify both binary-equivalence passes,
the preserved payload, zero warnings and incompatible-profile rejection.
Stack tests reject missing/duplicate required frames and exhaustion. These are
host tests and real A76 compilation, **not a new board boot or pmap observation**.

The expanded regression invocation passed **207 tests in 79.855 seconds**.
Final revalidation checked all 190 candidate input/generated pins and all 716
preceding PHY-object pins; the accepted zsh/socket image remains byte-identical.

The new hook's reviewed conservative C-frame sum is **12,256 / 16,384 bytes**,
leaving **4,128 bytes** with the existing 512-byte reserve requirement. The
runtime planner, tree and topology stack checks also pass. A preliminary
all-unit sum correctly failed; review excluded only demonstrably unreachable
SD/CPU/reservation/RNG decoder functions, using the existing topology auditor's
FDT/property/translation closure and counting all reachable emitted helper
alternatives together. No stack size/margin was increased. This remains a
listed nonrecursive C call-chain review, not a whole-program/IRQ high-water
proof.

- Directory: `build/rpi5/pcie-device-handoff-20261012-final`.
- Image: `handoff.bin`, **19,384,768 bytes**.
- Image SHA256: `dc5e3e2733da97abd5e38a4a7afe333acc462802dd4e7749a0a39cf430dbaabd`.
- Manifest SHA256: `0066df558ec54cd3932178dd2e1b127cdb6c0dcc5b27ba689e5def09d587bdf7`.
- **167 input pins + 23 generated-file pins**.
- Preserved kernel SHA256: `674e6a763a01a7e4becf0399d03641aa4e43ec1c1d995d67623546b9d64f5aad`.
- Preserved root SHA256: `3fa5ed9f501cedd744b0d6d75cc0886837db562f3bd42282284d82e2798d9a27`.
- Preserved payload SHA256: `c11a86bf08e30afd462036e722f3235e5c7503156db67f08594e5c3745fd2270`;
  offset `132736`, uniquely aligned.

Earlier `first/second` directories remain development artifacts. A test-only
relative include path was repaired. An expanded regression invocation also
exposed an existing `test_tree_handoff` sibling-import dependency; its invocation
uses the existing test directory on `PYTHONPATH`, without editing old tests.

## Next actual integration

The installed/tested image still has its original, narrower memory map. This
candidate closes the **software loader-declaration connection only**. Before
the destructive PHY sequence, provide genuine retained firmware power/clocks,
shared-controller/RESCAL ownership and RP1/config/DMA quiescence, and independently
admit autonomous reset timing and SSD return. Preserve controller 1 accessibility;
never use its shutdown/reset as cleanup. No public/registry boolean may replace
those conditions.

The real kernel PHY object remains separately compiled/uninstalled. Its final
kernel integration still needs intentional provider/FDT handoff, constructor/
catalogue registration, old `pe_fiq.o` replacement and final linkage (including
the original family's DSO requirement). Then continue the actual owner through
UBUS/RC/unused-window checks, windows/PERST/link, original-family config/BAR
assignment and readback, interrupts, DMA and GEM/PHY traffic. Working SSH and
broader userland/TTY compatibility remain in scope; neither networking nor
storage completion has been redefined around this declaration image.
