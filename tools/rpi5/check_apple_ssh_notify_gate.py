#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Default-off admission gate for the real Apple Libnotify prerequisite.

The OpenSSH link currently exposes notify_check and notify_register_check, but
the resolver uses a larger coherent API family.  This checker proves source
ownership and the public-SDK compilation boundary without replacing notifyd,
Mach/MIG, shared memory, XPC, dispatch, or regeneration behavior with doubles.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RESOLVER_REPORT = ROOT / "build/rpi5/apple-ssh-resolver-gate-20261014/report.json"
RESOLVER_REPORT_SHA256 = "a08929d2db4b2d3a16ec9e71ff918d40eceabc8f24961437ec376be6008843c0"
SOURCE = ROOT / "build/rpi5/apple-libnotify-main-candidate-20261014"
COMMIT = "715d461778f6b93c821d99390a0078bd6f6d8c04"

SOURCE_PINS = {
    "notify_client.c": "b3d6dc62ed4d93135b206111bafe18f7b0e225adcc2540ab631c24e3d98a5e48",
    "notify_internal.h": "ca2e09357d89a11eb40666c6a3ff50e4a51f6abbf0c5d386613ff22da88815cf",
    "notify_ipc.defs": "0f081ed9d8b0bc6f9b6d8fe5ba34f9d95a69c7d3c5373164ae31163034f70db3",
    "libnotify.c": "8bd83c18cd542b240a2771643aa895c880cf530b4911369644359c9697a0567c",
    "libnotify.h": "548c93fa143984b0b6a28c489442dc14696f74df1f7c3c7df97b9732f656f6f1",
    "notify.h": "c7bf63e398effebe5e8895f4b89eace820437cfdd9735ffeb99ed69707dd5bb3",
    "notify_private.h": "7fbd0fc627302851ff664aaa91495f56f2bfe8fea31a3d82e3897c610f4c950c",
    "table.c": "8c25c79a931c3c280a7b3632dec5cb162b24a610b6fb8a15e2b1783cd212ce43",
    "table.h": "49a1cdcfb95417a8e7bab9f1634d044b30354a3f43bd9f142ed0b6808594afb0",
    "Libnotify.xcodeproj/project.pbxproj": "40bc585bfa590e5b10ec7c6ee8f0ebcfd014cde02716a464a643099888b284a5",
    "xcodeconfig/base.xcconfig": "cb3a44afd467da6b87c3df07a35ca334a33c38010495a0b405427c1335000843",
    "xcodeconfig/libnotify.xcconfig": "7454a02694ac7629d7bf63bfda42e84089e0333ad10ce22e36b4726e63701682",
    "notifyd/notify_proc.c": "759940245a02da153267e04bae0ee08512648e40c6506854ac32638cb933cdd5",
    "notifyd/notifyd.c": "d0e73a638baa86bd614c358bacae6f1d2fca125e576d80f6e27997b803ad5bbf",
    "notifyd/pathwatch.c": "ddab625dcf37271d89b165f7071c486c4884f5a819e36fc904f3912129ba21d7",
    "notifyd/service.c": "35d02e58a79ece2304ab118eb29d3e145626ce7e477818b3711d4d4f172085ae",
    "tests/notify_regenerate.c": "c044982456b34054af62193ce47467fc0e2406d2e27ac39679694f9d84f7c899",
    "tests/notify_loopback.c": "780b73226d9e3738e7dbde12da5de8d20471d8d4efbdc23f28f958d0f3ba077d",
}

REQUIRED_PATTERNS = {
    "notify_client.c": [
        "notify_register_check(const char *name", "notify_check(int token",
        "bootstrap_look_up2(bootstrap_port, NOTIFY_SERVICE_NAME",
        "_notify_server_register_check_2", "_notify_server_check(",
        "shm_open(SHM_ID, O_RDONLY", "globals->shm_base[r->slot]",
        "regenerate_check(globals)", "notify_monitor_file(int token",
    ],
    "notify_ipc.defs": [
        "routine _notify_server_check", "routine _notify_server_register_check_2",
        "routine _notify_server_checkin", "routine _notify_server_regenerate",
    ],
    "libnotify.h": [
        '#define NOTIFY_SERVICE_NAME "com.apple.system.notification_center"',
        "#define NOTIFY_IPC_VERSION_MIN_SUPPORTED 3",
    ],
    "notifyd/notify_proc.c": [
        "__notify_server_register_check_2", "global.shared_memory_refcount[x]++",
        "__notify_server_check", "__notify_server_regenerate",
    ],
    "notifyd/notifyd.c": [
        "open_shared_memory(const char *name)", "shm_open(name, O_RDWR | O_CREAT",
        "dispatch_mach_mig_demux", "init_launch_config(service_name)",
    ],
    "notifyd/pathwatch.c": ["dispatch_source_create(DISPATCH_SOURCE_TYPE_VNODE", "sandbox_check_by_audit_token"],
    "xcodeconfig/libnotify.xcconfig": ["-ldispatch", "-lxpc", "-lsystem_collections"],
    "tests/notify_regenerate.c": ["notify_register_check", "notify_get_state", "NOTIFY_IPC_VERSION"],
}

CURRENT_IMPORTS = ["_notify_check", "_notify_register_check"]
REQUIRED_API = [
    "_notify_cancel", "_notify_check", "_notify_get_state",
    "_notify_monitor_file", "_notify_register_check", "_notify_register_plain",
]
NEWLY_REACHABLE = ["_notify_cancel", "_notify_get_state", "_notify_monitor_file", "_notify_register_plain"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_sources() -> None:
    commit = subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True).strip()
    if commit != COMMIT:
        raise ValueError("Exact Apple Libnotify commit required")
    for relative, digest in SOURCE_PINS.items():
        path = SOURCE / relative
        if sha256(path) != digest:
            raise ValueError(f"Apple Libnotify source drift: {relative}")
        expected = subprocess.check_output(["git", "-C", str(SOURCE), "show", f"{COMMIT}:{relative}"])
        if path.read_bytes() != expected:
            raise ValueError(f"Working source differs from Apple commit: {relative}")
        text = path.read_text()
        for pattern in REQUIRED_PATTERNS.get(relative, []):
            if pattern not in text:
                raise ValueError(f"Missing semantic ownership evidence: {relative}: {pattern}")


def public_sdk_compile_probe() -> dict[str, Any]:
    compiler = Path(subprocess.check_output(["xcrun", "--find", "clang"], text=True).strip()).resolve()
    sdk = Path(subprocess.check_output(["xcrun", "--show-sdk-path"], text=True).strip()).resolve()
    base = [
        str(compiler), "-target", "arm64-apple-darwin", "-mcpu=cortex-a76",
        "-ffreestanding", "-fblocks", "-fsyntax-only", "-isysroot", str(sdk),
        "-I", str(SOURCE),
    ]
    expected = {"notify_client.c": "bootstrap_priv.h", "libnotify.c": "os/lock_private.h"}
    results = {}
    for relative, header in expected.items():
        command = [*base, str(SOURCE / relative)]
        proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=30)
        match = re.search(r"fatal error: '([^']+)' file not found", proc.stderr)
        blocker = match.group(1) if match else None
        if proc.returncode == 0 or blocker != header:
            raise ValueError(f"Unexpected public-SDK compile boundary for {relative}: {blocker!r}")
        results[relative] = {"returncode": proc.returncode, "first_missing_private_header": blocker}
    return {
        "compiler": str(compiler), "compiler_sha256": sha256(compiler),
        "sdk": str(sdk), "units": results,
    }


def validate_report(report: dict[str, Any]) -> None:
    if report["resolver_gate_sha256"] != RESOLVER_REPORT_SHA256:
        raise ValueError("Wrong resolver predecessor")
    if report["current_unresolved_imports"] != CURRENT_IMPORTS:
        raise ValueError("Current notify import set changed")
    if report["required_api_closure"] != REQUIRED_API or report["newly_reachable_if_partial"] != NEWLY_REACHABLE:
        raise ValueError("Notify client API closure is incomplete")
    if report["admissible"] or report["provider_created"]:
        raise ValueError("Notify cannot pass without the real runtime/service")
    required = {
        "private_build_headers", "generated_mig_client_and_server",
        "bootstrap_privileged_service_registration", "notifyd_protocol_v3",
        "shared_memory_slot_lifecycle", "dispatch_restart_monitoring",
        "xpc_entitlement_semantics", "pathwatch_vnode_and_sandbox_semantics",
        "fork_and_regeneration_semantics", "target_behavior_tests",
    }
    if set(report["prerequisites"]) != required:
        raise ValueError("Notify prerequisite closure is incomplete")
    if any(report["forbidden_shortcuts"].values()):
        raise ValueError("A notify service facade or semantic shortcut was enabled")
    preservation = report["preservation"]
    if not all(preservation[k] for k in ("openssh_features_unchanged", "pam_enabled", "kerberos_gss_enabled", "filesystem_layout_unchanged")):
        raise ValueError("OpenSSH preservation contract changed")
    if any(preservation[k] for k in ("hardware_touched", "network_used", "target_executed", "accepted_runtime_modified")):
        raise ValueError("Software-only gate crossed its execution boundary")


def audit() -> dict[str, Any]:
    if sha256(RESOLVER_REPORT) != RESOLVER_REPORT_SHA256:
        raise ValueError("Exact resolver ownership report required")
    predecessor = json.loads(RESOLVER_REPORT.read_text())
    for symbol in CURRENT_IMPORTS:
        if symbol not in predecessor["remaining_imports"]:
            raise ValueError(f"Missing predecessor import: {symbol}")
    verify_sources()
    report: dict[str, Any] = {
        "profile": "apple-openssh-notify-service-admission-gate-v1",
        "resolver_gate": str(RESOLVER_REPORT),
        "resolver_gate_sha256": RESOLVER_REPORT_SHA256,
        "apple_libnotify_commit": COMMIT,
        "apple_source_sha256": SOURCE_PINS,
        "current_unresolved_imports": CURRENT_IMPORTS,
        "required_api_closure": REQUIRED_API,
        "newly_reachable_if_partial": NEWLY_REACHABLE,
        "compile_probe": public_sdk_compile_probe(),
        "service_contract": {
            "bootstrap_name": "com.apple.system.notification_center",
            "minimum_ipc_version": 3,
            "check_registration": "notifyd allocates/refcounts a shared-memory slot and returns its size, slot, and name id over MIG",
            "check_delivery": "client compares the daemon-owned shared-memory generation value under its check lock",
            "restart": "client watches notifyd, re-checks protocol/PID, and regenerates registrations after daemon restart",
            "path_monitoring": "notifyd owns vnode dispatch sources and sandbox/audit-token access checks",
        },
        "prerequisites": [
            "private_build_headers", "generated_mig_client_and_server",
            "bootstrap_privileged_service_registration", "notifyd_protocol_v3",
            "shared_memory_slot_lifecycle", "dispatch_restart_monitoring",
            "xpc_entitlement_semantics", "pathwatch_vnode_and_sandbox_semantics",
            "fork_and_regeneration_semantics", "target_behavior_tests",
        ],
        "forbidden_shortcuts": {
            "always_unchanged_notify_check": False,
            "in_process_only_registry": False,
            "forced_self_prefix": False,
            "forced_loopback_entitlement": False,
            "fake_bootstrap_port": False,
            "fake_mig_replies": False,
            "fixed_shared_memory_slot": False,
            "disabled_restart_regeneration": False,
            "disabled_path_monitoring": False,
            "feature_disabling": False,
        },
        "admissible": False,
        "provider_created": False,
        "reason": "The current public SDK cannot compile the unchanged client, and correct register/check behavior requires a privileged notifyd protocol-v3 service, daemon-owned shared memory, restart regeneration, dispatch/XPC, and pathwatch semantics.",
        "preservation": {
            "openssh_features_unchanged": True, "pam_enabled": True,
            "kerberos_gss_enabled": True, "filesystem_layout_unchanged": True,
            "filesystem_layout": ["/usr/bin/ssh", "/usr/sbin/sshd", "/usr/libexec", "/private/etc/ssh"],
            "hardware_touched": False, "network_used": False,
            "target_executed": False, "accepted_runtime_modified": False,
        },
        "next_admission_sequence": [
            "close the exact Apple private-header and generated-MIG build inputs without invented declarations",
            "compose the original libnotify client, collections, Blocks, dispatch, XPC, Mach and bootstrap owners",
            "port and launch the original notifyd protocol-v3 server with daemon-owned shared memory",
            "qualify check registration, first/unchanged/changed checks, cancellation and slot reuse",
            "qualify daemon restart regeneration, fork behavior, concurrent registration and path monitoring",
            "link the complete six-API resolver notify family and require no new unresolved or duplicate symbols",
        ],
    }
    validate_report(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit()
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
    print(payload, end="")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
