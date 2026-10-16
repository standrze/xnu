#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build one freestanding static multicall shell/init/utilities and RAM root."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_pid1 import inspect as inspect_macho
from ramroot import build, inspect

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).with_name("user")
PROGRAMS = ("sh", "echo", "cat", "ls", "wc", "sleep", "uname", "true", "false", "hexdump")

def run(*command):
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command!r}\n{result.stdout}{result.stderr}")
    return (result.stdout or result.stderr).strip()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--sd-read-trial", action="store_true",
                        help="Add the separate read-only /dev/rdiskN sector trial utility")
    parser.add_argument("--hfs-read-trial", action="store_true",
                        help="With --sd-read-trial, add the separately gated HFS read-only mount utility")
    parser.add_argument("--hfs-write-trial", action="store_true",
                        help="Distinct writable-HFS mount/fixed-file utilities; mutually exclusive with read trials")
    args = parser.parse_args()
    if args.hfs_write_trial and (args.sd_read_trial or args.hfs_read_trial):
        parser.error("--hfs-write-trial cannot be combined with read-only trial flags")
    if args.hfs_read_trial and not args.sd_read_trial:
        parser.error("--hfs-read-trial requires --sd-read-trial")
    hfs_header = None
    if args.hfs_read_trial or args.hfs_write_trial:
        from audit_storage_build import LOCK, source_input
        lock = json.loads(LOCK.read_text())
        hfs, _ = source_input(ROOT / 'build/rpi5/gate4-reference', ROOT / 'build/rpi5/gate4-sources',
                              'hfs', lock['dependencies']['hfs'])
        hfs_header = hfs / 'core/hfs_mount.h'
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    compiler, linker = run("xcrun", "--find", "clang"), run("xcrun", "--find", "ld")
    sdk = Path(run("xcrun", "--sdk", "macosx", "--show-sdk-path"))
    commands, objects = [], []
    sources = [SOURCE / name for name in ("start.S", "runtime.c", "parser.c", "shell.c", "utilities.c", "init.c")]
    if args.sd_read_trial:
        sources.append(SOURCE / "sdread.c")
    if args.hfs_read_trial:
        sources.append(SOURCE / "hfsro.c")
    if args.hfs_write_trial:
        sources += [SOURCE / 'hfsrw.c', SOURCE / 'hfswrite.c']
    for source in sources:
        obj = out / (source.stem + ".o")
        command = [compiler, "-isysroot", str(sdk), "-target", "arm64-apple-darwin", "-c", "-Os", "-ffreestanding",
                   "-fno-builtin", "-fno-stack-protector", "-Wall", "-Wextra", "-Werror",
                   "-DRPI5_SD_READ_TRIAL=" + str(int(args.sd_read_trial)),
                   "-DRPI5_HFS_READ_TRIAL=" + str(int(args.hfs_read_trial)),
                   "-DRPI5_HFS_WRITE_TRIAL=" + str(int(args.hfs_write_trial)),
                   str(source), "-o", str(obj)]
        if hfs_header:
            command[1:1] = ['-I', str(hfs_header.parent)]
        run(*command); commands.append(command); objects.append(str(obj))
    exe = out / "userland"
    command = [linker, "-arch", "arm64", "-static", "-e", "_start", "-no_adhoc_codesign",
               "-o", str(exe), *objects]
    run(*command); commands.append(command)
    raw = exe.read_bytes()
    executable_report = inspect_macho(raw)
    files = {"/sbin/launchd": (raw, 0o555)}
    files.update({"/bin/" + name: (raw, 0o555) for name in PROGRAMS})
    if args.sd_read_trial:
        files["/bin/sdread"] = (raw, 0o555)
    if args.hfs_read_trial:
        files["/bin/hfsro"] = (raw, 0o555)
    if args.hfs_write_trial:
        files["/bin/hfsrw"] = (raw, 0o555)
        files["/bin/hfswrite"] = (raw, 0o555)
    if args.hfs_read_trial or args.hfs_write_trial:
        files["/mnt/hfs/.anchor"] = (b"", 0o444)
    files.update({"/etc/motd": (b"Experimental Darwin XNU on Raspberry Pi 5. Read-only RAM root.\n", 0o444),
                  "/etc/demo.sh": (b"echo SCRIPT_BEGIN\npwd\nls /etc\ncat /etc/motd | wc\nfalse || echo SCRIPT_RECOVERED\necho SCRIPT_END\n", 0o444),
                  "/etc/empty": (b"", 0o444)})
    image, report = build(files)
    assert inspect(image) == report
    (out / "ramdisk.bin").write_bytes(image)
    inputs = sources + [SOURCE / "runtime.h", SOURCE / "parser.h", Path(__file__),
                        Path(__file__).with_name("ramroot.py"), Path(__file__).with_name("prepare_pid1.py")]
    if args.sd_read_trial:
        inputs.append(SOURCE / "sdread.h")
    if args.hfs_read_trial:
        inputs += [SOURCE / 'hfsro.h', hfs_header, LOCK]
    if args.hfs_write_trial:
        inputs += [SOURCE / 'hfsrw.h', SOURCE / 'hfswrite.h', hfs_header, LOCK]
    report["sd_read_trial"] = args.sd_read_trial
    report["hfs_read_trial"] = args.hfs_read_trial
    report["hfs_write_trial"] = args.hfs_write_trial
    report.update({"executable": executable_report, "commands": commands,
                   "sdk": str(sdk),
                   "sdk_header_sha256": {name: hashlib.sha256((sdk / 'usr/include' / name).read_bytes()).hexdigest()
                                         for name in ('sys/mount.h', 'sys/disk.h', 'sys/time.h', 'fcntl.h')}
                                         if args.hfs_read_trial or args.hfs_write_trial else {},
                   "compiler_version": run(compiler, "--version").splitlines()[0],
                   "linker_version": run(linker, "-v").splitlines()[0],
                   "source_head": run("git", "-C", str(ROOT), "rev-parse", "HEAD"),
                   "source_status": run("git", "-C", str(ROOT), "status", "--short"),
                   "source_inputs_sha256": {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
                   "scope": "host-validated static userland; physical shell trial not yet run"})
    (out / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))

if __name__ == "__main__":
    main()
