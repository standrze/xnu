#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserve the completed zsh smoke trial without booting or testing a VM."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--loader-dir", required=True, type=Path)
    ap.add_argument("--session-dir", required=True, type=Path)
    ap.add_argument("--variable-template", required=True, type=Path)
    ap.add_argument("--output-dir", required=True, type=Path)
    args = ap.parse_args()
    result = json.loads((args.session_dir / "result.json").read_text())
    serial = (args.session_dir / "serial.bin").read_bytes().replace(b"\r", b"")
    proof = [b"APPLE_ZSH:5.9\n", b"BUILTINS:zsh:42\n",
             b"Darwin  12377.121.6 arm64\n", b"PROMPT_RETURNED\n"]
    cursor = 0
    for marker in proof:
        cursor = serial.index(marker, cursor) + len(marker)
    if b"darwin-zsh# " not in serial[cursor:]:
        raise RuntimeError("no prompt after the final actual-output marker")
    if not result["guestStopped"] or result["termination"] != "guestStopped":
        raise RuntimeError("guest did not stop cleanly")
    if b"DARWIN:ZSH:FAULT" in serial:
        raise RuntimeError("fault trace in successful-trial evidence")
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    copies = {
        args.loader_dir / "efi.img": "efi.img",
        args.loader_dir / "BOOTAA64.EFI": "BOOTAA64.EFI",
        args.loader_dir / "manifest.json": "loader-manifest.json",
        args.variable_template: "efi-variables-template.bin",
        HERE / "build/zsh-static-diagnostic-2/zsh": "zsh",
        HERE / "build/zsh-static-diagnostic-2/manifest.json": "link-manifest.json",
        HERE / "build/zsh-root-diagnostic-2/ramdisk.bin": "ramdisk.bin",
        HERE / "build/zsh-root-diagnostic-2/manifest.json": "root-manifest.json",
        HERE / "apple-zsh-source.json": "provenance/apple-zsh-source.json",
        HERE / "apple-runtime.sources.lock.json": "provenance/apple-runtime.sources.lock.json",
    }
    for directory, name in [("zsh-core-minimum-2", "probe.json"),
                            ("darwin-abi-diagnostic-2", "manifest.json"),
                            ("apple-runtime", "manifest.json"),
                            ("apple-posix", "manifest.json"),
                            ("apple-terminal-1", "manifest.json"),
                            ("apple-math-1", "manifest.json")]:
        copies[HERE / "build" / directory / name] = f"provenance/{directory}.json"
    for name in ("serial.bin", "serial.txt", "result.json", "preflight.json",
                 "start-requested.json", "started.json", "stopped.json"):
        copies[args.session_dir / name] = "evidence/" + name
    # Preserve the exact archives named in the final link, not just their hashes.
    link = json.loads((HERE / "build/zsh-static-diagnostic-2/manifest.json").read_text())
    for archive, expected in link["archives"].items():
        path = Path(archive)
        if digest(path) != expected:
            raise RuntimeError(f"archive changed since linking: {path}")
        copies[path] = f"archives/{path.parent.name}/{path.name}"
    for source in HERE.glob("*.py"):
        copies[source] = "build-scripts/" + source.name
    for source in (HERE / "runtime").rglob("*"):
        if source.is_file():
            copies[source] = "runtime/" + str(source.relative_to(HERE / "runtime"))
    for source in (HERE / "src").iterdir():
        if source.is_file():
            copies[source] = "bootstrap-src/" + source.name
    for name in ("config.h", "config.modules"):
        source = HERE / "build/zsh-core-minimum-2" / name
        copies[source] = "configuration/" + name
    copies[HERE / "build/zsh-static-diagnostic-2/link.map"] = "link.map"
    for source in (HERE / "build/darwin-abi-diagnostic-2/include").rglob("*"):
        if source.is_file():
            copies[source] = "abi-headers/" + str(source.relative_to(HERE / "build/darwin-abi-diagnostic-2/include"))
    for source, target in copies.items():
        dest = out / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    (out / "efi-variables-template.bin").chmod(0o600)
    report = {"scope": "actual interactive Apple-source zsh VM smoke; not Pi or complete Darwin qualification",
              "outcome": "passed", "proof": [p.decode().strip() for p in proof],
              "promptReturned": True, "guestStopped": True,
              "genericRunnerMarkers": "commandRequested=false and shellReadyObserved=false are expected in interactive mode; real zsh has no bootstrap/agent marker protocol",
              "privateLocalArtifact": "EFI payload/disk embed per-image entropy; do not publish this capsule or firmware variables",
              "sha256": {str(p.relative_to(out)): digest(p)
                         for p in sorted(out.rglob("*")) if p.is_file()}}
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"directory": str(out), "outcome": "passed", "files": len(report["sha256"])}))


if __name__ == "__main__":
    main()
