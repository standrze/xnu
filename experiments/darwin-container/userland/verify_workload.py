#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Audit/preserve focused workload evidence. Never boots a VM or copies EFI state."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from ramroot import inspect as inspect_root


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def managed(session, statuses):
    result = json.loads((session / "result.json").read_text())
    agent = result["agent"]
    require(result["started"] and result["guestStopped"] and result["termination"] == "guestStopped",
            "missing actual managed guest stop")
    require(agent["handshakeCompleted"] and agent["protocolValid"] and agent["shutdownAcknowledged"],
            "incomplete framed lifecycle")
    require([command["exitStatus"] for command in agent["commands"]] == statuses,
            "unexpected command exit statuses")
    for command in agent["commands"]:
        require(command["terminalObserved"] and command["cleanupVerified"]
                and command["stdoutEOF"] and command["stderrEOF"] and not command["outputLimit"],
                "incomplete command cleanup/streams")
        for stream in ("stdout", "stderr"):
            require(len((session / command[stream + "Path"]).read_bytes()) == command[stream + "ByteCount"],
                    "captured stream length mismatch")
    require(result["commandSucceeded"] == all(status == 0 for status in statuses),
            "incorrect command success claim")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--managed-session", required=True, type=Path)
    parser.add_argument("--write-session", required=True, type=Path)
    parser.add_argument("--restart-session", required=True, type=Path)
    parser.add_argument("--package-session", required=True, type=Path)
    parser.add_argument("--failed-session", action="append", type=Path, default=[])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.package / "manifest.json").read_text())
    for name, expected in manifest["immutable_sha256"].items():
        require(digest(args.package / name) == expected, f"package input changed: {name}")
    zsh_hash = digest(args.package / "zsh")
    for mode in ("agent", "interactive"):
        root_path = args.package / f"ramroot-{mode}.bin"
        image = root_path.read_bytes()
        root = inspect_root(image)
        entries = {item["path"]: item for item in root["entries"]}
        require("/data" in entries and "/bin/zsh" in entries, "missing shell or mount point")
        zsh = entries["/bin/zsh"]
        require(hashlib.sha256(image[zsh["offset"]:zsh["offset"] + zsh["size"]]).hexdigest() == zsh_hash,
                "root does not contain packaged Apple-source zsh")
        loader = json.loads((args.package / f"provenance/loader-{mode}.json").read_text())
        require(loader["writableStorageProfile"]
                and loader["inputs"]["kernelSHA256"] == digest(args.package / "kernel.macho")
                and loader["inputs"]["ramrootSHA256"] == digest(root_path), "loader input mismatch")
    interactive = json.loads((args.package / "provenance/ramroot-interactive.json").read_text())
    require(interactive["interactive_shell"]["arguments"] == ["-i"], "history startup disabled")
    managed(args.managed_session, [0, 7])
    require(b"MANAGED_ZSH:5.9\n" in (args.managed_session / "command-1-stdout.bin").read_bytes()
            and b"ZSH_STDERR\n" in (args.managed_session / "command-1-stderr.bin").read_bytes(),
            "missing real managed shell/separate stderr evidence")
    managed(args.write_session, [0, 0])
    require((args.write_session / "command-1-stdout.bin").read_bytes() == b"WRITE_OK\n"
            and (args.write_session / "command-2-stdout.bin").read_bytes() == b"HISTORY_SAVED\n",
            "missing actual successful write output")
    restart = json.loads((args.restart_session / "result.json").read_text())
    serial = (args.restart_session / "serial.bin").read_bytes().replace(b"\r", b"")
    require(restart["guestStopped"] and restart["termination"] == "guestStopped", "restart did not stop")
    for marker in (b"RESTORED_FILE:PERSISTED_FILE\n", b"\nPERSISTED_SCRIPT\n", b"  SAVED_HISTORY\n",
                   b"DARWIN:INIT:ZSH_STOPPED:WAIT_STATUS=0\n", b"DARWIN:POWEROFF:REQUEST\n"):
        require(marker in serial, f"missing restart output: {marker!r}")
    managed(args.package_session, [0])
    stdout = (args.package_session / "command-1-stdout.bin").read_bytes()
    for marker in (b"PACKAGE_ZSH:5.9\n", b"PERSISTED_FILE\n", b"PERSISTED_SCRIPT\n",
                   b"SAVED_HISTORY\n", b"print -r -- INTERACTIVE_HISTORY_MARKER\n", b"exit\n"):
        require(marker in stdout, f"missing packaged command output: {marker!r}")
    args.output.mkdir(parents=True, exist_ok=False)
    sessions = [("managed", args.managed_session), ("write", args.write_session),
                ("restart", args.restart_session), ("package", args.package_session)]
    sessions += [(f"failed-{index + 1}", path) for index, path in enumerate(args.failed_session)]
    for label, session in sessions:
        destination = args.output / label
        destination.mkdir()
        for path in session.iterdir():
            if path.is_file() and path.name != "efi-variables.bin":
                shutil.copy2(path, destination / path.name)
    shutil.copy2(args.package / "manifest.json", args.output / "package-manifest.json")
    shutil.copytree(args.package / "provenance", args.output / "provenance")
    report = {
        "outcome": "passed", "package_version": manifest["version"],
        "scope": "focused Apple-silicon VM workload milestone; no Pi or production isolation claim",
        "requirements": {
            "managed_real_apple_zsh": "actual 5.9 output; separate streams; exits 0 and 7; acknowledged shutdown",
            "writable_storage": "managed file/script/history write; separate VM read; normal interactive history saved and reread",
            "versioned_package": "immutable hashes and embedded zsh checked; packaged launcher booted command and stopped",
        },
        "package": str(args.package.absolute()), "immutable_files_verified": len(manifest["immutable_sha256"]),
        "kernel_sha256": digest(args.package / "kernel.macho"), "zsh_sha256": zsh_hash,
        "data_disk_after_trial_sha256": digest(args.package / "data.raw"),
        "limitations": manifest["limitations"],
        "evidence_sha256": {str(p.relative_to(args.output)): digest(p)
                            for p in sorted(args.output.rglob("*")) if p.is_file()},
    }
    (args.output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": report["outcome"], "report": str(args.output / "verification.json")}))


if __name__ == "__main__":
    main()
