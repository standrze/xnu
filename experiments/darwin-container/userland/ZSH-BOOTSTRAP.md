# Apple-source zsh bootstrap

**Achieved 2026-10-12:** source-built Apple zsh 5.9 boots into a usable interactive
prompt in the XNU VM. Version, array/arithmetic builtins, an external command and
return to the prompt passed; the guest powered off cleanly.
See [the definitive goal, evidence and repeatable launch](ZSH-TRIAL.md).
No host `/bin/zsh`, Homebrew runtime, installed libSystem, or dynamic library was
copied. This work does not replace the frozen DC3 image or modify its kernel.

The notes below retain the implementation history. Statements about work still
remaining describe that earlier stage, not current status.

## Current core build

The private-header blocker below is resolved with unmodified XNU source headers
staged into an isolated include overlay. All 32 Apple zsh core objects now
compile with consistent freestanding, no-builtin, no-stack-protector and
no-fortify flags. The pristine Apple checkout remains unchanged.

```sh
python3 experiments/darwin-container/userland/probe_zsh.py \
  --target-minimum --objects-only \
  --output-dir experiments/darwin-container/userland/build/zsh-core-minimum-2
```

Use a new output directory when rebuilding. This builds only the shell core,
not tests or a VM. The generated configuration explicitly disables optional
iconv, `nl_langinfo`, terminfo `setupterm`, and `open_memstream`; zsh's supported
fallback paths remain. `clock_gettime` falls back to `gettimeofday`, private
`_mktemp` to genuine Apple `mktemp`, and `REALPATH_ACCEPTS_NULL` is disabled to
match the legacy Apple realpath implementation's caller-supplied-buffer contract.
Termcap and Darwin rune/ctype dependencies remain real
runtime requirements. This is a basic shell configuration without ZLE,
multibyte text, Unicode filename recoding or terminal job-control qualification.

The resulting [core archive](build/zsh-core-minimum-2/libapple-zsh-core.a) has
SHA256 `7457e246ea1db72d839af2dc8647bbae811be07faafb9dbb89724afa0061abfd`.
The adjacent [external-symbol closure](build/zsh-core-minimum-2/undefined-external-symbols.txt)
is complete for these core objects, unlike the historical nine-object probe.
There are no unresolved internal zsh references, installed runtime linkage,
fortified-string calls or compiler stack-probe dependencies. Guest startup,
source-built runtime linkage and the first boot to a real zsh prompt remain.

[`build_apple_posix.py`](build_apple_posix.py) builds 17 authentic historical
Apple Libc source objects for process, terminal, path, temporary-file and time
helpers. The archive is `build/apple-posix/libapple-posix.a`, with exact original
source hashes, generated-source hashes and narrowly recorded modern ABI/build
adaptations in its adjacent manifest. The legacy `ttyname` retains its actual
directory-search implementation, omitting only the optional obsolete `dev.db`
lookup. `signal` calls the real static sigaction implementation. No successful
runtime behavior is fabricated and no host libraries are linked.

The first guest startup exposed a missing `_SC_PAGESIZE` case in the older
sysconf source. The generated source now backports the reviewed `getpagesize()`
fallback from Apple's `Libc-1752.120.2/gen/FreeBSD/sysconf.c`, and compiles the
actual `Libc-391/gen/FreeBSD/getpagesize.c`, which queries `CTL_HW/HW_PAGESIZE`
through the real kernel sysctl. No page size is fabricated. Both source hashes
and the backport are recorded in the POSIX manifest. Updated archive SHA256:
`ea3c839783d4e9f20b3a2104885524f8d09dc036a8d4cfd4513feb45a1db58ea`.

## Source pin

Official repository: <https://github.com/apple-oss-distributions/zsh>.
Detached checkout: [`upstream/apple-zsh`](upstream/apple-zsh).

| Identity | Value |
| --- | --- |
| Apple release tag | `zsh-118` |
| Commit | `666e91a595af505ef61d5f9b87df7a014a4937c6` |
| Tree | `5b0477ab169cf2055cf00f847a775188222aeacc` |
| Version | `5.9`, from `zsh/Config/version.mk` and Apple's root Makefile |
| SHA256 of `git archive HEAD` | `4dd2b2bc94841fd5bc36ca5c53ad770fd090ddd935b040325939fc98fa1ce2ec` |
| SHA256 of `zsh/LICENCE` | `d06fdf3ef9b1ec69d6b9e170b0a9516fbad3523261ff1668bde3bfea6e0ef5f5` |

[Machine-readable pin](apple-zsh-source.json) includes the annotated
tag object and configure hashes. Upstream notices and `LICENCE` are preserved.
The licence separately identifies shell functions with other terms; the first
image need not install the optional function distribution.

## Smallest useful configuration

Start from the bundled generated `zsh/configure`, avoiding Apple's outer
CoreOS/ReleaseControl Makefile and its multibyte/Unicode/PCRE defaults.
Configure outside the pristine checkout with:

```sh
/absolute/path/to/upstream/apple-zsh/zsh/configure \
  --disable-dynamic --disable-multibyte --disable-locale \
  --disable-dynamic-nss --disable-pcre --disable-cap --disable-gdbm \
  --disable-etcdir --disable-fndir --disable-site-fndir --disable-runhelpdir \
  --without-tcsetpgrp
```

In the generated `config.modules`, retain `zsh/main` as `link=static load=yes`;
set every other module to `link=no load=no auto=no`. Then build only `Src/bin`,
not documentation, optional functions, installed modules or the test suite.
`--disable-dynamic` alone still selects several static ZLE/completion modules;
the explicit module selection matters. See `zsh/INSTALL` under “Adding and
removing modules”, `Src/zsh.mdd`, and `Src/Makefile.in:all/bin`.

This selects the real builtin/parser/expansion/arithmetic/execution core. It
does not promise interactive line editing, terminal job control, Unicode or
optional modules. `--without-tcsetpgrp` avoids configure's controlling-terminal
runtime check and qualifies the first target as noninteractive, without PTY
job control.

## Runtime closure that still has to be supplied

| Family | Source-backed requirement and smallest route |
| --- | --- |
| Darwin startup and syscalls | `Src/main.c` calls `zsh_main`; `Src/init.c:zsh_main` consumes `environ`, installs signals and initialises the runtime. Supply static startup plus the audited Darwin syscall ABI. Existing `libsyscall/` sources are a source for wrappers and signal return, rather than linking the installed runtime. |
| Allocation and stdio | `Src/mem.c` calls `malloc/calloc/realloc/free`; core builtins and setup use the FILE/stdio API. The current bootstrap `runtime.c` supplies neither. A source-built support layer must be labelled accurately; it is not AppleLibc merely because it implements some libc functions. |
| Signals | `Src/init.c:init_signals` and `Src/signals.c` require actual signal installation/masking/return behavior, including for noninteractive commands. Blocking signals in the existing bootstrap PID1 does not implement the shell's signal runtime. |
| Terminal handling | `configure.ac:804–818` requires `tgetent`. Core `init.c:init_term` references `tgetent`, `tgetstr`, `tgetflag`, `tgetnum`; `prompt.c` references `tputs`, `tgoto`. Use a source-built Apple ncurses/termcap closure for authentic terminal support. Optional terminfo calls depend on the generated feature header. |
| Locale and text | `--disable-locale --disable-multibyte` removes the requested locale/wide-character features. Darwin ctype/header expansions and libc implementation details may still require rune/locale support; measure actual object symbols before deciding the source subset. |
| Mathematics and general POSIX | `configure.ac` searches `libm` for `pow`, and the core includes arithmetic, filesystem, directory, environment, time and process functions. Use the object-level undefined-symbol closure to select source objects and actual syscall adapters. |

`--without-term-lib` is not a no-terminal option: `configure.ac:771–788` falls
back to searching terminal libraries. Likewise `ZSH_NO_TERM_HANDLING` only
suppresses terminal headers for particular source files; it does not remove
the core calls. `--enable-zsh-mem` is not a shortcut around libmalloc on this
kernel: its allocator calls `sbrk`, while current syscall 69 is `nosys`.

Host SDK configuration is useful for obtaining compiler/object evidence, but
its successful feature probes do not establish availability in the frozen
guest. The final cross configuration needs an explicit target feature header
and only libraries rebuilt from the selected sources.

## Bounded probe and shortest next step

[`probe_zsh.py`](probe_zsh.py) performs an out-of-tree configure and core-only
object/static-link probe within 60 seconds. It never runs zsh's test suite,
installs software, boots a VM, or copies host runtime files. The first probe
stopped at configure's “no controlling tty” check; its exact log is
[`build/zsh-core-probe-1/configure.log`](build/zsh-core-probe-1/configure.log).
The repaired [second configure](build/zsh-core-probe-2/configure.log) succeeded
with the explicit `--without-tcsetpgrp`. Its
[core build](build/zsh-core-probe-2/core-build.log) produced nine objects, then
stopped at `Src/init.c:40`:

```text
fatal error: 'System/sys/codesign.h' file not found
```

This is an Apple private source-header dependency, not a requirement to copy a
host binary. The pinned local XNU `bsd/sys/codesign.h` and
`osfmk/kern/cs_blobs.h` provide the `csops`, `CS_OPS_STATUS`, and `CS_INSTALLER`
contract. Preserve Apple's `csops` installer-safety check; do not remove
`__APPLE__` or replace this behavior with a success stub.

The [partial symbol inventory](build/zsh-core-probe-2/undefined-external-symbols.txt)
covers only `builtin`, `compat`, `cond`, `context`, `exec`, `glob`, `hashtable`,
`hashnameddir`, and `hist` objects. It still includes unresolved internal zsh
references and is **not** the complete external runtime closure. It confirms
Darwin rune/ctype and stdio globals, allocation, fortified string helpers,
compiler stack probing, and general POSIX dependencies despite disabled locale.
The host feature probes selected `-liconv -lncurses -lm -lc`; those installed
libraries are not acceptable guest inputs. No link or guest execution occurred.

Shortest next implementation step: stage those two reviewed XNU headers in an
isolated include overlay at `System/sys/codesign.h` and `kern/cs_blobs.h`, with
their notices intact, then resume the existing core build. From repository root,
after creating that overlay, the exact next command is:

```sh
make -C experiments/darwin-container/userland/build/zsh-core-probe-2/Src -j4 bin \
  CPPFLAGS="-I$PWD/experiments/darwin-container/userland/build/zsh-core-probe-2/include" \
  CFLAGS='-Os -ffreestanding -fno-builtin -fno-stack-protector -D_FORTIFY_SOURCE=0' \
  LDFLAGS='-Wl,-static'
```

That remains a dependency probe, not the final link: rebuild all core objects
with consistent flags, derive the complete external symbol closure, then select
the corresponding Apple runtime sources. The separately owned
[runtime minimum](APPLE-RUNTIME-MINIMUM.md) records the current source-built
leaf archive and unresolved startup/stdio/allocator closure. Final linking must
use guest startup, `-nostdlib`, Darwin `-static`, and only rebuilt source archives;
inspect for zero dynamic imports before adding a separate `/bin/zsh` to a new
agent RAM root. The first guest command should demonstrate zsh syntax directly:

```sh
/bin/zsh -f -c 'a=(darwin zsh); print -r -- "$ZSH_VERSION ${a[2]} $((6 * 7))"'
```

The required evidence is the actual version/array/arithmetic output and exit
status from that source-built guest binary. Native configure/object output is
not that evidence.
