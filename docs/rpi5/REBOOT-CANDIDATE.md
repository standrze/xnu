# Explicit user-controlled restart: offline candidate

The missing implementation is the platform reset endpoint, not a missing XNU
reboot syscall. This candidate is **default off, not linked into an accepted
kernel, not packaged, and not executed on the Pi**. Existing shutdown, watchdog,
recorders, boot arguments, firmware and images are unchanged.

## Existing original Apple path

`libsyscall/wrappers/reboot.c` forwards `reboot(howto)` to `__reboot(howto, NULL)`.
`bsd/kern/syscalls.master` assigns syscall 55. `bsd/kern/kern_xxx.c` retains the
root check and configured MAC authorization; its existing DEVELOPMENT panic
exception does not authorize an ordinary reboot. The path continues through
`reboot_kernel` in `kern_shutdown.c`, `host_reboot`, `halt_all_cpus`,
`PEHaltRestart` and `IOPlatformExpert::haltRestart`.

The original shutdown path handles process shutdown, sync/unmount, network and
IOKit power notifications. None are bypassed by this change. The terminal gap
is `PE_halt_restart == NULL`: the platform method returns -1, then the original
`halt_all_cpus` does not return to userland. No Pi-specific callback currently
fills this gap.

Apple's [original reboot utility](https://github.com/apple-oss-distributions/system_cmds/blob/main/reboot/reboot.c)
has a genuine `-q` branch that directly calls `reboot(howto)`; its default Apple
path uses `reboot3`/launchd services. `-q` does not itself set `RB_QUICK` in the
kernel flags. The complete utility also needs its real kext/bootstrap/logging
dependencies and is **not built or installed by this slice**. The original
public libsyscall wrapper is exercised with a native trap double, not replaced
by a fake syscall. A future CLI must use that real syscall path and report an
error if it returns; merely printing “reboot” is not an implementation.

## Exact existing firmware support

The normal accepted TF-A binary is
`413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46`,
from pinned Raspberry Pi TF-A revision
`332b62e0443b004287d2cfc032a70bba6fb86f35`.
`plat/rpi/rpi5/platform.mk` genuinely includes the common `rpi3_pm.c`; the name
does not imply use of a Pi 3 register map. The Pi 5 `rpi_hw.h` supplies PM base
`0x107d200000`.

The offline proof compares actual ELF load bytes to that binary, checks the
linked PSCI dispatch branch, reset callback table entry and target, and the
decoded reset MMIO sequence. `PSCI_SYSTEM_RESET` (`0x84000009`) invokes the
platform's short watchdog reset. The kernel candidate only issues SMC; it does
not itself access PM registers or synthesize a reset. The firmware publishes
PSCI 1.1 and its feature table includes SYSTEM_RESET when that callback exists.

SYSTEM_OFF is different: the same source explicitly performs a watchdog reset
after setting a HALT hint in RSTS. Whether the actual Pi 5 EEPROM bootloader
honors that hint and which rails remain powered is unproven. This candidate
does **not** call SYSTEM_OFF or advertise working `halt`/poweroff.

## Candidate scope and admission

New source only:

- `tools/rpi5/psci_restart_candidate_profile.py`: exact original platform-TU
  derivation, only replacing the no-callback fallback; original callbacks keep
  priority.
- `iokit/Kernel/rpi5_psci_restart_candidate.inc`: compiled only with
  `RPI5_PSCI_RESTART_CANDIDATE=1`, BCM2712 DEVELOPMENT and retained-FDT support.
  Runtime opt-in additionally requires `rpi5_psci_restart=1` and exactly
  `kPERestartCPU`. Panic, halt, UPS and unknown modes are not added.
- `loader/rpi5/psci_restart_candidate.{h,c}`: validates a bounded immutable
  retained same-boot Pi 5 firmware tree and its SMC PSCI binding, requires EL1,
  obtains an atomic one-shot gate, checks exact audited PSCI 1.1 and a fresh
  SYSTEM_RESET feature result, then attempts one reset. Any returned reset is
  failure, including a returned zero. Failed admitted attempts cannot retry.
- `osfmk/arm64/rpi5_psci_restart_candidate.S`: fixed VERSION/FEATURES/RESET
  leaves, cleared arguments and barriers. No generic SMC selector, no MMIO,
  no interrupt-mask mutation, no alternate reset path.

The FDT API's immutable same-boot provenance is supplied by the existing
retained handoff; the parser does not authenticate firmware or turn an arbitrary
tree into hardware authority. The target code is kernel-only; authorization
remains in Apple's original userland syscall path. There is no new userland
physical-access interface.

## Software evidence and remaining work

`python3 -m unittest tools.rpi5.tests.test_psci_restart_candidate -v` executes
the actual helper and existing FDT parser under ASan/UBSan, rejected/truncated
bindings, version/feature errors, returned-success rejection, reentry and 16
concurrent callers. It also executes the exact derived original platform method
with host-only endpoints and the whole original Apple libsyscall wrapper with
a trap double. Four groups passed; these are not firmware execution.

`python3 -m tools.rpi5.build_psci_restart_candidate` creates a distinct software
artifact. It compiles the actual original/default-off/opt-in platform TUs using
the real kernel command/header closure, verifies the disabled dispatch's exact
function bytes/relocations, and compiles the policy and fixed SMC leaves for
A76. Default-off has no candidate provider reference; the new leaf has no
undefined symbols, and the policy's imports are only the real FDT functions and
its four fixed architecture leaves. No compiler atomic-runtime helper appears.

The completed software candidate is `build/rpi5/psci-restart-candidate-pdjka9li`,
manifest `5339d6c36ae832b58fb285968630b1af44f4e1b0662a6c021d1c5b896ce67fb8`.
Its source/header/tool/generated pins and actual command outputs are retained.
It is **not** a full linked kernel or a bootable image.
Earlier `dq2su4r0` is preliminary: its native test manually numbered a platform
enum. The final test extracts the real Apple enum. Two intervening test-source
generation failures and their logs are also retained; production code did not
change during that test correction.

Next steps require a separately reviewed kernel composition and real original
reboot utility/runtime closure, followed by one authorized marker-guarded
restart and independent new Linux boot evidence. The existing bounded watchdog
must remain until that path is proven. A successful compile or a feature query
cannot prove completion of shutdown or physical reset, nor establish which
boot medium the firmware will select afterward.
