# Source-built terminal and math runtime

These static guest archives are built from official Apple-distributed source,
not copied from an installed macOS or Homebrew runtime. Build-tool executables
may use the host runtime; none is installed into the guest.

## Pins

| Repository | Tag | Commit |
| --- | --- | --- |
| apple-oss-distributions/ncurses | ncurses-79 | 1d2f7b26157890a542d967be0d1236e7a97f8f5b |
| apple-oss-distributions/Libm | Libm-93 | 21cbbd293ced890ff7eb7a898af184eca0aa9cfa |
| apple-oss-distributions/Libm | Libm-2026 | 17a5f9daa3f5679f7536b26f133b40cc078753c3 |

Keep upstream license notices. Ncurses carries its permissive upstream license.
The selected fdlibm pow/scalbn files carry Sun's permissive notices; ARM Libm
C files retain Apple's notices. These mixed historical source pins are not a
claim to match a current supported macOS runtime release.

## Repeatable build

```sh
python3 experiments/darwin-container/userland/build_apple_terminal.py --output-dir experiments/darwin-container/userland/build/apple-terminal-1
python3 experiments/darwin-container/userland/build_apple_math.py --output-dir experiments/darwin-container/userland/build/apple-math-1
```

Link `build/apple-terminal-1/lib/libtinfo.a` for the real tgetent, tgetstr,
tgetflag, tgetnum, tputs and tgoto implementation. Package the generated
`build/apple-terminal-1/terminfo` directory as `/usr/share/terminfo` and choose
`TERM=dumb` or `TERM=vt100`. Its binary entries are generated from Apple's
terminfo.src by a freshly source-built host tic; host terminfo entries are not
copied. Other ncurses archives and host tic/infocmp are build-only artifacts.

Ncurses generated headers receive two explicitly project-specific adaptations:
the unused dynamic-library multi-ABI insertion marker is removed; an incorrect
SCREEN-extended printf annotation is disabled. The implementation source is
unchanged. Build manifests record commands and archive/terminfo hashes.

Link `build/apple-math-1/libapple-math.a` for pow, fmod, scalbn, isinf and isnan.
The portable historical fdlibm C pow/scalbn algorithms are staged without the
old x86 math.h. Hardware sqrt/fabs/copysign use compiler intrinsics (no host
runtime import). The newer ARM soft-float C fmod algorithm is selected by its
real preprocessor feature guard and compiled for arm64 hardware FP.

`runtime/apple_math_adapters.c` is labeled project glue: the old zsh external
function names isinf/isnan delegate to Apple's authentic __fpclassify C
implementation. It is not a replacement math algorithm or success stub.

This is build/link progress only, not an independent runtime qualification or
guest-boot claim. No test suite or VM campaign is run by these scripts.
