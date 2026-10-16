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
ROOT = HERE.parents[2]
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
    parser.add_argument("--libinfo", action="store_true", help="compile original Apple Libinfo public address lookup instead of numeric adapter")
    parser.add_argument("--bootp", action="store_true", help="build dhcpctl using original Apple DHCP wire/BPF/IPv4 routines, not the full IPConfiguration daemon")
    parser.add_argument("--route", action="store_true", help="build original Apple network_cmds route command with source-built Libinfo/Libc")
    args = parser.parse_args()
    if args.bootp and not args.libinfo:
        parser.error("--bootp requires --libinfo")
    if args.route and (not args.libinfo or args.bootp):
        parser.error("--route requires --libinfo and cannot be combined with --bootp")
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    upstream = HERE / "upstream"
    pins = dict(PINS)
    if args.libinfo:
        pins["apple-Libinfo-542.40.3"] = "266295b80361952510d09799a58af6565baf5732"
    if args.bootp:
        pins["apple-bootp-268.1"] = "b470df0907d7a641d2f41b5c3bb38e93ed4602fe"
    if args.route:
        pins["apple-network_cmds-396.6"] = "f8c87f3c5eccdeb95e414c6b1b0c3b9dca4233ca"
    for name, commit in pins.items():
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
    sources.append(HERE / "runtime/resolver_capabilities.c")
    if not args.route:
        sources.append(HERE / ("src/dhcpctl.c" if args.bootp else "src/resolverctl.c"))
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
    if args.libinfo:
        libinfo = upstream / "apple-Libinfo-542.40.3"
        flags += ["-DDARWIN_APPLE_LIBINFO=1", "-fblocks", "-I", str(libinfo / "Libinfo"),
                  "-I", str(libinfo / "lookup.subproj"), "-include", str(HERE / "runtime/libinfo_build.h")]
        # These headers only affect discarded asynchronous/dyld declarations.
        # Synchronous lookup imports no dyld or dispatch implementation.
        (private_include / "mach-o").mkdir()
        (private_include / "mach-o/dyld_priv.h").write_text("/* Unused include in original libinfo.c; no dyld APIs referenced. */\n")
        (private_include / "dispatch").mkdir()
        (private_include / "dispatch/private.h").write_text("/* Async code is dead-stripped in this static build. */\n#define DISPATCH_QUEUE_OVERCOMMIT 2\n")
        (private_include / "sys").mkdir()
        (private_include / "net").mkdir()
        (private_include / "sys/sys_domain.h").write_bytes((ROOT / "bsd/sys/sys_domain.h").read_bytes())
        (private_include / "net/netsrc.h").write_bytes((ROOT / "bsd/net/netsrc.h").read_bytes())
        for header in ("sys/socketvar.h", "net/ntstat.h"):
            (private_include / header).write_text("/* Unused private include in original si_compare.c. */\n")
        sources += [libinfo / "lookup.subproj" / (name + ".c") for name in (
            "libinfo", "si_getaddrinfo", "si_data", "ils", "si_module", "si_compare", "getnameinfo_link")]
        sources += [libinfo / "gen.subproj" / (name + ".c") for name in (
            "getifaddrs", "if_indextoname", "if_nametoindex")]
        sources += [HERE / "runtime/libinfo_capabilities.c"]
        sources += [modern / "net/FreeBSD/send.c", modern / "net/FreeBSD/recv.c",
                    upstream / "Libc-Libc-391/stdlib/FreeBSD/reallocf.c"]
    if args.bootp:
        bootp = upstream / "apple-bootp-268.1"
        flags += ["-DDARWIN_APPLE_BOOTP=1", "-I", str(bootp / "bootplib"),
                  "-I", str(bootp / "IPConfiguration.bproj"),
                  "-include", str(HERE / "runtime/bootp_build.h")]
        (private_include / "SystemConfiguration").mkdir()
        (private_include / "SystemConfiguration/SCPrivate.h").write_text(
            "/* Only discarded CF-format diagnostics reference this API. */\n"
            "#include <CoreFoundation/CoreFoundation.h>\n"
            "#include <stdio.h>\n"
            "extern void SCPrint(Boolean, FILE *, CFStringRef, ...);\n")
        (private_include / "net/firewire.h").write_bytes((ROOT / "bsd/net/firewire.h").read_bytes())
        sources += [bootp / "bootplib" / (name + ".c") for name in (
            "dhcp_options", "dhcplib", "ptrlist", "bpflib", "bootp_transmit", "in_cksum")]
        sources.append(HERE / "runtime/bootp_guard.c")
        sources.append(upstream / "Libc-Libc-391/string/FreeBSD/bcmp.c")
        # Compile the complete original IPv4 section, with no algorithm edits.
        # The following IPv6/CGA section needs a different dependency closure.
        original_ifutil = bootp / "IPConfiguration.bproj/ifutil.c"
        content = original_ifutil.read_text()
        boundary = '\n#include <netinet6/in6_var.h>'
        if content.count(boundary) != 1:
            raise RuntimeError("unexpected Apple ifutil IPv4 section boundary")
        generated_ifutil = out / "ifutil-ipv4.c"
        generated_ifutil.write_text(content.split(boundary)[0] + "\n")
        sources.append(generated_ifutil)
    if args.route:
        network_cmds = upstream / "apple-network_cmds-396.6"
        flags += ["-DINET6=1", "-DDARWIN_APPLE_ROUTE=1", "-include", str(HERE / "runtime/network_command_build.h")]
        sources += [network_cmds / "route.tproj/route.c", HERE / "runtime/network_command_start.c"]
        sources.append(libinfo / "lookup.subproj/thread_data.c")
        old = upstream / "Libc-Libc-167"
        sources += [old / "gen.subproj/err.c", old / "stdlib.subproj/getopt.c"]
        sources += [upstream / "Libc-Libc-391" / name for name in (
            "net/FreeBSD/inet_ntoa.c", "net/FreeBSD/inet_netof.c", "net/FreeBSD/inet_lnaof.c",
            "net/FreeBSD/inet_network.c", "net/FreeBSD/linkaddr.c", "gen/FreeBSD/gethostname.c")]
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
    if args.libinfo:
        private_headers += list((libinfo / "lookup.subproj").glob("*.h"))
        private_headers += [libinfo / "Libinfo/libinfo_common.h"]
        private_headers += [HERE / "runtime/libinfo_build.h", ROOT / "bsd/sys/sys_domain.h",
                            ROOT / "bsd/net/netsrc.h", ROOT / "bsd/sys/socket.h",
                            ROOT / "bsd/netinet/in_private.h", modern / "fbsdcompat/namespace.h",
                            modern / "fbsdcompat/un-namespace.h"]
        flags += ["-I", str(modern / "fbsdcompat")]
        # Apple's published header-only atomic implementations, not host
        # libplatform linkage or replacement reference-count algorithms.
        platform = upstream / "apple-libplatform-375.120.2"
        (private_include / "libkern").mkdir()
        for name in ("OSAtomic.h", "OSAtomicDeprecated.h", "OSAtomicQueue.h", "OSSpinLockDeprecated.h"):
            original = platform / "include/libkern" / name
            (private_include / "libkern" / name).write_bytes(original.read_bytes())
            private_headers.append(original)
        flags += ["-DOSATOMIC_USE_INLINED=1"]
    if args.bootp:
        private_headers += list((bootp / "bootplib").glob("*.h"))
        private_headers += [bootp / "IPConfiguration.bproj" / name for name in (
            "ifutil.h", "rtutil.h", "mylog.h", "CGA.h")]
        private_headers += [HERE / "runtime/bootp_build.h", HERE / "runtime/bootp_guard.h",
                            ROOT / "bsd/sys/sockio_private.h", ROOT / "bsd/net/firewire.h"]
    if args.route:
        private_headers += [network_cmds / "route.tproj/keywords.h", HERE / "runtime/network_command_build.h",
                            ROOT / "bsd/net/route.h"]
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
    report = {"pins": pins, "commands": [], "sources": {}, "host_runtime_linked": False,
              "guest_executed": False, "scope": "original Apple direct unicast resolver; explicit unavailable system services",
              "asprintf_adaptations": "FILE extension unused; use selected real Apple vfprintf instead of unlocked variant",
              "verified_libc_archives": checked_archives,
              "private_header_sha256": {str(path): digest(path) for path in private_headers},
              "runtime_lock_sha256": digest(libc_lock_path),
              "apple_libinfo": args.libinfo,
              "apple_bootp": args.bootp,
              "apple_route": args.route,
              "capability_limits": [("original Libinfo public lookup, with bounded project direct-unicast module; not the macOS search/cache/mDNS service" if args.libinfo
                                     else "numeric IPv4 getaddrinfo packaging only, using original Apple inet_pton; not full Libinfo"),
                                    "no notifyd/configd/mDNSResponder, multicast or pthread creation",
                                    "single-thread once/mutex adapters and disabled unified logging" if args.libinfo else "no Libinfo runtime",
                                    "static Apple arc4random branch; not the modern corecrypto runtime"]}
    if args.bootp:
        report["ifutil_original"] = {"path": str(original_ifutil), "sha256": digest(original_ifutil),
                                     "selection": "entire IPv4 section before netinet6/in6_var.h; no algorithm changes"}
        report["capability_limits"] += ["project bounded DHCP orchestration/default-route adapter; not original Apple daemon or lease renewal",
                                        "original DHCP options parser guarded by project TLV length/overload validation",
                                        "C-format packet/IPv4 diagnostics redirected to real stdio; no CF runtime linked"]
    if args.route:
        report["scope"] = "original Apple network_cmds route command with source-built Libc/Libinfo; build evidence only"
        report["capability_limits"] += ["original route command built with INET6; network connectivity qualification remains IPv4",
                                        "project static entry captures actual argv for original Apple error/getopt routines",
                                        "original Libinfo thread_data with bounded project single-thread key storage; not full pthreads",
                                        "Libinfo reverse/network database service methods unavailable; numeric -n mode is qualified"]
    objects = []
    for index, source in enumerate(sources):
        obj = out / f"{index}-{source.stem}.o"
        # The original static branch uses abort(), not os_crash; the private
        # os/assumes declarations are entirely unused in this configuration.
        extra = ["-DVARIANT_STATIC=1", "-D__OS_ASSUMES_H__"] if source.name == "arc4random.c" else []
        if args.libinfo and source.name == "libinfo.c":
            extra += ["-Dsi_module_with_name=darwin_network_module_factory"]
        if args.libinfo and source.name in ("send.c", "recv.c"):
            extra += ["-D__sendto_nocancel=sendto", "-D__recvfrom_nocancel=recvfrom"]
        if args.route and source.name == "route.c":
            extra += ["-Dmain=darwin_network_command_main"]
        command = ["xcrun", "clang", *flags, *extra, "-c", str(source), "-o", str(obj)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (out / f"{index}-{source.stem}.log").write_text(result.stdout + result.stderr)
        report["commands"].append(command)
        report["sources"][str(source)] = digest(source)
        (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
        if result.returncode:
            raise RuntimeError(f"compile failed: {source}\n{result.stderr}")
        objects.append(obj)
    binary = out / ("route" if args.route else "dhcpctl" if args.bootp else "resolverctl")
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
