# Current Apple random wrapper and the separate Pi API adapter

This note records offline source, ABI, and failure-behavior evidence. Neither
future entropy executable has run on the Pi, generated live keys, or qualified
entropy. After the provider audit, both were packed in the distinct unexecuted
root45 candidate `root45-entropy-mob0oyvx`; the running/accepted images and
runtime were unchanged.

## Original Apple path: preserved, not silently replaced

The exact [Apple Libc source](https://github.com/apple-oss-distributions/Libc/blob/71bbe350ab79eef58113991d817ccc6165061a64/gen/FreeBSD/arc4random.c)
at revision `71bbe350ab79eef58113991d817ccc6165061a64` delegates normal Apple
`arc4random_buf` to `ccrng()->generate`, and uniform requests to `ccrng_uniform`.
Its `VARIANT_STATIC` branch is an older RC4-based implementation; that branch
was **not** selected. The normal wrapper ignores generation/uniform error
returns. Returning an error from a replacement provider therefore cannot make
this void API safely report failure. The original lazy cached handle also needs
an explicit initialization/concurrency contract; it is not adopted here.

The full original translation-unit attempt is preserved in
`build/rpi5/apple-arc4random-normal-audit-7quo4726`, manifest
`a40bd8518eb230260c0413eaf91a79703a381d8c8575d198362f69984258c124`.
It runs Apple's original feature-header generator for arm64/macOS, checks the
source against its Git revision, records before/consumed dependencies, and keeps
all compiler diagnostics. It does **not** compile or link successfully: current
userspace `os/assumes.h` needs matching private logging declarations such as
`os_log_send_and_compose` and `OS_LOG_F_SEND`. XNU's similarly named kernel
logging header is not that userspace provider. Empty missing-symbol lists in
this failed artifact are explicitly not evidence of link closure.

The existing `EXTERNAL_HEADERS/corecrypto/ccrng.h` is a declaration, not the
private implementation. Its own notice describes Apple's Internal Use License,
limits use to internal verification on owned/controlled devices, and prohibits
redistribution. Do not infer redistribution permission from its presence in an
XNU checkout, or call a project implementation Apple's corecrypto/FIPS RNG.
The Libc source file separately carries its permissive notice; other included
Apple sources carry their own notices, including APSL 2.0. These source notices
must remain intact and are not blanket clearance for all dependency licensing.

## Project-owned adapter: direct kernel API, no new generator

`tools/rpi5/user/kernel_entropy_arc4random.c` is explicitly project code,
BSD-2-Clause, and does not include or implement `ccrng`. It supplies only
`arc4random_buf` directly over the genuine kernel `getentropy` service:

- Zero length, including a null pointer, performs no syscall.
- Nonzero null and wrapping half-open address ranges terminate the process.
  Other invalid destinations are checked by the real kernel copyout path.
- Every request is divided into chunks of at most 256 bytes. Any request error,
  including EINTR or a later chunk failure, terminates with status 127. No retry,
  fallback, time-derived data, zero fill, or partial-success return is supplied.
- Actual target code calls the original exit syscall 1 through a volatile local
  function pointer and retains a BRK fallback if that impossible return occurs.
  A direct SDK-noreturn call would optimize away the fallback.
- There is no mutable global, heap allocation, user lock, RNG cache, or TLS
  cache. A fork inherits no adapter generator state or held adapter lock.
  This does not independently validate all Pi process-fork behavior.
- The adapter and diagnostic never emit/hash random data or seeds. Successful
  output inherits exactly the kernel entropy provenance and limitations in
  `entropy_runtime_provenance.md`; it does not improve or measure that quality.

Original LibreSSL 4.3.3 `crypto/rand/rand_lib.c` is unchanged. Its positive-size
`RAND_bytes` calls this adapter then returns 1; its original nonpositive-size
behavior also remains unchanged. `RAND_status`/`RAND_poll` are not readiness
proof. The new workload uses only lengths 0, 1, 256, 257, and 1024, erases each
buffer, and prints a metadata-only `QUALITY_NOT_PROVEN` result.

## Frozen offline evidence

`build/rpi5/kernel-entropy-rand-hfrb7y67/NOT_RUN_kernel_randprobe`:

- Manifest `f46bd17a8171c4272985875cfbb6a49d7305a49e26d2ee716facbe6aaac924f8`.
- Target `fed221215a29d62909e169f44bc66abac15603967db3f252737f419f30dca14a`,
  116432 bytes, static Cortex-A76 Mach-O, zero undefined imports.
- Exact retained chain is original `RAND_bytes` → project `arc4random_buf` →
  original syscall 500. The adapter object imports only `_exit` and
  `getentropy`, with no data/TLS symbols.
- Complete genuine pthread startup and four-thread prerequisite are unchanged.
  The one actual constructor is `_initialized_constructor`; this RAND-only TU
  does not reference/pull the libcrypto CPU-capability constructor required by
  the separate packet cipher workload.
- Source/consumed-header/generated-output hashes and the exact link delta are
  retained. Debug stripping changes no loaded section bytes.

`python3 -m unittest tools.rpi5.tests.test_kernel_entropy_rand_probe -v` passes
four focused groups. Tests verify the actual target providers/instructions,
dependency-membership deletion negatives, the preserved failed Apple build,
and the exact normal Apple function bodies under explicit provider doubles.
The real adapter plus original LibreSSL RAND body passes ASan/UBSan with 11
boundary sizes, 8 fail-stop cases, four concurrent threads, and fork while
threads are active. Test bytes are public synthetic fixtures, not entropy.
Parent and the independent reviewer also ran the focused tests successfully.

The main runner separately reported root43's ten-command packet batch and its
real process-exit query passing, including 48 valid and 5036 rejected packet
cases. That is a packet/runtime command milestone, not a random-provider or
entropy result. Full-trial recovery acceptance belongs to the main runner's
independently checked return/replay receipt, not this offline audit.
