#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Two short workspace boots: Apple utility smoke then persistence readback."""
import argparse
import json
from pathlib import Path
import shlex

from workspace_launcher import digest, validate_package
from workspace_trial import Session

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    package = args.package.resolve()
    manifest = validate_package(package)
    script = HERE / "tests/apple_utilities_smoke.zsh"
    report = {"package": str(package), "manifest_sha256": digest(package / "manifest.json"),
              "script_sha256": digest(script), "runs": [], "passed": [], "error": None,
              "scope": "two short actual XNU workspace boots; utility examples and clean persistence; no soak or full option suite"}
    try:
        for boot in (1, 2):
            session = Session(package / "darwin", output / "workspaces", "apple-userland")
            try:
                session.wait(b"darwin-zsh#", 100)
                metadata = json.loads((output / "workspaces/apple-userland/workspace.json").read_text())
                session.directory = Path(metadata["last_run"])
                report["runs"].append(str(session.directory))
                if boot == 1:
                    # Keep terminal submissions short and acknowledge each;
                    # this exercises a terminal, not a bulk file-upload API.
                    for i, line in enumerate(script.read_text().splitlines()):
                        redirect = ">" if i == 0 else ">>"
                        session.send("print -r -- " + shlex.quote(line) + f" {redirect} /data/.apple-utilities-smoke.zsh; print -r -- UTIL_STAGED_{i}\n")
                        session.wait(f"\r\nUTIL_STAGED_{i}\r\n".encode(), 5)
                    session.send("/bin/zsh -f /data/.apple-utilities-smoke.zsh; print -r -- UTIL_EXIT:$?\n")
                    session.wait(b"\r\nUTIL_EXIT:", 30)
                    session.collect(0.1)
                    if b"\r\nUTIL_ALL_OK\r\n" not in session.capture or b"\r\nUTIL_EXIT:0\r\n" not in session.capture:
                        raise RuntimeError("Apple utility script failed: " + bytes(session.capture[-2400:]).decode(errors="replace"))
                    for name in manifest["apple_utilities"]["commands"]:
                        report["passed"].append(name + ": actual guest command exercised")
                else:
                    session.send("[[ $(/bin/cat /data/apple-userland-proof) == APPLE_USERLAND_PERSISTENCE ]]; print -r -- UTIL_RESTART:$?\n")
                    session.wait(b"\r\nUTIL_RESTART:0\r\n")
                    report["passed"].append("source-built cat read saved data after clean workspace restart")
                session.stop()
                report["passed"].append(f"boot {boot}: clean guest shutdown")
            finally:
                if session.process.poll() is None:
                    session.send("exit\n")
                    for unused in range(50):
                        session.collect(0.1)
                        if session.process.poll() is not None:
                            break
                session.close()
        validate_package(package)
    except Exception as error:
        report["error"] = str(error)
    finally:
        (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if report["error"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
