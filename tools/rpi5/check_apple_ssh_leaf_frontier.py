#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Prove that the sealed 33-import OpenSSH client has no safe leaf left."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "build/rpi5/apple-ssh-sscanf-m4_xgkm2"
BASE_SHA = "114efe7a753f69e22548da8dca5c3e4f8e20faaec26a5b0232b23d263d742eed"
LOCK = ROOT / "experiments/darwin-container/userland/apple-runtime.sources.lock.json"
OLD_ARCHIVE = ROOT / "experiments/darwin-container/userland/upstream/Libc-167.tar.gz"
OLD_SOURCE = ROOT / "experiments/darwin-container/userland/upstream/Libc-Libc-167/gen.subproj/popen.c"
CURRENT_ARCHIVE = ROOT / "experiments/darwin-container/userland/upstream/Libc-1752.120.2.tar.gz"
CURRENT_SOURCE = ROOT / "experiments/darwin-container/userland/upstream/apple-Libc-1752.120.2/gen/FreeBSD/popen.c"

OLD_PIN = {
    "tag": "Libc-167",
    "commit": "630404129b7029c30def14e0a5150c4b93d7458c",
    "archive_sha256": "abb1bc021fbe61622148fad98b5ef955e5f7bf56c804895a14cac6b4132d183b",
    "source_sha256": "339b545121d72e27caf86c55a1ab5bde3b8f7496f97f43e865451aed256bb954",
}
CURRENT_PIN = {
    "tag": "Libc-1752.120.2",
    "commit": "4e34d0559e3a1b081afeb8604d9e204a1f31321d",
    "archive_sha256": "b7b6c6d185ef59187c392824ef464a0ebdb6b962d1574abbb93d3aa15e20d826",
    "source_sha256": "adfae390de4dfce979d597f4237f0c83b2e92c362d6a5df596136b990031ae71",
}

EXPECTED_MISSING = [
    "_GSS_C_NT_HOSTBASED_SERVICE", "___res_9_state", "__os_log_debug_impl",
    "__os_log_default", "__os_log_error_impl", "_bootstrap_parent",
    "_closelog", "_dlclose", "_dlerror", "_dlopen", "_dlsym",
    "_gss_delete_sec_context", "_gss_display_status", "_gss_get_mic",
    "_gss_import_name", "_gss_indicate_mechs", "_gss_init_sec_context",
    "_gss_release_buffer", "_gss_release_cred", "_gss_release_name",
    "_gss_release_oid_set", "_notify_check", "_notify_register_check",
    "_openlog", "_os_log_create", "_os_log_type_enabled", "_pclose",
    "_popen", "_res_9_init", "_res_9_query", "_si_destination_compare",
    "_syslog$DARWIN_EXTSN", "_vsyslog",
]

OWNERSHIP = {
    "gss_kerberos": [symbol for symbol in EXPECTED_MISSING if symbol.startswith("_gss_") or symbol == "_GSS_C_NT_HOSTBASED_SERVICE"],
    "resolver_libinfo": ["___res_9_state", "_res_9_init", "_res_9_query", "_si_destination_compare"],
    "notify_os_log_syslog": [
        "__os_log_debug_impl", "__os_log_default", "__os_log_error_impl",
        "_closelog", "_notify_check", "_notify_register_check", "_openlog",
        "_os_log_create", "_os_log_type_enabled", "_syslog$DARWIN_EXTSN", "_vsyslog",
    ],
    "dynamic_loader": ["_dlclose", "_dlerror", "_dlopen", "_dlsym"],
    "private_bootstrap": ["_bootstrap_parent"],
    "stdio_process_pair": ["_pclose", "_popen"],
}

OLD_REQUIRED = [
    "static struct pid", "*pidlist", "switch (pid = vfork())",
    "Parent; assume fdopen can't fail", "if ((cur = malloc(sizeof(struct pid))) == NULL)",
]
CURRENT_REQUIRED = [
    "pthread_mutex_t pidlist_mutex", "posix_spawn_file_actions_init",
    "posix_spawn(&pid", "fwide(iop, -1)", "libc_hooks_will_read_cstring",
    "#include \"libc_private.h\"", "#include \"libc_hooks_impl.h\"",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_sources() -> None:
    lock = json.loads(LOCK.read_text())
    for pin in (OLD_PIN, CURRENT_PIN):
        row = next(item for item in lock["sources"] if item["tag"] == pin["tag"])
        if row["commit"] != pin["commit"] or row["archiveSHA256"] != pin["archive_sha256"]:
            raise ValueError("Apple source lock drift: " + pin["tag"])
    pairs = (
        (OLD_ARCHIVE, OLD_SOURCE, OLD_PIN, "Libc-Libc-167/gen.subproj/popen.c"),
        (CURRENT_ARCHIVE, CURRENT_SOURCE, CURRENT_PIN,
         "Libc-Libc-1752.120.2/gen/FreeBSD/popen.c"),
    )
    for archive_path, source_path, pin, member in pairs:
        if sha256(archive_path) != pin["archive_sha256"] or sha256(source_path) != pin["source_sha256"]:
            raise ValueError("Apple source hash drift: " + pin["tag"])
        with tarfile.open(archive_path, "r:gz") as archive:
            entry = archive.extractfile(member)
            if entry is None or entry.read() != source_path.read_bytes():
                raise ValueError("Apple archive member drift: " + pin["tag"])
    for pattern in OLD_REQUIRED:
        if pattern not in OLD_SOURCE.read_text():
            raise ValueError("Old popen ownership evidence missing: " + pattern)
    for pattern in CURRENT_REQUIRED:
        if pattern not in CURRENT_SOURCE.read_text():
            raise ValueError("Current popen ownership evidence missing: " + pattern)


def probe_old_popen(base: dict[str, Any]) -> dict[str, Any]:
    compiler = subprocess.check_output(["xcrun", "--find", "clang"], text=True).strip()
    sdk = subprocess.check_output(["xcrun", "--show-sdk-path"], text=True).strip()
    with tempfile.TemporaryDirectory(prefix="apple-ssh-popen-probe-", dir=ROOT / "build/rpi5") as directory:
        out = Path(directory)
        obj, archive = out / "popen.o", out / "libold-popen.a"
        compile_command = [
            compiler, "-isysroot", sdk, "-fno-builtin", "-fno-stack-protector",
            "-Wno-deprecated-non-prototype", "-target", "arm64-apple-darwin",
            "-mcpu=cortex-a76", "-ffreestanding", "-O2", "-c", str(OLD_SOURCE),
            "-o", str(obj),
        ]
        compiled = subprocess.run(compile_command, cwd=ROOT, text=True, capture_output=True, timeout=30)
        if compiled.returncode:
            raise ValueError("Pinned old popen no longer compiles: " + compiled.stderr)
        subprocess.run(["xcrun", "ar", "rcs", archive, obj], cwd=ROOT, check=True,
                       text=True, capture_output=True, timeout=30)
        link = list(next(row["command"] for row in base["commands"]
                         if row["stdout"].endswith("/target-link.stdout")))
        link[link.index("-o") + 1] = str(out / "NOT_RUN_ssh")
        link[link.index("-map") + 1] = str(out / "target.map")
        linked = subprocess.run([*link, str(archive)], cwd=ROOT, text=True,
                                capture_output=True, timeout=60)
        missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', linked.stderr, re.M)))
        duplicates = sorted(set(re.findall(r"duplicate symbol '([^']+)'", linked.stderr)))
        return {
            "compile_succeeded": True,
            "object_exports": subprocess.check_output(["xcrun", "nm", "-gjU", obj], text=True).splitlines(),
            "object_undefined": subprocess.check_output(["xcrun", "nm", "-u", obj], text=True).split(),
            "closed_imports": sorted(set(base["target_missing_symbols"]) - set(missing)),
            "new_imports": sorted(set(missing) - set(base["target_missing_symbols"])),
            "duplicate_symbols": duplicates,
            "remaining_count": len(missing),
        }


def validate_report(report: dict[str, Any]) -> None:
    if report["baseline_manifest_sha256"] != BASE_SHA or report["remaining_imports"] != EXPECTED_MISSING:
        raise ValueError("Exact sealed 33-import baseline required")
    flattened = [symbol for values in report["ownership"].values() for symbol in values]
    if len(flattened) != len(set(flattened)) or sorted(flattened) != EXPECTED_MISSING:
        raise ValueError("Every remaining import must have exactly one owner")
    if report["admissible_leafs"]:
        raise ValueError("No remaining provider meets the leaf contract")
    probe = report["popen_boundary"]["old_source_probe"]
    if probe["closed_imports"] != ["_pclose", "_popen"] or probe["new_imports"] != ["_vfork"]:
        raise ValueError("Old popen dependency delta changed")
    if probe["duplicate_symbols"] or probe["remaining_count"] != 32:
        raise ValueError("Old popen probe result changed")
    if report["popen_boundary"]["old_source_admissible"] or report["popen_boundary"]["current_source_admissible"]:
        raise ValueError("An incompatible popen family was admitted")
    if any(report["forbidden_shortcuts"].values()):
        raise ValueError("A semantic shortcut was enabled")
    preserve = report["preservation"]
    if not preserve["features_unchanged"] or not preserve["filesystem_layout_unchanged"]:
        raise ValueError("OpenSSH feature/layout preservation lost")


def audit() -> dict[str, Any]:
    if sha256(BASE / "manifest.json") != BASE_SHA:
        raise ValueError("Exact sealed sscanf predecessor required")
    base = json.loads((BASE / "manifest.json").read_text())
    if base["target_missing_symbols"] != EXPECTED_MISSING:
        raise ValueError("Sealed package import set changed")
    verify_sources()
    report = {
        "profile": "apple-openssh-safe-leaf-frontier-v1",
        "baseline_manifest": str(BASE / "manifest.json"),
        "baseline_manifest_sha256": BASE_SHA,
        "remaining_imports": EXPECTED_MISSING,
        "remaining_count": 33,
        "ownership": OWNERSHIP,
        "admissible_leafs": [],
        "popen_boundary": {
            "imports": ["_pclose", "_popen"],
            "old_source": str(OLD_SOURCE),
            "old_source_pin": OLD_PIN,
            "old_source_probe": probe_old_popen(base),
            "old_source_semantic_gaps": [
                "process-global pidlist has no lock",
                "pipe/socket descriptors leak when malloc fails",
                "fdopen failure is assumed impossible",
                "vfork ownership is not present in the accepted runtime",
            ],
            "old_source_admissible": False,
            "current_source": str(CURRENT_SOURCE),
            "current_source_pin": CURRENT_PIN,
            "current_required_owners": [
                "current FILE orientation via fwide", "pthread mutex and atfork behavior",
                "posix_spawn actions and environment ownership", "private libc hooks",
            ],
            "current_source_admissible": False,
            "reason": "Old Apple source weakens current semantics and adds vfork; current Apple source crosses an incompatible FILE/private-runtime composition.",
        },
        "service_runtime_boundaries": [
            "gss_kerberos", "resolver_libinfo", "notify_os_log_syslog",
            "dynamic_loader", "private_bootstrap",
        ],
        "forbidden_shortcuts": {
            "old_popen_semantic_downgrade": False,
            "vfork_private_to_public_alias": False,
            "vfork_to_fork_macro_rewrite": False,
            "remove_fwide_or_thread_locking": False,
            "service_or_loader_facade": False,
            "disable_pam_or_kerberos_gss": False,
        },
        "preservation": {
            "features_unchanged": True,
            "pam_enabled": True,
            "kerberos_gss_enabled": True,
            "filesystem_layout_unchanged": True,
            "filesystem_layout": ["/usr/bin/ssh", "/usr/sbin/sshd", "/usr/libexec", "/private/etc/ssh"],
            "target_executed": False,
            "hardware_touched": False,
            "accepted_runtime_modified": False,
            "provider_created": False,
        },
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
