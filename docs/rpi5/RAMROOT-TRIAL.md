# Read-only multi-file RAM root

2026-10-11: **passed on the physical 8-GB Pi 5**. The previous
physical `fork`/`execve`/`wait4` milestone remains preserved in
[PROCESS-TRIAL.md](PROCESS-TRIAL.md). This dependency does not complete the
requested general shell or repeatable cold boot.

## Physical result — 18:20 UTC

The candidate below was staged at 18:16:19 UTC after re-verifying NVMe Linux,
SD UUID/PARTUUID, config and backups. One software SD reboot at 18:16:40 UTC
mounted ten archive nodes and passed the file checks. The first child exec
also succeeded, but a concurrent startup timer diagnostic tore the parent's
wait/COW and PASS text. That incomplete result was not counted as a pass.

The first same-boot recovery sent a long echo handshake; only its leading
characters arrived, with no newline/response. No second process command was
sent by that failed recorder. Source inspection shows the keyboard polls
every 16 ms. A short fresh echo, preceded by canonical VKILL and paced at
25 ms per byte, recovered the prompt. This supports the input-burst-loss
hypothesis but does not establish the exact buffering fault. Use paced host
input for longer lines until the receive path is investigated.

One process retry after startup logging settled then passed all seven checks:
cross-page file read, EOF, read-only/missing-file rejection, directory listing,
fork/exec from `/bin/child`, fresh arguments/BSS, exact child PID 3 exit 42,
parent COW and PID 1 prompt recovery. No second reboot, new image, kernel
rebuild or soak was needed. Four focused recovery/guard tests passed; the
changed short-paced echo fixture subsequently passed separately.

Evidence:

- Full boot/partial result: `build/rpi5/mac-ramroot-20261011/serial.bin`, SHA
  `5434d969a9bd53841d028eb91c54b77be1043eacee205c07d107dba8e1aca5df` (8 TX bytes).
- Failed long echo: `build/rpi5/mac-ramroot-recovery-20261011/serial.bin`, SHA
  `2562cade1d8c2398aafc6f9c2f6d94146dfcd7d622b70128c55a54435f641a16` (43 TX bytes).
- Successful same-boot retry: `build/rpi5/mac-ramroot-paced-recovery-20261011/{serial.bin,state.json}`,
  SHA `32c97a8998fc175ade4953ee561fd0e1cb24b60c831e9f4516cbc526f7aebe75` (31 TX bytes).
- Staging/config/reboot logs and artifact identities:
  `build/rpi5/shell-ramroot-20261011/`.

Recovery command (already completed):

```sh
caffeinate -i python3 tools/rpi5/serial_terminal_trial.py /dev/cu.usbmodem102 build/rpi5/mac-ramroot-paced-recovery-20261011 --ramroot-trial --recover-ramroot-result build/rpi5/mac-ramroot-20261011 --boot-wait-seconds 30 --seconds 180
```

The Pi is left running the successful RAM-root XNU image; all recorders have
exited. Next: the actual static shell and utility payload. Repeated cold boot
remains unproven. The user prefers autonomous work and physical-action requests
only when unavoidable; do not ask for another recovery before an image is ready.

## Implementation boundary

Only BCM2712 DEVELOPMENT enables the archive extension. Existing raw Mach-O
images retain the legacy mockfs lookup/paging behavior. A valid archive gives
each file its own vnode, stable file ID, exact length and backing-device
offset. Direct physical paging stays disabled; the existing cluster pager
reads the file's page-aligned extent. Open and directory listing are supported
for the archive, with read-only mount flags and 0444/0555 permissions.

The v1 image starts with the unchanged static launchd executable. All files
occupy disjoint 16-KiB-aligned extents followed by zero padding. The final
16-KiB page contains `RPI5RFS1`, version/count/total-size, and up to 32 node
records. A record has parent index, directory/file type, offset, byte length,
mode, reserved zero fields and a 63-byte maximum ASCII component name.
Earlier parent indices guarantee an acyclic root-connected tree. The parser
rejects duplicates, dot components, unsupported modes/types, overflow,
overlapping padded extents, metadata overlap and populated `/dev`. `/dev`
is reserved as the devfs mount point; `/sbin/launchd` must be executable at
offset zero. Maximum complete image size remains 64 MiB.

There are no archive writes, symlinks, hard links, ownership changes or
persistent storage. This is sufficient infrastructure for a bounded static
shell/utility payload; that payload has not been implemented here. The
kernel parser checks metadata bounds; it is not a cryptographic authenticator.
The existing loader integrity envelope covers the complete RAM image.

## Candidate and focused evidence

- Kernel: `build/rpi5-xcode27/run-ckc8qqkh/manifest.json`, SHA-256
  `d133f3a21ff9d3397aed7dfdd04210fe79061d8919d5046010dfa1919980a10f`.
- Loader: `build/rpi5/bl33-probe-ws35ep1c/probe.bin`, SHA-256
  `e1548c9e083fa7f4c78f19834075cab125683f76d3d9ac56ae3eb95705cdaa4d`.
- Archive: `build/rpi5/ramroot-trial-20261011/ramdisk.bin`, 131072 bytes,
  SHA-256 `2ebc665deb4969ecd63b9a91b5f2acf064ea03caaf003745f64cc6ac81d003b1`.
- Base commit `ac9718fb1af618d5ce8678d0dc6e8a58f252216f`, dirty port sources;
  base commit alone does not reproduce the port.
- Three packager/shared-parser tests passed, with native C AddressSanitizer
  and UndefinedBehaviorSanitizer checks. These are host fixtures, not XNU IO.
- Eleven focused protocol/linked-literal regression tests passed. These use
  socket pairs or synthetic Mach-O data, not emulation or physical execution.
- Sixteen actual-package preflight assertions passed.

The first build stopped before compilation because sandboxed Make could not
read host sysctls (`run-kuygutto`). The next compile reported type errors in
the new vnode operations (`run-rrrtwmsf`); these were corrected. One successful
incremental kernel build followed (`run-ckc8qqkh`), with one userspace build
and one loader build. No full suite, unchanged build loop, soak or QEMU run.

## Exact build and verification commands (already run)

```sh
python3 -m unittest tools.rpi5.tests.test_ramroot
python3 tools/rpi5/rpi5.py build --profile xcode27 --jobs 4 --with-crypto-candidate --activate-crypto --with-pthread-provider
python3 tools/rpi5/build_pid1.py --source tools/rpi5/pid1_ramroot.S --output-dir build/rpi5/pid1-ramroot-20261011
python3 tools/rpi5/build_ramroot_trial.py build/rpi5/pid1-ramroot-20261011/pid1 build/rpi5/ramroot-trial-20261011/ramdisk.bin
python3 tools/rpi5/build_probe.py --load-address 0x9000000 --kernel build/rpi5-xcode27/obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712 --init build/rpi5/ramroot-trial-20261011/ramdisk.bin --transfer --gate3-cpu-on-all --serial-terminal
python3 -m unittest tools.rpi5.tests.test_ramroot_serial tools.rpi5.tests.test_serial_process_trial tools.rpi5.tests.test_prepare_pid1.PreparePid1Tests.test_linked_process_literal_addresses tools.rpi5.tests.test_prepare_pid1.PreparePid1Tests.test_rejects_literal_coalescing_even_when_word_is_present
python3 tools/rpi5/check_serial_terminal_package.py build/rpi5/bl33-probe-ws35ep1c --kernel build/rpi5-xcode27/obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712 --init build/rpi5/ramroot-trial-20261011/ramdisk.bin --gate3-baseline build/rpi5/bl33-probe-ci45m9zs/probe.bin --ramroot-trial
```

The separate trial image uses `process` to check open, cross-page read from
`/etc/boundary`, EOF, write-open rejection, missing-path rejection and directory
listing including EOF. It then forks and execs `/bin/child` from a distinct
extent, checks fresh BSS/arguments, wait status 42, COW and PID 1 prompt recovery.
The two executable files currently contain the same diagnostic program;
this tests distinct file mappings, not different utility programs.

The recorder requires the terminal loader plus intact `RAMROOT:READY` and
`PROC:TRIAL_READY` markers, which repeat until input. It never sends this
trial to the older process-only or Gate 3 images. A RAM-root failure reports
a numbered step and syscall result; stop at the first actionable failure.

## Original hardware continuation (completed above)

The SSH check on `sandrzej@192.168.4.23` timed out after the build. Last direct
evidence is the successful process-trial XNU prompt; SSH failure alone does
not establish what is running. No SD writes or Pi power changes occurred in
this filesystem implementation turn. The staged SD still contains the proven
process image, not this candidate.

Staging requires NVMe Linux root `/dev/nvme0n1p2` and the exact XNU_PROBE
partition reinserted: UUID `4FA7-3725`, PARTUUID `5ae1f07e-01`. If Linux is
unavailable, power off, remove SD, boot Linux from SSD, then reinsert SD.
Use `build/rpi5/shell-ramroot-20261011/README.md` and its guarded staging script.
Arm the recorder before the one authorized software SD reboot:

```sh
caffeinate -i python3 tools/rpi5/serial_terminal_trial.py /dev/cu.usbmodem102 build/rpi5/mac-ramroot-20261011 --ramroot-trial --boot-wait-seconds 3600 --seconds 180
```

Required evidence: firmware SD boot, `RAMROOT:MOUNT NODES=10`, intact
readiness, `RAMROOT:FILES_PASS`, the matching-child process markers and seven
checks in `state.json`, preserved raw serial and its SHA-256. Record failures
as failures; compilation/preflight do not satisfy this hardware requirement.
If it passes, implement the actual static shell/utilities on this root, then
prove usable commands and repeated cold boots. Formal Gate 3 remains open.
