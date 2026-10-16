#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build a local, versioned Darwin workload package, not a Linux/OCI image."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

from prepare_pid1 import inspect as inspect_macho
from ramroot import build, inspect
from workspace_launcher import digest, validate_package

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
PROFILE = {"cpus": 1, "memory_mib": 512, "timeout_seconds": 60}


def string(value, label, maximum=4096):
    if not isinstance(value, str) or "\0" in value or len(value.encode()) > maximum:
        raise ValueError(f"{label} must be a NUL-free string of at most {maximum} UTF-8 bytes")
    return value


def guest_path(value, prefix=None):
    string(value, "guest path", 512)
    path = PurePosixPath(value)
    if not value.startswith("/") or str(path) != value or any(part in (".", "..") for part in value.split("/")):
        raise ValueError("guest paths must be canonical absolute paths")
    if prefix and not value.startswith(prefix + "/"):
        raise ValueError(f"payload files must be below {prefix}")
    return value


def validate_spec(spec):
    if not isinstance(spec, dict) or set(spec) - {"format", "name", "version", "entrypoint", "env", "cwd", "files", "network", "resources"}:
        raise ValueError("unknown workload specification fields")
    if spec.get("format") != "darwin-workload-spec-1":
        raise ValueError("expected darwin-workload-spec-1")
    for key in ("name", "version"):
        if not isinstance(spec.get(key), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,47}", spec[key]):
            raise ValueError(f"invalid {key}")
    argv = spec.get("entrypoint")
    if not isinstance(argv, list) or not 1 <= len(argv) <= 64:
        raise ValueError("entrypoint requires 1..64 arguments")
    for arg in argv:
        string(arg, "entrypoint argument")
    guest_path(argv[0])
    if sum(len(arg.encode()) + 1 for arg in argv) > 16384:
        raise ValueError("entrypoint exceeds 16 KiB")
    environment = spec.get("env", {})
    if not isinstance(environment, dict) or len(environment) > 32:
        raise ValueError("env must be an object with at most 32 variables")
    for key, value in environment.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or key in {"PWD", "OLDPWD", "ZDOTDIR", "ENV", "BASH_ENV", "IFS", "FPATH", "ZSH_ENV"} or key.startswith("DYLD_"):
            raise ValueError(f"unsupported environment variable: {key}")
        string(value, "environment value")
    if sum(len(key) + len(value.encode()) + 2 for key, value in environment.items()) > 16384:
        raise ValueError("environment exceeds 16 KiB")
    cwd = guest_path(spec.get("cwd", "/data"))
    if cwd != "/data" and cwd != "/app" and not cwd.startswith("/app/"):
        raise ValueError("cwd must be /data or an existing /app directory")
    network = spec.get("network", "none")
    if network not in ("none", "nat"):
        raise ValueError("network must be none or nat")
    if not isinstance(spec.get("resources", {}), dict):
        raise ValueError("resources must be an object")
    resources = PROFILE | spec.get("resources", {})
    if set(resources) != set(PROFILE) or type(resources["cpus"]) is not int or type(resources["memory_mib"]) is not int or resources["cpus"] != 1 or resources["memory_mib"] != 512:
        raise ValueError("this qualified runtime supports exactly one vCPU and 512 MiB")
    deadline = resources["timeout_seconds"]
    if type(deadline) is not int or not 1 <= deadline <= 3600:
        raise ValueError("timeout_seconds must be 1..3600")
    files = spec.get("files", [])
    if not isinstance(files, list) or len(files) > 12:
        raise ValueError("files must be a list of at most 12 entries (RAM-root node limit also applies)")
    paths = set()
    for record in files:
        if not isinstance(record, dict) or set(record) - {"source", "path", "executable"} or not {"source", "path"} <= set(record):
            raise ValueError("file requires source, path and optional executable")
        string(record["source"], "file source")
        path = guest_path(record["path"], "/app")
        if path == "/app/entry.zsh" or path in paths:
            raise ValueError("duplicate or reserved payload path")
        if type(record.get("executable", False)) is not bool:
            raise ValueError("executable must be a boolean")
        paths.add(path)
    return spec | {"env": environment, "cwd": cwd, "files": files, "network": network, "resources": resources}


def entry_script(spec):
    # No interpolated host command, eval, or DGA argument-size workaround that
    # drops arguments. zsh reads this immutable file from the package RAM root.
    lines = ["# Generated downstream adapter; executed by official source-built Apple zsh.", "emulate -R zsh",
             "export PATH=/bin:/sbin HOME=/data TERM=dumb TERMINFO=/etc/terminfo"]
    if spec["network"] == "nat":
        lines.append("/bin/dhcpctl || { print -u2 -- 'Darwin workload: DHCP failed'; exit 125; }")
    for key, value in sorted(spec["env"].items()):
        lines.append("export " + shlex.quote(key + "=" + value) + " || exit 125")
    lines.append("builtin cd -- " + shlex.quote(spec["cwd"]) + " || exit 125")
    lines.append("exec " + " ".join(shlex.quote(arg) for arg in spec["entrypoint"]))
    return ("\n".join(lines) + "\n").encode()


def unpack_root(image, max_nodes=32):
    report = inspect(image, max_nodes=max_nodes)
    return {entry["path"]: (image[entry["offset"]:entry["offset"] + entry["size"]], entry["mode"])
            for entry in report["entries"] if entry["type"] == "file"}


def copy_checked(source, destination):
    expected = digest(source)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    if digest(source) != expected or digest(destination) != expected:
        raise RuntimeError(f"source changed while copying: {source}")


def package(spec_path, output, workspace, kernel_build=None):
    spec_path, output, workspace = spec_path.resolve(), output.absolute(), workspace.resolve()
    spec = validate_spec(json.loads(spec_path.read_text()))
    base = validate_package(workspace)
    pin = None
    if kernel_build is None:
        pin = json.loads((HERE / "workload-runtime.json").read_text())
        kernel_build = EXPERIMENT / pin["kernel_build"]
    kernel_build = kernel_build.resolve()
    kernel_record = json.loads((kernel_build / "manifest.json").read_text())
    kernel = kernel_build / "obj/DEVELOPMENT_ARM64_VZGENERIC/kernel.development.vzgeneric"
    if kernel_record.get("exit_code") != 0 or not kernel_record.get("storage_profile") or not kernel_record.get("network_profile"):
        raise RuntimeError("requires a completed source-built storage/network VM kernel")
    if not any(record["sha256"] == digest(kernel) for record in kernel_record["kernels"]):
        raise RuntimeError("kernel differs from its successful build record")
    if pin and digest(kernel) != pin["kernel_sha256"]:
        raise RuntimeError("pinned workload runtime kernel changed")
    for relative, required in (("osfmk/prng/prng_random.c", "cc_clear(sizeof(native_rand), native_rand);"),
                               ("iokit/Kernel/VZGenericPlatformExpert.cpp", "VZXNU:NETWORK:ABSENT OFFLINE")):
        source = kernel_build / "source" / relative
        if required not in source.read_text() or kernel_record["effective_source_sha256"].get(relative) != digest(source):
            raise RuntimeError(f"kernel lacks its compiled workload prerequisite: {relative}")
    source_files = unpack_root((workspace / "ramdisk.bin").read_bytes(), max_nodes=base.get("ramroot_max_nodes", 32))
    root_nodes = kernel_record.get("ramroot_max_nodes", 32)
    utilities = base.get("apple_utilities")
    if utilities and root_nodes != 96:
        raise RuntimeError("broader Apple userland requires the separately compiled 96-node VM kernel")
    if root_nodes != 32:
        relative = "bsd/miscfs/mockfs/rpi5_ramroot_format.h"
        header = kernel_build / "source" / relative
        if (f"#define RPI5_RFS_NODES {root_nodes}u" not in header.read_text() or
                kernel_record["effective_source_sha256"].get(relative) != digest(header)):
            raise RuntimeError("RAM-root capacity was not compiled into the selected kernel")
    assets, payload_records = {}, []
    for record in spec["files"]:
        source = (spec_path.parent / record["source"]).resolve(strict=True)
        if not source.is_file() or source.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("payload source must be a regular file no larger than 4 MiB")
        data = source.read_bytes()
        mode = 0o555 if record.get("executable") else 0o444
        if mode == 0o555:
            inspect_macho(data)  # No copied dynamically-linked macOS binaries.
        assets[record["path"]] = (data, mode)
        payload_records.append({"path": record["path"], "mode": mode, "sha256": hashlib.sha256(data).hexdigest()})
    if output.exists() or output.is_symlink():
        raise ValueError("output must be a new directory; existing packages are never overwritten")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    temporary = Path(tempfile.mkdtemp(prefix="darwin-workload-build-", dir="/private/tmp"))
    # Preserve failed build artifacts; nothing here is a VM or an attached disk.
    for guest_name in ("/bin/zsh", "/bin/dhcpctl", "/bin/resolverctl", "/etc/terminfo/64/dumb"):
        destination = temporary / ("terminfo/64/dumb" if guest_name.endswith("/dumb") else Path(guest_name).name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_files[guest_name][0])
    command = [sys.executable, str(HERE / "build.py"), "--output-dir", str(temporary / "root"),
               "--mode", "agent-zsh", "--storage", "--workload-profile", "--zsh-binary", str(temporary / "zsh"),
               "--terminfo-dir", str(temporary / "terminfo"), "--ramroot-max-nodes", str(root_nodes)]
    if spec["network"] == "nat":
        command += ["--network", "--network-config-binary", str(temporary / "dhcpctl"),
                    "--resolver-binary", str(temporary / "resolverctl")]
    root_build = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (temporary / "root-build.log").write_text(root_build.stdout + root_build.stderr)
    if root_build.returncode:
        raise RuntimeError(f"managed root build failed; inspect {temporary}")
    files = unpack_root((temporary / "root/ramdisk.bin").read_bytes(), max_nodes=root_nodes) | assets
    if utilities:
        for name, expected in utilities["commands"].items():
            if not name.isascii() or not name.isalnum():
                raise RuntimeError("invalid source-built command name")
            data, mode = source_files["/bin/" + name]
            if hashlib.sha256(data).hexdigest() != expected or mode != 0o555:
                raise RuntimeError("workspace utility differs from its build record")
            files["/bin/" + name] = (data, mode)
    files["/app/entry.zsh"] = (entry_script(spec), 0o444)
    root, root_report = build(files, max_nodes=root_nodes)
    if len(root) > 8 * 1024 * 1024:
        raise ValueError("packaged RAM root exceeds the qualified loader's 8 MiB limit")
    directories = {entry["path"] for entry in root_report["entries"] if entry["type"] == "directory"}
    if spec["cwd"] not in directories or spec["entrypoint"][0] not in files or files[spec["entrypoint"][0]][1] != 0o555:
        raise ValueError("cwd must exist and entrypoint must name an installed executable")
    (output / "ramdisk.bin").write_bytes(root)
    image_tool = EXPERIMENT / "efi-probe/.build-zsh/out/Products/Debug/vz-efi-image"
    loader_command = [sys.executable, str(EXPERIMENT / "build_loader.py"), "--kernel", str(kernel),
                      "--ramroot", str(output / "ramdisk.bin"), "--storage", "--image-tool", str(image_tool)]
    if spec["network"] == "nat":
        loader_command.append("--network")
    result = subprocess.run(loader_command, capture_output=True, text=True, timeout=120)
    (temporary / "loader-build.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"loader build failed; inspect {temporary}")
    loader_record = json.loads(result.stdout[result.stdout.index("{"):])
    loader = Path(loader_record["directory"])
    image = bytearray((loader / "efi.img").read_bytes())
    payload = bytearray((loader / "BOOTAA64.EFI").read_bytes())
    slot = loader_record["bootEntropySlot"]
    offset, position, count = slot["diskOffset"], slot["payloadOffset"], slot["bytes"]
    if count != 256 or image[offset-position:offset-position+len(payload)] != payload:
        raise RuntimeError("loader entropy-slot/payload mismatch")
    image[offset:offset+count] = bytes(count)
    payload[position:position+count] = bytes(count)
    (output / "efi-template.img").write_bytes(image)
    (output / "loader-template.efi").write_bytes(payload)
    for name in ("container", "data-template.raw"):
        copy_checked(workspace / name, output / name)
    copy_checked(kernel, output / "kernel.macho")
    copy_checked(kernel_build / "manifest.json", output / "provenance/workload-kernel-build.json")
    for relative in ("osfmk/prng/prng_random.c", "iokit/Kernel/VZGenericPlatformExpert.cpp"):
        copy_checked(kernel_build / "source" / relative, output / "provenance/kernel-source" / relative)
    for source, name in ((HERE / "workload_runner.py", "darwin"), (HERE / "workspace_launcher.py", "support/workspace_launcher.py")):
        copy_checked(source, output / name)
    for source in (workspace / "provenance").rglob("*"):
        if source.is_file():
            copy_checked(source, output / "provenance/workspace" / source.relative_to(workspace / "provenance"))
    copy_checked(temporary / "root/manifest.json", output / "provenance/agent-root-build.json")
    copy_checked(loader / "manifest.json", output / "provenance/loader-build.json")
    copy_checked(HERE / "source-provenance.json", output / "provenance/bootstrap-utilities.json")
    for source in (HERE / "build.py", HERE / "pack_darwin_workload.py", HERE / "ramroot.py"):
        copy_checked(source, output / "provenance/build-sources" / source.name)
    for source in (HERE / "src").glob("*"):
        if source.is_file():
            copy_checked(source, output / "provenance/agent-source" / source.name)
    # Retain all already-collected component notices rather than inventing a
    # single license for the Apple kernel, runtime and downstream host runner.
    notices = HERE / "build/darwin-workload-0.1.0/licenses"
    if not notices.is_dir():
        raise RuntimeError("qualified component notices missing")
    for source in notices.rglob("*"):
        if source.is_file():
            copy_checked(source, output / "licenses" / source.relative_to(notices))
    for relative in ("container/LICENSE", "container/NOTICE.md", "containerization/LICENSE"):
        source = EXPERIMENT / relative
        copy_checked(source, output / "licenses" / relative.replace("/", "-"))
    if spec["network"] == "nat":
        for component in ("apple-libresolv-96", "apple-Libinfo-542.40.3", "apple-bootp-268.1"):
            copy_checked(HERE / "upstream" / component / "APPLE_LICENSE", output / "licenses" / (component + "-APPLE_LICENSE"))
    for source in (HERE / "build/darwin-workload-0.1.0/provenance/apple-runtime").glob("*.json"):
        copy_checked(source, output / "provenance/apple-runtime" / source.name)
    packaged_spec = {key: value for key, value in spec.items() if key != "files"} | {"files": payload_records}
    (output / "workload.json").write_text(json.dumps(packaged_spec, indent=2) + "\n")
    (output / "provenance/ramroot.json").write_text(json.dumps(root_report, indent=2) + "\n")
    for path in output.rglob("*"):
        if path.is_file():
            path.chmod(0o700 if path.name in ("darwin", "container") else 0o600)
    manifest = {"format": "darwin-workload-package-1", "version": "0.4.0" if utilities else "0.3.0", "name": spec["name"],
                "ramroot_max_nodes": root_nodes, "apple_utilities": utilities,
                "workload_version": spec["version"], "boot_entropy_slot": slot, "data_bytes": base["data_bytes"],
                "base_workspace_manifest_sha256": digest(workspace / "manifest.json"),
                "runtime": {"kernel": "source-built XNU VZGENERIC ARM64", "shell": "official Apple-source zsh 5.9",
                            "cpus": 1, "memory_mib": 512, "kernel_arena_mib": 320, "protocol": "DGA1"},
                "immutable_sha256": {str(path.relative_to(output)): digest(path) for path in sorted(output.rglob("*")) if path.is_file()},
                "limitations": ["Mac Apple-silicon Virtualization.framework host only", "not OCI or Linux binary compatibility",
                                "static no-import ARM64 executables and scripts; no full macOS runtime",
                                f"{root_nodes} total RAM-root nodes and 8 MiB root; stdin EOF; 1 MiB combined output cap",
                                "VM-per-workload, not production hostile-tenant isolation", "no power-loss durability guarantee"]}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return {"package": str(output), "manifest_sha256": digest(output / "manifest.json"),
            "workload": spec["name"], "files": len(payload_records), "ramroot_nodes": len(root_report["entries"]),
            "run": str(output / "darwin") + " run", "build_evidence": str(temporary)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workspace-package", type=Path, default=HERE / "build/darwin-workspace-0.4.2")
    parser.add_argument("--kernel-build", type=Path, help="completed isolated kernel build; defaults to workload-runtime.json pin")
    args = parser.parse_args()
    print(json.dumps(package(args.spec, args.output, args.workspace_package, args.kernel_build), indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"darwin-workload pack: {error}", file=sys.stderr)
        raise SystemExit(1)
