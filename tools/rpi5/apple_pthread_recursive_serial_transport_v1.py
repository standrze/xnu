#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Default-off command and evidence contract for the recursive-mutex target.

This module has no device discovery, serial open, SSH, media or reboot path.
It is consumed by a future bounded recorder only after the separately built
boot package has been installed through the normal sealed-media workflow.
"""
import hashlib
import re

TARGET_PATH = "/usr/local/libexec/xnu/pthreadprobe"
TARGET_SHA256 = "7077df6eeeb9c6e9d4c6a2dd2be05f92ed79933e976ee94fd98c5469db196ada"
PASS_LINE = b"PTHREAD:RECURSIVE PASS DEPTH=3 FOREIGN_EPERM=2 BUSY=2 RELEASED=1"
MAX_CAPTURE_BYTES = 65536
COMMAND_DEADLINE_SECONDS = 30
BOOT_WAIT_SECONDS = 600
TERMINAL_WATCHDOG_SECONDS = 180
NONCE = re.compile(r"[0-9a-f]{32}")


def validate_nonce(nonce):
    if not isinstance(nonce, str) or NONCE.fullmatch(nonce) is None:
        raise ValueError("fresh 128-bit lowercase-hex nonce required")


def command(nonce):
    """Return one fail-closed zsh command for the exact target path."""
    validate_nonce(nonce)
    script = (
        f"n={nonce}; print -r -- RMX:$n:BEGIN; {TARGET_PATH}; s=$?; "
        'print -r -- RMX:$n:STATUS:$s; exit $s'
    )
    if "'" in script or "\n" in script:
        raise ValueError("unsafe zsh command encoding")
    result = "/bin/zsh -f -c '" + script + "'"
    if len(result.encode("ascii")) > 1023:
        raise ValueError("recovery command exceeds target line capacity")
    return result


def recovery_command(nonce):
    """A distinct prompt-level exchange proves the child zsh exited zero."""
    validate_nonce(nonce)
    return f"echo RMX:{nonce}:RECOVERY_STATUS:$?"


def _lines(raw):
    if not isinstance(raw, bytes):
        raise TypeError("serial receipt must be bytes")
    if len(raw) > MAX_CAPTURE_BYTES:
        raise ValueError("bounded capture exceeded")
    return [line.strip(b"\r") for line in raw.splitlines()]


def inspect_execution(raw, nonce):
    validate_nonce(nonce)
    prefix = ("RMX:" + nonce + ":").encode()
    relevant = [line for line in _lines(raw)
                if line.startswith((b"RMX:", b"PTHREAD:RECURSIVE"))]
    expected = [prefix + b"BEGIN", PASS_LINE, prefix + b"STATUS:0"]
    if relevant != expected:
        raise ValueError("recursive-mutex output missing, duplicated, reordered, nonzero, or wrong nonce")
    return {
        "exact_target_line": PASS_LINE.decode(),
        "depth_three": True,
        "foreign_owner_eperm_count": 2,
        "busy_observation_count": 2,
        "final_release": True,
        "target_status_zero": True,
        "target_sha256": TARGET_SHA256,
    }


def inspect_recovery(raw, nonce):
    validate_nonce(nonce)
    expected = ("RMX:" + nonce + ":RECOVERY_STATUS:0").encode()
    relevant = [line for line in _lines(raw) if line.startswith(b"RMX:")]
    if relevant != [expected]:
        raise ValueError("separate recovery-shell zero-status proof missing or ambiguous")
    return {"recovery_shell_status_zero": True, "batch_process_exit_verified": True}


def accept(execution_raw, recovery_raw, nonce, elapsed_seconds):
    if not isinstance(elapsed_seconds, (int, float)) or not 0 <= elapsed_seconds <= COMMAND_DEADLINE_SECONDS:
        raise ValueError("command deadline exceeded or invalid")
    if len(execution_raw) + len(recovery_raw) > MAX_CAPTURE_BYTES:
        raise ValueError("combined bounded capture exceeded")
    result = inspect_execution(execution_raw, nonce) | inspect_recovery(recovery_raw, nonce)
    result.update({
        "capture_sha256": hashlib.sha256(execution_raw + recovery_raw).hexdigest(),
        "capture_bytes": len(execution_raw) + len(recovery_raw),
        "elapsed_seconds": elapsed_seconds,
        "recursive_mutex_target_execution_qualified": True,
        "atfork_fork_qualified": False,
        "cancelable_variant_qualified": False,
        "filex_stream_locking_qualified": False,
        "networking": False,
        "ssh_transport": False,
        "ssh_daemon": False,
    })
    return result


def execution_contract():
    return {
        "default_off": True,
        "hardware_execution": False,
        "target_path": TARGET_PATH,
        "target_sha256": TARGET_SHA256,
        "expected_line": PASS_LINE.decode(),
        "fresh_nonce_required": True,
        "max_capture_bytes": MAX_CAPTURE_BYTES,
        "command_deadline_seconds": COMMAND_DEADLINE_SECONDS,
        "boot_wait_seconds": BOOT_WAIT_SECONDS,
        "terminal_watchdog_seconds": TERMINAL_WATCHDOG_SECONDS,
        "separate_recovery_exchange_required": True,
        "one_shot_no_implicit_retry": True,
        "automatic_nvme_linux_return_required": True,
        "sealed_working_loader_restoration_required": True,
        "unrelated_feature_claims": [],
    }
