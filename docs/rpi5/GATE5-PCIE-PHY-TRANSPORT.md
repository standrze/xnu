# Actual kernel PCIe PHY transport — 2026-10-12

Kernel continuation: a separate copied build now wires the actual UBUS/AXI
stage to these same owned PHY sessions and watchdog lease, without modifying
the accepted sources/artifact. See [UBUS artifact and local evidence](GATE5-PCIE-UBUS-TRANSPORT.md).
This still supplies no hardware admission, boot caller or full kernel link.

Loader continuation: a separate **uninstalled** exact-page declaration candidate
now implements the required memory-type handoff, with unchanged kernel/root and
byte-identical disabled-patch replay. The currently installed/tested image still
has its narrower map; no PHY access or power/clock/recovery admission is implied.
See [Device-handoff artifact and tests](GATE5-PCIE-DEVICE-HANDOFF.md).

This is implemented kernel mapping/MMIO code and a separately compiled object,
**not an installed driver, admitted hardware trial or Ethernet milestone**.
The physically proven zsh/socket image is unchanged. Fresh read-only SSH to
`sandrzej@192.168.4.23` returned **No route to host**; current OS/root is unknown.
No serial, media, power, firmware, reboot or soak operation was performed.

## Implemented connection

`iokit/Kernel/BCM2712PCIePHYTransport.{h,cpp}` supplies the actual IOKit memory
descriptors, mappings, volatile register callbacks, barriers and kernel timing
used by the existing initial reset, shared RESCAL and SerDes/MDIO cores. It
does not supply success callbacks or fabricate COMPLETE prerequisite states.
`runInitialPHY` executes these actual implementations in order:

1. Attempt the irreversible [kernel watchdog ownership claim](GATE5-PCIE-WATCHDOG-OWNER.md).
2. Initialize/pulse bridge reset **44 only** using real SET/CLEAR/status accesses.
3. Initialize/run the real shared RESCAL calibration, retaining the singleton.
4. Initialize/run the real fixed 54-MHz SerDes sequence and its eight MDIO writes.
5. Check the lease again; publish the combined observation only on full success.

The preparing thread owns all later calls. Atomic preparation prevents reuse
and competing preparation on the same instance. A global atomic singleton
rejects another instance, and the actual provider is retained/opened without
seizing an existing owner. These software mechanisms do **not** prove exclusive
physical access by arbitrary code, nor power/clock accessibility.

Before even attempting a watchdog claim, preparation uses the strict original
raw-FDT decoder and maps only these fixed resources:

| Resource | Logical CPU physical extent | Actual rounded Device pages |
| --- | --- | --- |
| PCIe2 | `[0x1000120000,0x1000129310)` | `[0x1000120000,0x100012c000)` |
| Shared RESCAL | `[0x1000119500,0x1000119510)` | `[0x1000118000,0x100011c000)` |
| Reset bank | `[0x1001504318,0x1001504348)` | `[0x1001504000,0x1001508000)` |

The existing real `rpi5_physical_memory_type` kernel ABI must classify **every
rounded page as Device**, otherwise preparation rejects before mapping. Its
declaration/definition and the actual descriptor/pmap sources are pinned in the
build receipt. Descriptors use host-only/no-mapper/inhibited-cache options;
maps use inhibited cache. XNU's existing descriptor/pmap implementation maps
non-DRAM `VM_WIMG_IO` as Device, not ordinary RAM. No blanket peripheral mapping
or DMA descriptor is introduced. Rounded neighboring bytes are never allowed
by the callback access policy.

`BCM2712PCIePHYPolicy.h` is the same allowlist used by the kernel implementation
and native tests. Only aligned **32-bit** accesses are admitted:

- Reset phase: read `0x20`, write `0x18/0x1c` with exactly `0x1000`.
- Calibration phase: read/write START `0`, read STATUS `8` only.
- SerDes phase: `0x4304/0x184c/0x1100/0x1104`; `0x1108` read-only.
- Empty/prepared/complete/failed phases: no register access.

Each actual register access has watchdog checks before/after, `dmb osh` before
the volatile load/store and `dsb sy` afterward. Target assembly contains real
`ldr w`/`str w` operations. Ordering/time/delay callbacks also check the lease;
delays are restricted to 1–100 us and use the real `IODelay`. This is not
halfword/byte configuration-space support; that remains in the separate
configuration core and needs its concrete owner wiring.

## Lifetime and failure rules

Before attempting the claim, the object self-retains. Success **and failure**
keep it, the singleton, provider and mappings pinned until reset. This is a
short, one-shot diagnostic, not a production network-service lifetime policy.
Ordinary reference release can clean up only pre-claim preparation; after a
claim there is no unmap, provider close, lease release/reload or cleanup MMIO.

An owner-thread callback error quarantines all local sessions. Foreign-thread
calls reject without modifying owner state or doing MMIO. A failed write may
already have taken effect; combined output remains unchanged on failure.
No retry, controller shutdown, power/clock write, config selector, BAR,
interrupt delivery or DMA operation is exposed by this transport.

**Fault limitation:** a volatile access can abort or hang rather than returning
an error. Provider arbitration can also block. Pre/post guards cannot interrupt
those operations. Autonomous watchdog reset timing and its next boot destination
still require independently admitted physical evidence; finite code/tests do
not establish them. No registry property or public boolean stands in for that
admission.

## Verification and artifact

Build command:

```sh
python3 -m tools.rpi5.build_pcie_phy_transport \
  --output-dir build/rpi5/pcie-phy-transport-20261012-final
python3 -m unittest tools.rpi5.tests.test_pcie_phy_transport
```

All **four focused tests pass**. The full selected regression set, including
these four and the existing zsh/socket, original PCI, watchdog, bring-up,
metadata, installer and CPU/IRQ checks, passes **193 tests in 59.604 seconds**.
Native ASan/UBSan execution covers exact page
geometry, failure-output preservation and an exhaustive phase/bank/offset/
width/direction allowlist scan. A second native model runs the **real reset,
RESCAL, MDIO and SerDes implementations together**, through that allowlist,
and injects all **206 pre/post-guard failure positions** on its immediate-DONE
path. This includes a failure after a modeled write took effect and rejection
of further modeled I/O. Existing individual-core tests separately cover polling,
timeouts, backward/stalled clocks and other failure paths.

These are callback models, **not execution of IOKit mapping/provider lifetime
on the board**. The kernel unit is checked by real compilation/linkage and
target assembly inspection, without fake IOKit/PM implementations or headers.
Opt-in-disabled, non-DEVELOPMENT and non-BCM2712 compilations reject. Existing
output directories and accepted dependency/source locations are refused.

All eight new compilation units compile with **zero warnings**, using the
recorded actual A76/XNU C and C++ commands. The combined relocatable object
reuses the pinned original-family resource object and actual PM owner object:

- Directory: `build/rpi5/pcie-phy-transport-20261012-final`.
- Object: `apple-bcm2712-pcie-phy-diagnostic.o`, **852,256 bytes**.
- Object SHA256: `3354f5161deb3a4878e3417109a5f5af2b8f728923763ac91b1c7583767aaeaa`.
- Manifest SHA256: `bef1c4f8e022c6512628613b1d3a696985bb70dfc4b361399e5e53dab22bd731`.
- Assembly SHA256: `975529cf48951395bf171ae74c202f4a80931189efb595dadd200f617a7d07cb`.
- **715 input pins**; 536 undefined symbols, only existing family `___dso_handle`
  absent from the reference kernel. This is **not** a final kernel link.

The final link must replace the old `pe_fiq.o` with the patched owner, not add
both definitions or suppress duplicate symbols. The PCI family and transport
still need intentional built-in constructor/source/catalogue registration.
Earlier `first/second/third` directories are retained experiments, not current
accepted source-pin receipts. During development a private-header visibility
failure was resolved using the exact existing built-in ABI; test-only syntax
flags, temporary-path canonicalization and the modeled guard-count assertion
were corrected before the passing focused run.

## Remaining path to actual Ethernet

The accepted loader currently declares UART/PM/GIC and optional SD Device
pages, **not these PCIe/reset/RESCAL pages**. Consequently this new transport
deliberately cannot prepare against the current handoff. A distinct opt-in
loader package must add precisely validated Device extents; never weaken the
memory-type check or expand accepted baseline mappings in place.

Before any `runInitialPHY` call, close actual controller/shared-resource
power/clock ownership, RP1/config/DMA quiescence and autonomous recovery/SSD
return admission. Do not infer those from software state, FDT numbers, provider
open, SSH failure or a previous reset. The
[Raspberry Pi controller reference](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c)
specifically warns that powering down controller 1 can prevent shared RESCAL
access. This transport never powers it down. Reset offsets/bit selection were
checked against the
[original reset-controller reference](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/reset/reset-brcmstb.c).

Then extend the actual owner through UBUS/unused-window quiescence, RC/window
programming, bounded PERST/link training, original-family config/assignment/
BAR readback, IRQ and DMA ownership, and GEM/PHY Ethernet traffic. Simply
linking the original PCI family here does not attach this transport to its
abstract config/resource adapters or authorize enumeration. Preserve the
original SSH/userland workstream and the separate Gate 4 hold. No terminal,
networking or storage completion criteria have been reduced.
