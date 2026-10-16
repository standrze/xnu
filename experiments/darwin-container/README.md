# Darwin guest workstream

**Broader Apple-source command line is available (workspace 0.4.2).**
The default workspace and newly built workload packages now include 23 tools
compiled from official Apple distributions: `ls`, `cp`, `rm`, `mkdir`, `chmod`,
`touch`, `head`, `wc`, `uniq` and more. All 23 were exercised inside XNU, with
clean restart/readback and a separate managed-workload run. Earlier packages
remain unchanged. [Commands, source pins, rebuild and limits](APPLE-USERLAND.md).

**Packaged VM-backed Darwin workloads are available.**
`./experiments/darwin-container/darwin-workload` packages a declared application
and runs each invocation in its own source-built XNU VM. Entrypoint/arguments,
environment/cwd, immutable payloads, named data volumes, logs/status/stop, nonzero
exit propagation and opt-in NAT are implemented and guest-proven.
See [usage and the package contract](WORKLOADS.md) and
[focused completion evidence](results/2026-10-12-packaged-workloads/verification.json).
This is not OCI, Linux compatibility, or a production shared-kernel container runtime.

**Persistent Darwin workspace 0.4.2 is available on this Mac.**
Run `./experiments/darwin-container/darwin-workspace` from the repository root,
or supply a workspace name. It preserves files/history, automatically configures
networking and provisions fresh boot entropy. [Usage and verified scope](WORKSPACE.md).

Next-target planning: [remaining work, Linux hosts and native Intel VMs](LINUX-INTEL-PLAN.md).
The current verified Mac capabilities are summarized in the
[completion audit](COMPLETION-AUDIT.md); the chronological bootstrap descriptions
below retain their original, narrower scope. Linux support is planned, not yet
implemented or boot-proven.

Secondary, explicitly authorized experiment: adapt Apple's `container` and
`containerization` source to manage our custom XNU/Darwin guest through Apple's
Virtualization.framework. **No QEMU, no proprietary macOS restore image, and no
claim that Linux container images execute on XNU.** The physical Pi command-line
work continues independently.

Userland source policy: the bootstrap shell/agent are temporary enablers.
Build the intended real shell and libraries from pinned official Apple
open-source distributions, including [zsh](https://github.com/apple-oss-distributions/zsh),
under the [post-bootstrap source requirements](../../docs/rpi5/DESKTOP-OS-PRD.md#required-post-bootstrap-phase--build-the-real-apple-libraries).
Do not relabel copied host/Homebrew binaries or compatibility stubs as that
Apple-source runtime; downloaded, built, linked and guest-tested are distinct.

**Apple-source zsh VM milestone achieved (2026-10-12).** Real interactive zsh 5.9
boots on XNU, proves arrays/arithmetic and an external command, returns to the
prompt and shuts down cleanly. The working image and provenance are preserved.
See [evidence and repeatable launch](userland/ZSH-TRIAL.md). This does not deploy
zsh to the Pi or complete the wider DC4 runtime/isolation scope.

**Usable workload milestone achieved (2026-10-12).** The versioned local
`0.1.0` package adds managed zsh command/output/status/shutdown integration and
writable HFS+ files, scripts and shell history across clean VM restarts.
The packaged launcher has passed an actual guest run.
See [launch instructions and limitations](userland/WORKLOAD.md) and
[preserved verification](results/2026-10-12-workload/verification.json).

Earlier implementation priority (2026-10-12): take the shortest source-build route to Apple zsh.
DC3's managed guest is sufficient infrastructure; no additional soak or broad
test campaign precedes zsh. Build only its required runtime slice, retain recovery,
and use one focused boot smoke check. Full OCI, persistence and runtime breadth
are deferred. See the PRD's [fast lane](../../docs/rpi5/DESKTOP-OS-PRD.md#fast-lane-to-zsh-2026-10-12-user-direction).

**Earlier milestone: DC3 passed for the narrow managed-command target.**
`container darwin run --managed-agent` boots our source-built XNU/RAM-root agent,
runs ordered commands, captures exact separate binary output, preserves exit
statuses and cancellation, cleans descendants and observes actual guest shutdown.
The original DC2 shell path remains available. This is an experimental Darwin VM
path, not upstream Linux container replacement or a complete macOS runtime.
See [status and limitations](STATUS.md) and the
[verified final matrix](results/2026-10-12-dc3-verification.json).

## Source and ownership

Exact upstream commits and fork URLs are in [sources.lock.json](sources.lock.json).
`container/` and `containerization/` are independent Git checkouts on the local
`darwin-guest-bootstrap` branch, each retaining an `upstream` remote for Apple and
an `origin` remote for the user's fork. The existing `standrze/container` fork was
preserved; `standrze/containerization` was created for this workstream. Downloaded
upstream code retains its original notices. New code is identified as downstream
work. Nothing in this workstream changes the Pi's SD/NVMe images or serial reader.

The CLI uses a deliberately explicit sibling path dependency on our
`containerization` fork. Do not claim it builds against unmodified upstream
Containerization: the new `ContainerizationDarwin` product is downstream.
Each package's `Package.resolved` records its actual dependency graph.
The CLI's upstream `0.49.0` Containerization dependency is replaced by the pinned
main checkout, so untouched Linux source is not a claim of Linux runtime regression
coverage. Downstream manifest, lockfile and command-tree changes are intentional.

## First implementation

- `ContainerizationDarwin`: separate, lightweight configuration/preflight module.
  Does not change `LinuxContainer`, `Vminitd`, or the existing Linux VM lifecycle.
- `container darwin preflight`: built-in experimental command, not a plugin that
  calls installed container services. Checks host, resources, existing disk/store
  files and generic EFI VZ configuration; text or JSON output and failure status.
- `container darwin run`: a separate, bounded foreground EFI session with serial
  capture, fresh/copied firmware state and no installed service dependency. An
  optional command requires exact readiness and fresh nonce output markers;
  input echo is not accepted as a result. Interactive mode is line-buffered,
  not a full PTY. A clean VM stop alone is not evidence of an XNU boot.
- `efi-probe/`: independent, bounded test of custom ARM64 EFI guest execution.
  A disposable VM-owned disk and fresh EFI variables carry evidence. This is
  platform feasibility, **not XNU boot or a functioning Darwin container**.

Preflight never creates/resets an EFI store, starts a VM or runs a container
service. The library's boot disk is read-only and exposes no network, shared
directories, Rosetta or Linux OCI execution. Its downstream managed agent uses
only the dedicated serial channel, not Linux vminitd or network RPC. `darwin run` writes
firmware state and captured evidence only into a newly created output directory;
its optional EFI-store template is copied rather than changed in place.

`kernel/` builds a separate VZGENERIC target from an isolated working-source
snapshot. `loader/vz/` at the repository root supplies the independent EFI
handoff and virtio console. These are not substitutions for the Pi platform.

## Sequence and acceptance

| Gate | Outcome required | What it does not establish |
| --- | --- | --- |
| DC0: source/build | Pinned Apple sources; source-built experimental CLI and module; focused tests | Guest execution |
| DC1: EFI execution | Bounded, nonce-backed payload report and clean stop using Virtualization.framework | XNU boot, Apple runtime support or container isolation |
| DC2: XNU handoff | EFI memory ownership/ExitBootServices, new virtual platform target, console and scheduling, RAM-root shell | Pi drivers working in a VM, networking or Linux compatibility |
| DC3: managed command | Darwin guest agent launches a command and reports output, exit, cancellation and shutdown to host | Complete Docker/OCI runtime support |
| DC4: packaged workload | Versioned Darwin image/runtime contract, selected Apple source-built libraries, lifecycle/resource/isolation tests | Arbitrary macOS applications or a complete macOS distribution |

DC2 must remove Pi-specific device addresses, affinity, firmware, PSCI and
watchdog assumptions through a **separate virtual-platform target**, not fake Pi
nodes. Inventory the actual EFI/ACPI/FDT/device environment first. Retain the
proven Pi boot path. VM evidence never substitutes for Pi hardware evidence.

The initial measured VM profile is one virtual CPU and 512 MiB of firmware-visible
RAM, with an exclusively owned 320-MiB kernel arena. The earlier DC2 root and bootstrap shell
were source-built and static, not zsh, Apple launchd or a full LibSystem
environment. Console I/O is polled. Networking, persistent guest storage, SMP,
sleep/resume, arbitrary firmware layouts and hardened workload isolation remain
unqualified in that earlier profile. The workload package above subsequently
qualifies selected Apple-source zsh/runtime and clean-restart persistent storage.

The current EFI packager embeds a fresh host-generated random seed **per image
build**, not per VM boot. Reusing an image repeats those embedded seed bytes.
Use a newly packaged image for each diagnostic trial; a runtime entropy source
and security review are required before this becomes a production guest.

## Development commands

Read each checkout's local instructions. `containerization` requires its host
build target; it does not need a Linux guest build for this work:

```sh
cd containerization
swift package resolve
make containerization SWIFT_CONFIGURATION_EXTRA='-j 4'
swift test -j 4 --filter DarwinGuestPreflightTests
cd ../container
swift package resolve
swift build --product container -j 4 -Xswiftc -warnings-as-errors
swift test -j 4 --filter DarwinCommandTests
./script/build_and_run.sh
```

Do not run `make verify`, `make integration`, `make clean`, `make cleantest`,
`make install`, or `container system start/stop` for this experiment: upstream
integration changes globally named user services. No service changes or global
installation are required for preflight or the standalone EFI probe.

Validation results and limitations are recorded in [STATUS.md](STATUS.md).

## Managed command use

First build a new agent root, then package a fresh EFI image with `build_loader.py`
and the qualified VZGENERIC kernel. Do not point this command at a Pi SD image.
Use a new output directory for every session:

```sh
container/.build/out/Products/Debug/container darwin run \
  --managed-agent --boot-disk /absolute/fresh-efi.img \
  --output-dir /absolute/new-session --timeout-seconds 30 \
  --agent-command 'uname -a' --agent-command 'cat /etc/motd'
```

Paths above are relative to this workstream directory. CLI commands deliberately
use `/bin/sh -c`; library clients can supply `DarwinAgentCommand(arguments:)`
directly. Managed commands receive stdin EOF, not a PTY. `--cancel-after-seconds`
starts at STARTED and shuts down after cancellation; it cannot report success.
Per-command binary streams and raw serial remain in the output directory.
The development CLI emits an existing debug-build warning on host stderr;
the saved command stderr files contain only decoded application bytes.
See [protocol/limits](agent/PROTOCOL.md) and the
[direct API trial harness](agent/host-trial/README.md).
