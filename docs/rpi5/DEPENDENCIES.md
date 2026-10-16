# Gate 0 dependency and driver inventory

Status at project start: none of the Pi platform drivers or runtime providers
below has been implemented or validated on hardware.

| Dependency | Existing source / evidence | Required work |
|---|---|---|
| XNU | pinned Apple source in this fork | Cortex-A76 configuration and complete build |
| AvailabilityVersions | pinned in tools/rpi5/inputs.lock.json | SDK availability tool/headers generated and exported |
| Firehose | matching libdispatch source; source-built archive demonstrated | Exported header installed; rebuild archive for final config and verify link |
| Compiler runtime | upstream links `-lcc_kext` | Resolve exact helpers and source-build licensed implementations |
| Early entropy | `pexpert/gen/pe_gen.c`, `osfmk/prng/prng_random.c` | Supply 256 fresh seed bytes through Apple DT |
| Kernel PRNG | `register_and_init_prng`, `random_cpu_init` | Real provider, CPU generators and reseeding before consumers |
| Crypto functions | `libkern/crypto/register_crypto.c` | Register required real algorithms; inventory every used callback |
| AMFI/Image4/trust caches | nullable external providers, unconditional startup consumers | Explicit DEVELOPMENT policy; no blanket null success stubs |
| CoreEntitlements V2 headers | snapshot only exports older headers | Pi DEVELOPMENT uses opaque contexts and rejects V2 registration; no compatible V2 provider |
| Platform expert / CPUs | `iokit/Kernel/IOCPU.cpp` | Driver matching, CPU registration and lifecycle |
| PL011 | early polled implementation in `pexpert/arm/pe_serial.c` | UART10 mapping, clock/baud contract and console integration |
| Generic timer | ARM architectural register access | GICv2 IRQ handling, timebase, accounting and preemption |
| GICv2 / PSCI | no complete Pi implementation in this baseline | Distributor/CPU interface, SGIs, EL transitions and reset trampoline |
| Mockfs / memdev | existing in XNU | Width, page-unit and VA/PA correctness or validated fallback paging |
| SDHCI | no BCM2712 driver | Controller + IOStorageFamily + filesystem integration |
| PCIe / RP1 | no complete implementation | Host bridge, MSI, clocks/resets and DMA |
| Ethernet | no RP1 GEM driver | RP1 dependencies plus IONetworkingFamily integration |
| Darwin userspace | separate Apple OSS projects | Version/API closure; maintained init, libraries and utilities |

Initialization order: loader entropy -> XNU early random/VM -> platform and real
PRNG/crypto registration -> consumers and secondary CPUs. Exact startup ranks and
all consumer paths remain to be traced before Gate 0 passes. Link success does
not prove this runtime ordering.

Known review evidence:

- `makedefs/MakeInc.def`: KDK platform archive, auto-arm64e and subarchitecture linker flags.
- `osfmk/arm64/start.s`: L2 block bootstrap mapping and Apple CPU_OVRD path.
- `osfmk/arm/arm_init.c`: kernel load-command slide/fixup assumptions.
- `bsd/dev/memdev.c`: memory device base in 4 KiB units, narrowed in ioctl.
- `bsd/miscfs/mockfs/mockfs_fsnode.c`: base reconstructed with PAGE_SHIFT.
- `osfmk/vm/vm_object.c`: pager mapping expects the full kernel virtual address.
- Initial compilation also reaches legacy pointer narrowing in the non-coherent
  cache-dispatch path (`osfmk/arm/caches.c`) and panic-region code
  (`pexpert/arm/pe_init.c`). Pi callback width and checked panic offsets are now
  covered by native regression harnesses; actual hardware cache behavior remains
  unverified. Globally coherent I/O has not been enabled.

Hardware address reference values must be validated against the runtime FDT:
UART10 `0x107d001000`; GIC distributor `0x107fff9000`, CPU interface
`0x107fffa000`; SDHCI `0x1000fff000`; RP1 PCIe root `0x1000120000`.
Pi CPU MPIDRs are expected to be `0x000`, `0x100`, `0x200`, `0x300`.
These are reference values, not a replacement for address translation or discovery.
# PRNG provider licensing checkpoint

Five-source candidate subset verified: rand/hmac_drbg.c, mac/hmac.c,
hash/sha2small.c, codec/dec32be.c and codec/enc32be.c. Compiled with Cortex-A76,
-ffreestanding -fno-builtin -fno-stack-protector -D_FORTIFY_SOURCE=0 and combined
with `ld -r`, the only unresolved symbols are memcpy and memset. Without the
fortification override the host SDK introduces __memcpy_chk; kernel-header
integration is still required. `tools/rpi5/tests/bearssl_drbg_probe.c` linked
against this exact subset passes the first upstream SHA-256 HMAC_DRBG vector.
This is a host candidate test, not a registered or concurrency-tested provider.

Candidate evaluation: BearSSL was fetched from its official Git endpoint into
ignored `build/rpi5/bearssl-candidate`, at commit
`7bea48e5e850ab4cafbe68d3765cdaba13a86d6f`. Its LICENSE.txt and hmac_drbg.c carry
the MIT grant. No BearSSL code is linked into XNU yet. The
[official PRNG API](https://bearssl.org/apidoc/bearssl__rand_8h.html) provides
HMAC_DRBG init/generate/update with caller-owned context. This is a candidate
primitive, not a drop-in cckprng provider. Still required: pinned source subset,
known-answer tests, freestanding compile/dependency audit, per-CPU state/locking,
entropy-health failure handling, reseed policy and startup registration.
XNU entropy_provide requires a 64-byte recipient buffer and uses a try-lock;
the adapter must preserve zero/no-entropy versus negative/health-failure results.

Candidate verification: `make -j4 build/testcrypto` succeeds on this ARM64 host;
`build/testcrypto HMAC_DRBG SHA-256 HMAC` exits 0. The HMAC_DRBG test checks six
known-answer outputs (direct and vtable interfaces) using SHA-256. These are
upstream vectors, not evidence of kernel concurrency or entropy quality.
An isolated hmac_drbg.c compile with Cortex-A76, -ffreestanding, -fno-builtin and
-fno-stack-protector succeeds. Its undefined symbols are four BearSSL HMAC APIs
plus bzero/memcpy/memset; no allocation or OS entropy dependency appears in this
object. This is a single-object audit using host headers, not the finished
kernel library. Next close the HMAC/SHA-256 source subset and kernel headers,
then implement and test the entropy/synchronization adapter.

Apple's public [corecrypto repository](https://github.com/apple/corecrypto)
contains cckprng, but its [License.txt](https://github.com/apple/corecrypto/blob/main/License.txt)
states a 90-day internal security-verification grant and prohibits redistribution.
Do not import this as the distributable Pi provider without a separately suitable
grant. No corecrypto implementation was downloaded or imported in this review.
The published availability of source is not sufficient permission for this port.

The existing XNU `osfmk/corecrypto/ccdrbg_nisthmac.c` carries both an internal-use
notice and an Apple OS-reference/APSL notice. Resolve the applicable terms before
redistributing derived binaries or source; this report does not resolve that
legal ambiguity. Retain the imported notices unchanged.

Technical provider requirements from the pinned cckprng.h: per-generator
initialization, concurrency-safe generate/reseed, nonblocking refresh when its
shared lock is contended, an entropy callback that distinguishes no entropy from
health-test failure, and at most 256 output bytes per generate request. A small
early-boot DRBG alone does not satisfy this contract. Next evaluate a suitably
licensed provider and adapter against these requirements, rather than copying
the evaluation-only implementation.
