# SPDX-License-Identifier: BSD-2-Clause
"""Build the freestanding Gate 2 PID 1 and validate/package its raw RAMDisk."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shlex

from prepare_pid1 import inspect, inspect_process_literals

SOURCE = Path(__file__).with_name("pid1.S")


def run(*argv: str) -> str:
    completed = subprocess.run(argv, check=True, text=True, capture_output=True)
    return (completed.stdout or completed.stderr).strip()


def build(output_dir: Path, source: Path = SOURCE) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    compiler = run("xcrun", "--find", "clang")
    linker = run("xcrun", "--find", "ld")
    obj = output_dir / "pid1.o"
    executable = output_dir / "pid1"
    ramdisk = output_dir / "ramdisk.bin"
    compile_command = [compiler, "-target", "arm64-apple-darwin", "-c", str(source), "-o", str(obj)]
    link_command = [linker, "-arch", "arm64", "-static", "-e", "_start", "-no_adhoc_codesign",
                    "-o", str(executable), str(obj)]
    # Include preprocessed assembly dependencies in provenance (process trial
    # includes the proven terminal). No extra target compile/link is performed.
    dependencies = run(compiler, "-target", "arm64-apple-darwin", "-M", "-MT", "pid1", str(source))
    inputs = [Path(name) for name in shlex.split(dependencies.replace("\\\n", " ").split(":", 1)[1])]
    run(*compile_command)
    run(*link_command)
    raw = executable.read_bytes()
    result = inspect(raw)
    if b"RPI5XNU:PROC:TRIAL_READY" in raw:
        process_path = b"/bin/child" if b"RPI5XNU:RAMROOT:READY" in raw else b"/sbin/launchd"
        result["linked_process_literals"] = inspect_process_literals(raw, process_path)
    image = raw + bytes(result["ramdisk_size"] - len(raw))
    ramdisk.write_bytes(image)
    result.update({
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "object_sha256": hashlib.sha256(obj.read_bytes()).hexdigest(),
        "ramdisk_sha256": hashlib.sha256(image).hexdigest(),
        "compiler": compiler,
        "compiler_version": run(compiler, "--version").splitlines()[0],
        "linker": linker,
        "linker_version": run(linker, "-v").splitlines()[0],
        "commands": [compile_command, link_command],
        "source_inputs_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in inputs + [Path(__file__).resolve()]},
        "source_head": run("git", "-C", str(Path(__file__).resolve().parents[2]), "rev-parse", "HEAD"),
        "source_status": run("git", "-C", str(Path(__file__).resolve().parents[2]), "status", "--short"),
    })
    (output_dir / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source", type=Path, default=SOURCE,
                        help="freestanding PID 1 assembly source (default: Gate 2 ticker)")
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir, args.source), sort_keys=True))


if __name__ == "__main__":
    main()
