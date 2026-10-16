# Opt-in user-controlled restart diagnostic

This is a distinct software-qualified successor to the immutable full restart
composition. It has not been run on the Pi. It preserves the same HDMI/UART
mirror, root33 with `/sbin/reboot`, original Apple reboot wrapper/syscall55,
normal TF-A firmware, original fixed PSCI SYSTEM_RESET leaf and180-second
terminal service deadline plus15-second hardware fallback.

The new full image is `build/rpi5/display-restart-diagnostic-gb38kpad`:

- Manifest: `fb09729396cf9bbec7ced1b50b7846c8fa23e4b9b03c51e2dd0304725257f5ae`.
- Image: `752582b53fc340d0e01ec85b3054d4ddb8cfa2219cfb7139a266602629c95872`,20,184,896bytes.
- Independent byte-check report: `build/rpi5/restart-diagnostic-qualification-20261014/checker-report.json`, SHA`94bc691763caa37240edc89a742f597b0afd3bfc99d1767416fa34fc923a670f`.

Only four kernel owners change relative to the preceding restart image:
platform fallback, policy, existing UART owner and existing watchdog owner.
The same linked four display owners, root33 bytes, genuine CLI and fixed SMC
leaves remain unchanged. The loader changes only its unique tag and payload.
The previous uninstrumented and failed/intermediate build outputs are retained.

## Evidence and limits

After fresh tagged loader/kernel/root33/MIRROR/watchdog/restart eligibility
markers and a later recovery prompt, the receiver executes four bounded real
zsh5.9 exchanges. Only then it sends one nonce-bound zsh command invoking
`/sbin/reboot`. Echo alone is insufficient. The actual reboot runtime startup
must follow the executed nonce, then the checked pre-SMC marker, fresh BOOTSYS,
BOOTLOADER and NVMe. A separate witness must identify a new Linux boot on the
exact SSD/card before explicit restoration.

The diagnostic uses the existing mapped PL011 owner without console/video
locks. The PM snapshot uses one nonblocking acquisition of the existing
service gate, reads two route/count samples, and neither reloads the timer nor
changes its deadline. Every returned SMC remains failure. Poweroff is absent.
The policy excludes panic enum modes, not every possible panic context.

The watchdog encoding has nominal65536ticks/second, but no qualified maximum
physical clock-rate bound. Therefore RATE_BOUND remains0. The host comparison
starts at the final command's first transmitted byte and ends when the full
BOOTSYS marker arrives; this conservative interval must be shorter than the
rounded-down nominal remaining count minus one second. It is engineering
evidence only. `physical_psci_causality_proven` and
`unconditional_not_watchdog_proven` remain false, including on a passing
functional trial. This does not authorize watchdog removal.

The host capture allowance is300seconds; TX remains bounded to120seconds
from admission with a45-second command reserve. Full captured-tail faults,
returned calls, missing markers, contradictory output and late nominal return
remain failed evidence. Failed captures can still be safely restored after an
independent new Linux witness; restoration never upgrades the runtime result.

## Controller

`tools/rpi5/stage_restart_diagnostic_trial.py` accepts only the completed typed
`phy_reset_trial_v2.completed_restore` baseline. The current offline test binds
the414-entry restoration `pcie-phy-reset-restored-20261014`. Preparation and
all physical operations remain with the main hardware owner. Publication is
the inherited source-pinned config32/loader pair algorithm: normal firmware is
protected, both files are archived and new copies checked before rename,
unknown outcomes are recorded without retry or implicit rollback. The launch
helper arms and validates the actual modem-gated recorder before one verified
Linux reboot; it does not require a separate manual recorder invocation.

Offline tests:

```sh
RPI5_RESTART_DIAGNOSTIC_PACKAGE=build/rpi5/display-restart-diagnostic-gb38kpad \
python3 -m unittest tools.rpi5.tests.test_display_restart_diagnostic \
 tools.rpi5.tests.test_psci_restart_diagnostic \
 tools.rpi5.tests.test_restart_diagnostic_serial -v
python3 -m unittest tools.rpi5.tests.test_restart_diagnostic_transport \
 tools.rpi5.tests.test_restart_diagnostic_media -v
```

Native policy/accessor doubles do not become target providers. The media tests
execute the exact generated remote program only on regular files with explicit
device/mount doubles. No serial device, SSH connection, target Mach-O or real
restart is executed by these tests.
