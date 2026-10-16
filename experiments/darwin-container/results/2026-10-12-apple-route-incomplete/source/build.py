#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build the isolated, source-only Darwin VM bootstrap command-line RAM root."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_pid1 import inspect as inspect_macho
from ramroot import build, inspect

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE / "src"
SOURCES = ("start.S", "runtime.c", "parser.c", "shell.c", "utilities.c", "init.c", "poweroff.c")
PROGRAMS = ("sh", "echo", "cat", "ls", "wc", "sleep", "uname", "true", "false", "hexdump", "poweroff")
AGENT_SOURCES = ("agent_protocol.c", "agent.c", "agent_fixtures.c")
AGENT_PROGRAMS = ("agent-bytes", "agent-flood", "agent-stubborn", "agent-escape", "agent-orphan")


def run(*command):
    result = subprocess.run(command, text=True, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command!r}\n{result.stdout}{result.stderr}")
    return (result.stdout or result.stderr).strip()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path, help="new local directory; must not exist")
    parser.add_argument("--mode", choices=("shell", "agent", "zsh", "agent-zsh"), default="shell", help="bootstrap shell, managed agent, interactive zsh or managed Apple zsh workload")
    parser.add_argument("--zsh-binary", type=Path, help="source-built static zsh, required in zsh mode")
    parser.add_argument("--terminfo-dir", type=Path, help="source-built terminfo tree, required in zsh mode")
    parser.add_argument("--storage", action="store_true", help="Mount a separate HFS+ workload disk at /data before starting zsh or agent")
    parser.add_argument("--pty", action="store_true", help="Opt-in real XNU PTY shell/console relay; requires --mode zsh --storage")
    parser.add_argument("--framed-terminal", action="store_true", help="DGT1 binary-safe PTY transport with resize; requires --pty and matching host")
    parser.add_argument("--network", action="store_true", help="Include explicit experimental netctl bring-up diagnostic")
    parser.add_argument("--shared-gpu", action="store_true", help="Typed guest Metal bridge over DGT1; requires --framed-terminal")
    parser.add_argument("--apple-dns", action="store_true", help="Compile/use pinned official Apple DNS wire parser; requires --network")
    parser.add_argument("--resolver-binary", type=Path, help="source-built static Apple resolverctl to install; requires --network --storage")
    parser.add_argument("--network-config-binary", type=Path, help="source-built static dhcpctl to install; requires --network --storage")
    parser.add_argument("--route-binary", type=Path, help="source-built original Apple route command; requires --network")
    args = parser.parse_args()
    managed = args.mode in ("agent", "agent-zsh")
    apple_zsh = args.mode in ("zsh", "agent-zsh")
    if args.framed_terminal and not args.pty:
        parser.error("--framed-terminal requires --pty")
    if args.shared_gpu and not args.framed_terminal:
        parser.error("--shared-gpu requires --framed-terminal")
    if args.apple_dns and not args.network:
        parser.error("--apple-dns requires --network")
    if args.resolver_binary and (not args.network or not args.storage):
        parser.error("--resolver-binary requires --network --storage")
    if args.network_config_binary and (not args.network or not args.storage):
        parser.error("--network-config-binary requires --network --storage")
    if args.route_binary and not args.network:
        parser.error("--route-binary requires --network")
    if args.pty and (args.mode != "zsh" or not args.storage):
        parser.error("--pty requires --mode zsh --storage")
    if args.storage and not apple_zsh:
        parser.error("--storage requires an Apple-zsh mode")
    if apple_zsh and (not args.zsh_binary or not args.terminfo_dir):
        parser.error("zsh modes require --zsh-binary and --terminfo-dir")
    zsh_report = inspect_macho(args.zsh_binary.read_bytes()) if apple_zsh else None
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    compiler = run("xcrun", "--find", "clang")
    linker = run("xcrun", "--find", "ld")
    sdk = run("xcrun", "--sdk", "macosx", "--show-sdk-path")
    commands, objects = [], []
    apple_network_source = None
    if args.apple_dns:
        from build_apple_network import compile_parser
        apple_objects, apple_network_source = compile_parser(out,compiler,sdk)
        objects += apple_objects
    sources = SOURCES + (AGENT_SOURCES if managed else ()) + (("storage.c",) if args.storage else ())
    if args.pty:
        sources += ("terminal.c",)
    if args.framed_terminal:
        sources += ("terminal_protocol.c",)
    if args.network:
        sources += ("network.c",)
    if args.shared_gpu:
        sources += ("gpu_client.c", "gpu_relay.c")
    if args.apple_dns:
        sources += ("apple_dns.c",)
    for name in sources:
        source = SOURCE / name
        obj = out / (source.stem + ".o")
        command = [compiler, "-isysroot", sdk, "-target", "arm64-apple-darwin", "-c", "-Os", "-ffreestanding",
                   "-fno-builtin", "-fno-stack-protector", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(obj)]
        if managed:
            command.insert(1, "-DDARWIN_AGENT_INIT=1")
        elif args.mode == "zsh":
            command.insert(1, "-DDARWIN_ZSH_INIT=1")
        if apple_zsh:
            command.insert(1, "-DDARWIN_APPLE_USERLAND=1")
        if args.pty:
            command.insert(1, "-DDARWIN_PTY_INIT=1")
        if args.framed_terminal:
            command.insert(1, "-DDARWIN_TERMINAL_FRAMED=1")
        if args.network:
            command.insert(1, "-DDARWIN_NETWORK=1")
        if args.shared_gpu:
            command.insert(1, "-DDARWIN_SHARED_GPU=1")
        if args.apple_dns:
            command += ["-DDARWIN_APPLE_DNS=1", "-I", str(apple_network_source), "-D_FORTIFY_SOURCE=0"]
        if args.storage:
            command += ["-DDARWIN_WRITABLE_STORAGE=1", "-D__APPLE_API_UNSTABLE=1", "-I",
                        str(ROOT / "build/rpi5/gate4-sources/hfs/hfs-hfs-715.120.4/core")]
        run(*command)
        commands.append(command)
        objects.append(str(obj))
    executable = out / "userland"
    # No UUID makes identical toolchain/source builds produce identical Mach-O bytes.
    command = [linker, "-arch", "arm64", "-static", "-e", "_start", "-no_adhoc_codesign", "-no_uuid",
               "-o", str(executable), *objects]
    if args.apple_dns:
        command += ["-dead_strip", "-map", str(out / "link.map")]
    run(*command)
    commands.append(command)
    raw = executable.read_bytes()
    executable_report = inspect_macho(raw)
    files = {"/sbin/launchd": (raw, 0o555), "/sbin/init": (raw, 0o555), "/sbin/poweroff": (raw, 0o555)}
    files.update({"/bin/" + name: (raw, 0o555) for name in PROGRAMS})
    if managed:
        files["/sbin/darwin-agent"] = (raw, 0o555)
    if args.mode == "agent":
        files.update({"/bin/" + name: (raw, 0o555) for name in AGENT_PROGRAMS})
    files.update({
        "/etc/motd": (b"Experimental Darwin XNU VM. Source-built bootstrap shell; read-only RAM root.\n", 0o444),
        "/etc/demo.sh": (b"echo DARWIN_DEMO_BEGIN\npwd\nuname -a\ncat /etc/motd | wc\nfalse || echo RECOVERED\necho DARWIN_DEMO_END\n", 0o444),
        "/etc/empty": (b"", 0o444),
    })
    if args.mode == "zsh":
        # Keep within the kernel RAM-root node limit. The recovery bootstrap
        # sh and external-command smoke utilities remain separately available.
        keep = {"/sbin/launchd", "/sbin/init", "/sbin/poweroff", "/bin/sh",
                "/bin/echo", "/bin/uname", "/bin/poweroff", "/etc/motd", "/etc/empty"}
        if args.pty:
            keep.update(("/bin/cat", "/bin/ls", "/bin/sleep"))
        files = {name: record for name, record in files.items() if name in keep}
    if apple_zsh:
        files["/bin/zsh"] = (args.zsh_binary.read_bytes(), 0o555)
        files["/etc/terminfo/64/dumb"] = ((args.terminfo_dir / "64/dumb").read_bytes(), 0o444)
        if args.pty:
            files["/etc/terminfo/76/vt100"] = ((args.terminfo_dir / "76/vt100").read_bytes(), 0o444)
    if args.network:
        files["/bin/netctl"] = (raw, 0o555)
    if args.resolver_binary:
        inspect_macho(args.resolver_binary.read_bytes())
        files["/bin/resolverctl"] = (args.resolver_binary.read_bytes(), 0o555)
    if args.network_config_binary:
        inspect_macho(args.network_config_binary.read_bytes())
        files["/bin/dhcpctl"] = (args.network_config_binary.read_bytes(), 0o555)
    if args.route_binary:
        inspect_macho(args.route_binary.read_bytes())
        files["/bin/route"] = (args.route_binary.read_bytes(), 0o555)
    if args.shared_gpu:
        files["/bin/gpuctl"] = (raw, 0o555)
    if args.storage:
        for name in ("/etc/demo.sh", "/bin/hexdump", "/bin/wc"):
            files.pop(name, None)
        files["/data/.mountpoint"] = (b"Covered by the explicitly attached HFS+ workload disk.\n", 0o444)
    image, report = build(files)
    if inspect(image) != report:
        raise RuntimeError("RAM-root inspection did not match the canonical package")
    with (out / "ramdisk.bin").open("xb") as output:
        output.write(image)
    headers = ("runtime.h", "parser.h") + (("agent_protocol.h",) if managed else ())
    if args.framed_terminal:
        headers += ("terminal_protocol.h",)
    if args.shared_gpu:
        headers += ("gpu_client.h", "gpu_relay.h")
    inputs = [SOURCE / name for name in (*sources, *headers)]
    if apple_zsh:
        inputs += [args.zsh_binary, args.terminfo_dir / "64/dumb"]
        if args.pty:
            inputs += [args.terminfo_dir / "76/vt100"]
    inputs += [Path(__file__), HERE / "ramroot.py", HERE / "prepare_pid1.py", HERE / "source-provenance.json"]
    if args.apple_dns:
        inputs += [HERE / "build_apple_network.py", HERE / "apple-network.sources.lock.json"]
    if args.resolver_binary:
        inputs += [args.resolver_binary]
    if args.network_config_binary:
        inputs += [args.network_config_binary]
    if args.route_binary:
        inputs += [args.route_binary]
    abi_sources = [ROOT / name for name in (
        "bsd/sys/reboot.h", "bsd/kern/syscalls.master", "bsd/kern/kern_xxx.c", "bsd/kern/kern_shutdown.c",
        "bsd/sys/signal.h", "bsd/kern/kern_sig.c",
        "osfmk/arm64/machine_routines.c",
        "experiments/darwin-container/kernel/overlay/pexpert/arm/pe_vzgeneric.c",
    )]
    if managed:
        abi_sources += [ROOT / name for name in ("bsd/sys/termios.h", "bsd/sys/ttycom.h", "bsd/sys/fcntl.h",
                                                "bsd/sys/wait.h", "bsd/dev/arm/km.c", "bsd/kern/kern_time.c")]
    if args.storage:
        abi_sources += [ROOT / "bsd/sys/mount.h", ROOT / "bsd/vfs/vfs_syscalls.c",
                        ROOT / "build/rpi5/gate4-sources/hfs/hfs-hfs-715.120.4/core/hfs_mount.h"]
    if args.pty:
        abi_sources += [ROOT / name for name in ("bsd/sys/ttycom.h", "bsd/sys/termios.h",
                                                "bsd/kern/tty_ptmx.c", "bsd/kern/tty_pty.c")]
    if args.network:
        abi_sources += [ROOT / name for name in ("bsd/sys/socket.h", "bsd/sys/sockio.h", "bsd/sys/sockio_private.h",
                                                "bsd/net/if.h", "bsd/net/if_dl.h", "bsd/net/route.h", "bsd/net/bpf.h",
                                                "bsd/netinet/in.h", "bsd/netinet/in.c")]
    if args.shared_gpu:
        abi_sources += [ROOT / name for name in ("bsd/sys/un.h", "bsd/kern/uipc_usrreq.c", "bsd/sys/socket.h")]
    report.update({
        "executable": executable_report,
        "commands": commands,
        "sdk": sdk,
        "compiler_version": run(compiler, "--version").splitlines()[0],
        "linker_version": run(linker, "-v").splitlines()[0],
        "source_inputs_sha256": {str(p.resolve().relative_to(HERE)): sha256(p) for p in inputs},
        "abi_source_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in abi_sources},
        "poweroff_abi": {"syscall": 55, "flags": 8, "message_pointer": 0, "RB_POWERDOWN": "absent in this XNU",
                         "platform_contract": "RB_HALT -> HOST_REBOOT_HALT -> kPEHaltCPU -> PSCI SYSTEM_OFF"},
        "init_shutdown_abi": {"sigprocmask": 48, "sigpending": 52, "SIGTERM": 15,
                              "SIG_BLOCK": 1, "SIG_SETMASK": 3, "sigset_bytes": 4,
                              "policy": "PID1 blocks TERM, checks pending before fork/respawn, child restores saved mask"},
        "mode": args.mode,
        "writable_storage": args.storage,
        "pty_relay": args.pty,
        "framed_terminal": args.framed_terminal,
        "network_diagnostic": args.network,
        "shared_gpu_client": args.shared_gpu,
        "apple_dns_wire_parser": args.apple_dns,
        "apple_resolver_binary": str(args.resolver_binary.resolve()) if args.resolver_binary else None,
        "apple_network_config_binary": str(args.network_config_binary.resolve()) if args.network_config_binary else None,
        "apple_route_binary": str(args.route_binary.resolve()) if args.route_binary else None,
        "readiness_marker": "DARWIN:AGENT:READY:1" if managed else "DARWIN:SHELL:READY",
        "kernel_contract": "development ARM64 VZGENERIC, static Mach-O exec/fork, RPI5RFS1 mockfs RAM root, /dev/console",
        "scope": "host-built and structurally validated bootstrap userland; not VM execution evidence; not Apple launchd or zsh",
    })
    if managed:
        report["scope"] = "host-built static managed Darwin guest agent; structural/native validation only, not VM execution evidence"
        report["agent_contract"] = {"version": 1, "path": "/sbin/darwin-agent", "transport": "ASCII hex CRC32 DGA1",
                                    "protocol_sha256": sha256(HERE.parent / "agent" / "PROTOCOL.md"),
                                    "wire_vectors_sha256": sha256(HERE.parent / "agent" / "wire-vectors.json"),
                                    "payload_max": 256, "argv_max": 16, "commands_max": 16,
                                    "combined_output_max": 1048576, "wire_queue_bytes": 16384,
                                    "kill_abi": {"syscall": 37, "pid": -1, "posix": 0,
                                                 "no_remaining_processes": "kill(-1,0,0) == -ESRCH"},
                                    "termios_abi": {"bytes": 72, "ioctl": 54, "get": 0x40487413, "set": 0x80487414},
                                    "scope": "exclusive init+agent+one-job VM; no host broadcast signals"}
    elif args.mode == "zsh":
        report["scope"] = "source-built Apple zsh RAM root; structural build checks only, no guest execution claim"
        report["readiness_marker"] = None
        report["interactive_shell"] = {"path": "/bin/zsh", "arguments": ["-i"] if args.storage else ["-f", "-i"],
                                       "terminal": "vt100" if args.pty else "dumb", "prompt": "darwin-zsh%# ",
                                       "bootstrap_recovery_shell": "/bin/sh"}
    if apple_zsh:
        report["apple_zsh"] = {"path": "/bin/zsh", "executable": zsh_report,
                               "source_pin": "apple-zsh-source.json", "installed_host_runtime": False}
    if args.mode == "agent-zsh":
        report["scope"] = "managed guest agent with source-built Apple zsh; structural build checks only, no guest execution claim"
        report["agent_contract"]["fixture_programs_installed"] = False
    with (out / "manifest.json").open("x") as output:
        json.dump(report, output, indent=2, sort_keys=True)
        output.write("\n")
    print(json.dumps({"output_dir": str(out), "ramdisk_sha256": report["sha256"], "ramdisk_size": report["size"],
                      "executable_sha256": executable_report["sha256"], "scope": report["scope"]}, sort_keys=True))


if __name__ == "__main__":
    main()
