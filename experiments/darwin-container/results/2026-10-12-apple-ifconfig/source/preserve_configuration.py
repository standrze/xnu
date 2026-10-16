#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserve narrow Apple-bootp VM evidence without weakening prior verifiers."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from inspect_initializers import inspect_initializers

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("session", "loader", "ramroot", "bootp-build", "resolver-build", "zsh-build",
                 "kernel-build", "cli", "data-disk", "output", "working"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--route-build", type=Path, help="add original Apple route command provenance and require real routing-table trial")
    parser.add_argument("--ifconfig-build", type=Path, help="add original Apple ifconfig provenance and require actual MTU change/restore readback")
    args = parser.parse_args()
    if args.output.exists() or args.working.exists():
        parser.error("evidence and private checkpoint directories must be new")
    result = load(args.session / "result.json")
    trial = load(args.session / "configuration-trial.json")
    terminal = result.get("terminal", {})
    fixture = trial.get("network_fixture", {})
    events = fixture.get("events", [])
    if not (result.get("started") and result.get("guestStopped") and result.get("termination") == "guestStopped"
            and not result.get("error") and trial.get("error") is None and trial.get("cli_exit") == 0
            and len(trial.get("passed", [])) == 4 + bool(args.route_build) + bool(args.ifconfig_build)
            and bool(trial.get("apple_route")) == bool(args.route_build) and trial.get("cli_sha256") == digest(args.cli)
            and bool(trial.get("apple_ifconfig")) == bool(args.ifconfig_build)
            and terminal.get("handshakeCompleted") and terminal.get("exitStatus") == 0
            and not terminal.get("error") and not result.get("gpu", {}).get("enabled")
            and sorted(event.get("type", "") for event in events) == ["dns", "tcp"] and not fixture.get("errors")):
        raise RuntimeError("incomplete narrow configuration trial")
    dns = next(event for event in events if event["type"] == "dns")
    tcp = next(event for event in events if event["type"] == "tcp")
    if not (dns["guest"] == tcp["guest"] and dns["name"] == tcp["echo"] + ".darwin.test"
            and tcp["echo"] == fixture["token"] and re.fullmatch(r"[0-9a-f]{24}", tcp["echo"])):
        raise RuntimeError("independent fixture nonce/address mismatch")
    output = (args.session / "terminal-output.bin").read_bytes().replace(b"\r", b"")
    for marker in (b"\nDARWIN:NET:APPLE_BOOTP bootp-268.1 options match BPF checksum IPv4\n",
                   b"\nDARWIN:NET:DHCP IP=", b"\nAPPLE_BOOTP_STATUS:0\n", b"\nCONFIG_DNS_STATUS:0\n",
                   f"\nDARWIN:NET:APPLE_GETADDRINFO {dns['name']} {dns['answer']} Libinfo-542.40.3\n".encode(),
                   f"\nDARWIN:NET:APPLE_GAI_TCP ECHO={tcp['echo']}\n".encode(), b"\nAPPLE_GAI_STATUS:0\n"):
        if marker not in output:
            raise RuntimeError(f"missing decoded guest result: {marker!r}")
    root = load(args.ramroot / "manifest.json")
    loader = load(args.loader / "manifest.json")
    kernel = load(args.kernel_build / "manifest.json")
    zsh = load(args.zsh_build / "manifest.json")
    bootp = load(args.bootp_build / "manifest.json")
    resolver = load(args.resolver_build / "manifest.json")
    if not (root.get("framed_terminal") and root.get("pty_relay") and root.get("writable_storage")
            and kernel.get("network_profile") and kernel.get("exit_code") == 0
            and digest(args.ramroot / "ramdisk.bin") == root["sha256"] == loader["inputs"]["ramrootSHA256"]
            and digest(Path(loader["inputs"]["kernelSource"])) == loader["inputs"]["kernelSHA256"]
            and loader["inputs"]["kernelSHA256"] in {entry["sha256"] for entry in kernel["kernels"]}
            and digest(args.zsh_build / "zsh") == zsh["sha256"] == root["apple_zsh"]["executable"]["sha256"]
            and digest(args.bootp_build / "dhcpctl") == bootp["sha256"] == digest(Path(root["apple_network_config_binary"]))
            and digest(args.resolver_build / "resolverctl") == resolver["sha256"] == digest(Path(root["apple_resolver_binary"]))
            and bootp.get("apple_bootp") and bootp.get("apple_libinfo") and bootp.get("exit") == 0
            and bootp.get("host_runtime_linked") is False and resolver.get("apple_libinfo")):
        raise RuntimeError("kernel/root/original-binary provenance mismatch")
    for name, expected in root["source_inputs_sha256"].items():
        if digest(HERE / name) != expected:
            raise RuntimeError(f"root build input changed: {name}")
    source_hashes = {**bootp["sources"], **bootp["private_header_sha256"]}
    source_hashes[bootp["ifutil_original"]["path"]] = bootp["ifutil_original"]["sha256"]
    source_hashes[str(HERE / "upstream/Libc-Libc-391/stdio/FreeBSD/asprintf.c")] = bootp["asprintf_original_sha256"]
    for name, expected in {**source_hashes, **bootp["runtime_archives"]}.items():
        if digest(Path(name)) != expected:
            raise RuntimeError(f"built source/archive changed: {name}")
    if digest(HERE / "build_apple_resolver.py") != bootp["builder_sha256"]:
        raise RuntimeError("Apple bootp builder changed after compilation")
    route = None
    if args.route_build:
        route = load(args.route_build / "manifest.json")
        installed = Path(root.get("apple_route_binary") or "missing-route")
        if not (route.get("apple_route") and route.get("apple_libinfo") and route.get("exit") == 0
                and route.get("host_runtime_linked") is False
                and digest(args.route_build / "route") == route["sha256"] == digest(installed)
                and digest(HERE / "build_apple_resolver.py") == route["builder_sha256"]):
            raise RuntimeError("missing exact original Apple route build/installed binary")
        for marker in (b"\ndelete net default\n", f"\nadd net default: gateway {dns['answer']}\n".encode(),
                       b"\n   route to: default\n", f"\n    gateway: {dns['answer']}\n".encode(),
                       b"\n  interface: en0\n", b"\nAPPLE_ROUTE_STATUS:0\n"):
            if marker not in output:
                raise RuntimeError(f"missing original Apple route guest result: {marker!r}")
        route_link = (args.route_build / "link.map").read_text().split("# Dead Stripped Symbols:")[0]
        for symbol in ("darwin_network_command_main", "newroute", "rtmsg", "print_getmsg", "getaddr", "getopt"):
            if not re.search(r"\]\s+_" + symbol + r"$", route_link, re.MULTILINE):
                raise RuntimeError(f"original route implementation discarded: {symbol}")
        for name, expected in {**route["sources"], **route["private_header_sha256"], **route["runtime_archives"]}.items():
            if digest(Path(name)) != expected:
                raise RuntimeError(f"route build source/archive changed: {name}")
        source_hashes.update({**route["sources"], **route["private_header_sha256"]})
    ifconfig = None
    initializers = None
    if args.ifconfig_build:
        ifconfig = load(args.ifconfig_build / "manifest.json")
        installed = Path(root.get("apple_ifconfig_binary") or "missing-ifconfig")
        if not (ifconfig.get("apple_ifconfig") and ifconfig.get("apple_libinfo") and ifconfig.get("exit") == 0
                and ifconfig.get("host_runtime_linked") is False
                and digest(args.ifconfig_build / "ifconfig") == ifconfig["sha256"] == digest(installed)
                and digest(HERE / "build_apple_resolver.py") == ifconfig["builder_sha256"]):
            raise RuntimeError("missing exact original Apple ifconfig build/installed binary")
        lease = re.search(rb"DARWIN:NET:DHCP IP=([0-9.]+) MASK=([0-9.]+) ROUTER=([0-9.]+) DNS=([0-9.]+) LEASE=([0-9]+)", output)
        if not lease:
            raise RuntimeError("missing actual DHCP lease for interface readback")
        begin = 0
        for mtu, stage in ((1400, "SET"), (1500, "RESTORE")):
            end = output.find(f"\nAPPLE_IFCONFIG_{stage}_STATUS:0\n".encode(), begin)
            if end < 0:
                raise RuntimeError("missing successful original ifconfig command output")
            actual = output[begin:end]
            if not re.search(rb"(?:^|\n)en0: flags=[^\n]* mtu " + str(mtu).encode() + rb"\n", actual):
                raise RuntimeError("missing original ifconfig actual MTU readback")
            if not re.search(rb"\n\s+inet " + re.escape(lease[1]) + rb" netmask ", actual):
                raise RuntimeError("missing original ifconfig actual IPv4 display")
            begin = end + 1
        constructors = tuple("_" + name + "_ctor" for name in
                             ("inet", "inet6", "link", "bond", "bridge", "clone", "ifconfig", "ifmedia", "vlan"))
        initializers = inspect_initializers((args.ifconfig_build / "ifconfig").read_bytes(), constructors)
        ifconfig_link = (args.ifconfig_build / "link.map").read_text().split("# Dead Stripped Symbols:")[0]
        for symbol in ("darwin_network_command_main", "af_register", "cmd_register", "setifmtu", "in_status", "in_getaddr", "strtold", "sscanf"):
            if not re.search(r"\]\s+_" + symbol + r"$", ifconfig_link, re.MULTILINE):
                raise RuntimeError(f"original ifconfig implementation discarded: {symbol}")
        for name, expected in {**ifconfig["sources"], **ifconfig["private_header_sha256"], **ifconfig["runtime_archives"]}.items():
            if digest(Path(name)) != expected:
                raise RuntimeError(f"ifconfig source/archive changed: {name}")
        source_hashes.update({**ifconfig["sources"], **ifconfig["private_header_sha256"]})
    pins = {**bootp["pins"], **(route["pins"] if route else {}), **(ifconfig["pins"] if ifconfig else {})}
    for name in pins:
        checkout = HERE / "upstream" / name
        head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=no"], text=True)
        if head != pins[name] or dirty:
            raise RuntimeError(f"original Apple checkout changed: {name}")
        license_path = checkout / "APPLE_LICENSE"
        source_hashes[str(license_path)] = digest(license_path)
    archive_pins = {**bootp["verified_libc_archives"], **(route["verified_libc_archives"] if route else {}),
                    **(ifconfig["verified_libc_archives"] if ifconfig else {})}
    license_notes = []
    for pin in archive_pins.values():
        license_path = HERE / pin["localPath"] / "APPLE_LICENSE"
        if not license_path.is_file():
            license_path = HERE / pin["localPath"] / "LICENSE"
        if not license_path.is_file() and pin["tag"] == "Libc-167":
            # This original archive has no top-level license text. Its selected
            # files carry APSL 1.1 and BSD notices, retained verbatim below.
            selected = [Path(name) for name in source_hashes if Path(name).is_relative_to(HERE / pin["localPath"])]
            if not selected or not all("Apple Public Source License Version 1.1" in path.read_text() for path in selected):
                raise RuntimeError("unexpected Libc-167 source notice boundary")
            license_notes.append("Libc-167 archive has no top-level license text; selected files retain original APSL 1.1/BSD notices; distribution-license bundle is not qualified")
            continue
        source_hashes[str(license_path)] = digest(license_path)
    link_map = (args.bootp_build / "link.map").read_text().split("# Dead Stripped Symbols:")[0]
    retained = ("dhcpol_parse_packet", "dhcpol_find", "dhcpoa_add", "dhcp_packet_match", "bootp_transmit",
                "bpf_new", "bpf_write", "in_cksum", "inet_attach_interface", "inet_set_autoaddr", "inet_aifaddr")
    for symbol in retained:
        if not re.search(r"\]\s+_" + symbol + r"$", link_map, re.MULTILINE):
            raise RuntimeError(f"required original Apple function was discarded: {symbol}")
    args.output.mkdir(parents=True)
    for source in args.session.iterdir():
        if source.is_file() and source.name != "efi-variables.bin":
            copy(source, args.output / "guest-trial" / source.name)
    for source, target in ((args.loader / "manifest.json", "loader-manifest.json"),
                           (args.ramroot / "manifest.json", "root-manifest.json"),
                           (args.kernel_build / "manifest.json", "kernel-manifest.json"),
                           (args.zsh_build / "manifest.json", "zsh-manifest.json"),
                           (args.resolver_build / "manifest.json", "resolver-manifest.json"),
                           (args.bootp_build / "manifest.json", "bootp-manifest.json"),
                           (args.bootp_build / "link.map", "bootp-link.map")):
        copy(source, args.output / target)
    if route:
        copy(args.route_build / "manifest.json", args.output / "route-manifest.json")
        copy(args.route_build / "link.map", args.output / "route-link.map")
    if ifconfig:
        copy(args.ifconfig_build / "manifest.json", args.output / "ifconfig-manifest.json")
        copy(args.ifconfig_build / "link.map", args.output / "ifconfig-link.map")
    for name in ("build.py", "build_apple_resolver.py", "build_darwin_abi.py", "configuration_trial.py",
                 "terminal_trial.py", "preserve_configuration.py", "apple-runtime.sources.lock.json",
                 "runtime/bootp_guard_test.c"):
        source = HERE / name
        source_hashes[str(source)] = digest(source)
    if route:
        source = HERE / "runtime/network_command_start_test.c"
        source_hashes[str(source)] = digest(source)
    if ifconfig:
        source = HERE / "inspect_initializers.py"
        source_hashes[str(source)] = digest(source)
        source = HERE / "prepare_pid1.py"
        source_hashes[str(source)] = digest(source)
    for name in source_hashes:
        source = Path(name)
        relative = source.relative_to(HERE) if source.is_relative_to(HERE) else Path("xnu-source") / source.relative_to(ROOT)
        copy(source, args.output / "source" / relative)
    for source in (args.bootp_build / "include").rglob("*"):
        if source.is_file():
            copy(source, args.output / "generated-include" / source.relative_to(args.bootp_build / "include"))
    for source in (args.bootp_build / "abi").rglob("*"):
        if source.is_file() and source.suffix not in (".o", ".a"):
            copy(source, args.output / "abi" / source.relative_to(args.bootp_build / "abi"))
    if route:
        for subdir in ("include", "abi"):
            for source in (args.route_build / subdir).rglob("*"):
                if source.is_file() and source.suffix not in (".o", ".a"):
                    copy(source, args.output / "route-generated" / subdir / source.relative_to(args.route_build / subdir))
    if ifconfig:
        for subdir in ("include", "abi"):
            for source in (args.ifconfig_build / subdir).rglob("*"):
                if source.is_file() and source.suffix not in (".o", ".a"):
                    copy(source, args.output / "ifconfig-generated" / subdir / source.relative_to(args.ifconfig_build / subdir))
    # Check only the newly changed project boundary; do not repeat guest PTY/GPU
    # or the unchanged DHCP parser guard in the route-only increment.
    native_binary = args.output / ("network-command-start-test" if route else "bootp-guard-test")
    names = ("network_command_start.c", "network_command_start_test.c") if route else ("bootp_guard.c", "bootp_guard_test.c")
    command = ["xcrun", "clang", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-g",
               *(str(HERE / "runtime" / name) for name in names), "-o", str(native_binary)]
    if route:
        command += ["-D" + name + "=darwin_test_" + name for name in
                    ("pthread_key_create", "pthread_setspecific", "pthread_getspecific", "pthread_key_delete", "_NSGetArgv")]
    if ifconfig:
        # Only the new constructor ABI is inspected; do not rerun unchanged
        # argv/key-storage, DHCP guard, PTY or GPU checks for this increment.
        (args.output / "static-initializer-check.json").write_text(json.dumps(initializers, indent=2) + "\n")
    else:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
        native = subprocess.run([str(native_binary.resolve())], check=True, capture_output=True, text=True, timeout=15)
        (args.output / ("native-command-start-check.json" if route else "native-guard-check.json")).write_text(json.dumps({"compile_command": command,
            "exit": native.returncode, "stdout": native.stdout, "stderr": native.stderr,
            "scope": "ASan/UBSan host project ABI/bounds check only, not guest network proof"}, indent=2) + "\n")
    evidence = {str(p.relative_to(args.output)): digest(p) for p in sorted(args.output.rglob("*")) if p.is_file()}
    (args.output / "verification.json").write_text(json.dumps({
        "outcome": ("apple-ifconfig-route-bootp-guest-smoke-passed-not-full-service-or-goal" if ifconfig else
                    "apple-route-and-bootp-guest-smoke-passed-not-full-service-or-goal" if route else
                    "apple-bootp-selected-routines-guest-smoke-passed-not-full-daemon-or-goal"),
        "proved": trial["passed"], "retained_original_functions": retained,
        "bootp_sha256": bootp["sha256"], "resolver_sha256": resolver["sha256"],
        "route_sha256": route["sha256"] if route else None,
        "ifconfig_sha256": ifconfig["sha256"] if ifconfig else None,
        "static_initializers": initializers,
        "license_notes": license_notes,
        "kernel_sha256": loader["inputs"]["kernelSHA256"], "zsh_sha256": zsh["sha256"],
        "limits": ["project bounded DHCP orchestration, packet preflight and default-route adapter",
                   "not full Apple ipconfigd/configd/CoreFoundation service; no lease renewal or ARP conflict probe",
                   "local nonce-bound DNS/TCP fixture only, not internet/IPv6 qualification",
                   "ifconfig compilation of all original modules does not qualify every device, private ioctl or subcommand",
                   "no repeated PTY/GPU proof or soak; no Pi access", "private VM entropy images are excluded"],
        "sha256": evidence,
    }, indent=2) + "\n")
    args.working.mkdir(parents=True, mode=0o700)
    files = {"efi.img": args.loader / "efi.img", "BOOTAA64.EFI": args.loader / "BOOTAA64.EFI",
             "kernel.macho": Path(loader["inputs"]["kernelSource"]), "ramdisk.bin": args.ramroot / "ramdisk.bin",
             "zsh": args.zsh_build / "zsh", "container": args.cli, "data.raw": args.data_disk,
             "efi-variables-template.bin": args.session / "efi-variables.bin",
             "resolverctl": args.resolver_build / "resolverctl", "dhcpctl": args.bootp_build / "dhcpctl"}
    if route:
        files["route"] = args.route_build / "route"
    if ifconfig:
        files["ifconfig"] = args.ifconfig_build / "ifconfig"
    for name, source in files.items():
        copy(source, args.working / name)
        (args.working / name).chmod(0o700 if name == "container" else 0o600)
    (args.working / "manifest.json").write_text(json.dumps({
        "scope": "private Apple-bootp configuration VM checkpoint, not a versioned release or completed goal",
        "warning": "EFI/variables contain entropy; do not publish or assume safe seed reuse",
        "evidence": str(args.output.resolve()), "sha256": {name: digest(args.working / name) for name in files},
    }, indent=2) + "\n")
    print(args.output / "verification.json")
    print(args.working / "manifest.json")


if __name__ == "__main__":
    main()
