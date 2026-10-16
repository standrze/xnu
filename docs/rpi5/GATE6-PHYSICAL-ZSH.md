# Physical Pi zsh checkpoint — 2026-10-12 16:40 UTC

Historical first trial: its original failure remains preserved. A **separate
corrected-image trial at 19:03 UTC** now passes that script and interactive
checks; see [new physical result/current baseline](GATE6-METADATA-PHYSICAL.md).

Interactive Apple-source zsh 5.9 has executed on the physical Pi 5: a fixed
prompt, computed version/array/arithmetic output, external executable, returned
prompts and exit to the live recovery shell are independently audited. The
original script-file test failed and remains failed. This is not complete
Gate 6, a persistent distribution, Ethernet, SSH, or Gate 4 durability proof.

## Package, installation and boot

The distinct package `build/rpi5/bl33-probe-_qoqmu9u` was successfully built
before the interruption and reused, not rebuilt. Raw image: 18,008,768 bytes,
SHA256 `b3db210c0a880688bfda783e306fb6ad3473431d9a9cc68e25035d3c8fc32fd0`.
Loader manifest SHA256:
`4ffc91ce72b858787f9d9cdceb8e04d48ebadb85142d44b9f88b2ee609ca9c46`.
It embeds the unchanged proven kernel `d133f3a21ff9d3397aed7dfdd04210fe79061d8919d5046010dfa1919980a10f`
and the 24-node RAM root `ddbdffe24f4441985cadf5aa1556d2b409e0c8a39d6d86dd5352d49814712e08`.
All 14 original init/recovery/utility/data files and modes are preserved.

`check_zsh_trial_package.py` passed 27 checks for hashes, complete root
reconstruction, ELF/raw correspondence, source/output stability, profile and
the existing conservative 10,000-byte C-frame stack bound. Storage trials,
PCIe MMIO/config/reset observers and DMA are absent. This is diagnostic package
preflight, not universal ISA/ABI proof or whole-program stack qualification.

SSD Linux return was freshly verified as boot
`67033e75-2d50-40fa-a871-1a3eb05ff10a`, root `/dev/nvme0n1p2`, ext4 UUID
`04570742-280b-43cb-9564-73d454243b1c`, hostname `kamidana`.
`stage_zsh_trial.py` verified the exact authorized SD identity/layout and all
24 pinned historical NVMe backups, made complete fresh MBR/FAT/HFS backups,
preserved the topology image separately on SSD and SD, installed only the
new FAT boot file, and verified/unmounted it. No HFS mount/write, firmware/
configuration/EEPROM edit, repair, automatic retry or rollback occurred.
The regular-file rename is not claimed power-loss atomic on FAT.

Installation: `build/rpi5/zsh-trial-installed-20261012`, SSD run
`/home/sandrzej/xnu-gate6-zsh-ocpy9_w7`; result SHA256
`ef3bfb9739f941199d483ae0299d055e0536d08f4d27532f43a1583b60b59358`.
Preserved topology image: SSD `pcie-topology-passed.bin`, SD
`probe.pcie-topology-passed-20261012.bin`, SHA256
`038c2b9bd0b55fa35496632fad7a96e8ffff1f2a7b64006e5709757bd895b895`.
W3 and every prior backup remain preserved. Current full FAT SHA256 is
`1fb357e8483a43c92e92d3d0cb4a50aada0116bbb7a9267c35e983b04323277a`;
protected MBR/HFS hashes are unchanged. Do not rerun old installers against
this new current image/FAT state or replace their hashes simply to force acceptance.

The exclusive Debug Probe identity `E66480454F719939` and absence of another
serial owner were checked. `serial_zsh_trial.py` armed at 16:29:56 UTC before
the guarded one-shot software SD reboot at 16:31:07 UTC. The existing
`vcmailbox 0x0003808b 4 4 0xf61` boot request was used; EEPROM remained
`BOOT_ORDER=0xf461`. The recorder required the exact firmware image extent,
fresh ordered loader/profile/transfer markers, distinct 24-node root and
recovery prompt before sending a fresh nonce or any zsh command.

## Original script failure and same-boot diagnosis

The original trial reached the new root/recovery shell, proved fresh nonce
input, launched zsh, and observed ENTRY/TSD/ENTROPY/MAIN. It then reported:

```text
zsh: can't open input file: /etc/zsh-smoke.zsh
```

The guard stopped with 49 TX bytes and no script acceptance. Its failed state
and raw transcript were not replaced:
`mac-zsh-trial-20261012`, raw SHA256
`193ea9bf64dcf09bda4325d4b2d8b3e9cd47587c31af8c5b262b77c27daca546`.
No unchanged-image reboot or new soak followed.

A separate explicitly guarded same-boot read-only diagnosis required the
recent original failure/hash/image/device, then a new live recovery nonce.
Its first attempt stopped because the host expected `terminfo`, while the
real `ls` correctly returned `terminfo/`. Preserve that failed host expectation
in `mac-zsh-script-diagnostic-20261012`; it is not a Pi failure.
The corrected `mac-zsh-script-diagnostic-20261012-v2` completed: the recovery
shell listed and read the complete exact script, and zsh command-string
execution reported version 5.9 and these condition statuses:

```text
DIAG_EXISTS:0
DIAG_REGULAR:1
DIAG_READABLE:0
```

That is a real file-type/metadata inconsistency, **not yet a proven root cause**
of the script-open error. Source `setupshin` first uses access/stat/not-directory
checks and then `movefd(open(...))`; `movefd` uses F_DUPFD. The next diagnosis
needs raw stat/fstat bytes and open/descriptor-duplication results before
choosing a kernel, ABI adapter or zsh change. Do not fabricate a regular-file
answer, relax the acceptance guard, or modify the frozen VM capsule.
Corrected diagnostic raw SHA256:
`e9fc9b9e9ce4c699d39defc8d1f25cab213de024ee0393d62b98bc3f009da1c5`.

## Separate interactive result

On the same boot, another bounded diagnosis used a new recovery nonce, a
noninteractive zsh launcher exporting PS1/TERMINFO, and exec into interactive
zsh. Both startup traces and the fixed `pi-zsh# ` prompt were required before
commands. Actual complete output lines were:

```text
PI_ZSH:5.9
PI_BUILTINS:xnu:42
PI_EXEC_D398a412ebbd361cd
RECOVERED_D398a412ebbd361cd
```

The first is computed from `$ZSH_VERSION`; the second from a zsh array and
`6*7`; the third comes from external `/bin/echo` with a fresh nonce. Each
interactive result had a subsequent zsh prompt. After `exit`, the recovery
shell answered another fresh nonce and returned its own prompt. Echoed input
is not accepted as any of those output lines.

Evidence: `build/rpi5/mac-zsh-interactive-diagnostic-20261012`, 16:39:34–16:39:43
UTC, 273 TX bytes, raw SHA256
`6c22c22ac1a15267cafad3f2f60b8708e6cb1ddf713426fdc6698c841ddca02f`.
The offline `check_zsh_interactive_diagnostic.py` rechecks raw/state hashes,
exact outputs/order/prompts, both startup traces, fresh nonce, preservation of
the original failed trial, package/install identity and armed/reboot/same-boot
chronology. Validation SHA256:
`a53b259eaf546afa8d6eed40303ac1aa2666871311644b8811b4db6d83a1ac45`.
It explicitly leaves script-file, full Gate 6, networking and durability false.

All 42 selected staging/preservation/serial/inventory/root/diagnostic/audit host
tests pass. They are separate from the physical results above. No shared kernel
or VM source/capsule was edited or rebuilt for this trial. The Pi was last
proven in its recovery shell; all recorder handles finished and released serial.
The existing one-hour development watchdog still applies, without a guaranteed
SSD fallback. Do not assume current Linux SSH or repeat a boot for these results.
