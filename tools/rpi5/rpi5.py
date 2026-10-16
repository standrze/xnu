#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Gate 0 tooling. Generated files stay under build/rpi5; no system installs."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import shlex
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build/rpi5"
LOCK_PATH = ROOT / "tools/rpi5/inputs.lock.json"
EXPLORATORY_XCODE27 = {"xcode": "27.0", "xcode_build": "27A266a", "sdk": "27.0"}


def select_profile(profile):
    """Keep exploratory SDK, dependencies, and outputs away from Gate 1 evidence."""
    if profile == "canonical":
        return ROOT / "build/rpi5"
    if profile == "xcode27":
        return ROOT / "build/rpi5-xcode27"
    raise ValueError(f"Unknown build profile: {profile}")


def capture(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def reproducible_metadata(epoch):
    """Stable version metadata; this alone does not establish reproducibility."""
    if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 0:
        raise ValueError('Build epoch must be a nonnegative integer')
    date = datetime.fromtimestamp(epoch, timezone.utc)
    return {'KERNEL_BUILD_DATE': date.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'KERNEL_BUILD_OBJROOT': 'xnu/DEVELOPMENT_ARM64_BCM2712'}


def verify_archive(path, expected):
    actual = digest(path)
    if actual != expected:
        raise RuntimeError(f"SHA-256 mismatch for {path}: {actual}; expected {expected}")


def clone_sdk(source, destination):
    # Versioned Xcode SDK names can themselves be symlinks to MacOSX.sdk.
    # Resolve that top-level link, preserving only links within the copied tree.
    subprocess.run(["cp", "-cR", str(Path(source).resolve(strict=True)),
                    str(destination)], check=True)


def unpack_archive(archive, destination, directory):
    """Reject links, special files and paths outside the expected archive root."""
    destination = Path(destination)
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        for member in members:
            path = Path(member.name)
            if (path.is_absolute() or ".." in path.parts or not path.parts
                    or path.parts[0] != directory
                    or not (member.isfile() or member.isdir())):
                raise RuntimeError(f"Unsafe archive entry: {member.name}")
        # Extract into a new directory, so preexisting symlinks cannot redirect writes.
        if destination.exists():
            raise RuntimeError(f"Extraction destination already exists: {destination}")
        destination.mkdir(parents=True)
        bundle.extractall(destination, members=members, filter="data")


def toolchain(lock, allow_mismatch, profile="canonical"):
    if platform.system() != "Darwin":
        raise RuntimeError("The Gate 0 build currently requires macOS and Xcode")
    lines = capture("xcodebuild", "-version").splitlines()
    result = {
        "xcode": lines[0].removeprefix("Xcode "),
        "xcode_build": lines[1].removeprefix("Build version "),
        "sdk": capture("xcrun", "--sdk", "macosx", "--show-sdk-version"),
        "sdk_path": capture("xcrun", "--sdk", "macosx", "--show-sdk-path"),
        "compiler": capture("xcrun", "clang", "--version"),
        "host": platform.platform(),
    }
    mismatch = {k: {"expected": v, "actual": result[k]}
                for k, v in lock["toolchain"].items() if result[k] != v}
    if profile == "xcode27":
        unexpected = {k: {"expected": v, "actual": result[k]}
                      for k, v in EXPLORATORY_XCODE27.items() if result[k] != v}
        if unexpected:
            raise RuntimeError("Xcode 27 profile differs from observed installation: "
                               + json.dumps(unexpected))
        allow_mismatch = True
    result["canonical"] = not mismatch
    result["mismatches"] = mismatch
    if mismatch and not allow_mismatch:
        raise RuntimeError("Toolchain differs from lock: " + json.dumps(mismatch)
                           + ". Use --allow-toolchain-mismatch for recorded exploratory builds.")
    return result


def same_prepared_toolchain(prepared, current):
    """Allow Python's optional Mach-O host suffix, not toolchain drift."""
    if prepared.keys() != current.keys():
        return False
    for key in prepared:
        if key == "host":
            if prepared[key].removesuffix("-Mach-O") != current[key].removesuffix("-Mach-O"):
                return False
        elif prepared[key] != current[key]:
            return False
    return True


def source_state(lock):
    baseline = lock["xnu"]["commit"]
    subprocess.run(["git", "merge-base", "--is-ancestor", baseline, "HEAD"],
                   cwd=ROOT, check=True)
    patch = subprocess.check_output(["git", "diff", "HEAD", "--binary"], cwd=ROOT)
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=ROOT)
    return {
        "head": capture("git", "rev-parse", "HEAD"),
        "baseline": baseline,
        "status": capture("git", "status", "--short"),
        "tracked_diff_sha256": hashlib.sha256(patch).hexdigest(),
        "untracked_sha256": {os.fsdecode(p): source_entry_digest(ROOT / os.fsdecode(p))
                             for p in untracked.split(b"\0") if p},
    }


def source_entry_digest(path):
    """Hash Git-selected regular files or the link itself, never follow links.

    Git represents symlinks by their target text, including directory/dangling
    links. Following a directory link previously crashed the source guard.
    Retain every selected path and detect retargeting; do not add exclusions or
    follow links into unrelated/generated trees. Build dependencies are still
    separately hash-bound, and before/after source equality is still required.
    """
    path = Path(path)
    if path.is_symlink():
        return hashlib.sha256(b'SYMLINK\0' + os.fsencode(os.readlink(path))).hexdigest()
    return digest(path)


def doctor(lock, args):
    current = toolchain(lock, args.allow_toolchain_mismatch, args.profile)
    report = {"profile": args.profile, "toolchain": current, "source": source_state(lock),
              "lock_sha256": digest(LOCK_PATH),
              "gate": "not assessed by doctor; see docs/rpi5/GATE1-AUDIT.md"}
    print(json.dumps(report, indent=2))


def bootstrap(lock, args):
    current = toolchain(lock, args.allow_toolchain_mismatch, args.profile)
    source_state(lock)
    downloads = BUILD / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    sources = {}
    for name, dep in lock["dependencies"].items():
        archive = downloads / f"{name}.tar.gz"
        if not archive.exists():
            cached = Path(args.cache) / archive.name if args.cache else None
            if cached and cached.is_file():
                verify_archive(cached, dep["sha256"])
                shutil.copyfile(cached, archive)
            else:
                temporary = archive.with_suffix(".part")
                subprocess.run(["curl", "--fail", "--location", "--retry", "2",
                                "--proto", "=https", "--output", str(temporary),
                                dep["url"]], check=True)
                verify_archive(temporary, dep["sha256"])
                temporary.replace(archive)
        verify_archive(archive, dep["sha256"])
        dest = BUILD / "sources" / name
        if not dest.exists():
            unpack_archive(archive, dest, dep["directory"])
        sources[name] = dest / dep["directory"]

    sdk = BUILD / "sdk" / f"MacOSX{current['sdk']}.sdk"
    marker = sdk.parent / "prepared.json"
    if marker.exists():
        prepared = json.loads(marker.read_text())
        if (prepared["lock_sha256"] != digest(LOCK_PATH)
                or not same_prepared_toolchain(prepared["toolchain"], current)):
            raise RuntimeError("Existing SDK provenance differs; preserve it and use a fresh checkout")
        print(f"SDK already prepared: {sdk}")
        return
    if sdk.exists():
        raise RuntimeError(f"Incomplete SDK at {sdk}; move it aside before retrying")
    sdk.parent.mkdir(parents=True, exist_ok=True)
    # APFS clone: independent copy-on-write files, no SDK symlink overlay or sudo.
    clone_sdk(current["sdk_path"], sdk)
    av = sources["availability"]
    generated = BUILD / "availability"
    generated.mkdir(exist_ok=True)
    generator = generated / "availability"
    subprocess.run([sys.executable, str(av / "availability"), "--av_version",
                    lock["dependencies"]["availability"]["tag"], "--preprocess",
                    str(av / "availability"), str(generator)], check=True)
    # Reproduce the relevant upstream CMake generation/install mapping using its
    # own generator; no CMake/Ninja installation is needed for this NONE project.
    mapping = {
        "Availability.h": "usr/include/Availability.h",
        "AvailabilityInternal.h": "usr/include/AvailabilityInternal.h",
        "AvailabilityInternalLegacy.h": "usr/include/AvailabilityInternalLegacy.h",
        "AvailabilityMacros.h": "usr/include/AvailabilityMacros.h",
        "AvailabilityVersions.h": "usr/include/AvailabilityVersions.h",
        "AvailabilityInternalPrivate.h": "usr/local/include/AvailabilityInternalPrivate.h",
        "AvailabilityProhibitedInternal.h": "usr/local/include/AvailabilityProhibitedInternal.h",
        "os_availability.h": "usr/include/os/availability.h",
        "VersionMap.h": "usr/local/include/dyld/VersionMap.h",
        "for_dyld_priv.inc": "usr/local/include/dyld/for_dyld_priv.inc",
        "dyld_version_defines.h": "usr/local/include/mach-o/dyld_version_defines.h",
    }
    for template, relative in mapping.items():
        out = generated / template
        subprocess.run([sys.executable, str(generator), "--preprocess",
                        str(av / "templates" / template), str(out)], check=True)
        target = sdk / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out, target)
        if template.startswith("Availability"):
            visibility = "PrivateHeaders" if "/local/" in relative else "Headers"
            target = sdk / "System/Library/Frameworks/Kernel.framework/Versions/A" / visibility / template
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(out, target)
    target = sdk / "usr/local/libexec/availability.pl"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(generator, target)
    target.chmod(0o755)
    prepared = {"profile": args.profile, "toolchain": current, "sdk": str(sdk), "lock_sha256": digest(LOCK_PATH),
                "availability_sha256": digest(target),
                "note": "Availability prepared; firehose/compiler runtime not yet installed"}
    marker.write_text(json.dumps(prepared, indent=2) + "\n")
    print(json.dumps(prepared, indent=2))


def firehose(lock, args):
    """Build the single-source libfirehose_kernel target from pinned libdispatch."""
    current = toolchain(lock, args.allow_toolchain_mismatch, args.profile)
    prepared = json.loads((BUILD / "sdk/prepared.json").read_text())
    if prepared["lock_sha256"] != digest(LOCK_PATH) or not same_prepared_toolchain(prepared["toolchain"], current):
        raise RuntimeError("SDK provenance differs from current lock/toolchain")
    sdk = Path(prepared["sdk"])
    dep = lock["dependencies"]["libdispatch"]
    verify_archive(BUILD / "downloads/libdispatch.tar.gz", dep["sha256"])
    source = BUILD / "sources/libdispatch" / dep["directory"]
    config_dir = BUILD / "obj/DEVELOPMENT_ARM64_BCM2712/libkern/DEVELOPMENT"
    config = config_dir / "Makefile"
    defines = next(line.split("=", 1)[1] for line in config.read_text().splitlines()
                   if line.startswith("export CONFIG_DEFINES ="))
    evidence = Path(tempfile.mkdtemp(prefix="firehose-", dir=BUILD))
    obj = evidence / "firehose_buffer.o"
    archive = evidence / "libfirehose_kernel.a"
    command = [capture("xcrun", "--find", "clang"), "-arch", "arm64",
               "-mcpu=cortex-a76", "-mkernel", "-nostdinc", "-fno-builtin",
               "-fno-branch-target-identification", "-O2", "-std=gnu11",
               "-isysroot", str(sdk), "-DKERNEL=1", "-DKERNEL_PRIVATE=1",
               "-DXNU_KERNEL_PRIVATE=1", "-DLIBKERN_KERNEL_PRIVATE=1",
               "-DARM64_BOARD_CONFIG_BCM2712=1", "-DARM_LARGE_MEMORY=1",
               "-DDISPATCH_USE_DTRACE=0", "-DOS_ATOMIC_CONFIG_MEMORY_ORDER_DEPENDENCY=1",
               "-DOS_ATOMIC_CONFIG_STARVATION_FREE_ONLY=0"] + shlex.split(defines)
    includes = [config_dir, ROOT / "EXTERNAL_HEADERS", source, source / "src/firehose",
                BUILD / "obj/EXPORT_HDRS/libkern/firehose"]
    includes += sorted((BUILD / "obj/EXPORT_HDRS").iterdir())
    kernel = sdk / "System/Library/Frameworks/Kernel.framework"
    includes += [kernel / "PrivateHeaders", kernel / "Headers"]
    for include in includes:
        if include.is_dir():
            command += ["-I", str(include)]
    command += ["-c", str(source / "src/firehose/firehose_buffer.c"), "-o", str(obj)]
    report = {"profile": args.profile, "toolchain": current, "source": source_state(lock),
              "config_sha256": digest(config), "command": command,
              "libdispatch_input_sha256": {
                  str(p.relative_to(source)): digest(p)
                  for p in sorted(source.rglob("*")) if p.is_file()}}
    with (evidence / "build.log").open("w") as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode == 0:
            archive_command = [capture("xcrun", "--find", "libtool"), "-static",
                               "-o", str(archive), str(obj)]
            report["archive_command"] = archive_command
            result = subprocess.run(archive_command, stdout=log, stderr=subprocess.STDOUT)
    report["exit_code"] = result.returncode
    if result.returncode == 0:
        destination = sdk / "usr/local/lib/kernel" / archive.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(archive, destination)
        report["archive_sha256"] = digest(archive)
        report["installed_path"] = str(destination)
    (evidence / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print((evidence / "build.log").read_text())
    print(f"Evidence: {evidence / 'manifest.json'}")
    return result.returncode


def build(lock, args):
    if getattr(args, 'reproducible', False) and not getattr(args, 'fresh', False):
        raise RuntimeError('--reproducible requires --fresh to avoid stale version objects')
    current = toolchain(lock, args.allow_toolchain_mismatch, args.profile)
    state = source_state(lock)
    marker = BUILD / "sdk/prepared.json"
    if not marker.is_file():
        raise RuntimeError("Run bootstrap first")
    prepared = json.loads(marker.read_text())
    if prepared["lock_sha256"] != digest(LOCK_PATH) or not same_prepared_toolchain(prepared["toolchain"], current):
        raise RuntimeError("SDK provenance differs from current lock/toolchain")
    sdk = Path(prepared["sdk"])
    # This public source header belongs to libdispatch, not the private KDK.
    dep = lock["dependencies"]["libdispatch"]
    verify_archive(BUILD / "downloads/libdispatch.tar.gz", dep["sha256"])
    header = (BUILD / "sources/libdispatch" / dep["directory"]
              / "os/firehose_buffer_private.h")
    destination = sdk / "usr/local/include/kernel/os/firehose_buffer_private.h"
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Match libfirehose_kernel.xcconfig's exported-header preprocessing.
    filtered = subprocess.run(["unifdef", "-DKERNEL=1", "-DOS_FIREHOSE_SPI=1",
                               "-DOS_VOUCHER_ACTIVITY_SPI_TYPES=1",
                               "-UOS_VOUCHER_ACTIVITY_SPI", str(header)], capture_output=True)
    if filtered.returncode not in (0, 1):
        raise RuntimeError("Firehose header preprocessing failed")
    if not destination.exists() or destination.read_bytes() != filtered.stdout:
        destination.write_bytes(filtered.stdout)
    if digest(sdk / "usr/local/libexec/availability.pl") != prepared["availability_sha256"]:
        raise RuntimeError("Generated availability tool has changed")
    evidence = Path(tempfile.mkdtemp(prefix="run-", dir=BUILD))
    # Preserve prior artifacts. Fresh means new kernel output roots, not a
    # rebuilt SDK or libfirehose dependency; record that distinction below.
    outputs = (Path(tempfile.mkdtemp(prefix="fresh-", dir=BUILD))
               if getattr(args, "fresh", False) else BUILD)
    # Xcode does not reliably discover metadata for SDK copies outside its
    # platform directory. Supply the recorded version and original platform,
    # while every compiler still receives the private SDK as its sysroot.
    command = ["make", f"-j{args.jobs}", f"MAKEJOBS=--jobs={args.jobs}",
               f"SDKROOT={sdk}", f"SDKROOT_RESOLVED={sdk}",
               f"SDKVERSION={current['sdk']}", "PLATFORM=MacOSX",
               "PLATFORMPATH=" + capture("xcrun", "--sdk", "macosx", "--show-sdk-platform-path"),
               "HOST_SDKROOT=macosx",
               f"RC_DARWIN_KERNEL_VERSION={lock['xnu']['kernel_version']}",
               "TARGET_CONFIGS=DEVELOPMENT ARM64 BCM2712", "KDKROOT=",
               f"RPI5_EXPLORATORY_TOOLCHAIN={0 if current['canonical'] else 1}",
               f"RPI5_REPRODUCIBLE={1 if getattr(args, 'reproducible', False) else 0}",
               "BUILD_LTO=0", "DO_CTFMERGE=0",
               f"OBJROOT={outputs / 'obj'}", f"DSTROOT={outputs / 'dst'}",
               f"SYMROOT={outputs / 'sym'}", args.target]
    crypto_candidate = None
    if getattr(args, 'with_crypto_candidate', False):
        result = subprocess.run([sys.executable, str(ROOT/'tools/rpi5/probe_crypto_table.py'),
            '--kernel-adapters', '--with-startup', '--build-root', str(BUILD)],
            cwd=ROOT, text=True, capture_output=True, check=True)
        summary = json.loads(result.stdout)
        candidate_dir = Path(summary['directory']).resolve()
        if not candidate_dir.is_relative_to(BUILD.resolve()):
            raise RuntimeError('Crypto candidate escaped the build directory')
        candidate_manifest = candidate_dir/'manifest.json'
        candidate_report = json.loads(candidate_manifest.read_text())
        candidate_object = candidate_dir/'crypto-table.o'
        if not candidate_report['kernel_adapter_flags'] or not candidate_report['with_startup']:
            raise RuntimeError('Crypto candidate lacks kernel/startup configuration')
        if digest(candidate_object) != candidate_report['object_sha256']:
            raise RuntimeError('Crypto candidate object differs from its manifest')
        for path, expected in candidate_report['source_sha256'].items():
            if digest(ROOT/path) != expected:
                raise RuntimeError('Crypto source changed during preparation: '+path)
        command.insert(-1, f'RPI5_CRYPTO_CANDIDATE_OBJECT={candidate_object}')
        if getattr(args, 'activate_crypto', False):
            command.insert(-1, 'RPI5_CRYPTO_STARTUP=1')
        crypto_candidate = {'manifest':str(candidate_manifest),
            'manifest_sha256':digest(candidate_manifest),'object':str(candidate_object),
            'object_sha256':digest(candidate_object),'startup_enabled':getattr(args, 'activate_crypto', False)}
    pthread_provider = None
    if getattr(args, 'with_pthread_provider', False):
        if args.profile != 'xcode27' or args.target != 'all':
            raise RuntimeError('Pthread provider requires the Xcode 27 all target')
        result = subprocess.run(
            [sys.executable, str(ROOT / 'tools/rpi5/build_pthread_provider.py'),
             '--build-root', str(BUILD), '--objroot', str(BUILD / 'obj')],
            cwd=ROOT, text=True, capture_output=True, check=True)
        pthread_provider = json.loads(result.stdout)
        provider_object = Path(pthread_provider['object']).resolve()
        if not provider_object.is_relative_to(BUILD.resolve()):
            raise RuntimeError('Pthread provider escaped the build directory')
        if digest(provider_object) != pthread_provider['object_sha256']:
            raise RuntimeError('Pthread provider object differs from its manifest')
        if digest(Path(pthread_provider['manifest'])) != pthread_provider['manifest_sha256']:
            raise RuntimeError('Pthread provider manifest changed during preparation')
        command.insert(-1, f'RPI5_PTHREAD_PROVIDER_OBJECT={provider_object}')
    storage_provider = None
    if getattr(args, 'with_storage_provider', False):
        if args.profile != 'xcode27' or args.target != 'all' or not getattr(args, 'fresh', False):
            raise RuntimeError('Storage provider requires a fresh Xcode 27 all target')
        result = subprocess.run(
            [sys.executable, str(ROOT / 'tools/rpi5/build_storage_provider.py'),
             '--output-root', str(outputs),
             *(['--write-trial'] if getattr(args,'storage_write_trial',False) else [])],
             cwd=ROOT, text=True, capture_output=True, check=True)
        storage_provider = json.loads(result.stdout)
        if storage_provider.get('write_trial',False) is not bool(getattr(args,'storage_write_trial',False)):
            raise RuntimeError('Storage provider profile mismatch')
        storage_object = Path(storage_provider['object']).resolve()
        storage_config = Path(storage_provider['configuration']['directory']).resolve()
        if (not storage_object.is_relative_to((ROOT / 'build/rpi5').resolve())
                or not storage_config.is_relative_to(outputs.resolve())):
            raise RuntimeError('Storage provider or profile escaped its isolated output root')
        if digest(storage_object) != storage_provider['object_sha256']:
            raise RuntimeError('Storage provider object changed before build')
        if digest(Path(storage_provider['manifest'])) != storage_provider['manifest_sha256']:
            raise RuntimeError('Storage provider manifest changed before build')
        command.insert(-1, f'RPI5_STORAGE_PROVIDER_OBJECT={storage_object}')
        if getattr(args,'storage_write_trial',False):
            command.insert(-1, 'RPI5_STORAGE_WRITE_TRIAL=1')
        command.insert(-1, f'MASTERCONFDIR={storage_config}')
    version_metadata = None
    if getattr(args, 'reproducible', False):
        epoch = int(capture('git', 'show', '-s', '--format=%ct', lock['xnu']['commit']))
        version_metadata = reproducible_metadata(epoch)
        for key, value in version_metadata.items():
            command.insert(-1, f'{key}={value}')
    report = {"started_utc": datetime.now(timezone.utc).isoformat(),
              "profile": args.profile,
              "command": command, "toolchain": current, "source": state,
              "lock_sha256": digest(LOCK_PATH), "target": args.target,
              "fresh_kernel_outputs": getattr(args, "fresh", False),
              "version_metadata": version_metadata,
              "output_root": str(outputs),
              "crypto_candidate": crypto_candidate,
              "pthread_provider": pthread_provider,
              "storage_provider": storage_provider,
              "firehose_header_sha256": digest(destination)}
    manifest = evidence / "manifest.json"
    manifest.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Build log: {evidence / 'build.log'}", flush=True)
    env = os.environ.copy()
    # An inherited build customization must not secretly supply binary providers.
    for key in ("KDKROOT", "MAKEFLAGS", "MFLAGS", "LD_KERNEL_LIBS", "LD_KERNEL_ARCHIVES",
                "RPI5_COMPILER_RUNTIME", "RPI5_CRYPTO_CANDIDATE_OBJECT", "RPI5_CRYPTO_STARTUP", "RPI5_PTHREAD_PROVIDER_OBJECT", "RPI5_STORAGE_PROVIDER_OBJECT", "RPI5_STORAGE_WRITE_TRIAL", "MASTERCONFDIR", "RPI5_REPRODUCIBLE", "TARGET_CONFIGS", "SDKROOT"):
        env.pop(key, None)
    with (evidence / "build.log").open("w") as log:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    report["exit_code"] = result.returncode
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["source_at_finish"] = source_state(lock)
    report["source_unchanged_during_build"] = state == report["source_at_finish"]
    if result.returncode == 0 and args.target == 'all':
        kernel = outputs / 'obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712'
        report['kernel_artifact'] = {'path': str(kernel), 'sha256': digest(kernel),
                                     'bytes': kernel.stat().st_size}
    manifest.write_text(json.dumps(report, indent=2) + "\n")
    print("\n".join((evidence / "build.log").read_text(errors="replace").splitlines()[-35:]))
    print(f"Evidence: {manifest}")
    return result.returncode


def main():
    if sys.version_info < (3, 12):
        print("rpi5: Python 3.12 or newer is required", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("doctor", "bootstrap", "firehose", "build"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--allow-toolchain-mismatch", action="store_true")
        cmd.add_argument("--profile", choices=("canonical", "xcode27"), default="canonical",
                         help="Select isolated experimental Xcode 27 outputs; canonical remains Gate 1")
        if name == "bootstrap":
            cmd.add_argument("--cache", help="Optional directory of already downloaded archives")
        if name == "build":
            cmd.add_argument("--target", choices=("exporthdrs", "all"), default="all")
            cmd.add_argument("--jobs", type=int, default=4)
            cmd.add_argument("--fresh", action="store_true",
                             help="Use new output roots; retain the prepared SDK and dependencies")
            cmd.add_argument('--reproducible', action='store_true',
                             help='With --fresh, pin version date/root and enable reproducible linking; verify repeat outputs separately')
            cmd.add_argument('--with-crypto-candidate', action='store_true',
                             help='Source-build and link the provider, without enabling startup')
            cmd.add_argument('--activate-crypto', action='store_true',
                             help='Enable experimental pre-IOKit registration; requires --with-crypto-candidate')
            cmd.add_argument('--with-pthread-provider', action='store_true',
                             help='Source-build and link pinned libpthread on Xcode 27 BCM2712')
            cmd.add_argument('--with-storage-provider', action='store_true',
                             help='Experimental built-in IOStorageFamily/HFS; requires fresh outputs and runtime providers')
            cmd.add_argument('--storage-write-trial',action='store_true',
                             help='Distinct bounded-write storage profile; requires --with-storage-provider')
    args = parser.parse_args()
    if getattr(args,'storage_write_trial',False) and not getattr(args,'with_storage_provider',False):
        parser.error('--storage-write-trial requires --with-storage-provider and its fresh/runtime-provider gates')
    if getattr(args, 'activate_crypto', False) and not getattr(args, 'with_crypto_candidate', False):
        parser.error('--activate-crypto requires --with-crypto-candidate')
    if getattr(args, 'with_pthread_provider', False) and not getattr(args, 'activate_crypto', False):
        parser.error('--with-pthread-provider requires --activate-crypto for a bootable Pi kernel')
    if getattr(args, 'with_storage_provider', False) and (
            not getattr(args, 'fresh', False) or args.profile != 'xcode27'
            or args.target != 'all' or not getattr(args, 'with_pthread_provider', False)):
        parser.error('--with-storage-provider requires --fresh --profile xcode27 --target all --with-pthread-provider')
    if getattr(args, "jobs", 1) < 1:
        parser.error("--jobs must be positive")
    lock = json.loads(LOCK_PATH.read_text())
    try:
        global BUILD
        BUILD = select_profile(args.profile)
        return globals()[args.action](lock, args) or 0
    except (RuntimeError, OSError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print(f"rpi5: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
