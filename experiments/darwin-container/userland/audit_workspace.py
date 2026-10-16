#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Recheck workspace completion from preserved actual runs, without booting again."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil

from workspace_launcher import digest, validate_package

HERE = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    trial = json.loads((args.trial / "verification.json").read_text())
    require(trial["error"] is None and len(trial["workspace_runs"]) == 2, "two successful launcher runs required")
    package = Path(trial["package"])
    manifest = validate_package(package)
    require(digest(package / "manifest.json") == trial["package_manifest_sha256"], "package changed after actual trial")
    require(digest(HERE / "workspace_launcher.py") == manifest["immutable_sha256"]["darwin"], "packaged launcher differs from current source")
    kernel_record = json.loads((package / "provenance/kernel-build.json").read_text())
    root_record = json.loads((package / "provenance/root-build.json").read_text())
    loader_record = json.loads((package / "provenance/loader-build.json").read_text())
    require(kernel_record["exit_code"] == 0 and kernel_record["network_profile"] and kernel_record["storage_profile"], "kernel profile/build incomplete")
    require(digest(package / "kernel.macho") == loader_record["inputs"]["kernelSHA256"], "loader kernel provenance mismatch")
    require(digest(package / "ramdisk.bin") == root_record["sha256"] == loader_record["inputs"]["ramrootSHA256"], "root provenance mismatch")
    seed_source = package / "provenance/prng_random.c"
    require("cc_clear(sizeof(native_rand), native_rand);" in seed_source.read_text(), "seed clearing fix missing")
    require(digest(seed_source) == kernel_record["effective_source_sha256"]["osfmk/prng/prng_random.c"], "seed fix not part of kernel build inputs")
    for name, expected in root_record["source_inputs_sha256"].items():
        require(digest(HERE / name) == expected, f"root source changed after build: {name}")
    for name, expected in loader_record["sources"].items():
        if name != "payload.S":
            require(digest(HERE.parents[2] / name) == expected, f"loader source changed after build: {name}")
    runs = [Path(path) for path in trial["workspace_runs"]]
    require(runs[0].parents[1] == runs[1].parents[1], "restart used a different named workspace")
    captures, seeds = [], []
    fixture = trial["network_fixture"]
    require(not fixture["errors"] and sorted(event["type"] for event in fixture["events"]) == ["dns", "tcp"], "independent DNS/TCP observations missing")
    for index, run in enumerate(runs):
        result = json.loads((run / "session/result.json").read_text())
        terminal = result["terminal"]
        require(result["guestStopped"] and result["termination"] == "guestStopped" and not result.get("error") and
                terminal["handshakeCompleted"] and terminal["exitStatus"] == 0 and not terminal.get("error"), "run did not reach normal terminal/guest exit")
        serial = (run / "session/serial.bin").read_bytes().replace(b"\r", b"")
        require(b"DARWIN:WORKSPACE:NETWORK_READY\n" in serial, "automatic network completion absent")
        lease = re.search(rb"DARWIN:NET:DHCP IP=([0-9.]+) MASK=([0-9.]+) ROUTER=([0-9.]+) DNS=([0-9.]+)", serial)
        require(lease is not None, "real lease missing")
        capture = (run / "session/terminal-output.bin").read_bytes()
        require(b"\r\nWS_READY:ready:5.9:/data:/data\r\n" in capture, "real guest readiness output missing")
        launch = json.loads((run / "launch.json").read_text())
        require(digest(run / "boot.img") == launch["boot_sha256"], "actual boot image changed")
        require("--variable-store" not in launch["command"], "workspace reused firmware variable template")
        with (run / "boot.img").open("rb") as image:
            image.seek(manifest["boot_entropy_slot"]["diskOffset"])
            seeds.append(image.read(256))
        if index == 0:
            require(b"\r\nWS_WRITE:0\r\n" in capture and b"\r\nWS_INTERRUPT:130\r\n" in capture, "initial write or foreground interrupt proof missing")
            require(b"\r\nWS_TCP:0\r\n" in capture, "guest network command failed")
            require(all(event["guest"] == lease[1].decode() for event in fixture["events"]), "network witness is not this guest")
            echo = next(event["echo"] for event in fixture["events"] if event["type"] == "tcp")
            require(f"\r\nDARWIN:NET:APPLE_GAI_TCP ECHO={echo}\r\n".encode() in capture, "guest/host TCP tokens differ")
        else:
            require(b"\r\nWS_RESTORED:0\r\n" in capture, "saved file and history were not restored")
        captures.append(capture)
    require(all(any(seed) and len(seed) == 256 for seed in seeds) and seeds[0] != seeds[1], "seed reuse or invalid entropy")
    slot = manifest["boot_entropy_slot"]
    with (package / "efi-template.img").open("rb") as image:
        image.seek(slot["diskOffset"])
        require(image.read(256) == bytes(256), "immutable template contains provisioned entropy")
    workspace = runs[0].parents[1]
    metadata = json.loads((workspace / "workspace.json").read_text())
    require(metadata["last_outcome"] == "clean-shutdown" and metadata["last_exit_code"] == 0, "workspace outcome is not clean")
    descriptor = os.open(workspace / "workspace.lock", os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(descriptor)
    baseline = HERE / "build/apple-ifconfig-working-2026-10-12"
    baseline_record = json.loads((baseline / "manifest.json").read_text())
    require(all(digest(baseline / name) == expected for name, expected in baseline_record["sha256"].items()), "original checkpoint changed")
    frozen = HERE / "build/darwin-workload-0.1.0"
    frozen_manifest = json.loads((frozen / "manifest.json").read_text())
    require(all(digest(frozen / name) == expected for name, expected in frozen_manifest["immutable_sha256"].items()), "frozen workload changed")
    output = args.output.absolute()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    shutil.copy2(args.trial / "verification.json", output / "verification.json")
    for index, run in enumerate(runs, 1):
        destination = output / f"boot-{index}"
        destination.mkdir()
        for path in (run / "session").iterdir():
            if path.is_file() and path.name != "efi-variables.bin":
                shutil.copy2(path, destination / path.name)
        for name in ("launch.json", "trial-terminal.bin"):
            shutil.copy2(run / name, destination / name)
    completion = {"status": "complete", "scope": "persistent named Darwin workspace on the current Apple-silicon Mac",
        "package_manifest_sha256": digest(package / "manifest.json"), "package_sha256": manifest["immutable_sha256"],
        "evidence_sha256": {str(path.relative_to(output)): digest(path) for path in output.rglob("*") if path.is_file()},
        "current_source_sha256": {name: digest(HERE / name) for name in
            ("workspace_launcher.py", "package_workspace.py", "workspace_trial.py", "audit_workspace.py", "build.py", "src/init.c")},
        "requirements_verified": trial["passed"], "fresh_entropy_across_actual_boots": True,
        "seed_clear_fix_in_compiled_snapshot": True, "baseline_checkpoint_hashes_preserved": len(baseline_record["sha256"]),
        "frozen_workload_hashes_preserved": len(frozen_manifest["immutable_sha256"]),
        "limitations": manifest["limitations"], "verification": "existing two successful boot records rechecked; no new VM boot"}
    (output / "completion.json").write_text(json.dumps(completion, indent=2) + "\n")
    print(json.dumps({"status": completion["status"], "evidence_files": len(completion["evidence_sha256"]),
                      "preserved_frozen_hashes": completion["frozen_workload_hashes_preserved"], "output": str(output)}))


if __name__ == "__main__":
    main()
