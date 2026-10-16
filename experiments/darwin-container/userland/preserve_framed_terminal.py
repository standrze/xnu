#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserve verified DGT1 terminal evidence and a private working VM snapshot."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("session", "previous-session", "loader", "ramroot", "zsh-build", "kernel-build",
                 "cli", "data-disk", "output", "working"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    for session in (args.previous_session, args.session):
        result = load(session / "result.json")
        trial = load(session / "terminal-trial.json")
        terminal = result.get("terminal", {})
        if not (result["started"] and result["guestStopped"] and result["termination"] == "guestStopped"
                and not result.get("error") and not trial["error"] and trial["cli_exit"] == 0
                and terminal.get("handshakeCompleted") and terminal.get("exitStatus") == 0
                and not terminal.get("error") and terminal.get("acknowledgedSizes") == [[35, 120], [47, 132]]
                and trial["cli_sha256"] == digest(args.cli)):
            raise RuntimeError(f"incomplete actual guest terminal trial: {session}")
    output = (args.session / "terminal-output.bin").read_bytes().replace(b"\r", b"")
    for marker in (b"\nFRAME_SAVED\n", b"print -r -- FRAME_SAVED >> /data/framed-note; exit",
                   b"\nZLE_EDIT\n", b"\nTERMINAL_TTY_JOB_OK\n", b"\nJOB_STATUS:130\n",
                   b"SIZE_CHANGED:47:132", b"BYTE_ROUNDTRIP:\x80\xff:END",
                   b"suspended", b"continued"):
        if marker not in output:
            raise RuntimeError(f"missing decoded guest output: {marker!r}")
    if output.count(b"\nFRAME_HISTORY_RECALL\n") != 2:
        raise RuntimeError("missing actual up-arrow history recall")
    root = load(args.ramroot / "manifest.json")
    loader = load(args.loader / "manifest.json")
    kernel = load(args.kernel_build / "manifest.json")
    link = load(args.zsh_build / "manifest.json")
    if not (root["framed_terminal"] and root["pty_relay"] and root["writable_storage"]
            and root["sha256"] == digest(args.ramroot / "ramdisk.bin") == loader["inputs"]["ramrootSHA256"]
            and root["apple_zsh"]["executable"]["sha256"] == link["sha256"] == digest(args.zsh_build / "zsh")
            and kernel["exit_code"] == 0 and loader["inputs"]["kernelSHA256"] in {k["sha256"] for k in kernel["kernels"]}
            and digest(Path(loader["inputs"]["kernelSource"])) == loader["inputs"]["kernelSHA256"]):
        raise RuntimeError("kernel/root/zsh provenance mismatch")
    args.output.mkdir(parents=True, exist_ok=False)
    for session, name in ((args.previous_session, "first-boot"), (args.session, "persistence-boot")):
        destination = args.output / name
        destination.mkdir()
        for source in session.iterdir():
            if source.is_file() and source.name != "efi-variables.bin":
                shutil.copy2(source, destination / source.name)
    for source, name in ((args.loader / "manifest.json", "loader-manifest.json"),
                         (args.ramroot / "manifest.json", "root-manifest.json"),
                         (args.zsh_build / "manifest.json", "zsh-link-manifest.json"),
                         (args.kernel_build / "manifest.json", "kernel-manifest.json"),
                         (HERE / "apple-zsh-source.json", "apple-zsh-source.json"),
                         (HERE / "TERMINAL-PROTOCOL.md", "TERMINAL-PROTOCOL.md")):
        shutil.copy2(source, args.output / name)
    evidence_files = {str(p.relative_to(args.output)): digest(p) for p in sorted(args.output.rglob("*")) if p.is_file()}
    report = {"outcome": "terminal-milestone-passed-not-full-goal", "proved": trial["passed"],
              "kernel_sha256": loader["inputs"]["kernelSHA256"], "zsh_sha256": link["sha256"],
              "remaining": ["real guest VirtIO network driver and address/DNS/TCP exchange",
                            "guest GPU request/client channel and returned real Metal result"],
              "limits": ["compctl module not linked", "no multibyte locale support", "not production isolation or a soak"],
              "sha256": evidence_files}
    (args.output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    # EFI embeds fresh entropy and firmware state. Never publish this directory.
    args.working.mkdir(parents=True, exist_ok=False, mode=0o700)
    files = {"efi.img": args.loader / "efi.img", "BOOTAA64.EFI": args.loader / "BOOTAA64.EFI",
             "kernel.macho": Path(loader["inputs"]["kernelSource"]), "ramdisk.bin": args.ramroot / "ramdisk.bin",
             "zsh": args.zsh_build / "zsh", "container": args.cli, "data.raw": args.data_disk,
             "efi-variables-template.bin": args.session / "efi-variables.bin"}
    for name, source in files.items():
        shutil.copy2(source, args.working / name)
        (args.working / name).chmod(0o700 if name == "container" else 0o600)
    (args.working / "manifest.json").write_text(json.dumps({
        "scope": "private working DGT1 terminal snapshot, not a versioned release or completed overall goal",
        "warning": "EFI and variables contain entropy; do not publish or treat seed reuse as production safe",
        "evidence": str(args.output.resolve()), "sha256": {name: digest(args.working / name) for name in files},
    }, indent=2) + "\n")
    print(args.output / "verification.json")
    print(args.working / "manifest.json")


if __name__ == "__main__":
    main()
