#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Audit the documented PTY/network/shared-compute endpoint without booting.

Checks preserved raw guest/host observations and their current artifact hashes.
Does not reinterpret compilation, a host-only test or a prior report's outcome
label as guest execution. No Pi access, new soak, or VM mutation occurs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from prepare_pid1 import inspect as inspect_macho
from ramroot import inspect as inspect_root

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def verify_hashes(folder, hashes):
    for name, expected in hashes.items():
        require(digest(folder / name) == expected, f"artifact changed: {folder / name}")
    return len(hashes)


def guest(folder, trial_name):
    result, trial = load(folder / "result.json"), load(folder / trial_name)
    terminal = result.get("terminal", {})
    require(result.get("started") and result.get("guestStopped")
            and result.get("termination") == "guestStopped" and not result.get("error")
            and trial.get("cli_exit") == 0 and not trial.get("error")
            and terminal.get("handshakeCompleted") and terminal.get("exitStatus") == 0
            and not terminal.get("error"), f"incomplete actual guest session: {folder}")
    return result, trial, (folder / "terminal-output.bin").read_bytes().replace(b"\r", b"")


def markers(output, values):
    for value in values:
        require(value in output, f"missing decoded guest output: {value!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="new audit directory")
    parser.add_argument("--terminal-check-log", required=True, type=Path, help="existing six-check raw-mode/framing/write-queue transcript")
    args = parser.parse_args()
    require(not args.output.exists(), "audit directory must be new")
    results = PROJECT / "results"
    terminal_dir = results / "2026-10-12-framed-terminal"
    combined_dir = results / "2026-10-12-apple-libinfo"
    config_dir = results / "2026-10-12-apple-ifconfig"
    evidence_counts = {}
    for directory in (terminal_dir, combined_dir, config_dir):
        evidence_counts[str(directory.relative_to(PROJECT))] = verify_hashes(directory, load(directory / "verification.json")["sha256"])
    combined_verification = load(combined_dir / "verification.json")
    host_count = verify_hashes(PROJECT, combined_verification["host_source_sha256"])

    checkpoint_counts = {}
    for name in ("terminal-framed", "network", "shared-gpu", "apple-network-gpu", "apple-resolver",
                 "apple-libinfo", "apple-bootp", "apple-route", "apple-ifconfig"):
        folder = HERE / "build" / (name + "-working-2026-10-12")
        checkpoint_counts[name] = verify_hashes(folder, load(folder / "manifest.json")["sha256"])
    frozen = HERE / "build/darwin-workload-0.1.0"
    frozen_count = verify_hashes(frozen, load(frozen / "manifest.json")["immutable_sha256"])

    persistence, _, persisted_output = guest(terminal_dir / "persistence-boot", "terminal-trial.json")
    markers(persisted_output, (b"\nREADBACK_BEGIN\n", b"\nFRAME_SAVED\n", b"\nREADBACK_END\n",
                              b"print -r -- FRAME_SAVED >> /data/framed-note; exit"))
    result, trial, output = guest(combined_dir / "guest-trial", "terminal-trial.json")
    markers(output, (b"\nTERMINAL_TTY_JOB_OK\n", b"\nSIZE_INITIAL:35:120\n", b"\nZLE_EDIT\n",
                     b"suspended  /bin/sleep 20\n", b"continued  /bin/sleep 20\n", b"\nJOB_STATUS:130\n",
                     b"SIZE_CHANGED:47:132", b"BYTE_ROUNDTRIP:\x80\xff:END"))
    require(output.count(b"\nFRAME_HISTORY_RECALL\n") == 2, "missing actual up-arrow history recall")
    require(result["terminal"]["acknowledgedSizes"] == [[35, 120], [47, 132]], "missing actual resize acknowledgements")

    host_log = args.terminal_check_log.read_text()
    for name in ("rawModeForwardsControlBytesAndRestoresTerminal", "pipedInputDoesNotAcquireTerminalModeOrChangeFlags",
                 "binaryPayloadFragmentationAndResizeAcknowledgements", "rejectsCorruptionWrongSessionAndSkippedSequence",
                 "queueBoundsAndFatalWriteErrorsCannotLoseTheCursor", "shortWritesInterruptionsAndBackpressurePreserveExactByteOrder"):
        require(re.search(r"Test " + name + r"\(\) passed", host_log), "missing successful focused host check: " + name)
    require("Test run with 6 tests in 3 suites passed" in host_log, "incomplete focused host transcript")

    gpu = result.get("gpu", {})
    require(gpu.get("enabled") and gpu.get("deviceName") and not gpu.get("error")
            and (gpu.get("submitted"), gpu.get("completed"), gpu.get("rejected")) == (3, 2, 1), "missing actual host Metal execution")
    seeds, operations = trial.get("gpu_seeds", []), gpu.get("operations", [])
    require(len(seeds) == 2 and len(operations) == 3 and operations[-1]["status"] == 1, "missing unsupported GPU operation proof")
    for index, seed in enumerate(seeds):
        a, b = [(seed + i) * 0.5 for i in range(16)], [-i * 0.25 for i in range(16)]
        operation = operations[index]
        require(operation["id"] == index + 1 and operation["status"] == 0 and operation["left"] == a
                and operation["right"] == b and operation["result"] == [x + y for x, y in zip(a, b)], "GPU operands/results not matched independently")
        markers(output, (f"\nDARWIN:GPU:ADD OK seed={seed} count=16\n".encode(),))
    markers(output, (b"\nDARWIN:GPU:UNSUPPORTED status=1\n",))
    gpu_host_checks = (combined_dir / "host-focused-checks.txt").read_text()
    for name in ("protocolRoutesOnlyOneSessionCheckedRequestAndRequiresResponseBeforeExit", "disabledBridgeBoundsUnsupportedReplayAndSessionQuota"):
        require(re.search(r"Test " + name + r"\(\) passed", gpu_host_checks), "missing focused GPU ownership/bounds check")

    configured, config_trial, config_output = guest(config_dir / "guest-trial", "configuration-trial.json")
    require(len(config_trial.get("passed", [])) == 6 and config_trial.get("apple_route")
            and config_trial.get("apple_ifconfig"), "incomplete original Apple configuration trial")
    fixture = config_trial.get("network_fixture", {})
    events = fixture.get("events", [])
    require(not fixture.get("errors") and sorted(item["type"] for item in events) == ["dns", "tcp"], "missing actual host-witnessed DNS/TCP traffic")
    dns, tcp = next(e for e in events if e["type"] == "dns"), next(e for e in events if e["type"] == "tcp")
    require(dns["guest"] == tcp["guest"] and dns["guest"] != dns["answer"]
            and dns["name"] == fixture["token"] + ".darwin.test" and tcp["echo"] == fixture["token"]
            and re.fullmatch(r"[0-9a-f]{24}", fixture["token"]), "DNS/TCP witness nonce or guest mismatch")
    markers(config_output, (b"\nDARWIN:NET:APPLE_BOOTP bootp-268.1 options match BPF checksum IPv4\n",
                            b"\nAPPLE_BOOTP_STATUS:0\n", b"\nCONFIG_DNS_STATUS:0\n",
                            b"\nAPPLE_IFCONFIG_SET_STATUS:0\n", b"\nAPPLE_IFCONFIG_RESTORE_STATUS:0\n",
                            b" mtu 1400\n", b" mtu 1500\n", b"\nAPPLE_ROUTE_STATUS:0\n",
                            f"\n    gateway: {dns['answer']}\n".encode(), b"\n  interface: en0\n",
                            f"\nDARWIN:NET:APPLE_GETADDRINFO {dns['name']} {dns['answer']} Libinfo-542.40.3\n".encode(),
                            f"\nDARWIN:NET:APPLE_GAI_TCP ECHO={tcp['echo']}\n".encode(), b"\nAPPLE_GAI_STATUS:0\n"))

    # Latest root adds commands, not a changed untested terminal/GPU runtime.
    combined_root, latest_root = load(combined_dir / "root-manifest.json"), load(config_dir / "root-manifest.json")
    combined_working, latest_working = HERE / "build/apple-libinfo-working-2026-10-12", HERE / "build/apple-ifconfig-working-2026-10-12"
    for folder in (combined_working, latest_working):
        inspect_root((folder / "ramdisk.bin").read_bytes())
    for name in ("container", "kernel.macho", "zsh", "resolverctl"):
        require(digest(combined_working / name) == digest(latest_working / name), "latest checkpoint changed qualified artifact: " + name)
    old_image, new_image = (combined_working / "ramdisk.bin").read_bytes(), (latest_working / "ramdisk.bin").read_bytes()
    latest_entries = {entry["path"]: entry for entry in latest_root["entries"] if entry["type"] == "file"}
    carried = []
    for entry in combined_root["entries"]:
        if entry["type"] != "file":
            continue
        new = latest_entries.get(entry["path"])
        require(new and entry["mode"] == new["mode"] and old_image[entry["offset"]:entry["offset"] + entry["size"]]
                == new_image[new["offset"]:new["offset"] + new["size"]], "latest root changed qualified file: " + entry["path"])
        carried.append(entry["path"])
    require(combined_root["executable"]["sha256"] == latest_root["executable"]["sha256"], "changed PTY/GPU executable")
    for flag in ("framed_terminal", "pty_relay", "writable_storage", "network_diagnostic", "shared_gpu_client", "apple_dns_wire_parser"):
        require(latest_root.get(flag) is True, "missing latest root capability: " + flag)
    latest_verification = load(config_dir / "verification.json")
    for name in ("zsh", "resolverctl", "dhcpctl", "route", "ifconfig"):
        inspect_macho((latest_working / name).read_bytes())
    require(digest(latest_working / "container") == trial["cli_sha256"] == config_trial["cli_sha256"], "guest evidence uses different CLI")
    require(digest(latest_working / "kernel.macho") == latest_verification["kernel_sha256"] == combined_verification["kernel_sha256"], "guest evidence uses different kernel")
    require(configured["terminal"]["exitStatus"] == persistence["terminal"]["exitStatus"] == 0, "missing clean termination")

    report = {
        "outcome": "documented-terminal-network-shared-compute-endpoint-achieved-experimental",
        "scope_basis": "INTERACTIVE-NETWORK-GPU.md numbered acceptance criteria, original three-capability goal, and Apple-source-first policy",
        "requirements": {
            "terminal": "actual controlling PTY/ZLE arrows/history, Ctrl-Z/jobs/fg, Ctrl-C 130, SIGWINCH resize, binary bytes and saved-history restart; focused host raw restore/backpressure checks",
            "network": "actual VZ NAT/XNU en0, original Apple bootp routines and route/ifconfig configuration, original Libinfo/libresolv lookup, independent fresh guest DNS/TCP witness",
            "gpu": "typed guest C client/relay requests executed on host Metal, independently matched returned vectors and explicit unsupported status; session/quota/bounds checks",
            "source_policy": "pinned original Apple XNU/zsh/Libc/libplatform/resolver/Libinfo/bootp/network_cmds; project VirtIO transports, static ABI and bounded DHCP/GPU adapters remain labeled",
            "preservation": "frozen workload 0.1.0 and all nine qualified checkpoints hash-identical; physical Pi outside scope"
        },
        "evidence_hash_counts": evidence_counts,
        "current_qualified_host_source_hashes": host_count,
        "checkpoint_hash_counts": checkpoint_counts,
        "frozen_workload_immutable_hashes": frozen_count,
        "latest_checkpoint": str(latest_working.relative_to(PROJECT)),
        "byte_identical_carried_files": carried,
        "latest_checkpoint_hashes": load(latest_working / "manifest.json")["sha256"],
        "test_policy": "read-only completion audit of existing evidence; no new VM boot, broad tests or soak",
        "limits_and_separate_future_work": [
            "experimental Apple-silicon Virtualization.framework VM, not portable-to-all-hosts or production isolation",
            "PTY transport/job control achieved; optional compctl and multibyte locales remain absent",
            "IPv4 fixture-qualified networking; not internet/IPv6 qualification, mDNS/search/cache or full configd/IPConfiguration service",
            "DHCP acquisition uses original Apple routines with project bounded orchestration; no lease renewal, rebinding or ARP conflict probe",
            "shared GPU is bounded float32 vector add (16 elements, 1024 requests/session), not arbitrary Metal, a graphics desktop or passthrough",
            "private EFI/variable entropy not published; repeat seed use and hostile-guest security are not qualified",
            "historical per-increment reports remain unchanged; their not-full-goal labels are superseded only by this aggregate requirement audit"
        ],
        "audit_source_sha256": digest(Path(__file__)),
        "scope_document_sha256_at_audit": digest(PROJECT / "INTERACTIVE-NETWORK-GPU.md"),
        "terminal_check_log_sha256": digest(args.terminal_check_log),
    }
    args.output.mkdir(parents=True)
    shutil.copy2(args.terminal_check_log, args.output / "existing-terminal-focused-checks.log")
    shutil.copy2(Path(__file__), args.output / "audit_followon.py")
    (args.output / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": report["outcome"], "audit": str(args.output / "audit.json"), "evidence_hash_counts": evidence_counts}))


if __name__ == "__main__":
    main()
