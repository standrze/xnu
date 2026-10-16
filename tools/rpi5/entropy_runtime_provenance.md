# Root43 entropy provenance and the next bounded diagnostic

This is an offline audit of the frozen root43 packet candidate, not evidence of
cryptographic entropy quality or a reason to create live SSH keys. No hardware,
accepted runtime, kernel, root, or sealed trial source was changed.

## What the current image actually does

- Root43 loader: `build/rpi5/root43-packet-vqgxaczi`, manifest
  `e9a093d1006ebcab38ffdfb93bf776db43e73e35c2f879d61fb0bcba6572aaf6`.
- Kernel: `build/rpi5/root42-confirmed-kernel-20261013-final/kernel.root-confirmed`,
  SHA256 `a1c5bc529cbbd25a40adc25a4a8da2c6a4545f366e767929ac00b5ef73c8fc56`.
- Packet target: `build/rpi5/apple-ssh-packet-pthread-iabcb1gr/NOT_RUN_sshpacketprobe`,
  SHA256 `7934dcd0b9882e1ad9a22834bc3f76af805283c8cdb264d26e885c0275879d1b`.

The loader validates `/chosen/bootloader/version` against
`6219bf00832ac18711372008da5ed99cf1c62ecf` and build timestamp `6a31e51d`.
It selects exactly 64 bytes from `/chosen/rng-seed`. Those checks establish
consistency with a trusted firmware handoff, not authenticated attestation.
The pinned official [EEPROM release notes](https://github.com/raspberrypi/rpi-eeprom/blob/279e8b86fd038f026a8daad1223305a15a7d1f2b/firmware-2712/release-notes.md)
describe the May 26, 2026 correction making the Pi 5 seed properties use the
bootsys hardware RNG. That vendor assertion remains the source assumption;
this audit does not measure its entropy, independence, or hardware health.

`loader/rpi5/firmware_seed.c` performs domain-separated HKDF-SHA256 through the
pinned BearSSL implementation, producing 256 interface bytes from the 64-byte
input. It rejects all-zero input, consumes once, and wipes the input. The actual
loader uses the isolated scratch-stack wrapper, copied full-FDT seed serializer,
and verified boot-data commit path. Public bytes 0..63 occur only in a separately
cleared self-test; they are not the XNU seed. Expansion and nonzero checks add no
entropy. The resulting bytes enter Apple's writable `/chosen/random-seed`.

Apple `pexpert/gen/pe_gen.c:PE_get_random_seed` copies and erases that property.
`osfmk/prng/prng_random.c` requires 256 bytes on ARM, divides the material among
kernel/early/accumulator/reseed derivations, and clears intermediate seeds.
The ARM `bootseed_init_native` contribution is zero, not RNDR or another fresh
hardware source. A timebase value personalizes the provider; it is not credited
as entropy. The linked provider is the project BearSSL HMAC-DRBG binding in
`build/rpi5-xcode27/crypto-table-probe-1pbpk3t3/crypto-table.o`, not Apple's private
corecrypto PRNG implementation.

The Apple accumulator remains real: `entropy_collect` samples the timebase on
interrupts, filters samples, performs repetition/adaptive-proportion tests, and
withholds refresh material until its startup/sample thresholds. The port's
provider handles empty/busy refresh without resetting its finite request count;
a reported health failure quarantines it and the binding panics. User mixing
does not reset the fresh-entropy request limit. Source health-test assumptions
are not automatically validated for the Pi's interrupt environment.

The original `getentropy` syscall (500) bounds requests at 256 bytes, calls
`read_random`, then returns `copyout` status. It does **not** separately require
`entropy_health_startup_done == 1`. Therefore successful syscall output may rely
on the initial firmware-derived seed before a later accumulator reseed.

## Userland markers and remaining real service gap

Legacy zsh/utility startup in
`experiments/darwin-container/userland/runtime/darwin_static.c` calls
`getentropy` for an eight-byte TSD cookie and prints `DARWIN:ZSH:ENTROPY` after
success. That proves API completion, not source quality. The genuine pthread
startup used by pthreadprobe/packetprobe replaced this legacy entry. Its main
thread uses XNU's actual apple-vector registration/TSD contract. In the frozen
packet link map `_getentropy` is dead-stripped: the fixed public packet cases
do not request random keys. The LibreSSL constructor only queries CPU features.

LibreSSL's original `RAND_status()` and `RAND_poll()` return 1; those values are
not entropy evidence. Its genuine `RAND_bytes()` calls `arc4random_buf`.
Forcing that original symbol into the exact private runtime link exposes the
single real unresolved import `_arc4random_buf`. The build's original
`HAVE_ARC4RANDOM_BUF`/`HAVE_GETENTROPY` settings were not altered.

The selected current Apple Libc `gen/FreeBSD/arc4random.c` has two materially
different paths: normal Apple builds delegate to `ccrng`/`ccrng_uniform`, whereas
the `VARIANT_STATIC` branch retains an older RC4-based generator. Do not silently
select that branch merely to close a symbol. A genuine modern Apple-compatible
random-service choice and fork/thread/error semantics need explicit review;
adding a fake `ccrng` or treating RAND_status as readiness is not closure.

## Built future diagnostic (not in root43)

`build/rpi5/apple-entropy-api-x4zxvaug/NOT_RUN_entropyprobe`:

- Target SHA256 `a998573358dec3c362c0ec41a74f48e1e61ca4d770ac3495fd1790289298cd50`;
  116416 bytes, static ARM64 Mach-O, zero undefined symbols.
- Manifest SHA256 `b488248ba8522edfd445d5b4d36bc0b260feef92171451d41d2af1dedc842c47`.
- Reuses the exact complete genuine pthread startup, create/join prerequisite,
  original syscall emitter and original sysctlbyname provider. Only the workload
  object is replaced; unused packet objects/libraries are removed explicitly.
- One actual constructor: `_initialized_constructor`. Original getentropy target
  instructions select syscall 500; target map names the retained real providers.
- Requests 0, 1 and 256 bytes, then verifies EINVAL for 257 and EFAULT for an
  invalid destination. The successful output buffers are immediately erased.
- Reads ten existing read-only `kern.entropy.health` / `kern.entropy.filter`
  counters. Does not read analysis buffers or print/hash random output or seeds.
- Missing/wrong-width counters or observed health-failure counts produce nonzero
  exit status. Even a zero diagnostic exit explicitly prints `QUALITY_NOT_PROVEN`.
  Startup_done=0 is reported, not forged into readiness.

`python3 -m unittest tools.rpi5.tests.test_apple_entropy_probe -v` passes three
groups: actual target closure/dependency omission negatives/syscall instruction;
the real diagnostic under ten explicit API-failure fixtures; and the original
XNU syscall body under ASan/UBSan with all 257 admitted sizes, two oversized
requests, and copyout failure. Host fixtures use public synthetic bytes and do
not execute the Pi providers or measure entropy. No target execution is claimed.

The smallest next hardware evidence is this metadata-only API/counter diagnostic
in a separately reviewed future root. It would expose actual availability and
health-counter behavior, not independently qualify firmware RNG or permit live
keys. The unchanged root43 trial takes precedence.
