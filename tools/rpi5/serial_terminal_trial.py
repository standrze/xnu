#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Guarded, bounded Pi 5 serial-terminal acceptance trial on Linux or macOS.

Start this before booting the opt-in terminal image. No bytes are transmitted
until its unique loader marker and XNU's serial-keyboard marker are received.
The RAM-root trial instead requires its distinct repeated userspace readiness
marker, since concurrent SMP logs can tear the generic keyboard line. Its
actual command responses, not the readiness text, prove input delivery.
If concurrent CPU logs corrupt the first PID 1 banner/prompt, a single
terminal-only echo probe recovers a clean prompt before acceptance commands.
"""

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import secrets
import sys
import termios
import time

BANNER = b"XNU-RPI5 TERMINAL PID1 OK"
PROMPT = b"xnu-rpi5> "
KEYBOARD_START = b"Serial keyboard started"
TERMINAL_LOADER = b"RPI5XNU:BL33:UART_IRQ_BINDING SPI=121 INTID=153 NOT_ENABLED"
PROCESS_READY = b"RPI5XNU:PROC:TRIAL_READY"
PROCESS_PASS = b"RPI5XNU:PROC:PASS"
RAMROOT_READY = b"RPI5XNU:RAMROOT:READY"
RAMROOT_PASS = b"RPI5XNU:RAMROOT:FILES_PASS CROSS_PAGE=1 EOF=1 READONLY=1 MISSING=1 READDIR=1"
WAKE_NONCE = b"RPI5_TERMINAL_WAKE"
TICKS_RESULT = re.compile(rb"TICKS=0x([0-9a-f]{16}) FREQ=0x([0-9a-f]{16})")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def valid_probe_device(device, platform=sys.platform):
    if platform == "darwin":
        return re.fullmatch(r"/dev/cu\.usbmodem[A-Za-z0-9_-]+", device) is not None
    if platform.startswith("linux"):
        return device.startswith("/dev/serial/by-id/usb-Raspberry_Pi_Debug_Probe_")
    return False


def read_until(fd, output, capture, marker, deadline):
    """Return bytes through marker, retaining all raw bytes for audit."""
    while marker not in capture:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"timed out waiting for {marker!r}")
        ready, _, _ = select.select([fd], [], [], min(remaining, 1.0))
        if not ready:
            continue
        data = os.read(fd, 4096)
        if not data:
            raise RuntimeError("serial disconnected")
        output.write(data)
        capture += data
        if marker not in capture and len(capture) > 4096:
            capture = capture[-4096:]
    end = capture.index(marker) + len(marker)
    return capture[:end], capture[end:]


def wait_for_boot_markers(fd, output, deadline, extra_markers=(), keyboard_required=True,
                          abort_markers=()):
    """Require this terminal loader and the XNU receive poller to start."""
    required = (TERMINAL_LOADER,) + ((KEYBOARD_START,) if keyboard_required else ()) + tuple(extra_markers)
    seen = set()
    capture = b""
    while len(seen) != len(required):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            missing = [marker for marker in required if marker not in seen]
            raise TimeoutError(f"timed out waiting for {missing!r}")
        ready, _, _ = select.select([fd], [], [], min(remaining, 1.0))
        if not ready:
            continue
        data = os.read(fd, 4096)
        if not data:
            raise RuntimeError("serial disconnected")
        output.write(data)
        capture = (capture + data)[-4096:]
        for marker in abort_markers:
            if marker in capture:
                raise RuntimeError(f'boot failure before readiness: {marker!r}')
        seen.update(marker for marker in required if marker in capture)
    return BANNER in capture and PROMPT in capture


def transmit(fd, command, progress):
    remaining = memoryview(command)
    while remaining:
        _, ready, _ = select.select([], [fd], [], 2.0)
        if not ready:
            raise TimeoutError("serial transmit stalled")
        count = os.write(fd, remaining)
        if count <= 0:
            raise RuntimeError("serial transmit failed")
        progress["transmitted_bytes"] += count
        remaining = remaining[count:]


def parse_ticks(response):
    match = TICKS_RESULT.search(response)
    if not match:
        raise RuntimeError("ticks response missing fixed-width counter/frequency")
    counter, frequency = (int(value, 16) for value in match.groups())
    if frequency == 0:
        raise RuntimeError("ticks response reports zero counter frequency")
    return counter, frequency


def parse_process_result(response):
    """Require fork, fresh exec/argv/BSS, exact-child wait status and COW."""
    child = re.findall(rb"RPI5XNU:PROC:EXEC_CHILD PID=0x([0-9a-f]{16}) "
                       rb"ARG=RPI5_EXEC_ARG BSS_ZERO=1", response)
    parent = re.findall(rb"RPI5XNU:PROC:WAIT_CHILD PID=0x([0-9a-f]{16}) "
                        rb"STATUS=0x00002a00 COW=1", response)
    fork = b"RPI5XNU:PROC:FORK_CHILD"
    if b"RPI5XNU:PROC:FAIL" in response or len(child) != 1 or len(parent) != 1 or \
            child != parent or int(child[0], 16) <= 1 or fork not in response or \
            PROCESS_PASS not in response:
        raise RuntimeError("process result did not prove fork/exec/wait/COW")
    if not (response.index(fork) < response.index(b"RPI5XNU:PROC:EXEC_CHILD") <
            response.index(b"RPI5XNU:PROC:WAIT_CHILD") < response.index(PROCESS_PASS)):
        raise RuntimeError("process result markers out of order")
    return int(child[0], 16)


def process_trial(fd, output, seconds, boot_wait_seconds, progress):
    """One focused shell-dependency check; never type into older images."""
    if "ramroot_recovery" in progress:
        recover_ramroot_prompt(fd, output, progress)
        progress["checks"].append("captured_ramroot_and_fresh_echo_after_quiet")
    elif "resume_boot" in progress:
        wait_for_process_resume(fd, output, time.monotonic() + boot_wait_seconds)
        progress["checks"].append("captured_loader_and_live_process_readiness")
    else:
        ramroot = progress.get("ramroot_trial", False)
        wait_for_boot_markers(fd, output, time.monotonic() + boot_wait_seconds,
                              extra_markers=((PROCESS_READY, RAMROOT_READY) if ramroot else (PROCESS_READY,)),
                              keyboard_required=not ramroot)
        # RAM-root's repeated PID1-specific marker supersedes the generic
        # one-time keyboard log; actual responses prove RX, not that log.
        progress["checks"].append("ramroot_loader_and_pid1_ready" if ramroot else
                                   "process_image_loader_and_keyboard")
    deadline = time.monotonic() + seconds
    transmit(fd, b"process\n", progress)
    capture = b""
    while PROCESS_PASS not in capture:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("process launch did not complete")
        ready, _, _ = select.select([fd], [], [], min(remaining, 1.0))
        if not ready:
            continue
        data = os.read(fd, 4096)
        if not data:
            raise RuntimeError("serial disconnected during process launch")
        output.write(data)
        capture += data
        failure = re.search(rb"RPI5XNU:PROC:FAIL[^\n]*\n", capture)
        if failure:
            raise RuntimeError("process launch failed: " +
                               failure[0].decode("ascii", "replace").strip())
        if b"Unknown command. Type help." in capture:
            raise RuntimeError("process command not recognized by payload")
        if b"RPI5XNU:BL33:" in capture or b"Debian GNU/Linux" in capture:
            raise RuntimeError("reboot detected during process launch")
        if len(capture) > 16384:
            raise RuntimeError("process result exceeded bounded capture")
    end = capture.index(PROCESS_PASS) + len(PROCESS_PASS)
    if progress.get("ramroot_trial"):
        if RAMROOT_PASS not in capture or capture.index(RAMROOT_PASS) > capture.index(b"RPI5XNU:PROC:FORK_CHILD"):
            raise RuntimeError("RAM-root file checks missing before process launch")
        progress["checks"].append("ramroot_cross_page_eof_readonly_missing_readdir")
    progress["child_pid"] = parse_process_result(capture[:end])
    progress["checks"].extend(("fork_child", "exec_argv_and_fresh_bss",
                               "wait_exact_child_exit_42", "parent_cow_isolation"))
    read_until(fd, output, capture[end:], PROMPT, deadline)
    transmit(fd, b"status\n", progress)
    _, tail = read_until(fd, output, b"", b"PID 1 alive; serial console active.", deadline)
    read_until(fd, output, tail, PROMPT, deadline)
    progress["checks"].append("pid1_prompt_after_reap")


def process_resume_evidence(directory, device):
    """Resume only a recent, zero-TX process capture on this same device.

    This is explicit operator recovery for a torn generic keyboard log, not
    proof that the poller works. Require fresh process-only markers next; a
    successful command response is the actual input-delivery evidence.
    """
    state = json.loads((directory / "state.json").read_text())
    raw_path = directory / "serial.bin"
    if raw_path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("resume capture exceeds bound")
    raw = raw_path.read_bytes()
    age = (datetime.now(timezone.utc) -
           datetime.fromisoformat(state["ended_utc"])).total_seconds()
    if not (state.get("process_trial") is True and
            state.get("transmitted_bytes") == 0 and
            state.get("device") == device and 0 <= age <= 900 and
            state.get("sha256") == hashlib.sha256(raw).hexdigest()):
        raise ValueError("resume requires a recent intact zero-TX process capture on this device")
    if raw.count(TERMINAL_LOADER) != 1:
        raise ValueError("resume requires exactly one captured terminal loader")
    after_loader = raw.split(TERMINAL_LOADER, 1)[1]
    if after_loader.count(PROCESS_READY) < 2 or PROMPT not in after_loader:
        raise ValueError("resume requires repeated process readiness and prompt")
    after_ready = after_loader.split(PROCESS_READY, 1)[1]
    if any(marker in after_ready for marker in
           (b"RPI5XNU:BL33:", b"RPi: BOOTSYS", b"Debian GNU/Linux", b"panic(")):
        raise ValueError("reset or panic after captured readiness")
    return {"directory": str(directory), "sha256": state["sha256"],
            "keyboard_marker_seen": KEYBOARD_START in raw,
            "guard": "captured_loader_plus_two_fresh_process_ready_prompts"}


def ramroot_recovery_evidence(directory, device):
    """Explicit single same-boot retry for an interrupted result, not a loop.

    Requires recorded successful file checks/exec and a returned prompt, with
    only one process command sent. A known failure or reset is not recoverable
    by this option. The original incomplete result remains incomplete.
    """
    state = json.loads((directory / "state.json").read_text())
    path = directory / "serial.bin"
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("recovery capture exceeds bound")
    raw = path.read_bytes()
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(state["ended_utc"])).total_seconds()
    if not (state.get("ramroot_trial") is True and state.get("transmitted_bytes") == 8 and
            state.get("device") == device and 0 <= age <= 900 and
            state.get("sha256") == hashlib.sha256(raw).hexdigest() and
            not state.get("ramroot_recovery")):
        raise ValueError("recovery requires recent intact single-command RAM-root capture")
    required = (TERMINAL_LOADER, b"RPI5XNU:RAMROOT:MOUNT NODES=10 BYTES=131072 READONLY",
                RAMROOT_READY, PROCESS_READY, RAMROOT_PASS, b"RPI5XNU:PROC:EXEC_CHILD")
    if any(marker not in raw for marker in required) or raw.count(TERMINAL_LOADER) != 1:
        raise ValueError("RAM-root recovery identity/file/exec evidence missing")
    after = raw.split(RAMROOT_READY, 1)[1]
    if any(marker in after for marker in (b"RPI5XNU:BL33:", b"RPi: BOOTSYS",
                                          b"Debian GNU/Linux", b"panic(", b"RPI5XNU:PROC:FAIL")):
        raise ValueError("failure or reset prevents RAM-root recovery")
    if PROMPT not in raw.split(b"RPI5XNU:PROC:EXEC_CHILD", 1)[1]:
        raise ValueError("no returned prompt after child execution")
    return {"directory": str(directory), "sha256": state["sha256"],
            "reason": "startup UART collision; retry once after quiet and fresh echo"}


def recover_ramroot_prompt(fd, output, progress, quiet_seconds=2.0):
    deadline = time.monotonic() + 10
    quiet_until = time.monotonic() + quiet_seconds
    recent = b""
    while time.monotonic() < quiet_until:
        now = time.monotonic()
        if now >= deadline:
            raise TimeoutError("serial did not settle for same-boot recovery")
        ready, _, _ = select.select([fd], [], [], min(quiet_until - now, deadline - now))
        if ready:
            data = os.read(fd, 4096)
            if not data:
                raise RuntimeError("serial disconnected during recovery")
            output.write(data)
            recent = (recent + data)[-4096:]
            if any(marker in recent for marker in (b"RPI5XNU:BL33:", b"RPi: BOOTSYS",
                                                  b"Debian GNU/Linux", b"panic(")):
                raise RuntimeError("reset or panic during recovery")
            quiet_until = time.monotonic() + quiet_seconds
    # The receive thread polls every 16 ms. A long unpaced recovery line
    # lost its tail on hardware, leaving a partial canonical input line.
    # Clear that line (default VKILL), then pace a short fresh nonce.
    nonce = b"R" + secrets.token_hex(4).encode()
    for byte in b"\x15echo " + nonce + b"\n":
        transmit(fd, bytes((byte,)), progress)
        time.sleep(0.025)
    _, tail = read_until(fd, output, b"", b"ECHO: " + nonce, time.monotonic() + 10)
    read_until(fd, output, tail, PROMPT, time.monotonic() + 10)


def wait_for_process_resume(fd, output, deadline):
    """No TX until two new process-specific readiness/prompt pairs arrive."""
    capture = b""
    pairs = 0
    while pairs < 2:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("fresh process readiness did not arrive")
        ready, _, _ = select.select([fd], [], [], min(remaining, 1.0))
        if not ready:
            continue
        data = os.read(fd, 4096)
        if not data:
            raise RuntimeError("serial disconnected during resume")
        output.write(data)
        capture += data
        if any(marker in capture for marker in
               (b"RPI5XNU:BL33:", b"RPi: BOOTSYS", b"Debian GNU/Linux", b"panic(")):
            raise RuntimeError("reset or panic during process resume")
        while PROCESS_READY in capture:
            start = capture.index(PROCESS_READY) + len(PROCESS_READY)
            end = capture.find(PROMPT, start)
            if end < 0:
                break
            pairs += 1
            capture = capture[end + len(PROMPT):]
        capture = capture[-4096:]


def trial(fd, output, seconds, nonce=b"RPI5_TERMINAL_PROBE", progress=None,
          boot_wait_seconds=None):
    boot_deadline = time.monotonic() + (seconds if boot_wait_seconds is None
                                        else boot_wait_seconds)
    if progress is None:
        progress = {"checks": [], "transmitted_bytes": 0}
    clean_banner = wait_for_boot_markers(fd, output, boot_deadline)
    deadline = time.monotonic() + seconds
    progress["checks"].append("terminal_loader_and_keyboard")
    if clean_banner:
        progress["checks"].append("terminal_banner_prompt")
        time.sleep(0.25)
    else:
        # Secondary CPU UART writes can tear the one-time PID 1 banner and
        # prompt. The loader marker is exclusive to this terminal image, so
        # one echo probe is safe here but never sent to the Gate 3 baseline.
        time.sleep(1.0)
        transmit(fd, b"echo " + WAKE_NONCE + b"\n", progress)
        matched, remainder = read_until(fd, output, b"", b"ECHO: " + WAKE_NONCE,
                                        deadline)
        read_until(fd, output, remainder, PROMPT, deadline)
        progress["checks"].append("terminal_wake_echo")

    steps = [
        (b"help\n", b"help, status, ticks, echo TEXT", "help"),
        (b"status\n", b"PID 1 alive; serial console active.", "status"),
        (b"ticks\n", b"TICKS=0x", "ticks_first"),
        (b"ticks\n", b"TICKS=0x", "ticks_monotonic"),
        (b"echo " + nonce + b"\n", b"ECHO: " + nonce, "echo"),
        (b"statuz\x7fs\n", b"PID 1 alive; serial console active.", "line_editing"),
        (b"unknown\n", b"Unknown command. Type help.", "unknown_command"),
        (b"status\n", b"PID 1 alive; serial console active.", "repeated_command_recovery"),
    ]
    prior_ticks = None
    for command, response, name in steps:
        # Drop already captured post-prompt logs before sending. The next
        # response cannot exist before its command is transmitted.
        capture = b""
        transmit(fd, command, progress)
        matched, capture = read_until(fd, output, capture, response, deadline)
        through_prompt, capture = read_until(fd, output, capture, PROMPT, deadline)
        if name.startswith("ticks_"):
            counter, frequency = parse_ticks(matched + through_prompt)
            if prior_ticks is not None and (counter <= prior_ticks[0] or
                                            frequency != prior_ticks[1]):
                raise RuntimeError("ticks did not advance at a stable frequency")
            prior_ticks = counter, frequency
        progress["checks"].append(name)
    return progress


def check_late_terminal(fd, output, target, progress):
    """Keep the same open serial session through the old reset window."""
    recent = b""
    while time.monotonic() < target:
        ready, _, _ = select.select([fd], [], [], min(target - time.monotonic(), 1.0))
        if not ready:
            continue
        chunk = os.read(fd, 4096)
        if not chunk:
            raise RuntimeError("serial disconnected during late check")
        output.write(chunk)
        recent = (recent + chunk)[-4096:]
        if b"RPI5XNU:BL33:" in recent or b"Debian GNU/Linux" in recent:
            raise RuntimeError("reboot detected before late terminal check")
    nonce = b"RPI5_TERMINAL_LATE_CHECK"
    transmit(fd, b"echo " + nonce + b"\n", progress)
    _, remainder = read_until(fd, output, b"", b"ECHO: " + nonce,
                              time.monotonic() + 15)
    read_until(fd, output, remainder, PROMPT, time.monotonic() + 15)
    progress["checks"].append("late_echo_after_old_watchdog_window")


def run_trial(fd, output, seconds, late_check_seconds, progress,
              boot_wait_seconds=None):
    """Only count terminal longevity after its initial commands have passed."""
    trial(fd, output, seconds, progress=progress, boot_wait_seconds=boot_wait_seconds)
    if late_check_seconds:
        accepted_monotonic = time.monotonic()
        check_late_terminal(fd, output, accepted_monotonic + late_check_seconds,
                            progress)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device", help="Linux Debug Probe by-id path or macOS /dev/cu.usbmodem path")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--seconds", type=int, default=180,
                        help="Initial-command timeout after boot markers; excludes boot/late waits")
    parser.add_argument("--boot-wait-seconds", type=int, default=600,
                        help="Receive-only wait for terminal boot markers (30–3600 seconds)")
    parser.add_argument("--late-check-seconds", type=int, default=0,
                        help="Retain the session and test this many seconds after initial acceptance")
    parser.add_argument("--process-trial", action="store_true",
                        help="Only test fork/exec/wait/COW and prompt recovery on the distinct process image")
    parser.add_argument("--resume-process-boot", type=Path,
                        help="Explicit same-boot recovery from a recent zero-TX process capture; requires fresh readiness")
    parser.add_argument("--ramroot-trial", action="store_true",
                        help="Run file checks plus exec from a separate RAM-root file; requires its distinct readiness marker")
    parser.add_argument("--recover-ramroot-result", type=Path,
                        help="Explicit once-only same-boot retry after a torn result; requires captured file/exec success and prompt")
    args = parser.parse_args()
    if args.ramroot_trial:
        args.process_trial = True
        if args.resume_process_boot:
            parser.error("RAM-root recovery from prior captures is not supported")
    if args.recover_ramroot_result and not args.ramroot_trial:
        parser.error("result recovery requires --ramroot-trial")
    if not valid_probe_device(args.device):
        parser.error("Raspberry Pi Debug Probe serial path required for this host")
    if not 30 <= args.seconds <= 600:
        parser.error("duration must be 30–600 seconds")
    if not 30 <= args.boot_wait_seconds <= 3600:
        parser.error("boot wait must be 30–3600 seconds")
    if args.late_check_seconds and not 180 <= args.late_check_seconds <= 600:
        parser.error("late check must be 180–600 seconds after initial acceptance")
    if args.process_trial and args.late_check_seconds:
        parser.error("process trial is focused; do not combine it with another soak/late check")
    if args.resume_process_boot and not args.process_trial:
        parser.error("resume is restricted to the process trial")
    resume = (process_resume_evidence(args.resume_process_boot, args.device)
              if args.resume_process_boot else None)
    recovery = (ramroot_recovery_evidence(args.recover_ramroot_result, args.device)
                if args.recover_ramroot_result else None)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    started = utc_now()
    fd = None
    old = None
    result = {"status": "failed", "checks": [], "transmitted_bytes": 0}
    if args.ramroot_trial:
        result["ramroot_trial"] = True
    if recovery is not None:
        result["ramroot_recovery"] = recovery
    if resume is not None:
        result["resume_boot"] = resume
    try:
        fd = os.open(args.device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        old = termios.tcgetattr(fd)
        config = termios.tcgetattr(fd)
        config[0] = config[1] = config[3] = 0
        config[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        config[4] = config[5] = termios.B115200
        config[6][termios.VMIN] = 0
        config[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, config)
        if resume is not None:
            termios.tcflush(fd, termios.TCIFLUSH)  # Require new, not queued markers.
        with (args.output_dir / "serial.bin").open("xb", buffering=0) as output:
            print("TERMINAL_TRIAL_READY 115200 8N1 MARKER_GUARDED", flush=True)
            if args.process_trial:
                process_trial(fd, output, args.seconds, args.boot_wait_seconds, result)
            else:
                run_trial(fd, output, args.seconds, args.late_check_seconds, result,
                          args.boot_wait_seconds)
            os.fsync(output.fileno())
        result["status"] = "passed"
    except Exception as exc:
        result["error"] = str(exc)
        print(f"TERMINAL_TRIAL_ERROR {exc}", file=sys.stderr, flush=True)
    finally:
        if fd is not None:
            if old is not None:
                termios.tcsetattr(fd, termios.TCSANOW, old)
            os.close(fd)
        raw = args.output_dir / "serial.bin"
        result.update({"started_utc": started, "ended_utc": utc_now(),
                       "device": args.device, "baud": 115200,
                       "requested_seconds": args.seconds,
                       "boot_wait_seconds": args.boot_wait_seconds,
                       "late_check_seconds": args.late_check_seconds,
                       "late_check_anchor": "after_initial_acceptance",
                       "process_trial": args.process_trial,
                       "bytes": raw.stat().st_size if raw.exists() else 0,
                       "sha256": hashlib.sha256(raw.read_bytes()).hexdigest() if raw.exists() else None})
        (args.output_dir / "state.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
