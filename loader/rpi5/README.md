# Native Pi loader components — not an XNU loader

## Repeatable host build

Run `python3 tools/rpi5/build_probe.py --load-address 0x200000` from the repo.
This example address is only a host link test, not an approved board placement.
The pinned project-local Zig installation is required. Each invocation uses a
fresh `build/rpi5/bl33-probe-*` directory, compiles all native source files and
emits ELF, raw binary and a provenance manifest. No media is written.

The build checks static AArch64 ELF identity, entry, non-overlapping LOAD ranges,
no writable/executable segments, no undefined symbols/remaining relocations,
and agreement of raw bytes with file-backed LOAD ranges. It does not validate
instructions or firmware memory ownership. Two fresh builds on the current
host produced identical ELF/raw output; raw SHA-256:
09c0f7266d20ef36d1fd8fcfbcac3d9525a51f553e4c48a45db7b2aef8693abe.

## BL33 entry probe

Runtime FDT inspection also reports advertised RAM ranges through
rpi5_fdt_memory. The bounded eight-range inventory accepts explicit one/two-cell
addresses and sizes, sorts active ranges and rejects overlap/40-bit overflow.
It is not allocator input: reservation and live-image subtraction remain open.
`memory.S` supplies the compiler-required freestanding non-overlapping memcpy
using byte accesses; callers remain responsible for valid source/destination.

`ranges.c` provides bounded native subtraction of explicit exclusions from
sorted RAM, with atomic failure on malformed input or excess final fragments.
It does not discover reservations and is not yet allocator-integrated.
The host sanitizer test compares 1,000 generated cases to a bytewise oracle.
`memory.S` also supplies the compiler-required bytewise memset implementation.

Native reservation discovery now covers the FDT header map and bounded static
reserved-memory nodes with matching root widths/empty ranges. Disabled nodes
are skipped and reusable pools remain excluded. Dynamic requests (including
the pinned tree's CMA request), IOMMU policy and nested active reservations
stop discovery without returning partial output. Runtime reports this state;
it does not turn incomplete discovery into an allocation map.

`fdt.c` supplies native, allocation-free FDT framing validation over an already
readable buffer. It checks header versions, sizes, block alignment/overlap and
reservation-map termination/overflow, with a 16 MiB maximum total size. It also
validates structure nesting, property order/bounds, strings, padding and END.
The CPU extractor separately checks consumed-field and CPU-name/affinity
uniqueness, supports one/two address cells and at most four Cortex-A76 CPUs,
requires PSCI and retains disabled entries with an enabled-state mask. It uses
exact single-string compatibility and rejects container status properties;
other bindings require deliberate extension. General duplicate-name checking
and physical-reservation overlap policy remain absent.
These functions now supply the read-only PSCI affinity inventory from x0.
The access wrapper bounds an aligned 32-bit pointer above 0x80000 to TF-A's
4 MiB DT window (clipped at 4 GiB). It explicitly trusts the pinned firmware
handoff for readable, stable RAM; bounds checking does not establish physical
readability. A bad pointer can take the fatal exception path. Supported, offline
secondary CPUs are now started serially using dedicated stacks and bounded
record waiting; see TF-A-CONTRACT.md. They remain parked until reset. This
startup path has not run on the Pi. Each secondary now runs the bounded timer
IRQ test before publishing its record; primary validates the result serially.
UART writes are restricted to the primary. Initialized secondary fault handlers
publish a separate terminal fault record for primary-side logging; very early
or nested faults can still surface only as timeout.
Sanitizer tests include truncated/malformed fixtures and the local pinned Pi DTB.

probe_entry.S, probe_main.c and probe.ld form a limited native BL33 diagnostic
payload, not an XNU loader. It requires the firmware to load it at its linked
address, enter on one CPU at EL2 with MMU/data/instruction caches disabled and
pass the runtime FDT PA in x0. It masks exceptions, installs parking vectors,
establishes a 16 KiB stack, clears BSS and prints EL/MIDR/MPIDR/CNTFRQ/FDT_PA over
the pinned Pi UART10 address. It then establishes the single-primary EL1
transition described in docs/rpi5/TF-A-CONTRACT.md, reports EL1 control state
and CNTVCT, queries PSCI capabilities, inventories GIC IDs/CPU target mask,
runs masked timer-condition and one-shot single-core IRQ probes,
and performs serialized PSCI CPU_ON probes with per-CPU EL1, timer IRQ, target-bit
and feature records. It then parks before XNU loading. This path is not hardware-tested.
PSCI_VERSION and PSCI_FEATURES use the SMC conduit only after runtime FDT validation.
Raw 32-bit query results are diagnostics, not gate-pass
markers. A hung firmware SMC has no timeout/recovery in this probe.

The virtual-timer probe owns CNTV, programs an approximately 1 ms compare value,
keeps IMASK set and polls ISTATUS for at most one million iterations. It disables
the timer before reporting. The iteration bound is not a time guarantee; it
prevents a stalled counter from causing an infinite polling loop. An observed
condition does not establish GIC delivery, timer IRQ routing or frequency
accuracy. This masked test does not unmask interrupts. Invalid frequency/counter overflow stops
the test without enabling the timer.

The subsequent IRQ test is described in docs/rpi5/GIC-CONTRACT.md. It checks
for conflicting GIC state before enabling timer 27, uses bounded polling,
then restores controller state with readback. It has not executed on the Pi;
the existing host tests do not simulate this new interrupt-delivery path.

After stack/BSS initialization, vectors identify all 16 architectural slots
and report EL plus its ESR, ELR, raw FAR and SPSR using a separate 16 KiB
exception stack. Before reporting, the handler restores silent parking vectors
so a UART or stack fault during diagnostics cannot recursively call the logger.
This is fatal-only reporting, not recoverable exception handling. FAR validity
must be interpreted from ESR. Faults before initialization still park silently.
No deliberate-fault hardware test has yet verified this path.

UART mapping/clocking and firmware configuration must be reviewed before use.
The probe validates the runtime FDT, MMIO/timer/clock bindings and CPU inventory,
then exercises timer IRQs and PSCI CPU startup. It does not load XNU: the native
loader/planner helpers are built but not called by this entry path. The UART's
iteration timeout cannot recover a bus exception; a nested fault
in the diagnostic handler parks without further output.

The linker requires explicit LOADER_BASE. An earlier, pre-fault-handler host-only build at 0x200000 produced
build/rpi5/bl33-entry-probe.elf and .bin; the raw binary SHA-256 is
662ab0ee938a17a1de31a3b1ec2993c4197f3d699c8f0d09cc89b1feab73bcd6.
ELF LOAD memory spans end at 0x2057a0, including the non-file-backed stack.
These addresses have not been checked against the user's runtime FDT or other
firmware-loaded images. No boot-media configuration is supplied or applied.

`uart.c` supplies bounded polling transmit and drain operations for a
firmware-configured PL011. The caller must provide an accessible Device-memory
mapping, exclusive UART ownership and a nonzero polling budget. Success from
putc means acceptance into the UART, not completed transmission; drain requires
TXFE set and BUSY clear. It does not set clocks, baud divisors, pin mux or CR.
The iteration budget is not a time deadline and cannot recover from an MMIO
bus fault. Valid mapping and device identity must be established beforehand.

Native host tests use a register-array model, not hardware. The component
compiles for Cortex-A76 freestanding with no undefined symbols. The diagnostic
entry stub and single-primary EL transition above exist; kernel transfer remains
unimplemented. All-CPU normalization and hardware validation remain required.

## Historical toolchain checkpoints

The installed Apple clang 21 successfully compiles uart.c with
`--target=aarch64-none-elf -mcpu=cortex-a76 -ffreestanding -nostdlib`.
The host test verifies ELF64 little-endian ET_REL/EM_AARCH64, separately from
the Mach-O register-model executable. No ELF linker was found in PATH or the
standard Xcode/Homebrew LLVM/LLD locations. Before building a standalone image,
provide a pinned AArch64-capable ELF linker (such as LLVM ld.lld), record its
provenance/version, then validate the linked segments and entry. The Mac linker
is not a substitute for this ELF link step. No system toolchain was installed
or modified during this checkpoint.

Follow-up: a project-local Zig 0.16.0 download now supplies the ELF link driver.
Archive provenance/checksum are pinned in tools/rpi5/loader-toolchain.lock.json;
the verified archive and extracted tool remain under ignored build output.
Set ZIG_GLOBAL_CACHE_DIR to the project's build/rpi5/zig-cache for each invocation.
The command `zig cc -target aarch64-freestanding -nostdlib -fuse-ld=lld` linked
the Apple-clang-produced UART ELF object successfully. The resulting
uart-link-probe.elf has no dynamic section and separate read-only/executable
LOAD segments. Its entry is the ordinary UART function solely as a linker
probe: it has no boot prologue, stack or CPU setup and must not be booted.
No system install or global PATH change was made.
