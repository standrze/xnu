# Linked restart candidate (software qualification only)

This distinct candidate extends the accepted full-height HDMI/zsh image. It
does not change or stage that accepted image. The old 180-second terminal
watchdog deadline and 15-second hardware countdown remain unchanged.

`/sbin/reboot` is a small, project-owned front end, not Apple's complete
launchd-integrated reboot utility. No arguments calls the unchanged Apple
`reboot(RB_AUTOBOOT)` wrapper and the original generated syscall 55 stub.
`--help` is the only non-destructive option; other options exit 64. Every
return from the reboot syscall is reported as failure, including an unexpected
zero. It does not expose QUICK, NOSYNC, HALT or PANIC flags, or imitate success.

The selected genuine static pthread startup establishes the existing real
libkernel callbacks, main-thread/TSD and errno providers before the command.
Apple's kernel suser/MAC authorization, process shutdown, sync/unmount and
platform shutdown dispatch are untouched. The new platform fallback is enabled
only by its compile macro and the explicit `rpi5_psci_restart=1` boot argument;
an existing platform callback still takes precedence.

The fallback requires the retained same-boot Pi 5 FDT and SMC PSCI binding,
EL1, the exact audited PSCI 1.1 version and SYSTEM_RESET feature. It makes one
fixed SYSTEM_RESET request, never retries, and never treats a returned firmware
call as successful reset. Poweroff is unsupported. Panic *enum modes* are
excluded, but Apple can request ordinary restart from a panic context; this
candidate does not claim all panic contexts are excluded.

The full kernel retains every accepted HDMI/root/watchdog object except the
single IOPlatformExpert replacement, and adds the reviewed policy/SMC objects
with the actual kernel compiler flags. The loader retains all accepted allocation,
mapping, FDT, CPU and stack paths; only its unique marker/explicit boot argument
and embedded payload differ. The root preserves every previous file byte and
mode, adding `/sbin/reboot` for 33 nodes. The legacy socketprobe identity catalog
is intentionally unchanged and must not be used to assert complete root33 identity.

Qualification separates actual native loader/relocation tests and host syscall
doubles from target execution. A full static link, exact wrapper/trap/SMC
instruction audit and source/header closure do not prove physical restart.
Neither this image nor its target utility has been executed by the builder or
tests. A future explicitly authorized trial must independently distinguish PSCI
restart from watchdog recovery before removing any watchdog fallback.
