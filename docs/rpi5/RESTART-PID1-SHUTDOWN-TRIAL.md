# PID1 shutdown-policy successor

This is a distinct candidate, not an amendment to the failed copy-phase trial.
The latter reached XNU and zsh, but the kernel's normal shutdown SIGTERM killed
the project PID1, causing a panic. Its capture remains invalid.

The new image changes only `/sbin/launchd` in the 33-node root. The kernel,
panic path, `/bin/sh`, zsh, genuine `/sbin/reboot`, framebuffer and copy-phase
watchdog policy remain unchanged. PID1 uses real Darwin syscalls 48 and 52,
plus nonblocking wait4(7), to block and observe SIGTERM. It permanently stops
respawning after observation, reaps without exiting, and sleeps at most one
second between polls. A child restores the complete old signal mask before
exec. One fork already in flight may cross signal delivery; atomic prevention
of every post-arrival fork is not claimed. Failure to install the initial mask
does not produce readiness or a child, but does not prove TERM protection.

Candidate: `build/rpi5/display-restart-init-xw9wi1um`.
Manifest: `c55fcd57295b24135deb7bcf1d525d0e87ca934e9e4e49723bd2f0e1780675a4`.
Image: `91cd2dae1ecd4b5fe21a66cfa2dfa521ca9a39c4ebf6a9aa7e9220257803b36c`.
Tag: `7de3ff0d569648c88bd65546c7d05b09`.
Qualified report: `build/rpi5/restart-init-qualification-20261014/checker-report-v2.json`,
SHA `0f7c541c7cde478905290dad64070d6e3af809677a94867381e4f9c162cc024e`.
The separately pinned v2 byte-report qualifier scopes historical component
checks separately from the current root-only launchd change. The original
report, checker and package remain intact; the old preparation is unused.

## Admission and result

The host requires the new image tag, exact root33/copy/framebuffer/watchdog
markers, restart eligibility, and the new `INIT:SHUTDOWN_READY` marker followed
by the shell prompt. Four fresh nonce-bound zsh checks precede exactly one
genuine `/sbin/reboot` invocation. Echoed commands are not output proof.

Zero or one exact `INIT:STOPPING SIGTERM NO_RESPAWN` row is accepted between
actual executed reboot nonce and PRE_SMC. It is optional because the original
kernel may suspend PID1 before its next poll. Error stops, duplicate or
misordered stop rows, panic, and whole-return-tail faults remain failures.
Return requires actual fresh firmware/NVMe and independently verified new
SSD Linux. Nominal early-watchdog comparison is engineering evidence only;
unconditional physical PSCI causality and permission to remove the watchdog
remain false. The 180-second service, 15-second hardware countdown, 120-second
TX window/45-second reserve, and 300-second host return budget are unchanged.

## Operator handoff (main hardware owner only)

Current completed baseline is `restart-copy-restored-20261014`, catalog434;
the new controller calls only `stage_restart_copy_trial.restoration` for it.
No preparation or hardware is performed by this document or qualification.

```sh
python3 tools/rpi5/stage_restart_init_trial.py prepare \
  --baseline build/rpi5/restart-copy-restored-20261014 \
  --prior-seal-sha256 a1829bedad203cc6a4f1b10037358309792a46a0d3941daee20887d1cb8a0c4c \
  --prior-plan-sha256 9aa6aefa7c32f74999417067cd46d612028cfc54c085508193983941d441bb52 \
  --linux-boot-id 2a3ae56f-82b9-44eb-a300-6fed62839224 \
  --output build/rpi5/restart-init-prepared-v2-20261014
```

After independent byte admission, `publish` takes the returned prepared seal
and `--execute`. `launch` takes the actual installed seal/plan, fresh verified
boot, device and unused capture/output directories. Its original `arm_once`
recognizes the real `CAPTURE_ARMED RESTART_INIT` line before its single SSH
reboot. Use `return`, then explicit `restore --execute`, then `replay` with
their actual result pins. Unknown starts are never retried. All original
config/loader archives and normal-firmware protection remain in force.

## Offline qualification

```sh
RPI5_INIT_SHUTDOWN_PACKAGE="$PWD/build/rpi5/init-shutdown-0oa103mt" \
RPI5_INIT_SHUTDOWN_MANIFEST_SHA256=6c49760687b828a5ed0b90968d751b32b79d761b69d3928424973ace987f4623 \
python3 -m unittest tools.rpi5.tests.test_init_shutdown -v

RPI5_RESTART_INIT_PACKAGE="$PWD/build/rpi5/display-restart-init-xw9wi1um" \
RPI5_RESTART_INIT_MANIFEST_SHA256=c55fcd57295b24135deb7bcf1d525d0e87ca934e9e4e49723bd2f0e1780675a4 \
python3 -m unittest tools.rpi5.tests.test_display_restart_init -v

python3 -m unittest tools.rpi5.tests.test_restart_init_transport \
  tools.rpi5.tests.test_restart_init_media -v
```

Native policy cases use explicit process/kernel doubles. The full target TU,
static executable, exact root bytes and actual native loader materialization
are checked separately. These do not claim target shutdown execution.
