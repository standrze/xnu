# Gate 3 BCM2712 cluster and sleep-path audit

`HAS_CLUSTER=1` in `BCM2712.h` is required for the reset/per-CPU lookup to
retain MPIDR Aff1. It does **not** mean that the four Cortex-A76 cores are
four independent cache or scheduler clusters. The BCM2712 case in
`osfmk/arm64/machine_routines.c` maps each physical Aff1 to logical cluster
zero, and publishes core IDs within that group. This distinction must survive
future topology edits.

`NO_CPU_OVRD=1` avoids Apple's `CPU_OVRD` register operations. The remaining
Apple-only sleep instructions in `arm64_prepare_for_sleep` (including
`ACNTHV_CTL_EL2` and `S3_5_C15_C1_1`) are inside
`APPLE_ARM64_ARCH_FAMILY` in `machine_routines_asm.s`; BCM2712 uses the
non-Apple `wfi` loop instead. Likewise, `cpu_sleep()` uses the non-
`USE_APPLEARMSMP` `PE_cpu_machine_quiesce()` path, not Apple's CPU-down path.

This is a reachability audit, **not** a suspend/resume validation. The generic
`ml_arm_sleep()` path still calls the non-Apple `arm64_prepare_for_sleep(true)`
loop. Neither system sleep nor CPU hotplug/resume has been implemented or
tested on the Pi; no Gate 3 result should imply that those features work.
Before enabling either, give BCM2712 explicit platform power-state handling
and an on-board resume test. The current Gate 3 soak exercises timer/IPI/SMP
operation while the machine remains powered, not suspend-to-RAM.
