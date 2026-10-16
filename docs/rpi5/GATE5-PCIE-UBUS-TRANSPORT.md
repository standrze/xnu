# Actual kernel PHY-to-UBUS continuation — 2026-10-12

Preparation continuation: a separate copied build now connects retained boot
FDT metadata, a real kernel Normal-RAM view and private Apple OSData seed
sanitization to this owner's actual strict preparation. See the
[retained-FDT checkpoint](GATE5-FIRMWARE-FDT-HANDOFF.md). It still introduces no
boot caller, activation, physical admission or complete kernel.

A separate, **uninstalled** IOKit transport now runs the actual UBUS/AXI core
after the actual reset44/shared-RESCAL/54-MHz-SerDes chain. It is not a complete
PCI bridge, admitted physical trial or Ethernet milestone. Accepted source,
kernel, root and zsh/socket image bytes are unchanged. No Pi, serial, SD, power,
firmware, reboot or soak operation occurred for this checkpoint. Gate 4 remains
held separately; original zsh/socket/SSH/userland requirements remain in scope.

## Real connection, not synthetic prerequisites

`tools/rpi5/patches/pcie-ubus-transport.patch` extends **copies** of the accepted
`BCM2712PCIePHYTransport.{h,cpp}`. `BCM2712PCIeUBUS.inc` supplies the new
`runPHYAndUBUS` entry. Its output must be stable and independent of the owner.

1. Reject null output, foreign thread or a non-PREPARED instance, without I/O.
2. Call the actual `runInitialPHY` into a local observation. Its existing
   retain-before-claim, single watchdog claim, real reset/calibration/SerDes
   cores and provider/maps/singleton ownership are preserved.
3. Enter a distinct UBUS phase and recheck the same watchdog/provider guard.
4. Initialize `rpi5_pcie_ubus` with the **same actual completed SerDes session**,
   not a newly fabricated COMPLETE object or replacement success callback.
5. Execute the real UBUS core through the same ordered volatile callbacks.
6. Recheck the guard, mark COMPLETE and publish the combined observation only
   after full success. No lease renewal or second watchdog claim occurs.

UBUS programming implements the existing core's error-response suppression,
all-ones read-error data, fixed UBUS/configuration-retry timeouts, AXI QoS fix,
Reserved-0 timing-bit fallback and disabled VDM QoS reception. The core has no
poll loop and uses 20 callbacks normally, 23 with the fallback. This is not a
wall-clock/fault-containment guarantee for a hung physical transaction.

`BCM2712PCIeUBUSPolicy.h` preserves every original phase and access permission,
adding **only** these aligned 32-bit bridge transactions in the new phase:

| Offset | Permission |
| --- | --- |
| `0x40a4` | UBUS control read/write |
| `0x40a8` | UBUS timeout read/write |
| `0x405c` | Configuration-retry timeout read/write; not configuration-space access |
| `0x416c` | AXI control read/write |
| `0x40a0` | VDM QoS control read/write |
| `0x4170` | Error-data write only; no all-ones readback |

The new phase cannot access reset, RESCAL, MDIO, config selectors, windows,
PERST, endpoint BARs, interrupts or DMA. COMPLETE/FAILED still admit no register
access. It adds no physical mappings or Device declarations: the three banks
and five pages remain those of the earlier transport. The separately built
[loader handoff](GATE5-PCIE-DEVICE-HANDOFF.md) remains uninstalled.

Each register read/write and ordering callback retains the real before/after
watchdog/provider guard. On failure, all four local sessions and MDIO become
quarantined; already-issued writes persist, and there is no cleanup MMIO,
retry, reset, power-off or release of the pinned ownership. A foreign caller
cannot mutate the preparing thread's state. These are software restrictions,
not independent proof of physical access exclusivity or actual clock/power.

## Build and local evidence

```sh
python3 -m tools.rpi5.build_pcie_ubus_transport \
  --output-dir build/rpi5/pcie-ubus-transport-20261012-final
PYTHONPATH=tools/rpi5/tests:tools/rpi5 python3 -m unittest \
  tools.rpi5.tests.test_pcie_ubus_transport
```

The builder verifies the exact accepted PHY receipt and its inputs/outputs,
checks the seven reused C objects against that receipt, then compiles the
patched **real IOKit C++ transport** and actual UBUS C core with recorded A76/
XNU-header commands. Both new units are warning-free. The partial link uses
the original Apple PCI-family/resource object and actual PM-watchdog owner,
not the old combined PHY object (which would duplicate the class). It rejects
new unresolved dependencies beyond the already documented family
`___dso_handle` requirement. It retains actual target assembly and hashes all
generated files, verifies stable inputs, requires a new output directory and
refuses accepted/source locations. It has no staging or hardware command.

All **four focused tests pass**:

- ASan/UBSan executes the actual four C cores in order with the actual phase
  policy under modeled register callbacks. Both AXI paths complete, retain
  session identity and use 28/29 writes. Their 248/254 guard positions are
  fault-injected individually (**502 cases**), including post-write failures.
  Failure leaves combined output unchanged, quarantines every stage and admits
  no retry or further modeled write. All-ones read failures cover each UBUS
  readable register. Null output is rejected before starting.
- Exhaustive phase/bank/offset/width/direction checks verify the 11 new
  permissions and exact equivalence to the old policy outside the new phase.
- Actual kernel compile/partial link, input/output/log hashes, metaclass and
  generated assembly are checked. Missing UBUS/PHY opt-in, non-DEVELOPMENT and
  non-BCM profiles reject. Existing output is not overwritten.
- Dependency-receipt drift and unsafe output locations reject.

The callback model does **not** execute the C++ IOKit lifecycle on the Pi or
prove map accessibility, watchdog reset timing/destination, power/clock
retention, shared-resource exclusivity, RP1 quiescence or working Ethernet.
Actual compilation is separate evidence from native modeling.

The expanded **211-test regression suite passes in 76.392 seconds**, covering
the new continuation, declaration handoff, previous PHY/watchdog/PCI cores,
Apple-family integration, loader/tree/stack checks, original zsh and socket/
metadata/root staging/trial tooling, recovery guards and GIC/SGI/topology tests.
No full-kernel or physical-board acceptance is inferred from that result.

## Distinct artifact

- Directory: `build/rpi5/pcie-ubus-transport-20261012-final`.
- Object: `apple-bcm2712-pcie-ubus-diagnostic.o`, **855,480 bytes**.
- Object SHA256: `ef5560aa0597c9cb4fc475a10866dbd08da172bb4122519b956e3ff69de46f45`.
- Manifest SHA256: `cec6fb504b3b7b903bee2622c271c5e08bc3557a6bdf22033648b6559db4098b`.
- Actual target assembly SHA256: `42facd3c90c4042aaec2798ab7417ec8ca5d7c3ef3ca3bbd248d41de8fba7b83`.
- **732 input pins + 17 generated-file pins**, independently revalidated
  (747 unique files; the copied source/header occur in both sets).
- 536 undefined symbols at partial-link scope; only the pre-existing DSO
  requirement is absent from the reference kernel.

The `first` directory preserves a copy-patch hunk-placement failure. The
corrected patch applies with fuzz zero; `second` is a development artifact,
and `final` is authoritative. No accepted file was edited to repair it.

## Next actual integration

No boot caller, registry admission boolean, catalogue/source-list entry or
complete kernel is introduced. Genuine retained power/clock/shared-RESCAL
ownership, RP1/DMA quiescence and independent bounded reset/SSD-return admission
remain prerequisites **before** calling the destructive reset/PHY/UBUS entry.
Keep controller 1 accessible; never reset/power it off as cleanup.

Intentional raw-FDT/provider handoff, constructors/catalogue, replacing rather
than duplicating `pe_fiq.o`, and the original PCI-family DSO requirement remain
full-kernel integration work. The next register stages are unused-window/
interrupt/DMA quiescence checks, RC/window programming and PERST/link training,
then original-family config/BAR assignment/readback, interrupts, DMA and GEM
Ethernet. Neither working SSH nor persistent files/history is claimed here.
