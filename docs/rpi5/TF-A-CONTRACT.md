# Pi 5 TF-A entry contract — source checkpoint

Candidate source is pinned in tools/rpi5/tfa.lock.json to Raspberry Pi's fork,
commit 332b62e0443b004287d2cfc032a70bba6fb86f35. The ignored checkout is clean.
BL31 now builds from this checkout; it has not been installed or booted.

## Build checkpoint

Use make in build/rpi5/tfa-candidate with PLAT=rpi5 DEBUG=1
RPI3_RUNTIME_UART=-1 and absolute CC/LD/OC/AR paths to the checked-in
tools/rpi5/tfa-clang, tfa-lld, tfa-objcopy and tfa-ar wrappers. These use Apple
clang's aarch64-none-elf target and the pinned local Zig toolchain. The first
attempt stopped at a missing archiver; the explicit archiver wrapper resolved it.
Tool discovery still warns about unused host tools and the object-copy identity;
the actual link and binary conversion complete successfully.

Output: build/rpi5/tfa-candidate/build/rpi5/debug/bl31.bin, 45,174 bytes,
SHA-256 `413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46`.
The associated ELF is little-endian AArch64, has no undefined symbol entries or
dynamic section, and its LOAD memory extents end at 0x14000, inside the observed
0x80000 firmware reservation. The source checkout remains clean. This is a
build/structural checkpoint, not reproducibility certification or hardware proof.

## Entry semantics

### Native single-primary transition checkpoint (2026-09-05)

The probe now writes HCR_EL2.RW with other bits clear (non-VHE, no stage 2 or
interrupt routing), CNTHCTL_EL2=3, CNTVOFF_EL2=0, CPTR_EL2=0x33ff,
MDCR_EL2/HSTR_EL2/VTTBR_EL2=0. Constants were checked against this pinned
tree's include/arch/aarch64/arch.h. SCTLR_EL1=0x30d00800 retains baseline RES1
bits with M/C/I off; CPACR_EL1 and CNTKCTL_EL1 are zero and both EL1 timers
are disabled. The probe uses no FP/SIMD. SP_EL1 and VBAR_EL1 are established
before ERET with SPSR_EL2=0x3c5 (masked EL1h). FDT PA survives in x19.

EL1 reads/reports CurrentEL, SCTLR, DAIF and CNTVCT, then stops before timer
interrupt setup. Fatal vectors select EL1 versus EL2 syndrome registers and
parking VBAR by CurrentEL. This is a compiled/source-reviewed transition, not
a measured hardware result, a complete XNU entry contract, or secondary-CPU
normalization. Firmware remains responsible for loaded-code visibility and
EL3 access permissions. No cache-enabled entry is accepted.

The rpi5 platform selects common/rpi4_bl31_setup.c and common/rpi3_common.c.
With RPI3_DIRECT_LINUX_BOOT=1 and the required AArch64 profile, setup chooses
the firmware-provided payload entry, or PRELOADED_BL33_BASE when explicitly
configured. It supplies the physical FDT pointer in x0 and zeros x1–x3.
rpi3_get_spsr_for_bl33_entry returns EL2h with all exceptions masked, and the
entry descriptor is marked non-secure. Thus the planned loader is a BL33
replacement using that input ABI; it must not interpret x0 as XNU boot_args.

The loader must preserve the FDT pointer before establishing its own stack,
validate its current exception level, and explicitly establish the EL1 contract.
The source evidence here does not yet prove cache/MMU state, timer trap setup,
secondary entry or all register values. Those remain required for native entry.

The platform's makefile sets RPI3_RUNTIME_UART=0, whereas docs/plat/rpi5.rst
describes a default of -1. Set -1 explicitly for the planned test build to
disable TF-A runtime logging and avoid sharing the console with loader polling.
Boot-time TF-A logging and loader baud/configuration still need coordination.

## Secondary preflight

Runtime conduit validation now precedes even PSCI_VERSION: one enabled /psci
node must contain method=smc and a 0.2/1.0 compatible string. Missing/duplicate
consumed fields, duplicate /psci nodes, HVC or unsupported status stop the probe.
This validates the advertised ABI, not the actual firmware implementation.

Secondary fault reporting follow-up: TPIDRRO_EL0 now holds slot+1 (zero on
primary). After safe-stack/vector setup, fatal diagnostics publish exception
slot, level, syndrome, return address, raw fault address and saved state before
setting ready=2 with DSB/SEV. Primary prints this record and stops; it must not
assume interrupt-controller cleanup succeeded on a fault path. No secondary
UART accesses occur in this path. Very early or nested faults can still yield
only timeout. TPIDR registers are diagnostic-private until an XNU handoff
explicitly reinitializes them. Fault injection on the actual board remains open.

Per-secondary timer follow-up: before publishing ready, each secondary runs the
bounded timer IRQ test and copies its verification/acknowledgment/count/status
into its private record. Primary checks those fields before proceeding. All
other CPUs remain IRQ-masked/parked, so shared IRQ scratch and distributor
setup are serialized. This design is not a concurrent SMP interrupt facility.
The primary affinity owns UART writes, including fatal reports; secondary faults
currently cause an eventual primary timeout rather than interleaved serial text.
Timer enablement/cleanup and record publication have only host/build evidence.

Dispatch follow-up: the probe now calls CPU_ON64 serially for enabled non-self
runtime affinities only after CPU_ON64/AFFINITY_INFO64 feature support and an
exact OFF result. Context is the unique list index; nonzero ready slots are
rejected. It waits for the cache-disabled record publication with a one-second
CNTVCT/CNTFRQ bound and a ten-million-iteration stall cap, then checks affinity,
EL1, M/C/I clear, all DAIF masked and equal frequency. CPU_ON errors, timeouts
or invalid records stop the caller; slots are never retried or reclaimed in this
run. There is no CPU_OFF or cleanup of an already-started CPU: it stays parked
until board reset. An SMC itself can still hang without a watchdog. This is
compiled diagnostic code, not a claim that any secondary has started on the Pi.

tests/test_secondary_model.py now runs the production dispatch body with
explicit PSCI, counter and barrier substitutes under address/undefined-behavior
sanitizers. It checks arguments, result validation and stop/no-further-start
behavior, including a stalled counter and nonzero primary affinity. Ready-state
publication is injected by the model; cross-CPU visibility, actual SMC and the
assembly entry remain hardware validation obligations.

Secondary entry is now implemented but not dispatched: probe_secondary_entry
accepts only slot contexts 0–3, requires EL2 with MMU/caches off, selects a
dedicated 16 KiB normal stack and 16 KiB fault stack, and branches into the same
EL1 normalization as primary. It never clears BSS. TPIDR_EL1/EL2 are reserved
by this diagnostic for the CPU's fault-stack pointer. The secondary records
MPIDR/EL/SCTLR/DAIF/CNTFRQ/CNTVCT, performs DSB before publishing ready, then
parks. This is a cache-disabled one-writer record protocol, not general SMP
locking or cache-coherency proof. Caller-side ownership, record validation and
timeouts remain required before CPU_ON. Fatal logging still needs console
coordination when multiple CPUs are live. No timer IRQ runs on a secondary yet.

Runtime integration supersedes the initial static candidate inventory below:
enabled affinities now come from rpi5_fdt_cpus. The source handoff is a uint32
dtb_ptr32 accepted when stub_magic is cleared. TF-A maps the containing aligned
2 MiB region plus the next 2 MiB as non-secure memory, but does not validate
the FDT contents in this Pi 5 setup path. The probe's access wrapper bounds the
header/blob to this window and the 32-bit address space, rejects unaligned or
ATF-reservation pointers, then invokes native structure/binding validation.
Readable, stable RAM is a trusted firmware ABI precondition, not something
these numeric checks prove. Physical faults park through fatal diagnostics.
This contract applies to the pinned default DTB handoff, not an arbitrary
RPI3_PRELOADED_DTB_BASE override. No runtime hardware result exists yet.

The pinned board DTB CPU reg values are 0, 0x100, 0x200 and 0x300, all with
enable-method=psci. rpi3_topology.c validates affinity fields and, when MPIDR.MT
is set, requires Aff0=0 before shifting affinity for platform core indexing.
Do not replace these target affinities with array indices 0–3.

The EL1 probe now queries AFFINITY_INFO64 for those four candidate values with
lowest_affinity_level=0, but only after PSCI_FEATURES reports support. MPIDR is
masked with 0xff00ffffff to preserve Aff3/Aff2/Aff1/Aff0 while excluding flags.
An unknown boot affinity skips the candidate inventory. Raw 64-bit responses
are retained; only exact 0/1/2 are labelled ON/OFF/ON_PENDING. This is a static
diagnostic candidate list, not runtime CPU discovery or authority to power on
a CPU. Secondary startup still needs runtime topology, separate stacks, an
entry path that does not clear primary BSS, and a publication/timeout protocol.

The upstream Pi 5 documentation warns that its DRAM is not protected between
secure and non-secure worlds. This port must not be presented as providing
Apple secure-boot or secure-world isolation guarantees.

Source: [pinned Raspberry Pi TF-A tree](https://github.com/raspberrypi/arm-trusted-firmware/tree/332b62e0443b004287d2cfc032a70bba6fb86f35).
