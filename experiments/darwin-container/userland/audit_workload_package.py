#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Recheck package/real-VM records and preserve only non-secret evidence; no VMs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from pack_darwin_workload import entry_script, unpack_root
from workload_runner import digest, outcome, package_manifest, status


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_package(package):
    manifest, spec = package_manifest(package)
    files = unpack_root((package / "ramdisk.bin").read_bytes())
    require(files["/app/entry.zsh"][0] == entry_script(spec), "entrypoint/env/cwd adapter mismatch")
    for record in spec["files"]:
        data, mode = files[record["path"]]
        require(hashlib.sha256(data).hexdigest() == record["sha256"] and mode == record["mode"], "embedded payload mismatch")
    root_build = json.loads((package / "provenance/agent-root-build.json").read_text())
    require(root_build["mode"] == "agent-zsh" and root_build["packaged_workload_profile"] and root_build["writable_storage"], "wrong managed runtime")
    require(hashlib.sha256(files["/bin/zsh"][0]).hexdigest() == root_build["apple_zsh"]["executable"]["sha256"], "Apple-zsh binary provenance mismatch")
    loader = json.loads((package / "provenance/loader-build.json").read_text())
    require(loader["inputs"]["kernelSHA256"] == digest(package / "kernel.macho") and
            loader["inputs"]["ramrootSHA256"] == digest(package / "ramdisk.bin"), "loader embedded-input mismatch")
    kernel = json.loads((package / "provenance/workload-kernel-build.json").read_text())
    require(kernel["exit_code"] == 0 and any(item["sha256"] == digest(package / "kernel.macho") for item in kernel["kernels"]), "kernel not from successful recorded source build")
    for relative in ("osfmk/prng/prng_random.c", "iokit/Kernel/VZGenericPlatformExpert.cpp"):
        require(digest(package / "provenance/kernel-source" / relative) == kernel["effective_source_sha256"][relative], "compiled kernel prerequisite changed")
    slot = manifest["boot_entropy_slot"]
    with (package / "efi-template.img").open("rb") as stream:
        stream.seek(slot["diskOffset"])
        require(stream.read(256) == bytes(256), "package template contains a provisioned seed")
    return manifest


def check_run(directory, expected_state, expected_code):
    record = json.loads((directory / "run.json").read_text())
    result = json.loads((directory / "session/result.json").read_text())
    observed = outcome(result, record["native_exit_code"], record["cancel_requested"])
    require(all(record[key] == value for key, value in observed.items()), "wrapper outcome differs from native evidence")
    require(record["state"] == expected_state and record["runner_exit_code"] == expected_code and
            record["managed_completion_verified"] and record["guest_stopped"], "incomplete/incorrect run")
    require(status(directory)["state"] != "running", "qualification left a live VM/lock")
    launch = json.loads((directory / "launch.json").read_text())
    require(digest(directory / "boot.img") == launch["boot_sha256"], "run boot image differs from launch")
    command = result["agent"]["commands"][0]
    for stream in ("stdout", "stderr"):
        require((directory / "session" / command[stream + "Path"]).stat().st_size == command[stream + "ByteCount"], "stream byte-count mismatch")
    return record


def preserve_run(source, destination):
    destination.mkdir(mode=0o700)
    for name in ("run.json", "launch.json"):
        shutil.copy2(source / name, destination / name)
    (destination / "session").mkdir()
    for path in (source / "session").iterdir():
        if path.is_file() and path.name != "efi-variables.bin" and path.suffix in (".json", ".bin", ".txt"):
            shutil.copy2(path, destination / "session" / path.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--trial", required=True, type=Path)
    parser.add_argument("--nat-run", required=True, type=Path)
    parser.add_argument("--nat-package", required=True, type=Path)
    parser.add_argument("--example-package", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = check_package(args.package)
    check_package(args.example_package)
    nat_manifest = check_package(args.nat_package)
    trial = json.loads((args.trial / "verification.json").read_text())
    require(trial["outcome"] == "passed" and trial["package_manifest_sha256"] == digest(args.package / "manifest.json"), "trial failed or package changed")
    seeds, records = [], {}
    for label, state, code in (("write", "succeeded", 0), ("restart", "succeeded", 0), ("nonzero", "exited", 7),
                               ("independent", "succeeded", 0), ("cancel", "cancelled", 130)):
        run = args.trial / "state/runs" / label
        records[label] = check_run(run, state, code)
        require(records[label]["package_manifest_sha256"] == trial["package_manifest_sha256"], "run used another package")
        raw = (run / "session/serial.bin").read_bytes()
        require(b"VZXNU:NETWORK:ABSENT OFFLINE" in raw and b"VZXNU:NET:READY" not in raw, "offline run device evidence missing")
        with (run / "boot.img").open("rb") as stream:
            stream.seek(manifest["boot_entropy_slot"]["diskOffset"])
            seeds.append(stream.read(256))
    require(len(set(seeds)) == 5 and all(any(seed) for seed in seeds), "reused/missing entropy")
    require(records["write"]["data_disk"] == records["restart"]["data_disk"] != records["independent"]["data_disk"], "volume identity mismatch")
    require(records["cancel"]["started_at"] < records["independent"]["started_at"] < records["independent"]["finished_at"] < records["cancel"]["finished_at"], "independent VM did not overlap the cancelled VM")
    require(records["cancel"]["cancel_accepted"] is True, "missing cancellation acceptance")
    collision = json.loads((args.trial / "state/runs/collision/run.json").read_text())
    require(collision["state"] == "failed" and "already attached" in collision["error"], "volume collision was not rejected")
    nat = check_run(args.nat_run, "succeeded", 0)
    require(nat["package_manifest_sha256"] == digest(args.nat_package / "manifest.json") and nat["volume"] is None, "NAT disposable-run mismatch")
    raw = (args.nat_run / "session/serial.bin").read_bytes()
    out = (args.nat_run / "session/command-1-stdout.bin").read_bytes()
    require(nat["network"] == "nat" and b"VZXNU:NET:READY en0" in raw and b"DARWIN:NET:DHCP IP=" in out and b"count=1" in out, "NAT package did not configure network and run its entrypoint")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for label in records:
        preserve_run(args.trial / "state/runs" / label, args.output / label)
    preserve_run(args.nat_run, args.output / "nat-disposable")
    shutil.copy2(args.package / "manifest.json", args.output / "trial-package-manifest.json")
    shutil.copy2(args.example_package / "manifest.json", args.output / "example-package-manifest.json")
    shutil.copy2(args.nat_package / "manifest.json", args.output / "nat-package-manifest.json")
    shutil.copy2(args.package / "workload.json", args.output / "trial-workload.json")
    shutil.copy2(args.trial / "verification.json", args.output / "trial-verification.json")
    (args.output / "collision.json").write_text(json.dumps(collision, indent=2) + "\n")
    report = {"outcome": "passed", "goal": "packaged VM-backed Darwin workloads", "package_format": manifest["format"],
              "runtime_version": manifest["version"], "kernel_sha256": digest(args.package / "kernel.macho"),
              "example_package": str(args.example_package.resolve()), "trial_package": str(args.package.resolve()),
              "requirements": trial["passed"] + ["explicit NAT/DHCP entrypoint run with an independent disposable data disk",
                "package integrity, payload/adapter, official-zsh/kernel/loader provenance rechecked without more VMs"],
              "immutable_files_verified": len(manifest["immutable_sha256"]) + len(nat_manifest["immutable_sha256"]),
              "failed_attempts_retained": ["counter-0.3.0-build-failed: external input provenance path handling",
                "workload-state/trial-1: sandbox denial then NIC-required kernel panic; bounded forced stop, not a pass",
                "packaged-workload-trial-1: example used unsupported bootstrap uname -s and unbraced zsh variables; clean exit 2"],
              "limitations": manifest["limitations"],
              "evidence_sha256": {str(path.relative_to(args.output)): digest(path) for path in sorted(args.output.rglob("*")) if path.is_file()}}
    (args.output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": "passed", "report": str(args.output / "verification.json"),
                      "evidence_files": len(report["evidence_sha256"])}, indent=2))


if __name__ == "__main__":
    main()
