#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Plan by default; fixed read-only PCIe power/clock/IRQ Linux reference."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

try:
    from . import pcie_reference_core as reference
    from . import pcie_lifecycle_reference_core as core
except ImportError:
    import pcie_reference_core as reference
    import pcie_lifecycle_reference_core as core

ROOT = Path(__file__).resolve().parents[2]
SOURCES = (Path(__file__), Path(reference.__file__), Path(core.__file__))


def hashes():
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in SOURCES}


def remote_source():
    # Distinct module namespace keeps the original strict allowlist unchanged.
    return ("import json\nimport types\nreference = types.ModuleType('pcie_reference_core')\nexec(" +
            repr(Path(reference.__file__).read_text()) + ", reference.__dict__)\n" +
            Path(core.__file__).read_text() +
            "\nprint(json.dumps(capture_lifecycle(reference), sort_keys=True))\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="NEW local evidence directory")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    before = hashes()
    remote = remote_source()
    plan = {"host": reference.HOST, "execute": args.execute,
            "root_identity": reference.ROOT_IDENTITY, "source_sha256": before,
            "remote_program_sha256": hashlib.sha256(remote.encode()).hexdigest(),
            "extra_property_allowlist": core.EXTRA_PROPERTIES,
            "operations": core.OPERATIONS, "limitations": core.LIMITATIONS}
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    if not args.execute:
        print(json.dumps({"plan_only": True, "output": str(out)}))
        return 0
    result = {"passed": False, "ssh_attempted": False, "remote_outcome": "not-started"}
    try:
        if hashes() != before or remote_source() != remote:
            raise ValueError("source changed before SSH")
        result.update(ssh_attempted=True, remote_outcome="unknown")
        response = subprocess.run([
            "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=8", reference.HOST, "sudo -n python3 -",
        ], input=remote, text=True, capture_output=True, timeout=45)
        (out / "remote.stdout").write_text(response.stdout)
        (out / "remote.stderr").write_text(response.stderr)
        result.update(remote_outcome="exited", remote_exit_code=response.returncode)
        response.check_returncode()
        report = json.loads(response.stdout)
        decoded = core.validate_lifecycle(report, reference)
        if hashes() != before:
            raise ValueError("source changed during capture")
        result.update(passed=True, decoded=decoded, source_sha256=before,
                      boot_id=report["identity_after"]["boot_id"],
                      reference_sha256=hashlib.sha256(response.stdout.encode()).hexdigest(),
                      limitations=core.LIMITATIONS)
    except subprocess.TimeoutExpired as error:
        for name, value in (("partial.stdout", error.stdout), ("partial.stderr", error.stderr)):
            if value is not None:
                (out / name).write_bytes(value.encode() if isinstance(value, str) else value)
        result["error"] = str(error)
        raise
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        (out / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": True, "output": str(out), "decoded": decoded}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
