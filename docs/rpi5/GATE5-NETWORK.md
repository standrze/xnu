# Gate 5: PCIe/RP1 Ethernet resource groundwork

2026-10-12 newest continuation: the actual IOKit owner now composes the real
prior chain, RC/windows, bounded link training and post-link CLKREQ, with true
LE16 MMIO, guarded long waits and fresh pre-release unused-window inspections.
Five focused tests and a distinct complete kernel/native loader validation pass;
12,806 modeled owner-guard and 12,810 provider-failure positions are covered.
All 2,380 pins revalidate. No concrete lifecycle provider/personality/boot caller
or physical activation is added: inherited power/clock/shared ownership,
IRQ/endpoint/DMA quiescence and autonomous recovery remain required. Next close
that provider/access/recovery evidence, package/preflight, then actual RP1
config/BAR/IRQ/DMA/GEM/packet validation. No Ethernet or SSH acceptance claim.
[Actual controller integration and its remaining boundary](GATE5-PCIE-CONTROLLER.md).
All **268 selected regressions pass** in 137.465 seconds with localhost access.
Prior pins and 35 unchanged tested zsh/socket checks also pass; not board proof.

2026-10-12 newest continuation: the actual owner now applies the firmware's
no-L0s advertisement setting before link training. The new clock core also
implements all post-link CLKREQ modes, retaining absent/default semantics and
keeping root ASPM/clock-PM disabled. Five focused tests, a separate complete
kernel and native real-loader host-buffer validation pass; 2,343 pins and the
unchanged proven zsh/socket package revalidate. Post-link clock is compiled,
not transport-wired; genuine lifecycle/quiescence/recovery admission and real
RC/windows/link still precede activation, then config/BAR/IRQ/DMA/GEM. No NIC,
physical admission, installed image change or board action is claimed.
[Clock policy implementation and remaining integration](GATE5-PCIE-CLOCK.md).
All **263 selected regressions pass** in 116.236 seconds with localhost access;
this is not physical packet/driver acceptance.

2026-10-12 newest continuation: full original firmware options are now checked
before real provider/mapping preparation, and the actual owner applies the
stock tree's VDM QoS map after its existing PHY/UBUS/unused-window chain. FIFO
and no-map paths are also implemented. Six focused tests and a distinct complete
kernel link pass; no physical activation, inherited-domain/recovery admission,
RC/link/IRQ/DMA or Ethernet claim. CLKREQ/ASPM remain retained declarations
for the next link-policy integration.
[Source, artifact and next steps](GATE5-PCIE-PROFILE-QOS.md).

2026-10-12 latest integration: original Apple PCI/FDT/watchdog components now
link in a complete separate kernel, and the actual PHY/UBUS transport adds a
guarded read-only inspection of unused inbound/outbound windows. Six new
focused tests and native real-loader host-buffer validation pass. This does
not activate a provider or authorize power/clocks, IRQ/DMA, RC/windows/link or
Ethernet; the proven serial-zsh/socket image remains untouched.
[Complete link](GATE5-PCIE-KERNEL-LINK.md),
[unused-window implementation and next provider requirements](GATE5-PCIE-UNUSED-WINDOWS.md).
The entries below are earlier checkpoints, not fresh hardware observations.

2026-10-12 config continuation: true-width serialized root/RP1 configuration
now connects through an abstract subclass to Apple's original IOPCIBridge
API. A76/family relocatable linkage and all 140 selected regressions pass;
no concrete provider/hardware attachment/BAR/DMA/NIC claim. An independently
validated fresh Linux RP1 reference is available after verified SSD return.
[Config implementation, evidence and actual-provider boundary](GATE5-APPLE-PCI-CONFIG.md).
No SD mount/write, serial/power/firmware/reboot or soak operation occurred.

2026-10-12 full-family header integration: all eleven source entries of the
original Apple PCI kext target compile against actual Pi XNU headers, with
actual IIG output and a separate narrowly adapted bridge copy. Relocatable
linkage passes; final kernel/constructor/family attachment remains unproved
(`___dso_handle` unresolved against the reference kernel). All 135 selected
regressions pass. **No RP1 enumeration, DMA authorization or Ethernet claim.**
[Original reuse, patches and backend sequence](GATE5-APPLE-PCI-BUILD.md).
Pristine source and accepted boot images are preserved; no board operation.

2026-10-12 Apple reuse continuation: the original pinned `IOPCIRange.cpp` and
range declarations now cross-compile unchanged for A76 with a small fixed-RP1
policy adapter. The actual Apple allocator handles three BAR candidates and up
to eight PCI-space reservations; 4,096 sanitized fragmentation cases and all
130 selected regressions pass. A composed relocatable object has no runtime
dependencies. **Not BAR assignment, a whole IOPCIFamily kext or physical NIC
integration.** [Source, artifact and provider boundary](GATE5-APPLE-RANGES.md).
Existing access/recovery admission still precedes hardware use. Fresh SSH has
No route to host; serial/media/power and accepted images are untouched.

2026-10-12 RC continuation: the actual window programmer is now invoked by a
new root misc/class/endian/16-bit ASPM/clock-PM setup core; link startup requires
the same completed RC session. Sanitized RC/window/UBUS/link composition and
146 new callback-failure positions pass, with freestanding A76 combined linkage.
Not in a boot image/hardware-wired or a trained link/NIC claim. Provider,
unused-window and safe reset-destination admission remain. [RC checkpoint](GATE5-RC.md).
Follow the user's explicit Apple-reuse preference: original IOPCIFamily and
IONetworkingFamily for compatible generic infrastructure, labeled board backend;
original ifconfig/route are already prepared in an unstaged Pi RAM root.
[Apple-source reuse](GATE6-APPLE-TOOLS.md).

2026-10-12 actual-access continuation: a distinct standalone A76 candidate now
contains real register-load leaves, a two-pass fixed read allowlist and actual
early FDT/primary/PM/fatal-watchdog handling. All 15 local package checks and
92 selected regressions pass; **no installation or physical success is claimed**.
Reset destination/rollback remains an explicit admission gap, not an assumed
automatic SSD return. [Actual-access candidate and next boundary](GATE5-ACCESS.md).
Known-good zsh is unchanged; no board/serial/media/firmware operation occurred.

2026-10-12 link continuation: a fixed Gen2/x4 one-shot link-start component now
checks RC prerequisites, performs 16-bit target-speed access, disables CLKREQ
overrides, releases PERST#, measures settling and bounds link polling. Sanitized
models cover all 21 link-arrival paths and 1,701 callback-failure positions;
A76 compilation and all 90 selected regressions pass. It is not hardware-wired
or a trained-link/NIC claim. [Link setup and remaining provider boundary](GATE5-LINK.md).
The known-good zsh package is unchanged, still passes all 37 checks, and no
serial/media/power/firmware operation occurred. Gate 4 remains independently held.

2026-10-12 window continuation: a pure FDT-derived encoder and actual callback
programmer now cover three inbound and two outbound slots. The known four-byte
outbound decode excess requires explicit acknowledgement; hardware permission
does not extend with it. Quiescent/RC/PERST guards, ordered readbacks and final
verification are host-tested, including all 112 callback failures. The real
access/provider lifecycle and unused-slot safety are still unfinished; no link,
DMA or NIC claim. See [window checkpoint](GATE5-WINDOWS.md). No board operation.

2026-10-12 SerDes continuation: bounded port-0 MDIO and the fixed 54-MHz
BCM2712 setup are implemented, with actual MDIO-core composition and prerequisite
calibration/reset checks. All 27 focused host tests pass. These components are
not hardware-integrated; no trained link, RP1 enumeration or Ethernet claim is
added. Next close the real provider and compose RC/window/PERST/link setup.
See [SerDes checkpoint](GATE5-SERDES.md). No Pi, serial, media or VM operation.

2026-10-12 continuation: shared RESCAL calibration is now implemented in
`pcie_rescal.{h,c}`, with bounded monotonic polling, preserved unrelated bits,
exclusive-provider claim, readback checks and quarantine. Sanitized host models
cover every callback failure across all poll paths; an A76 freestanding compile
passes. It is not wired to hardware and does not establish a trained link or
working Ethernet. See [shared calibration lifecycle](GATE5-BRIDGE-LIFECYCLE.md).
The remaining power/clock/Device-access provider and SerDes/link work continues
independently of the held SD durability gate.

2026-10-12 15:39 UTC: the next initial bridge-reset component is implemented
and host-tested in `pcie_reset.{h,c}`. It targets only FDT reset 44 with bounded
assert/release/status phases and quarantines errors without retry or rollback.
It is not wired into BL33/XNU and performed no hardware reset. See the
[bridge lifecycle contract](GATE5-BRIDGE-LIFECYCLE.md) for mapping proposals,
verified register-layout differences, shared RESCAL ownership, and the remaining
power/clock/SerDes/link sequence. Ethernet remains unproven; Gate 4 stays blocked.

## Accepted scope and ownership

2026-10-12 continuation: the user explicitly authorized independent Gate 5
development while Gate 4 durability is held. This main thread remains the sole
board/serial/media owner. The host-only observation work below adds no board
operation and does not require writable storage. The earlier ownership split
below describes how the original helpers were developed, not a requirement to
wait for Gate 4 completion before continuing networking.

The first independent Gate 5 milestone is a freestanding, read-only decoder of
the Pi 5 PCIe/RP1 Ethernet resource binding. The next host-side milestone is a
pure resource planner using a separately observed RP1 BAR1 assignment. This
thread owns `loader/rpi5/pcie_fdt.{h,c}`, `loader/rpi5/pcie_resource_plan.{h,c}`,
their focused `tools/rpi5/tests/test_pcie_*.py` checks, and this file. Gate 4
storage work owns the shared build, loader integration, kernel, plan/status
files, boot media, UART, and physical board. These helpers perform no MMIO,
PCI configuration writes, clock/reset changes, DMA, packet transmission, or
kernel attachment.

The existing generic `rpi5_fdt_reg` accepts simple buses only. PCI child
addresses have three cells, including address-space flags, so treating the
RP1 GEM `reg` value as a CPU physical address would be incorrect. This decoder
must retain the distinction among CPU MMIO, PCI memory, RP1-local offsets, and
DMA addresses. Static bridge windows are candidates; only live enumeration can
identify the actual RP1 BAR assignment. The [Raspberry Pi Linux RP1 PCI
driver](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/mfd/rp1.c)
uses BAR1 for its peripheral MMIO and matches PCI vendor/device `1de4:0001`.

## Source binding used for host verification

The optional pinned firmware DTB is
`build/rpi5/bcm2712-rpi-5-b-2768f610.dtb`, SHA-256
`399caff4dcf03c55e20b6a4a7907dd8bd1c0cc42a9fc79e0b3b2ad4f7511585a`.
Its enabled PCIe host is `/axi/pcie@1000120000`, with `linux,pci-domain = 2`.
Its `msi-parent` points to `/axi/msi-controller@1000130000`; the other two
PCIe hosts are disabled in this image. The child `rp1` bus maps its local
`0xc040000000` aperture to PCI memory, and `ethernet@100000` declares a
`0x4000` register span, interrupt `<6 4>`, and the `raspberrypi,rp1-gem` /
`cdns,macb` compatible strings. The GEM's offset in the RP1 aperture is
`0x100000`. The MIP `reg` property's first extent is CPU MMIO at
`0x1000130000`; its second extent is a PCI MSI target address at
`0xfffffff000`, not CPU MMIO. These are declarations in a pinned file, not
proof of the actual 8-GB board's handoff, link state, BAR assignment,
interrupt delivery, or DMA coherency. The saved filtered Linux tree omits
`/axi` and cannot establish
those facts either.

The binding interpretation follows the [Devicetree Specification's `ranges`
and `dma-ranges` definitions](https://devicetree-specification.readthedocs.io/en/stable/devicetree-basics.html#ranges)
and [Raspberry Pi's BCM2712 PCIe/MIP source description](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/arch/arm64/boot/dts/broadcom/bcm2712.dtsi).

## Implemented and checked on the host

`rpi5_fdt_pcie_rp1` decodes this exact enabled Pi 5 binding into typed
resources. It validates PCI and RP1 address spaces, complete parent `/axi`
translation coverage, interrupt and MSI phandles/ranges, reset provider cell
widths, RP1 clocks, and the GEM/PHY path. It rejects unsupported IRQ override
properties and malformed, ambiguous, disabled, overflowing, or truncated
inputs without changing its output. The returned GEM and clock addresses are
**RP1 BAR offsets**; no BAR is assigned or mapped. The returned DMA windows
are declarations only, including a separate MIP MSI target alias; they do not
grant buffer ownership, coherency, or permission to initiate DMA.

Run `python3 -m unittest tools.rpi5.tests.test_pcie_fdt -v` for the three
focused checks: a mandatory synthetic DTB with negative topology cases, an
A76 freestanding compile, and a hash-pinned firmware DTB decode with mutation
checks under ASan/UBSan when that optional local artifact is present. These
are host checks, not physical Pi evidence. The decoder is now compiled into
BL33 only with the separate `--gate5-pcie-topology` opt-in described below;
it is not in the XNU kernel and has not run in the Pi's standalone handoff.

`rpi5_pcie_resource_plan` is the next pure step. Given that decoded binding
and a **separately verified PCI bus address** for RP1 BAR1, it validates the
RP1 identity, memory decode state, BAR size/alignment, whole-BAR containment
in exactly one nonprefetchable host window, 40-bit CPU bounds, and GEM/clock
register plus 16-KiB page extents within BAR1. The FDT's declared `0x410000`
RP1 aperture can extend beyond BAR1; requiring that whole aperture to fit in
BAR1 rejected the read-only Linux observation of a `0x400000` BAR1. The
planner returns proposed CPU physical spans
without touching hardware. The FDT's zero PCI base describes a static child
aperture; it is not a live BAR value. The Linux `pci_resource_start(pdev, 1)`
value is already a host resource, so it cannot be used as the planner's PCI
bus base. A caller must also verify that the bridge actually programmed the
outbound window. The tests use a synthetic FDT with the BAR1 base and size
reported by the storage thread's read-only Linux capture on 2026-10-12;
the synthetic tree is not a runtime FDT snapshot. Run
`python3 -m unittest tools.rpi5.tests.test_pcie_resource_plan -v` for the
ASan/UBSan translation and rejection checks, the A76 freestanding compile,
and an optional hash-pinned comparison of the saved Linux PCI/FDT reference
with the pinned firmware DTB.
No boot or kernel caller uses this planner yet.

## Read-only Linux reference and Gate 5 continuation

While retaining exclusive board ownership, the Gate 4 writer saved one
read-only Linux capture at
`build/rpi5/rp1-linux-reference-20261012/reference.json` (SHA-256
`ece8b18da3d1b863800e4973cbb5f544c7ef3896a64b12742a0903cd8bda27bf`).
It records the 2026-10-12 00:31:46 UTC NVMe Linux root, kernel
`6.18.34+rpt-rpi-2712`, and RP1 PCI function `0002:01:00.0` with ID
`1de4:0001`. PCI command `0x0406` has memory decoding enabled. Raw BAR1
config is zero, yet Linux assigns BAR1 the CPU range
`[0x1f00000000, 0x1f00400000)` (4 MiB). This is a valid BAR base-zero
assignment, not an unassigned device. Raw BAR2 is `0x400000`; its Linux CPU
resource is `[0x1f00400000, 0x1f00410000)`. Those adjacent resources are
consistent with the FDT's `0x410000` RP1 range spanning BAR1 and BAR2. The
host planner now accepts this layout and derives GEM
`[0x1f00100000, 0x1f00104000)` and
clocks `[0x1f00018000, 0x1f00028038)`; the clock page mapping ends at
`0x1f0002c000`.

Twenty-seven captured PCIe/RP1/MIP/GEM property values match the pinned
firmware DTB byte-for-byte. The capture contains only five FDT nodes, lacks
the root/`/axi` dependencies for a full live decoder pass, and has no boot ID.
The storage writer's `revalidation.json` (SHA-256
`070f53f4eb40851f1274e3a6b8621d26456910567188aab3ff89a5bd81bc931b`)
matches its PCI header/resources and selected FDT properties and has a stable
boot ID around that later check; it cannot retroactively bind the first
capture to the same boot.
It reports a 32-bit Linux DMA mask, 61 MSI-X entries, and an `eth0` platform
device whose state was `down`. These facts are a **Linux reference**; they do
not prove XNU bridge programming, interrupt delivery, DMA coherency, link, or
packet traffic. No second board session was run by this thread.

These host helpers do not enumerate RP1 or attach a NIC. The next implementation
steps are PCIe bridge bring-up and configuration-space enumeration, MIP MSI and
RP1 interrupt routing, RP1 clocks/resets, DMA address translation/cache policy,
then GEM and IONetworkingFamily integration. These need separate design and
hardware evidence before any claim of working Ethernet.
PHY reset GPIO behavior, a live MAC address, link state, and packet DMA remain
unproven by this host work.

## Implemented bounded PCIe observation core — 2026-10-12

`loader/rpi5/pcie_observe.{h,c}` adds a freestanding callback-based observation
of bus 1/device 0/function 0. It requires a caller-owned, already safe BCM2712
bridge Device mapping and exclusive selector/lifecycle ownership. Before
selection, every config read, and final publication it checks RC role,
`DL_ACTIVE`, `PHYLINKUP`, and absence of L23. It rejects all-ones status.
The only write callback may select `0x00100000` at bridge offset `0x9000`;
an explicit ordering callback and selector readback precede header reads at
`0x8000`. There is no generic register-write/config-write interface, reset,
link training, BAR sizing/assignment, bus-master enabling, DMA or RP1 access.
Callbacks must return within a caller-enforced bound.

Two 64-byte header passes must agree on identity, revision/class, header type,
command and BARs. The supported profile is RP1 `1de4:0001`, Ethernet class,
type-0 header and three independent nonprefetchable 32-bit memory BARs. It
preserves volatile PCI status separately from stable resource checks. Output
commits only on success; errors stop without retry, but the selector side
effect is not rolled back. A zero BAR1 base is retained as zero, not labeled
unassigned. Assignment, size, programmed outbound translation, DMA permission
and coherency are intentionally absent from the result.

All register/binding facts were verified against the primary
[Raspberry Pi Linux BCM2712 controller source](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c)
on 2026-10-12; algorithms and the failure/publication contract are independently
written. Link checks cannot eliminate an asynchronous link-loss CPU abort,
prove the bridge accessible, or replace fault handling. This core is **not yet
wired into BL33 or XNU**; no hardware access occurred during this continuation.

`python3 -m unittest tools.rpi5.tests.test_pcie_observe -v` passes two checks:
ASan/UBSan model coverage of exact callback ordering, each of 69 callback fault
positions, link loss before each config read/final check, invalid identity/BAR
profiles, selector mismatch, stable-field changes and unchanged error output;
and a freestanding Cortex-A76 object with zero undefined symbols. Together with
the FDT/planner/GEM checks, 10 focused tests pass. The Linux-derived header
fixture is a host model, not a new XNU runtime snapshot.

Next integrate only after bridge mapping/lifecycle safety and bring-up are
established. A bounded diagnostic image should capture runtime FDT, bridge
status and config observations before allowing any RP1 mapping. Then verify
outbound windows, BAR assignment/size, MIP/MSI-X/RP1 routing, clocks/reset and
DMA/cache contracts before MAC/PHY and independent packet tests.

Runtime wiring remains with this thread's sole Pi/build owner. The next board
dependency is a separately packaged, bounded XNU PCIe bridge-state and
configuration-space observation; the Linux resource allocation alone cannot
show what a standalone loader programmed. The [Raspberry Pi Linux BCM2712
controller driver](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c#L834-L860)
checks `DL_ACTIVE` and `PHYLINKUP` at bridge offset `0x4068` before accessing a
downstream function. Even a PCI config *read* then writes an ECAM selector to
`EXT_CFG_INDEX` at offset `0x9000` before reading `EXT_CFG_DATA` at `0x8000`
plus the register offset. For RP1 bus 1, device/function 0, the selector is
`0x00100000`; the PCI domain is not encoded. These registers fit the decoded
bridge extent at CPU base `0x1000120000`. This selector write is distinct from
a PCI config write, but it still needs explicit hardware-trial ownership and
a confirmed accessible, trained bridge. Linux's [probe and setup
sequence](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c#L2300-L2396)
enables clocks, handles resets, programs windows and starts the link before
enumeration; the BL33 handoff state is unverified, including whether it is
safe to read bridge status. A fuller property-allowlisted live FDT would also
allow the decoder to run against runtime topology. Any such capture
must exclude `/chosen` identity/seed properties before reading or transmission
and record a boot ID to bind observations to one Linux boot.

## Live Linux topology reconciliation and loader integration — 2026-10-12

`capture_pcie_reference.py` is plan-only by default. Its separate `--execute`
mode performs one SSH operation to the exact authorized Pi and reads only the
standard 64-byte RP1 PCI header, assigned resource list and 12 explicitly named
OF nodes/property allowlists. It follows the stable `/proc/device-tree` ABI,
not the raw complete firmware DTB. `/chosen`, seeds, serial numbers and MAC
properties are never requested. It reads every allowed property twice,
preserving missing properties as null and retaining unsupported IRQ overrides
so filtering cannot turn those overrides into a supported binding. It requires
the exact SSD Linux root/hostname and matching boot/kernel identity around both
identical snapshots; source drift or unknown timeout fails without retry.

One actual capture completed at 2026-10-12 14:28 UTC in
`build/rpi5/rp1-topology-live-20261012`. The before/after boot ID was
`36ac234c-2a31-4b30-bb5d-de87fa5bd8e2`. Its native ASan/UBSan checker accepted
the filtered topology with the existing C decoder and reconciled the raw BAR1
PCI base zero, Linux-assigned 4-MiB size and CPU base `0x1f00000000` with the
FDT resource planner. GEM is `[0x1f00100000, 0x1f00104000)`; clocks are
`[0x1f00018000, 0x1f00028038)`, RP1 IRQ is 6, PHY address is 1.

Immutable artifact hashes:

- `remote.stdout`: `05481b30cc9a9a735863bc85307fe75e088f00ce630058bbb59a2391ed54ce3c`.
- `filtered-topology.dtb`: `ab673a783d7bd7f58fd5b905f0c0e9bc954e8a0ff6cc797de969acea2b88c6bf`.
- `result.json`: `9669fdf6ae12c595a2a272a3f9c5830ad722c52f0c92b94e18f8a4ddf59f6be3`.

This replaces the earlier missing-parent limitation **for the filtered Linux
decoder comparison only**. It does not turn the earlier five-node capture into
a complete snapshot, establish uniqueness among omitted phandles, close external
clock/IOMMU bindings, establish original firmware/XNU handoff state, or grant
MMIO/DMA permission. The reconstructed DTB has no RAM reservations or unrelated
devices and **must never be used as a boot DTB or memory-allocation input**.
No direct MMIO, PCI configuration write, SD operation, network change or reboot
occurred. Kernel internals may use a config selector to service ordinary PCI
header reads; this is distinct from changing PCI configuration.

The opt-in loader hook `rpi5_pcie_topology_log` now runs after `runtime_cpus`
returns with validated FDT framing/window and before secondary CPU probes. It
logs the bridge/MIP declarations, GEM BAR offset/size, IRQ/PHY and outbound
window declarations. Its final marker explicitly says
`PASS PCIE_MMIO=0 CONFIG_ACCESS=0 DMA=0 NIC_READY=0`. Decode/output failure stops
the opt-in flow; default preprocessing removes the hook and its extra objects.
Both CLI and preprocessor reject combining it with storage-trial profiles.
The MMIO observer remains separate/unwired: this hook cannot train/read a link.

A fresh **host-only diagnostic**, with no embedded kernel or XNU transfer, is
`build/rpi5/bl33-probe-fqg0m3ec`; raw SHA256
`05d74ef66481a2faab89b80d616bfd0568d15f1c5d500fa73d85b61a7a429e10`.
Manifest SHA256 `c73bcae8c798af8fcbf5e137f70f84d588e6e58b2ff64ea313804ad434bd4eb4`.
All 374 Pi loader/tool source hashes were unchanged around its build, recorded
in `source-stability.json`. The reviewed conservative C-frame sum is 10,000
bytes of the 16-KiB early stack, leaving 6,384 bytes and exceeding the required
512-byte margin. This is not whole-program stack proof. Placement is explicitly
unverified; **do not install this standalone host artifact**. No new Pi boot
or bootloader-stage topology marker is claimed.

Six focused capture/controller checks and three topology integration checks
pass: allowlist/absence fidelity, source drift/no retry, stable boot/resources,
native decode/planning, actual preprocessing/default-off and storage exclusion,
each console-output failure and stack-budget rejection. The next physical
step needs a distinct recovery-backed diagnostic package and recorder; then
actual boot-stage declarations can precede safe bridge mapping, bring-up and
the separate config observer. No repeated storage/cache trial is warranted.
Including the existing PCIe/GEM and build-profile checks, all 28 focused tests
pass. The linked diagnostic ELF contains the topology logger/decoder but not
`rpi5_pcie_observe_rp1`, and has zero undefined symbols; this is not board proof.

Primary ABI reference: [Linux device-tree sysfs documentation](https://www.kernel.org/doc/Documentation/ABI/testing/sysfs-firmware-ofw).

## Physical full-FDT declaration trial — 2026-10-12 15:05 UTC

The next distinct package was built with:

```sh
python3 tools/rpi5/build_probe.py --load-address 0x9000000 --kernel build/rpi5/shell-userland-20261011/kernel.development.bcm2712 --init build/rpi5/shell-userland-20261011/ramdisk.bin --transfer --serial-terminal --gate3-cpu-on-all --gate5-pcie-topology
```

Output `build/rpi5/bl33-probe-28ubwa1k`; raw SHA256
`038c2b9bd0b55fa35496632fad7a96e8ffff1f2a7b64006e5709757bd895b895`;
manifest SHA256 `e7ef46cdf8bd319dbcff46457cea82591dc40189a964d8fbefc2a8edf065ea64`.
The reused, physically proven kernel SHA256 is
`d133f3a21ff9d3397aed7dfdd04210fe79061d8919d5046010dfa1919980a10f`;
RAM-root SHA256 `d32891113ad2ecdb1637bfdfd58991574026877cfb827a4bd0cd229980541f55`.
There was no new kernel/userland build or modification to the parallel VM work.
The host preflight rechecks those immutable inputs, every recorded loader
input/output hash, ELF/raw correspondence, compile/profile switches, shell
package checks and stack budget. Storage is disabled; the observer is not linked.

`stage_pcie_topology.py` is local-plan-only by default. Its distinct execute mode
requires the pinned actual W3 recovery/protection chain, current verified SSD
boot and exact CID/CSD/layout/partition identity, unmounted/unheld SD and inactive
automounters. It verifies all 20 NVMe recovery artifacts; backs up/readback-checks
the complete current MBR/FAT/HFS on SSD; verifies baseline hashes before mounting
only FAT; preserves W3 separately on SSD and SD; installs by bounded regular-file
copy/readback/rename; and remounts read-only/unmounts before final protection checks.
It never mounts HFS, changes firmware/configuration, reboots, retries or rolls
back automatically. FAT power-loss atomicity is explicitly not claimed.

Actual installation `build/rpi5/pcie-topology-installed-20261012` succeeded,
SSD run `/home/sandrzej/xnu-gate5-topology-z4ll1si5`. W3 is preserved as
`hfs-cache-buffer-failed.bin` there and SD
`probe.hfs-cache-buffer-failed-20261012.bin`. Fresh full snapshots retain the
installer's established `*.before-write.*` filenames; they do **not** mean any
XNU/HFS write was performed. Complete MBR/HFS remained unchanged; post-install
FAT SHA256 is `b200d1fcc91a2e36ba700b9967a8c5efc79c43a616575e7ce6286f98b98ade60`.
Installer result SHA256
`329c4c4bf151700824d71429d920a8d81f0e3c4341c0ca728f7d3100e1645c78`.

Verified Debug Probe `E66480454F719939`, `/dev/cu.usbmodem102`, had no competing
owner. `long_serial_capture.py` armed at 15:02:11 UTC, 115200 8N1, RX-only for
90 seconds. The recorded guarded one-shot SD reboot was requested at 15:02:18
UTC, using the existing `vcmailbox 0x0003808b 4 4 0xf61` path without EEPROM edit.
Firmware explicitly selected SD and loaded this image's exact 17205952-byte
extent at `0x9000000`; it reset PCI1 and PCI2 before OS handoff. The BL33 entry
guard passed and the full firmware FDT decoder emitted:

```text
BRIDGE CPU_START=0000001000120000 CPU_END=0000001000129310
MIP CPU_START=0000001000130000 MSI_PCI_TARGET=000000fffffff000
GEM BAR_OFFSET=0000000000100000 BYTES=0000000000004000 RP1_IRQ=0000000000000006 PHY_ADDRESS=0000000000000001
OUTBOUND SPACE=0000000002000000 PCI_BASE=0000000000000000 CPU_BASE=0000001f00000000 BYTES=00000000fffffffc NOT_PROGRAMMING_PROOF
OUTBOUND SPACE=0000000043000000 PCI_BASE=0000000400000000 CPU_BASE=0000001c00000000 BYTES=0000000300000000 NOT_PROGRAMMING_PROOF
PASS PCIE_MMIO=0 CONFIG_ACCESS=0 DMA=0 NIC_READY=0
```

These are actual runtime **declarations**, not register/window/link observations.
The filtered Linux DTB was not installed or used for allocation/boot. XNU then
mounted the original 19-node/589824-byte read-only RAM root and emitted intact
repeated shell-ready markers plus prompt, despite expected SMP UART interleaving
of some one-time banners. The recorder sent zero bytes; no new shell-command
acceptance or storage operation is claimed. No panic/second boot/rejection.

Capture `build/rpi5/mac-pcie-topology-trial-20261012` finished at 15:03:41 UTC,
32866 bytes, raw SHA256
`74453addcae85eded5b397d3a8dd737d923c615055b3ae48441f2beae8133a07`.
`check_pcie_topology_boot.py` rechecks package/install evidence, capture hash,
recorder/reboot chronology, exact declaration lines/order, single SD/loader
boot, transfer/RAM-root/shell readiness and absence of failures/storage activity.
`validation.json` SHA256
`7be8fe76ccdf43e72ee9f76ba764905da2fc4fb21f5bb8e00ae3e6b8b72df00e`.
The 90-second recording is a finite boot diagnostic, not a new stability soak.
Serial is released. Pi is now in XNU; the unchanged one-hour terminal watchdog
still applies and SSD fallback is not guaranteed. No manual action is requested.

Next close bridge register accessibility, clock/reset ownership, and safe
mapping/lifecycle requirements before wiring link/config observation. Firmware
reset messages reinforce that earlier Linux allocation/link state cannot be
carried forward as evidence. Then verify actual trained link, BAR/window
programming, interrupt routing and DMA/coherency before MAC/PHY/packet tests.
Gate 4 cache admission and its original durability exit remain unchanged.

All 46 focused host tests pass, including new boot-audit mutation/failure cases
and installer preservation/source-drift/result-completeness checks, existing
regular-file fault injection, topology preprocessing/logging/stack checks and
PCIe/GEM/package regressions. Log: `mac-pcie-topology-trial-20261012/focused-tests.log`.
These tests do not emulate FAT power loss or substitute for the actual board
capture above. `git diff --check` passed; no unrelated files were reformatted.
