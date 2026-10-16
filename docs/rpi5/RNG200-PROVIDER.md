# RNG200 boot-seed provider investigation

## Approved derivation implementation, not runtime integration

`firmware_seed_tree.c` provides the tree transaction: preflight seeded length,
invoke a supplied consume-once callback, temporarily attach a 256-byte
random-seed property, encode, restore the board-tree graph and wipe the derived
scratch. Post-consumption encoder failure erases the intended output extent;
preflight/consume failure leaves output unchanged. The caller must supply
disjoint valid buffers and validated FDT source/version. Host sanitizer tests
mock consume/encode to verify order, graph restoration, failure cleanup and
canaries; they do not replace actual serializer tests or board integration.
Build `bl33-probe-4s2j34i1` succeeds. No runtime caller or real seed access yet.

Runtime version guard implemented in `rpi5_firmware_seed_version`: exact
`/chosen/bootloader/version` 41-byte NUL-terminated identity
`6219bf00832ac18711372008da5ed99cf1c62ecf`, and four-byte build-timestamp
`6a 31 e5 1d`. Both were checked via metadata-only reads in recovered Linux.
The helper uses the structural/duplicate-checking property parser and validates
lengths/extents before comparing these nonsecret values. Synthetic tests mutate
every identity/timestamp byte and inject length, bounds and absence failures.
It is a trusted-firmware consistency guard, not cryptographic attestation.
Standalone enforcement and real-seed integration remain pending; no seed data
was accessed during the metadata check.

Candidate `bl33-probe-urryvlpk` adds a synthetic board self-test after kernel
readback. The isolated wrapper now rejects null/wrapping argument ranges and
scratch-stack overlaps before switching stacks. Self-test fills scratch with
0xa5, confirms an overlapping-output call is rejected without changing it,
derives from public bytes 0..63, checks source erasure and the entire 16 KiB
stack, compares the output's SHA256 with an independent Python oracle, then
checks retry rejection and erasure again. Its output is cleared and never
attached to any tree or passed to XNU. No real seed values are read or hashed.
Build succeeds; board execution remains pending. Runtime firmware version and
writable FDT ownership still need integration before actual seed consumption.

Isolated-stack candidate `bl33-probe-dt8tlv9t` adds an AArch64 wrapper around
consume-once. It switches to a 16 KiB probe-owned BSS stack, restores the caller
stack, wipes the full scratch stack with explicit stores and DSB, clears x1–x17,
and restores saved x18–x20/LR. Other callee-saved registers are preserved by the
C ABI; crypto C is compiled general-register-only. The build conservatively
sums all emitted frames in the nonrecursive seed/HKDF/HMAC/SHA256/codec units
and enforces a 512-byte margin. Disassembly inspected for stack restoration,
wipe loop and register cleanup. This is not hardware execution evidence.
All arguments must be disjoint from the dedicated stack and the wrapper must
not be reentered; runtime caller checks are still pending. Fatal exceptions
do not guarantee erasure and must never proceed to XNU. No real seed consumed.

`firmware_seed_fdt.c` adds metadata-only source selection through the existing
structural/duplicate-checking FDT property parser: exact `/chosen/rng-seed`,
64-byte length, exact FDT total and in-bounds value extent. Output may not alias
the FDT. A poison-pointer mock test confirms this selector never dereferences
property bytes; it tests metadata propagation, not the separately tested FDT
parser. Build `bl33-probe-ntj1tv5h` succeeds. Runtime caller must still establish
writable retained-FDT ownership and pinned firmware provenance; selection
alone does not establish either. No real seed consumed or logged.

`rpi5_firmware_seed_consume` adds a single-primary consume-once transaction.
It validates disjoint source/output/state ranges before accessing state or
changing anything, rejects a previously consumed state, marks accepted input
consumed before derivation, and clears the source on both successful derivation
and all-zero-input failure. Invalid metadata preserves all buffers. Tests cover
success, retry, metadata rejection, state aliasing and failed derivation.
The caller must never reset the state for a boot, and must first validate the
source's writable FDT ownership/version. This is not a concurrency primitive.
No real firmware seed is accessed; library stack residue remains a separate
runtime integration prerequisite.

The user approved the firmware-derived alternative. `firmware_seed.c` now
implements HKDF-SHA256 through the existing pinned, unmodified BearSSL source:
64-byte input, absent salt (HKDF's zero salt), ASCII info
`rpi5-xnu/boot-seed/v1` without NUL, and 256-byte output. This provides derived
seed material, not 256 bytes of raw entropy. Security is bounded by input
entropy and the cryptographic construction; no measured firmware entropy bound
is claimed. Existing raw-word collector semantics remain unchanged.

Host sanitizer tests pass RFC 5869 case 1 and a Python HMAC-based independent
oracle for this exact format. They cover invalid lengths, null input, alias,
all-zero rejection, source preservation and output canaries. The wrapper wipes
its explicit HKDF context/output scratch; BearSSL internal stack temporaries
are not guaranteed erased by those wipes. Runtime integration must address
that residue, fresh firmware provenance/version, one-time source consumption,
source erasure, and output ownership. No real seed has been read or logged.
Build `bl33-probe-u_8itxd5` succeeds but does not invoke the new provider.

## Alternative contract under review: firmware seed derivation

The pinned EEPROM release notes at commit
`279e8b86fd038f026a8daad1223305a15a7d1f2b`, lines 135–141, were fetched again
and confirm the May 26 fix makes Pi 5's rng-seed/kaslr-seed use bootsys HWRNG
output. Actual standalone metadata has already established a 64-byte rng-seed.
This is vendor source provenance, not an independently measured entropy bound.

Source audit of `osfmk/prng/prng_random.c` distinguishes the ARM 256-byte
request from entropy strength: the function checks returned length, uses the
first 64 bytes for kprng, and uses the other three chunks for separate derived
seeds. Passing length alone is not security qualification. Conversely the
length check does not prove a requirement for 2048 independent entropy bits.

[RFC 5869](https://www.rfc-editor.org/rfc/rfc5869.html) supplies an established
extract-and-expand mechanism for producing longer pseudorandom key material
from a secret input. A potential alternative is a separately named firmware
seed provider, with domain-separated derivation to the 256-byte XNU interface.
It must not masquerade as the existing health-accepted raw-word callback.
Derived length does not increase input entropy. Firmware freshness, secrecy,
version binding, single-use consumption and erasure remain necessary.

This is a design alternative, not implemented or qualified. Before adoption,
specify the security-strength assumption, salt/info and algorithm, use a vetted
implementation with published vectors, review the four downstream seed uses,
and add metadata/ownership/consume-once failure tests. No seed values were
collected or logged. The existing raw 256-byte provider contract is unchanged.

## Standalone metadata evidence

Actual BL33 run `serial-capture-1awe85cm`, candidate `bl33-probe-uqzluws5`
(probe SHA-256 `4c8843bbef2c39042dcc6462000cd2b209b9b3e9c19d58419ae8231476bed277`),
reports `/chosen/rng-seed` length 64 bytes, `kaslr-seed` length 8 bytes,
and `random-seed` absent. Only metadata was inspected; no seed values were
read, hashed, copied or logged by the diagnostic. This supersedes inference
from the post-Linux tree, where rng-seed was absent.

The firmware property is not a direct 256-byte source for the current contract.
Do not concatenate the two properties without evidence of independence, or
pad/expand them while claiming 256 raw fresh bytes. Source qualification and
an appropriate runtime provider remain open. No seed contract was changed.

Latest metadata-only Linux check: `/chosen/rng-seed` and `random-seed` are
absent; `kaslr-seed` has an 8-byte inode size. No property contents were read.
Linux may consume/remove firmware properties, so these observations do not
establish standalone boot metadata. Candidate `bl33-probe-uqzluws5` adds
runtime property presence/length reports after FDT structure validation. It
never dereferences the returned property value; a host test uses an invalid
data pointer and offset to enforce this diagnostic boundary. Build succeeded;
standalone evidence is pending. Do not treat this as seed collection or source
qualification, and do not expand an 8-byte property to claim 256 fresh bytes.

Status: identified hardware and source behavior, **not a qualified loader
entropy provider**. No seed collection or RNG register writes performed.

## Implemented transaction layer

`loader/rpi5/boot_seed.c` collects exactly 256 bytes from a bounded nonblocking
provider callback, with a whole-transaction counter deadline and finite polling
budget. It rechecks time after every callback, rejects unknown/fault statuses,
publishes output only after complete success and clears volatile scratch on all
collection exits. The polling budget terminates a stalled counter; a callback
that itself blocks violates the interface and cannot be interrupted here.
Counter wrap is supported within the documented less-than-2^63 tick interval.

The host sanitizer test covers exact-size completion, partial failure, delayed
availability, invalid provider state, stalled counter, counter wrap and exact
deadline boundaries, plus output canaries and invalid inputs. The source also
cross-compiles for freestanding Cortex-A76. It is linked for build checking but
not called by the probe and has no MMIO implementation. Tests use deterministic model words only;
they are not an entropy fallback. Clearing stack scratch does not guarantee
erasure of register spills or source-provider storage.

## XNU consumption boundary

The current non-SPTM `PE_get_random_seed` in `pexpert/gen/pe_gen.c` finds
`/chosen/random-seed`, copies up to the request length and zeros those property
bytes in place. It returns zero for an all-zero consumed seed. ARM
`bootseed_init_bootloader` in `osfmk/prng/prng_random.c` requires the full
256-byte request and panics on a short result. The collector therefore also
rejects an all-zero transaction without modifying output; its model test covers
this failure. Nonzero output still does not establish entropy quality.

Use exactly 256 raw bytes for this property: no integer byte swapping, string
terminator or prefix. The encoded Apple tree must remain writable and owned
through consumption. The serializer copies property bytes, so the collector's
output becomes a second seed-bearing buffer: clear that source after successful
encoding, and clear both buffers if a later handoff step fails. XNU clearing
its property does not clear the loader's source copy. Do not serialize a real
seed into an archived host artifact; collect and encode only at runtime after
the source and handoff ownership contracts have passed.

The `seed_tree.c` wrapper now preflights the complete graph and added property's
capacity before collecting, refuses an existing random-seed property, preserves
other chosen properties/children, and clears its temporary seed after encoding
or collection failure. Tests compare encoded bytes with the regular serializer
using deterministic model words and verify failed collection leaves output and
length untouched. This does not validate the rest of the board tree. The seed
collector and wrapper are now included in diagnostic builds for freestanding
compile/link checks, but neither is called by the probe; no hardware provider
has been enabled.

## Early-stack budget

Probe builds now sum the reviewed seed/tree C call chains using compiler stack
usage, including the serializer's declared recursion limit plus the leaf frame.
The observed maximum chain before this check was 9328 bytes on a 16384-byte
early stack, leaving 7056 bytes for callers and other requirements. The build
rejects an exhausted budget, missing frame evidence or an unreviewed depth.
This is not a whole-program stack proof: provider callback frames, runtime
callers, exception paths and hardware execution still require review. Do not
enable the hardware collector merely because this local budget passes.

## Evidence, 2026-09-10

New firmware-source evidence: the official
[2712 EEPROM release notes](https://github.com/raspberrypi/rpi-eeprom/blob/master/firmware-2712/release-notes.md)
state that the 2026-05-26 release corrected the entropy source for FDT
`rng-seed` and `kaslr-seed` on Pi 5 to use the HWRNG enabled by bootsys.
That is the release observed on this board. This establishes a vendor-described
source rationale worth evaluating; earlier notes that treated firmware seed
provenance as wholly unknown are superseded to that extent. It does not establish
the runtime property length, independence between properties, sufficient entropy,
or safe copy/erase behavior. Do not concatenate potentially related seeds or
pad a short seed to claim 256 bytes of fresh hardware entropy. Inspect only
property metadata first; never log or hash real seed contents. Firmware seed
reuse/consumption and version pinning must be reviewed before integration.

The running Pi reports `107d208000.rng` as current and available hardware RNG,
bound to `iproc-rng200`. Its live compatible string is
`brcm,bcm2711-rng200`. This agrees with the existing translated MMIO candidate
[0x107d208000,0x107d208028), but Linux driver binding is not standalone readiness.

Raspberry Pi Linux branch rpi-6.18.y was resolved to commit
`cff533aec2fa601846766b32ff57204e0a61bed7`. Reviewed
[driver source](https://github.com/raspberrypi/linux/blob/cff533aec2fa601846766b32ff57204e0a61bed7/drivers/char/hw_random/iproc-rng200.c).
This identifies the inspected source, not the exact source of the installed kernel.

The BCM2711-compatible path differs from generic iProc initialization and reads.
It preserves an already-enabled generator; otherwise it programs a warm-up
threshold, FIFO threshold and sampling configuration. Reads wait for warm-up
and then FIFO availability. The warm-up loop has no deadline, and a waiting
FIFO read can also spin indefinitely. The generic path instead checks fault
status and attempts bounded restart. Do not mix those paths without validating
the hardware semantics. No driver code has been copied into the loader.

## Required implementation and acceptance

### Public documentation search boundary, 2026-09-10

The official [BCM2712 processor overview](https://www.raspberrypi.com/documentation/computers/processors.html#bcm2712)
describes the processor and peripherals but does not specify RNG200 startup or
health-status registers. Searching the text of the official
[BCM2711 peripheral manual](https://datasheets.raspberrypi.com/bcm2711/bcm2711-peripherals.pdf)
finds RNG interrupt references, not the needed health/startup contract; it is
also a different SoC. Neither source closes the provider qualification gap.
This is a statement about the inspected sources, not proof that no public
documentation exists. RP2350 TRNG documentation is not applicable to BCM2712.

If seeking vendor clarification, the concrete questions are: which RNG200
revision BCM2712 implements; valid health/status bits for its BCM2711-compatible
interface; required warm-up and post-reset discard conditions; clock/reset
ownership after firmware/BL31; and whether FIFO availability implies successful
internal health tests. No vendor message has been sent. Board observations can
test bounded startup/read behavior but cannot alone establish entropy quality
or the interpretation of undocumented health bits.

### TF-A fallback assessment

The pinned TF-A checkout at
`332b62e0443b004287d2cfc032a70bba6fb86f35` was inspected for an alternative
secure-monitor entropy service. `make_helpers/defaults.mk` sets `TRNG_SUPPORT`
to zero; `plat/rpi/rpi5/platform.mk` does not enable it, and the Pi platform
sources supply no `plat_get_entropy` or `plat_entropy_setup` implementation.
The existing BL31 link map contains no TRNG service/provider symbols. Thus the
presence of generic TF-A TRNG service sources does not supply this build with
an entropy service. No SMC entropy request was issued to the board.

The optional stack-protector path is a different facility, not a TRNG service:
`rpi3_stack_protector.c` calls `drivers/rpi3/rng/rpi3_rng.c`, whose word reader
polls without a deadline using an older control/status/data register interface.
Pi 5 platform defaults disable this stack protector. Do not enable it as an
entropy workaround or import that reader as a BCM2712 RNG200 implementation.
This source inspection rules out an already-implemented fallback; it does not
prove that a separately implemented TF-A RNG200 service would be impossible.

The next hardware-provider work still needs documented or qualified BCM2712
health/startup semantics. A source which merely returns nonzero FIFO words
cannot truthfully satisfy the existing `RPI5_SEED_WORD` health-accepted contract.
Keep the collector disconnected until those prerequisites are met. This does
not prevent a diagnostic-only BL33 run that explicitly stops before XNU.

### Independent implementation cross-check

TianoCore's
[BCM2838 RNG driver](https://github.com/tianocore/edk2-platforms/blob/2db572db2fead29fbb4b622b0ea954b2f2f93a62/Silicon/Broadcom/Bcm283x/Drivers/Bcm2838RngDxe/Bcm2838RngDxe.c)
was inspected on 2026-09-10 (master resolved to the linked commit). Its comments
describe Raspberry Pi 4 experiments: the bit counter increases during warm-up
and saturates, while FIFO availability is withheld until warm-up completes.
Consequently the Linux bit-count comparison alone must not be presented as
proof that the configured warm-up threshold has elapsed. The TianoCore reader
uses bounded FIFO retries, but its short per-word timeout presumes initialization
happened sufficiently earlier. An immediate standalone boot-seed request needs
an explicit startup deadline, not a copied short retry duration.

This source explicitly acknowledges missing register documentation; it does
not resolve BCM2712 health-status or reset semantics. Its Pi 4 timing observations
must not be asserted as measured Pi 5 timing. Source license is
BSD-2-Clause-Patent; no implementation has been imported.

Design consequence: model startup and steady-state collection separately, keep
the overall 256-byte transaction bounded even when words arrive intermittently,
and require FIFO availability before every destructive FIFO read. A saturating
bit count is not a freshness test. Do not claim that generic iProc health bits
are established for this compatible path by either reviewed implementation.

### Acceptance checklist

- Establish standalone clock/reset and exclusive-access prerequisites. Linux
  observations cannot establish the inherited firmware state after BL31.
- Confirm BCM2711-compatible status/health semantics on BCM2712 before relying
  on generic iProc fault bits or reset behavior.
- Bound all warm-up and FIFO waits using an established counter deadline plus
  a finite polling budget. Missing clock or stuck hardware must terminate.
- Collect the complete 256-byte boot seed or fail. Never publish a short seed
  or replace failure with timestamps, fixed data or a deterministic PRNG.
- Publish only after success; clear scratch on failure and after handoff. Never
  log seed bytes or their hash. Do not treat sample appearance as entropy proof.
- Test enabled/disabled inherited state, delayed/stuck warm-up, empty FIFO,
  health failures before and during collection, exact-size completion and
  cleanup in a register model before enabling actual hardware collection.
- Record the actual entropy-source rationale and standalone hardware results;
  host tests alone do not qualify its entropy or establish Gate 1 completion.

Next work is a reviewed BCM2711-compatible reader contract and bounded register
model, not wiring a generic RNG loop directly into the Apple device tree.
