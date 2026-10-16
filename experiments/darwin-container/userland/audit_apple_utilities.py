#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Cross-check source-built command bytes, focused guest proof, and old packages."""
import argparse
import json
from pathlib import Path

from prepare_pid1 import inspect as inspect_macho
from ramroot import inspect
from workload_runner import package_manifest
from workspace_launcher import digest, validate_package

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    workspace = HERE / "build/darwin-workspace-0.4.2"
    workload = HERE / "build/apple-userland-workload-0.4.1"
    trial_path = EXPERIMENT / "results/2026-10-12-apple-utilities-trial-4/verification.json"
    run = EXPERIMENT / "results/2026-10-12-apple-userland-workload-final/runs/apple-userland-final"
    base = validate_package(workspace)
    manifest, spec = package_manifest(workload)
    trial = json.loads(trial_path.read_text())
    assert trial["error"] is None and len(trial["runs"]) == 2
    assert trial["manifest_sha256"] == digest(workspace / "manifest.json")
    assert trial["script_sha256"] == digest(HERE / "tests/apple_utilities_smoke.zsh")
    expected = base["apple_utilities"]["commands"]
    assert len(expected) == 23 and manifest["apple_utilities"]["commands"] == expected
    counts = {}
    for package in (workspace, workload):
        image = (package / "ramdisk.bin").read_bytes()
        root = inspect(image, max_nodes=96)
        counts[package.name] = len(root["entries"])
        assert len(image) <= 8 * 1024 * 1024
        try:
            inspect(image)
        except ValueError:
            pass
        else:
            raise RuntimeError("32-node default unexpectedly accepted expanded root")
        files = {entry["path"]: entry for entry in root["entries"]}
        for name, checksum in expected.items():
            entry = files["/bin/" + name]
            raw = image[entry["offset"]:entry["offset"] + entry["size"]]
            assert inspect_macho(raw)["sha256"] == checksum and entry["mode"] == 0o555
            assert name + ": actual guest command exercised" in trial["passed"]
    record = json.loads((run / "run.json").read_text())
    result = json.loads((run / "session/result.json").read_text())
    stdout = (run / "session/command-1-stdout.bin").read_bytes()
    assert record["state"] == "succeeded" and record["managed_completion_verified"] and record["guest_stopped"]
    assert record["package_manifest_sha256"] == digest(workload / "manifest.json")
    assert result["guestStopped"] and result["termination"] == "guestStopped" and not result.get("error")
    assert b"APPLE_USERLAND_WORKLOAD:zsh=5.9:unique-lines=2\n" in stdout
    serial = (run / "session/serial.bin").read_bytes()
    assert b"VZXNU:NETWORK:ABSENT OFFLINE" in serial and b"VZXNU:NET:READY" not in serial
    prior = {}
    for package in (HERE / "build/darwin-workspace-0.2.0", HERE / "build/counter-0.3.0"):
        if "workspace" in package.name:
            validate_package(package)
        else:
            package_manifest(package)
        prior[package.name] = digest(package / "manifest.json")
    evidence = [trial_path, workspace / "manifest.json", workload / "manifest.json", run / "run.json",
                run / "session/result.json", run / "session/command-1-stdout.bin", run / "session/command-1-stderr.bin",
                HERE / "build_apple_utilities.py", HERE / "build.py", HERE / "build_darwin_abi.py",
                HERE / "ramroot.py", HERE / "pack_darwin_workload.py", HERE / "package_workspace.py",
                HERE / "apple-utilities.sources.lock.json", HERE / "tests/apple_utilities_smoke.zsh"]
    report = {"status": "passed", "scope": "23 source-built tools, two short workspace boots and one final offline managed job; not a full option/security suite",
              "commands": sorted(expected), "root_nodes": counts, "loader_root_limit_bytes": 8388608,
              "host_default_and_pi_node_limit": 32, "vm_only_node_limit": 96,
              "old_packages_integrity_verified": prior, "guest_outcome": record["state"],
              "sha256": {str(path.relative_to(EXPERIMENT)): digest(path) for path in evidence},
              "failed_trials_retained": ["trial-1: bulk terminal paste stalled", "trial-2: read-only mkdir ancestor",
                                         "trial-3: old calendar conversion hung; replaced by Apple Libc-391 time code"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps({"status": report["status"], "commands": len(expected), "root_nodes": counts,
                      "evidence": str(args.output)}))


if __name__ == "__main__":
    main()
