#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compile-only integration screen of exact pinned storage sources.

Keeps pristine sources, header overlay, commands and diagnostics under build/.
Does not modify SDKs, link a kernel, invent providers or prove disk access.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

from rpi5 import unpack_archive, verify_archive

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "tools/rpi5/gate4-storage.lock.json"
STORAGE_UNITS = ("IOStorage.cpp", "IOMedia.cpp", "IOBlockStorageDevice.cpp",
                 "IOBlockStorageDriver.cpp", "IOMediaBSDClient.cpp",
                 "IOPartitionScheme.cpp", "IOFDiskPartitionScheme.cpp", "IOGUIDPartitionScheme.cpp")
HFS_UNITS = ("hfs_vfsops.c", "hfs_vnops.c", "hfs_readwrite.c")
HFS_PATCH = ROOT / "tools/rpi5/patches/hfs-builtin-config.patch"
HFS_STARTUP_PATCH = ROOT / "tools/rpi5/patches/hfs-builtin-startup.patch"
HFS_SERVICE_PATCH = ROOT / "tools/rpi5/patches/hfs-builtin-service.patch"
COMPRESSION_SCREEN = ROOT / "tools/rpi5/gate4-compression-screen.h"
PI_STORAGE_UNITS = ("rpi5_sdhci_core.c", "rpi5_sd_handoff.c", "rpi5_sd_contract.c", "BCM2712SDStorage.cpp")
PI_STORAGE_INPUTS = PI_STORAGE_UNITS + ("rpi5_sdhci_core.h", "rpi5_sd_handoff.h", "rpi5_sd_contract.h")
PI_STORAGE_WRITE_UNITS = ("rpi5_sdhci_core.c", "rpi5_sd_handoff.c", "rpi5_sd_contract.c",
                          "rpi5_sd_write_policy.c", "rpi5_sdhci_write.c", "rpi5_sd_transfer.c",
                          "rpi5_sd_memory.cpp", "rpi5_sd_cache.c", "BCM2712SDWriteStorage.cpp")
PI_STORAGE_WRITE_INPUTS = PI_STORAGE_WRITE_UNITS + (
    "rpi5_sdhci_core.h", "rpi5_sd_handoff.h", "rpi5_sd_contract.h", "rpi5_sd_write_policy.h",
    "rpi5_sdhci_write.h", "rpi5_sd_transfer.h", "rpi5_sd_memory.h", "rpi5_sd_cache.h")


def staged_hfs(source, run):
    """Adapt a fresh copy only; never mutate the verified pristine cache."""
    staged = run / "hfs-adapted"
    shutil.copytree(source, staged)
    for patch in (HFS_PATCH, HFS_STARTUP_PATCH, HFS_SERVICE_PATCH):
        result = subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-d", str(staged),
                                 "-i", str(patch)], capture_output=True, check=False)
        log = run / (patch.stem + ".log")
        log.write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError("HFS adaptation failed; see " + str(log))
    return staged


def generate_storage_iig(storage, run, sdk, objroot):
    """Use the actual Apple generator and XNU IIG definitions, not stand-ins."""
    executable = subprocess.check_output(["xcrun", "--find", "iig"], text=True).strip()
    definition = storage / "BlockStorageDeviceDriverKit/IOUserBlockStorageDevice.iig"
    header = run / "include/BlockStorageDeviceDriverKit/IOUserBlockStorageDevice.h"
    header.parent.mkdir()
    impl = run / "IOUserBlockStorageDevice.iig.cpp"
    command = [executable, "--def", str(definition), "--header", str(header),
               "--impl", str(impl), "--framework-name", "BlockStorageDeviceDriverKit", "--",
               "-I", str(ROOT / "iokit"), "-I", str(ROOT / "osfmk"), "-I", str(ROOT / "bsd"),
               "-I", str(objroot / "bsd"), "-isysroot", str(sdk), "-x", "c++", "-std=gnu++2b",
               "-D__IIG=1", "-DDRIVERKIT_PRIVATE=1", "-DPRIVATE_WIFI_ONLY=1",
               "-D__MAC_OS_X_VERSION_MIN_REQUIRED=270000"]
    result = subprocess.run(command, capture_output=True, timeout=60)
    log = run / "iig.log"
    log.write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("Storage IIG generation failed; see " + str(log))
    unqualified = run / "include/IOUserBlockStorageDevice.h"
    shutil.copyfile(header, unqualified)
    return {"command": command, "executable_sha256": hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
            "definition_sha256": hashlib.sha256(definition.read_bytes()).hexdigest(),
            "outputs": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (header, impl, unqualified)},
            "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()}


def source_input(cache, source_root, name, dep):
    archive = cache / (name + ".tar.gz")
    verify_archive(archive, dep["sha256"])
    destination = source_root / name
    if not destination.exists():
        unpack_archive(archive, destination, dep["directory"])
    source = destination / dep["directory"]
    hashes = {}
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            path = Path(member.name)
            if (path.is_absolute() or ".." in path.parts or not path.parts
                    or path.parts[0] != dep["directory"] or not (member.isfile() or member.isdir())):
                raise RuntimeError("Unsafe archive member: " + member.name)
            if not member.isfile():
                continue
            relative = Path(*path.parts[1:])
            actual = source / relative
            if actual.is_symlink() or not actual.is_file() or not actual.resolve().is_relative_to(source.resolve()):
                raise RuntimeError("Unsafe or missing cached source: " + str(actual))
            expected = hashlib.sha256(bundle.extractfile(member).read()).hexdigest()
            if hashlib.sha256(actual.read_bytes()).hexdigest() != expected:
                raise RuntimeError("Cached source differs from pinned archive: " + str(actual))
            hashes[str(relative)] = expected
    actual_files = {str(p.relative_to(source)) for p in source.rglob("*") if p.is_file()}
    if actual_files != hashes.keys():
        raise RuntimeError("Cached source contains unpinned files")
    return source, hashes


def compile_command(template, source, obj, overlay, source_dir, hfs=False, adapted=False):
    arguments = template["arguments"]
    result, i = [], 0
    while i < len(arguments):
        arg = arguments[i]
        if arg in ("-o", "-MF", "-MT", "-MQ"):
            i += 2
            continue
        if arg in ("-MMD", "-MD", "-MP"):
            i += 1
            continue
        result.append(str(source) if arg == template["file"] else arg)
        i += 1
    # This is a pristine-upstream compatibility screen, not the final kernel
    # warning policy. Keep all warnings in logs while surfacing semantic errors.
    result += ["-I", str(overlay), "-I", str(source_dir), "-Wno-error", "-o", str(obj)]
    if hfs:
        result += ["-include", str(source_dir / "kext-config.h")]
        if adapted:
            # BSDKernel.exports aliases the external KPI to this real wrapper.
            # Built-in translation units see its native name in sys/ubc.h.
            result += ["-DRPI5_HFS_BUILTIN=1", "-Dubc_create_upl=ubc_create_upl_external"]
    return result


def symbol_set(path, undefined=False):
    # -g would omit private-extern built-in providers such as startup helpers.
    return set(subprocess.check_output(["xcrun", "nm", "-ju" if undefined else "-jU", str(path)],
                                       text=True).splitlines())


def link_screen(run, results, kernel, write_trial=False):
    """Resolve cross-family references without pretending this is a kernel link."""
    output = run / "storage-hfs-partial.o"
    objects = [run / (row["unit"] + ".o") for row in results]
    command = ["xcrun", "ld", "-r", "-arch", "arm64", "-o", str(output), *map(str, objects)]
    result = subprocess.run(command, capture_output=True, timeout=60)
    log = run / "partial-link.log"
    log.write_bytes(result.stdout + result.stderr)
    report = {"command": command, "returncode": result.returncode,
              "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
              "scope": "relocatable link and symbol inventory; not a final kernel link or ABI/runtime proof"}
    if result.returncode == 0:
        report["object"] = str(output)
        report["object_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
        unresolved = symbol_set(output, undefined=True)
        report["undefined_symbols"] = sorted(unresolved)
        report["kernel"] = str(kernel)
        report["kernel_sha256"] = hashlib.sha256(kernel.read_bytes()).hexdigest()
        report["not_defined_in_reference_kernel"] = sorted(unresolved - symbol_set(kernel))
        definitions = symbol_set(output)
        required = {"_decmpfs_init", "_decmpfs_cnode_alloc", "_decmpfs_read_compressed",
                    "_hfs_vfsops", "_hfs_getencodingbias", "_hfs_setencodingbias", "_hfs_pickencoding",
                    "__ZN7IOMedia10gMetaClassE", "__ZN20IOBlockStorageDriver10gMetaClassE",
                    "_rpi5_sd_start", "_rpi5_sd_read_sector",
                    "_rpi5_sd_handoff", "_rpi5_sd_binding_decode"}
        required.add("__ZN21BCM2712SDWriteStorage10gMetaClassE" if write_trial else
                     "__ZN16BCM2712SDStorage10gMetaClassE")
        if write_trial:
            required.update(("_rpi5_sd_start_identified", "_rpi5_sd_write_authorize", "_rpi5_sd_write_sector",
                             "_rpi5_sd_write_wait_ready", "_rpi5_sd_cache_probe", "_rpi5_sd_cache_probe_traced", "_rpi5_sd_transfer"))
            forbidden={"__ZN16BCM2712SDStorage10gMetaClassE"}
        else:
            forbidden={"__ZN21BCM2712SDWriteStorage10gMetaClassE", "_rpi5_sd_write_sector"}
        report["forbidden_profile_definitions"] = sorted(forbidden & definitions)
        report["missing_required_definitions"] = sorted(required - definitions)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "build/rpi5/gate4-reference")
    parser.add_argument("--sources", type=Path, default=ROOT / "build/rpi5/gate4-sources")
    parser.add_argument("--kernel-commands", type=Path, default=ROOT /
                        "build/rpi5-xcode27/obj/DEVELOPMENT_ARM64_BCM2712/compile_commands.json")
    parser.add_argument("--adapted", action="store_true", help="Apply reviewed built-in HFS configuration to a fresh copy")
    parser.add_argument("--all-units", action="store_true", help="Compile all root kernel-storage and HFS core units")
    parser.add_argument("--write-trial", action="store_true", help="Distinct bounded-write adapter; never stage or boot")
    parser.add_argument("--reference-kernel", type=Path, default=ROOT /
                        "build/rpi5/shell-userland-20261011/kernel.development.bcm2712")
    args = parser.parse_args()
    if args.write_trial and not (args.adapted and args.all_units):
        parser.error('--write-trial requires --adapted --all-units')
    pi_units=PI_STORAGE_WRITE_UNITS if args.write_trial else PI_STORAGE_UNITS
    pi_inputs=PI_STORAGE_WRITE_INPUTS if args.write_trial else PI_STORAGE_INPUTS
    lock = json.loads(LOCK.read_text())
    release = args.cache / "release-macos265.json"
    verify_archive(release, lock["distribution"]["release_sha256"])
    # Pinned manifest and input lock must agree, including the XNU version.
    distribution = json.loads(release.read_text())
    projects = {p["project"]: p["tag"] for p in distribution["projects"]}
    if projects["xnu"] != lock["distribution"]["xnu_tag"]:
        raise RuntimeError("Distribution XNU mismatch")
    prepared, inputs = {}, {}
    for name, dep in lock["dependencies"].items():
        if projects[name] != dep["tag"]:
            raise RuntimeError("Distribution storage dependency mismatch")
        prepared[name], inputs[name] = source_input(args.cache, args.sources, name, dep)
    commands = json.loads(args.kernel_commands.read_text())
    cpp = next(row for row in commands if row["file"].endswith("/iokit/Kernel/IOCPU.cpp"))
    c = next(row for row in commands if row["file"].endswith("/bsd/dev/memdev.c"))
    run = Path(tempfile.mkdtemp(prefix="gate4-build-audit-", dir=ROOT / "build/rpi5"))
    overlay = run / "include/IOKit/storage"
    overlay.mkdir(parents=True)
    for header in prepared["IOStorageFamily"].glob("*.h"):
        shutil.copyfile(header, overlay / header.name)
    sdk = ROOT / "build/rpi5-xcode27/sdk/MacOSX27.0.sdk"
    sdk_headers = sdk / "usr/include"
    public_header_hashes = {}
    for name in ("TargetConditionals.h", "AssertMacros.h"):
        header = sdk_headers / name
        public_header_hashes[name] = hashlib.sha256(header.read_bytes()).hexdigest()
        shutil.copyfile(header, run / "include" / name)
    generated = generate_storage_iig(prepared["IOStorageFamily"], run, sdk, args.kernel_commands.parent)
    if args.adapted:
        prepared["hfs"] = staged_hfs(prepared["hfs"], run)
    storage_units, hfs_units = STORAGE_UNITS, HFS_UNITS
    if args.all_units:
        storage_units = tuple(p.name for p in sorted(prepared["IOStorageFamily"].glob("*.cpp")))
        hfs_units = tuple(p.name for p in sorted((prepared["hfs"] / "core").glob("*"))
                          if p.suffix in (".c", ".cpp"))
    groups = [("IOStorageFamily", prepared["IOStorageFamily"], storage_units),
              ("hfs", prepared["hfs"] / "core", hfs_units)]
    if args.all_units:
        groups += [("hfs-encodings", prepared["hfs"] / "hfs_encodings",
                    ("hfs_encodings.c", "hfs_encodinghint.c", "hfs_encodings_kext.cpp")),
                   ("xnu-decmpfs", ROOT / "bsd/kern", ("decmpfs.c",)),
                   ("rpi5-storage", ROOT / "iokit/Kernel", pi_units)]
    results = []
    for family, directory, units in groups:
        if family == "IOStorageFamily" and args.all_units:
            units += ("IOUserBlockStorageDevice.iig.cpp",)
        for unit in units:
            template = cpp if unit.endswith(".cpp") else c
            source = run / unit if unit.endswith(".iig.cpp") else directory / unit
            command = compile_command(template, source, run / (unit + ".o"),
                                      run / "include", prepared["hfs"] / "core" if family.startswith("hfs") else directory,
                                      hfs=family.startswith("hfs"), adapted=args.adapted)
            if family.startswith("hfs") and args.adapted:
                command += ["-I", str(args.kernel_commands.parent / "bsd/DEVELOPMENT")]
            if family == "hfs-encodings" and args.adapted:
                # These normally independent kexts own independent allocation
                # counters. Preserve that ownership when linking them built-in.
                command += ["-Dhfs_allocated=rpi5_hfs_encodings_allocated"]
            if family == "xnu-decmpfs":
                # The final storage kernel must enable FS_COMPRESSION globally;
                # this isolated compile closes the real provider, not zero aliases.
                command += ["-include", str(COMPRESSION_SCREEN)]
            if family == "rpi5-storage":
                command += ["-DRPI5_STORAGE_PROVIDER=1", "-Werror"]
                if args.write_trial:
                    command += ["-DRPI5_STORAGE_WRITE_PROVIDER=1"]
            result = subprocess.run(command, cwd=template["directory"], capture_output=True, timeout=60)
            log = run / (unit + ".log")
            log.write_bytes(result.stdout + result.stderr)
            results.append({"unit": unit, "family": family, "command": command,
                            "source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                            "object_sha256": hashlib.sha256((run / (unit + ".o")).read_bytes()).hexdigest() if result.returncode == 0 else None,
                            "directory": template["directory"], "returncode": result.returncode,
                            "log": str(log), "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()})
            print(unit, "COMPILED" if result.returncode == 0 else "INCOMPLETE", flush=True)
    linked = link_screen(run, results, args.reference_kernel, args.write_trial) if args.all_units and all(r["returncode"] == 0 for r in results) else None
    report = {"scope": "compile and optional relocatable-link integration screen; no final kernel link, board boot, mount or disk writes",
              "lock_sha256": hashlib.sha256(LOCK.read_bytes()).hexdigest(),
              "kernel_commands_sha256": hashlib.sha256(args.kernel_commands.read_bytes()).hexdigest(),
              "public_sdk_header_hashes": public_header_hashes,
              "generated_storage_iig": generated,
              "adapted": args.adapted, "all_core_units": args.all_units, "write_trial": args.write_trial,
              "adaptation_patch_sha256": hashlib.sha256(HFS_PATCH.read_bytes()).hexdigest() if args.adapted else None,
              "startup_patch_sha256": hashlib.sha256(HFS_STARTUP_PATCH.read_bytes()).hexdigest() if args.adapted else None,
              "service_patch_sha256": hashlib.sha256(HFS_SERVICE_PATCH.read_bytes()).hexdigest() if args.adapted else None,
              "adapted_source_hashes": {str(p.relative_to(prepared["hfs"])): hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in prepared["hfs"].rglob("*") if p.is_file()} if args.adapted else None,
              "warning_policy": "warnings recorded, not errors, for pristine-upstream compile-only compatibility screen",
              "pristine_source_hashes": inputs, "results": results,
              "pi_storage_input_sha256": {name: hashlib.sha256((ROOT / 'iokit/Kernel' / name).read_bytes()).hexdigest()
                                        for name in pi_inputs} if args.all_units else None,
              "partial_link": linked,
              "requires_final_kernel_fs_compression": args.all_units,
              "compression_screen_header_sha256": hashlib.sha256(COMPRESSION_SCREEN.read_bytes()).hexdigest() if args.all_units else None,
              "all_screened_units_compiled": all(r["returncode"] == 0 for r in results),
              "gate4_achieved": False}
    (run / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(run)


if __name__ == "__main__":
    main()
