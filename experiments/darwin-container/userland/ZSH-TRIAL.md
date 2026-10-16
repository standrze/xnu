# Apple-source zsh: VM milestone achieved

2026-10-12. The XNU VZ guest boots into real interactive Apple-distributed zsh
5.9, built from pinned `apple-oss-distributions/zsh` release `zsh-118`. This is
the VM endpoint, **not Raspberry Pi zsh deployment**, full macOS, general
LibSystem qualification or completion of DC4.

## Definitive goal and outcome

Boot the managed Darwin/XNU VM into an interactive, source-built Apple zsh;
prove its version, arrays/arithmetic, one external executable and return to the
prompt. Preserve the working image, source/build provenance and launch command.
Use only necessary build/link checks and a focused boot smoke, repairing actual
failures; no soak or broad qualification campaign.

All endpoint requirements passed. Actual guest output in the
[serial capture](../results/2026-10-12-zsh/serial.txt):

```text
darwin-zsh# print -r -- "APPLE_ZSH:$ZSH_VERSION"
APPLE_ZSH:5.9
darwin-zsh# a=(darwin zsh); print -r -- "BUILTINS:${a[2]}:$((6 * 7))"
BUILTINS:zsh:42
darwin-zsh# /bin/uname -a
Darwin  12377.121.6 arm64
darwin-zsh# print -r -- PROMPT_RETURNED
PROMPT_RETURNED
darwin-zsh# /sbin/poweroff
```

The guest reached `CPU halted`; the host recorded `guestStopped` after 15.197
seconds. This excerpt removes CR formatting and prompt spacing; original bytes
are preserved alongside it. Version and builtin results are computed output,
not merely echoed input. `/bin/uname` and `/sbin/poweroff` are explicitly project
bootstrap utilities, **not Apple-source replacements**.

The runner's `commandRequested=false`, `commandSucceeded=false` and
`shellReadyObserved=false` are expected in `--interactive` mode: zsh does not
emit the bootstrap shell's readiness/nonce protocol. Actual serial results and
the returned prompt establish this milestone, not those generic runner fields.

## Preserved inputs

Private local capsule: [`build/zsh-working-2026-10-12`](build/zsh-working-2026-10-12/).
Its manifest hashes the image, binary, root, link map, exact input archives,
build/source manifests, configuration/ABI headers, project runtime and bootstrap
sources, and evidence. Generated artifacts are ignored by Git. The EFI image
contains per-image entropy; neither it nor firmware variables should be
published as public evidence. Original upstream sources and license notices
remain in the pinned `upstream/` trees.

| Input | SHA256 |
| --- | --- |
| Static zsh | `78d947f6a08e26ceebbf275a7e15479aabbc61645ac407c546b1a82e74b437e5` |
| Read-only RAM root | `9c15abc1254963a9681eadf7fa0924cb0a1cd0425565210ac3b32e07f47c95ec` |
| VZ kernel, reused unchanged | `b3a0d9f49e2af4bfe28ac716111b05a030d1c8fb273c1e4ffe103e2a36582d53` |
| Working EFI disk | `58134645ef98107ac65c29858a076ca137775a5d792def48706125bb35a7b434` |
| Actual serial bytes | `587041d4426ebaa39129d5c488686958bdd4e7067de44bb5e6fce393291a0fff` |

The final link passed `prepare_pid1.inspect`: thin arm64 static Mach-O with
`LC_UNIXTHREAD`, no dynamic-loader/library commands, undefined symbols, indirect
imports or unresolved section relocations. SDK **headers** and the host compiler
were used; no installed macOS/Homebrew runtime objects or binaries were linked
into zsh. Runtime inputs are authentic Apple Libc, libplatform, ncurses and Libm
source builds, plus explicitly downstream static startup/syscall/own-task VM
glue. This selected combination is not an Apple-supported OS release.

## Repeat the working launch

From repository root on this Apple-silicon Mac, using the existing signed CLI:

```sh
trial_dir="$(mktemp -d /private/tmp/apple-zsh-session.XXXXXX)"
experiments/darwin-container/container/.build/out/Products/Debug/container darwin run \
  --interactive \
  --boot-disk experiments/darwin-container/userland/build/zsh-working-2026-10-12/efi.img \
  --variable-store experiments/darwin-container/userland/build/zsh-working-2026-10-12/efi-variables-template.bin \
  --output-dir "$trial_dir/session" \
  --timeout-seconds 3600
```

The EFI template is copied, not changed in place. Type `/sbin/poweroff` to shut
down, or host Ctrl-C to stop this dedicated VM. One vCPU, 512 MiB VM RAM, a
320-MiB kernel arena, polled serial and read-only root; no host-directory sharing
or guest network. Input is line-buffered, not a full PTY. The one-hour deadline
is a safety limit, not a soak; **no trial was run with that longer deadline**.

Reusing the preserved image repeats its embedded seed. For a new diagnostic
trial, repackage the preserved root with `build_loader.py` for fresh per-image
entropy, leaving this known-working image intact. Runtime entropy and the
inherited kernel seed-clear defect remain hardening limitations.

## Build and repair record

Exact final link command/archive hashes:
[`build/zsh-static-diagnostic-2/manifest.json`](build/zsh-static-diagnostic-2/manifest.json).
The root was built with:

```sh
python3 experiments/darwin-container/userland/build.py --mode zsh \
  --output-dir experiments/darwin-container/userland/build/zsh-root-diagnostic-2 \
  --zsh-binary experiments/darwin-container/userland/build/zsh-static-diagnostic-2/zsh \
  --terminfo-dir experiments/darwin-container/userland/build/apple-terminal-1/terminfo
```

Use a new output directory when rebuilding. The source-built EFI packager was
rebuilt with SwiftPM; no Swift tests were run. The loader manifest records its
kernel/root inputs and loader source hashes.

Two unsuccessful startup trials preceded the repaired smoke, not three
successful acceptance boots. The first crashed before a prompt; a trace in the
second located `zhalloc` writing through a null heap pointer. Libc-167's
`sysconf` lacked modern `_SC_PAGESIZE`, returned -1, and zsh's heap rounding
produced a zero-length mapping. The final POSIX build backports genuine Apple
`getpagesize`, querying kernel `HW_PAGESIZE`. Authentic XNU UNIX03 mmap/munmap
wrappers replace bare legacy entrypoints so zero-length requests fail correctly.
The working image retains labeled startup/fault diagnostics. No further boot or
soak was needed.

## Deliberately deferred

ZLE/completion, Unicode/multibyte and non-C locales, dynamic libraries, job-control
qualification, writable storage/history, networking, OCI packaging, production
isolation and Pi deployment. Original DC3 agent/kernel and Pi artifacts were
not replaced. This is a small usable source-built zsh prompt, not a complete
Apple userland or graphical system.

This product includes software developed by the University of California,
Berkeley and its contributors. Upstream license and attribution requirements
remain applicable to future distribution.
