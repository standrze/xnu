# Darwin workload 0.1.0

The three-part workload milestone is boot-proven on this Apple-silicon Mac:
managed real Apple-source zsh, writable HFS+ storage across VM restarts, and a
versioned local package with a foreground launcher. This is our source-built
XNU guest, not the host macOS kernel, a macOS restore image, or a Linux container.
The physical Pi workstream was not changed.

## Launch

From the repository root:

```sh
experiments/darwin-container/userland/build/darwin-workload-0.1.0/darwin
```

At the `darwin-zsh#` prompt, use `cd /data` for writable files. `/` remains a
read-only RAM root. HOME is `/data`; history is `/data/.zsh_history` with a
1000-entry limit. Type `exit` for normal history save, HFS+ unmount and VM shutdown.
The serial terminal is line-buffered: it is not full PTY/ZLE editing.
The default interactive safety deadline is one hour, configurable with
`--timeout-seconds 1...3600`; exit normally before that deadline for clean storage.

For a managed command with captured output, exit status and automatic shutdown:

```sh
experiments/darwin-container/userland/build/darwin-workload-0.1.0/darwin \
  --command 'print -r -- $ZSH_VERSION; /bin/uname -a'
```

Each invocation creates `runs/<unique-ID>/` inside the package. `result.json`
records lifecycle and command status; `command-1-stdout.bin` and
`command-1-stderr.bin` are separate captures. Managed commands have a 256-byte
encoded argv payload limit, no interactive stdin, and a default 60-second deadline.
Long scripts can instead be saved under `/data` and invoked by path.
All output, including current zsh startup diagnostics on stderr, is preserved.

Requires an Apple-silicon Mac with Virtualization.framework and Python 3.
The packaged development CLI has the existing virtualization entitlement;
no installed `container` service is required. The launcher verifies immutable
file hashes and takes a sidecar disk lock. Never attach one writable image to
multiple VMs or mount it on the host while its VM is running.

## What is included

- Source-built VZGENERIC XNU kernel, two EFI/RAM-root profiles (managed and
  interactive), zsh 5.9 and the exact static archives used to link it.
- Pinned official Apple zsh, selected Libc/libplatform/Libm/ncurses source
  implementations, plus clearly labeled project startup/ABI adapters. This is
  not a complete LibSystem, dyld environment or arbitrary macOS binary runtime.
- Apple IOStorageFamily/HFS+ source-built into the separate VM storage profile;
  a project VirtIO PCI block transport, with real reads/writes and FLUSH.
- Labeled project bootstrap `sh`, `echo`, `cat`, `ls`, `sleep`, `uname`,
  `true`, `false` and `poweroff` utilities. These are not claimed to be the
  corresponding Apple command implementations.
- A writable 128-MiB journaled HFS+ `data.raw`, containing the trial's demo
  script, note and history; licenses, source pins, manifests and SHA-256 hashes.

The package is a **private local artifact** under `userland/build/`, not a
redistributable macOS image. EFI payloads/stores contain private entropy;
do not publish them. Reusing these images repeats the embedded boot seed,
and the inherited kernel seed-clear issue remains. Selected source/build
recipes are included, but complete upstream checkouts and the SDK are not;
this is not a standalone rebuildable source distribution.

## Focused evidence

[The preserved verification report](../results/2026-10-12-workload/verification.json)
checks the immutable package, the real zsh embedded in both roots, and these
actual VM results:

| Requirement | Actual evidence |
| --- | --- |
| Managed zsh | Version 5.9, arrays/arithmetic, external command, separate stderr, exits 0 and 7, stream EOF/cleanup, acknowledged shutdown |
| Persistent files/scripts/history | Managed write; separate interactive VM read and execution; loaded history; normal `exit`; later packaged VM read of the newly saved history |
| Versioned launch | `0.1.0` launcher booted the packaged kernel/root, ran zsh against its copied writable disk, returned 0 and observed guest-requested stop |

Kernel SHA-256: `60e4f5fa3c8025fe88f3a42ac5bb5b7331035943a78aba005df76d7949795e76`.
zsh SHA-256: `78d947f6a08e26ceebbf275a7e15479aabbc61645ac407c546b1a82e74b437e5`.
Three focused host preflight checks passed. Runtime repairs addressed the
classic personality parser, read-only ancestor lookup while crossing `/data`,
and HFS FinderInfo copies crossing compiler-visible subobjects; bounds checks
remain enabled. A launcher RAW-file lock conflicted with VZ's storage lock and
was replaced by the sidecar guard before the successful packaged run.
The earlier failures are preserved alongside the passing evidence, excluding
private firmware variables. No soak or broad new regression campaign was run.

Clean restart persistence is proven, **not power-loss recovery**. There is no
network, GPU, shared host directory, full PTY, OCI runtime compatibility, SMP,
or production security/isolation claim. This completes the requested narrow
workload milestone, not every acceptance condition of the wider DC4 roadmap.
