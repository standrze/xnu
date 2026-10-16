#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build pinned Apple syscall/signal/setjmp code with explicit static ABI glue."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PLATFORM = HERE / "upstream/apple-libplatform-375.120.2"

# Public symbol -> kernel call and nargs. The assembly comes from Apple's
# SYS.h, not a handwritten reimplementation of ordinary syscall stubs.
CALLS = {
    "_exit": ("exit", 1), "read": ("read", 3), "write": ("write", 3),
    "darwin_open": ("open", 3), "close": ("close", 1), "wait4": ("wait4", 4),
    "link": ("link", 2), "unlink": ("unlink", 1), "chdir": ("chdir", 1),
    "fchdir": ("fchdir", 1), "chmod": ("chmod", 2), "chown": ("chown", 3),
    "getpid": ("getpid", 0), "getppid": ("getppid", 0), "getuid": ("getuid", 0),
    "geteuid": ("geteuid", 0), "getgid": ("getgid", 0), "getegid": ("getegid", 0),
    "access": ("access", 2), "__kill": ("kill", 3), "setuid": ("setuid", 1),
    "setgid": ("setgid", 1), "getpgrp": ("getpgrp", 0), "setpgid": ("setpgid", 2),
    "dup": ("dup", 1), "dup2": ("dup2", 2), "umask": ("umask", 1),
    "darwin_ioctl": ("ioctl", 3), "darwin_fcntl": ("fcntl", 3),
    "execve": ("execve", 3), "readlink": ("readlink", 3), "symlink": ("symlink", 2),
    "rename": ("rename", 2), "lseek": ("lseek", 3), "fchmod": ("fchmod", 2),
    "fchown": ("fchown", 3), "select": ("select", 5),
    "getrusage": ("getrusage", 2),
    "getrlimit": ("getrlimit", 2), "setrlimit": ("setrlimit", 2),
    "setreuid": ("setreuid", 2), "setregid": ("setregid", 2),
    "seteuid": ("seteuid", 1), "setegid": ("setegid", 1),
    "sigprocmask": ("sigprocmask", 3), "__sigsuspend_nocancel": ("sigsuspend", 1),
    "__sigaction": ("sigaction", 3), "__sigreturn": ("sigreturn", 3),
    "__sigaltstack": ("sigaltstack", 2), "__mmap": ("mmap", 6), "__munmap": ("munmap", 2),
    "mprotect": ("mprotect", 3), "sysctl": ("sysctl", 6), "getdirentries64": ("getdirentries64", 4),
    "apple_getdirentries64": ("getdirentries64", 4),
    "stat": ("stat64", 2), "fstat": ("fstat64", 2), "lstat": ("lstat64", 2),
    "fstatfs": ("fstatfs64", 2), "issetugid": ("issetugid", 0),
    "getentropy": ("getentropy", 2), "csops": ("csops", 4),
    "setitimer": ("setitimer", 3), "getitimer": ("getitimer", 2),
    "getpriority": ("getpriority", 2), "setpriority": ("setpriority", 3),
    "getdtablesize": ("getdtablesize", 0), "getgroups": ("getgroups", 2),
}

# Opt-in socket ABI for standalone Apple-source network tools. Defaults and
# the qualified zsh archive stay unchanged.
NETWORK_CALLS = {
    "socket": ("socket", 3), "connect": ("connect", 3), "bind": ("bind", 3),
    "setsockopt": ("setsockopt", 5), "getsockopt": ("getsockopt", 5),
    "getpeername": ("getpeername", 3), "sendto": ("sendto", 6),
    "recvfrom": ("recvfrom", 6), "recvmsg": ("recvmsg", 3),
    "writev": ("writev", 3), "pselect": ("pselect", 6),
    "shutdown": ("shutdown", 2),
}

# Opt-in ordinary filesystem operations for the Apple-source utility profile.
UTILITY_CALLS = {
    "mkdir": ("mkdir", 2), "rmdir": ("rmdir", 1), "utimes": ("utimes", 2),
    "fsync": ("fsync", 1), "ftruncate": ("ftruncate", 2),
    "futimes": ("futimes", 2),
    "chflags": ("chflags", 2), "fchflags": ("fchflags", 2),
    "mknod": ("mknod", 3), "mkfifo": ("mkfifo", 2),
    "undelete": ("undelete", 1),
}

def run(command):
    p = subprocess.run([str(x) for x in command], capture_output=True, text=True, timeout=120)
    if p.returncode:
        raise RuntimeError(f"{command}\n{p.stdout}{p.stderr}")
    return p.stdout

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--diagnostics", action="store_true", help="opt-in startup/fault tracing for a failed smoke boot")
    ap.add_argument("--network", action="store_true", help="include Apple SYS.h socket syscall wrappers")
    ap.add_argument("--utilities", action="store_true", help="include Apple SYS.h filesystem utility wrappers")
    args = ap.parse_args()
    out = args.output_dir.resolve(); out.mkdir(parents=True, exist_ok=True)
    sdk = run(["xcrun", "--sdk", "macosx", "--show-sdk-path"]).strip()
    inc = out / "include"; (inc / "os").mkdir(parents=True, exist_ok=True)
    # Apple errno's local include and setjmp's os/tsd.h are the same source.
    (inc / "tsd.h").write_bytes((ROOT / "libsyscall/os/tsd.h").read_bytes())
    (inc / "os/tsd.h").write_bytes((ROOT / "libsyscall/os/tsd.h").read_bytes())
    (inc / "os/internal.h").write_bytes((PLATFORM / "internal/os/internal.h").read_bytes())
    (inc / "stack_logging_internal.h").write_bytes((ROOT / "libsyscall/mach/stack_logging_internal.h").read_bytes())
    cc = ["xcrun", "clang", "-target", "arm64-apple-macosx13.0", "-isysroot", sdk,
          "-I", str(inc), "-I", str(ROOT / "libsyscall/custom"), "-Os", "-ffreestanding",
          "-fno-builtin", "-fno-stack-protector", "-D_FORTIFY_SOURCE=0"]
    if args.diagnostics:
        cc.append("-DDARWIN_ZSH_DIAGNOSTICS=1")
    generated = out / "syscalls.S"
    calls = {**CALLS, **(NETWORK_CALLS if args.network else {}),
             **(UTILITY_CALLS if args.utilities else {})}
    generated.write_text('#include "SYS.h"\n' + ''.join(
        f"__SYSCALL2(_{public}, {kernel}, {nargs}, cerror_nocancel)\n"
        for public, (kernel, nargs) in calls.items()) + '\n.subsections_via_symbols\n')
    inputs = [generated, ROOT / "libsyscall/custom/custom.s", ROOT / "libsyscall/custom/errno.c",
              ROOT / "libsyscall/custom/__gettimeofday.s", ROOT / "libsyscall/wrappers/kill.c",
              ROOT / "libsyscall/wrappers/sigsuspend-base.c",
              ROOT / "libsyscall/wrappers/unix03/mmap.c",
              ROOT / "libsyscall/wrappers/unix03/munmap.c",
              PLATFORM / "src/setjmp/arm64/setjmp.s", PLATFORM / "src/setjmp/generic/sigaction.c",
              PLATFORM / "src/setjmp/generic/sigtramp.c",
              HERE / "upstream/apple-Libc-1752.120.2/sys/sigaction.c", HERE / "runtime/darwin_entry.S",
              HERE / "upstream/apple-Libc-1752.120.2/gen/dirfd.c",
              HERE / "runtime/darwin_static.c", HERE / "runtime/darwin_vm.c",
              HERE / "runtime/darwin_sleep.c"]
    commands = []; objects = []
    for i, source in enumerate(inputs):
        obj = out / f"{i}-{source.stem}.o"
        extras = []
        if source.name == "sigsuspend-base.c":
            extras = ["-D__SIGSUSPEND=__sigsuspend_nocancel"]
        if source.name == "sigtramp.c":
            extras = ["-D__OS_INTERNAL_H__", "-DOS_NOEXPORT=extern __attribute__((visibility(\"hidden\")))"]
        if source.suffix.lower() == ".s":
            command = cc + ["-E", "-P", "-x", "assembler-with-cpp", str(source)]
            asm = out / f"{i}-preprocessed.s"
            asm.write_text(run(command).replace("%%", "\n"))
            commands.append(command)
            command = cc + ["-c", "-x", "assembler", str(asm), "-o", str(obj)]
        else:
            command = cc + extras + ["-c", str(source), "-o", str(obj)]
        run(command); commands.append(command); objects.append(obj)
    archive = out / "libdarwin-static-abi.a"
    archive.unlink(missing_ok=True)
    run(["xcrun", "ar", "rcs", archive, *objects])
    report = {"archive": str(archive), "sha256": digest(archive), "commands": commands,
              "inputs": {str(p): digest(p) for p in inputs}, "syscalls": calls,
              "network": args.network,
              "utilities": args.utilities,
              "scope": "source-build only; no guest execution; static single-thread ABI glue"}
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"archive": str(archive), "sha256": digest(archive)}))

if __name__ == "__main__":
    main()
