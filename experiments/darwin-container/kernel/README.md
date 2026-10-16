# VZGENERIC XNU experiment

Packaged workloads 0.3.0 use the separate build `build/vzgeneric-jyf6xwpb/`,
kernel SHA-256 `950c413cddeab8bea8748971e40a1b3ace06f66daac06e5ea42cdfb19a393803`.
It retains the seed-clear correction and permits a genuinely absent virtual NIC;
a present but invalid network device still fails configuration. Offline and NAT
managed workload boots are qualified by [the package trial](../WORKLOADS.md).
This did not replace or rebuild the workspace kernel below.

The persistent workspace uses the distinct successful build
`build/vzgeneric-1fx0koif/`, kernel SHA-256
`d48000f2f821b4b81a652e43ee00b186059ad531273476fbd9c7ff124245145a`.
Its isolated snapshot fixes the inherited `native_rand` clearing length with
`sizeof(native_rand)`. It passed the workspace shell/network and clean-restart
trial. [Current workspace and evidence](../WORKSPACE.md). Earlier artifacts and
the inherited-issue observations below describe their original build state.

This is an isolated **single-vCPU DEVELOPMENT** kernel target for a generic
ARM64 EFI virtual machine managed by Apple's Virtualization.framework. It is
not the existing Apple `VMAPPLE` machine target and uses no QEMU or Apple private
platform-support archive. Building it is not evidence that XNU has booted.

Current DC3-qualified VM kernel: SHA-256
`b3a0d9f49e2af4bfe28ac716111b05a030d1c8fb273c1e4ffe103e2a36582d53`.
The managed output-flood trial exposed an invalid timer-status invariant in the
previous `a8048424...` kernel. The VZ-only `vz_irq.inc` now treats an acknowledged
PPI27 with cleared timer status as stale: complete it without running the clock
handler. Pending timers still run the normal handler; other unexpected real
interrupts still panic. An ISB now precedes EOI to synchronize timer rearming.
This matches the handling distinction in the public
[Linux architectural timer implementation](https://github.com/torvalds/linux/blob/master/drivers/clocksource/arm_arch_timer.c)
without importing its code. The old kernel/manifest are preserved under
`build/vzgeneric-jj770p16/dc2-dc3-pre-timer-fix/`.

Three focused native dispatch/overlay checks and actual final-kernel VZ command,
cancel, orphan, deadline, two full output-cap trials and a legacy-shell regression
passed. See the [DC3 report](../results/2026-10-12-dc3-verification.json).
The inherited seed-clear defect below is still unresolved; the old kernel's exact
stack-layout observation is not a hardening proof for this newly linked image.

The separate DGT1 PTY follow-on kernel is
`e7ed0c3afc37936087b012b3be136c888b257b33beb64d234db691b6abce27d8`,
in `build/vzgeneric-abbct5u5/`. It adds used-ring acquire ordering, empty RX
completion recycling and explicit invalid-completion failures. A native console
fixture and two focused real PTY boots passed; this does not re-qualify DC3 or
claim a soak. The old storage kernel and private `0.1.0` package remain intact.
See [terminal evidence](../results/2026-10-12-framed-terminal/verification.json).

The distinct opt-in network kernel is SHA-256
`0501225204ac5711fd409f82e9ff70138d126c002f654bea758827345c023da9`,
in `build/vzgeneric-8c5vzyrd/`. It adds the modern PCI VirtIO net driver,
bounded owned DMA and XNU Ethernet ifnet/BPF plumbing. Real guest DHCP, DNS A
and TCP exchange passed together with all PTY checks. Subsequent userland-only
images also passed guest-triggered host Metal compute and original Apple DNS
wire parsing; the GPU bridge requires no new kernel GPU device.
[Latest combined evidence](../results/2026-10-12-apple-network-gpu/verification.json).
[Network transport/limitations](../userland/NETWORK.md).
This is a separate experimental profile, not a new Pi or DC3 qualification.

## Build boundary

`build.py` copies the **current working source**, including the source-only Pi
port's uncommitted changes, into a new `kernel/build/vzgeneric-*` directory. It
hashes copied files, checks for concurrent source changes, and applies a reviewed
allowlist of portable compatibility guards plus the maintained `overlay/`.
It never edits the shared kernel tree or any Raspberry Pi build output.

The default reference is the successful
`build/rpi5-xcode27/run-obi6gw3d/manifest.json`. The script verifies the recorded
crypto and pthread object **and manifest** hashes, then copies those inputs into
the VM run directory. The existing source-prepared SDK is a read-only input.
The reference build's removable-SD/HFS provider and configuration are deliberately
not imported. Reference artifacts must still exist and match; stale inputs fail
instead of silently falling back to a binary SDK/KDK provider.

```sh
python3 experiments/darwin-container/kernel/build.py --prepare-only
python3 experiments/darwin-container/kernel/build.py --resume /absolute/path/to/kernel/build/vzgeneric-RUN
```

`--sync-overlay` on resume explicitly refreshes maintained overlay files,
installs the idempotent VZ trace/aperture-fix hooks, and records their new hashes.
Other source transformations in `build.py` require a new
snapshot, or an explicitly recorded equivalent patch to the isolated source.
Compilation may require normal host access because Apple's makefiles query
hardware size using `sysctl`. All generated files remain in this experiment.

## Hardware and loader contract

The initial observed VM has EL1 entry, 16-KiB page support, a 24-MHz architectural
counter, 36-bit physical addresses, a GICv3 distributor at `0x10000000`, a single
redistributor at `0x10010000`, and non-secure virtual timer PPI 27. The firmware's
FADT declares **PSCI HVC**, not the physical Pi's SMC. The kernel is deliberately
limited to these initial capabilities and does not claim portable SMP support.

The EFI loader must stop firmware services and transfer with MMU and caches
disabled under the retained legacy ARM boot-argument contract. Every retained
allocation (kernel, writable device tree, boot args, console record/rings and RAM
root) must be owned and protected from subsequent free-page allocation. The
managed physical span is entirely Normal RAM and obeys the bootstrap page-table
alignment/congruence requirements. No Pi UART identity mapping is enabled.

The diagnostic entry extension passes the physical console-record address in
`x2`, while `x0` remains standard `boot_args`. The VZ-only stack-free assembly
trace preserves it in `x27` and a writable global, and emits bounded checkpoints
`XDAZPMVC`. Initial C checkpoints read the global; C is free to use `x27`.
Two discovered console BAR pages get temporary Device identity mappings, with
conflicting/unsupported table layouts rejected. An early physical exception
vector prints `!E<ESR> L<ELR> F<FAR>` and parks. VM checkpoints `a` through `j`
retain this diagnostic while the old low mappings exist. The normal kernel
exception vector is restored immediately before `arm_vm_init` invalidates those
mappings. After VM setup, checkpoints use a separate normal-mapped console
binding, not the old identity aliases, to locate serial driver initialization.
These are localization diagnostics, not successful kernel initialization.

Apple device-tree properties consumed by the new target:

| Node/property | Representation |
| --- | --- |
| root `compatible` | Exactly `apple,vz-generic` including its terminating NUL |
| `/chosen/dram-base`, `dram-size` | LE64 DRAM envelope |
| `/chosen/vz-memory-map` | Existing v1 typed memory-map encoding: version/count LE32 then type/start/end LE64 records; Normal before Device, 16-KiB aligned, nonoverlapping |
| `/chosen/random-seed` | Fresh loader-obtained entropy, not a fixture or constant; normal Apple consumer clears it |
| `/chosen/vz-console` | LE64 PA of retained writable `vz_console_shared` record |
| `/chosen/vz-psci-hvc` | LE32 `1`, only after firmware verifies the HVC conduit |
| `/chosen/memory-map/RAMDisk` | LE64 PA and length of the unchanged read-only RAM-root format |
| `/cpus` | Exactly one CPU with actual MPIDR affinity LE32 `reg`, `state=running`, and measured `timebase-frequency` |
| `/arm-io/ranges` | Normal Apple arm-io bus envelope; nonzero physical base required by existing clock/serial discovery |
| `/arm-io/interrupt-controller/reg` | Four LE64 **absolute** values: GICD PA/size, GICR PA/size; GICR size is `0x20000` |
| console node | `compatible=virtio,pci-console`, `AAPL,phandle=1` |
| `/defaults/serial-device` | LE32 console phandle `1` |

The memory map must classify the GIC and every virtio BAR mapping as Device.
Console queues and record must lie within the kernel's retained managed RAM.
The kernel binds the loader's established virtio rings without resetting the
device. The shared transport source is copied verbatim from
`loader/vz/virtio_console.{h,c}` and its input hash is recorded.

The GIC driver routes PPI27 and self-SGI1 as Group 1 IRQs using ICC registers.
It does not select the Apple Group 0/FIQ implementation. CPU registration and
self-signaling are real; secondary start, CPU sleep and unsupported IRQs fail
explicitly. Shutdown/restart invokes PSCI only after the declared HVC contract.
Distributor setup disables delivery before switching affinity routing and clears
inherited local/SPI pending and active state. Register identities were checked
against the public [Linux GICv3 definitions](https://github.com/torvalds/linux/blob/master/include/linux/irqchip/arm-gic-v3.h);
the implementation here is independently written, not a copied Linux driver.

## Reuse versus omissions

Reusable: source-only crypto/PRNG and pthread runtime, ARM VM/syscalls/process
model, read-only RAM root, and source-built static Mach-O userland. Legacy `rpi5`
names remain on those portable formats/providers for compatibility; they do not
mean Pi hardware code is selected.

Not included: Pi MMIO UART, GIC-400, PM watchdog, SMP trampoline/PSCI-SMC trials,
soak/qualification workloads, physical SD/HFS transport, network device driver,
dynamic linker/LibSystem, normal launchd, graphics, writable filesystem or Linux
OCI execution. This target does not enable private Apple PAC/CTRR virtualization.

The next proof is actual kernel entry, timer-driven scheduling, PID 1 executing
from the RAM root, an exact serial handshake/command round trip, and guest-driven
PSCI shutdown. A linked Mach-O file alone proves none of those.

## First build evidence

The initial isolated `make all` completed with exit 0 in
`build/vzgeneric-jj770p16/`. Its manifest includes the source snapshot,
effective source hashes, provider-input hashes, overlay hashes and exact command.
The log retains earlier failed compiler/link attempts as well; the final manifest
is the completion record.

Preserved initial artifact:
`build/vzgeneric-jj770p16/pretrace-baseline/kernel.development.vzgeneric`

SHA-256:
`6537d80bdb99706946800daeef6b538e7438e262a1eb437c61fc65914362abc5`

This initial pre-trial revision includes the loader's console alignment checks and
interrupt-masked single-vCPU ring mutation, so nested diagnostic output cannot
reuse a half-published descriptor. A fresh prepare-only snapshot also completed
successfully with the maintained build script and complete packaging closure.

Static checks: plain ARM64 `EXECUTE`/`NOUNDEFS`, no undefined symbols, real
`pe_vz_*`/virtio console/stack-probe symbols present, Pi boot-UART/watchdog/
PSCI-SMC/secondary-trampoline/Gate-3 symbols absent. This evidence is **build and
linked-binary validation only**, not a successful XNU VM boot.

The first real VM trial timed out after 45 seconds with the loader's native
console and XNU-handoff lines, but no registered kernel-console output. Its disk
and capture are retained at `/private/tmp/darwin-vz-xnu-trial-1`.
The first diagnostic kernel (`2b6080d0676102e79ce9f5e05dd94b050b9d1f560986ab7b57b99f1c36a81f79`)
emitted all six pre-MMU markers `XDAZPM` in the real VM, localizing progress through
initial page-table and control-register setup. It still did not reach the normal
kernel console. The second diagnostic kernel adds the temporary BAR mappings and
post-MMU/initial-C checkpoints. Its SHA-256 is
`1518930f7db9c3f3b5c791eaa123b7c6ada139807e6f17986fd72c531a1aa04f`.
Trial 3 emitted `XDAZPMVCISTBDELHKW`, reaching the call to `arm_vm_init`.

The third diagnostic image (`bdfe473f76cbaee2033c7e978064d221836acffb371ab899f7bfafb6ffd619b0`)
emitted VM checkpoints `a` through `h`, then an assertion trap. The exact binary
descriptor identified `arm_vm_physmap_init`'s final extent assertion: alignment
holes made its mapping exceed the reserved virtual aperture. The VZ-only fix
reserves `PTOV_TABLE_SIZE * ARM_TT_TWIG_SIZE` alignment headroom, matching the
existing non-large-memory path, and includes this in the L1 reservation. It
preserves randomized slide granularity, physical RAM size, and the assertion.
`python3 experiments/darwin-container/kernel/test_physmap_aperture.py` passes
three arithmetic regression tests, not kernel runtime tests.

Current artifact at `obj/DEVELOPMENT_ARM64_VZGENERIC/` rebuilt successfully with
SHA-256 `a8048424c4fb7c223fb3d90bc52f6bc5fe67aa28d6407f431899471a3b2257c9`.
Trials 7 and 8 subsequently booted this exact kernel in real VZ VMs, executed
RAM-root commands (including a timer-driven sleep), preserved nonce-bound exit
statuses 0 and 1, and powered off through normal XNU shutdown and PSCI HVC.
See `../results/2026-10-12-xnu-trial-7/` and `../results/2026-10-12-xnu-trial-8/`.
The earlier fault JSON remains a historical pre-fix/pre-trial record, not the
current runtime outcome. This narrow shell proof is not long-run or security
qualification.

## Known inherited issue: seed-buffer clearing

Read-only review found a separate size mismatch inherited in the frozen source
snapshot's `osfmk/prng/prng_random.c:bootseed_init`: `native_rand` is
`3 * SEED_SIZE` (192 bytes), but its final `cc_clear` uses
`BOOTLOADER_ENTROPY_REQUEST_SIZE` (256 bytes on ARM64). This is a 64-byte
out-of-bounds clear and remains a source-hardening follow-up; it has **not** been
changed in the frozen diagnostic kernel.

For the exact `a8048424...` kernel, linked `_early_random_init` disassembly places
`native_rand` at `sp+0xf0` through `sp+0x1af`, and `bootloader_rand` at `sp+0x1b0`
through `sp+0x2af`. The 256-byte clear at `0xfffffe00074761ac`–`0xfffffe00074761b4`
overlaps only the first 64 bytes of the already-cleared bootloader buffer in
this particular stack layout; it does not reach the canary (`sp+0x2b8`) or saved
frame/return registers. That observation does not make the C access valid or
prove other builds safe. Actual VM checkpoints passed entropy initialization
and reached the shell, so this is **not** the diagnosed physical-aperture startup
assertion or the later bootstrap-PID1 shutdown failure. Fix and regression-test
the size expression separately before any production/security qualification.
