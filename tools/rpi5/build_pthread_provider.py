#!/usr/bin/env python3
"""Build the pinned libpthread kernel provider for BCM2712 DEVELOPMENT."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from rpi5 import digest, unpack_archive, verify_archive


ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "tools/rpi5/gate2-pthread.lock.json"
PATCHES = (
    ROOT / "tools/rpi5/patches/libpthread-kern.patch",
    ROOT / "tools/rpi5/patches/xnu-pthread-header-overlay.patch",
)
CONFIG = "DEVELOPMENT_ARM64_BCM2712"
SOURCES = ("kern_init.c", "kern_support.c", "kern_synch.c")


def provider_key(archive_hash, patch_hashes, header_hash, lock_hash=""):
    encoded = json.dumps([archive_hash, patch_hashes, header_hash, lock_hash],
                         separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:20]


def fetch_archive_if_missing(archive, pinned):
    if archive.exists():
        verify_archive(archive, pinned["sha256"])
        return
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not pinned["url"].startswith("https://"):
        raise RuntimeError("Pthread archive URL must use HTTPS")
    with tempfile.NamedTemporaryFile(prefix="pthread-download-", suffix=".part",
                                     dir=archive.parent, delete=False) as temporary:
        pending = Path(temporary.name)
    try:
        subprocess.run(["curl", "--fail", "--location", "--retry", "2",
                        "--proto", "=https", "--output", str(pending),
                        pinned["url"]], check=True)
        verify_archive(pending, pinned["sha256"])
        pending.replace(archive)
    finally:
        pending.unlink(missing_ok=True)


def prepare_source(build_root, lock):
    pinned = lock["libpthread"]
    archive = build_root / f"{pinned['tag']}.tar.gz"
    fetch_archive_if_missing(archive, pinned)
    patch_hashes = {p.name: digest(p) for p in PATCHES}
    header_hash = digest(ROOT / "bsd/sys/pthread_internal.h")
    key = provider_key(pinned["sha256"], patch_hashes, header_hash, digest(LOCK))
    stage = build_root / "pthread-provider" / key
    source = stage / pinned["directory"]
    marker = stage / "source.json"
    provenance = {"lock_sha256": digest(LOCK), "archive_sha256": pinned["sha256"],
                  "commit": pinned["commit"], "patch_sha256": patch_hashes,
                  "xnu_header_sha256": header_hash}
    if marker.exists():
        if json.loads(marker.read_text()) != provenance:
            raise RuntimeError(f"Existing pthread stage provenance changed: {stage}")
    elif stage.exists():
        raise RuntimeError(f"Incomplete pthread stage: {stage}")
    else:
        stage.parent.mkdir(parents=True, exist_ok=True)
        unpack_archive(archive, stage, pinned["directory"])
        subprocess.run(["patch", "-s", "-p1", "-d", str(source),
                        "-i", str(PATCHES[0])], check=True)
        (stage / "sys").mkdir()
        shutil.copyfile(ROOT / "bsd/sys/pthread_internal.h",
                        stage / "sys/pthread_internal.h")
        subprocess.run(["patch", "-s", "-p1", "-d", str(stage),
                        "-i", str(PATCHES[1])], check=True)
        marker.write_text(json.dumps(provenance, indent=2) + "\n")
    for relative, expected in lock["adapted_sha256"].items():
        path = stage / relative if relative.startswith("sys/") else source / relative
        verify_archive(path, expected)
    return stage, source, provenance


def compile_provider(build_root, objroot):
    lock = json.loads(LOCK.read_text())
    if lock["schema_version"] != 1 or lock["xnu_tag"] != "xnu-12377.121.6":
        raise RuntimeError("Unsupported Gate 2 pthread pin")
    stage, source, provenance = prepare_source(build_root, lock)
    database = objroot / CONFIG / "compile_commands.json"
    commands = json.loads(database.read_text())
    template = next((item for item in commands
                     if item["file"].endswith("bsd/pthread/pthread_shims.c")), None)
    if template is None:
        raise RuntimeError(f"Missing XNU pthread compile command: {database}")
    sdk = build_root / "sdk/MacOSX27.0.sdk"
    if not sdk.is_dir():
        raise RuntimeError(f"Missing prepared Xcode 27 SDK: {sdk}")
    objects = []
    commands_used = []
    objdir = stage / "obj"
    objdir.mkdir(exist_ok=True)
    for filename in SOURCES:
        path = source / "kern" / filename
        output = objdir / (path.stem + ".o")
        args = list(template["arguments"])
        args[args.index(template["file"])] = str(path)
        args[args.index("-o") + 1] = str(output)
        first_include = args.index("-I")
        args[first_include:first_include] = ["-I", str(stage)]
        args += [
            "-I", str(source), "-I", str(source / "private"),
            "-I", str(source / "include"), "-I", str(ROOT / "osfmk"),
            "-I", str(sdk / "usr/include"),
            "-I", str(sdk / "System/Library/Frameworks/Kernel.framework/Versions/A/Headers"),
            "-I", str(objroot / CONFIG / "config"),
            "-include", "kern/ast.h",
            "-D", "ABSOLUTETIME_SCALAR_TYPE", "-D", "NEEDS_SCHED_CALL_T",
            "-D", "__PTHREAD_EXPOSE_INTERNALS__",
            "-D", "pthread_kern=rpi5_pthread_kern",
            "-ferror-limit=0",
        ]
        log = stage / (path.stem + ".log")
        with log.open("w") as stream:
            result = subprocess.run(args, cwd=template["directory"],
                                    stdout=stream, stderr=subprocess.STDOUT)
        commands_used.append({"directory": template["directory"],
                              "arguments": args, "source_sha256": digest(path),
                              "object": str(output), "log": str(log),
                              "exit_code": result.returncode})
        if result.returncode:
            raise RuntimeError(f"Pthread compilation failed: {filename}; see {log}")
        objects.append(output)
    combined = objdir / "libpthread-kern.o"
    link = [template["arguments"][0], "-target", "arm64-apple-macosx27.0",
            "-arch", "arm64", "-nostdlib", "-r", *(str(p) for p in objects),
            "-o", str(combined)]
    subprocess.run(link, check=True)
    undefined = subprocess.check_output(["nm", "-u", str(combined)], text=True).splitlines()
    report = {"source": provenance, "stage": str(stage), "compile_database": str(database),
              "commands": commands_used, "partial_link": link,
              "objects_sha256": {str(p): digest(p) for p in objects},
              "object": str(combined), "object_sha256": digest(combined),
              "undefined_symbols": undefined}
    manifest = stage / "manifest.json"
    manifest.write_text(json.dumps(report, indent=2) + "\n")
    report["manifest"] = str(manifest)
    report["manifest_sha256"] = digest(manifest)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-root", type=Path, default=ROOT / "build/rpi5-xcode27")
    parser.add_argument("--objroot", type=Path,
                        default=ROOT / "build/rpi5-xcode27/obj")
    args = parser.parse_args()
    try:
        build_root = args.build_root.resolve(strict=True)
        if build_root != (ROOT / "build/rpi5-xcode27").resolve():
            raise RuntimeError("Pthread provider must use the isolated Xcode 27 build root")
        report = compile_provider(build_root, args.objroot.resolve(strict=True))
        print(json.dumps({key: report[key] for key in
                          ("object", "object_sha256", "manifest", "manifest_sha256")},
                         indent=2))
        return 0
    except (RuntimeError, OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
        print(f"pthread provider: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
