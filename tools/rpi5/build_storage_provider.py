#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build explicit experimental built-in Apple storage/HFS provider and config.

Never stage media or boot the board. The final kernel supplies decmpfs itself
with FS_COMPRESSION enabled globally; the compile-screen object is not reused.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from rpi5 import digest, verify_archive
from audit_storage_build import HFS_PATCH, HFS_STARTUP_PATCH, HFS_SERVICE_PATCH, LOCK, COMPRESSION_SCREEN, PI_STORAGE_UNITS, PI_STORAGE_INPUTS
from audit_storage_build import PI_STORAGE_WRITE_UNITS, PI_STORAGE_WRITE_INPUTS

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATCH = ROOT / "tools/rpi5/patches/xnu-storage-config.patch"
MASTER_FILES = ("MASTER", "MASTER.arm64", "MASTER.arm64.bcm2712")


def prepare_config(output_root):
    config = output_root / "storage-config"
    config.mkdir()
    originals = {}
    for filename in MASTER_FILES:
        source = ROOT / "config" / filename
        originals[filename] = digest(source)
        shutil.copyfile(source, config / filename)
    result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-d", str(config),
                             "-i", str(CONFIG_PATCH)], capture_output=True)
    (config / "patch.log").write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("Storage profile patch failed: " + str(config / "patch.log"))
    return {"directory": str(config), "source_sha256": originals,
            "patch_sha256": digest(CONFIG_PATCH),
            "generated_sha256": {name: digest(config / name) for name in MASTER_FILES},
            "requires_fs_compression": True}


def provider_from_screen(manifest, write_trial=False):
    if type(write_trial) is not bool:
        raise RuntimeError('Storage profile selection must be boolean')
    manifest = manifest.resolve()
    if not manifest.is_relative_to((ROOT / "build/rpi5").resolve()):
        raise RuntimeError("Storage screen escaped the isolated build directory")
    report = json.loads(manifest.read_text())
    if report.get('write_trial',False) is not write_trial:
        raise RuntimeError('Storage screen profile does not match requested read-only/write trial')
    pi_units=PI_STORAGE_WRITE_UNITS if write_trial else PI_STORAGE_UNITS
    pi_inputs=PI_STORAGE_WRITE_INPUTS if write_trial else PI_STORAGE_INPUTS
    link = report.get("partial_link") or {}
    if (not report.get("adapted") or not report.get("all_core_units")
            or not report.get("all_screened_units_compiled")
            or link.get("returncode") != 0 or link.get("missing_required_definitions") != []
            or link.get("not_defined_in_reference_kernel") != []
            or link.get("forbidden_profile_definitions", None if write_trial else []) != []):
        raise RuntimeError("Storage screen lacks complete compile/link/provider evidence")
    for path, key in ((LOCK, "lock_sha256"), (HFS_PATCH, "adaptation_patch_sha256"),
                      (HFS_STARTUP_PATCH, "startup_patch_sha256"),
                      (HFS_SERVICE_PATCH, "service_patch_sha256"),
                      (COMPRESSION_SCREEN, "compression_screen_header_sha256")):
        verify_archive(path, report[key])
    run = manifest.parent
    objects = []
    for row in report["results"]:
        source = Path(row["source"]).resolve()
        if digest(source) != row["source_sha256"]:
            raise RuntimeError("Storage source changed after screen: " + str(source))
        # decmpfs is built normally by the final kernel, never duplicated here.
        if row["family"] != "xnu-decmpfs":
            obj = run / (row["unit"] + ".o")
            if not obj.is_file():
                raise RuntimeError("Missing storage object: " + str(obj))
            if not row.get("object_sha256") or digest(obj) != row["object_sha256"]:
                raise RuntimeError("Storage object changed after screen: " + str(obj))
            objects.append(obj)
    pi_rows = [row for row in report['results'] if row['family'] == 'rpi5-storage']
    if (len(pi_rows) != len(pi_units)
            or {row['unit'] for row in pi_rows} != set(pi_units)):
        raise RuntimeError("Storage screen is missing the real Pi storage adapter units")
    inputs=report.get('pi_storage_input_sha256') or {}
    if inputs.keys()!=set(pi_inputs):
        raise RuntimeError("Storage screen lacks Pi source/header provenance")
    for name, expected in inputs.items():
        verify_archive(ROOT / 'iokit/Kernel' / name,expected)
    for row in report['results']:
        if row['family']=='rpi5-storage' and Path(row['source']).resolve()!=ROOT / 'iokit/Kernel' / row['unit']:
            raise RuntimeError("Pi storage source path is not the real adapter")
    output = run / "storage-hfs-provider.o"
    command = ["xcrun", "ld", "-r", "-arch", "arm64", "-o", str(output), *map(str, objects)]
    result = subprocess.run(command, capture_output=True, timeout=60)
    log = run / "provider-link.log"
    log.write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("Storage provider link failed: " + str(log))
    record = {"object": str(output), "object_sha256": digest(output),
              "screen_manifest": str(manifest), "screen_manifest_sha256": digest(manifest),
              "command": command, "log_sha256": digest(log), "input_object_sha256": {
                  str(p): digest(p) for p in objects},
              "requires_fs_compression": True, "write_trial": write_trial,
              "scope": "experimental built-in provider; no final kernel link or hardware/storage proof",
              "warning_policy": report["warning_policy"]}
    record_path = run / "provider.json"
    record_path.write_text(json.dumps(record, indent=2) + "\n")
    return {**record, "manifest": str(record_path), "manifest_sha256": digest(record_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument('--write-trial',action='store_true',help='Build only the distinct write-trial provider')
    args = parser.parse_args()
    result = subprocess.run([sys.executable, str(ROOT / "tools/rpi5/audit_storage_build.py"),
                             "--adapted", "--all-units", *(['--write-trial'] if args.write_trial else [])], cwd=ROOT, text=True,
                            capture_output=True, check=True)
    run = Path(result.stdout.strip().splitlines()[-1])
    record = provider_from_screen(run / "manifest.json", args.write_trial)
    record["configuration"] = prepare_config(args.output_root)
    print(json.dumps(record))


if __name__ == "__main__":
    main()
