#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Package a new workspace profile, retaining its source/build provenance."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from workspace_launcher import digest

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-build", required=True, type=Path)
    parser.add_argument("--root-build", required=True, type=Path)
    parser.add_argument("--loader-build", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", default="0.2.0")
    args = parser.parse_args()
    baseline = HERE / "build/apple-ifconfig-working-2026-10-12"
    baseline_record = json.loads((baseline / "manifest.json").read_text())
    cli = baseline / "container"
    if digest(cli) != baseline_record["sha256"]["container"]:
        raise RuntimeError("qualified host CLI changed")
    kernel_record = json.loads((args.kernel_build / "manifest.json").read_text())
    root_record = json.loads((args.root_build / "manifest.json").read_text())
    loader_record = json.loads((args.loader_build / "manifest.json").read_text())
    kernel = args.kernel_build / "obj/DEVELOPMENT_ARM64_VZGENERIC/kernel.development.vzgeneric"
    root = args.root_build / "ramdisk.bin"
    root_nodes = root_record.get("ramroot_max_nodes", 32)
    if root_nodes != kernel_record.get("ramroot_max_nodes", 32):
        raise RuntimeError("RAM-root capacity does not match compiled VM kernel")
    if root_nodes != 32:
        format_header = args.kernel_build / "source/bsd/miscfs/mockfs/rpi5_ramroot_format.h"
        if (f"#define RPI5_RFS_NODES {root_nodes}u" not in format_header.read_text() or
                kernel_record["effective_source_sha256"]["bsd/miscfs/mockfs/rpi5_ramroot_format.h"] != digest(format_header)):
            raise RuntimeError("enlarged RAM-root profile was not compiled")
    if kernel_record.get("exit_code") != 0 or not kernel_record.get("network_profile") or not kernel_record.get("storage_profile"):
        raise RuntimeError("requires a completed storage/network VM kernel")
    if not any(item["sha256"] == digest(kernel) for item in kernel_record["kernels"]):
        raise RuntimeError("kernel differs from its successful build")
    if not all(root_record.get(key) for key in ("automatic_network", "writable_storage", "pty_relay", "framed_terminal")):
        raise RuntimeError("requires the automatic-network PTY workspace root")
    if loader_record["inputs"]["kernelSHA256"] != digest(kernel) or loader_record["inputs"]["ramrootSHA256"] != digest(root):
        raise RuntimeError("loader/kernel/root mismatch")
    seed_fix = args.kernel_build / "source/osfmk/prng/prng_random.c"
    if "cc_clear(sizeof(native_rand), native_rand);" not in seed_fix.read_text():
        raise RuntimeError("workspace kernel lacks the seed clearing fix")
    if kernel_record["effective_source_sha256"]["osfmk/prng/prng_random.c"] != digest(seed_fix):
        raise RuntimeError("seed fix was not included in the compiled source record")
    image = bytearray((args.loader_build / "efi.img").read_bytes())
    payload = bytearray((args.loader_build / "BOOTAA64.EFI").read_bytes())
    if digest(args.loader_build / "BOOTAA64.EFI") != loader_record["payloadSHA256"]:
        raise RuntimeError("EFI payload changed")
    slot = loader_record["bootEntropySlot"]
    offset, payload_offset, count = slot["diskOffset"], slot["payloadOffset"], slot["bytes"]
    if count != 256 or not 0 <= payload_offset <= len(payload) - count or not 0 <= offset <= len(image) - count:
        raise RuntimeError("invalid bounded entropy slot")
    start = offset - payload_offset
    if start < 0 or image[start:start + len(payload)] != payload:
        raise RuntimeError("disk does not contain the recorded contiguous EFI payload")
    image[offset:offset + count] = bytes(count)
    payload[payload_offset:payload_offset + count] = bytes(count)
    output = args.output.absolute()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (output / "efi-template.img").write_bytes(image)
    (output / "loader-template.efi").write_bytes(payload)
    copies = {cli: "container", kernel: "kernel.macho", root: "ramdisk.bin",
              HERE / "workspace_launcher.py": "darwin",
              args.kernel_build / "manifest.json": "provenance/kernel-build.json",
              seed_fix: "provenance/prng_random.c",
              args.root_build / "manifest.json": "provenance/root-build.json",
              args.loader_build / "manifest.json": "provenance/loader-build.json",
              HERE / "apple-runtime.sources.lock.json": "provenance/apple-runtime.sources.lock.json",
              HERE / "apple-network.sources.lock.json": "provenance/apple-network.sources.lock.json",
              HERE / "apple-zsh-source.json": "provenance/apple-zsh-source.json"}
    utilities = root_record.get("apple_utilities")
    if utilities:
        utility_manifest = Path(utilities["manifest"])
        if digest(utility_manifest) != utilities["manifest_sha256"]:
            raise RuntimeError("utility build manifest changed")
        copies[utility_manifest] = "provenance/apple-utilities-build.json"
        for name in ("source-bundle.tar.gz", "NOTICES.txt"):
            origin = utility_manifest.parent / name
            utility_record = json.loads(utility_manifest.read_text())
            if digest(origin) != utility_record["distribution_sha256"][name]:
                raise RuntimeError("utility source/notices drift")
            copies[origin] = "provenance/apple-utilities/" + name
    for source, relative in copies.items():
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        expected = digest(source)
        shutil.copy2(source, destination)
        if digest(source) != expected or digest(destination) != expected:
            raise RuntimeError(f"source changed during packaging: {source}")
    subprocess.run([sys.executable, str(HERE / "create_data_disk.py"), str(output / "data-template.raw")], check=True)
    for path in output.rglob("*"):
        if path.is_file():
            path.chmod(0o700 if path.name in ("darwin", "container") else 0o600)
    manifest = {"format": "darwin-workspace-1", "version": args.version, "boot_entropy_slot": slot,
        "ramroot_max_nodes": root_nodes, "apple_utilities": utilities,
        "data_bytes": (output / "data-template.raw").stat().st_size,
        "immutable_sha256": {str(path.relative_to(output)): digest(path) for path in sorted(output.rglob("*")) if path.is_file()},
        "scope": "experimental named Mac-hosted XNU workspace; official Apple-source zsh and network commands",
        "entropy": "template slot is zero; launcher fills from host os.urandom before each boot; loader rejects zero slot",
        "limitations": ["one vCPU; static runtime; bounded one-hour foreground session",
                        "DHCP acquisition at boot, no renewal service", "clean restart persistence; no power-loss claim",
                        "Metal compute is opt-in and limited to the existing typed API", "not production isolation"]}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"package": str(output), "version": manifest["version"], "immutable_files": len(manifest["immutable_sha256"])}))


if __name__ == "__main__":
    main()
