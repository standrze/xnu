# Apple PCI family: actual Pi XNU header integration screen

2026-10-12. All eleven source entries of Apple's selected IOPCIFamily kext
target now compile against the actual Cortex-A76 Pi XNU build headers and
combine into a Mach-O relocatable object, with two explicit patches applied
only to a separate source copy. This advances the generic PCI infrastructure
beyond the earlier isolated range allocator. **It is not a final kernel link,
driver attachment, enumerated RP1, DMA authorization or working Ethernet.**
Nothing was installed; the working serial zsh image and historical backups are
unchanged. Gate 4 durable storage/history remains independently held.

## Original sources and build environment

Pristine source is the same selected
[IOPCIFamily-726.100.6](https://github.com/apple-oss-distributions/IOPCIFamily/tree/503b7da7c8d67bc2dedecd83dd07b72f4644ec4b),
commit `503b7da7c8d67bc2dedecd83dd07b72f4644ec4b`.
`tools/rpi5/audit_apple_pci_build.py` verifies the commit, clean checkout and
every tracked source hash. It derives the eleven entries from the original
kext Sources phase, rather than quietly excluding inconvenient source files:

- IOPCIBridge, IOPCIDevice and the actual generated IOPCIDevice IIG implementation;
- IOPCIConfigurator, IOPCIRange and IOPCIDeviceMappedIO;
- IOPCITraceEventBuffer and IOPCIMessagedInterruptController;
- AppleVTD, IOPCIDeviceI386 and IOPCIBridgeLegacy, whose architecture guards
  leave essentially empty objects for this ARM profile, not functional x86 drivers.

Compilation reuses the hash-pinned actual `IOService.cpo.json` from
`fresh-435uage7/obj/DEVELOPMENT_ARM64_BCM2712`, including its real exported
XNU/generated headers, `meta_features.h`, kernel-private definitions and
`-mcpu=cortex-a76`. Original output/dependency destinations are removed.
Actual Apple `iig` generates the PCIDriverKit header and implementation from
the original definition and XNU DriverKit definitions. No invented classes,
allocator-only private-header shim, or fake DART provider is used.

A separate include overlay copies original SDK `Availability*.h`,
`os/availability.h`, `TargetConditionals.h` and `AssertMacros.h` as a consistent
set. This fixes the mixed new-SDK/old-XNU availability-helper expansion error;
it does not disable availability checks or replace kernel API declarations.
Source, compiler, generated outputs, compiler-discovered dependencies, logs
and original kernel hashes are recorded and rechecked for changes.
Original warnings remain in logs (875 across the adapted compile); semantic
errors are not suppressed. A production warning cleanup is still outstanding.

## Explicit adaptation boundary

The pristine full-header screen is retained as a failed baseline: ten entries
compile, but `IOPCIBridge.cpp` requires unavailable `IOKit/dart/IODARTKeys.h`.
An empty replacement header or guessed platform-function strings would hide
that incompatibility, so neither is supplied.

The adapted mode copies all original tracked sources/notices/license to its
own output tree and applies two zero-fuzz patches. Only `IOPCIBridge.cpp`
changes; the pristine checkout, public declarations and all other sources
remain byte-identical:

1. `pci-bcm2712-no-apple-dart.patch` guards the private DART include and two
   Apple-only mapper platform-function blocks behind `RPI5_PCI_NO_APPLE_DART`.
   Using that flag without `ARM64_BOARD_CONFIG_BCM2712` is a compile error.
   This does **not** install an identity mapper, prove absence of translation
   requirements, enable bus mastering, or supply Pi DMA coherency/translation.
   The original method and device-removal call remain present; only their
   Apple-DART-specific operation is omitted for this profile.
2. `pci-cxx-return-types.patch` replaces `return NULL` in a boolean predicate
   with `return false`, and `return true` in a void method with `return`.
   These fix actual compiler errors without weakening return-type checking.

Original per-file notices remain intact. The repository has mixed historical
APSL notices; its root license is retained, not treated as blanket legal or
redistribution clearance. Any external release must handle applicable source,
modification and notice obligations for the actual selected files.

## Evidence and limitations

Pristine screen: `build/rpi5/apple-pci-pristine-headers-20261012-final`.
Manifest SHA256 `426a35c30f31ba3044d3a88b27df445637067bd06185523497c90ff2451f90ed`.
Its missing-header failure is preserved, not waived as pristine success.

Adapted screen: `build/rpi5/apple-pci-bcm2712-headers-20261012-final`.
Manifest SHA256 `70b44e294bf2e55c4d9bb2eeacab5d89db361636ae40a2bcae12b092a0a3c117`.
`IOPCIFamily-partial.o` is 714,520 bytes, SHA256
`0b9e4598dfc86654234ccf74bf5a88ca62454f325f35b5db7c078c15e72b0cb4`.

All eleven entries compile and `ld -r` succeeds. Real IOPCIBridge,
IOPCIDevice and IOPCIConfigurator metaclasses plus original range allocator
definitions are present. Of 528 undefined names in the combined object, 527
exist in the reference kernel's symbol inventory; `___dso_handle` does not.
This is only a name-level comparison. No dummy DSO symbol was supplied;
constructor/module lifetime integration needs a real final link and startup
proof. Vtable/layout/API semantic compatibility, symbol visibility, constructor
ordering and built-in catalogue registration are not proved by `nm`.

Five focused tests perform real pristine/adapted builds, check the original
source phase, reject wrong commits/templates/unsafe output locations, verify
input/artifact hashes and overwrite refusal, check the exact changed-file set,
verify no shim/fake declarations, and exercise the BCM-only compile guard.
They do not run original PCI code against hardware.
All 135 selected regressions pass, including the existing Apple allocator,
socket diagnostic, zsh metadata/replay, protected installation and PCIe cores.
This is a selected host suite, not the full XNU test suite or a Pi boot trial.

```
python3 -m unittest tools.rpi5.tests.test_apple_pci_build -v
python3 tools/rpi5/audit_apple_pci_build.py --output-dir NEW_PRISTINE_DIRECTORY
python3 tools/rpi5/audit_apple_pci_build.py --bcm2712-no-apple-dart --output-dir NEW_ADAPTED_DIRECTORY
```

The pristine command exits nonzero as expected. Existing output directories
are never reused. Inputs/artifacts of earlier attempts are preserved separately.

## Next integration sequence

1. Add the BCM2712 root-bridge backend using these actual original interfaces:
   serialized configuration selector/data access, true subword operations,
   root/endpoint and link checks, bus range and FDT-derived resource apertures.
   Do not let enumeration/configuration enable DMA before provider admission.
2. Complete a separate opt-in final-kernel build, genuine constructor lifetime
   and family registration, resolving the DSO dependency through the actual
   build/module model. Keep existing accepted kernels and recovery images intact.
3. Close actual Device mapping, power/clock/shared ownership, unused-window and
   bounded reset/one-shot SSD recovery prerequisites before installing the
   existing read-access probe or enabling any write bring-up sequence.
4. Compose reset/calibration/SerDes/UBUS/RC/windows/link and observe RP1; use
   original configurator/range machinery for actual BAR assignment/readback,
   then reconcile resources. The prior allocator returns candidates, not
   observed assignments.
5. Implement RP1 interrupt/MSI-X/MIP integration, GEM clocks/PHY, independently
   admitted DMA/coherency and original IONetworkingFamily attachment; validate
   real packets before claiming wired Ethernet or SSH readiness.

Fresh read-only SSH to `192.168.4.23` timed out. That does not identify the
running OS. No serial handle, SD access, power operation, reboot or soak was
started, and inability to reach Linux did not prevent this local build work.
