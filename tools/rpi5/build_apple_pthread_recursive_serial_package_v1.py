#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the default-off Pi serial package for one exact recursive-mutex target.

No media, serial device, SSH or reboot operation exists in this builder.  It
replaces only the already-reserved pthreadprobe regular file, regenerates the
root identity executable/catalog, and embeds that root in the frozen terminal
kernel/loader lineage with a fresh trial marker.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import types
import uuid

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.rpi5 import build_root42_pthread_package as boot
from tools.rpi5 import check_root42_pthread_root as root_check
from tools.rpi5 import root_capacity_pthread as root_builder
from tools.rpi5 import apple_pthread_recursive_serial_transport_v1 as transport

BASE_ROOT = root_check.PACKAGE
BASE_ROOT_MANIFEST_SHA256 = root_check.MANIFEST_SHA
BASE_ROOT_SHA256 = root_check.IMAGE_SHA
TARGET_PACKAGE = ROOT / "build/rpi5/apple-pthread-recursive-target-v1-vquibrum"
TARGET_MANIFEST_SHA256 = "a3d2f7b5fa41778ac49a8584655351ae88581b64299eacc06f770967d75a5e3e"
TARGET = TARGET_PACKAGE / "NOT_RUN_recursive_mutex_target"
ENTRY = transport.TARGET_PATH
IDENTITY = root_builder.IDENTITY
PROFILE = "apple-pthread-recursive-serial-default-off-v1"
BASE_BOOT = ROOT / "build/rpi5/root42-pthread-ulws4mq6"
BASE_BOOT_MANIFEST_SHA256 = "c45503701eaed84be939e72ddb2afb0e45af86f3d5260f1212a40eca90fcb8be"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def merge(target, more):
    for name, digest in more.items():
        if name in target and target[name] != digest:
            raise ValueError("conflicting immutable input: " + name)
        target[name] = digest


def verify_target():
    if sha(TARGET_PACKAGE / "manifest.json") != TARGET_MANIFEST_SHA256:
        raise ValueError("recursive target manifest drift")
    record = json.loads((TARGET_PACKAGE / "manifest.json").read_text())
    if (record.get("target") != str(TARGET) or record.get("target_sha256") != transport.TARGET_SHA256
            or sha(TARGET) != transport.TARGET_SHA256 or not record.get("target_link_complete")
            or record.get("target_undefined_symbols") != [] or record.get("pi_executed") is not False):
        raise ValueError("exact unexecuted recursive target required")
    pins = {str(TARGET_PACKAGE / "manifest.json"): TARGET_MANIFEST_SHA256,
            str(TARGET): transport.TARGET_SHA256}
    for key in ("source_inputs_sha256", "generated_sha256"):
        for name, digest in record[key].items():
            path = Path(name) if Path(name).is_absolute() else TARGET_PACKAGE / name
            if sha(path) != digest:
                raise ValueError("recursive target closure drift: " + name)
            merge(pins, {str(path): digest})
    return record, pins


def build_root():
    root_check.inspect(BASE_ROOT)
    target_record, target_pins = verify_target()
    prior = json.loads((BASE_ROOT / "manifest.json").read_text())
    original = root_builder.old.profile.files_from((BASE_ROOT / "ramdisk.bin").read_bytes())
    if len(original) != 30 or ENTRY not in original or IDENTITY not in original:
        raise ValueError("exact frozen 42-node pthread root required")
    if root_builder.old.profile.sha(original[ENTRY][0]) != root_builder.PTHREAD_SHA:
        raise ValueError("frozen predecessor pthread target changed")

    pins = dict(prior["inputs_sha256"])
    merge(pins, prior["generated_sha256"])
    merge(pins, target_pins)
    for path in (BASE_ROOT / "manifest.json", Path(__file__).resolve(), Path(transport.__file__).resolve()):
        merge(pins, {str(path): sha(path)})
    root_builder.old.verify(pins)

    output = Path(tempfile.mkdtemp(prefix="apple-pthread-recursive-root-v1-", dir=ROOT / "build/rpi5"))
    expanded = dict(original)
    expanded[ENTRY] = (TARGET.read_bytes(), 0o555)
    audit = root_check.prior_check.static_entry(expanded[ENTRY][0], "_darwin_static_start")

    _, layout = root_builder.old.profile.build(expanded)
    rows = []
    for item in layout["entries"]:
        path, isdir = item["path"], item["type"] == "directory"
        rows.append({
            "path": path,
            "mode": item["mode"] | (0o40000 if isdir else 0o100000),
            "bytes": 0 if isdir or path == IDENTITY else len(expanded[path][0]),
            "sha256": "" if isdir else None if path == IDENTITY else root_builder.old.profile.sha(expanded[path][0]),
        })
    (output / "rootidentity_catalog.h").write_text(root_builder.old.identity.header(rows))

    compile_args = next(list(row["command"]) for row in prior["commands"]
                        if "-c" in row["command"] and row["command"][-1] == str(BASE_ROOT / "identity.d"))
    compile_args = compile_args[:compile_args.index("-MD")]
    old_object = compile_args[compile_args.index("-o") + 1]
    new_object = output / "rootidentity.o"
    compile_args[compile_args.index("-o") + 1] = str(new_object)
    compile_args = ["-I" + str(output) if arg == "-I" + str(BASE_ROOT) else arg for arg in compile_args]
    if "-I" + str(output) not in compile_args:
        raise ValueError("root identity include was not rebound")
    commands = []
    root_builder.old.compile_actual(compile_args, output, "identity", commands, pins)
    source_link = next(list(row["command"]) for row in prior["commands"] if "-o" in row["command"]
                       and row["command"][row["command"].index("-o") + 1] == str(BASE_ROOT / "socketprobe")
                       and "-c" not in row["command"])
    link = [str(new_object) if arg == old_object else str(output / "socketprobe")
            if arg == str(BASE_ROOT / "socketprobe") else arg for arg in source_link]
    root_builder.old.run(link, output, "identity-link", commands)
    if root_builder.old.run(["xcrun", "nm", "-u", str(output / "socketprobe")],
                            output, "identity-undefined", commands).strip():
        raise ValueError("recursive root identity has unresolved symbols")

    expanded[IDENTITY] = ((output / "socketprobe").read_bytes(), 0o555)
    for row in rows:
        if row["path"] == IDENTITY:
            row.update(bytes=len(expanded[IDENTITY][0]),
                       sha256=root_builder.old.profile.sha(expanded[IDENTITY][0]))
    raw, layout = root_builder.old.profile.build(expanded)
    if len(layout["entries"]) != 42 or len(expanded) != 30 or root_builder.old.profile.files_from(raw) != expanded:
        raise ValueError("recursive root did not round-trip as exact 42-node/30-file root")
    for path, value in original.items():
        if path not in (ENTRY, IDENTITY) and expanded[path] != value:
            raise ValueError("unrelated root member changed: " + path)
    (output / "ramdisk.bin").write_bytes(raw)
    root_builder.old.verify(pins)

    report = {
        "profile": "apple-pthread-recursive-root-default-off-v1",
        "default_off": True,
        "hardware_execution": False,
        "baseline": str(BASE_ROOT),
        "baseline_manifest_sha256": BASE_ROOT_MANIFEST_SHA256,
        "input_root_sha256": BASE_ROOT_SHA256,
        "output_sha256": sha(output / "ramdisk.bin"),
        "output_bytes": len(raw),
        "output_nodes": 42,
        "output_files": 30,
        "identity_catalog": rows,
        "commands": commands,
        "inputs_sha256": pins,
        "changed_files_sha256": {ENTRY: transport.TARGET_SHA256,
                                 IDENTITY: sha(output / "socketprobe")},
        "unchanged_files_sha256": {path: root_builder.old.profile.sha(value[0])
                                     for path, value in original.items() if path not in (ENTRY, IDENTITY)},
        "target_manifest": str(TARGET_PACKAGE / "manifest.json"),
        "target_manifest_sha256": TARGET_MANIFEST_SHA256,
        "target_sha256": transport.TARGET_SHA256,
        "target_executable_audit": audit,
        "target_source_contract": target_record["source_contract"],
        "execution_contract": transport.execution_contract(),
        "installed": False,
        "pi_executed": False,
        "serial_actions": 0,
        "sd_actions": 0,
        "reboots": 0,
        "networking": False,
        "ssh_transport": False,
    }
    report["generated_sha256"] = {str(path): sha(path) for path in output.iterdir() if path.is_file()}
    (output / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return output, report


def marker(tag):
    if not isinstance(tag, str) or re.fullmatch(r"[0-9a-f]{32}", tag) is None:
        raise ValueError("fresh 128-bit tag required")
    return ("RPI5XNU:BL33:PTHREAD_RECURSIVE_TRIAL TAG=" + tag
            + " CPUS=4 ROOT_NODES=42 WATCHDOG_READY_V2")


def build_boot(root_directory, root_report):
    root_manifest = root_directory / "manifest.json"
    root_manifest_sha = sha(root_manifest)
    if sha(root_directory / "ramdisk.bin") != root_report["output_sha256"]:
        raise ValueError("recursive root bytes changed")
    if sha(BASE_BOOT / "manifest.json") != BASE_BOOT_MANIFEST_SHA256:
        raise ValueError("frozen terminal boot package manifest drift")
    base = json.loads((BASE_BOOT / "manifest.json").read_text())
    for name, digest in base["generated_sha256"].items():
        if sha(name) != digest:
            raise ValueError("frozen generated terminal artifact drift: " + name)
    old_root = Path(base["root"])
    old_payload = (BASE_BOOT / "payload.bin").read_bytes()
    old_root_raw = old_root.read_bytes()
    if len(old_root_raw) != root_report["output_bytes"] or not old_payload.endswith(old_root_raw):
        raise ValueError("frozen terminal payload/root boundary changed")

    package = Path(tempfile.mkdtemp(prefix="apple-pthread-recursive-serial-v1-", dir=ROOT / "build/rpi5"))
    tag = uuid.uuid4().hex
    old_marker = base["trial_marker"]
    new_marker = marker(tag)
    original_main = (BASE_BOOT / "probe_main.c").read_text()
    if original_main.count(old_marker) != 1:
        raise ValueError("frozen terminal trial marker is ambiguous")
    new_main = original_main.replace(old_marker, new_marker)
    (package / "probe_main.c").write_text(new_main)
    (package / "probe_main.c.diff").write_text("".join(difflib.unified_diff(
        original_main.splitlines(True), new_main.splitlines(True),
        fromfile=str(BASE_BOOT / "probe_main.c"), tofile="probe_main.c")))
    (package / "payload.bin").write_bytes(old_payload[:-len(old_root_raw)] + (root_directory / "ramdisk.bin").read_bytes())
    (package / "payload.S").write_text('.section .payload,"a"\n.balign 64\n.incbin "' + str(package / "payload.bin") + '"\n')

    def old_command(label):
        return list(next(row["command"] for row in base["commands"] if Path(row["log"]).name == label))

    replacements = {
        str(BASE_BOOT / "probe_main.c"): str(package / "probe_main.c"),
        str(BASE_BOOT / "probe_main.o"): str(package / "probe_main.o"),
        str(BASE_BOOT / "main.d"): str(package / "main.d"),
        str(BASE_BOOT / "payload.S"): str(package / "payload.S"),
        str(BASE_BOOT / "payload.o"): str(package / "payload.o"),
        str(BASE_BOOT / "payload.d"): str(package / "payload.d"),
        str(BASE_BOOT / "probe.elf"): str(package / "probe.elf"),
        str(BASE_BOOT / "probe.bin"): str(package / "probe.bin"),
    }
    commands = [
        ("main-compile", [replacements.get(arg, arg) for arg in old_command("main-compile.log")]),
        ("payload-compile", [replacements.get(arg, arg) for arg in old_command("payload-compile.log")]),
        ("trial-link", [replacements.get(arg, arg) for arg in old_command("batch-link.log")]),
        ("trial-copy", [replacements.get(arg, arg) for arg in old_command("batch-copy.log")]),
    ]
    command_records = []
    for label, command in commands:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=90)
        (package / (label + ".stdout")).write_text(result.stdout)
        (package / (label + ".stderr")).write_text(result.stderr)
        command_records.append({"label": label, "command": command, "returncode": result.returncode,
                                "stdout": label + ".stdout", "stderr": label + ".stderr"})
        if result.returncode or result.stderr:
            raise ValueError(label + " failed: " + result.stderr[-4000:])

    pins = {
        str(BASE_BOOT / "manifest.json"): BASE_BOOT_MANIFEST_SHA256,
        str(root_manifest): root_manifest_sha,
        str(Path(__file__).resolve()): sha(Path(__file__).resolve()),
        str(Path(transport.__file__).resolve()): sha(Path(transport.__file__).resolve()),
    }
    for command in (row[1] for row in commands):
        for argument in command:
            path = Path(argument)
            if path.is_absolute() and path.is_file() and not path.is_relative_to(package):
                merge(pins, {str(path): sha(path)})
    for dependency_file in (package / "main.d", package / "payload.d"):
        for name, digest in boot.base.dependencies(dependency_file.read_text()).items():
            merge(pins, {name: digest})
    boot.base.verify(pins)

    raw = (package / "probe.bin").read_bytes()
    payload_offset = base["handoff"]["payload_offset"]
    if raw[:payload_offset].count((new_marker + "\r\n\0").encode()) != 1:
        raise ValueError("fresh recursive marker is not unique in the real loader")
    if old_marker.encode() in raw:
        raise ValueError("predecessor trial marker leaked into recursive image")
    if (package / "payload.bin").read_bytes()[:-root_report["output_bytes"]] != old_payload[:-len(old_root_raw)]:
        raise ValueError("kernel payload prefix changed")

    generated = {str(path): sha(path) for path in package.iterdir() if path.is_file()}
    report = {
        "profile": PROFILE,
        "tag": tag,
        "trial_marker": new_marker,
        "default_off": True,
        "hardware_execution": False,
        "inputs_sha256": pins,
        "generated_sha256": generated,
        "commands": command_records,
        "tool_identity": boot.base.tool_identity(),
        "image": str(package / "probe.bin"),
        "image_sha256": sha(package / "probe.bin"),
        "image_bytes": len(raw),
        "kernel": base["kernel"],
        "kernel_sha256": base["kernel_sha256"],
        "kernel_manifest": base["kernel_manifest"],
        "kernel_manifest_sha256": base["kernel_manifest_sha256"],
        "root": str(root_directory / "ramdisk.bin"),
        "root_sha256": root_report["output_sha256"],
        "root_manifest": str(root_manifest),
        "root_manifest_sha256": root_manifest_sha,
        "root_nodes": 42,
        "root_files": 30,
        "handoff": base["handoff"],
        "geometry": base["geometry"],
        "normal_firmware_sha256": base["normal_firmware_sha256"],
        "terminal_watchdog_seconds": base["terminal_watchdog_seconds"],
        "hardware_watchdog_seconds": base["hardware_watchdog_seconds"],
        "watchdog_ready_marker": base["watchdog_ready_marker"],
        "watchdog_ready_profile": base["watchdog_ready_profile"],
        "frozen_terminal_boot_manifest": str(BASE_BOOT / "manifest.json"),
        "frozen_terminal_boot_manifest_sha256": BASE_BOOT_MANIFEST_SHA256,
        "only_root_payload_and_unique_trial_marker_changed": True,
        "recursive_target": str(TARGET),
        "recursive_target_sha256": transport.TARGET_SHA256,
        "execution_contract": transport.execution_contract(),
        "automatic_return_and_restoration_required": True,
        "qualified_for_future_staging": False,
        "remaining_action": "sealed prepare/publish, one bounded serial run, automatic Linux return, and loader restoration",
        "installed": False,
        "pi_executed": False,
        "serial_actions": 0,
        "sd_actions": 0,
        "reboots": 0,
        "networking": False,
        "ssh_transport": False,
        "ssh_daemon": False,
    }
    (package / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return package, report


def build():
    root_directory, root_report = build_root()
    package, report = build_boot(root_directory, root_report)
    return package, report


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    directory, record = build()
    print(json.dumps({
        "package": str(directory),
        "manifest_sha256": sha(directory / "manifest.json"),
        "image": record["image"],
        "image_sha256": record["image_sha256"],
        "root": record["root"],
        "root_sha256": record["root_sha256"],
        "target_sha256": record["recursive_target_sha256"],
        "trial_marker": record["trial_marker"],
        "hardware_execution": False,
    }, indent=2, sort_keys=True))
