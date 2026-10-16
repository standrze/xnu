# Static serial shell — repeat cold-boot milestone passed

Updated 2026-10-11. This follows the physically successful
[process](PROCESS-TRIAL.md) and [RAM-root](RAMROOT-TRIAL.md) dependencies.
It is an actual bounded shell implementation, not the earlier four-command
diagnostic interpreter. **All twelve shell checks passed on the physical Pi**
on 2026-10-11, including two independently recorded true cold boots of the
same image. The repeatable serial-shell milestone is achieved; this is not
a complete Darwin distribution or formal Gate 3 qualification.

## Physical result

SSH returned at 19:37 UTC. The Pi was verified on `/dev/nvme0n1p2` Linux with
the exact XNU_PROBE SD identity. The guarded staging script completed at
19:38:16 UTC, preserving the successful RAM-root image on SD and NVMe. The
candidate hash read back correctly and the SD was remounted read-only.
Firmware, DTB, boot configuration and EEPROM settings were unchanged.

The recorder was armed before the authorized software reboot at 19:38:40 UTC.
Firmware explicitly selected SD, and XNU mounted 19 nodes / 589824 bytes.
The repeated shell-ready marker appeared; all twelve checks passed at
19:39:40 UTC with 235 transmitted bytes. This includes external executable
launch, quoted arguments, file/directory IO, pipes, exit status, cwd and input
redirection, readonly failure recovery, nested scripts and a live prompt after
blocking sleep. The console is now a usable bounded shell, not the former
four-command diagnostic interpreter.

Evidence: `build/rpi5/mac-shell-trial-20261011/{serial.bin,state.json}`.
Raw serial SHA-256:
`f01903ca37c5e31fc14883a739f42d8ba9c0488d0a12be83f58929393d9a78fc`.
The capture contains one loader start, intact generic keyboard-start and
watchdog-kick markers, and no kernel panic. One-time init/process banners
were interleaved by concurrent UART writers; those text fragments are not
treated as independent proof. The actual shell command results prove execution.
`validation.json`, `staging.log` and `reboot.log` in the package preserve
the outcome, boot configuration and source/build identities.

This was **one software reboot**, not a cold boot or formal Gate 3 exit.
The first true cold start passed all twelve checks at 20:00:21 UTC, with
235 transmitted bytes. The user confirmed power cycling, and firmware
recorded `power-on-reset 1`, one boot/loader start and SD boot. Evidence:
`build/rpi5/mac-shell-cold1-20261011/{serial.bin,state.json}`; serial SHA-256
`c60c8cf768b68802b1d1db87a760f886434426d1426d1ac92ff2c2f6c1027e93`.
The recorder had waited for the user; its start time is not the boot time.
There was no panic or intervening reset during acceptance.

The second true cold start passed all twelve checks at 20:15:24 UTC, again
with 235 transmitted bytes, user confirmation, firmware `power-on-reset 1`,
one boot/loader start, SD boot, the same RAM-root identity and no panic or
intervening reset. Evidence:
`build/rpi5/mac-shell-cold2-20261011/{serial.bin,state.json}`; serial SHA-256
`698fbaf107b2b403051a25a70324fe9547b8a56d6f6eb0d804da2a4ec4cbf468`.
Its recorder also waited for the user; recorder uptime is not a stability
soak or the boot duration. Pre-boot watchdog messages in both cold captures
belong to the previous boot and are not extra successful boot attempts.

This establishes two separate cold boots to an interactive userspace shell
on the physical 8-GB Pi, in addition to the initial software-boot trial.
No image change, SD rewrite, kernel rebuild, additional restart or soak was
needed between them. Each capture's scope string describes that single
run; `validation.json` and `completion-audit.json` record the combined
repeatability evidence. Formal Gate 3 remains open.

Both recorders have finished and released the serial port. The Pi is left
at the shell prompt on the second cold boot; no background test or soak is
running. The next step is using the shell, not another qualification run.

## Use the shell from the Mac

The verified Debug Probe callout is `/dev/cu.usbmodem102`, at 115200 8N1.
In Terminal:

```sh
screen /dev/cu.usbmodem102 115200
```

Press Enter to display `xnu:/# `, then try `help`, `ls /bin`, `cat /etc/motd`,
`echo alpha beta | wc`, or `sh /etc/demo.sh`. To disconnect screen and release
the serial port, press Ctrl-A, then backslash, and confirm with `y`.
Do not run two serial readers simultaneously. Opening this terminal does
not require Linux, SSH, removing the SD or another reboot. The development
watchdog window and read-only-root limitations below still apply.

## Implementation and limits

`tools/rpi5/user/` provides a freestanding static arm64 Mach-O, with no libc,
dyld, imported symbols or code-signature dependency. PID 1 opens the console,
forks and execs `/bin/sh`, reaps children and respawns the shell after exit.
One multicall executable is copied into eleven disjoint executable file
extents; utilities dispatch by `argv[0]`, with real `fork`/`execve`/`wait4`.

The shell supports arguments, single/double quotes, backslash escapes,
pipelines, `;`, `&&`, `||`, `<`, `>`, `>>`, `sh -c`, and script files. Builtins:
`cd`, `pwd`, `help`, `status`, `exit`. Programs: `echo`, `cat`, `ls`, `wc`,
`sleep`, `uname`, `true`, `false`, `hexdump`, and `sh` itself. `uname` obtains
kernel values through `sysctl`, not hard-coded identity strings.

This is not a POSIX-complete shell. Only `$?` and `$PWD` expand, once per
input line. There is no globbing, command substitution, shell-variable
assignment, background work, job control or history. `exit` accepts no
arguments. Line capacity is 1023 bytes, commands per line 16, arguments per
command 32, and parsed string storage 4096 bytes. Logical paths are maintained
in userspace and passed to nested shells through `PWD`; there are no symlinks
in this root. The canonical TTY provides input echo and basic erase/kill.
Foreground signal/job-control behavior remains untested on the board.

The root is read-only. Output redirection to ordinary files must fail;
`/dev/null` and `/dev/console` remain available. There is no SSH, network,
SD filesystem driver, reboot command or claim of persistent storage.
The reused kernel's terminal watchdog service window is bounded to one hour;
this candidate is not an indefinitely unattended distribution and does not
guarantee automatic SSD fallback after watchdog expiry.

## Artifacts and provenance

Package: `build/rpi5/shell-userland-20261011/`.

| Artifact | SHA-256 |
| --- | --- |
| `probe.bin` | `bf01b0eedcce48249a7358772f74613d0b0453217f35576369945de25d50374f` |
| `userland` | `9e373b2ff45145c0172c48ae83a9b2a23e8446ed2bd6afa89f9aa811b320b161` |
| `ramdisk.bin` | `d32891113ad2ecdb1637bfdfd58991574026877cfb827a4bd0cd229980541f55` |
| Reused RAM-root kernel | `d133f3a21ff9d3397aed7dfdd04210fe79061d8919d5046010dfa1919980a10f` |
| Preserved working RAM-root probe | `e1548c9e083fa7f4c78f19834075cab125683f76d3d9ac56ae3eb95705cdaa4d` |

The archive contains 19 nodes and is 589824 bytes. Source base is
`ac9718fb1af618d5ce8678d0dc6e8a58f252216f` plus the dirty downstream port.
`userland-manifest.json` records compiler/linker versions, commands and all
userland source hashes. Kernel provenance remains the prior successful build,
not a new kernel compile: `kernel-build-manifest.json`,
`kernel-tracked-port.patch`, and `kernel-untracked-port.tar.gz` preserve it.
`shell-source.tar.gz` preserves this shell, builders, checks and documentation.
`loader-build-manifest.json` is the unmodified loader manifest;
`manifest.json` adds the copied package image's path/hash for package checking.
Do not apply source snapshots over the dirty checkout.

Final build commands:

```sh
python3 tools/rpi5/build_userland.py --output-dir build/rpi5/userland-shell-appendfix-20261011
python3 tools/rpi5/build_probe.py --load-address 0x9000000 --kernel build/rpi5/shell-ramroot-20261011/kernel.development.bcm2712 --init build/rpi5/userland-shell-appendfix-20261011/ramdisk.bin --transfer --serial-terminal --gate3-cpu-on-all
```

The loader output is `build/rpi5/bl33-probe-w1tx91oz/`. The first local
candidate was superseded before hardware testing after a parser review found
that a later input redirect incorrectly cleared an earlier append flag.
That concrete fix, not an unchanged-image rerun, prompted the second build.
No kernel rebuild or soak was performed; the one hardware software reboot
and its result are recorded above.

## Validation already completed

Fourteen focused host tests passed:

```sh
python3 -m unittest tools.rpi5.tests.test_shell tools.rpi5.tests.test_serial_shell_trial tools.rpi5.tests.test_serial_terminal_package -v
```

Seven test native C shell/parser/utility logic with ASan/UBSan and a POSIX
syscall adapter, including real host fork/exec/pipe/wait, scripts, directory
changes, descriptor restoration and 20000 deterministic malformed parser
inputs. Four test mocked serial transport, including zero transmission to
the old diagnostic image and rejecting input echo as output proof. Three
retain the existing package-identity regression coverage. These tests are
**neither XNU emulation nor Pi hardware validation**. The final guard-only
change also passed its four transport tests.

All fourteen checks in `preflight.json` pass, including original Gate 3
baseline hash, static executable validation, full archive embedding, distinct
utility extents, intended boot arguments and absence of qualification/soak
flags. `sh -n tools/rpi5/stage_shell_trial.sh` also passed. The candidate
was subsequently staged and passed the physical trial described above.

## Recorded software-boot procedure (completed)

Do not repeat this staging procedure on the current SD: the expected old
image has already been replaced, and the guards intentionally refuse it.
The two cold-boot checks are also complete. This section preserves the
original procedure for reproducibility, not instructions to repeat it now.

The Mac sees Debug Probe `E66480454F719939` at `/dev/cu.usbmodem102`; no
competing owner was present before arming. Pi SSH to `192.168.4.23` initially
timed out while packaging; that did not identify its OS. Access returned on
the user's next continuation, allowing the entire staging and trial to run
remotely. XNU has no SSH, so SSH absence after this boot is expected, not
an instruction to keep retrying or to request unnecessary Linux recovery.

1. Verify fresh SSH, hostname `kamidana`, root `/dev/nvme0n1p2`, and SD
   `/dev/mmcblk0p1`, label XNU_PROBE, UUID `4FA7-3725`, PARTUUID `5ae1f07e-01`.
   If Linux remains unreachable, the single required physical recovery is:
   power off, remove SD, boot SSD Linux, then reinsert SD while Linux is up.
   Do not reboot with the unchanged old XNU SD merely to retry SSH.
2. Recheck the package, copy and stage only after verifying Linux:

```sh
python3 tools/rpi5/check_serial_terminal_package.py build/rpi5/shell-userland-20261011 --kernel build/rpi5/shell-userland-20261011/kernel.development.bcm2712 --init build/rpi5/shell-userland-20261011/ramdisk.bin --gate3-baseline build/rpi5/bl33-probe-ci45m9zs/probe.bin --shell-trial
scp build/rpi5/shell-userland-20261011/probe.bin sandrzej@192.168.4.23:/home/sandrzej/xnu-shell-candidate-20261011.bin
ssh sandrzej@192.168.4.23 'sudo -n sh -s -- bf01b0eedcce48249a7358772f74613d0b0453217f35576369945de25d50374f' < build/rpi5/shell-userland-20261011/stage-on-pi.sh > build/rpi5/shell-userland-20261011/staging.log
```

   The staging script refuses any other root/partition identity, unexpected
   current image, firmware/config hash, or missing prior backup. It preserves
   the working RAM-root probe on both NVMe and SD, verifies a temporary copy,
   then replaces `probe.bin` and remounts read-only. No firmware/config edit.
3. Recheck Probe USB identity and port ownership. Start the recorder on the
   Mac **before** rebooting. Choose a new capture directory for every boot:

```sh
caffeinate -i python3 tools/rpi5/serial_shell_trial.py /dev/cu.usbmodem102 build/rpi5/mac-shell-trial-20261011 --boot-wait-seconds 3600
```

   Wait for `SHELL_TRIAL_ARMED`. It sends nothing until a fresh loader marker
   and the distinct repeated shell-ready marker. One-time generic keyboard,
   init or mount messages can be torn by concurrent UART writers; actual
   command responses, not banner presence, must prove usable userspace.
4. Recheck Linux root and staged `probe.bin` hash. Then record UTC time,
   issue `sudo -n vcmailbox 0x0003808b 4 4 0xf61`, `sync`, and
   `sudo -n reboot` over SSH. This is the existing one-shot SD boot override,
   not an EEPROM change. Save output as `reboot.log` in the package.
5. Require the new `state.json` status `passed`, all twelve checks, raw
   `serial.bin` and its hash. Inspect the full boot for firmware
   `Boot mode: SD (01)`, `RAMROOT:MOUNT NODES=19 BYTES=589824`, the init/shell
   process evidence where intact, and no intervening reboot/panic. The trial
   proves fresh nonce echo, quoting, file/directory IO, a two-process pipe,
   exact exit status, conditional recovery, cwd, input redirection, readonly
   failure, nested scripts, timed blocking and recovered shell prompt.

The recorder sends at 25 ms per byte and stops at the first actionable
failure. It never types into the existing diagnostic image. No soak or
automatic repeat of a failed command. Preserve failure evidence and fix
that failure before another attempt. A passed software-boot trial still
requires separate recorded cold boots to meet the user's goal. Those two
boots are now recorded above; no formal Gate 3 qualification is claimed.
