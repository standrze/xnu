#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One bounded shell acceptance trial. Never transmits into diagnostic images."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import select
import termios
import time

try:
    from .serial_terminal_trial import (TERMINAL_LOADER, utc_now, valid_probe_device,
                                       wait_for_boot_markers)
except ImportError:
    from serial_terminal_trial import (TERMINAL_LOADER, utc_now, valid_probe_device,
                                      wait_for_boot_markers)

PROMPT = re.compile(rb"(?:\r?\n)?xnu:[^\r\n]*# ")
DEFAULT_COMMAND_BYTES = 65536
MAX_COMMAND_BYTES = 262144

def matched_lines(data):
    return data.replace(b"\r", b"").split(b"\n")

def check_response(data, expected):
    lines = matched_lines(data)
    if not all(value in lines for value in expected):
        raise RuntimeError("shell result missing exact output lines: " + repr(expected))
    return True

def receive(fd, output, deadline):
    ready, _, _ = select.select([fd], [], [], max(0, min(1, deadline - time.monotonic())))
    if not ready:
        return b""
    data = os.read(fd, 4096)
    if not data:
        raise RuntimeError("serial disconnected")
    output.write(data)
    return data

def command(fd, output, text, expected, progress, seconds=30,
            max_bytes=DEFAULT_COMMAND_BYTES):
    # Larger file dumps must opt in explicitly. Reject an invalid bound before
    # transmitting, and retain the proven shell/SD trials' default 64-KiB cap.
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_COMMAND_BYTES:
        raise ValueError("command output limit must be 1..262144 bytes")
    # Pace bytes through the proven 16-ms RX poller; do not burst a whole line.
    for byte in (text + "\n").encode("ascii"):
        _, ready, _ = select.select([], [fd], [], 2)
        if not ready or os.write(fd, bytes([byte])) != 1:
            raise RuntimeError("serial transmit failed")
        progress["transmitted_bytes"] += 1
        time.sleep(0.025)
    deadline, data = time.monotonic() + seconds, b""
    while time.monotonic() < deadline:
        data += receive(fd, output, deadline)
        if len(data) > max_bytes:
            raise RuntimeError("command output limit exceeded")
        if TERMINAL_LOADER in data or b"panic(cpu" in data:
            raise RuntimeError("reboot or kernel panic during shell command")
        # Startup readiness prompts may still be queued. Only accept a prompt
        # after every required *output line*, never text inside the echoed input.
        normalized = data.replace(b"\r", b"")
        # A read can end immediately after the expected text, before its LF.
        # split() includes that unfinished line; only complete output lines can
        # authorize completion, and the prompt must follow the last such line.
        matches = [list(re.finditer(rb"(?:^|\n)" + re.escape(value) + rb"\n", normalized))
                   for value in expected]
        if all(matches):
            latest = max((items[-1].end() for items in matches), default=0)
            if PROMPT.search(normalized[latest:]):
                check_response(data, expected)
                return data
    raise TimeoutError("shell command did not complete: " + text)

def trial(fd, output, wait, progress):
    wait_for_boot_markers(fd, output, time.monotonic() + wait,
                         extra_markers=(b"RPI5XNU:SHELL:READY",), keyboard_required=False)
    # The image-specific shell marker repeats until input. One-time init and
    # kernel messages can be torn by SMP UART writers; actual exec/IO results
    # below prove the path, not mere presence of those log strings.
    progress["checks"].append("fresh_loader_and_distinct_shell_ready")
    # Receive startup chatter before testing fork/pipe results. Not a soak.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        receive(fd, output, deadline)
    nonce = "S" + secrets.token_hex(4)
    command(fd, output, "echo " + nonce, [nonce.encode()], progress)
    progress["checks"].append("external_echo_fresh_nonce")
    command(fd, output, "echo 'two words'", [b"two words"], progress)
    progress["checks"].append("quoted_arguments")
    command(fd, output, "cat /etc/motd", [b"Experimental Darwin XNU on Raspberry Pi 5. Read-only RAM root."], progress)
    progress["checks"].append("external_file_read")
    command(fd, output, "ls /bin", [b"sh", b"cat", b"wc", b"uname"], progress)
    progress["checks"].append("directory_read")
    command(fd, output, "echo alpha beta | wc", [b"1 2 11"], progress)
    progress["checks"].append("pipe_two_external_processes")
    command(fd, output, "false && echo BAD || echo RECOVERED", [b"RECOVERED"], progress)
    progress["checks"].append("wait_status_conditional")
    command(fd, output, "false", [], progress)
    command(fd, output, "echo $?", [b"1"], progress)
    progress["checks"].append("exit_status_expansion")
    command(fd, output, "cd /etc; pwd", [b"/etc"], progress)
    command(fd, output, "cat < motd | wc", [b"1 10 63"], progress)
    progress["checks"].append("cwd_relative_path_input_redirect")
    command(fd, output, "echo x > /etc/new || echo READONLY", [b"READONLY"], progress)
    progress["checks"].append("readonly_failure_recovery")
    command(fd, output, "sh /etc/demo.sh", [b"SCRIPT_BEGIN", b"SCRIPT_RECOVERED", b"SCRIPT_END"], progress)
    progress["checks"].append("nested_shell_script")
    command(fd, output, "cd /; sleep 1; echo " + nonce, [nonce.encode()], progress)
    progress["checks"].append("blocking_wait_then_live_prompt")
    progress["scope"] = "single physical shell boot; repeated cold boot and formal Gate 3 not established"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device")
    parser.add_argument("output", type=Path)
    parser.add_argument("--boot-wait-seconds", type=int, default=3600)
    args = parser.parse_args()
    if not valid_probe_device(args.device) or not 30 <= args.boot_wait_seconds <= 3600:
        parser.error("expected Debug Probe callout/stable device and bounded 30..3600 boot wait")
    args.output.mkdir(parents=True, exist_ok=False)
    state = {"status": "failed", "started_utc": utc_now(), "device": args.device,
             "checks": [], "transmitted_bytes": 0, "baud": 115200}
    fd, original = None, None
    try:
        fd = os.open(args.device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        original = termios.tcgetattr(fd)
        config = termios.tcgetattr(fd)
        config[0] = config[1] = config[3] = 0
        config[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        config[4] = config[5] = termios.B115200
        config[6][termios.VMIN] = config[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, config)
        termios.tcflush(fd, termios.TCIFLUSH)  # fresh boot evidence, not queued old logs
        with (args.output / "serial.bin").open("xb", buffering=0) as output:
            print("SHELL_TRIAL_ARMED 115200 8N1 NO_TX_UNTIL_SHELL_BOOT", flush=True)
            trial(fd, output, args.boot_wait_seconds, state)
        state["status"] = "passed"
    except (Exception, KeyboardInterrupt) as error:
        state["error"] = str(error) or "interrupted"
    finally:
        if fd is not None:
            if original is not None:
                termios.tcsetattr(fd, termios.TCSANOW, original)
            os.close(fd)
        raw = args.output / "serial.bin"
        state.update({"ended_utc": utc_now(), "bytes": raw.stat().st_size if raw.exists() else 0,
                      "serial_sha256": hashlib.sha256(raw.read_bytes()).hexdigest() if raw.exists() else None})
        (args.output / "state.json").write_text(json.dumps(state, indent=2) + "\n")
        print(json.dumps(state), flush=True)
    return 0 if state["status"] == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
