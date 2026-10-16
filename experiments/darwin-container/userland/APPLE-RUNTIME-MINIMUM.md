# Small Apple-source runtime for static zsh

## Current static runtime build

`python3 build_apple_runtime.py` builds `build/apple-runtime/libapple-runtime.a`
from 104 pinned Apple-distributed C translation units and two explicitly labeled
project ABI/startup adapter units. It uses the compiler and SDK **headers**, not installed
runtime objects, dylibs or executables. The build rejects implicit function
declarations and integer/pointer conversions. `manifest.json` records every
original/generated source hash, compiler command, object hash and archive hash.
This archive alone does not claim a successful guest boot; the final linked
zsh and console transcript are the runtime acceptance evidence.

The static source selection intentionally uses older authentic Apple sources
where they avoid a full contemporary LibSystem initializer:

- Libc-167: genuinely single-thread stdio, environment, qsort/mergesort,
  strtol/strtoul, dtoa/strtod, strings, time/calendar, directory enumeration,
  atexit/exit and error strings.
- Libc-391: the LP64 scalable allocator and rune/classification tables.
- Libc-1752.120.2: Ctype inline implementations, strcat/strncat, fmtcheck and
  open_memstream.
- libplatform-375.120.2: portable memory movement and core string operations.

All download pins are in `apple-runtime.sources.lock.json`; downloaded trees
are unchanged. Adaptations occur only in generated build copies. They are:

1. The SDK FILE pointer slot `_extra` is named `_up` for selected Libc-167
   stdio, at the same ABI offset/width. All stdio implementations consistently
   use the old byte-stream layout; no wide-stream implementation is mixed in.
2. Libc-167 positional printf's old lvalue `va_arg` extension becomes an Apple
   arm64 stack-cursor capture followed by the real compiler `va_arg` advance.
3. Scalable allocator page constants are 16384/14 for this guest. Allocation,
   free lists, coalescing and resizing remain Apple implementation. Project
   wrappers lazily create the real zone and publish malloc/calloc/realloc/free;
   private locks use acquire/release atomic operations. Parent syscall glue
   supplies own-task VM mapping operations, not host malloc.
4. Old DIR member spellings map to modern SDK names; getdirentries maps to
   the real 64-bit inode syscall adapter. Stat/dirent layouts use modern SDK
   declarations, matching zsh. Signed directory-read failures are checked before
   assigning the SDK's unsigned buffer-size field.
5. Ctype's locale access selects the real C rune table directly instead of
   modern thread-local locale state. Only the C locale is in scope initially.
6. Public prototype modernization (fgets and unsetenv), symbol visibility and
   platform dispatch spellings are recorded in the generator. Open_memstream
   uses Apple's real funopen-based implementation without the unavailable
   wide-stream orientation hook, because the selected streams are byte-only.

Project adapters provide standard stream pointers, dispatch memcpy/bcopy to
Apple memmove, index to Apple strchr, and alphasort to Apple strcoll. Abort
restores and raises real SIGABRT, with `_exit` fallback; assertion diagnostics
terminate the process. These are not silent success-returning substitutes.
Source archives retain original license and attribution text, including the
older Berkeley advertising acknowledgment requirements.

This product includes software developed by the University of California,
Berkeley and its contributors.

## Earlier investigation (historical)

Nine unmodified Apple-distributed Libc files now compile into
`build/apple-libc-leaf/libapple-libc-leaf.a`. This is reusable source-build
progress, not a complete C runtime or a working zsh executable. No VM, broad
test run, host runtime library, frozen DC3 binary or guest image was involved.
Exact source pins, source/object/archive hashes and remaining symbols are in
[apple-runtime.sources.lock.json](apple-runtime.sources.lock.json).

The Apple zsh pin is `zsh-118`, commit
`666e91a595af505ef61d5f9b87df7a014a4937c6`, containing zsh 5.9. Its build/probe
work is recorded separately by the zsh workstream. The runtime tags here are
pinned official source candidates, not a claim that their combination is an
Apple-supported release or ABI-compatible completed runtime.

## Minimum source closure identified so far

| Requirement | Concrete ABI / symbols | Authentic implementation source |
| --- | --- | --- |
| Basic strings and stdlib | `strspn`, `strcspn`, `strpbrk`, `strsep`, `strrchr`, `strdup`, `strndup`, `abs`, `bsearch` | Compiled Libc leaf archive below |
| Memory/string primitives | `memcpy`, `memmove`, `memset`, `strlen`, `strcmp`, related core operations | Selected libplatform routines; the leaf archive itself still needs `memcpy` and `strlen` |
| Allocation | `malloc`, `calloc`, `realloc`, `free` | libmalloc; not implemented by the small guest `rt_*` runtime |
| Standard streams / formatted I/O | `__stdinp`, `__stdoutp`, `__stderrp`, `__sF`, `fopen`, `fdopen`, `fclose`, `fflush`, `fprintf`, `vfprintf`, `snprintf`, stream internals | Libc `stdio/FreeBSD` plus the initializer/header closure |
| Thread state used even by libc | `pthread_once`, `pthread_mutex_lock`, `pthread_mutex_unlock`, `pthread_mutex_destroy`, TSD and errno state | Real libpthread initialization and primitives; modern Apple stdio calls these even for a single-threaded shell |
| Process/syscall boundary | `fork`, `execve`, `wait4`, `pipe`, `read`, `write`, `open`, `close`, `fcntl`, `ioctl`, `stat`/`fstat`/`lstat`, directory calls, `mmap`, `munmap`, `__error`, `cerror` | Existing XNU `libsyscall` plus selected Libc wrappers; generated syscalls must match this kernel |
| Signal installation/return | `sigaction` -> `__platform_sigaction` -> `__sigaction`; `_sigtramp`, `__sigreturn`; `sigprocmask`, `sigsuspend` | Libc `sys/sigaction.c`, libplatform `src/setjmp/generic/{sigaction,sigtramp}.c`, XNU libsyscall |
| Nonlocal jumps | `_setjmp`, `_longjmp`, `setjmp`, `longjmp`, signal-mask variants | libplatform `src/setjmp/arm64/setjmp.s`; uses the initialized TSD pointer-munging token |
| Terminal capability core | `tgetent`, `tgetstr`, `tgetflag`, `tgetnum`, `tputs`, `tgoto` | Apple-distributed ncurses/termcap source subset, still to pin/build in the zsh workstream |
| Numeric/locale helpers | `strtol` family and C-locale classification; floating helpers only if retained by core objects | Selected Libc locale/stdlib/gdtoa; libm only for actual surviving undefined math symbols |

This table is source-derived. A full zsh core-object undefined-symbol inventory
has not yet completed, so it is not an exact final link manifest. Disable
dynamic modules, locale/multibyte features, PCRE, capabilities, GDBM and extra
modules for the first noninteractive build. This reduces features but does not
erase core stdio, arithmetic, job/signal or terminal symbol references. In
particular, zsh configure requires `tgetent`; disabling ZLE does not remove it.

## Why dyld and full LibSystem are not the first build step

A fully resolved static Mach-O can use the guest's established static entry
contract; dyld is not intrinsically required by zsh's parser. Configure zsh with
dynamic loading disabled and do not introduce `LC_LOAD_DYLINKER` or dylib imports.
That does require replacing the *startup orchestration*, not replacing Apple
implementations with fake success functions.

Apple Libc `sys/_libc_init.c` exposes `__libc_init` and `_libc_initializer`, which
initialize program variables, fork hooks, locale, guards and stdio. Its
`stdio/stdio_init.c` dyld SDK-compatibility query is guarded by
`PR_96211868_CHECK`; a documented static build setting of zero removes that
query's calls, but does not solve the remaining initializer closure. Modern
libmalloc receives optional loader callbacks; that alone is not evidence the
whole allocator can already run without startup work. Libsystem's normal
initializer pulls many unrelated system components, so building the complete
umbrella library first would enlarge this experiment substantially.

Keep the necessary real startup state: argc/argv/environ and ProgramVars, errno,
Mach/task/page information used by the selected routines, pthread main-thread
and TSD state, allocator initialization, signal trampoline registration and
stdio/locale initialization. Existing `rt_call` returns `-errno`; libc entry
points instead return their documented failure sentinel and publish errno.
They are not interchangeable APIs. `libsyscall/custom/errno.c` also calls the
pthread cancellation hook and reads direct TSD slots.

Two apparent shortcuts do not close the runtime:

- zsh's `--enable-zsh-mem` allocator still calls `sbrk` in `Src/mem.c`, even
  when its separate heap path uses mmap. Kernel syscall 69 is `nosys` for old
  sbrk. This option does not provide a ready allocator for this guest.
- Modern Apple stdio contains unconditional pthread once/mutex calls in
  `stdio/FreeBSD/findfp.c`. Defining a single-thread flag alone does not supply
  those implementations or the TSD setup used by arm64 nonlocal jumps.

## Concrete completed source-build step

From this directory, the nine files were compiled with Apple Clang 21.0.0 and
MacOSX27.0 SDK **headers only**, then archived. There was no executable link:

```sh
runtime_source_dir="$PWD/upstream/apple-Libc-1752.120.2"
runtime_output_dir="$PWD/build/apple-libc-leaf"
runtime_sdk="$(xcrun --sdk macosx --show-sdk-path)"
mkdir -p "$runtime_output_dir"
for runtime_leaf in \
  string/FreeBSD/strspn.c string/FreeBSD/strcspn.c \
  string/FreeBSD/strpbrk.c string/FreeBSD/strsep.c \
  string/FreeBSD/strrchr.c string/FreeBSD/strdup.c \
  string/FreeBSD/strndup.c stdlib/FreeBSD/abs.c stdlib/FreeBSD/bsearch.c; do
  xcrun clang -target arm64-apple-macosx13.0 -isysroot "$runtime_sdk" \
    -include machine/limits.h -Os -ffreestanding -fno-builtin \
    -fno-stack-protector -fno-common -Wall -Wextra -Werror \
    -c "$runtime_source_dir/$runtime_leaf" \
    -o "$runtime_output_dir/$(basename "$runtime_leaf" .c).o" || exit $?
done
ZERO_AR_DATE=1 xcrun ar -rcs "$runtime_output_dir/libapple-libc-leaf.a" \
  "$runtime_output_dir"/*.o
xcrun nm -g "$runtime_output_dir/libapple-libc-leaf.a"
```

An initial freestanding compile lacked `LONG_BIT`; including the SDK's real
`machine/limits.h` fixed that header context without editing Apple source.
The archive defines the nine functions plus `bsearch_b`. Its only undefined
symbols are `_malloc`, `_memcpy`, `_strlen`; the optional blocks entrypoint
adds no unresolved Blocks runtime symbols. Archive SHA-256:
`3a4be64367ef9db5471acbcf8555958e0c8c0ca8f24eed158170cac34c685546`.

Stop here for this step. The next useful source-build work is selected
libplatform memory/string objects, then the actual zsh unresolved-symbol list
to choose allocator, stdio, terminal and startup closure. Do not satisfy those
symbols with host dylibs or success-returning stubs and call that an Apple
runtime. No execution correctness is claimed by this archive build.

Official source references: [Libc](https://github.com/apple-oss-distributions/Libc/tree/Libc-1752.120.2),
[libplatform](https://github.com/apple-oss-distributions/libplatform/tree/libplatform-375.120.2),
[libmalloc](https://github.com/apple-oss-distributions/libmalloc/tree/libmalloc-812.100.31),
[Apple zsh](https://github.com/apple-oss-distributions/zsh/tree/zsh-118).
