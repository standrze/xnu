#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Audit the genuine Apple resolver/Libinfo ownership boundary for OpenSSH.

This is intentionally an admission gate, not a provider builder.  The three
resolver imports are a coherent transport/configuration subsystem and
si_destination_compare is a distinct Libinfo network-selection subsystem.
Neither may be replaced by a size-only state object, no-op initialization,
DNS/notify doubles, or the reduced no-dependencies comparator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "build/rpi5/apple-ssh-localtime-r-5apxxhjz"
BASE_MANIFEST_SHA256 = "0093975e99016eca90282e2e9dd68264855d40a0bf3c9230d570cc671f3c11c1"

LIBRESOLV = ROOT / "build/rpi5/apple-libresolv-candidate-20261014"
LIBRESOLV_COMMIT = "e48cd914edc1cb14f8289b8e2dfdaac360481cd2"
LIBINFO = ROOT / "build/rpi5/apple-libinfo-main-candidate-20261013"
LIBINFO_COMMIT = "39b70c515baee5b609e7e91693edbd934b6845a1"
LIBNOTIFY = ROOT / "build/rpi5/apple-libnotify-main-candidate-20261014"
LIBNOTIFY_COMMIT = "715d461778f6b93c821d99390a0078bd6f6d8c04"
CONFIGD = ROOT / "experiments/darwin-container/userland/upstream/apple-configd-453.19"
CONFIGD_COMMIT = "5ab18e75fd838206cf76cab596a41a3050404867"
OPENSSH = ROOT / "build/rpi5/apple-openssh-candidate-20261013"
OPENSSH_COMMIT = "f386b2e948280f6ecac875329c0b56020821d558"

EXPECTED_MISSING = [
    "_GSS_C_NT_HOSTBASED_SERVICE", "___res_9_state", "__os_log_debug_impl",
    "__os_log_default", "__os_log_error_impl", "_bootstrap_parent",
    "_closelog", "_dlclose", "_dlerror", "_dlopen", "_dlsym",
    "_gss_delete_sec_context", "_gss_display_status", "_gss_get_mic",
    "_gss_import_name", "_gss_indicate_mechs", "_gss_init_sec_context",
    "_gss_release_buffer", "_gss_release_cred", "_gss_release_name",
    "_gss_release_oid_set", "_notify_check", "_notify_register_check",
    "_openlog", "_os_log_create", "_os_log_type_enabled", "_pclose",
    "_perror", "_popen", "_res_9_init", "_res_9_query",
    "_si_destination_compare", "_sscanf", "_syslog$DARWIN_EXTSN",
    "_vsyslog",
]

SOURCE_PINS = {
    "OpenSSH/ssh.c": (OPENSSH / "openssh/ssh.c", "a634caf3eb77c5d16c976552615407341cefa09796ef509ef145586ee4bd95b6"),
    "OpenSSH/getrrsetbyname.c": (OPENSSH / "openssh/openbsd-compat/getrrsetbyname.c", "33eaf1ff4aa3ca8d9891686bc43a88a1676126c1703b59227ea7cc29496cdbde"),
    "libresolv/res_state.c": (LIBRESOLV / "res_state.c", "224714377ea3675b73dcd645e8ce7a45ad9c1e5b3602f5f6fdd97d5256b1c7cf"),
    "libresolv/res_data.c": (LIBRESOLV / "res_data.c", "892efe63efd6ab86b635edcd60638036fed78747ec38c3bcfd5a01ac963c97cd"),
    "libresolv/res_init.c": (LIBRESOLV / "res_init.c", "483747cf6b4dd8a38984037c2aa93f73301ad6bd88c6de9e2f078031ef718666"),
    "libresolv/res_mkquery.c": (LIBRESOLV / "res_mkquery.c", "6af5f8a912cc9e45773a9397e75e51f86ef6ac505b56568f8fd5e586ac293a02"),
    "libresolv/res_query.c": (LIBRESOLV / "res_query.c", "4bc83a78a96c55966a1672e15be81ad37fa4d481a08cce972f4b711769415ccf"),
    "libresolv/res_send.c": (LIBRESOLV / "res_send.c", "2cdd1cd9f793c762dad17541913d4b8b4ba4ddcabd487e555cc5878bc92697ed"),
    "libresolv/dns.c": (LIBRESOLV / "dns.c", "90150d4d5282c90676850cdc9e807363b766fbc87a7f141c1e4b64c18cd5bb8d"),
    "libresolv/project.pbxproj": (LIBRESOLV / "libresolv.xcodeproj/project.pbxproj", "a50d5e14c3e74b2f0cde97efbfeb0fc9a95ef710e55423227f41163bc3ceef38"),
    "Libinfo/si_compare.c": (LIBINFO / "lookup.subproj/si_compare.c", "c626fbdfe86367dc93daf925dfe78cf99ad2364c7ec5640b8b196b3a49930dc3"),
    "configd/dnsinfo_copy.c": (CONFIGD / "dnsinfo/dnsinfo_copy.c", "3340fdf007154a3c195101515017ec9230a31d98b82fb93c7b97c43db9cb4bcc"),
    "configd/dnsinfo_private.c": (CONFIGD / "dnsinfo/dnsinfo_private.c", "f712879719649c193faf0584eee37981a3d751a2729e33083ce8f3e053f77be8"),
    "configd/dnsinfo_server.c": (CONFIGD / "dnsinfo/dnsinfo_server.c", "1c0274464b6551160b9543cca82d136bbce699cc7f467910d7c020f4556d4442"),
    "Libnotify/notify_private.h": (LIBNOTIFY / "notify_private.h", "7fbd0fc627302851ff664aaa91495f56f2bfe8fea31a3d82e3897c610f4c950c"),
}

REQUIRED_PATTERNS = {
    "OpenSSH/ssh.c": ["Force initialization of Libinfo logging", "si_destination_compare(&dummy, 0, &dummy, 0, false)"],
    "OpenSSH/getrrsetbyname.c": ["(_resp->options & RES_INIT)", "res_init()", "res_query(hostname"],
    "libresolv/res_state.c": ["__res_state(void)", "dyld_program_minos_at_least", "_dns_check_sys_config_notify", "res_ndestroy"],
    "libresolv/res_data.c": ["res_init(void)", "__res_vinit(statp, 1)", "res_nquery(statp", "res_nsend(statp"],
    "libresolv/res_init.c": ["__res_vinit_from_dns", "dns_configuration_copy()", "_dns_open_sys_config_notify", "fopen(_PATH_RESCONF"],
    "libresolv/res_mkquery.c": ["res_nmkquery(res_state", "res_nrandomid(statp)"],
    "libresolv/res_query.c": ["DNSServiceQueryRecord", "DNSServiceProcessResult", "notify_register_plain", "kevent("],
    "libresolv/res_send.c": ["res_nsend(res_state", "notify_get_state", "socket(nsap->sa_family", "sendto("],
    "libresolv/dns.c": ["dns_configuration_copy()", "notify_register_check", "notify_monitor_file", "_dns_open_sys_config_notify"],
    "Libinfo/si_compare.c": ["si_destination_compare(", "si_destination_compare_no_dependencies", "socket(PF_SYSTEM", "CTLIOCGINFO", "mach_absolute_time()", "os_log_create"],
    "configd/dnsinfo_copy.c": ["dns_configuration_copy()", "shared_dns_infoGet", "_dns_configuration_server_port()", "vm_deallocate"],
    "configd/dnsinfo_private.c": ["bootstrap_look_up", "DNS_SERVER"],
    "configd/dnsinfo_server.c": ["_shared_dns_infoGet", "_shared_dns_infoSet", "_dns_configuration_notify_key"],
}

OWNERS = {
    "resolver_transport": ["___res_9_state", "_res_9_init", "_res_9_query"],
    "libinfo_destination": ["_si_destination_compare"],
    "notify": ["_notify_check", "_notify_register_check"],
    "os_log": ["__os_log_debug_impl", "__os_log_default", "__os_log_error_impl", "_os_log_create", "_os_log_type_enabled"],
    "gss": ["_GSS_C_NT_HOSTBASED_SERVICE", "_gss_delete_sec_context", "_gss_display_status", "_gss_get_mic", "_gss_import_name", "_gss_indicate_mechs", "_gss_init_sec_context", "_gss_release_buffer", "_gss_release_cred", "_gss_release_name", "_gss_release_oid_set"],
    "dynamic_loader": ["_dlclose", "_dlerror", "_dlopen", "_dlsym"],
    "syslog": ["_closelog", "_openlog", "_syslog$DARWIN_EXTSN", "_vsyslog"],
    "stdio_process": ["_pclose", "_perror", "_popen", "_sscanf"],
    "private_bootstrap": ["_bootstrap_parent"],
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _commit(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def verify_sources() -> dict[str, str]:
    commits = {
        "apple-libresolv": _commit(LIBRESOLV),
        "apple-Libinfo": _commit(LIBINFO),
        "apple-libnotify": _commit(LIBNOTIFY),
        "apple-configd": _commit(CONFIGD),
        "apple-OpenSSH": _commit(OPENSSH),
    }
    expected = {
        "apple-libresolv": LIBRESOLV_COMMIT,
        "apple-Libinfo": LIBINFO_COMMIT,
        "apple-libnotify": LIBNOTIFY_COMMIT,
        "apple-configd": CONFIGD_COMMIT,
        "apple-OpenSSH": OPENSSH_COMMIT,
    }
    if commits != expected:
        raise ValueError(f"Apple source commit drift: {commits!r}")
    for name, (path, digest) in SOURCE_PINS.items():
        if sha256(path) != digest:
            raise ValueError(f"Apple source drift: {name}")
        text = path.read_text(errors="strict")
        for pattern in REQUIRED_PATTERNS.get(name, []):
            if pattern not in text:
                raise ValueError(f"Required ownership evidence missing: {name}: {pattern}")
    return commits


def validate_report(report: dict[str, Any]) -> None:
    if report["baseline_manifest_sha256"] != BASE_MANIFEST_SHA256:
        raise ValueError("Wrong baseline pin")
    if report["remaining_imports"] != EXPECTED_MISSING:
        raise ValueError("The exact 35-import baseline is required")
    flattened = sorted(symbol for values in report["ownership"].values() for symbol in values)
    if flattened != EXPECTED_MISSING:
        raise ValueError("Every remaining import must have exactly one owner group")
    if report["selected_tranche"]["imports"] != OWNERS["resolver_transport"]:
        raise ValueError("Resolver tranche membership changed")
    if report["selected_tranche"]["admissible"]:
        raise ValueError("Resolver tranche cannot pass before its real services pass")
    required = {
        "thread_local_resolver_state", "dns_wire_query_construction",
        "systemconfiguration_dns_mach_service", "notify_runtime_and_service",
        "mdnsresponder_dnsservice_transport", "udp_tcp_kqueue_transport",
        "target_native_resolver_tests",
    }
    if set(report["selected_tranche"]["prerequisites"]) != required:
        raise ValueError("Resolver prerequisite closure is incomplete")
    if any(report["forbidden_shortcuts"].values()):
        raise ValueError("A semantic shortcut was enabled")
    if report["libinfo_destination"]["admissible"]:
        raise ValueError("Libinfo destination subsystem cannot pass yet")
    if report["libinfo_destination"]["replacement"] != "none":
        raise ValueError("Libinfo comparator replacement is forbidden")
    if not report["preservation"]["features_unchanged"] or not report["preservation"]["filesystem_layout_unchanged"]:
        raise ValueError("OpenSSH feature/layout preservation was lost")


def audit() -> dict[str, Any]:
    if sha256(BASE / "manifest.json") != BASE_MANIFEST_SHA256:
        raise ValueError("Exact sealed 35-import OpenSSH package required")
    manifest = json.loads((BASE / "manifest.json").read_text())
    missing = manifest.get("target_missing_symbols")
    if missing != EXPECTED_MISSING:
        raise ValueError("Sealed package import set changed")
    commits = verify_sources()
    source_hashes = {name: digest for name, (_, digest) in SOURCE_PINS.items()}
    report: dict[str, Any] = {
        "profile": "apple-openssh-resolver-ownership-gate-v1",
        "baseline_manifest": str(BASE / "manifest.json"),
        "baseline_manifest_sha256": BASE_MANIFEST_SHA256,
        "remaining_imports": missing,
        "remaining_count": len(missing),
        "ownership": OWNERS,
        "apple_source_commits": commits,
        "apple_source_sha256": source_hashes,
        "selected_tranche": {
            "name": "resolver_transport",
            "imports": OWNERS["resolver_transport"],
            "source_units": [
                "res_state.c", "res_data.c", "res_init.c", "res_mkquery.c",
                "res_query.c", "res_send.c", "dns.c",
            ],
            "prerequisites": [
                "thread_local_resolver_state", "dns_wire_query_construction",
                "systemconfiguration_dns_mach_service", "notify_runtime_and_service",
                "mdnsresponder_dnsservice_transport", "udp_tcp_kqueue_transport",
                "target_native_resolver_tests",
            ],
            "admissible": False,
            "reason": "Apple resolver semantics cross configd Mach/MIG DNS state, notify, mDNSResponder DNSService, and kernel socket/kqueue transport; those runtime owners are not yet qualified.",
        },
        "libinfo_destination": {
            "imports": OWNERS["libinfo_destination"],
            "source_unit": "lookup.subproj/si_compare.c",
            "required_runtime": ["os_log", "pthread_atfork", "PF_SYSTEM/SYSPROTO_CONTROL", "CTLIOCGINFO", "network_statistics", "getifaddrs", "mach_absolute_time"],
            "consumer_evidence": "apple-OpenSSH openssh/ssh.c invokes full si_destination_compare for Libinfo logging initialization before daemonization",
            "replacement": "none",
            "admissible": False,
            "reason": "si_destination_compare_no_dependencies skips full source selection/statistics behavior and is not an ABI-equivalent owner.",
        },
        "forbidden_shortcuts": {
            "static_res_state_facade": False,
            "res_init_noop": False,
            "dnsservice_stub": False,
            "notify_stub": False,
            "configd_stub": False,
            "no_dependencies_comparator_alias": False,
            "feature_disabling": False,
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
        },
        "next_admission_sequence": [
            "qualify real libnotify client plus notify service ownership",
            "qualify configd shared_dns_info Mach/MIG client and server ownership",
            "qualify mDNSResponder DNSService client transport",
            "qualify socket, TCP/UDP, kqueue and interrupt semantics on the target kernel",
            "build the complete seven-unit resolver tranche and require exactly three closed imports with no additions or duplicates",
            "run deterministic file-config, configd-config, unicast UDP/TCP, mDNS, cancellation, reload and concurrent-state tests",
            "audit full Libinfo destination comparison independently after its os_log and kernel-control prerequisites exist",
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
    return 2 if not report["selected_tranche"]["admissible"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
