# Apple VZ platform inventory: 2026-10-12

One diagnostic VM ran from `2026-10-12T02:29:34Z` to `02:29:35Z`, with one CPU,
512 MiB RAM, generic EFI, one writable disposable virtio block disk, and one
virtio serial device. It passed nonce validation, complete diagnostic capture,
memory-map checks, and clean guest shutdown. No disk was mounted and no Pi,
physical disk, host shares, or networking was used.

Nonce: `567fce812c484fed95301a2966a48f8f`.
Small raw reports are preserved in [results/2026-10-12-platform](results/2026-10-12-platform/).
The original complete run remains `/private/tmp/darwin-efi-probe.qc63nS`.
No disk images, EFI executable, host executable, or variable store are copied into results.

This is **platform discovery for the XNU lifecycle target**, not XNU execution.
These are observed addresses for this exact configuration, not a stability promise
from Apple. A loader should discover them; changing VM devices can change PCI layout.

## Kernel handoff facts

| Facility | Observed value / source |
|---|---|
| EFI entry | EL1; counter frequency 24,000,000 Hz |
| RAM | 512 MiB, physical `0x70000000`–`0x90000000` exclusive, split into 21 RAM descriptors |
| Additional EFI MMIO descriptors | `0x01000000` / 128 KiB; `0x20050000` / 4 KiB |
| GIC | MADT reports GICv3; distributor `0x10000000` |
| Redistributor | `0x10010000`, span `0x20000` for the one CPU |
| CPU | MPIDR `0`; enabled. GICC legacy MMIO CPU-interface base is zero |
| Timer | GTDT nonsecure physical EL1 GSIV `30`, virtual GSIV `27`, EL2 GSIV `26`; EL1/virtual flags zero |
| PSCI | FADT ARM flags `3`: compliant and HVC conduit |
| PCI ECAM | MCFG segment `0`, base `0x40000000`, buses `0`–`255` |
| ACPI roots/tables | RSDP, XSDT, FACP/FADT, DSDT (830 bytes), GTDT, APIC/MADT, MCFG |
| Absent tables | No SPCR or SSDT in this XSDT; no FDT configuration table |

The memory map is the snapshot taken while EFI boot services remain active, not
the final `ExitBootServices` map. A real loader must reacquire that map/key and
preserve runtime/reserved memory correctly. The raw descriptor size is 48 bytes,
version 1, and there are 23 descriptors. See
[platform.json](results/2026-10-12-platform/diagnostics/platform.json).

## Why serial was silent

`LocateHandle(ByProtocol, EFI_SERIAL_IO_PROTOCOL_GUID)` returned `EFI_NOT_FOUND`
(`0x800000000000000e`), with zero serial handles. The host serial log remained empty.
There was no SPCR describing a firmware UART. Thus this configuration does not
expose the host's virtio serial device through a firmware Serial I/O protocol.

The console hardware is nevertheless present: PCI `0000:00:05.0`, vendor `0x1af4`,
device `0x1043`, class `0x078000`: a modern virtio console. The kernel/loader needs
a native virtio-PCI console transport; a Pi PL011 driver is not a substitute.
Feature negotiation, virtqueues, DMA/barriers, and transmit/receive are still
implementation work. This probe did not initialize its virtqueues or transmit
through the PCI transport, so it proves discovery, not working serial I/O.

### Console PCI configuration

The raw [pci-1.bin](results/2026-10-12-platform/diagnostics/pci-1.bin) starts with
four 64-bit little-endian location integers (segment, bus, device, function),
followed by exactly 256 bytes of PCI configuration space. The device's ECAM
configuration address is `0x40028000` for this run.

- BAR0 is 64-bit memory: low `0x00010004`, high `0x00000001` → `0x100010000`.
- BAR2 is memory `0x50000000`.
- PCI command is `0x0016` (memory and bus mastering enabled by firmware).
- Interrupt pin is `1` (INTA); interrupt-line byte is `255`, not a usable GSIV.

The capability chain begins at PCI offset `0x40`:

| PCI capability offset | Kind | BAR | Offset within BAR | Length | Effective address |
|---|---|---|---|---|---|
| `0x40` | Virtio common config (type 1) | 0 | `0x0000` | `0x38` | `0x100010000` |
| `0x50` | Virtio ISR (type 3) | 0 | `0x1000` | `0x01` | `0x100011000` |
| `0x60` | Virtio notify (type 2) | 0 | `0x4000` | `0x10` | `0x100014000` |
| `0x74` | Virtio device config (type 4) | 0 | `0x8000` | `0x0c` | `0x100018000` |
| `0x84` | MSI-X (capability ID `0x11`) | 2 | table `0`, PBA `0x50` | 5 vectors | BAR2-relative |

The notification multiplier is `4`; a queue's notify address still depends on
its negotiated `queue_notify_off`, not merely the capability base. The raw DSDT
contains the static PCI `_PRT`; its device-5/pin-0 entry maps to GSIV `69`. This
is a static AML reading, not a tested interrupt-delivery result. Initial polled
console bring-up need not depend on MSI-X or that routing.

The block device is PCI `0000:00:06.0`, `1af4:1042`, BAR0 `0x100000000`, BAR2
`0x50001000`. A PCI host bridge is at `00:00.0`, `106b:1a05`.

## Capture bounds and binary format

`DIAG.BIN` is a preallocated 256-KiB file. ACPI table reads require the complete
range to lie inside one non-MMIO EFI RAM descriptor and a valid checksum.
Each table is limited to 64 KiB, XSDT traversal to 64 entries, Serial I/O handles
to 16, and PCI handles to 32. A capture error prevents a diagnostic pass. Absence
of a firmware serial protocol is recorded but is not itself a capture error.

The 64-byte little-endian header contains magic `EFIDIAG2` (8 bytes), version at
offset 8, used length at 12, nonce ASCII at 16 (32 bytes), record count at 48,
completion flag at 52. Each record has a 16-byte header: kind, index, payload
length, reserved; each is a 32-bit integer. Payloads follow without alignment padding:

1. RSDP bytes.
2. Complete ACPI table bytes (including DSDT/SSDT AML when present).
3. Raw EFI memory-map bytes, with descriptor metadata in the text report.
4. EFI Serial I/O device-path bytes, if available.
5. Four 64-bit PCI location integers and 256 configuration bytes.

Host extraction validates nonce, completion, length bounds, unique record IDs,
ACPI checksums and table lengths. No AML is executed on the host. The small
`platform.json` decoder covers MADT/GIC, GTDT, FADT/PSCI, MCFG and SPCR fields;
the original bytes remain available for independent analysis.

## Verification

Build and six focused tests passed:

```sh
/bin/bash experiments/darwin-container/efi-probe/script/build_and_run.sh --build-only
```

The one authorized VM run passed:

```sh
/bin/bash experiments/darwin-container/efi-probe/script/run_prepared.sh /private/tmp/darwin-efi-probe.qc63nS
```

That directory is single-use: rerunning is deliberately refused once results
exist. A future trial needs a freshly prepared image. No further VM runs were made.

## Public format references

Decoding is original code using public formats, not copied implementation:

- [UEFI specification](https://uefi.org/specs/UEFI/2.10/): memory descriptors, protocol discovery, Serial I/O and PCI I/O.
- [ACPICA FADT declarations](https://github.com/acpica/acpica/blob/master/source/include/actbl.h).
- [ACPICA GTDT declarations](https://github.com/acpica/acpica/blob/master/source/include/actbl1.h).
- [ACPICA MADT/MCFG declarations](https://github.com/acpica/acpica/blob/master/source/include/actbl2.h).
- [ACPICA SPCR declarations](https://github.com/acpica/acpica/blob/master/source/include/actbl3.h).
- [Virtio 1.2 specification](https://docs.oasis-open.org/virtio/virtio/v1.2/virtio-v1.2.html): modern PCI capabilities and console device semantics.
