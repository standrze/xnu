# Darwin VM bootstrap userland

**2026-10-12 update:** the opt-in `--mode zsh` root now boots real source-built
Apple zsh 5.9 in the XNU VM. See [the completed milestone and launch](ZSH-TRIAL.md).
The original project bootstrap shell described below remains recovery tooling.

This is an isolated snapshot of the project's source-built Pi bootstrap
runtime, parser, shell and multicall utilities, adapted for the VM. The original
`tools/rpi5/user/` files are not modified. `source-provenance.json` records their
initial hashes. This small shell is not zsh, Apple `/bin/sh`, Apple launchd,
libSystem or a complete Darwin distribution.

Build on a Mac with Xcode command-line tools:

```sh
python3 experiments/darwin-container/userland/build.py --output-dir experiments/darwin-container/userland/build/trial-1
python3 -m unittest discover -s experiments/darwin-container/userland/tests -v
```

The output path must be new. The helper compiles only the local C/assembly
sources, statically links one arm64 Mach-O and packages it at `/sbin/launchd`,
`/sbin/init`, `/bin/sh`, `/bin/echo`, `/bin/uname`, `/bin/cat` and the other paths
listed in the manifest. No existing macOS executables or runtime libraries are
copied. The SDK/compiler provide headers and the toolchain only. UUID generation
is disabled to permit byte-identical builds with the same inputs/toolchain.

`ramdisk.bin` retains the existing `RPI5RFS1` format and `/sbin/launchd` at byte
zero. This is deliberate format compatibility with the shared mockfs provider,
not a claim that the VM is Pi hardware. The manifest records all local source
hashes, compiler/linker versions, commands, ABI source hashes and image hashes.

## Guest requirements

- Development arm64 XNU with the VZGENERIC platform, static Mach-O execution,
  working BSD fork/exec/wait/pipe/sysctl, and the `RPI5RFS1` mockfs RAM-root path.
- Loader supplies the image through the existing RAMDisk/init memory contract.
- `/dev/console` must support read/write; init opens it and duplicates it to
  descriptors 0–2. PID 1 forks `/bin/sh`, reaps children and respawns the shell.
  It blocks SIGTERM only in PID 1, checks for a pending shutdown request before
  fork/respawn, and parks instead of exiting when shutdown kills its shell.
  Each child restores the saved signal mask before exec; signal dispositions
  remain default. XNU then suspends PID 1 during normal shutdown. The native
  regression uses syscall doubles, not host signal changes or a host reboot.
- Guest credentials must retain root for `reboot(2)`.
- Interactive shell startup emits exactly one own-line `DARWIN:SHELL:READY`.
  Each nonempty input line gets a leading newline before execution, so serial
  output cannot be attached to a non-echoing prompt. `$?` expands per input line;
  host automation must send the command and its status echo on separate lines.
- Boot root is read-only. No networking, dynamic linker, job control, globbing,
  writable root or full POSIX shell compatibility is promised.

## Power off: use the Darwin ABI actually present

This XNU's `bsd/kern/syscalls.master` defines syscall 55 as
`reboot(int opt, char *msg)`. `bsd/sys/reboot.h` defines `RB_HALT = 0x08` and
**does not define `RB_POWERDOWN`**. A power-down flag from another BSD/Linux
must not be invented or reused.

The VM utility calls syscall 55 with `RB_HALT` and a null message. The source
path is `reboot_kernel` (`bsd/kern/kern_shutdown.c`) → `HOST_REBOOT_HALT` →
`halt_all_cpus(false)` (`osfmk/arm64/machine_routines.c`) →
`PEHaltRestart(kPEHaltCPU)` → the VM platform's PSCI `SYSTEM_OFF` HVC.
If the syscall returns, `poweroff` exits nonzero even when the return value was
zero: an issued request is not evidence of a powered-off guest.

The native test adapter records this syscall without executing it; it cannot
reboot the host. Native parser/shell tests and structural Mach-O/RAM-root
inspection are **not VM execution evidence**. Runtime acceptance still needs
real serial command output, exact nonce/status framing and the host's actual
guest-stop callback.

## Opt-in managed guest agent (DC3)

```sh
python3 experiments/darwin-container/userland/build.py --mode agent --output-dir experiments/darwin-container/userland/build/agent-trial-1
python3 -m unittest discover -s experiments/darwin-container/userland/tests -v
```

The default remains `--mode shell`. Agent mode builds only local C/assembly into
the static arm64 executable, adds `/sbin/darwin-agent`, and selects that PID1
child at compile time. PID1 still blocks TERM, restores the child's prior mask,
and reaps adopted descendants. If the agent fails, PID1 parks; it never silently
respawns a new managed session. The Pi sources and kernel remain unchanged.

The dedicated agent implements [DGA1](../agent/PROTOCOL.md): ASCII/hex records
with CRC32, one negotiated session, strict per-direction sequences, bounded
direct-exec argv, separate stdout/stderr pipes and EOFs, explicit exit/signal
metadata, cancellation, output truncation evidence, and normal Darwin halt.
Commands receive stdin EOF, cwd `/`, and fixed `PATH=/bin`, `PWD=/`, `HOME=/`,
`TERM=dumb`. There is one active command, at most sixteen per session, sixteen
arguments and 256 argv bytes. The combined output cap is 1 MiB. A 16 KiB
transmit queue retains short-write cursors across EINTR/EAGAIN while polling
control and pipe readiness; capture high water reserves room for control.

The 72-byte Darwin termios ioctl disables tty echo, editing and translations.
The frozen console still strips bit 7, so payloads are hex encoded. Host control
must remain paced below the 1,024-byte tty input queue. TERM gets approximately
one second before KILL; cleanup/drain then has a bounded deadline. Timing uses
guest wall time, with the host monotonic deadline and VZ stop as the ultimate
boundary. This is an exclusive disposable init/agent/job VM, not an isolation
boundary against a root command changing guest state.

Agent-only `kill(-1, signal, 0)` uses the audited non-POSIX Darwin filtering:
PID1, system processes and the caller are excluded. It catches descendants that
leave process groups. The leader must be reaped, both streams must finish, and
`kill(-1, 0, 0)` must return ESRCH before terminal completion. Zombies count as
remaining; PID1 reaps adopted descendants. Cleanup errors fail the session.
After cancellation intent or output overflow, no next EXEC is allowed.

Source-built fixtures take no arguments:

- `/bin/agent-bytes`: stdout bytes 0–255 and stderr bytes 255–0.
- `/bin/agent-flood`: alternating 256-byte stdout/stderr blocks totaling 2 MiB.
- `/bin/agent-stubborn`: block TERM, print `TERM_BLOCKED`, park until KILL.
- `/bin/agent-escape`: block TERM, fork a `setsid` descendant, print its PID and
  `ESCAPED_DESCENDANT`, keep both processes alive until managed cleanup.
- `/bin/agent-orphan`: the same descendant, with leader exit 0. VZ-only fixture.

Native tests execute the actual agent/codec/fixtures under ASAN/UBSAN with an
adapter. They compare independent golden frames and exercise fragmentation,
binary streams, EOF, exit-vs-signal, malformed/stale messages, short I/O,
cancel races, output limits, launch failure and cleanup failure. Native signals
target only fork-registered test child identities and their discovered children;
the adapter never executes host broadcast kill or reboot. Immediate orphan
creation is refused natively because registry discovery can race reparenting.
The halt syscall is a safe process-exit double. These checks and structural
Mach-O/RAM-root inspection do not establish actual guest execution or shutdown.
