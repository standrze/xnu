# SSH platform-service closure audit — 2026-10-13

Scope: offline source, actual static-link diagnostics, and native host tests.
No existing runtime/VM source, accepted package, security configuration, or Pi
hardware is changed. Host pthreads used by tests are not target pthread support.

## Exact source inputs

- Official Apple libpthread main: `42d026df5b07825070f60134b980a1ec2552dfee`,
  fetched to `build/rpi5/apple-libpthread-main-candidate-20261013`.
- Official Apple Libc main: `71bbe350ab79eef58113991d817ccc6165061a64`,
  `build/rpi5/apple-libc-main-candidate-20261013`.
- Verified official LibreSSL 4.3.3 in
  `build/rpi5/libressl-4.3.3-input-X8xG1B/libressl-4.3.3`.
- Frozen genuine-provider packet link:
  `build/rpi5/apple-ssh-libressl-packet-9ws4lrfd/target-static-link.stderr`.

Primary source locations:
<https://github.com/apple-oss-distributions/libpthread>,
<https://github.com/apple-oss-distributions/Libc>,
<https://github.com/libressl/portable>, <https://www.libressl.org/releases.html>.

## Actual packet dependency boundary

The exact failed link identifies these live call sites, not all symbols present
in the archive:

| Import | Actual live caller | Required behavior |
|---|---|---|
| pthread_mutex_lock/unlock | CRYPTO_lock, CRYPTO_add_lock | Real mutual exclusion and visibility; LibreSSL ignores the returned error code |
| pthread_self | ERR_get_state | Real per-thread identity for error-state lookup/allocation |
| pthread_equal | err_state_LHASH_COMP | Identity comparison of valid pthread objects |
| sysctlbyname | crypto_cpu_caps_init | Six actual kernel CPU-feature queries |

`crypto/crypto_lock.c` owns a statically initialized mutex for every
`CRYPTO_NUM_LOCKS` entry. A failing or no-op mutex implementation would permit
unsynchronized error hashes/reference counts; returning ENOTSUP is insufficient
because these callers do not check it. None is provided here.

`crypto/err/err.c` contains additional pthread_once calls in
ERR_load_ERR_strings; `crypto/crypto_init.c` uses pthread_once and identities in
OPENSSL_init_crypto. Those paths are dead-stripped from this narrow packet link,
not satisfied by an existing provider. The broader SSH initializer must preserve
them. Do not disable upstream initialization or error handling to close symbols.

## Genuine sysctl slice

The unchanged current Apple `gen/FreeBSD/sysctlbyname.c` first calls __sysctl with
OID `[0,3]` to resolve the requested name, then invokes __sysctl on that returned
OID. It propagates errors from both stages. The new assembly uses the original
Apple SYS.h emitter for the real XNU sysctl trap and existing cerror/TSD errno
path. It does not return manufactured CPU flags or classify missing selectors
as successful zero values.

LibreSSL queries `hw.optional.arm.FEAT_AES`, FEAT_PMULL, FEAT_SHA1, FEAT_SHA256,
FEAT_SHA512 and FEAT_SHA3. The existing kernel source declares these nodes via
`bsd/kern/kern_mib.c` and `osfmk/arm/arm_features.inc`.
`osfmk/arm/commpage/commpage.c` derives SHA512/SHA3 from ISAR0; its Apple crypto
extension configuration controls AES/PMULL/SHA1/SHA256. An actual Pi query and
confirmation against its CPU/platform configuration remain necessary. No flags
are changed by this userland leaf.

The native test invokes the real host sysctl for read-only selectors on eight
concurrent threads, compares each returned value/size with the host's original
sysctlbyname, exercises nonexistent selectors, short and size-only buffers, and
injects six distinct syscall errno failures at each of the two stages. These
tests verify the original leaf's behavior, not target kernel capability values.

## Why the pthread gap is not a four-function shim

The preserved `runtime/darwin_static.c` installs a single static 128-word TSD
array with slots for a self-like pointer, errno, and random cookie. It explicitly
has no pthread-created threads. This is not Apple's `struct pthread_s`.

Current Apple's `src/pthread_tsd.c:pthread_self` reads the real TSD pthread
pointer and validates its signature. `src/pthread.c:pthread_equal` compares valid
pthread pointers. It would be incorrect to export only these names around the
bootstrap array and describe a pthread runtime.

`__pthread_init` expects the genuine main pthread object, initializes its random
pointer-munging token/signature, stack bounds, thread ID/port, scheduler info,
thread list, key state and mutex policy. `_pthread_bsdthread_init` registers
thread entry points and actual layout offsets with the kernel and verifies
required features. These requirements precede threaded allocator/error/TSD use.

Current mutex code uses atomic transitions and genuine per-thread owner values,
with psynch_mutexwait/drop or ulock_wait/wake for contention. Its ulock path reads
the Mach thread port from the proper TSD slot. pthread_once also needs atomic
once/wait/reset primitives and cancellation cleanup behavior. Creating and
joining real threads requires their allocation, stack/TSD lifecycle, creation,
termination, errno isolation, destructor and fork contracts.

The XNU syscall table has psynch_mutexwait/drop, bsdthread_create/register,
thread_selfid, and ulock_wait/wake entries. Source/table presence is not proof
that a complete supported userland pthread lifecycle already runs on the Pi.

The old single-process `runtime/libinfo_capabilities.c` once/mutex maps and
`runtime/resolver_capabilities.c` opaque bootstrap identity are **not reused**.
Likewise, `network_command_start.c`'s process-local key map is not general TLS.

## Constructor requirement

LibreSSL's genuine `openssl_init_crypto_constructor` is in __mod_init_func and
invokes crypto_cpu_caps_init. The preserved network command startup only walks
constructors under DARWIN_APPLE_IFCONFIG, not for the packet command. A distinct
future startup must invoke the actual bounded constructor list after required
runtime initialization, exactly once, and validate it from the linked image.
Closing sysctlbyname alone does not satisfy this requirement.

## Next correct integration sequence

1. Retain this genuine sysctl provider and its target archive; the remaining
   actual packet link errors must be the four pthread names above.
2. Build current original Apple pthread and required libplatform once/lock/Mach
   dependencies in a private target; report missing private headers/providers
   without changing semantics or public ABI layout.
3. Supply an actual static main-pthread/bootstrap contract and bsdthread
   registration, replacing the experiment's incompatible process-local key map
   only in a distinct startup artifact. Native tests must exercise real
   contention, create/join, TSD/errno isolation, once/cancellation and failure
   paths; a single-thread cipher KAT does not qualify this layer.
4. Bind and audit genuine constructors and crypto initialization, then test the
   full linked packet program on the Pi through the parent's hardware workflow.

This slice does not claim SSH transport, entropy qualification, thread safety of
the existing allocator/stdio runtime, target packet execution, or an installable
SSH binary. Full pthread startup integration is a separate substantive task.
