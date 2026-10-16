#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Check four unstaged standalone Gate 3 packages share one exact kernel."""

import argparse
import hashlib
import json
from pathlib import Path
import re


ROLES = {
    "inventory": "gate3_xnupost_inventory",
    "concurrency": "gate3_concurrency_trial",
    "kernel_tlb": "gate3_tlb_trial",
    "user_tlb": "gate3_user_tlb_trial",
}
EXCLUSIVE = tuple(ROLES.values())
HEX256 = re.compile(r"[0-9a-f]{64}\Z")
ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect(packages: dict[str, Path], kernel: Path | None = None,
            init: Path | None = None) -> dict:
    reports = {}
    kernel_hashes = set()
    init_hashes = set()
    for role, flag in ROLES.items():
        directory = packages[role]
        manifest = json.loads((directory / "manifest.json").read_text())
        image = directory / "probe.bin"
        digest = sha256(image)
        recorded = [value for name, value in manifest.get("sha256", {}).items()
                    if (Path(name) if Path(name).is_absolute() else ROOT / name).resolve()
                    == image.resolve()]
        kernel_hash = manifest.get("embedded_kernel", {}).get("sha256")
        init_hash = manifest.get("embedded_init", {}).get("sha256")
        checks = {
            "image_hash_matches_manifest": len(recorded) == 1 and recorded[0] == digest,
            "kernel_hash_format": isinstance(kernel_hash, str) and bool(HEX256.fullmatch(kernel_hash)),
            "init_hash_format": isinstance(init_hash, str) and bool(HEX256.fullmatch(init_hash)),
            "transfer_and_four_cpus": manifest.get("xnu_transfer_enabled") is True and
                manifest.get("gate3_cpu_on_all") is True,
            "exactly_intended_trial": all(manifest.get(name) is (name == flag)
                                          for name in EXCLUSIVE),
            "no_other_selector": all(name in manifest and not manifest[name] for name in (
                "gate3_register_cpus", "gate3_register_boot_cpu", "gate3_cpu_on_1",
                "gate3_xnupost_index", "gate3_xnupost_config",
                "gate3_qualification_config", "gate3_soak_seconds")),
        }
        if isinstance(kernel_hash, str):
            kernel_hashes.add(kernel_hash)
        if isinstance(init_hash, str):
            init_hashes.add(init_hash)
        reports[role] = {"image": str(image), "sha256": digest,
                         "kernel_sha256": kernel_hash, "init_sha256": init_hash,
                         "checks": checks}
    checks = {
        "one_kernel": len(kernel_hashes) == 1,
        "one_init": len(init_hashes) == 1,
        "distinct_images": len({item["sha256"] for item in reports.values()}) == len(ROLES),
        "kernel_file_matches": kernel is None or
            (len(kernel_hashes) == 1 and sha256(kernel) in kernel_hashes),
        "init_file_matches": init is None or
            (len(init_hashes) == 1 and sha256(init) in init_hashes),
        "each_package_valid": all(all(item["checks"].values()) for item in reports.values()),
    }
    return {"packages": reports, "checks": checks,
            "package_set_pass": all(checks.values()),
            "scope": "host package identity only; no board placement, boot or runtime proof"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for role in ROLES:
        parser.add_argument("--" + role.replace("_", "-"), required=True, type=Path)
    parser.add_argument("--kernel", type=Path)
    parser.add_argument("--init", type=Path)
    args = parser.parse_args()
    packages = {role: getattr(args, role) for role in ROLES}
    report = inspect(packages, args.kernel, args.init)
    print(json.dumps(report, indent=2))
    if not report["package_set_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
