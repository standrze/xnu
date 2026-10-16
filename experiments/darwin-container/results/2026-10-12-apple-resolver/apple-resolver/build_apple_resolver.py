#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build standalone Apple res_ninit/res_nquery/res_nsend against source Libc."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

from prepare_pid1 import inspect

HERE = Path(__file__).resolve().parent
PINS = {
    "apple-libresolv-96": "e48cd914edc1cb14f8289b8e2dfdaac360481cd2",
    "apple-configd-453.19": "5ab18e75fd838206cf76cab596a41a3050404867",
    "apple-Libnotify-121": "7d2c4ee53f37a1f43d2b075d3e848b2483028e6a",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command):
    return subprocess.check_output([str(item) for item in command], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, default=HERE / "build/zsh-terminal-static-1/manifest.json")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    upstream = HERE / "upstream"
    for name, commit in PINS.items():
        checkout = upstream / name
        if run(["git", "-C", checkout, "rev-parse", "HEAD"]) != commit or run([
                "git", "-C", checkout, "status", "--porcelain", "--untracked-files=no"]):
            raise RuntimeError(f"dirty or unpinned original Apple checkout: {name}")
    sdk = run(["xcrun", "--sdk", "macosx", "--show-sdk-path"])
    resolver = upstream / "apple-libresolv-96"
    modern = upstream / "apple-Libc-1752.120.2"
    baseline = json.loads(args.runtime_manifest.read_text())
    archives = [Path(path) for path in baseline["archives"] if Path(path).name in (
        "libapple-runtime.a", "libapple-posix.a", "libapple-libc-leaf.a")]
    if len(archives) != 3:
        raise RuntimeError("expected exactly the three source-built Apple runtime archives")
    for archive in archives:
        if digest(archive) != baseline["archives"][str(archive)]:
            raise RuntimeError(f"runtime archive changed: {archive}")
    abi = out / "abi"
    run(["python3", HERE / "build_darwin_abi.py", "--network", "--output-dir", abi])
    private_include = out / "include"
    private_include.mkdir()
    (private_include / "_bounds.h").write_bytes((modern / "include/_bounds.h").read_bytes())
    flags = ["-target", "arm64-apple-macosx26.0", "-isysroot", sdk, "-Os", "-ffreestanding",
             "-fno-builtin", "-fno-stack-protector", "-D_FORTIFY_SOURCE=0",
             "-Werror=implicit-function-declaration", "-Wno-deprecated-declarations",
             "-include", str(HERE / "runtime/resolver_build.h"),
             "-I", str(resolver), "-I", str(upstream / "apple-configd-453.19/dnsinfo"),
             "-I", str(upstream / "apple-Libnotify-121"), "-I", str(modern / "darwin"),
             "-I", str(private_include), "-I", str(modern),
             '-D_PATH_RESCONF="/data/resolv.conf"']
    sources = [resolver / (name + ".c") for name in (
        "ns_name", "ns_parse", "ns_netint", "ns_samedomain", "res_comp", "res_init", "res_data", "res_mkquery", "res_query", "res_send")]
    sources += [modern / name for name in (
        "net/inet_ntop.c", "net/inet_pton.c", "net/FreeBSD/inet_addr.c", "gen/FreeBSD/arc4random.c")]
    sources += [HERE / "runtime/resolver_capabilities.c", HERE / "src/resolverctl.c"]
    # Retain Apple-391's asprintf allocation/format algorithm, adapting only
    # the FILE extension and unlocked formatter ABI to the selected Libc-167.
    original_asprintf = upstream / "Libc-Libc-391/stdio/FreeBSD/asprintf.c"
    generated_asprintf = out / "asprintf.c"
    content = original_asprintf.read_text().replace('#include "local.h"', '')
    content = content.replace("struct __sFILEX ext;", "")
    content = content.replace("f._extra = &ext;", "f._extra = NULL;")
    content = content.replace("INITEXTRA(&f);", "")
    content = content.replace("__vfprintf(", "vfprintf(")
    generated_asprintf.write_text(content)
    sources.append(generated_asprintf)
    # These Libc checkouts are archive extractions, not Git worktrees. Verify
    # selected sources and private headers against the already pinned archive
    # bytes rather than accidentally resolving the parent XNU Git HEAD.
    libc_lock_path = HERE / "apple-runtime.sources.lock.json"
    libc_lock = json.loads(libc_lock_path.read_text())
    private_headers = [HERE / "runtime/resolver_build.h", modern / "include/_bounds.h",
                       modern / "darwin/libc_private.h", modern / "os/assumes.h"]
    private_headers += list(resolver.glob("*.h")) + list((resolver / "arpa").glob("*.h"))
    private_headers += [upstream / "apple-configd-453.19/dnsinfo/dnsinfo.h",
                        upstream / "apple-Libnotify-121/notify.h", upstream / "apple-Libnotify-121/notify_private.h"]
    checked_archives = {}
    for pin in libc_lock["sources"]:
        checkout = HERE / pin["localPath"]
        selected = [path for path in [*sources, original_asprintf, *private_headers] if path.is_relative_to(checkout)]
        if not selected:
            continue
        archive = upstream / (pin["tag"] + ".tar.gz")
        if digest(archive) != pin["archiveSHA256"]:
            raise RuntimeError(f"Apple source archive does not match pinned bytes: {archive}")
        with tarfile.open(archive) as package:
            members = {member.name.partition("/")[2]: member for member in package.getmembers() if member.isfile()}
            for path in selected:
                member = members[str(path.relative_to(checkout))]
                if package.extractfile(member).read() != path.read_bytes():
                    raise RuntimeError(f"selected original Apple source changed: {path}")
        checked_archives[pin["tag"]] = pin
    report = {"pins": PINS, "commands": [], "sources": {}, "host_runtime_linked": False,
              "guest_executed": False, "scope": "original Apple direct unicast resolver; explicit unavailable system services",
              "asprintf_adaptations": "FILE extension unused; use selected real Apple vfprintf instead of unlocked variant",
              "verified_libc_archives": checked_archives,
              "private_header_sha256": {str(path): digest(path) for path in private_headers},
              "runtime_lock_sha256": digest(libc_lock_path),
              "capability_limits": ["numeric IPv4 getaddrinfo packaging only, using original Apple inet_pton; not full Libinfo",
                                    "no notifyd/configd/mDNSResponder, multicast or pthread creation",
                                    "static Apple arc4random branch; not the modern corecrypto runtime"]}
    objects = []
    for index, source in enumerate(sources):
        obj = out / f"{index}-{source.stem}.o"
        # The original static branch uses abort(), not os_crash; the private
        # os/assumes declarations are entirely unused in this configuration.
        extra = ["-DVARIANT_STATIC=1", "-D__OS_ASSUMES_H__"] if source.name == "arc4random.c" else []
        command = ["xcrun", "clang", *flags, *extra, "-c", str(source), "-o", str(obj)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (out / f"{index}-{source.stem}.log").write_text(result.stdout + result.stderr)
        report["commands"].append(command)
        report["sources"][str(source)] = digest(source)
        (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
        if result.returncode:
            raise RuntimeError(f"compile failed: {source}\n{result.stderr}")
        objects.append(obj)
    binary = out / "resolverctl"
    command = ["xcrun", "ld", "-arch", "arm64", "-platform_version", "macos", "26.0", "27.0",
               "-static", "-e", "_start", "-dead_strip", "-no_adhoc_codesign", "-no_uuid",
               "-alias", "_fopen", "_fopen$DARWIN_EXTSN", "-map", str(out / "link.map"),
               "-o", str(binary), str(abi / "libdarwin-static-abi.a"), *map(str, objects), *map(str, archives)]
    result = subprocess.run(command, text=True, capture_output=True, timeout=120)
    (out / "link.log").write_text(result.stdout + result.stderr)
    report.update({"link_command": command, "exit": result.returncode,
                   "runtime_archives": {str(path): digest(path) for path in archives},
                   "asprintf_original_sha256": digest(original_asprintf),
                   "builder_sha256": digest(Path(__file__))})
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    if result.returncode:
        raise RuntimeError(result.stderr)
    if run(["xcrun", "nm", "-u", binary]):
        raise RuntimeError("unexpected unresolved import")
    report["executable"] = inspect(binary.read_bytes())
    report["sha256"] = digest(binary)
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"binary": str(binary), "sha256": report["sha256"]}))


if __name__ == "__main__":
    main()
