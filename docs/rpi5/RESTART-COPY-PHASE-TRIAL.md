# Restart loader copy-phase successor

This is a loader-only successor to the preserved failed diagnostic image. It
does not change the diagnostic kernel, root33, `/sbin/reboot`, container bytes,
materializer, framebuffer ownership, or any inherited loader object except
`loader-main.o`. Hardware execution is not established by this document.

The failed capture stopped after `PHYSICAL_COPY_BEGIN`, before XNU. The accepted
root32 trace's last serviced kernel hash to old first copy renewal was about
15.666 seconds; the root33 image added about 116 ms before materialization.
The root digest was logged but did not match the sole kernel hash-renewal
workload. This is source-and-timing evidence of a tight uncovered transition,
not a calibrated measurement of the hardware watchdog clock.

The new loader spends the same two copy renewals at verified plan/pre-copy and
materialized-equal/DSB/post-copy. It no longer renews after readback. All kernel
and root checks still precede the first renewal; full readback still precedes
transfer. A no-write final admission requires both phases, the same workload
and placement, the original 60-second outer deadline, and less than a nominal
15 seconds since phase2. The existing separate final transfer renewal remains.
Hash maximum128, copy maximum2, 60-second outer and 15-second countdown are
unchanged. Accepted readback-start to transfer-marker receipt time is
10.629805375 seconds, not a promise about the next boot.

The frozen candidate is `build/rpi5/display-restart-copy-sgf9_m1d`, manifest
`e01f4e177cbb89a0f9b0663a711683de4b7ea92551c8a10a3885b2d1b38b7aa2`.
Image SHA256 is `b1a5b55f05275b96b89224aa431681b73c94eac782f0268ca06b88de71a6444b`.
The retained checker report is `build/rpi5/restart-copy-qualification-20261014/checker-report.json`,
SHA256 `13aadf72a550868f1497b4ed0469d1f575a01e0846108beed02b40510cc8dd7f`.

The distinct controller accepts only a completed diagnostic restoration via
`stage_restart_diagnostic_trial.restoration`, including exact original config,
normal firmware and working loader. Current baseline is restored424, not414.
The receiver preserves the five-command and full-tail guards. Its exact ARMED
line contains `CAPTURE_ARMED`, tested with the original live-child `arm_once`
body. Failed/missing/duplicate/dead ARMED or ambiguous reboot cannot retry.

Main/operator-only preparation (no hardware action):

```sh
python3 -m tools.rpi5.stage_restart_copy_trial prepare \
  --baseline build/rpi5/restart-diagnostic-restored-20261014 \
  --prior-seal-sha256 b1b6c43f05c6d8a351eb337820bfe8aebcbeeffbf273e38e30d09aeed5dd4ed0 \
  --prior-plan-sha256 ff5928dc9430564f8a219152d9894517b569612cd9926170e3e9968953f4da43 \
  --linux-boot-id 6b0cf970-cefc-4a08-8c79-41e4bff6bf05 \
  --output build/rpi5/restart-copy-prepared-20261014
```

Use the returned exact prepared pin for `publish`; then the exact installed
checkpoint/plan pins for `launch`, `return`, `restore`, and `replay`. The same
module's `--help` exposes those operations. Publication does not reboot. Launch
owns one armed receiver and one freshly boot/root-verified SSH reboot. Never
reuse an output/capture path or retry an unknown operation.

Even an ordered real syscall→PRE_SMC→fresh Linux return remains engineering
evidence with `physical_psci_causality_proven=false` and
`unconditional_not_watchdog_proven=false`. The diagnostic nominal timing check
does not authorize removing the kernel's unchanged 180-second service plus
15-second hardware fallback. Poweroff remains unsupported.
