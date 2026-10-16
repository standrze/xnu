#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Independently qualify the immutable default-off recursive serial package."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.rpi5 import apple_pthread_recursive_serial_transport_v1 as transport
from tools.rpi5 import root_capacity_pthread as root_builder

PACKAGE = ROOT / "build/rpi5/apple-pthread-recursive-serial-v1-at_40hw7"
MANIFEST_SHA256 = "8ea50631c499b7d5e7e61ce3851c768d6f6ceddfe8e06854413a7fd038fd3d3d"
IMAGE_SHA256 = "599dab54c0974791c8255b2d81bf0c3825973b11bf8a902581ac508a1f71f276"
ROOT_SHA256 = "0d9243d287466e011d6114db1bc8bf018ecb539519461416143ce03c7555e0da"
NONCE = "0123456789abcdef0123456789abcdef"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def receipt(nonce=NONCE):
    return (b"xnu:/# command echo\r\nRMX:" + nonce.encode() + b":BEGIN\r\n"
            + transport.PASS_LINE + b"\r\nRMX:" + nonce.encode() + b":STATUS:0\r\nxnu:/# ")


def recovery(nonce=NONCE):
    return b"RMX:" + nonce.encode() + b":RECOVERY_STATUS:0\r\nxnu:/# "


def qualify(package=PACKAGE):
    package = Path(package).resolve()
    if package != PACKAGE.resolve() or sha(package / "manifest.json") != MANIFEST_SHA256:
        raise ValueError("exact immutable recursive serial package required")
    manifest = json.loads((package / "manifest.json").read_text())
    if (manifest.get("profile") != "apple-pthread-recursive-serial-default-off-v1"
            or manifest.get("default_off") is not True or manifest.get("hardware_execution") is not False
            or manifest.get("installed") is not False or manifest.get("pi_executed") is not False):
        raise ValueError("package is not an unexecuted default-off candidate")
    if manifest.get("image_sha256") != IMAGE_SHA256 or sha(manifest["image"]) != IMAGE_SHA256:
        raise ValueError("recursive boot image changed")
    if manifest.get("root_sha256") != ROOT_SHA256 or sha(manifest["root"]) != ROOT_SHA256:
        raise ValueError("recursive root image changed")
    if manifest.get("recursive_target_sha256") != transport.TARGET_SHA256:
        raise ValueError("recursive target binding changed")
    for key in ("inputs_sha256", "generated_sha256"):
        for name, digest in manifest[key].items():
            if sha(name) != digest:
                raise ValueError("sealed package closure drift: " + name)

    files = root_builder.old.profile.files_from(Path(manifest["root"]).read_bytes())
    if len(files) != 30 or hashlib.sha256(files[transport.TARGET_PATH][0]).hexdigest() != transport.TARGET_SHA256:
        raise ValueError("exact recursive executable is not embedded at the Apple-convention path")
    if files[transport.TARGET_PATH][1] != 0o555:
        raise ValueError("recursive executable mode changed")
    trial_marker = manifest["trial_marker"]
    if re.fullmatch(r"RPI5XNU:BL33:PTHREAD_RECURSIVE_TRIAL TAG=[0-9a-f]{32} CPUS=4 ROOT_NODES=42 WATCHDOG_READY_V2",
                    trial_marker) is None:
        raise ValueError("recursive boot marker changed")
    payload_offset = manifest["handoff"]["payload_offset"]
    raw = Path(manifest["image"]).read_bytes()
    if raw[:payload_offset].count((trial_marker + "\r\n\0").encode()) != 1:
        raise ValueError("recursive marker is not unique in loader bytes")
    contract = manifest.get("execution_contract")
    if contract != transport.execution_contract() or not manifest.get("automatic_return_and_restoration_required"):
        raise ValueError("bounded execution/return contract changed")

    command = transport.command(NONCE)
    recovery_command = transport.recovery_command(NONCE)
    accepted = transport.accept(receipt(), recovery(), NONCE, 1.25)
    if not accepted["recursive_mutex_target_execution_qualified"]:
        raise ValueError("synthetic exact receipt was not accepted")

    rejected = []
    mutations = {
        "depth": receipt().replace(b"DEPTH=3", b"DEPTH=2"),
        "eperm": receipt().replace(b"FOREIGN_EPERM=2", b"FOREIGN_EPERM=1"),
        "busy": receipt().replace(b"BUSY=2", b"BUSY=1"),
        "release": receipt().replace(b"RELEASED=1", b"RELEASED=0"),
        "status": receipt().replace(b"STATUS:0", b"STATUS:1"),
        "nonce": receipt().replace(NONCE.encode(), ("f" * 32).encode()),
        "duplicate": receipt() + b"\n" + transport.PASS_LINE,
        "order": receipt().replace(b"RMX:" + NONCE.encode() + b":BEGIN\r\n", b"")
                 + b"\nRMX:" + NONCE.encode() + b":BEGIN",
    }
    for name, raw_mutation in mutations.items():
        try:
            transport.accept(raw_mutation, recovery(), NONCE, 1)
        except ValueError:
            rejected.append(name)
        else:
            raise ValueError("mutation was accepted: " + name)
    for name, recovery_mutation in {
        "recovery_nonzero": recovery().replace(b"STATUS:0", b"STATUS:1"),
        "recovery_missing": b"xnu:/# ",
        "recovery_duplicate": recovery() + b"\n" + recovery(),
    }.items():
        try:
            transport.accept(receipt(), recovery_mutation, NONCE, 1)
        except ValueError:
            rejected.append(name)
        else:
            raise ValueError("mutation was accepted: " + name)
    try:
        transport.accept(receipt(), recovery(), NONCE, transport.COMMAND_DEADLINE_SECONDS + 1)
    except ValueError:
        rejected.append("deadline")
    else:
        raise ValueError("expired deadline was accepted")

    sources = (Path(__file__).resolve(), Path(transport.__file__).resolve(),
               ROOT / "tools/rpi5/build_apple_pthread_recursive_serial_package_v1.py",
               ROOT / "tools/rpi5/tests/test_apple_pthread_recursive_serial_transport_v1.py")
    return {
        "format": "apple-pthread-recursive-serial-transport-qualification-v1",
        "qualified": True,
        "default_off": True,
        "hardware_execution": False,
        "hardware_actions": 0,
        "package": str(package),
        "manifest_sha256": MANIFEST_SHA256,
        "image_sha256": IMAGE_SHA256,
        "root_sha256": ROOT_SHA256,
        "target_path": transport.TARGET_PATH,
        "target_sha256": transport.TARGET_SHA256,
        "trial_marker": trial_marker,
        "command": command,
        "recovery_command": recovery_command,
        "execution_contract": contract,
        "synthetic_parser_oracle": accepted,
        "mutation_rejections": sorted(rejected),
        "mutation_rejection_count": len(rejected),
        "source_sha256": {str(path): sha(path) for path in sources},
        "runtime_claims": ["recursive-depth-three", "foreign-owner-eperm-two",
                           "partial-release-busy-two", "final-release"],
        "excluded_claims": ["atfork-fork", "cancelable-variant", "filex-stream-locking",
                            "networking", "ssh-transport", "ssh-daemon"],
        "remaining_physical_action": "sealed stage, one bounded serial execution, automatic NVMe return, then sealed loader restoration",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=PACKAGE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = qualify(args.package)
    if args.output.exists():
        raise ValueError("qualification output already exists")
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"qualified": True, "output": str(args.output),
                      "sha256": sha(args.output), "hardware_actions": 0}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
