#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Package verified source-built Darwin inputs in a new private versioned directory.

Does not run VMs, format media, alter services or overwrite an existing package.
EFI payloads contain entropy: this is a local capsule, not a public distribution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
ROOT = HERE.parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--kernel-build", required=True, type=Path)
    parser.add_argument("--agent-loader", required=True, type=Path)
    parser.add_argument("--interactive-loader", required=True, type=Path)
    parser.add_argument("--agent-root", required=True, type=Path)
    parser.add_argument("--interactive-root", required=True, type=Path)
    parser.add_argument("--data-disk", required=True, type=Path)
    parser.add_argument("--write-session", required=True, type=Path)
    parser.add_argument("--read-session", required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?", args.version):
        parser.error("version must be an explicit semantic version")
    kernel = args.kernel_build / "obj/DEVELOPMENT_ARM64_VZGENERIC/kernel.development.vzgeneric"
    kernel_record = json.loads((args.kernel_build / "manifest.json").read_text())
    if kernel_record.get("exit_code") != 0 or not kernel_record.get("storage_profile"):
        raise RuntimeError("requires a successful distinct storage-profile kernel build")
    if not any(item["sha256"] == digest(kernel) for item in kernel_record["kernels"]):
        raise RuntimeError("kernel no longer matches its successful build record")
    storage = args.kernel_build / "storage-provider/vz-storage-provider.o"
    if digest(storage) != kernel_record["storage_provider"]["object_sha256"]:
        raise RuntimeError("storage provider changed since kernel link")
    capsule = HERE / "build/zsh-working-2026-10-12"
    capsule_record = json.loads((capsule / "manifest.json").read_text())
    link_record = json.loads((capsule / "link-manifest.json").read_text())
    if digest(capsule / "zsh") != link_record["sha256"]:
        raise RuntimeError("zsh no longer matches its source-built link record")
    copies = {
        kernel: "kernel.macho", args.kernel_build / "manifest.json": "provenance/kernel-build.json",
        args.kernel_build / "storage-provider/manifest.json": "provenance/storage-build.json",
        args.kernel_build / "storage-provider/vz-storage-provider.o": "libraries/vz-storage-provider.o",
        capsule / "zsh": "zsh", capsule / "link-manifest.json": "provenance/zsh-link.json",
        capsule / "efi-variables-template.bin": "efi-variables-template.bin",
        EXPERIMENT / "container/.build/arm64-apple-macosx/debug/container": "bin/container",
        HERE / "apple-zsh-source.json": "provenance/apple-zsh-source.json",
        HERE / "apple-runtime.sources.lock.json": "provenance/apple-runtime.sources.lock.json",
        ROOT / "APPLE_LICENSE": "licenses/XNU-APPLE_LICENSE",
    }
    for source, name in (
        ("apple-zsh/zsh/LICENCE", "zsh-LICENCE"),
        ("apple-Libm-93/APPLE_LICENSE", "Libm-APPLE_LICENSE"),
        ("Libc-Libc-391/APPLE_LICENSE", "Libc-391-APPLE_LICENSE"),
        ("apple-Libc-1752.120.2/APPLE_LICENSE", "Libc-1752-APPLE_LICENSE"),
        ("apple-libplatform-375.120.2/LICENSE", "libplatform-LICENSE"),
        ("apple-ncurses/ncurses/COPYING", "ncurses-COPYING"),
    ):
        copies[HERE / "upstream" / source] = "licenses/" + name
    for source, name in (
        ("IOStorageFamily/IOStorageFamily-IOStorageFamily-337.100.1/APPLE_LICENSE", "IOStorageFamily"),
        ("hfs/hfs-hfs-715.120.4/APPLE_LICENSE", "HFS"),
    ):
        copies[ROOT / "build/rpi5/gate4-sources" / source] = f"licenses/{name}-APPLE_LICENSE"
    for mode, loader, ramroot in (("agent", args.agent_loader, args.agent_root),
                                 ("interactive", args.interactive_loader, args.interactive_root)):
        record = json.loads((loader / "manifest.json").read_text())
        if not (record.get("writableStorageProfile") and record["inputs"]["kernelSHA256"] == digest(kernel)
                and record["inputs"]["ramrootSHA256"] == digest(ramroot / "ramdisk.bin")
                and record["payloadSHA256"] == digest(loader / "BOOTAA64.EFI")):
            raise RuntimeError(f"{mode} loader/kernel/root mismatch")
        copies[loader / "efi.img"] = f"efi-{mode}.img"
        copies[loader / "BOOTAA64.EFI"] = f"loader-{mode}.efi"
        copies[loader / "manifest.json"] = f"provenance/loader-{mode}.json"
        copies[ramroot / "ramdisk.bin"] = f"ramroot-{mode}.bin"
        copies[ramroot / "manifest.json"] = f"provenance/ramroot-{mode}.json"
    for label, session in (("write", args.write_session), ("restart", args.read_session)):
        result = json.loads((session / "result.json").read_text())
        if not result["guestStopped"] or result["termination"] != "guestStopped":
            raise RuntimeError("only clean stopped sessions may enter the workload capsule")
        if label == "write":
            if not result["commandSucceeded"] or b"WRITE_OK\n" not in (session / "command-1-stdout.bin").read_bytes():
                raise RuntimeError("missing actual managed write proof")
        else:
            serial = (session / "serial.bin").read_bytes().replace(b"\r", b"")
            if not all(marker in serial for marker in (b"RESTORED_FILE:PERSISTED_FILE\n", b"\nPERSISTED_SCRIPT\n", b"  SAVED_HISTORY\n")):
                raise RuntimeError("missing actual restart file/script/history proof")
        for path in session.iterdir():
            if path.is_file() and path.name != "efi-variables.bin":
                copies[path] = f"evidence/{label}/{path.name}"
    for source in (capsule / "archives").rglob("*"):
        if source.is_file():
            if digest(source) != capsule_record["sha256"][str(source.relative_to(capsule))]:
                raise RuntimeError(f"preserved Apple archive changed: {source}")
            copies[source] = "libraries/" + str(source.relative_to(capsule / "archives"))
    # Retain the actual runtime adapters, ABI headers and configuration alongside
    # pinned-source build recipes. This is not a standalone SDK/source archive.
    for directory in ("runtime", "abi-headers", "configuration", "build-scripts"):
        for source in (capsule / directory).rglob("*"):
            if source.is_file():
                if digest(source) != capsule_record["sha256"][str(source.relative_to(capsule))]:
                    raise RuntimeError(f"preserved source changed: {source}")
                copies[source] = "source/apple-runtime/" + str(source.relative_to(capsule))
    for source in (capsule / "provenance").iterdir():
        if source.is_file():
            copies[source] = "provenance/apple-runtime/" + source.name
    for source in list(HERE.glob("*.py")) + list((HERE / "src").iterdir()):
        if source.is_file():
            copies[source] = "source/userland/" + str(source.relative_to(HERE))
    for source in (EXPERIMENT / "kernel").glob("*.py"):
        copies[source] = "source/kernel/" + source.name
    for source in (EXPERIMENT / "kernel").glob("*.patch"):
        copies[source] = "source/kernel/" + source.name
    copies[EXPERIMENT / "kernel/storage-configuration.h"] = "source/kernel/storage-configuration.h"
    copies[EXPERIMENT / "build_loader.py"] = "source/build_loader.py"
    copies[HERE / "source-provenance.json"] = "provenance/bootstrap-utilities.json"
    for source in (ROOT / "loader/vz").iterdir():
        if source.is_file():
            copies[source] = "source/loader-vz/" + source.name
    for source in (EXPERIMENT / "kernel/overlay").rglob("*"):
        if source.is_file():
            copies[source] = "source/kernel/overlay/" + str(source.relative_to(EXPERIMENT / "kernel/overlay"))
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    immutable = {}
    for source, name in copies.items():
        before = digest(source)
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if digest(destination) != before or digest(source) != before:
            raise RuntimeError(f"input changed during packaging: {source}")
        immutable[name] = before
    shutil.copy2(output / "source/userland/workload_launcher.py", output / "darwin")
    immutable["darwin"] = digest(output / "darwin")
    if args.data_disk.is_symlink() or not args.data_disk.is_file():
        raise RuntimeError("data disk must be an existing regular file")
    data_hash = digest(args.data_disk)
    shutil.copy2(args.data_disk, output / "data.raw")
    if digest(output / "data.raw") != data_hash or digest(args.data_disk) != data_hash:
        raise RuntimeError("data disk changed during packaging; stop its VM before copying")
    (output / "data.raw").chmod(0o600)
    (output / "efi-variables-template.bin").chmod(0o600)
    (output / "darwin").chmod(0o755)
    (output / "runs").mkdir(mode=0o700)
    readme = output / "README.md"
    readme.write_text(f"""# Darwin workload {args.version}

Private local experimental Apple-silicon VM package. Requires macOS,
Virtualization.framework and Python 3. No installed container service is needed.

Run `./darwin` for interactive Apple-source zsh 5.9; use `exit` to save history,
unmount HFS+ and shut down. HOME, HISTFILE and saved files live under `/data`.
Run `./darwin --command 'print -r -- $ZSH_VERSION'` for captured managed output,
exit status and automatic shutdown. Evidence is written to a fresh `runs/` folder.
Never run two VMs with the same writable data disk. The launcher locks its disk.

The kernel, zsh, selected Apple-source libraries, HFS+/IOStorage provider,
labeled bootstrap utilities, provenance, notices and immutable hashes are included.
Build recipes retain upstream pins and local SDK paths; this is not a complete
standalone source/SDK distribution. Do not publish EFI images or variable stores:
they contain private entropy, and reuse currently repeats embedded seed bytes.

No full PTY/ZLE/completion, networking, GPU, OCI compatibility, production isolation
or power-loss durability is claimed. The default disk includes the focused trial's
demo script, note and history. Only one clean-shutdown persistence trial is qualified.
See manifest.json for the exact profile and limits.
""")
    immutable["README.md"] = digest(readme)
    manifest = {"version": args.version, "profile": "experimental Apple-silicon VZ Darwin workload",
        "immutable_sha256": immutable, "data_disk_initial_sha256": digest(output / "data.raw"),
        "apple_zsh_version": "5.9", "source_policy": "pinned Apple-source static libraries and zsh; labeled project bootstrap utilities/glue",
        "utilities": ["sh", "echo", "cat", "ls", "sleep", "uname", "true", "false", "poweroff"],
        "limitations": ["private local artifact: EFI images contain per-image entropy; do not publish",
            "one vCPU, 512 MiB VM RAM, 320 MiB kernel arena; no network or shared host directories",
            "serial is line-buffered, not a complete PTY; zsh core only, no ZLE/completion/multibyte",
            "managed commands: 256-byte argv payload; no managed stdin/PTY; not OCI or production isolation",
            "embedded entropy repeats when an EFI image is reused; inherited seed-clear hardening remains",
            "persistent storage verified for clean shutdown/restart, not power-loss recovery",
            "default data disk contains the focused trial's demo script, note and shell history"]}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"package": str(output), "version": args.version, "immutable_files": len(immutable)}))


if __name__ == "__main__":
    main()
