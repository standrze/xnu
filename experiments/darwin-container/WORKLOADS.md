# Packaged VM-backed Darwin workloads

This is a local package format for **our source-built XNU guest**, not a host
macOS process, shared-kernel container, Linux OCI image, or macOS application
bundle. Every run boots a separate Apple-silicon Virtualization.framework VM.
The interactive [persistent workspace](WORKSPACE.md) remains a separate product.

New packages use runtime 0.4.0: the same 23 [Apple-source CLI tools](APPLE-USERLAND.md)
as workspace 0.4.2, with a separately compiled 96-node VM RAM root. Existing
0.3.0 packages remain frozen and runnable with their original, narrower tools.
Try the ready-built `userland/build/apple-userland-workload-0.4.1` package with
`darwin-workload run`; its example specification is
[`examples/apple-userland/workload.json`](examples/apple-userland/workload.json).

## Build and run

From the repository root, package the included counter application:

```sh
./experiments/darwin-container/darwin-workload pack \
  experiments/darwin-container/examples/counter/workload.json \
  --output experiments/darwin-container/userland/build/counter-0.3.0

./experiments/darwin-container/darwin-workload run \
  experiments/darwin-container/userland/build/counter-0.3.0 \
  --volume my-counter --name counter-1
```

The example package at that output path is already built here; skip `pack` to
use it now, or choose a different new output directory when rebuilding.

Run again with `--name counter-2 --volume my-counter`: the counter increases
because `/data` is the same disk, even though the VM, boot entropy and firmware
variables are new. Run names must be unique; existing runs are never overwritten.
Omit `--volume` for an independent disposable data image retained with that run.

The built package is relocatable. On a compatible Apple-silicon Mac with Python 3.9+,
run its own `./darwin run --volume my-counter` without this source checkout or
Xcode. Packaging, unlike running, requires this checkout, the pinned local runtime
builds, Xcode command-line tools, the existing Zig linker and EFI image tool.
No global installation or installed Apple container daemon is used.

State defaults to `darwin-workloads/` in your current directory. Use the same
`--state-root PATH` for related run/status/log/stop commands and named volumes.
Do not store state inside the immutable package.

```sh
./experiments/darwin-container/darwin-workload status PACKAGE counter-1
./experiments/darwin-container/darwin-workload logs PACKAGE counter-1
./experiments/darwin-container/darwin-workload logs PACKAGE counter-1 --stderr
./experiments/darwin-container/darwin-workload stop PACKAGE counter-1
```

Runs stay in the foreground; ordinary shell backgrounding is available.
Ctrl-C, SIGTERM or `stop` requests the existing managed agent's cancellation and
descendant cleanup before VM shutdown. `stop` reports intent, not completion:
check `status` for the verified outcome. It writes a private control FIFO rather
than signalling a potentially reused PID from a stale file.

Application output streams live on stdout/stderr and in separate binary log
files. The current qualified zsh runtime also emits its startup diagnostics on
stderr; these are retained, not filtered or represented as application output.
Wrapper status messages are on stderr, never application stdout.

## Manifest contract

See [the runnable specification](examples/counter/workload.json).

| Field | Contract |
| --- | --- |
| `format` | Exactly `darwin-workload-spec-1`; unknown fields fail |
| `name`, `version` | Explicit package identity/version; 1–48 safe characters |
| `entrypoint` | Literal argument array, absolute installed executable; 1–64 arguments, at most 16 KiB total |
| `env` | Explicit exports; at most 32 variables / 16 KiB, no NUL, reserved loader/shell controls rejected |
| `cwd` | `/data` by default, or an existing immutable `/app` directory |
| `files` | Local source files installed below `/app`; scripts/data read-only; static no-import ARM64 Mach-O executables may use `executable: true` |
| `network` | `none` by default: no NIC. `nat`: explicit VZ NAT NIC and source-built DHCP setup before entrypoint |
| `resources` | Qualified fixed profile: one vCPU, 512 MiB VZ RAM, 320 MiB kernel arena; deadline 1–3600 seconds, default 60 |

File source paths are relative to the specification (absolute local sources are
also accepted). `/app/entry.zsh` is reserved for the generated launch adapter.
The current VM RAM-root profile permits **96 total nodes**, including runtime files
and directories; the packager enforces that actual total and the loader's 8 MiB
root limit. Individual payload files are at most 4 MiB. Unsupported dynamic
executables, path traversal, collisions, missing entrypoints and missing working
directories fail packaging rather than silently dropping files or settings.
The prior 0.3.0/Pi profiles retain their 32-node default. The packager checks the
selected kernel's compiled capacity and never feeds a 96-node image to a
32-node kernel. The payload-entry limit remains 12 files.

Arguments and environment are shell-quoted into an immutable adapter executed
by real Apple-source zsh. The agent sends only a fixed short launch command;
application arguments are not interpolated into the host shell or truncated to
the transport's 256-byte EXEC envelope. The bootstrap `/bin/sh` is downstream
code, not Apple's shell. zsh and its selected runtime libraries retain official
Apple-source pins and build provenance.

## Package, data and outcome contracts

`manifest.json` records hashes of the EFI template, kernel, RAM root, CLI, runner,
workload specification and provenance/notices. The runner verifies them before
creating a VM. These are local integrity checks, **not a signature or a security
boundary against someone who can replace the package and manifest together**.
Only trusted local packages should be executed.

The EFI template has a reserved zero seed slot. Each run fills it with fresh
host entropy in a private new boot image; the loader rejects zero seeds. The
kernel includes the corrected seed-clear length and permits a genuinely absent
NIC. The prior workspace kernel/package is unchanged.

Named `/data` volumes are independent, owned, 128 MiB journaled HFS+ regular-file
images. Existing data is never reformatted or replaced when changing packages.
An inherited exclusive sidecar lock plus VZ's disk lock prevents concurrent
writable attachment. No host directory, device, GPU or host filesystem is shared
into the guest. Guest workload code runs as root inside its own VM.

Each run retains `run.json`, `launch.json`, raw serial, exact stdout/stderr,
native lifecycle records, a private boot image and private EFI variables.
Do not publish boot images or firmware variables; they contain entropy/state.

| Runner result | Meaning |
| --- | --- |
| `succeeded`, status 0 | Guest command exited 0; complete streams, verified cleanup, shutdown ACK and actual guest stop |
| `exited`, original status | Nonzero normal command exit preserved, not called success |
| `signalled`, 128 + signal | Observed signal termination with complete cleanup and stop |
| `cancelled`, status 130 | Managed cancellation observed, cleanup and actual stop verified |
| `timed-out`, status 124 | Deadline with managed completion/cleanup and actual stop verified |
| `failed`, status 1 | Missing/corrupt/incomplete protocol, output cap, launch/cleanup failure or forced stop; never a successful workload |
| `incomplete` in status | Running metadata survived a lost supervisor but no lock is held; no clean-completion claim |

Managed stdin is EOF; this is a noninteractive job runner, not the PTY workspace.
Combined output is capped at 1 MiB by the existing agent; overflow fails rather
than reporting complete logs. NAT is not an egress filter or exposed-service
manager; DHCP acquisition has no renewal daemon. No registry, OCI import, Docker
API, Linux/Intel host support, full LibSystem/dyld, or hostile-tenant security
qualification is included in this milestone.

## Completion boundary

The goal is complete when a declared package boots real XNU/Apple-source zsh,
honors its literal arguments/environment/cwd and immutable payload, saves and
restores named data across fresh VMs, preserves nonzero exit and separate logs,
supports managed stop, rejects a concurrent writable-volume attachment, and runs
another independent VM without sharing its data. Use a short focused trial, not
a soak. Broader Apple-source userland, Linux ports and shared-kernel containers
are explicitly outside this goal.

The [completion evidence](results/2026-10-12-packaged-workloads/verification.json)
records five short actual offline VM runs and one NAT/disposable-data run. All
six stopped; no soak was added. Six focused native controls cover validation,
literal adapter generation, integrity/symlink rejection and outcome semantics.
Private boot/data images and EFI variables stay in local build/state directories.

The NAT example is [workload-nat.json](examples/counter/workload-nat.json), with
an already-built package at `userland/build/networked-counter-0.3.0`.
Recheck the existing evidence without booting anything:

```sh
python3 experiments/darwin-container/userland/audit_workload_package.py \
  --package experiments/darwin-container/userland/build/counter-trial-0.3.0 \
  --trial experiments/darwin-container/userland/build/packaged-workload-trial-2 \
  --nat-package experiments/darwin-container/userland/build/networked-counter-0.3.0 \
  --nat-run experiments/darwin-container/workload-state/package-nat-check/runs/nat-smoke \
  --example-package experiments/darwin-container/userland/build/counter-0.3.0 \
  --output /private/tmp/darwin-workload-audit-NEW
```

Choose a new audit output path each time. The audit verifies native outcomes,
package/embedded payload/provenance hashes, volume identities, overlapping runs,
fresh entropy, no-NIC and NAT evidence; it excludes private EFI/boot images from
the copied evidence. Failed build/boot/example attempts are retained separately
and described in the completion report.
