#!/usr/bin/env python3
"""Compile the small, pinned Apple Libc POSIX source closure; no host linkage."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
OLD = HERE / "upstream/Libc-Libc-167"
NEWER = HERE / "upstream/Libc-Libc-391"
MODERN = HERE / "upstream/apple-Libc-1752.120.2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=HERE / "build/apple-posix")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    generated = output / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    sdk = subprocess.check_output(["xcrun", "--sdk", "macosx", "--show-sdk-path"], text=True).strip()
    jobs = [(OLD / "gen.subproj" / (name + ".c"), name) for name in
            "alarm getcwd gethostname isatty nice signal sleep sysconf termios times ttyname uname wait3".split()]
    jobs += [(OLD / "stdio.subproj/mktemp.c", "mktemp"),
             (OLD / "compat43.subproj/killpg.c", "killpg"),
             (OLD / "string.subproj/strftime.c", "strftime"),
             (NEWER / "gen/FreeBSD/getpagesize.c", "getpagesize")]
    flags = ["-target", "arm64-apple-macosx13.0", "-isysroot", sdk, "-std=gnu89", "-Os", "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-fno-common", "-D_FORTIFY_SOURCE=0", "-include", str(HERE / "runtime/apple_posix/compat.h"), "-I" + str(HERE / "runtime/apple_libc/include"), "-I" + str(OLD / "headers.subproj"), "-Wno-deprecated-non-prototype", "-Wno-deprecated-declarations", "-Wno-incompatible-pointer-types", "-Werror=implicit-function-declaration", "-Werror=int-conversion", "-Wno-macro-redefined"]
    records, failed = [], []
    for original, name in jobs:
        content = original.read_text()
        changes = []
        if name == "gethostname":
            content = content.replace("long\ngethostname(name, namelen)\n\tchar *name;\n\tint namelen;", "int\ngethostname(char *name, size_t namelen)")
            changes.append("modern gethostname return and size_t argument ABI spelling")
        if name == "signal":
            content = content.replace("_sigaction_nobind(", "sigaction(")
            changes.append("static target calls real sigaction without historical lazy-binding bypass")
        if name == "sysconf":
            content = content.replace("\tstruct clockinfo clk;", "")
            changes.append("remove unused private struct clockinfo local")
            anchor = "\tcase _SC_CLK_TCK:\n\t\treturn (CLK_TCK);"
            if content.count(anchor) != 1:
                raise RuntimeError("pinned sysconf page-size insertion anchor drifted")
            content = content.replace(anchor, anchor + "\n\t/* Reviewed modern Apple sysconf getpagesize fallback. */\n\tcase _SC_PAGESIZE:\n\t\treturn (getpagesize());")
            changes.append("backport _SC_PAGESIZE getpagesize fallback from Libc-1752.120.2 gen/FreeBSD/sysconf.c; real kernel HW_PAGESIZE queried by Libc-391 getpagesize.c")
        if name == "termios":
            content = content.replace("#include <sys/tty.h>", "")
            content = content.replace("#define KERNEL\t\t\t/* XXX - FREAD and FWRITE ifdef'd KERNEL*/", "")
            changes.append("use modern public ioctl/termios headers and explicit FREAD/FWRITE constants")
        if name == "ttyname":
            content = content.replace("#include <db.h>", "")
            content = content.replace("\tDB *db;\n\tDBT data, key;\n\tstruct {\n\t\tmode_t type;\n\t\tdev_t dev;\n\t} bkey;\n", "")
            start = content.index("\tdb = dbopen(")
            end = content.index("\treturn (oldttyname(fd, &sb));", start)
            content = content[:start] + content[end:]
            changes.append("omit optional dev.db optimization, retain actual oldttyname directory fallback")
        source = generated / (name + ".c")
        source.write_text(content)
        obj = output / (name + ".o")
        command = ["xcrun", "clang", *flags, "-I" + str(original.parent), "-c", str(source), "-o", str(obj)]
        result = subprocess.run(command, capture_output=True, text=True)
        (output / (name + ".log")).write_text(result.stdout + result.stderr)
        record = {"source": str(original.relative_to(HERE)), "sourceSHA256": sha(original), "generatedSHA256": sha(source), "adaptations": changes, "command": command, "exit": result.returncode}
        if name == "sysconf":
            reference = MODERN / "gen/FreeBSD/sysconf.c"
            record["pageSizeBackportReference"] = {"source": str(reference.relative_to(HERE)), "sourceSHA256": sha(reference)}
        if result.returncode:
            failed.append(name)
            print(name + ": " + result.stderr[:2500])
        else:
            record["objectSHA256"] = sha(obj)
        records.append(record)
    report = {"hostRuntimeLinked": False, "sources": records, "failed": failed}
    if not failed:
        archive = output / "libapple-posix.a"
        subprocess.run(["xcrun", "ar", "-rcs", str(archive), *[str(output / (name + ".o")) for _, name in jobs]], check=True)
        report["archiveSHA256"] = sha(archive)
        nm = subprocess.check_output(["xcrun", "nm", "-g", str(archive)], text=True)
        (output / "symbols.txt").write_text(nm)
        defined, undefined = set(), set()
        for line in nm.splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[-2] in ("U", "T", "D", "S", "B", "C"):
                (undefined if fields[-2] == "U" else defined).add(fields[-1])
        report["undefined"] = sorted(undefined - defined)
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "sources"}))
    return bool(failed)


if __name__ == "__main__":
    raise SystemExit(main())
