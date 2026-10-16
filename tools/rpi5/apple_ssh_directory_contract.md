# Current Apple directory-family prerequisite

The new, software-only package is `build/rpi5/apple-ssh-directory-5vnm2xih`.
Its manifest SHA-256 is
`a31b1f23788746c51ba590d5a560eb61155618fb49ffcdf95af0142d1b359cd9`.

The unchanged 176-translation-unit OpenSSH client from the accepted 41-import
spawn composition now has **40 unresolved imports**, closing only `readdir_r`.
There are no newly reachable imports or duplicate definitions. This is not a
linked or running SSH client, and no target program, syscall or filesystem was
executed by this work.

## One directory ABI, not a new function beside old internals

Five legacy `gen-{closedir,opendir,readdir,telldir,seekdir}.o` members are removed
from a **new private copy** of the existing archive. Every other object member
is byte-identical; the archive index necessarily changes. No accepted archive
or image is modified. The replacement family uses current Apple Libc commit
`71bbe350ab79eef58113991d817ccc6165061a64`:

- Complete original `readdir.c`, `closedir.c`, `telldir.c`, `seekdir.c` and
  `rewinddir.c`.
- Original `opendir.c` with exactly two ownership-cleanup additions, below.
- The genuine original `create-syscalls.pl` output for private
  `__getdirentries64`, syscall 344, including its original argument extension
  and `cerror_nocancel` policy.
- Original `gen/__dirent.h`, `telldir.h` and XNU `dirent_private.h`; no invented
  private structure or EOF constant.

The original full-client compile flags and the new provider flags independently
compile the same 22-field ABI witness. Their emitted constant arrays match:
`DIR` is 136 bytes with a 64-byte embedded mutex, and `struct dirent` is 1048
bytes with a 1024-byte name field. This proves the selected consumer/provider
size, alignment and field-offset agreement; it is not a general ABI guarantee
for unrelated third-party binaries.

## Original negative results and precise corrections

The original inputs and failed build outputs are retained. The final package
contains both original and corrected native programs:

1. Original `_GENERIC_DIRSIZ` in `_fbsd_compat_.h` computes a member address
   through a null pointer. Actual `readdir_r` fails under UBSan. The derived
   header replaces just that constant expression with
   `(unsigned long)__builtin_offsetof(struct dirent, d_name)`, retaining the
   original rounding and arithmetic.
2. A union-directory rewind replaces its previous `dd_buf` without releasing
   it. The corrected `opendir.c` frees the previous buffer immediately before
   successful replacement.
3. A union-directory read error loses its new, local buffer. The correction
   frees that buffer after saving `errno` and before the existing close/restore
   sequence. The prior directory buffer remains owned and unchanged.

The native original cleanup oracle reports two outstanding buffers; the same
oracle reports zero with the corrected body. Test-only bookkeeping then frees
the original leaked allocations, so the intentional negative does not leak
from the test process. Both opposite expectations fail. Sanitizers stay enabled
and the original null-member failure is not suppressed.

## Evidence and limits

Run `python3 -m unittest tools.rpi5.tests.test_apple_ssh_directory -v`.

Six focused groups verify complete source/header/generated/tool membership and
omission/mutation negatives; exact source corrections; the emitted ABI arrays;
16 forced live directory providers with zero undefined symbols and strict
static Mach-O inspection; exact full-client replacement/delta; and native
ASan/UBSan execution of the actual family.

The native filesystem and allocation-failure interface is explicitly a test
double. It exercises buffering/growth, EOF extensions and old-kernel EOF,
seek/tell cookies across refills, rewind, fd ownership, union duplicate and
whiteout filtering, read/open/stat/fcntl/allocation failures, original errno
preservation, deleted entries, maximum/overlong names with guarded output, and
four host threads consuming exactly 192 entries from one actual shared `DIR`.
The mutex operations in that workload are the host pthread implementation,
not a claim of Pi execution.

The target forced contract instead has live owners in the real existing Apple
pthread mutex archive, original variadic normal-variant open/openat wrappers,
genuine selected `reallocf`, and the existing syscall/TSD error archive.
Its inherited bootstrap allocator remains inherited; this work does not
qualify modern libmalloc, fork integration, union mounts on the Pi, arbitrary
malformed kernel directory records, notification services or the complete
client. No feature/configuration was disabled and no service or success stub
was introduced. Compiler warnings remain in the captured logs.
