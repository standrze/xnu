#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One bounded package qualification: persistence, exit, concurrent VM and stop."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from workload_runner import digest, package_manifest


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    package, output = args.package.resolve(), args.output.absolute()
    manifest, spec = package_manifest(package)
    require(spec["env"].get("DARWIN_PACKAGE_TRIAL") == "1", "requires opt-in counter trial package")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    root = output / "state"
    passed, runs, processes = [], [], []
    failure = None

    def command(action, *arguments):
        return [str(package / "darwin"), action, *arguments, "--state-root", str(root)]

    def start(label, volume):
        out = (output / (label + "-launcher-stdout.bin")).open("xb")
        err = (output / (label + "-launcher-stderr.bin")).open("xb")
        process = subprocess.Popen(command("run", "--name", label, "--volume", volume), stdout=out, stderr=err)
        processes.append((process, out, err))
        return process

    def finish(label, process, code, count, state):
        require(process.wait(timeout=40) == code, f"{label}: unexpected runner status")
        run = root / "runs" / label
        record = json.loads((run / "run.json").read_text())
        result = json.loads((run / "session/result.json").read_text())
        require(record["state"] == state and record["managed_completion_verified"] and record["guest_stopped"], f"{label}: incomplete managed outcome")
        stdout = (run / "session/command-1-stdout.bin").read_bytes()
        stderr = (run / "session/command-1-stderr.bin").read_bytes()
        require(f"DARWIN_WORKLOAD:zsh=5.9:count={count}:cwd=/data\n".encode() in stdout, f"{label}: missing application output")
        startup = b"DARWIN:ZSH:ENTRY\nDARWIN:ZSH:TSD\nDARWIN:ZSH:ENTROPY\nDARWIN:ZSH:MAIN\n"
        require(stderr == startup * 2 + b"separate stderr from Darwin workload\n", f"{label}: stderr not captured separately")
        require(b"Darwin\n" in stdout, f"{label}: no external guest command")
        serial = (run / "session/serial.bin").read_bytes()
        require(b"VZXNU:NETWORK:ABSENT OFFLINE" in serial and b"VZXNU:NET:READY" not in serial, f"{label}: offline VM device policy not proven")
        require("--network-nat" not in json.loads((run / "launch.json").read_text())["command"], "offline run attached a NAT NIC")
        # Byte counts and terminal/cleanup already checked by the native agent;
        # cross-check persisted files rather than treating wrapper text as proof.
        observed = result["agent"]["commands"][0]
        require(observed["stdoutByteCount"] == len(stdout) and observed["stderrByteCount"] == len(stderr), "captured byte counts mismatch")
        runs.append(label)
        passed.append(f"{label}: {state}, separate streams, complete cleanup and actual guest stop")
        return record

    try:
        finish("write", start("write", "persist"), 0, 1, "succeeded")
        finish("restart", start("restart", "persist"), 0, 2, "succeeded")
        passed.append("same immutable package and named /data volume restored across fresh VM boots")
        finish("nonzero", start("nonzero", "persist"), 7, 3, "exited")
        slow = start("cancel", "persist")
        until = time.monotonic() + 20
        captured = root / "runs/cancel/session/command-1-stdout.bin"
        while time.monotonic() < until:
            if captured.exists() and b"count=4" in captured.read_bytes():
                break
            if slow.poll() is not None:
                raise RuntimeError("slow workload stopped before cancellation")
            time.sleep(0.05)
        else:
            raise RuntimeError("slow workload did not start")
        state = subprocess.run(command("status", "cancel"), capture_output=True, check=True, timeout=10)
        require(json.loads(state.stdout)["state"] == "running", "status did not report the live locked VM")
        collision = subprocess.run(command("run", "--name", "collision", "--volume", "persist"), capture_output=True, timeout=10)
        require(collision.returncode == 1 and b"already attached" in collision.stderr, "concurrent writable volume attach not rejected")
        passed.append("live status and exclusive named-volume collision guard")
        independent = start("independent", "other")
        finish("independent", independent, 0, 1, "succeeded")
        require(slow.poll() is None, "first VM did not remain active during independent VM run")
        passed.append("two simultaneous XNU VMs; independent named volume starts its own counter at 1")
        subprocess.run(command("stop", "cancel"), capture_output=True, check=True, timeout=10)
        record = finish("cancel", slow, 130, 4, "cancelled")
        require(record["cancel_accepted"] is True, "guest did not accept cancellation")
        logs = subprocess.run(command("logs", "restart"), capture_output=True, check=True)
        require(logs.stdout == (root / "runs/restart/session/command-1-stdout.bin").read_bytes(), "logs command changed application bytes")
        passed.append("logs command returns captured application bytes")
        seeds = []
        for label in runs:
            with (root / "runs" / label / "boot.img").open("rb") as image:
                image.seek(manifest["boot_entropy_slot"]["diskOffset"])
                seeds.append(image.read(256))
        require(all(any(seed) for seed in seeds) and len(set(seeds)) == len(seeds), "missing or repeated boot entropy")
        package_manifest(package)
        passed.append("fresh entropy in every boot; immutable package inputs unchanged")
    except Exception as error:
        failure = str(error)
    finally:
        for process, out, err in processes:
            if process.poll() is None:
                process.send_signal(2)
                process.wait(timeout=30)
            out.close()
            err.close()
        report = {"outcome": "passed" if failure is None else "failed", "error": failure, "passed": passed,
                  "package": str(package), "package_manifest_sha256": digest(package / "manifest.json"),
                  "kernel_sha256": digest(package / "kernel.macho"), "runs": runs,
                  "scope": "five short actual XNU VM runs; no soak or hostile-tenant security claim"}
        (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
