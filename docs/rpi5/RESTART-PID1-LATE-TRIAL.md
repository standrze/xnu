# Bounded late PID1 readiness successor

The prior image reached the real XNU/root33 shell, but its early PID1 readiness
line was lost to independent SMP/kernel console output. Its 41,681-byte capture
remains failed with zero host UART payload input. No success is reconstructed.

This distinct image changes only `/sbin/launchd` in the root. The blocked-TERM,
nonexiting stop-respawn policy is retained. The first readiness report follows
one successfully completed one-second select sleep before the first fork.
Interrupted sleeps do not count. At most two later reports follow successful
one-second polling sleeps; the global three-report cap survives shell respawns.
Each report checks pending TERM, reads and compares the actual complete blocked
signal mask, and checks pending TERM again. Every report has leading/trailing
newlines. This is scheduling deferral and explicit framing, **not UART line
atomicity**. One fork already in flight may still cross signal arrival.

The parser accepts one through three exact reports, rejects malformed/fourth
reports and reports after observed stopping/reset, and retains every raw byte.
Only complete validated readiness lines may be disregarded as pending output;
faults, nonce outputs and command statuses are not stripped or reconstructed.
The first exact report still requires a following fresh shell-ready/prompt.

The kernel, framebuffer ownership/mapping, `/bin/sh`, zsh, actual `/sbin/reboot`,
normal firmware, copy-phase watchdog policy and all other root files are
unchanged. The 180-second terminal service, 15-second watchdog, 120-second TX
budget/45-second reserve, 300-second host return bound and no-retry policy stay
unchanged. Nominal early return is engineering evidence, not unconditional
physical PSCI causality or permission to remove the watchdog.

## Exact candidate

- PID1: `build/rpi5/init-shutdown-late-framed-5roryvz5`, manifest
  `5c17c8e1e496a55b6f9e459e0e1482ea9a74176c1093ce331bef95540b62ec31`.
- Image: `build/rpi5/display-restart-late-framed-tquvyn12`, manifest
  `80fb3f47301a1d7be2ccc9834706f47feb635b98690e4c9404e383c196b77c2e`.
- Probe SHA: `fc36a84986b6bb49c8bd6659331257f64d7b52937285f6e0b2d77a637fb36dce`.
- Tag: `a52ab98358c3409cb560358cd3c79eca`.
- Saved report: `build/rpi5/restart-late-qualification-20261014/checker-report.json`,
  SHA `7fdf307bd644e2f27579250193c021117059255faefdd7e7778fc21d36bf1c16`.

The unframed `benslain`/`aoqc9rzu` prototypes and their sources remain preserved
and unused. Current and historical component report fields are explicitly
separated in the new checker.

## Main-only operator handoff

Only the actual completed `stage_restart_init_trial.restoration` schema is
accepted: current catalog444, original config/loader restored and normal
firmware unchanged. These commands are instructions, not performed here.

```sh
python3 tools/rpi5/stage_restart_late_trial.py prepare \
  --baseline build/rpi5/restart-init-restored-20261014 \
  --prior-seal-sha256 373c070c66e6b4efba6030b61d80b356ed86a3a4bfe06714820a8d1b6fb14273 \
  --prior-plan-sha256 0efb9d6b74c809663f4291df02743c0fedecf72be8d4535943ff2cc44e79f4e4 \
  --linux-boot-id 2a46da4b-72b7-4145-b5f3-d84a05d64b91 \
  --output build/rpi5/restart-late-prepared-20261014
```

After independent byte admission, use the unchanged `publish --execute`,
`launch`, `return`, explicit `restore --execute` and `replay` operations with
their actual seals/plans and new unused directories. The original `arm_once`
must recognize the actual `CAPTURE_ARMED RESTART_LATE` line before one SSH
reboot. Main alone controls these operations.

## Offline checks

```sh
RPI5_INIT_SHUTDOWN_LATE_FRAMED_PACKAGE="$PWD/build/rpi5/init-shutdown-late-framed-5roryvz5" \
RPI5_INIT_SHUTDOWN_LATE_FRAMED_MANIFEST_SHA256=5c17c8e1e496a55b6f9e459e0e1482ea9a74176c1093ce331bef95540b62ec31 \
python3 -m unittest tools.rpi5.tests.test_init_shutdown_late_framed -v

RPI5_RESTART_LATE_FRAMED_PACKAGE="$PWD/build/rpi5/display-restart-late-framed-tquvyn12" \
RPI5_RESTART_LATE_FRAMED_MANIFEST_SHA256=80fb3f47301a1d7be2ccc9834706f47feb635b98690e4c9404e383c196b77c2e \
python3 -m unittest tools.rpi5.tests.test_display_restart_late_framed -v

python3 -m unittest tools.rpi5.tests.test_restart_late_serial \
  tools.rpi5.tests.test_restart_late_transport \
  tools.rpi5.tests.test_restart_late_media -v
```

Native process/kernel effects and host recorder/SSH/device effects use explicit
doubles. Whole PID1 A76 TU/static link and exact loader/root materialization
are separate checks. None proves target shutdown, scanout, or PSCI execution.
