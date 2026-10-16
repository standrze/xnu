# Pi provider startup contract — hardware startup observed 2026-09-12

Capture `serial-capture-a8bp8q85` explicitly reports crypto/PRNG registration
completion before IOKit. Current hashes, requirement audit, and limits are in
[GATE1-AUDIT.md](GATE1-AUDIT.md). The boot coordinator returns through real table
registration, entropy initialization, generator init/reseed and early-seed
clearing. This does not establish all later runtime algorithms or concurrency.
The historical entries below retain earlier implementation checkpoints; their
pending/unimplemented startup statements are superseded by this observation.

## Seed publication deferred until diagnostic CPUs are quiescent (2026-09-11)

The primary now prepares and verifies the kernel copy without consuming the
firmware seed. It retains only pointers and placement metadata in static probe
BSS. After the secondary CPU tests return successfully and the primary timer
interrupt test verifies cleanup, it consumes the pending preparation once and
runs the seed transaction. Failures in the CPU/interrupt checks therefore occur
before publication of seed-bearing boot data. The diagnostic still erases that
data and stops without calling `rpi5_transfer`.

The source-order regression test covers this sequencing (not hardware behavior),
and the reviewed stack paths now reflect publication from `probe_el1_main`
rather than from the nested planner. All 159 host tests passed in 38.623 seconds.
Fresh build `build/rpi5/bl33-probe-5pi5svvy` succeeded. The preceding build
`bl33-probe-tjm69xcr` passed the native Mach-O copy/layout comparison for kernel
SHA-256 `e203b4cd5e0a240faf9e862a01d815b6b51e2bd28b2bcbe81f6512353e2f6765`.
Neither image was installed. Gate 1 remains unproven: actual guarded transfer,
watchdog policy at entry, and XNU hardware execution remain pending.

## Retained boot-data transaction (2026-09-11)

`loader/rpi5/boot_data.c` now provides `rpi5_boot_data_commit` for the
pending transfer path. It validates disjointness using the entire encoded
tree scratch capacity, publishes and reads back physical args/tree, then
wipes the full redundant scratch buffer while retaining the destinations.
Invalid preflight mutates nothing; post-preflight failure consumes scratch
and clears destinations. This avoids erasing XNU's only seed-bearing tree
on a successful handoff. Existing diagnostic publication behavior is unchanged
and no transfer call has been enabled.

Host tests cover retained args/tree, complete scratch wiping, canaries,
insufficient capacity and overlap involving only the extra wipe capacity.
The focused boot-data/stack checks pass under their configured sanitizer and
compiler checks, and the diagnostic BL33 still builds. Actual handoff wiring,
post-publication failure cleanup, watchdog ownership and physical execution
remain unfinished.

## Activation-kernel loader preflight (2026-09-11)

Built diagnostic BL33 `build/rpi5/bl33-probe-m91a7z6y` with the activation
kernel e203b4cd5e0a240faf9e862a01d815b6b51e2bd28b2bcbe81f6512353e2f6765.
`compare_native_macho.py --post-cma-layout` agrees on 18 segments, 93,496
local relocations, 17,367,040 materialized bytes and 16,306,824 container
bytes. Entry remains fffffe00074c8488, targeting start_first_cpu at
fffffe00074ca05c. This is host-buffer/layout evidence only. The probe still
erases published args/tree and stops before XNU, so it must not be mistaken
for the pending transfer-enabled image.

Read-only SSH checks reconfirm kamidana at 192.168.4.23 running Linux
6.18.34+rpt-rpi-2712 from /dev/nvme0n1p2. The 119.4 GiB SD has an unmounted
512 MiB XNU_PROBE partition. Leszy at 192.168.4.76 exposes the same Debug
Probe E66480454F719939 serial interface as ttyACM0. No media writes or reboot
were performed. Before transfer, preserve verified physical boot data,
erase only redundant secret copies, retain a bounded watchdog and confirm
secondary/timer quiescence. Those loader changes remain unfinished.

## Opt-in startup activation build (2026-09-11)

`rpi5.py build --with-crypto-candidate --activate-crypto` now enables an
experimental call after SYSCTL initialization and address-permutation seed
setup, before PE_init_iokit. The CLI rejects activation without the candidate
option; make also rejects startup activation without an explicit candidate
object. Both inherited candidate and activation variables are removed from
the make environment. Default and link-only builds do not activate it.

The exploratory activation build with `--allow-toolchain-mismatch --jobs 4`
succeeded in `build/rpi5/run-hsi3in23/manifest.json`, with
startup_enabled=true and unchanged source during build. Kernel SHA-256:
`e203b4cd5e0a240faf9e862a01d815b6b51e2bd28b2bcbe81f6512353e2f6765`.
The compiled startup.o has a BRANCH26 relocation to the coordinator at
0x1048, before PE_init_iokit at 0x109c in kernel_bootstrap_thread. This
proves compiled call placement, not runtime registration success. The
existing early-read_random diagnostic still fails closed if an overlooked
earlier consumer exists. Startup log checkpoints bracket registration.

No SD image was changed and no XNU instruction has executed on the board.
Loader data-retention/transfer, watchdog/recovery preparation and hardware
evidence remain required before declaring Gate 1 complete. This section
supersedes historical statements below that no coordinator call site exists.

## First kernel link with candidate provider (2026-09-11)

The opt-in command `python3 tools/rpi5/rpi5.py build
--allow-toolchain-mismatch --with-crypto-candidate --jobs 4` now builds the
provider from source, verifies its object/source hashes against its manifest,
and passes an explicit RPI5_CRYPTO_CANDIDATE_OBJECT to BCM2712 make. The
object is a link prerequisite and the coordinator symbol is retained without
being called. Inherited candidate-object overrides are removed. The kernel
build manifest records candidate artifact hashes and startup_enabled=false.
Default builds do not opt in.

After a sandbox-denied sysctl attempt, the permitted local build succeeded:
`build/rpi5/run-ffdeeyof/manifest.json`, source unchanged during build.
The resulting kernel SHA-256 is
`58905cc8342ec688f3200b7b6918d01c6d7670dc8d78193fd61796ced24926e1`.
Inspection of its unstripped symbol table confirms rpi5_crypto_functions,
rpi5_crypto_platform_start, rpi5_prng_platform_start and
rpi5_chachapoly_functions are present. This supersedes earlier notes that
the candidates had never been linked into a kernel, but not their runtime
cautions: no coordinator call site exists, no provider has executed, and
the SD image was not updated. Toolchain mismatch remains exploratory.
Startup-order closure, activation and guarded hardware evidence are still
required for Gate 1.

## Startup-inclusive link check (2026-09-11)

`probe_crypto_table.py --kernel-adapters --with-startup` roots dependency
selection at the coordinator rather than just the table. The successful
`build/rpi5/crypto-table-probe-17x817br/manifest.json` compiles 77 units and
links 70, including generator, refresh, provider, binding, platform and
coordinator. External references are constrained to the existing kernel's
memory/stack-protector functions, CPU/startup/crypto globals, early_random,
read_random, registration routines, panic and the five mutex/group services.
No candidate-to-candidate reference remains unresolved. This does not link
or execute the real kernel entropy/registration functions, and no call site
or boot image has changed.

Further VM source inspection: vm_map_range_random_uniform is used by user
map range configuration (which excludes kernel maps); swap_crypt_initialize
is invoked by vm_swap_encrypt rather than vm_mem_bootstrap; generate_jop_key
is conditional on ptrauth_calls. These observations narrow earlier-consumer
questions but are not an exhaustive compiled call-graph proof.

## Candidate coordinator (2026-09-11)

`rpi5_crypto_startup.c` now sequences crypto-table registration before
`rpi5_prng_platform_start`, so entropy initialization's SHA-512 calls have
a table. It checks boot CPU, completed SYSCTL but not completed EARLY_BOOT,
and unpublished crypto globals. Failed table registration stops before PRNG
startup. Host service-stand-in tests exercise each precondition, registration
failure, successful ordering and duplicate-start rejection; the actual unit
compiles with recorded kernel flags. It has no call site or STARTUP hook and
is not selected in the build. These tests do not execute real locks/entropy.

The proposed call site is in kernel_bootstrap_thread after SYSCTL and before
PE_init_iokit. The observed locks.c RNG use is lck_bench_main after user copyin;
kalloc.c's is kalloc_type_test_policy, not ordinary allocation bootstrap.
InitIOKit invokes IOLibInit, OSlibkernInit and startup-extension machinery,
so registration should precede it. This narrows the candidate placement but
does not yet exclude earlier indirect consumers or prove real mutex/entropy
behavior. That audit remains required before enabling the coordinator.

## Registration publication guard (2026-09-11)

BCM2712 `register_crypto_functions` now checks every top-level table slot
before publishing g_crypto_funcs or crypto_init. The inline check in
`libkern/crypto/rpi5_crypto_slots.h` requires all 56 fields to be non-NULL;
other platforms retain their existing behavior. This closes the structural
gap where a non-NULL but incomplete table could mark crypto initialized.
Real-header tests independently remove each declared slot and require
rejection. The registration-body test checks that failed publication leaves
global state unchanged; it uses a small presence-check stand-in, while the
real presence helper is exercised separately. The full registration unit
also compiles with recorded libkern kernel flags. This remains a structural
guard, not a validation of nested methods, cryptographic behavior or timing.

Startup inspection also confirms PE_init_iokit runs before EARLY_BOOT in
kernel_bootstrap_thread, and startup_phase during a callback is set to that
callback's subsystem minus one. An EARLY_BOOT hook alone would not precede
IOKit; a PERCPU hook would not satisfy the candidate's completed-PERCPU guard.
Do not add either hook by phase-name intuition. Earlier consumers and the
mutex/per-CPU requirements still need the complete ordering audit before
registration is enabled.

## Aggregate candidate table (2026-09-11)

`osfmk/prng/rpi5_crypto_table.c` now explicitly maps all 56 top-level
`crypto_functions` fields to the candidate digest, HMAC, cipher, padding,
random and RSA implementations. `test_crypto_table.py` derives the current
field names from the local XNU declaration and checks exact set coverage,
without duplicate or NULL initializers. The aggregate translation unit
compiles with recorded BCM2712 flags, checking actual callback/descriptor
types rather than stand-in declarations.

This is not a completeness certificate for nested mode methods, algorithm
semantics, dependency linkage or runtime behavior. In particular the existing
ECB round-key compatibility question, kmem handle semantics, RSA edge cases
and startup ordering remain subject to the audits below. No registration or
STARTUP hook is present, and this file is not selected in the kernel build.
`python3 tools/rpi5/probe_crypto_table.py` now performs the aggregate crypto
link check: 71 adapter/primitive units compile for arm64 Cortex-A76 with
freestanding, general-register-only flags, then link into one relocatable
object. The clean BearSSL revision is checked before compilation. The
undefined-symbol set must exactly match bzero, memcpy, memset, memcmp,
memmove and read_random. Clang emits bzero for several zero-initialized
cipher contexts; it is an existing XNU memory primitive. All candidate
crypto and BearSSL references resolve. The successful run is
`build/rpi5/crypto-table-probe-hxpcbkfs/manifest.json`, containing commands,
compiler identity, source hashes, object hash and dependency list.

This check excludes the ordinary PRNG implementation and startup adapter,
which supply the read_random boundary. It is neither a final kernel link
nor evidence of first-consumer correctness, stack bounds or hardware startup.
The audit now derives an object-level dependency closure rooted at
`_rpi5_crypto_functions`, rejecting duplicate definitions or a missing root.
The latest run `build/rpi5/crypto-table-probe-za8x334o/manifest.json` compiles
71 units but links only the 64 reachable units; seven unused i31 helper
objects are omitted, with the expected external dependency set unchanged.
Selected/omitted source paths are recorded. Unit tests cover transitive
references, cycles, external symbols, unused objects and invalid roots or
duplicate definitions. This is object-level selection, not proof that every
function within a retained object is used.

Build integration inspection confirms `rpi5.py` removes inherited library
overrides and `MakeInc.def` restricts BCM2712's LD_KERNEL_LIBS to the explicit
compiler-runtime input. Preserve these controls: provider integration needs
an explicit source/provenance path, not a hidden environment override or an
untracked probe-object dependency. Actual kernel build selection remains
unfinished.

`probe_crypto_table.py --kernel-adapters` now recompiles every candidate
adapter with the recorded `prng_random.o.json` BCM2712 command, preserving
its kernel macros, ABI settings, include roots and working directory while
redirecting object/dependency outputs. BearSSL primitives retain the explicit
freestanding Cortex-A76/general-register-only command; this is deliberately
a mixed build check, not a claim that upstream code passed every XNU warning.
The flags-record hash is included in the manifest. Run
`build/rpi5/crypto-table-probe-0xf1yrve/manifest.json` links the same 64-unit
closure successfully. Its only extra external references are the expected
kernel stack-protector guard/failure symbols. The combined object still
excludes PRNG implementation/startup and has not been added to a boot image.

## ChaCha20 streaming preparation (2026-09-11)

`bsd/netinet6/esp_chachapoly.c` processes individual mbufs in place with
arbitrary lengths. BearSSL's raw ChaCha20 API discards unused partial-block
keystream, so calling it independently for each mbuf is not compatible.
The new internal `rpi5_chacha_stream.c` retains a 64-byte pad and position,
starts AEAD text at counter one, and rejects requests past (2^32-1) blocks
before modifying state or output. Exact in-place and disjoint buffers are
supported; partial overlap is rejected. State must be initialized and
serialized by its caller, with input/output disjoint from state.

Host tests check all 258 splits of a 257-byte message against BearSSL's
one-shot result, byte-at-a-time in-place decryption, and consumption of the
last legal counter block in two pieces followed by unchanged-state rejection
of further output. ASan/UBSan and recorded kernel translation-unit checks
pass. This tests buffering, not an independent ChaCha conformance vector.
Poly1305 streaming now has an internal candidate in `rpi5_poly1305.c`,
adapted from the pinned MIT-licensed BearSSL `poly1305_ctmul.c` with its
copyright/license retained. It preserves accumulator/key state across calls,
zero-pads only at explicit AEAD segment boundaries, and wipes state on final.
It is deliberately not a general unpadded Poly1305 interface. An independent
Python big-integer oracle checks lengths 0..65 and every two-part split,
including tag canaries, idempotent padding and final state wiping under
ASan/UBSan. The kernel translation unit also compiles. Multiple-segment
AEAD length-footer vectors and broader key patterns remain to be tested.
`rpi5_chachapoly.c` now combines these primitives into an internal AEAD
state machine, with a size assertion against XNU's context capacity. It
derives the one-time MAC key at counter zero, pads AAD and ciphertext at
their boundaries, appends the little-endian length footer, and compares all
16 tag bytes on decryption without overwriting the supplied tag. It rejects
AAD after text, direction changes, and reuse after finalization. Decrypted
output is unauthenticated until successful finish. Caller-owned buffers must
remain disjoint from state; exact in-place text processing is supported.
Host tests compare 64 AAD/text length pairs, all two-part text splits and
bytewise AAD against BearSSL's one-shot AEAD, with in-place decryption,
per-byte bad-tag tests, state checks and canaries under ASan/UBSan. The
kernel translation unit compiles. The fixed `KAT_POLY1305` known-answer
fixture from pinned BearSSL's tests now also checks every two-part split of
both AAD and plaintext, without calling BearSSL to compute the expected
ciphertext/tag. Additional checks cover invalid direction, NULL output,
partial overlap, SIZE_MAX text, NULL AAD/tag, overflowing AAD length and
exhausted text counter; rejected operations preserve state/output. This is
host evidence, not live authentication or startup evidence. XNU
callback bindings now exist in `rpi5_chachapoly_binding.c` for init, reset,
setnonce, AAD, encrypt/decrypt and finalize/verify. They copy the private
representation through XNU's context storage, check a marker and state
bounds, reject buffers overlapping that storage, and wipe temporary copies.
Reset retains key/nonce but clears per-message state; a new setnonce is
required before text. Verification mismatch consumes the message and returns
CCERR_INTEGRITY, whereas invalid call order returns CCERR_PARAMETER. Tests
exercise repeated reset/setnonce cycles and successful/failed authentication
through the actual callback types with the fixed known-answer fixture.
Kernel translation-unit checks pass. The nonce-increment lookup is resolved:
Apple's `ccchacha20poly1305/src/ccchacha20poly1305.c`, Git blob
`96e59142ea805fc98b297b83dbd9c20dd502486e`, exposes an unimplemented
`incnonce` that returns 1. The candidate now provides the same non-mutating
failure behavior rather than a NULL pointer or an invented increment rule.
Tests verify context/nonce preservation and the NULL-argument failure case.
Source metadata and the function were read through GitHub's contents API;
no Apple implementation was imported. All ten callback slots are populated,
but table presence alone does not establish complete-provider correctness.
The host harness now compiles and executes the unchanged
`libkern/crypto/corecrypto_chacha20poly1305.c` wrappers against the candidate
table. Every plaintext split of the fixed known-answer fixture passes through
reset/setnonce/AAD/encrypt/finalize and in-place decrypt/verify, alternating
valid and invalid tags. Verification preserves the supplied tag and consumes
the context after either authentication result. The wrappers reject repeated
verification, setnonce without reset, context-overlapping input/output/tag,
NULL nonce/context and a foreign descriptor without changing valid state or
output. Recorded libkern flags also compile the unmodified wrapper unit.
Dependency auditing and registration remain unfinished; this table is still
not selected in XNU.
The standalone ChaCha text helper
alone offers no authentication and is not a complete crypto-table callback.

## RSA adapter audit and preparation (2026-09-11)

The concrete in-tree consumer in `bsd/kern/chunklist.c` imports a public
modulus with exponent 65537 and verifies a SHA-256 digest. The libkern wrapper
sets context capacity to 4096 bits even for smaller keys: import must not
mistake that capacity for the mathematical modulus length. The public context
layout in `ccrsa.h` contains native-word modulus and exponent regions; a
pointer-bearing BearSSL key cannot simply replace that layout. Preserve
capacity and caller-owned storage, and reconstruct bounded big-endian key
views for verification without retaining caller input pointers.

XNU's digest OIDs contain the DER tag and length. BearSSL's verifier accepts
length followed by the OID value, and returns a recovered digest rather than
comparing it with the expected digest. The eventual callback must initialize
`valid` to false, validate the key/signature/digest, check the verifier result,
and compare the complete recovered digest before setting valid true. A
successful public-key operation alone is not signature authentication.

`rpi5_rsa_digest.c` now translates trusted MD5/SHA-1/SHA-256/SHA-384/SHA-512
OID constants with exact digest lengths, rejecting other encodings. NULL OID
currently supports only the documented 36-byte MD5+SHA-1 interoperability
case. This is candidate policy, not a claim of complete external-client
compatibility (additional digest identifiers require audit). Translation
returns internal constants, not caller-provided length prefixes. Tests cover
all five mappings, per-byte mutations, wrong digest sizes, and NULL cases
under ASan/UBSan; the real kernel translation unit compiles separately.
Candidate public-key import is now implemented in `rpi5_rsa.c`. It preserves
the caller's word capacity, strips leading zero bytes, checks bounded odd
modulus/exponent with 3 <= exponent < modulus, and stages native-word values
before writing. It records the actual modulus bit length and zeros unused
words. The Montgomery area is zero and its method pointer is NULL: this is
explicitly a paired-provider representation, not a usable general cczp
arithmetic context. Only the future paired verifier may consume it.

Host tests check 64 modulus lengths, each in exact-sized and fixed-4096-bit
capacity layouts, including modulus/exponent word positions, actual bit
length, untouched trailing storage, and rejection without context mutation.
The typed table fixture runs with ASan/UBSan; the translation unit compiles
with recorded kernel flags. Additional key edge cases remain unfinished.
`rpi5_rsa_verify.c` now exports bounded big-endian modulus/exponent views,
checks actual bit length and signature length, invokes the pinned BearSSL
i31 PKCS#1 verifier, and compares all recovered digest bytes before setting
`valid`. The caller must provide a writable `valid` disjoint from key and
inputs. An OpenSSL RSA-2048/SHA-256 fixture verifies under ASan/UBSan;
per-byte digest changes, a changed signature, short signature and incorrect
digest length fail, and the key remains unchanged. The kernel translation
unit also compiles. The OpenSSL matrix now includes 1024/4096-bit SHA-256
and 2048-bit MD5/SHA-1/SHA-256/SHA-384/SHA-512 (seven cases). Each case
also compiles and executes unmodified `libkern/crypto/corecrypto_rsa.c`
against the candidate table, exercising its fixed-capacity import and verify
wrappers. Invalid bit length, zero/oversized capacity, NULL key and NULL
valid output are checked; supplied valid outputs are cleared on rejection.
Legacy digests here are compatibility coverage, not recommended algorithms.
Malformed encoding coverage, NULL-OID verification, stack/dependency auditing
and live startup remain to be verified.
No RSA callback has been registered and this preparation closes no boot gate.

## Random API caller audit (2026-09-11)

The kmem candidate now exists in `rpi5_crypto_random.c`. A caller-owned
HMAC-SHA256 DRBG fits the 256-byte maximum and pointer alignment (compile-time
assertions). Initialization obtains a fresh 32-byte seed through the legacy
bridge and wipes the temporary seed. Generate/uniform subsequently use only
the local state and BearSSL; no reseed, lock, allocation, or ordinary-provider
reentry is performed. This is specifically the kmem contract, not a replacement
for the reseeded cryptographic kernel PRNG. Uniform uses rejection sampling.
Only initialized kmem handles are currently accepted by the newer callbacks;
other handle types and external-client compatibility remain to be audited.

Host tests exercise the actual table types, lengths 0..1025 against a direct
BearSSL stream, six uniform bounds including a high-rejection bound, two
initializations, output/state canaries, and no seed-service reentry during
generation under ASan/UBSan. Recorded kernel compilation flags also pass.
The host harness additionally intercepts only the trap intrinsic while
including the actual adapter body, and checks NULL/misaligned contexts,
invalid marker/vtable/digest pointers, NULL/wrapping/overlapping output,
zero uniform bounds and independently misaligned uniform output. It verifies
unchanged output and valid state on argument rejection, no extra seed calls,
and an unchanged state for zero-length generation. The uniform oracle counts
rejections and asserts that the rejection path actually executes. A separate
Python hmac/hashlib DRBG calculation checks the second context's first
32-byte output, independently of BearSSL. Trap interception is host-only;
the separately compiled kernel translation unit retains real traps.
These checks do not establish concurrency/interrupt reentrancy, broad DRBG
conformance, or boot-time execution. The
candidate remains unselected and unregistered pending those checks and the
remaining complete-provider work.

The legacy bridge is now a candidate in `osfmk/prng/rpi5_ccrng.c`: its
singleton callback delegates nonempty requests to `read_random` in at most
256-byte chunks, without narrowing the total size_t length. Invalid handles,
nonempty NULL output, wrapping address ranges and output overlapping the
singleton are rejected before service calls. Zero length makes no service
call. Acquiring the handle does not initialize the PRNG; nonempty generation
inherits BCM2712 read_random's readiness panic and ordinary provider locking.
It is consequently not the kmem lock-free implementation.

`test_ccrng.py` tests the actual crypto-table callback type, every length
0..1025, chunk count and output continuity, canaries and invalid arguments
with ASan/UBSan and a deterministic service stand-in. That stand-in tests
dispatch only, not entropy quality. The translation unit also compiles with
recorded BCM2712 kernel flags. The candidate is not selected or registered;
boot-time ordering and live PRNG behavior remain unverified.

The remaining random callbacks cannot all be aliases of `read_random`.
`libkern/libkern/crypto/rand.h` explicitly requires an initialized kmem
generator to acquire no locks, although its initialization may acquire one.
`vmgo_chunk_select_random_slot` in `osfmk/vm/vm_map_store.c` disables
preemption around `crypto_random_uniform(zpercpu_get(ks_rng_ctx), ...)`.
The candidate ordinary provider in `osfmk/prng/rpi5_prng_platform.c` uses
a mutex. Routing this kmem call through that provider would violate the
interface contract. This is a source-established implementation constraint,
not a board failure.

Revised remaining random implementation sequence:

1. Add the legacy `ccrng_fn` bridge to the ordinary, registered kernel PRNG;
   preserve the size_t request without truncating it to read_random's u_int.
   Reject invalid requests before touching output. Do not use the early
   generator as an implicit fallback or claim FIPS validation.
2. Provide a distinct caller-owned kmem state, no larger than the published
   256-byte limit and compatible with `ZALIGN_PTR`. Seed it during init from
   the ordinary provider; subsequent generate/uniform operations must neither
   lock nor allocate nor call back into the ordinary provider. Verify state
   size, alignment, independent seeds, and absence of those dependencies.
   Per-CPU allocation and preemption disabling establish serialization for
   the observed VM caller, not for arbitrary external consumers.
3. Implement uniform sampling with rejection rather than biased modulo-only
   reduction. Define and test zero-bound rejection, bound one, large bounds,
   and forced rejection sequences. Check context dispatch against the actual
   initialized handle; the header does not establish that NULL means the
   global generator.
4. Close registration ordering before selecting these candidates in the
   kernel build. `vm_map_store_crypto_init` runs at EARLY_BOOT/MIDDLE and
   initializes every per-CPU kmem context. The complete crypto table and
   ordinary PRNG must be available before that callback if it seeds through
   read_random. PERCPU precedes EARLY_BOOT in `kern/startup.h`, but the
   candidate's PERCPU guard alone does not prove an appropriate startup hook
   or exclude earlier consumers. Trace those before adding a hook.

This audit does not establish callback implementation, kernel linkage,
runtime locking correctness, or Gate 1 completion. No reboot is required
until a materially changed, checked boot candidate is available.

The successful kernel build does not establish this sequence. All provider
registration and hardware evidence below remain required for Gate 0/1.

Current source audit confirms there is no in-tree call to either registration
function in the selected platform code. `read_erandom`/`read_frandom` explicitly
retain the early generator until registration, whereas `read_random` directly
dispatches refresh/generate and needs the ordinary provider. BCM2712 now panics
explicitly when read_random precedes registration, instead of calling an unset
callback. A host test compiles the actual function and verifies no callback or
output mutation occurs on that path; ready-state dispatch remains unchanged.
This is diagnostic coverage, not a provider or a fallback.

Do not choose the registration phase from a name-only search: the read_random
hits in kalloc_type_test_policy and epoch_sync's random_delay are test paths,
not proof of an early bootstrap call. entropy_init initializes its own mutex
after its first SHA-512 calls; this still requires the lock subsystem and a
complete crypto provider to be ready. The earliest ordinary consumer remains
to be established across indirect calls and IOKit startup.

Host wrapper compatibility is now checked by `tools/rpi5/probe_bearssl.py`:
it extracts the unchanged SHA-512 wrapper bodies from the local XNU source,
preserving its license, and compiles them against the actual context and crypto
table headers. A host-only partial fixture connects the candidate descriptor and
callbacks. The probe checks 1,290 boundary/chunk combinations with context
canaries, including zero-length updates, and cross-checks digests with hashlib.
No fixture is registered in XNU. Passing this test does not establish that the
rest of the crypto table, synchronization, entropy or startup ordering works.

## Verified dependency edge

`register_and_init_prng` in osfmk/prng/prng_random.c invokes `entropy_init`
before installing its PRNG context and callbacks. `entropy_init` in
osfmk/prng/entropy.c immediately calls SHA512_Init/Update. The implementations
in libkern/crypto/corecrypto_sha2.c dereference `g_crypto_funcs->ccsha512_di`.
Consequently **crypto registration must precede PRNG registration**, even when
the new PRNG primitive uses its own SHA-256 implementation. A standalone BearSSL
DRBG does not close this dependency. Do not register a partial crypto table as
if it provided the full API.

## Required ordering

PRNG adapter constraints verified against the current caller:

- `read_random_generate` splits requests at CCKPRNG_GENERATE_MAX_NBYTES
  (256), queries cpu_number separately for every chunk, and does not pin
  preemption itself. Never use a generator slot without synchronization on
  the assumption that its numeric CPU identifier implies exclusive access.
  A test of the actual wrapper covers boundary sizes and changing CPU IDs.
- `entropy_provide` requires 64 bytes of input capacity and initially sets
  output length to zero. A contended mutex or insufficient startup/sample
  count returns zero; health failure returns negative with zero bytes; success
  returns a positive sample count and 64 bytes. Positive count is an estimate,
  not a byte count. Do not reseed from uninitialized buffer bytes on a zero
  result or treat a negative result as temporary lack of samples.
- The header's CCKPRNG_MAX_REQUEST_SIZE value (4096) is not the generate
  callback contract: that callback explicitly limits each request to 256.
  initgen must reject duplicate and out-of-range identifiers. Refresh must
  not wait for a contended shared provider lock; reseed and generation may
  run concurrently and require a defined lock order.

These observations constrain the pending adapter. No per-CPU exclusivity,
locking implementation, reseed schedule or failure-recovery policy has yet
been implemented or verified by this audit.

1. Loader supplies fresh boot entropy; existing lazy early_random initialization
   derives boot seeds. Never substitute the deterministic host-test seed.
2. Locks and per-CPU storage needed by entropy collection/provider state exist.
3. Register a complete, audited crypto table, including SHA-512 digest callbacks
   and descriptors compatible with XNU's context allocation and wrappers.
4. Initialize the provider's global/per-CPU synchronization and call
   register_and_init_prng on the boot CPU. Its registration check requires all
   five used callbacks. Entropy initialization must not recursively call the
   unregistered PRNG.
5. Registration initializes the boot generator and reseeds it before returning;
   seed buffers and early generator state are then cleared by the existing code.
6. Secondary random_cpu_init calls occur only after registration. Every ordinary
   read_random consumer requires the provider; there is no fallback there.

## Unresolved placement and tests

The BCM2712 NFS/GSS CTS path now keeps the normalized mbuf chain linked,
checks normalization errors, and writes completed CTS output back to the
existing tail rather than freeing and appending it. The new tail helper checks
copy-in, returned byte count and copyback errors, always releases its temporary
allocation, and never copies rejected cipher output into the mbuf. Its caller
releases the IV on helper/prefix-walk failures. Non-Pi paths are unchanged.
An extracted-body ASan/UBSan harness exercises 17–32-byte tails both as a root
and as a linked tail, with allocation/copy/cipher/writeback faults and short or
oversized returned counts. This is mocked mbuf evidence, not live NFS traffic.
The complete modified GSS translation unit also compiles using recorded BSD
kernel flags. Remaining provider and startup work is unchanged.

Candidate `rpi5_cts.c` adds CBC-CS3 for the six checked AES/DES/3DES CBC
descriptors. Inputs must exceed one block; final blocks swap even for exact
block multiples. In-place operation captures the final pieces before processing
the prefix; decryption reconstructs the stolen ciphertext suffix. Success
returns the input byte count and sets IV to the final logical CBC ciphertext
block; rejected input returns zero. Tests cover 192 algorithm/key/length cases,
all tail lengths through four blocks, independently composed OpenSSL-CBC
references, disjoint/in-place operations, IV results, wrong direction/context,
short inputs and overlap rejection under ASan/UBSan. All seventeen adapter
translation units compile with the recorded kernel flags. The NFS/GSS caller
currently discards the CTS return count; propagating candidate failures there
remains an integration task before registering this provider.

DES raw-key helpers now supply both table callbacks. Odd-parity adjustment
preserves the seven effective key bits in every byte. Weak-key detection checks
the standard four weak and twelve semi-weak keys, cross-checked with OpenSSL's
https://raw.githubusercontent.com/openssl/openssl/master/crypto/des/set_key.c
reference constants. The candidate ignores parity bits without changing input;
this deliberately detects equivalent weak effective keys even with bad parity.
Unsupported weak-key lengths return CCERR_PARAMETER (the in-tree caller uses
exactly eight bytes). Tests cover all 256 byte values for parity/idempotence,
all 256 parity variants of each weak key, every one-bit effective-key mutation,
invalid lengths and typed function-pointer assignment under ASan/UBSan. Kernel
compilation and existing DES/3DES mode tests pass. No full provider is registered.

DES/3DES CBC descriptors now share the compact schedule loader with ECB. They
support exact in-place or disjoint data buffers, require an eight-byte IV
disjoint from key/data storage, and preserve IV/output on preflight errors.
OpenSSL CBC references cover single DES (equivalent repeated-key EDE3) and
three-key 3DES at every two-call split of 16 blocks. Tests check intermediate
and final ciphertext IVs, in-place encryption/decryption, schedule preservation,
wrong algorithm/direction, partial overlap, block-count overflow and missing IV
under ASan/UBSan. The existing ECB tests and kernel compiler checks still pass.
DES raw-key helpers and other unfinished provider operations remain outstanding;
no registration or board reboot is performed by these tests.

Candidate `rpi5_des.c` implements single-DES and three-key 3DES ECB directions
over BearSSL des_ct. XNU's single-DES wrapper reserves 256 bytes, smaller than
BearSSL's shared DES/3DES context, so the adapter serializes only 32 or 96 subkey
words plus its checked header. A common header is validated before reading the
larger schedule, preventing a wrong-mode call from reading beyond a DES buffer.
Tests verify actual wrapper-size fit, OpenSSL outputs for 0–16 blocks, in-place
round trips, wrong algorithm/direction, invalid key lengths, overlaps, overflow,
canaries and unchanged schedules under ASan/UBSan. The DES reference uses the
equivalent OpenSSL EDE3 operation with three identical DES keys. All sixteen
adapter units compile under the recorded BCM2712 flags. This is legacy API
compatibility only. DES CBC modes and raw-key helpers remain missing; ECB's
optional roundkey callback is not implemented. No full provider is registered.

GCM init_with_iv/inc_iv helpers now implement the locally documented managed-IV
lifecycle: a 12-byte initial nonce starts the AAD phase; reset preserves that
nonce; increment changes only its big-endian 64-bit suffix and starts the next
message. Manual set_iv is prohibited for managed contexts, and increment is
prohibited for ordinary init contexts, before reset, or with the wrong direction
descriptor. Counter exhaustion returns CCERR_OVERFLOW without state/output
mutation rather than repeating an IV. Callers still own cross-context key/nonce
uniqueness; this is not a FIPS certification claim. Typed table fixtures exercise
all AES key sizes, compare each managed message tag with independently initialized
manual-IV context output, check repeated messages and the counter boundary,
and retain the 18 known-answer cases under ASan/UBSan. The helpers compile with
kernel flags. Full crypto registration and hardware startup remain unimplemented.

Candidate `rpi5_aes_gcm.c` implements the descriptor's init, set_iv, AAD,
payload, finalize and reset callbacks over BearSSL ct64 CTR/GHASH. State ordering
is KEY → AAD → DATA → FINAL, with reset returning to KEY. Local header semantics
require decryption finalization to verify the supplied tag and then overwrite it
with the calculated tag even on failure; this is implemented with CCERR_INTEGRITY
for mismatches. Decrypted output remains unauthenticated until finalization.
The saved context clears its internal block-cipher pointer and rebinds it to each
local copy before use, preventing dangling stack pointers across calls. AAD and
payload length limits are checked before processing. Zero-length IVs and tag
lengths outside 1–16 are rejected. init_with_iv/inc_iv helpers remain missing.
Tests extract 18 published GCM known-answer cases from the pinned BearSSL test
data, checking all three key sizes, varied IV/AAD/payload lengths, six chunk
sizes, in-place decryption, altered-tag rejection, legacy tag overwrite, invalid
call ordering and canaries under ASan/UBSan. All fifteen adapter translation
units compile with recorded BCM2712 flags. Registration and hardware remain open.

Candidate XTS-AES now supplies both directions, init/key_sched, set_tweak and
full-block processing for 128- or 256-bit component keys. Equal component keys
and 192-bit component keys are rejected. Tweaks advance by multiplication in
the XTS binary field and track a cumulative 2^20-block limit; rejected block
calls return NULL before modifying output/tweak. Full blocks only match the
local wrappers; no ciphertext-stealing interface is provided. Tests use an
independent Python field-arithmetic/OpenSSL-ECB reference, every two-call split
of 16 blocks, in-place operations, invalid inputs, and injected near-limit
state for cumulative-boundary checks. ASan/UBSan caught misaligned paired AES
key storage; making the shared key type 16-byte aligned fixed it, and all AES
modes were rerun. Tests also verify CBC/XTS contexts fit real libkern wrapper
storage. These are candidate host tests and translation-unit checks, not kernel
registration, storage-driver functionality or hardware XNU execution.

XTS integration audit: the local interface returns a tweak pointer from its
block callback and tracks a 2^20-block limit per tweak, but the existing libkern
encrypt/decrypt wrappers discarded that pointer. BCM2712 wrappers now translate
a NULL callback return to CCERR_INTERNAL; non-Pi behavior is unchanged. The
candidate XTS implementation must return NULL on a rejected operation and avoid
partial writes. An extracted-body test verifies tweak errors bypass the block
callback, NULL does not report success, and a successful pointer still returns
zero for both directions. The full wrapper compiles with its own recorded
libkern flags (PRNG/osfmk flags are not interchangeable because of header order).
XTS encryption/decryption itself is still unimplemented.

Candidate AES-CTR now preserves partial keystream blocks across calls and
implements setctr by discarding the old pad. Its descriptor advertises historical
block_size=1 and ecb_block_size=16. Counter behavior was checked against Apple's
public ccmode_ctr_crypt source (https://raw.githubusercontent.com/apple/corecrypto/main/ccmode/src/ccmode_ctr_crypt.c):
only the final 64 bits increment, in big-endian order, wrapping without changing
the prefix. No Apple implementation was imported. Independent test ciphertexts
use OpenSSL AES-ECB over Python-constructed counters, including the low-64-bit
wrap. All 258 two-call byte splits of a 257-byte message are checked for all
three key sizes, with reset-after-partial-use, in-place decryption, unchanged
state on rejected calls and ASan/UBSan. Key/counter reuse remains the caller's
responsibility. XTS/GCM and the other unfinished provider operations remain;
no crypto registration or XNU execution is enabled by this candidate.

AES-CBC encrypt/decrypt descriptors now reuse the candidate ct64 key schedule.
The IV is consumed and updated to the final ciphertext block on success; zero
blocks preserve it. Input/output may be exactly in place or disjoint; IV and key
context must be disjoint from the data buffers. Preflight failures leave output
and IV unchanged. Independent OpenSSL CBC vectors cover all three AES key sizes
and every two-call split of 16 blocks. Tests check intermediate/final IV values,
in-place encryption/decryption, wrong-direction keys, overlap/overflow/null-input
rejection and canaries under ASan/UBSan. Kernel translation-unit checks pass.
CTR/XTS/GCM and other provider operations are still missing; no registration.

Candidate `rpi5_aes_ecb.c` supplies AES-128/192/256 encrypt/decrypt descriptors
using pinned BearSSL ct64. Each ECB block uses a fresh zero-IV single-block CBC
primitive; no padding or cross-block chaining occurs. Context storage contains a
copied key schedule and direction marker, never a cast overlay. Exact in-place
or disjoint input/output is supported; partial overlaps, invalid key lengths,
size overflow and wrong-direction contexts are rejected without output writes.
Context/input/output must be disjoint as a caller precondition. The adapter
roundkey callback is not implemented (no in-tree uses found); external consumers
requiring it remain unsupported. Independent OpenSSL outputs cover all three
key sizes and 0–16 blocks, with in-place round trips, canaries, rejection tests,
unchanged key contexts and ASan/UBSan. All fourteen adapter units compile with
the recorded kernel flags. This is not provider registration or a complete
cipher implementation: CBC/CTR/XTS/GCM and other required algorithms remain.

Candidate `rpi5_crypto_hmac.c` implements all seven size-explicit HMAC callbacks
using the same descriptor selection and existing HMAC core. Local policy requires
full-length tags, aligned context capacity at least the reported size and a
consistent algorithm/context lifetime. The real header's bool verify callbacks
return true for matching tags and false for mismatches. External compatibility
for truncation, malformed arguments and lifecycle semantics remains unproved.
The host fixture assigns every callback without casts and checks all five
algorithms, 585 key/message combinations, streaming generation/verification,
excess-storage canaries and one-shot rejection after flipping each tag byte.
Verification compares the entire public tag length with a volatile accumulator
and clears the temporary tag. This establishes functional behavior, not a
machine-code constant-time audit. All thirteen candidate units compile with the
recorded BCM2712 flags; none is registered as a complete crypto provider.

Candidate `rpi5_crypto_digest.c` now implements the five newer size-explicit
digest callbacks with exact function-pointer types from register_crypto.h.
All five algorithms reuse the checked digest dispatch. Local candidate policy
requires a context capacity at least the reported size, aligned context storage,
an exact output size and a consistent algorithm for a context lifetime; invalid
parameters trap before delegation. The available header defines signatures but
does not document all caller semantics, and no in-tree callers of these newer
fields were found. These local policies are not claimed as verified compatibility
with external consumers. The host fixture exercises one-shot and streaming
outputs against hashlib, with excess context/output storage canaries. All twelve
candidate translation units compile under the recorded BCM2712 kernel flags.
No complete provider or startup hook has been enabled.

Candidate digest coverage now includes MD5 and SHA-1 through
`rpi5_legacy_digest.c`, with explicit native-word/serialized-state conversion
(MD5 little endian, SHA-1 big endian). These are compatibility implementations,
not choices for new cryptographic uses. Shared digest dispatch and HMAC accept
all five table algorithms. Independent hashlib vectors cover 13 message lengths
and 129 chunk sizes per legacy algorithm, repeated finalization and output/context
canaries under ASan/UBSan. HMAC coverage expands to 585 algorithm/key/message
combinations, each with one-shot and eight streaming chunk sizes. All eleven
adapter units compile with the recorded kernel flags. No complete crypto table
is registered: cipher, RSA and newer crypto API coverage is still outstanding.

Candidate `rpi5_prng_binding.c` supplies the five used cckprng callbacks with a
singleton identity token separate from provider storage. It validates the
pinned 64-byte seed/8-byte nonce contract and personalizes the seed with a
versioned HMAC-SHA512 label before generator instantiation. The nonce carries
no entropy credit. User-visible reseed uses mix, not qualified refresh credit.
`test_prng_binding` invokes the real header's function-pointer table without
casts and checks an independent first-output vector, activation, seed mixing,
empty/contended refresh and source preservation under ASan/UBSan. Header
dependency output confirms the repository cckprng.h is selected; system headers
precede EXTERNAL_HEADERS to avoid shadowing SDK availability declarations.
Candidate `rpi5_prng_platform.c` now implements XNU mutex callbacks, a real
nonreturning panic, and an explicit registration entry point. It rejects
duplicate startup, missing crypto registration, startup before PERCPU and
non-boot CPU execution before initializing its lock. It forces lazy boot-seed
initialization with early_random before register_and_init_prng. The BCM2712
profile declares MAX_CPUS=4; a static assertion checks provider capacity.
No automatic startup hook or build selection is installed. crypto_init alone
does not establish crypto-table completeness; the eventual caller must register
the full provider first. Exact placement and runtime locking remain unproved.

`test_prng_platform` compiles this translation unit with the recorded real
BCM2712 kernel flags and generated headers. The first compile caught unrelated
BearSSL umbrella-header documentation errors under XNU's warning policy; the
generator now includes only the required random/HMAC headers, without disabling
warnings. This compilation is not kernel linkage or hardware execution evidence.

The compilation check now covers all ten PRNG and SHA/HMAC candidate units.
It caught missing exported prototypes and alignment warnings in byte-storage
context macros. Shared declarations and memcpy-based scalar accessors now
preserve the pinned XNU digest/HMAC layout without stronger-alignment casts;
SHA compression retains a separate kernel-independent header. SHA-2 wrapper
vectors, HMAC vectors and sanitizer tests are rerun against these accessors.
The platform body also executes in a host harness checking rejected startup
orders, lock initialization, binding preparation, early seed initialization,
registration, duplicate-start rejection and mutex callback behavior. Kernel
services are mocked in that execution test; hardware startup remains untested.

The binding harness also intercepts expected panic paths with setjmp/longjmp:
calls before preparation, null context, invalid initialization sizes/count or
entropy callback, duplicate initialization/activation, inactive generation and
out-of-range activation. An entropy health failure must release the lock before
panic; subsequent generation leaves output untouched, mixing and activation
remain refused, and another refresh cannot call the failed entropy source.
These checks pass under ASan/UBSan; they exercise the candidate binding, not
kernel panic handling or hardware startup.

The refresh reseed callback now returns success/failure explicitly. A failed
generator update causes provider-wide failure/erasure before unlock and returns
SOURCE_FAILURE, never RESEEDED. The provider test injects a terminal state in
generator 2 so earlier generators have already updated, then verifies failure
and erasure of all four streams. Refresh and provider tests pass under
ASan/UBSan. This closes a false-success error path in the candidate core; the
XNU binding and full crypto provider remain unimplemented.

`rpi5_prng_provider.c` connects candidate generators and refresh with one shared
caller-supplied mutex. All streams are instantiated before publication without
retaining the source seed; initgen only enables a unique in-range slot. Mix and
qualified refresh update inactive as well as active streams. Health/source
failure latches and erases every generator while holding that same mutex.
`test_prng_provider` passes two host threads generating 2,000 requests from one
slot, actual try-lock contention, activation validation, mix/reseed counters,
and permanent failure rejection/erasure under ASan/UBSan. This is a correctness-
first serialized design, not parallel per-generator throughput. The XNU lock
adapter, cckprng callback binding, startup hook, complete crypto table and
kernel execution remain absent. No SMP kernel claim follows from pthread tests.

Refresh failure ordering is tightened: a required failure_locked callback runs
on health/source-contract errors before unlock, under the provider lock shared
with generation. Returning a negative result and latching failure afterward
would leave a generation window between detection and latching. Tests now
require the callback for every invalid source response, assert it runs before
unlock and without reseeding, and reject all 31 incomplete callback sets.
The real contention test still passes. An actual provider-wide failure latch
and generator lock integration remain to be connected; this fixes the boundary
contract, not the whole provider.

The generator's independent Python HMAC model now covers the full tested
sequence for IDs 0, 1 and UINT32_MAX: first 32 bytes, a second 17-byte request,
31-byte user mixing followed by 64-byte output, user mixing at the request
limit, qualified reseeding, then 256-byte output. All bytes and request-counter
transitions match under ASan/UBSan. This checks update-after-generate and both
mix/reseed paths, not merely stream initialization. Concurrency and provider
integration are still unverified; test seeds are public fixtures only.

`rpi5_prng_generator.c` now provides candidate serialized generator state using
the pinned BearSSL HMAC-DRBG. Initialization derives a stream seed using
HMAC-SHA256 over a fixed versioned label and LE32 generator ID, keyed by the
caller-qualified 64-byte seed. Requests are 1–256 bytes. A conservative project
limit of 2^20 requests requires qualified reseeding; mixing untrusted user
input does not reset it. Failure erases DRBG state and rejects later operations.
`test_prng_generator` passes independent Python HMAC-derived first-output
vectors for three IDs plus duplicate-init, request-limit, output-canary,
mix-versus-reseed and terminal-failure checks under ASan/UBSan. Caller locking,
provider-wide seed lifecycle, concurrency, refresh connection and XNU callbacks
are still missing. The initial-output vectors are not a complete DRBG/reseed
validation or an entropy-strength measurement.

Refresh contention now has a real pthread-mutex test: one thread holds the
provider lock inside its reseed callback until the other thread completes
1,000 refresh calls. Every competing call returns BUSY without touching entropy
or reseed callbacks; after release/join, refresh succeeds again. Condition
variables establish ordering without timing sleeps; a 15-second process timeout
detects blocking regressions. Both refresh tests pass under ASan/UBSan. This
verifies the callback boundary with host mutexes, not XNU lock implementation,
generator synchronization, health-failure latching or SMP kernel execution.

`rpi5_prng_refresh.c` implements the candidate entropy callback boundary:
one nonblocking lock attempt, no entropy call on contention, explicit empty/
health-failure/source-contract-failure results, reseed only for positive sample
count with exactly 64 returned bytes, and scratch erasure before unlock.
The caller must turn negative results into a provider failure; no generator or
kernel policy is connected yet. `test_prng_refresh` validates missing callbacks,
contention, callback order, all combinations of six signed sample counts and
six lengths, and erasure observed by unlock while the scratch is still live,
under ASan/UBSan. It does not prove actual mutex concurrency or DRBG reseeding.

The HMAC tests now call all four operations through a partial fixture typed
by the actual register_crypto.h header, without casts; all 351 cases still
pass under ASan/UBSan. `bearssl-probe-2w8zw20m` includes the HMAC object in the
freestanding dependency audit (only memcpy/memset remain undefined) and in the
instrumented candidate build. HMAC execution coverage comes from the separate
HMAC test, not that probe's SHA-2/DRBG harness. The full host suite now passes
129 tests. No candidate table is registered or linked into the boot kernel.

Candidate `rpi5_hmac.c` implements HMAC-SHA256/384/512 init/update/final and
one-shot operations using XNU's inner digest plus saved outer-state layout.
It hashes long keys, retains separate ipad/opad states, and clears temporary
key/pad/digest contexts on normal completion. No allocator, RNG or registration
is used. `test_hmac_adapter` checks 351 independently generated Python HMAC
cases (3 algorithms, 9 key lengths, 13 message lengths), eight chunk sizes,
empty inputs and output canaries with all sources under ASan/UBSan. These tests
do not establish malformed-state behavior, all stack/register erasure, kernel
dispatch registration or completeness of the remaining crypto table.

`bearssl-probe-xag5t0ur` connects SHA-256/384/512 to a common candidate digest
dispatch. The host partial table uses it, and extracted XNU SHA256 wrappers
pass 845 chunk/boundary cases with context/output canaries. All 13 SHA-256
digests match hashlib; existing SHA-384/512 cases still pass. Every source is
also rebuilt under ASan/UBSan, producing identical output without diagnostics.
The freestanding object audit retains only memcpy/memset dependencies. This
closes SHA-2 shared-dispatch and wrapper tests, not the complete crypto table,
kernel startup registration, concurrency or entropy-provider requirements.

Candidate `rpi5_sha256_digest.c` now supplies SHA-256 descriptor, compression,
init/update/final and one-shot operations using explicit BearSSL state transfer
into XNU's context layout. `test_sha256_adapter` checks 13 lengths including
55/56 and 63/64 padding/block boundaries, all chunk sizes 1–65, repeated final,
zero-length input and output canaries against Python hashlib. Every source in
that test is instrumented with ASan/UBSan. It is not yet wired into the shared
crypto dispatch, the XNU SHA256 wrappers or the kernel build. The candidate
rejects count overflow rather than wrapping its 64-bit message-bit count.

`bearssl-probe-b7nu_ixd` passes the candidate harness with every primitive,
adapter and extracted wrapper recompiled under AddressSanitizer and UBSan
(nonrecovering). Output exactly matches the ordinary run and sanitizer stderr
is empty; both streams are retained. The freestanding undefined-symbol audit
still runs separately on uninstrumented objects. This exercises existing
SHA-384/SHA-512 and DRBG cases; it is not concurrency, malformed-state, kernel
execution or whole-provider coverage. Future candidate probe runs perform both
builds, and command failures now expose compiler diagnostics.

`bearssl-probe-m_ihak1v` now extracts the unchanged SHA384_Init/Update/Final
wrappers as well as SHA-512 from the pinned XNU source, preserving its license.
The host fixture supplies the SHA-384 descriptor; all 1,290 chunk/boundary
cases pass through the real wrappers with context and output canaries intact.
Results match the separately checked hashlib digests, including both padding
boundary cases. This closes the SHA-384 wrapper-compatibility test gap, not
kernel registration or the rest of the crypto provider.

`bearssl-probe-d56hfqi4` extends the candidate to SHA-384 with its distinct
initial state and exactly 48 output bytes. Both descriptor identities use the
shared SHA-512 compression path; unrelated descriptors remain rejected. The
SHA-384 one-shot and 1,290 chunk/boundary cases match BearSSL and independently
checked hashlib results at ten lengths, with output canaries. Existing SHA-512
wrapper tests still pass. These are candidate descriptor/dispatch tests, not
tests of XNU's SHA-384 wrappers or a registered provider. The crypto table still
needs the other required digest, HMAC, cipher, RSA and random operations.

`bearssl-probe-rzkx1yi2` adds SHA-512 finalization and one-shot callbacks with
the exact register_crypto.h function-pointer signatures. The host partial
fixture now dispatches all four SHA-512 operations. One-shot outputs match the
independently checked digests at all ten boundary lengths; finalization also
passes all 1,290 chunk/boundary cases. The one-shot temporary context is cleared
with volatile writes on successful return (not a claim that every callee stack
copy or register is erased). Other digest descriptors are rejected, not
silently treated as SHA-512. The linked candidate still has only memcpy/memset
external dependencies. This is partial host-tested functionality, not a complete
crypto table, kernel registration, entropy test or boot proof.

The candidate now has SHA-512 init/update functions using the actual ccdigest
storage accessors, with buffered-block processing and pre-mutation counter
validation. `bearssl-probe-6xcr7kml` checks full init/update/final operation with
chunk sizes 1 through 129 at the ten existing message lengths, including empty
updates. All outputs match the independently checked digest. It is still not
registered, and malformed-context traps and kernel execution need further tests.

Candidate SHA-512 bridge now includes final-state padding and output encoding.
It takes the completed-block bit count and a tail shorter than 128 bytes,
preserves input state/tail, and rejects invalid alignment, null required inputs
and counter overflow. The host probe compares complete bridge digests at all ten
boundary lengths against BearSSL, whose results are independently checked by
hashlib. Evidence: `bearssl-probe-tgg_wo8n`. It is not yet a ccdigest descriptor
callback or selected kernel source; context access and provider integration remain.

SHA-512 adapter detail: corecrypto_sha2.c dispatches Init/Update through table
callbacks but Final through `di->final`. The provider must supply the digest
descriptor callback and honor the fixed SHA512_CTX storage, not merely provide
new table pointers. The expanded eight-source BearSSL candidate passes byte-wise
SHA-512 updates at lengths 0, 1, 111, 112, 127, 128, 129, 255, 256 and 257 against
Python hashlib, including padding/block boundaries. Evidence is in
`bearssl-probe-5pvjvfzn/manifest.json`; only memcpy/memset remain external to the
combined candidate object. This still does not test the XNU context adapter.

kernel_bootstrap initializes through SYSCTL, computes address-permutation salts
using early_random, calls PE_init_iokit, then advances to EARLY_BOOT. This is
evidence of the upstream sequence, not permission to insert a hook arbitrarily.
Audit the first ordinary random consumer and lock/per-CPU readiness before
choosing the registration phase. The bootstrap source alone does not prove all
indirect calls or IOKit constructors are safe.

Required adapter verification: independent known-answer/reseed vectors, bounded
generation requests, unique generator initialization, concurrent generation and
reseed, try-lock refresh, zero/no-entropy handling distinct from negative health
failure, seed/state zeroization, and boot/secondary startup-order assertions.
Host candidate tests currently cover only the cryptographic primitive.
