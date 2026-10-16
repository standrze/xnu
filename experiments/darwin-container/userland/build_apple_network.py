#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compile pinned, unmodified Apple DNS wire-parser sources for the guest."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_parser(out, compiler, sdk):
    lock_path = HERE / "apple-network.sources.lock.json"
    pin = json.loads(lock_path.read_text())
    source = HERE / pin["localPath"]
    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()
    if git("rev-parse", "HEAD") != pin["commit"] or git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("official Apple resolver checkout does not match the clean pinned commit")
    directory = out / "apple-network"
    directory.mkdir(exist_ok=False)
    commands, objects = [], []
    for name in pin["selectedSources"]:
        obj = directory / (Path(name).stem + ".o")
        command = [compiler, "-isysroot", sdk, "-target", "arm64-apple-darwin", "-c", "-Os",
                   "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-D_FORTIFY_SOURCE=0",
                   "-D__FBSDID(x)=", "-Werror=implicit-function-declaration", "-Wno-deprecated-declarations",
                   "-I", str(source), str(source / name), "-o", str(obj)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (directory / (name + ".log")).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"Apple resolver compile failed: {name}\n{result.stderr}")
        commands.append(command)
        objects.append(str(obj))
    inputs = [source / name for name in pin["selectedSources"]]
    inputs += [source / name for name in ("arpa/nameser.h", "nameser.h", "resolv.h", "port_before.h", "port_after.h", "APPLE_LICENSE")]
    report = {"source_pin": pin, "source_sha256": {str(p.relative_to(source)): digest(p) for p in inputs},
              "lock_sha256": digest(lock_path), "builder_sha256": digest(Path(__file__)),
              "commands": commands, "host_runtime_linked": False,
              "scope": "compiled original Apple DNS wire-parser objects; no guest execution or full resolver claim"}
    (directory / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return objects, source
