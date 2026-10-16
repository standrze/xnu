# Next shell dependency: userspace process launch

Audit and package date: 2026-10-11. Process execution: **passed on physical Pi 5**.

## Physical process result — 17:44 UTC

The corrected literal image `043eeb43dc55aeb520be7cd5c4541ad39b222b120a6ddf166f809ea834a20341`
was staged with preserved backups and booted once from SD by software reboot.
The first recorder stopped with zero TX because the generic keyboard-start
line was torn. Its boot capture contains the intact terminal loader and
repeated process-ready prompts. A guarded host-only recovery continued that
same boot; no additional reboot or payload build was performed.

Recovery validates the recent zero-TX capture's hash and device, requires one
loader and repeated process readiness, rejects reset/panic evidence, discards
queued input and requires two fresh process-ready/prompt pairs before TX.
The missing keyboard log is explicitly recorded, not synthesized or counted
as observed. Input delivery is established by actual command responses.
Seven focused host protocol checks pass, including rejection of stale,
modified, already-transmitted and reset captures, and no TX without fresh
process-specific readiness. The default cold-start guard is unchanged.

The Pi produced, in order:

```text
RPI5XNU:PROC:FORK_CHILD
RPI5XNU:PROC:EXEC_CHILD PID=0x0000000000000002 ARG=RPI5_EXEC_ARG BSS_ZERO=1
RPI5XNU:PROC:WAIT_CHILD PID=0x0000000000000002 STATUS=0x00002a00 COW=1
RPI5XNU:PROC:PASS
xnu-rpi5> status
PID 1 alive; serial console active.
xnu-rpi5>
```

All six process checks passed; 15 bytes were transmitted (`process`, then
`status`). Evidence and exact staging/boot commands are preserved in
`build/rpi5/shell-process-literals-20261011/`. Full boot capture:
`build/rpi5/mac-process-literals-20261011/serial.bin`, SHA-256
`7c71de7977085c3fa3f535a2319d589f318dd8b1e98f67fb2bcd3fb7b789b4cd`.
Same-boot command capture and machine-readable result:
`build/rpi5/mac-process-literals-resume-20261011/{serial.bin,state.json}`,
serial SHA-256 `56ba2971c946c933bdb30a7d868bced5ac091f121c37fab84204cbb34eba806d`.

This proves the shell's process-launch prerequisite, not a general shell,
cold-boot repeatability, or formal Gate 3 exit. Next: implement a bounded
read-only multi-file RAM root while preserving the single-executable path.

## Latest physical result and revised continuation

The readiness retry image was subsequently staged and booted once on the Pi.
Its clean repeated marker was received, then `process` returned
`Unknown command. Type help.`. The recorder was stopped at that failure with
eight transmitted bytes. No fork/exec result was obtained. Evidence:
`build/rpi5/mac-process-handshake-20261011/{state.json,serial.bin,outcome.json}`;
raw SHA-256 `3c84babbe5c54c557ec310cd2e743e16a7f16ec1c9b4e46fc9545ebaddf00591`.

Disassembly and linked symbols proved the cause: `_process_cmd`, `_newline`,
and `_crlf` all addressed `0x100000af2`, containing `LF CR LF process NUL`.
The newline literals lacked NUL terminators in the cstring section, causing
linker coalescing. Both are now terminated; the builder and package verifier
check exact bytes at linked command/exec-argument/newline symbol addresses.
The runner also fails immediately if the process command is rejected.

Seven focused tests passed. The new check rejects the actual faulty artifact;
the corrected package passes all 14 assertions. One payload and loader build
produced `build/rpi5/bl33-probe-w7agabax/probe.bin`, SHA-256
`043eeb43dc55aeb520be7cd5c4541ad39b222b120a6ddf166f809ea834a20341`, with the
same working kernel. Physical validation later passed as recorded above.
**The artifact record is `build/rpi5/shell-process-literals-20261011/README.md`
and its staging script.** Preserve the following earlier history; do not restage
either superseded process image.

### Earlier readiness failure

SSH access was restored and Linux root `/dev/nvme0n1p2` verified. The exact
XNU_PROBE card and both original image hashes matched. A verified working
polling backup was saved on SD and NVMe, then the original process image
`bl33-probe-wal7ixew` was staged by changing only `probe.bin`.
`build/rpi5/shell-process-trial-20261011/{staging.log,reboot.log}` records SD,
configuration, firmware-file hashes, EEPROM and the one software reboot.

That SD boot reached userspace, but concurrent secondary CPU UART messages
tore the one-time `RPI5XNU:PROC:TRIAL_READY` marker. The guarded recorder was
stopped after diagnosing it, with **zero transmitted bytes** and no process
result. Raw evidence: `build/rpi5/mac-process-trial-20261011/{serial.bin,state.json}`,
SHA-256 `ca94e6a08332d08eaaeb93092a40244f64493e65c18b82717b83ee5685a72658`.
This is not cold-boot proof, a fork/exec failure, or a successful process trial.

The process-only payload now repeats readiness once per second using `select`
until the first console input. It does not repeat process commands or relax
the host's marker requirements. Four focused protocol tests pass, including
no transmission after a torn marker until a clean repeat arrives. One revised
payload/loader build produced `bl33-probe-6du6vix7`, all 13 package assertions
pass. Revised probe SHA-256:
`c8e9009e77fe9266ea1c77baff48589c3b988d46ed9bc71f415c36b07cb8679e`.

The readiness-only staging instructions in
`build/rpi5/shell-process-handshake-20261011/README.md` are now historical;
use the corrected literals package above. The working kernel and preserved
four-command polling payload were not changed. No new soak or full suite.

## Why this is next

The physical Pi already boots the polling console. The missing evidence for
a shell is process launch, not another UART driver or stability soak.
`bsd/kern/kern_fork.c`, `bsd/kern/kern_exec.c` and
`osfmk/arm64/status.c:thread_set_child` implement fork/exec, but the four-command
PID 1 never calls them. On arm64 Darwin a forked child is identified by
`x1 == 1`; testing `x0 == 0` directly would be wrong without libc's wrapper.
The exec-built stack starts with a pointer-sized argc slot before argv.

The current mockfs has only root, devfs mount point and one executable vnode.
`sbin` aliases root; `launchd` names that executable. There is no `/bin/sh`,
directory listing implementation or multi-file root. The first new trial
therefore uses `/sbin/launchd` to re-exec the same static Mach-O in child mode,
without changing the working kernel, mockfs or SD format.

The opt-in `pid1_process.S` adds `process` to the existing terminal. It checks:

1. `fork` creates a child, which writes a distinct BSS cookie.
2. `execve` replaces the child's image and passes two checked arguments.
3. The re-executed child observes fresh zero-filled BSS and exits with code 42.
4. PID 1 waits for that exact PID, checks normal exit status `0x2a00`, and
   checks that its own cookie was not changed by the child (COW isolation).
5. PID 1 returns to the prompt and answers `status`.

Errors identify the failing stage; fork/wait/exec errors include errno where
available. A child exits on failure rather than spinning forever. A kernel
hang is still bounded only by the existing recovery policy; the host runner
has a separate command deadline and does not power-cycle the board.

This is a shell prerequisite, **not a general shell**. After it passes on the
Pi, add a bounded read-only multi-file RAM root and a static shell/utility
payload, then prove real command execution and repeated controlled cold boot.
Neither Ethernet nor persistent storage is required for that RAM-root path.

## Evidence separation and provenance

| Result | Evidence | Scope |
| --- | --- | --- |
| Physical polling console passed | `build/rpi5/mac-terminal-v231-longwait-20261011/state.json`, `serial.bin` | Eleven checks on Pi 5; not fork/exec or a general shell |
| Process payload built | `build/rpi5/pid1-process-20261011/manifest.json` | Static arm64 Mach-O; exact compile/link commands and included assembly hashes |
| Process loader built | `build/rpi5/bl33-probe-wal7ixew/manifest.json` | One build, existing kernel reused; source/input hashes and full loader commands |
| Focused host checks passed | Commands below; 17 protocol/regression tests plus 3 package tests | Synthetic socket protocol and package rejection, not CPU emulation |
| Original package preflight passed | Thirteen identity assertions | Substring checks missed the later linked-literal defect |
| First physical process-image boot | Handshake failed before commands | XNU userspace reached; torn readiness marker, zero TX, no process result |
| Revised readiness handshake | Physical handshake passed; process command rejected | Eight TX bytes; linked cstring defect prevented fork |
| Corrected command literals | Physical process trial passed | Six process checks, child PID 2; split capture on one software boot, not cold-boot repeatability |

No QEMU boot was performed for this change and no emulator result is credited
as Pi evidence. The successful physical polling capture SHA-256 is
`f83420c5aa17df11770b814e7062fa90c305c5a7b9941f251a799dd44cdcfc74`.

Base commit: `ac9718fb1af618d5ce8678d0dc6e8a58f252216f`, **dirty checkout**.
The new code is uncommitted; do not claim that the base commit alone reproduces
the port. The payload manifest hashes its entry source, included terminal
source and builder. The loader manifest hashes its source inputs and embedded
payloads. The reused kernel's original provider-enabled build command/source
inventory is in `build/rpi5-xcode27/run-glrazu5x/manifest.json`.
Commands are recorded for reproduction; bit-for-bit reproducibility of a
second complete build has not been tested and no redundant rebuild was run.

| Artifact | SHA-256 |
| --- | --- |
| New `bl33-probe-wal7ixew/probe.bin` | `cf9b829ce449501f41b5df53024d6e6eea4a85bfcd84d15b35d695008612e92f` |
| New `pid1-process-20261011/ramdisk.bin` | `04109ba13256f340e9f4adb969873a1e90e5e6bcfecdb716539a54f806fce592` |
| Reused kernel | `a0c1a934b795c9f7e1f1c4e4c888d31327069023e1c74024b76fe4717bbbc741` |
| Preserved working polling probe | `a4fb01fcee8724cd68b5a162b77c80e72880a2afba0db9366fda9d7371d8ca53` |
| Preserved Gate 3 baseline | `454906aa802f013549ef936a9d15bcc42b10638ed73d6759a276797737b1d06c` |

## Build and focused check commands

Run from this checkout; the outputs below already exist. Reuse them rather
than rerunning unchanged builds. Choose a new output directory if source changes.

```sh
python3 tools/rpi5/build_pid1.py --source tools/rpi5/pid1_process.S --output-dir build/rpi5/pid1-process-20261011
python3 tools/rpi5/build_probe.py --load-address 0x9000000 --kernel build/rpi5-xcode27/obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712 --init build/rpi5/pid1-process-20261011/ramdisk.bin --transfer --gate3-cpu-on-all --serial-terminal
python3 -m unittest tools.rpi5.tests.test_serial_process_trial tools.rpi5.tests.test_serial_terminal_trial
python3 -m unittest tools.rpi5.tests.test_serial_terminal_package
```

The loader command produced `bl33-probe-wal7ixew`. Preflight before staging:

```sh
python3 tools/rpi5/check_serial_terminal_package.py build/rpi5/bl33-probe-wal7ixew --kernel build/rpi5-xcode27/obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712 --init build/rpi5/pid1-process-20261011/ramdisk.bin --gate3-baseline build/rpi5/bl33-probe-ci45m9zs/probe.bin --process-trial
```

The existing kernel can be rebuilt if a kernel change becomes necessary with:

```sh
python3 tools/rpi5/rpi5.py build --profile xcode27 --jobs 4 --with-crypto-candidate --activate-crypto --with-pthread-provider
```

Do not run that merely to test this userspace change or overwrite the working
kernel unnecessarily. A provider-free kernel previously panicked during
crypto initialization.

## Original hardware continuation (superseded by revised package above)

Prerequisite: Pi reachable in **NVMe Linux**, not the old XNU image. Before any
write, verify `hostname` is `kamidana`, `findmnt -n -o SOURCE /` is
`/dev/nvme0n1p2`, and `lsblk` plus `blkid /dev/mmcblk0p1` identify the disposable
VFAT **XNU_PROBE**, UUID **4FA7-3725**, PARTUUID **5ae1f07e-01**. If any identity
differs, stop and resolve the target; do not substitute an NVMe partition.

Do not assume watchdog expiry returns to NVMe: an earlier capture
(`build/rpi5/mac-soak-transition-20260927`) disproved automatic fallback with
the SD inserted. That old result is not a fresh test of today's configuration,
but no new fallback guarantee is made here. If a physical transition is
needed, power off completely before removing the SD and boot NVMe Linux
without it. Never remove the SD while the Pi is powered on. Confirm Linux and
the currently reachable IP before planning SD staging.

Last verified SD configuration (2026-10-11) is shown below. Read it back on
Linux before staging; the package's expected-config file is a reference, not
authority to replace unknown support files or boot settings.

```ini
[all]
arm_64bit=1
enable_uart=1
uart_2ndstage=1
auto_initramfs=0
camera_auto_detect=0
display_auto_detect=0
armstub=bl31.bin
kernel=probe.bin
kernel_address=0x9000000
device_tree=bcm2712-rpi-5-b.dtb
device_tree_address=0xb000000
set_reboot_order=0xf6
kernel_watchdog_timeout=60
```

Embedded kernel command line remains:

```text
serial=3 debug=0xa -enable_kprintf_spam kt=2 -noprogress rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 bcm2712_cpu_on_all=1 bcm2712_terminal_watchdog=1
```

Stage **only the new probe.bin** after these checks:

1. Read the SD read-only first. Require the current probe hash to be the
   working polling hash above. Verify the Gate 3 baseline backup separately
   (`probe.gate3-20260927.bin`) and preserve all existing backups.
2. Keep a distinct verified backup of the current polling probe both on SD
   and NVMe. Transfer the candidate to a distinct NVMe filename, hash it,
   then mount only the verified SD partition writable. Copy to a temporary
   SD filename, verify its hash, atomically rename it to `probe.bin`, sync,
   and remount read-only. Do not overwrite the backup names or change firmware.
3. Leave the Pi running Linux until the Mac's receiver prints READY. Close
   any user `screen` session first; there must be only one serial owner.

On the Mac, verify the connected Debug Probe is serial `E66480454F719939` and
resolve its current `/dev/cu.usbmodem…` path. The last path was
`/dev/cu.usbmodem102`, firmware 2.3.1. Start this **before** the one boot attempt:

```sh
caffeinate -i python3 tools/rpi5/serial_terminal_trial.py /dev/cu.usbmodem102 build/rpi5/mac-process-trial-20261011 --process-trial --boot-wait-seconds 3600 --seconds 180
```

Do not reuse the output directory if it exists. The runner refuses to send
input until it receives the terminal-only loader marker, `Serial keyboard
started`, and `RPI5XNU:PROC:TRIAL_READY`. It sends just `process` and `status`;
it does not repeat the old terminal test matrix or start a soak.

After READY, in the verified Pi Linux SSH session request one-shot SD boot:

```sh
sudo vcmailbox 0x0003808b 4 4 0xf61
sudo reboot
```

This is one controlled trial boot, **not cold-boot reproducibility proof**.
Archive configuration and EEPROM readback before reboot. Expected serial order:

```text
RPI5XNU:PROC:TRIAL_READY
RPI5XNU:PROC:FORK_CHILD
RPI5XNU:PROC:EXEC_CHILD PID=0x<16 hex digits> ARG=RPI5_EXEC_ARG BSS_ZERO=1
RPI5XNU:PROC:WAIT_CHILD PID=0x<same PID> STATUS=0x00002a00 COW=1
RPI5XNU:PROC:PASS
xnu-rpi5>
PID 1 alive; serial console active.
xnu-rpi5>
```

Required evidence: raw `serial.bin`, its SHA-256 and `state.json` with six
checks and matching child PID; exact staged probe/config hashes, kernel and
init manifests, source revision/hashes, and boot type. A first failure should
retain the failure-stage line or kernel panic, change the hypothesis/code,
and **not** rerun unchanged. Missing markers means no input and no acceptance.
After this dependency passes, the full shell and its repeatable cold boot
remain unfinished. The roughly one-hour watchdog-service window and formal
Gate 3 backlog remain unchanged; automatic return to NVMe is not certified.
