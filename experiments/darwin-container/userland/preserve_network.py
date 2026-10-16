#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserve one actual networking+PTY trial; never relabel it full-goal evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("session", "loader", "ramroot", "zsh-build", "kernel-build", "cli",
                 "data-disk", "native-check", "output", "working"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--shared-gpu", action="store_true", help="Additionally require actual guest/host Metal proof")
    parser.add_argument("--host-check", type=Path, help="Focused host protocol check transcript")
    parser.add_argument("--apple-dns-check", type=Path, help="Original DNS parser native boundary check transcript")
    parser.add_argument("--resolver-build", type=Path, help="Additionally require and preserve original Apple UDP/TCP resolver evidence")
    parser.add_argument("--apple-libinfo", action="store_true", help="Additionally require original Apple public address/interface lookup and resolved TCP")
    args = parser.parse_args()
    if args.apple_libinfo and not args.resolver_build:
        parser.error("--apple-libinfo requires --resolver-build")
    result = load(args.session / "result.json")
    trial = load(args.session / "terminal-trial.json")
    terminal = result.get("terminal", {})
    fixture = trial.get("network_fixture", {})
    events = fixture.get("events", [])
    dns = [e for e in events if e.get("type") == "dns"]
    tcp = [e for e in events if e.get("type") == "tcp"]
    dns_tcp = [e for e in events if e.get("type") == "dns_tcp"]
    if not (result["started"] and result["guestStopped"] and result["termination"] == "guestStopped"
            and not result.get("error") and not trial["error"] and trial["cli_exit"] == 0
            and terminal.get("handshakeCompleted") and terminal.get("exitStatus") == 0
            and not terminal.get("error") and terminal.get("acknowledgedSizes") == [[35, 120], [47, 132]]
            and trial["cli_sha256"] == digest(args.cli) and not fixture.get("errors")
            and len(dns) == (3 if args.apple_libinfo else 2 if args.resolver_build else 1)
            and len(tcp) == (2 if args.apple_libinfo else 1) and dns[0]["guest"] == tcp[0]["guest"]
            and dns[0]["name"] == tcp[0]["echo"] + ".darwin.test"):
        raise RuntimeError("incomplete actual network+terminal trial")
    output = (args.session / "terminal-output.bin").read_bytes().replace(b"\r", b"")
    for marker in (b"DARWIN:NET:DHCP IP=", b"NET_DHCP_STATUS:0", b"DARWIN:NET:DNS",
                   b"DARWIN:NET:TCP", b"NET_EXCHANGE_STATUS:0", b"\nZLE_EDIT\n",
                   b"\nTERMINAL_TTY_JOB_OK\n", b"\nJOB_STATUS:130\n", b"SIZE_CHANGED:47:132",
                   b"BYTE_ROUNDTRIP:\x80\xff:END", b"suspended", b"continued"):
        if marker not in output:
            raise RuntimeError(f"missing decoded guest marker: {marker!r}")
    root = load(args.ramroot / "manifest.json")
    loader = load(args.loader / "manifest.json")
    kernel = load(args.kernel_build / "manifest.json")
    link = load(args.zsh_build / "manifest.json")
    if not (root["framed_terminal"] and root["pty_relay"] and root["writable_storage"]
            and root["network_diagnostic"] and kernel["network_profile"]
            and root["sha256"] == digest(args.ramroot / "ramdisk.bin") == loader["inputs"]["ramrootSHA256"]
            and root["apple_zsh"]["executable"]["sha256"] == link["sha256"] == digest(args.zsh_build / "zsh")
            and kernel["exit_code"] == 0 and loader["inputs"]["kernelSHA256"] in {k["sha256"] for k in kernel["kernels"]}
            and digest(Path(loader["inputs"]["kernelSource"])) == loader["inputs"]["kernelSHA256"]):
        raise RuntimeError("kernel/root/zsh provenance mismatch")
    if args.shared_gpu:
        gpu = result.get("gpu", {})
        seeds = trial.get("gpu_seeds", [])
        ops = gpu.get("operations", [])
        if not (root.get("shared_gpu_client") and gpu.get("enabled") and gpu.get("deviceName")
                and not gpu.get("error") and gpu.get("submitted") == 3 and gpu.get("completed") == 2
                and gpu.get("rejected") == 1 and len(seeds) == 2 and len(ops) == 3 and ops[-1]["status"] == 1):
            raise RuntimeError("missing actual shared Metal session evidence")
        for index, seed in enumerate(seeds):
            a = [(seed + i) * 0.5 for i in range(16)]
            b = [-i * 0.25 for i in range(16)]
            if not (ops[index]["status"] == 0 and ops[index]["left"] == a and ops[index]["right"] == b
                    and ops[index]["result"] == [x + y for x, y in zip(a, b)]
                    and f"DARWIN:GPU:ADD OK seed={seed} count=16".encode() in output):
                raise RuntimeError("guest seed/host Metal operands/result mismatch")
    apple_parser = root.get("apple_dns_wire_parser", False)
    if apple_parser:
        if not args.apple_dns_check or b"DARWIN:NET:APPLE_DNS_WIRE libresolv-96" not in output:
            raise RuntimeError("missing actual Apple wire parser checks")
        parser_report = load(args.ramroot / "apple-network/manifest.json")
        pin = parser_report["source_pin"]
        upstream = HERE / pin["localPath"]
        for name, expected in parser_report["source_sha256"].items():
            if digest(upstream / name) != expected:
                raise RuntimeError("Apple parser source changed after build")
    if args.resolver_build:
        resolver = load(args.resolver_build / "manifest.json")
        executable = args.resolver_build / "resolverctl"
        installed = Path(root.get("apple_resolver_binary", ""))
        if not (resolver.get("exit") == 0 and resolver.get("host_runtime_linked") is False
                and digest(executable) == resolver["sha256"] == digest(installed)
                == root["source_inputs_sha256"][str(installed.relative_to(HERE))]
                and len(dns_tcp) == 1 and not fixture.get("errors")
                and all(event["guest"] == tcp[0]["guest"] and event["name"] == dns[0]["name"]
                        and event["answer"] == dns[0]["answer"] for event in [*dns, *dns_tcp])):
            raise RuntimeError("missing exact original Apple resolver binary/fixture provenance")
        for transport in ("udp", "tcp"):
            marker = f"DARWIN:NET:APPLE_QUERY {transport} {dns[0]['name']} {dns[0]['answer']} libresolv-96".encode()
            if marker not in output:
                raise RuntimeError("missing original Apple resolver guest result")
        if args.apple_libinfo:
            if not (resolver.get("apple_libinfo") is True and
                    all(event["guest"] == tcp[0]["guest"] and event["echo"] == tcp[0]["echo"] for event in tcp)):
                raise RuntimeError("missing original Apple Libinfo build/resolved TCP provenance")
            for marker in (b"DARWIN:NET:APPLE_LIBINFO_NUMERIC IPv4 IPv6 errors en0=",
                           f"DARWIN:NET:APPLE_GETADDRINFO {dns[0]['name']} {dns[0]['answer']} Libinfo-542.40.3".encode(),
                           f"DARWIN:NET:APPLE_GAI_TCP ECHO={tcp[0]['echo']}".encode(), b"APPLE_GAI_STATUS:0"):
                if marker not in output:
                    raise RuntimeError("missing original Apple public lookup result")
        for path, expected in {**resolver["sources"], **resolver["private_header_sha256"],
                               **resolver["runtime_archives"]}.items():
            if digest(Path(path)) != expected:
                raise RuntimeError(f"resolver source/runtime changed after build: {path}")
    args.output.mkdir(parents=True, exist_ok=False)
    destination = args.output / "guest-trial"
    destination.mkdir()
    for source in args.session.iterdir():
        if source.is_file() and source.name != "efi-variables.bin":
            shutil.copy2(source, destination / source.name)
    for source, name in ((args.loader / "manifest.json", "loader-manifest.json"),
                         (args.ramroot / "manifest.json", "root-manifest.json"),
                         (args.zsh_build / "manifest.json", "zsh-link-manifest.json"),
                         (args.kernel_build / "manifest.json", "kernel-manifest.json"),
                         (HERE / "apple-zsh-source.json", "apple-zsh-source.json"),
                         (args.native_check, "native-net-ring-check.txt")):
        shutil.copy2(source, args.output / name)
    if args.host_check:
        shutil.copy2(args.host_check, args.output / "host-focused-checks.txt")
    if apple_parser:
        shutil.copy2(args.apple_dns_check, args.output / "native-apple-dns-check.txt")
        shutil.copy2(args.ramroot / "apple-network/manifest.json", args.output / "apple-network-manifest.json")
        shutil.copy2(args.ramroot / "link.map", args.output / "userland-link.map")
        shutil.copy2(HERE / "apple-network.sources.lock.json", args.output / "apple-network.sources.lock.json")
        for name in parser_report["source_sha256"]:
            target = args.output / "apple-network-source" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(upstream / name, target)
    if args.resolver_build:
        for source, name in ((args.resolver_build / "manifest.json", "manifest.json"),
                             (args.resolver_build / "link.map", "link.map"),
                             (args.resolver_build / "abi/manifest.json", "abi-manifest.json"),
                             (HERE / "build_apple_resolver.py", "build_apple_resolver.py"),
                             (HERE / "build_darwin_abi.py", "build_darwin_abi.py"),
                             (HERE / "apple-runtime.sources.lock.json", "apple-runtime.sources.lock.json")):
            target = args.output / "apple-resolver" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        resolver_sources = {**resolver["sources"], **resolver["private_header_sha256"]}
        resolver_sources[str(HERE / "upstream/Libc-Libc-391/stdio/FreeBSD/asprintf.c")] = resolver["asprintf_original_sha256"]
        for name in resolver["pins"]:
            path = HERE / "upstream" / name / "APPLE_LICENSE"
            resolver_sources[str(path)] = digest(path)
        for pin in resolver["verified_libc_archives"].values():
            path = HERE / pin["localPath"] / "APPLE_LICENSE"
            if not path.is_file():
                path = HERE / pin["localPath"] / "LICENSE"
            resolver_sources[str(path)] = digest(path)
        for name, expected in resolver_sources.items():
            source = Path(name)
            if digest(source) != expected:
                raise RuntimeError("resolver preservation source mismatch")
            relative = source.relative_to(HERE) if source.is_relative_to(HERE) else Path("xnu-source") / source.relative_to(HERE.parents[2])
            target = args.output / "apple-resolver/source" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    host_sources = list((HERE.parent / "containerization/Sources/ContainerizationDarwin").glob("*.swift"))
    host_sources += list((HERE.parent / "container/Sources/ContainerCommands/Darwin").glob("*.swift"))
    host_hashes = {str(p.relative_to(HERE.parent)): digest(p) for p in sorted(host_sources)}
    evidence = {str(p.relative_to(args.output)): digest(p) for p in sorted(args.output.rglob("*")) if p.is_file()}
    (args.output / "verification.json").write_text(json.dumps({
        "outcome": ("terminal-network-shared-gpu-smoke-passed-not-full-goal" if args.shared_gpu
                    else "network-smoke-milestone-passed-not-full-goal"), "proved": trial["passed"],
        "kernel_sha256": loader["inputs"]["kernelSHA256"], "zsh_sha256": link["sha256"],
        "remaining": (["guest GPU client/channel and returned real Metal result"] if not args.shared_gpu else [])
                     + ["pinned Apple address/DHCP configuration and full Libinfo/service integration"],
        "limits": (["original Apple Libinfo public lookup with bounded direct-unicast module; no macOS search/cache/mDNS/configd service"] if args.apple_libinfo else
                   ["original Apple unicast resolver with restricted numeric IPv4 getaddrinfo adapter; not full Libinfo or configd"]
                   if args.resolver_build else [("original Apple DNS wire parser only; not full resolver/configuration service" if apple_parser
                    else "project bootstrap netctl, not Apple ipconfig/Libresolv")])
                  + ["nonce-bound fixture DNS A lookup and TCP echo, not general internet or IPv6 qualification",
                   "DHCP bootstrap only, no lease renewal", "not a soak or production isolation"]
                  + (["GPU bridge: float32 vector add only, 16 elements/request, 1024 requests/VM; not a Metal ABI or desktop"]
                     if args.shared_gpu else []),
        "sha256": evidence,
        "host_source_sha256": host_hashes,
    }, indent=2) + "\n")
    args.working.mkdir(parents=True, exist_ok=False, mode=0o700)
    files = {"efi.img": args.loader / "efi.img", "BOOTAA64.EFI": args.loader / "BOOTAA64.EFI",
             "kernel.macho": Path(loader["inputs"]["kernelSource"]), "ramdisk.bin": args.ramroot / "ramdisk.bin",
             "zsh": args.zsh_build / "zsh", "container": args.cli, "data.raw": args.data_disk,
             "efi-variables-template.bin": args.session / "efi-variables.bin"}
    if args.resolver_build:
        files["resolverctl"] = args.resolver_build / "resolverctl"
    for name, source in files.items():
        shutil.copy2(source, args.working / name)
        (args.working / name).chmod(0o700 if name == "container" else 0o600)
    (args.working / "manifest.json").write_text(json.dumps({
        "scope": "private network+PTY" + ("+shared GPU" if args.shared_gpu else "")
                 + " snapshot, not a versioned release or completed overall goal",
        "warning": "EFI and variables contain entropy; do not publish or assume safe seed reuse",
        "evidence": str(args.output.resolve()), "sha256": {name: digest(args.working / name) for name in files},
    }, indent=2) + "\n")
    print(args.output / "verification.json")
    print(args.working / "manifest.json")


if __name__ == "__main__":
    main()
