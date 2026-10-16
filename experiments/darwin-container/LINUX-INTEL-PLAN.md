# Darwin VM: remaining work, Linux hosts and Intel targets

2026-10-12. Planning only: no Linux deployment, new VM trial or physical Pi
operation was performed for this document. The existing Mac checkpoint is kept
unchanged. This plan extends the completed experimental VM milestone; it does
not reopen its soak or verification gates.

## Starting point

The [completion audit](COMPLETION-AUDIT.md) records a real source-built ARM64
XNU guest with Apple-source zsh 5.9, PTY/job control/editing/resize, persistent
HFS+ files and history, managed commands and orderly shutdown. It also records
real guest DHCP/DNS/TCP using pinned Apple networking sources and project VirtIO
transport. The GPU proof is a bounded vector-add API executed by host Metal,
not general Metal compatibility or a graphical desktop.

The latest qualified checkpoint is
`userland/build/apple-ifconfig-working-2026-10-12/`. Its Mac executable, Apple VZ
firmware state and ARM64 guest platform are not a Linux release. No Linux-host or
x86_64-guest boot has been demonstrated by this workstream.

## Three different destinations

| Destination | Proposed route | Current gap |
| --- | --- | --- |
| Current ARM64 Darwin on an Intel/AMD Linux host | QEMU AArch64 system emulation (TCG) | Linux launcher and guest virtual-platform port; slower emulated CPU |
| ARM64 Darwin on ARM64 Linux | QEMU/KVM after the same platform port | Real host/CPU/page-size/firmware qualification; not automatically proven by TCG |
| Native-architecture x86_64 Darwin VM on Intel Linux | x86_64 XNU/userland + QEMU/KVM | Separate boot, kernel-platform and ABI port; no current x86 image |

KVM accelerates a compatible guest architecture on the host CPU; it does not
translate this ARM64 guest into x86. QEMU supplies the cross-architecture route.
[QEMU acceleration](https://www.qemu.org/docs/master/system/introduction.html)
and [ARM virt platform](https://www.qemu.org/docs/master/system/arm/virt.html).

In all three cases this remains **our XNU kernel inside a VM**, not a Linux
container borrowing the Linux kernel. Linux OCI binaries do not become Darwin
binaries. QEMU would be a new optional Linux backend; the current Mac backend
continues using Virtualization.framework without QEMU.

Booting a PC directly, with no Linux host, is a fourth and much larger target.
It is described below for comparison, not added to the current VM scope.

## Reuse first, with explicit boundaries

- Retain pinned official Apple XNU, zsh, selected Libc/libplatform, HFS+ and
  IOStorageFamily, libresolv, Libinfo, bootp and network_cmds sources already
  used here. Keep source/adaptation manifests and original notices.
- Reuse our guest agent, terminal framing, command/status protocol, HFS data
  format and VirtIO work where the new machine contract matches. Virtual-device
  support must still be checked against QEMU, not assumed from the VirtIO name.
- Keep platform-specific code separate from the shared runtime. Prefer published
  Apple implementations where they actually provide the needed functionality;
  source presence, successful build and guest validation are separate states.
- Use QEMU and EDK II firmware instead of writing a hypervisor. Pin the QEMU
  version, versioned machine model, firmware and CPU/device profile.
- The local containerization checkout already has a Linux Cloud Hypervisor
  backend, but its VM/vminitd lifecycle is for Linux guests. It does not provide
  a ready Darwin backend or ARM-on-x86 emulation. Consider its process/API code
  for reuse and a later same-architecture backend, not a shortcut around the
  guest port. [Cloud Hypervisor](https://github.com/cloud-hypervisor/cloud-hypervisor).
- First run Mac-built guest artifacts on Linux. Building all guest components
  from source **on Linux** is a separate toolchain task, not a prerequisite for
  running them there. Do not copy installed macOS runtime binaries into the guest.

## Implementation sequence

### L0 — Capture the Linux target and freeze a development baseline

Inventory CPU architecture/model, distribution/version, RAM/disk space, QEMU
and firmware availability. Check `/dev/kvm` permissions only for a same-ISA
accelerated run. Use a regular-user workspace, private control sockets and
image files; do not replace the host OS or use raw host disks.

Preserve the qualified Mac image and make distinct Linux development artifacts.
Record host/guest architecture separately in the manifest. Fix the documented
seed-buffer clearing size defect in the new kernel build; do not overwrite the
old checkpoint. Design fresh entropy delivery per boot, rather than distributing
the current embedded private seed as a reusable public image.

Exit: explicit machine/backend profile and reproducible artifact inputs. Exact
host setup commands follow the observed Linux distribution, not guessed package
names. No GPU, desktop, libvirt or Docker requirement for this milestone.

### L1 — Reach the real zsh prompt on QEMU ARM64

Begin with one CPU and a bounded RAM allocation, fresh UEFI variables, modern
PCI VirtIO console/block/net devices and no GPU. Add a minimal diagnostic launch
recipe before porting the whole Swift CLI.

The existing EFI loader in `../../loader/vz/boot.c` rejects platforms unless
ECAM is `0x40000000`, GICD is `0x10000000`, GICR is `0x10010000`, the timer is
24 MHz, and the platform supplies its exact single-CPU/PPI27/PSCI-HVC contract.
Replace those assumptions with a separate supported platform profile and
validated ACPI/FDT discovery. Preserve fail-closed bounds and memory ownership;
do not simply remove the checks. Adapt GIC ranges, timer frequency, PSCI conduit,
PCI BAR mappings, 16-KiB-page capability and retained DMA allocations as needed.

QEMU explicitly warns that ARM machine images are not generally interchangeable,
and that device locations on `virt` must be discovered rather than assumed.
[ARM machines](https://www.qemu.org/docs/master/system/target-arm.html),
[virt hardware description](https://www.qemu.org/docs/master/system/arm/virt.html#hardware-configuration-information-for-bare-metal-programming).

Reuse the existing ARM64 runtime and source-built zsh where their contracts
remain unchanged. Pass real entropy through the loader and verify guest shutdown
against the selected firmware/platform. Keep early diagnostics separate from
framed application traffic.

Exit: one actual Linux-host boot reaches PID 1 and the real zsh prompt, runs an
external guest command with the expected status, and shuts down cleanly. This
proves Linux-host execution, not native Intel speed or full OS compatibility.

### L2 — Provide a usable Linux command-line launcher

Separate backend-independent configuration, guest protocol and lifecycle from
Apple Virtualization.framework. Add a Linux process/QMP backend and connect the
existing framed terminal to a dedicated QEMU character socket. Never mix QMP or
firmware diagnostic text with guest protocol frames.

Port the host terminal handling to Linux termios/PTY/signal behavior, with
restoration on failure, resize forwarding, bounded I/O and process cleanup.
The existing Mac CLI imports and terminal/GPU implementations cannot merely be
recompiled unchanged. A small Linux executable reusing the shared library is
acceptable initially; do not make porting every Apple container service a gate.

Add writable-disk locking, per-session firmware state, clean start/stop/status
and explicit unsupported-feature errors. Start with user-mode NAT, avoiding
privileged bridge/TAP setup. Confirm our PCI VirtIO queue/feature handling and
DHCP/DNS behavior against the chosen QEMU devices/NAT implementation.

Exit: one command on Linux opens real zsh with working Ctrl-C/job control/resize;
a saved file/history survives one clean restart; guest DNS and TCP work against
a known endpoint. Package with source/artifact manifests and documented limits.
GPU requests report unavailable until a Linux GPU backend exists.

**L2 is the first Linux delivery endpoint.** Use one combined smoke session plus
the single restart needed to demonstrate persistence, not a soak campaign.

### I1 — Build a native-architecture x86_64 guest for Intel/KVM

Run an early x86 source/build feasibility inventory in parallel with L1/L2; do
not turn the ARM portability proof into an indefinite prerequisite if native
Intel performance becomes the priority.

Apple publishes x86_64 XNU source and build configurations. That saves writing
an x86 kernel from scratch, but does not supply this project's complete bootable
PC VM. [Official XNU source/build instructions](https://github.com/apple-oss-distributions/xnu).

Required implementation:

1. Close a pinned x86_64 kernel build and required source-built providers; add an
   isolated x86 VM configuration, initially one vCPU.
2. Supply an x86_64 EFI loader (`BOOTX64.EFI`), boot arguments, relocations and
   memory map appropriate to the upstream x86 entry contract. The present ARM
   transition assembly and `BOOTAA64.EFI` cannot be reused as executables.
3. Connect platform discovery, ACPI/PCI, LAPIC/interrupts, clocks, console and
   shutdown to one pinned virtual PC profile. Audit upstream platform-provider
   dependencies instead of assuming an Apple machine's drivers are present.
4. Rebuild the real Apple zsh and runtime for x86_64; implement/verify x86 syscall,
   signal-return, TSD, varargs, startup and page-size assumptions. Current ABI
   generators and Mach-O validators are ARM64-specific. Reuse the x86 assembly
   already published in XNU libsyscall where applicable; rebuild architecture-
   specific crypto/pthread providers rather than carrying over ARM object files.
5. Adapt/reuse VirtIO storage/network and the existing guest/host protocols.
   Replace ARM-specific barrier, counter and wait primitives in the transports
   with x86 implementations, then execute through KVM on the actual Intel host.

Exit: the L2 shell/persistence/network workflow passes on a confirmed x86_64
guest with KVM active, not TCG or an ARM image. Only then describe it as an
accelerated Intel Darwin VM. AMD is a separate CPU-compatibility validation,
not automatically implied by an Intel pass. SMP/performance tuning follows.

### P1 — Make the command-line OS broadly useful

These are separate from the first Linux-host boot and can be incrementally
developed on the existing Mac VM:

- Add missing everyday source-built tools and a reproducible image/install/update
  workflow. Preserve user data across image replacement, not just VM restarts.
  Complete optional zsh modules and multibyte/locale support as needed.
- Expand the small static runtime toward a coherent LibSystem/libpthread/dyld
  environment for dynamically linked, multithreaded software. Keep selected
  older Apple sources and project adapters accurately labeled.
- Add persistent network configuration, lease renewal/rebinding and conflict
  handling; then broader DNS policy, TLS tooling and secure remote access.
  Full configd and mDNS service parity is not necessary before a useful shell.
- Provide a guest compiler/linker/headers/build tools if self-hosted compilation
  is desired. Source-building on the Mac today does not mean compilation inside
  the guest already works. Audit Linux-native cross-build dependencies separately:
  current scripts rely on `xcrun`, Apple SDK headers and Mach-O tooling.
- Address production isolation, entropy, privileges, recovery and crash/disk
  integrity before putting secrets or untrusted workloads in it. Current
  completion evidence is not a production security assessment.
- Optional Linux shared compute: reuse the bounded request protocol, add an
  explicitly new host backend such as Vulkan or CUDA after capability research.
  This does not expose Metal on Linux, require GPU passthrough, or provide a
  desktop/graphics API. Broader GPU operations are another scope decision.

Linux-native builds, richer runtime, SMP, GPU and desktop work must not silently
become gates blocking the first working Linux-host zsh.

## If “like Linux on an Intel box” means bare metal

Defer until I1 works, and target one named motherboard/CPU/device configuration,
not generic PC compatibility. Additional work includes a bootable installer and
recovery path, firmware/ACPI platform providers, physical disk drivers (NVMe or
AHCI as appropriate), USB keyboard/input, a basic console, an actual NIC driver,
interrupt routing and power management. Physical devices replace the VirtIO
devices that made the VM tractable. GPU acceleration and broad hardware support
are separate large projects.

Reuse applicable published Apple drivers/frameworks after checking source,
architecture and device IDs. Do not assume that open XNU includes every driver
shipped in macOS or that a compiled driver supports an arbitrary PC. There is no
current evidence justifying a bare-metal installer or general Intel-PC readiness.

## What the user needs to provide

For implementation: access to the intended Linux host and its CPU/distribution
details (read-only inventory can obtain these). For accelerated x86 operation,
hardware virtualization must be enabled and the launcher allowed to access
`/dev/kvm`. Install the distribution's QEMU system-emulation and appropriate
EDK II firmware packages when the target is confirmed. A Swift toolchain is
needed only if building the host Swift launcher there; the initial boot probe
can use QEMU directly with guest artifacts built on the Mac.

No SD card, Pi, physical power-cycle sequence, extra GPU or disk erasure is needed.
The 4090 is not needed for the shell, and its presence does not identify the CPU
architecture/vendor or prove KVM availability.

## Distance and estimates

These are coarse engineering planning ranges, not measured completion dates or
promises. A first QEMU firmware/kernel-entry probe is needed to narrow them.

| Outcome | Assessment from current code |
| --- | --- |
| Current Mac command-line VM | Already achieved for the documented experimental profile |
| First ARM64 zsh on Linux via emulation | Days-to-weeks-class port, depending on firmware/device-contract differences |
| Repeatable Linux-host shell with persistence/network | Additional integration/packaging work; still a prototype, not distro parity |
| Hardware-accelerated x86_64 Darwin VM on Intel | Weeks-to-months-class architecture/platform port; build/provider closure unproven |
| Bare-metal shell on one selected Intel PC | Months-class or longer, strongly dependent on device-driver availability |
| Broad, Linux-like hardware/software ecosystem | Open-ended OS/distribution project; no defensible short ETA |

Recommended next implementation: L0 and a bounded L1 boot probe, with an x86
build-dependency inventory in parallel. Deliver L2 for portability, then prioritize
I1 for native Intel speed. Re-estimate after actual boot evidence. No new soak,
desktop or full macOS-service requirement is introduced by this plan.
