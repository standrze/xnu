# BCM2712 configuration bridge over original IOPCIFamily

2026-10-12. A serialized configuration-access core and an actual subclass of
Apple's original `IOPCIBridge` now compile for Cortex-A76 and link with the
[previously screened original family](GATE5-APPLE-PCI-BUILD.md). All 140 selected
host regressions pass. This is **not a concrete attached root bridge, actual
MMIO access, RP1 enumeration, BAR assignment, DMA or Ethernet acceptance**.
No boot image/kernel source-list or catalogue change was made.

## Configuration transaction implementation

`loader/rpi5/pcie_config.{h,c}` supports fixed root `00:00.0` and RP1 `01:00.0`.
Other valid BDFs return absent without any callback. Misaligned offsets,
invalid widths/BDF fields, access past the 4-KiB configuration space and values
that exceed a subword reject without I/O. Read output is published only on
complete success. All-ones configuration data remains valid, unlike an
all-ones controller-status read.

The controller routing follows the primary
[Raspberry Pi Linux controller reference](https://github.com/raspberrypi/linux/blob/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c):
root accesses are direct; endpoint accesses select bus/devfn through an index
register and use the data window. The
[ECAM definitions](https://github.com/torvalds/linux/blob/master/include/linux/pci-ecam.h)
place bus at bit 20 and devfn at bit 12, with a 12-bit register offset.
This implementation's fixed RP1 selector is `0x00100000`; INDEX is `0x9000`
and DATA is `0x8000` in the decoded PCIe2 mapping.

Each transaction holds the provider's shared config lock across lifecycle
checks, ordering, controller status, selector write/order/readback, true-width
data transfer and final status/selector/lifecycle checks. Root access requires
RC role and not L23, but can inspect root config with endpoint link down.
Endpoint access additionally requires both data-link and PHY-up indications
before selector/data access and in final checks. There are at most 15 callbacks,
no polling, retries, cleanup writes or rollback. Only lock release follows a
failed callback; a failed acquire never authorizes unlocked state mutation.

Actual byte/halfword writes are required; no word read-modify-write may touch
adjacent PCI W1C status. The provider must authorize **every** config write,
including BAR sizing/assignment, bus numbering/reset, MSI/interrupt enables
and bus mastering. A denied write quarantines the session. This callback is
not a no-op production policy, a DMA grant or physical evidence: the concrete
provider still has to implement it from independent hardware ownership and
phase-specific admission. No provider implementation exists yet.

Init checks the same exact physical base `0x1000120000`, size `0x9310`, owner
context and consistent link/RC/windows/UBUS/SerDes/MDIO/reset/calibration chain.
States are rechecked under lock on use. These software states do not prove
accessibility, power/clock/shared-resource ownership, bounded callback latency,
DMA coherency, fault containment or a safe reset destination.
In particular, a link-status sample cannot prevent asynchronous link loss
from causing a CPU abort. Already-issued writes may persist after failure.
Only this config session is quarantined; the physical owner must prohibit
other controller clients from treating earlier COMPLETE states as permission
to restart/use a failed controller.

## Original Apple API connection

`iokit/Kernel/BCM2712PCIConfigBridge.{h,cpp}` derives from the actual original
`IOPCIBridge`, implementing all six byte/halfword/word virtual config methods,
fixed first/last buses, root address space and no-PCI-I/O-aperture response.
`BCM2712PCIConfigAddress.h` uses Apple's original endian-specific address
bitfields: low register byte comes from the method argument; extended register
bits come from `space.es.registerNumExtended`. The `space.s.registerNum` byte
is not added to the supplied offset or treated as ECAM.

Absent/error reads return width-appropriate all-ones. The original virtual
writes return void, so the adapter maintains a monotonic atomic failure latch
in addition to core quarantine; subsequent access is refused after a
non-absence error. A concrete provider must check `configAccessHealthy` before
and after original enumeration/configuration and handle failure, rather than
interpreting a void return or original `start` return as write success.

The subclass is deliberately abstract, enforced by a compiler assertion:
`start` and `configure` remain pure virtual. Original `IOPCIBridge::start`
immediately enumerates, so inheriting it without a real host owner/resource
implementation is not permitted. Binding is protected, once-only and before
publication. No public registry boolean or auto-match personality admits
hardware. The owner must retain/drain callback, mapping and session lifetimes
until all configuration users have detached. No fake IOKit declarations or
allocator shim is used.

## Local evidence

Five focused tests cover:

- ASan/UBSan controller model: every valid config offset/width (14,336 reads),
  all 132 callback-failure positions across root/endpoint reads/writes, exact
  callback bounds, failed posted-write effects with no rollback, W1C-neighbor
  preservation, all absent BDFs, malformed requests, all endpoint status-byte
  patterns, selector corruption and 15 prerequisite-chain mutations;
- actual pthread mutex ownership with two threads/4,000 serialized reads,
  and same-thread callback recursion rejection without state corruption;
- a freestanding A76 core object with no undefined runtime dependencies;
- native execution of the adapter's pure address helper using **original
  Apple headers/types**, all 65,536 BDF combinations and 8,192 root/endpoint
  offset cases. Only the test's host deployment target is lowered; no kernel
  API or driver executes on the Mac;
- actual A76 original-header subclass compilation, unchanged original-family
  relocatable linkage, input/output hashes, changed baseline rejection and
  overwrite/unsafe-output refusal.

All 140 selected regressions pass (37.186 seconds), including earlier Apple
family/allocator, sockets, zsh metadata/replay/protected installation and PCIe
cores. This is not the full XNU suite, a concrete provider test or a Pi boot.

`tools/rpi5/build_apple_pci_config.py` binds the exact previous family manifest
and its pristine sources/generated headers/objects before compiling the new
core and subclass. New board code is warning-clean under the actual XNU
template's strict warnings; original family headers are system includes,
while the consistent availability overlay retains its required precedence.
All 638 captured inputs are checked for build-time stability.

Artifact `build/rpi5/apple-pci-config-20261012-final/apple-bcm2712-pci-config.o`:
730,792 bytes, SHA256
`cd3b0f6a874ea2d47e043381b5df82be0c6a5a81764f8efe368a755a906809fa`.
Manifest SHA256
`7588f60a64495f648d8e41fa16f25bb0bd4a0c4584e9b39039ae66c2f7e9ac8b`.
The combined object still has 528 undefined names, with only `___dso_handle`
absent from the reference kernel's symbol inventory. No new fake provider or
DSO symbol was added; final link, constructor/module lifetime, ABI semantics
and startup registration remain unproved.

```
python3 -m unittest tools.rpi5.tests.test_pcie_config -v
python3 tools/rpi5/build_apple_pci_config.py --output-dir NEW_DIRECTORY
```

## Fresh Linux reference and remaining work

SSH now reaches verified SSD Linux: root `/dev/nvme0n1p2`, ext4 UUID
`04570742-280b-43cb-9564-73d454243b1c`, boot ID
`d5c3e702-5caf-4452-8799-7cd29803a06a`. The existing allowlisted two-pass
Linux reference collector succeeded under
`build/rpi5/pcie-linux-reference-config-20261012`; result SHA256
`35777669741980d45871dba6dde3320e23253de065440d19939c0110df1dcfb1`,
reference SHA256 `0d3c4990b7bb98a4a84ecd7c03ff93f95c797948f1e8f69603071134ded55004`.
The native topology/resource planner validates BAR1 PCI base zero/size 4 MiB,
CPU span `[0x1f00000000,0x1f00400000)`, GEM
`[0x1f00100000,0x1f00104000)` and clocks
`[0x1f00018000,0x1f00028038)`. This is Linux's assignment, not XNU authority.

Read-only Linux inventory also shows RP1 at `0002:01:00.0`, wired `eth0`
NO-CARRIER and wireless `wlan0` UP/LOWER_UP. No interface settings changed.
The exact known SD CID `1b534d474432533530654f68d1a16100`, 128177930240-byte
size, MBR ID `5ae1f07e` and FAT/HFS partition geometry are present and unmounted;
EEPROM remains SD-first `0xf461`. The current FAT/probe hash and complete
40-artifact preservation chain have **not** yet been freshly revalidated;
this inventory is not staging admission. No SD mount/write, serial access,
power action, firmware update, reboot or soak occurred.

Next implement the concrete Device-mapped owner with genuine power/clock/
shared-lifecycle and bounded recovery admission, connect this config adapter
and original family resource/address translation, and complete an opt-in final
kernel/constructor registration build. Audit original enumeration's config
writes against phase policy; do not blindly authorize DMA to get it through
startup. Only then admit physical RP1 enumeration/BAR readback, followed by
interrupts, GEM/PHY/DMA/IONetworkingFamily and wire traffic tests.

Independently, verified SSD Linux now permits preparing the baseline-aware
socket trial installer and explicit post-mount identity-framing correction.
The existing socket image still passes all 34 package checks but is unstaged.
Fresh hashes/snapshots and all 40 older backups must pass before staging; arm
the guarded recorder before any software reboot. No repeated manual restart
or extra soak is requested. Gate 4 durability/history stays held separately.
