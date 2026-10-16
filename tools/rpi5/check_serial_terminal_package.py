#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preflight the opt-in terminal image before any Pi SD staging."""

import argparse
import hashlib
import json
from pathlib import Path

try:
    from .prepare_pid1 import inspect_process_literals
    from .ramroot import inspect as inspect_ramroot
except ImportError:
    from prepare_pid1 import inspect_process_literals
    from ramroot import inspect as inspect_ramroot

ROOT = Path(__file__).resolve().parents[2]
GATE3_BASELINE_SHA256 = "454906aa802f013549ef936a9d15bcc42b10638ed73d6759a276797737b1d06c"
TERMINAL_COMMAND = (b"serial=3 debug=0xa -enable_kprintf_spam kt=2 -noprogress "
                    b"rd=md0 launchdsuffix=release bcm2712_register_secondaries=1 "
                    b"bcm2712_cpu_on_all=1 bcm2712_terminal_watchdog=1")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect(package: Path, kernel: Path, init: Path, baseline: Path,
            process_trial: bool = False, ramroot_trial: bool = False,
            shell_trial: bool = False) -> dict:
    manifest = json.loads((package / "manifest.json").read_text())
    image = package / "probe.bin"
    image_hash = sha256(image)
    kernel_hash = sha256(kernel)
    init_hash = sha256(init)
    baseline_hash = sha256(baseline)
    recorded = [value for name, value in manifest.get("sha256", {}).items()
                if (Path(name) if Path(name).is_absolute() else ROOT / name).resolve()
                == image.resolve()]
    with image.open("rb") as stream:
        image_bytes = stream.read()
    main_commands = [command for command in manifest.get("commands", [])
                     if any(Path(item).name == "probe_main.c" for item in command)]
    disallowed = ("gate3_register_cpus", "gate3_register_boot_cpu", "gate3_cpu_on_1",
                  "gate3_tlb_trial", "gate3_user_tlb_trial", "gate3_concurrency_trial",
                  "gate3_xnupost_inventory", "gate3_xnupost_index", "gate3_xnupost_config",
                  "gate3_qualification_config", "gate3_soak_seconds")
    checks = {
        "image_hash_matches_manifest": len(recorded) == 1 and recorded[0] == image_hash,
        "kernel_matches_manifest": manifest.get("embedded_kernel", {}).get("sha256") == kernel_hash,
        "init_matches_manifest": manifest.get("embedded_init", {}).get("sha256") == init_hash,
        "baseline_is_unchanged_gate3_image": baseline_hash == GATE3_BASELINE_SHA256,
        "terminal_and_baseline_distinct": image_hash != baseline_hash,
        "terminal_four_cpu_transfer": manifest.get("serial_terminal") is True and
            manifest.get("xnu_transfer_enabled") is True and
            manifest.get("gate3_cpu_on_all") is True,
        "no_gate3_trial_or_qualification": all(name in manifest and not manifest[name]
                                               for name in disallowed),
        "terminal_compile_switch": len(main_commands) == 1 and
            "-DRPI5_SERIAL_TERMINAL=1" in main_commands[0],
        "terminal_boot_command_embedded": TERMINAL_COMMAND in image_bytes,
        "terminal_pid1_embedded": b"XNU-RPI5 TERMINAL PID1 OK" in image_bytes and
            b"xnu-rpi5> " in image_bytes,
        "monotonic_diagnostic_embedded": b"TICKS=0x" in image_bytes and
            b" FREQ=0x" in image_bytes,
        "runtime_irq_binding_guard_embedded":
            b"UART_IRQ_BINDING SPI=121 INTID=153 NOT_ENABLED" in image_bytes,
    }
    if shell_trial:
        # This is real multi-file userland, not the old diagnostic interpreter.
        del checks["terminal_pid1_embedded"]
        del checks["monotonic_diagnostic_embedded"]
        checks["shell_init_and_prompt_embedded"] = all(marker in image_bytes for marker in (
            b"RPI5XNU:INIT:READY", b"RPI5XNU:SHELL:READY", b"xnu:/# "))
        try:
            init_bytes = init.read_bytes()
            archive = inspect_ramroot(init_bytes)
            programs = ("sh", "echo", "cat", "ls", "wc", "sleep", "uname", "true", "false", "hexdump")
            entries = {entry["path"]: entry for entry in archive["entries"]}
            paths = ["/sbin/launchd"] + ["/bin/" + name for name in programs]
            executables = [entries[path] for path in paths]
            checks["shell_programs_readonly_disjoint"] = (
                all(e["mode"] == 0o555 and e["type"] == "file" and e["size"] > 0 for e in executables)
                and len({e["offset"] for e in executables}) == len(executables)
                and entries["/sbin/launchd"]["offset"] == 0)
            checks["shell_archive_fully_embedded"] = init_bytes in image_bytes
            checks["shell_no_old_diagnostic_dispatch"] = b"RPI5XNU:PROC:TRIAL_READY" not in init_bytes
        except (ValueError, KeyError):
            checks["shell_archive_valid"] = False
    if process_trial:
        process_markers = (b"RPI5XNU:PROC:TRIAL_READY", b"RPI5XNU:PROC:FORK_CHILD",
                           b"RPI5XNU:PROC:EXEC_CHILD PID=0x",
                           b"RPI5XNU:PROC:WAIT_CHILD PID=0x",
                           b"RPI5XNU:PROC:PASS", b"--process-child", b"RPI5_EXEC_ARG")
        init_bytes = init.read_bytes()
        checks["distinct_process_payload_embedded"] = all(
            marker in init_bytes and marker in image_bytes for marker in process_markers)
        try:
            if ramroot_trial:
                archive = inspect_ramroot(init_bytes)
                launchd = next(e for e in archive["entries"] if e["path"] == "/sbin/launchd")
                child = next(e for e in archive["entries"] if e["path"] == "/bin/child")
                checks["ramroot_distinct_child_extent"] = child["offset"] > 0
                checks["ramroot_specific_markers"] = all(marker in image_bytes for marker in (
                    b"RPI5XNU:RAMROOT:READY", b"RPI5XNU:RAMROOT:FILES_PASS",
                    b"RPI5XNU:RAMROOT:MOUNT"))
                inspect_process_literals(init_bytes[:launchd["size"]], b"/bin/child")
                inspect_process_literals(init_bytes[child["offset"]:child["offset"] + child["size"]], b"/bin/child")
            else:
                inspect_process_literals(init_bytes)
            checks["linked_process_literals_exact"] = True
        except ValueError:
            checks["linked_process_literals_exact"] = False
    return {"image": str(image), "image_sha256": image_hash,
            "kernel_sha256": kernel_hash, "init_sha256": init_hash,
            "baseline_sha256": baseline_hash, "checks": checks,
            "preflight_pass": all(checks.values()),
            "scope": "host package identity only; no SD write, board boot, UART input or IRQ proof"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--kernel", required=True, type=Path)
    parser.add_argument("--init", required=True, type=Path)
    parser.add_argument("--gate3-baseline", required=True, type=Path)
    parser.add_argument("--process-trial", action="store_true",
                        help="Require the separate fork/exec/wait trial payload as well")
    parser.add_argument("--ramroot-trial", action="store_true",
                        help="Require RAM-root metadata, separate child extent and filesystem trial markers")
    parser.add_argument("--shell-trial", action="store_true",
                        help="Require the actual static shell/init/utility RAM root instead of diagnostic commands")
    args = parser.parse_args()
    if args.shell_trial and (args.process_trial or args.ramroot_trial):
        parser.error("shell trial is distinct from the diagnostic process/RAM-root trials")
    report = inspect(args.package, args.kernel, args.init, args.gate3_baseline,
                     process_trial=args.process_trial or args.ramroot_trial,
                     ramroot_trial=args.ramroot_trial, shell_trial=args.shell_trial)
    print(json.dumps(report, indent=2))
    if not report["preflight_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
