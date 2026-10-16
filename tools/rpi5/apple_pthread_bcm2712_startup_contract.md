# Private BCM2712 Apple pthread startup contract — 2026-10-13

Scope: offline ARM64 compile/link and native macOS tests, not a boot package or
proof of working pthreads on the Pi. Accepted user runtime, VM sources, kernel
VM protection policy, and previously frozen artifacts remain unchanged.

## What now builds

The current original Apple pthread main implementation and fourteen selected
pthread/platform implementation units compile for `arm64-apple-darwin`,
`-mcpu=cortex-a76`. This preserves their original implementation bodies,
once/lock algorithms, and thread identity/signature validation. It does not
comprise all of libSystem. Exact original source commits, generated headers,
compiler `-M` scans, and consumed `.d` records are in each artifact manifest.

| Artifact under `build/rpi5/` | Result | Manifest SHA256 |
| --- | --- | --- |
| `apple-pthread-bcm2712-qualified-x9kp1ral` | 15-unit genuine selected archive | `a1f0a4a25efad30a2fb152e5c3a0b0797348deea88786bb28546310ca9e1f00b` |
| `apple-pthread-wait-if5o744t` | Original emitters for five wait/wake syscalls | `394565fbae712065b2a09adbdde6eb681ddc3045562ba3c5ccb62fcbbc95b23d` |
| `apple-pthread-bcm2712-check-kgbwgqa0` | Genuine abort provider, unsupported-feature and forced-startup link evidence | `7b377e6b732a8da13f74fa1f0500ed3ebbe9c6962ed5d8da65ac52b0a6626c8b` |
| `apple-pthread-startup-contract-t9v7gpfa` | Original abort-wrapper tests and actual user/kernel registration layout agreement | `fc8db3c791f55b0286b12ef38cd2a412b525af7c62400771a8e5a2c86d5ac325` |

## Explicit target capabilities, not fabricated Apple hardware

BCM2712's Cortex-A76 does not provide Apple's per-thread APRR JIT service or
Arm MTE. The private target declares `RPI5_PTHREAD_NO_PER_THREAD_JIT=1` and
`CONFIG_MTE=0`. One original private-header preprocessor condition is extended
to reflect that platform distinction. `config_preserved` is explicitly false.
No accepted SDK or pristine original checkout was edited.

The private capability query returns false. The private hardware transition
helpers trap if somehow called; they cannot return fabricated success. All
four public `pthread_jit_*` implementation bodies are unchanged. They retain
Apple's documented unsupported-platform semantics: support query zero, protect
and freeze no-ops, callback invoked directly. This does **not** promise per-thread
JIT protection. No general VM W^X policy is changed or relaxed by this slice;
MAP_JIT allocation/protection behavior has not been exercised on the Pi.

Primary references:

- [Apple pthread JIT API and unsupported semantics](https://github.com/apple-oss-distributions/libpthread/blob/42d026df5b07825070f60134b980a1ec2552dfee/man/pthread_jit_write_protect_np.3)
- [Apple private target selection](https://github.com/apple-oss-distributions/libpthread/blob/42d026df5b07825070f60134b980a1ec2552dfee/kern/kern_internal.h)
- [Arm Cortex-A76 support and technical references](https://support.arm.com/compute-ip/cortex-a76)
- [Arm MTE architecture white paper](https://developer.arm.com/-/media/%20Arm%20Developer%20Community/PDF/Arm_Memory_Tagging_Extension_Whitepaper.pdf)

Native ASan/UBSan tests execute exact original public function bodies with only
test symbol names changed. They verify the advertised unsupported behavior,
not a substitute APRR implementation. Actual A76 object disassembly is retained.

## Actual syscall error contract

Original `libsyscall` `SYS.h` emitters generate these real syscall instructions:

| Service | Number |
| --- | --- |
| `__psynch_mutexwait` | 301 |
| `__psynch_mutexdrop` | 302 |
| `__ulock_wait` | 515 |
| `__ulock_wait2` | 544 |
| `__ulock_wake` | 516 |

The original emitters preserve carry/error handling through `cerror_nocancel`.
The actual XNU `sys_ulock.c` owns `ULF_NO_ERRNO` negative-error conversion;
the wrapper does not fabricate it. Native namespaced versions execute 96,000
real invalid-operation errors across eight threads, two bounded real timeouts,
and a real cross-thread wait/wake. The test checks both errno and NO_ERRNO
behavior. It does not invoke psynch on fabricated registration state, and it
does not establish target-kernel runtime behavior.

The complete original `terminate_with_reason.c` plus original emitters for
syscalls 520/521 provide abort semantics. Four native wrapper cases verify
SIGABRT unmasking, exact argument forwarding, and the actual terminate fallback.
Only those tests substitute the two nonreturning syscall endpoints; no target
success shim is used. Target real abort execution remains untested.

## Required genuine main-thread state

The linked Pi kernel includes the real `libpthread-kern.o` provider built from
Apple `libpthread-539.100.4`; it is not the nosys fallback. Its object SHA256 is
`2b9dcf13e82bfb461b78a86eb05876ed47bde5b11c3ec2dd7256f1e2d155381e`.
Its registration structure is extracted from that exact original source and
checked against the current user headers. All ten field offsets agree. Native
values are independently asserted by the actual A76 compiler:

| Layout | Bytes |
| --- | ---: |
| `sizeof(struct pthread_s)` | 6368 |
| `offsetof(struct pthread_s, tsd)` | 224 |
| `offsetof(struct pthread_s, sig)` | 0 |
| `offsetof(struct pthread_s, thread_id)` | 216 |
| Registration structure | 56 |

This is ABI/layout evidence, not feature-registration execution.

Original `__pthread_init` requires a real main `pthread_s` already published to
the direct TSD slot. It then obtains genuine host priority information, parses
the kernel's `main_stack`, `ptr_munge`, and `th_port` apple-vector values, erases
the consumed secret strings, refreshes the thread signature, installs real TSD
and thread-list state, and registers actual pthread entrypoints/offsets with the
kernel. The non-debug token must be nonzero. Real allocator and exit callbacks
must be supplied through the original `_libpthread_functions` contract.

On this no-PAC target, `pthread_self` validates the thread signature against the
real pointer-munging token; `pthread_equal` is already the original identity
comparison, not a stub. The accepted command bootstrap's 128-word TSD array is
not a `pthread_s`. Its process-local key map is not a multithread implementation.
Neither may be reused as if genuine main-thread setup had occurred.

## Real unresolved startup dependencies and next sequence

The narrow packet-cipher program now links after dead stripping, but is saved
as `NOT_RUN_packet-uninitialized`. **Do not execute, stage, or distribute it as
a working runtime.** Genuine `__pthread_init` is not called. The link also
reports duplicate private `_memcpy` and `_memset` definitions: the original
pthread TU contains no-export platform wrappers that need deliberate local
scope in a separate static integration, not a silent overriding definition.

Forcing the original `__pthread_init` live exposes exactly fourteen remaining
Mach-O symbols. Real provider locations establish the next bounded sequence:

1. `___bsdthread_register`, `___exit`, `___workq_open`: original syscall emitters;
   `__platform_bzero`, `__platform_memset`, `__platform_strlen`: original
   libplatform memory/string implementations. Compile and audit in new output.
2. `_mach_host_self`, `_mach_thread_self`: original Mach traps/wrappers.
   `_host_info`, `_mach_port_construct`, `_mach_port_deallocate`: matching
   generated MIG user calls plus their actual message/runtime closure.
3. `_thread_start`, `_start_wqthread`: original `pthread_asm.s` entrypoints,
   retaining full actual thread/workqueue startup behavior.
4. `__os_xbs_chrooted`: original libkernel initialization object owns this state;
   integrate its real initialization contract, not an invented false global.
5. Once those providers and static symbol isolation are correct, create a
   distinct startup that preserves the actual kernel apple vector, installs a
   correctly sized/aligned real main thread, initializes libkernel/pthread in
   the original order, and only then runs library constructors and main.

Re-linking at each slice may expose further real dependencies. A single-thread
packet invocation does not justify fake locks, fake identities, omitted CPU
feature discovery, or skipping LibreSSL constructors. Genuine concurrent
lock/once/TSD behavior and target failure paths must be tested before acceptance.

Focused regression command (no board access):

```sh
python3 -m unittest tools.rpi5.tests.test_apple_pthread_startup_contract -v
```

The suite verifies frozen input hashes, exact generated and consumed dependency
membership (including deletion rejection), original header/body preservation,
real syscall relocations, host failures, all registration offsets, and the
explicitly incomplete startup boundary. It never runs a `NOT_RUN_` executable.
