#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Plan by default; --execute collects fixed read-only Linux RP1/OF metadata."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

try:
    from . import pcie_reference_core as core
except ImportError:
    import pcie_reference_core as core

ROOT = Path(__file__).resolve().parents[2]
SOURCES = [Path(__file__), Path(core.__file__), ROOT / "tools/rpi5/pcie_reference_host.c"] + [
    ROOT / "loader/rpi5" / name for name in (
        "fdt.c", "fdt.h", "fdt_reg.c", "ranges.h", "pcie_fdt.c", "pcie_fdt.h",
        "pcie_resource_plan.c", "pcie_resource_plan.h",
    )
]


def hashes():
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in SOURCES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path, help="NEW local evidence directory")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    before = hashes()
    remote = Path(core.__file__).read_text() + "\nprint(json.dumps(capture_linux(), sort_keys=True))\n"
    plan = {"host": core.HOST, "mode": "execute" if args.execute else "plan-only",
            "root_identity": core.ROOT_IDENTITY, "property_allowlist": core.PROPERTIES,
            "remote_program_sha256": hashlib.sha256(remote.encode()).hexdigest(),
            "source_sha256": before, "sd_actions": 0, "mmio_accesses": 0,
            "pci_config_writes": 0, "network_changes": 0, "reboots": 0,
            "scope": "Filtered Linux reference, not XNU bridge/IRQ/DMA/network acceptance"}
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    if not args.execute:
        print(json.dumps({"plan_only": True, "output": str(out)}))
        return
    binary = out / "pcie-reference-check"
    command = ["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
               "-fsanitize=address,undefined", "-I", str(ROOT / "loader/rpi5"),
               str(ROOT / "tools/rpi5/pcie_reference_host.c")] + [
        str(ROOT / "loader/rpi5" / name) for name in (
            "fdt.c", "fdt_reg.c", "pcie_fdt.c", "pcie_resource_plan.c",
        )
    ] + ["-o", str(binary)]
    result = {"passed": False, "scope": plan["scope"], "compile_command": command,
              "ssh_attempted": False, "remote_outcome": "not-started"}
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=60)
        if hashes() != before:
            raise ValueError("source changed before SSH; not capturing")
        # No retry: even an uncertain capture outcome is preserved as such.
        result.update(ssh_attempted=True, remote_outcome="unknown")
        observed = subprocess.run([
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", core.HOST,
            "sudo -n python3 -",
        ], input=remote, text=True, capture_output=True, timeout=45)
        (out / "remote.stdout").write_text(observed.stdout)
        (out / "remote.stderr").write_text(observed.stderr)
        result.update(remote_outcome="exited", remote_exit_code=observed.returncode)
        if observed.returncode:
            raise ValueError(f"read-only capture failed ({observed.returncode})")
        report = json.loads(observed.stdout)
        bar = core.validate_capture(report)
        blob = core.encode_properties(report["first"]["of_properties_hex"])
        topology = out / "filtered-topology.dtb"
        topology.write_bytes(blob)
        decoded = subprocess.run([str(binary), str(topology), hex(bar["pci_base"]),
                                  hex(bar["size"]), hex(bar["cpu_base"])],
                                 text=True, capture_output=True, timeout=30)
        (out / "decoder.stdout").write_text(decoded.stdout)
        (out / "decoder.stderr").write_text(decoded.stderr)
        if decoded.returncode:
            raise ValueError(f"native topology/resource checker failed ({decoded.returncode})")
        if hashes() != before:
            raise ValueError("source changed during reference capture")
        result.update(passed=True, boot_id=report["identity_before"]["boot_id"],
                      reference_sha256=hashlib.sha256(observed.stdout.encode()).hexdigest(),
                      filtered_topology_sha256=hashlib.sha256(blob).hexdigest(),
                      decoded=json.loads(decoded.stdout), bar_observation=bar,
                      source_sha256=before, xnu_runtime_proven=False)
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
    print(json.dumps({"passed": True, "output": str(out), "decoded": result["decoded"]}))


if __name__ == "__main__":
    main()
