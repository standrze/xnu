#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build a separate VZ virtio-block + pinned Apple IOStorageFamily/HFS provider.

Reuses only source verification/build adaptation helpers, never Pi transport
objects, media, source edits, or installed services. Generated files are local.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools/rpi5"))
from audit_storage_build import source_input, staged_hfs, compile_command, generate_storage_iig
from audit_storage_build import LOCK, HFS_PATCH, HFS_STARTUP_PATCH, HFS_SERVICE_PATCH


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-commands", required=True, type=Path)
    args = parser.parse_args()
    args.kernel_commands = args.kernel_commands.resolve()
    commands = json.loads(args.kernel_commands.read_text())
    cpp = next(c for c in commands if c["file"].endswith("/iokit/Kernel/IOCPU.cpp"))
    c = next(c for c in commands if c["file"].endswith("/bsd/dev/memdev.c"))
    if not all("VZGENERIC" in " ".join(t["arguments"]) for t in (cpp, c)):
        raise ValueError("requires real VZGENERIC compilation commands")
    run = Path(tempfile.mkdtemp(prefix="vzstorage-", dir=HERE / "build"))
    print(f"RUN={run}", flush=True)
    lock = json.loads(LOCK.read_text())
    prepared, hashes = {}, {}
    for name, dependency in lock["dependencies"].items():
        prepared[name], hashes[name] = source_input(ROOT / "build/rpi5/gate4-reference",
            ROOT / "build/rpi5/gate4-sources", name, dependency)
    storage = prepared["IOStorageFamily"]
    include = run / "include"
    (include / "IOKit/storage").mkdir(parents=True)
    for header in storage.glob("*.h"):
        shutil.copy2(header, include / "IOKit/storage" / header.name)
    sdk = ROOT / "build/rpi5-xcode27/sdk/MacOSX27.0.sdk"
    for name in ("TargetConditionals.h", "AssertMacros.h"):
        shutil.copy2(sdk / "usr/include" / name, include / name)
    generated = generate_storage_iig(storage, run, sdk, args.kernel_commands.parent)
    hfs = staged_hfs(prepared["hfs"], run)
    fortify = HERE / "hfs-fortify.patch"
    result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-d", str(hfs), "-i", str(fortify)], capture_output=True)
    (run / "hfs-fortify.log").write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("HFS subobject-safe copy adaptation failed")
    # Adapt the fresh service copy for this VM; original patches remain intact.
    for path in hfs.rglob("*"):
        if path.is_file() and path.suffix in (".h", ".c", ".cpp"):
            text = path.read_bytes()
            changed = text.replace(b'"bcm2712_hfs"', b'"vz_hfs"').replace(b"RPI5XNU:HFS:", b"VZXNU:HFS:")
            changed = changed.replace(b"RPI5HFSEncodingsReady", b"VZHFSEncodingsReady").replace(b"RPI5HFSRegistered", b"VZHFSRegistered")
            if changed != text:
                path.write_bytes(changed)
    groups = [("IOStorageFamily", storage, sorted(storage.glob("*.cpp")) + [run / "IOUserBlockStorageDevice.iig.cpp"]),
              ("hfs", hfs / "core", sorted(p for p in (hfs / "core").iterdir() if p.suffix in (".c", ".cpp"))),
              ("hfs-encodings", hfs / "core", [hfs / "hfs_encodings" / n for n in
                  ("hfs_encodings.c", "hfs_encodinghint.c", "hfs_encodings_kext.cpp")]),
              ("vz-transport", ROOT / "loader/vz", [HERE / "overlay/iokit/Kernel/VZBlockStorage.cpp", ROOT / "loader/vz/virtio_block.c"])]
    results = []
    for family, directory, units in groups:
        for source in units:
            template = cpp if source.suffix == ".cpp" else c
            obj = run / (source.name + ".o")
            command = compile_command(template, source, obj, include, directory,
                                      hfs=family.startswith("hfs"), adapted=True)
            command += ["-include", str(HERE / "storage-configuration.h"), "-I", str(args.kernel_commands.parent / "bsd/DEVELOPMENT")]
            if family == "hfs-encodings":
                command += ["-Dhfs_allocated=rpi5_hfs_encodings_allocated"]
            result = subprocess.run(command, cwd=template["directory"], capture_output=True, timeout=60)
            log = run / (source.name + ".log")
            log.write_bytes(result.stdout + result.stderr)
            results.append({"family": family, "source": str(source), "source_sha256": digest(source),
                "command": command, "directory": template["directory"], "returncode": result.returncode,
                "object": str(obj), "object_sha256": digest(obj) if result.returncode == 0 else None,
                "log": str(log), "log_sha256": digest(log)})
            print(source.name, result.returncode, flush=True)
    record = {"scope": "VZ-specific source-built storage provider; no mount/persistence proof",
        "kernel_commands_sha256": digest(args.kernel_commands), "lock_sha256": digest(LOCK),
        "upstream": lock, "pristine_source_sha256": hashes, "generated_iig": generated,
        "adaptation_sha256": {str(p): digest(p) for p in (HFS_PATCH, HFS_STARTUP_PATCH, HFS_SERVICE_PATCH, fortify, HERE / "storage-configuration.h")},
        "adapted_source_sha256": {str(p.relative_to(hfs)): digest(p) for p in hfs.rglob("*") if p.is_file()},
        "results": results, "all_compiled": all(r["returncode"] == 0 for r in results)}
    if record["all_compiled"]:
        output = run / "vz-storage-provider.o"
        command = ["xcrun", "ld", "-r", "-arch", "arm64", "-o", str(output), *[r["object"] for r in results]]
        result = subprocess.run(command, capture_output=True)
        (run / "link.log").write_bytes(result.stdout + result.stderr)
        record["link"] = {"command": command, "returncode": result.returncode}
        if result.returncode == 0:
            record.update(object=str(output), object_sha256=digest(output))
    (run / "manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    print(run / "manifest.json", flush=True)
    return 0 if record.get("object") else 1


if __name__ == "__main__":
    raise SystemExit(main())
