#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build pinned Apple-published CLI tools with the source-built static C runtime."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import tarfile

from prepare_pid1 import inspect

HERE = Path(__file__).resolve().parent
PINS = {
    "file_cmds-82": "da9f74ebc406f385e4c325e103a8f21f4cc8d22b",
    "text_cmds-47": "81805ecdebe0ce0e7f3ea054d615444dd2b0d25b",
    "shell_cmds-81": "edbf7e70982a319bf8564c0450707e4bdf3a7f1f",
}
COMMANDS = {
    **{name: ("text_cmds-47", [f"{name}/{name}.c"]) for name in
       ("cat", "head", "wc", "uniq", "comm", "fold", "rev")},
    **{name: ("shell_cmds-81", [f"{name}/{name}.c"]) for name in
       ("basename", "dirname", "echo", "pwd", "printenv", "uname", "sleep", "tee")},
    **{name: ("file_cmds-82", [f"{name}/{name}.c"]) for name in
       ("mkdir", "rmdir", "ln", "touch", "chmod")},
    "rm": ("file_cmds-82", ["rm/rm.c", "ls/stat_flags.c"]),
    "cp": ("file_cmds-82", ["cp/cp.c", "cp/utils.c"]),
    "ls": ("file_cmds-82", ["ls/ls.c", "ls/cmp.c", "ls/print.c", "ls/util.c", "ls/stat_flags.c"]),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command):
    return subprocess.check_output(list(map(str, command)), text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, default=HERE / "build/zsh-terminal-static-1/manifest.json")
    parser.add_argument("--resume", action="store_true", help="retry an incomplete utility build only")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if args.resume:
        previous = json.loads((out / "manifest.json").read_text())
        if previous.get("format") != "apple-source-utilities-1" or previous.get("complete"):
            raise RuntimeError("refusing to overwrite completed or unrelated build")
    out.mkdir(parents=True, exist_ok=args.resume)
    upstream = HERE / "upstream"
    for tag, commit in PINS.items():
        checkout = upstream / ("apple-" + tag)
        if run(["git", "-C", checkout, "rev-parse", "HEAD"]) != commit or run([
                "git", "-C", checkout, "status", "--porcelain", "--untracked-files=no"]):
            raise RuntimeError(f"unpinned or modified Apple checkout: {checkout}")
    libm = upstream / "apple-Libm"
    if run(["git", "-C", libm, "rev-parse", "HEAD"]) != "17a5f9daa3f5679f7536b26f133b40cc078753c3" or run([
            "git", "-C", libm, "status", "--porcelain", "--untracked-files=no"]):
        raise RuntimeError("unpinned Apple Libm")
    baseline = json.loads(args.runtime_manifest.read_text())
    archives = [Path(p) for p in baseline["archives"] if Path(p).name in
                ("libapple-runtime.a", "libapple-posix.a", "libapple-libc-leaf.a", "libapple-math.a")]
    if len(archives) != 4 or any(sha(p) != baseline["archives"][str(p)] for p in archives):
        raise RuntimeError("source-built Apple runtime archive drift")
    abi = out / "abi"
    run(["python3", HERE / "build_darwin_abi.py", "--utilities", "--output-dir", abi])
    sdk = run(["xcrun", "--sdk", "macosx", "--show-sdk-path"])
    old = upstream / "Libc-Libc-167"
    libc391 = upstream / "Libc-Libc-391"
    support = [old / p for p in ("gen.subproj/err.c", "stdlib.subproj/getopt.c",
               "gen.subproj/setmode.c", "gen.subproj/fts.c", "string.subproj/strmode.c",
               "locale.subproj/setlocale.c", "stdio.subproj/fgetln.c", "stdlib.subproj/atof.c",
               "string.subproj/rindex.c", "gen.subproj/getbsize.c",
               "stdio.subproj/sscanf.c", "stdio.subproj/vfscanf.c")]
    support += [libc391 / p for p in ("gen/FreeBSD/basename.c", "gen/FreeBSD/dirname.c",
                                     "locale/FreeBSD/mbtowc.c", "gen/strtofflags.c",
                                     "stdtime/FreeBSD/localtime.c", "stdtime/FreeBSD/asctime.c")]
    support += [libm / "Source/ARM/ilogb.c"]
    support += [HERE / "runtime/utility_start.c"]
    support_headers = sorted({header for source in support for header in source.parent.glob("*.h")})
    support_headers += [HERE / "runtime/utility_build.h", HERE / "runtime/apple_libc/compat.h"]
    # Verify old archive-extracted Libc sources against pinned Apple downloads.
    lock = json.loads((HERE / "apple-runtime.sources.lock.json").read_text())
    verified = {}
    for pin in lock["sources"]:
        checkout = HERE / pin["localPath"]
        selected = [p for p in [*support, *support_headers] if p.is_relative_to(checkout)]
        if not selected:
            continue
        archive = upstream / (pin["tag"] + ".tar.gz")
        if sha(archive) != pin["archiveSHA256"]:
            raise RuntimeError("Libc archive pin drift")
        with tarfile.open(archive) as package:
            members = {m.name.partition("/")[2]: m for m in package.getmembers() if m.isfile()}
            for p in selected:
                if package.extractfile(members[str(p.relative_to(checkout))]).read() != p.read_bytes():
                    raise RuntimeError(f"original Libc source drift: {p}")
        verified[pin["tag"]] = pin
    inc = out / "include"
    inc.mkdir(exist_ok=args.resume)
    (inc / "rune.h").write_text('#include <stdio.h>\n#include <sys/param.h>\n#undef _LC_LAST\n#define _LC_LAST 6\n#define _PATH_LOCALE "/usr/share/locale"\nextern int setrunelocale(const char *);\n')
    (inc / "_stdio.h").write_text((Path(sdk) / "usr/include/_stdio.h").read_text().replace(
        "struct __sFILEX *_extra;", "unsigned char *_up;"))
    for name in ("namespace.h", "un-namespace.h"):
        (inc / name).write_text("/* Static utility profile uses public SDK ABI names. */\n")
    (inc / "libc_private.h").write_text("/* Selected commands are single-thread processes. */\n#define __isthreaded 0\n")
    flags = ["-target", "arm64-apple-macosx26.0", "-isysroot", sdk, "-std=gnu89", "-Os",
             "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-D_FORTIFY_SOURCE=0",
             "-Werror=implicit-function-declaration", "-Werror=int-conversion",
             "-Wno-deprecated-declarations", "-Wno-deprecated-non-prototype",
             "-Wno-incompatible-pointer-types", "-include", str(HERE / "runtime/utility_build.h"),
             "-I", str(inc)]
    report = {"format": "apple-source-utilities-1", "pins": PINS,
              "repositories": {tag: f"https://github.com/apple-oss-distributions/{tag.rsplit('-', 1)[0]}" for tag in PINS},
              "runtime_archives": {str(p): sha(p) for p in archives}, "verified_libc_archives": verified,
              "builder_sha256": sha(Path(__file__)), "sources": {}, "commands": {},
              "libm": {"repository": "https://github.com/apple-oss-distributions/Libm", "tag": "Libm-2026", "commit": "17a5f9daa3f5679f7536b26f133b40cc078753c3"},
              "private_header_sha256": {str(p): sha(p) for p in support_headers},
              "abi_manifest_sha256": sha(abi / "manifest.json"),
              "host_runtime_linked": False, "guest_executed": False,
              "limits": ["historical Apple-published releases; not current macOS userland",
                         "static single-thread C/POSIX locale only; no dyld or full LibSystem",
                         "project entry/locale ABI glue; original command algorithms retained",
                         "project numeric UID/GID formatting only; account name databases unavailable"]}

    def save():
        (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")

    def compile_source(original, target, extra=()):
        content = original.read_text()
        adaptations = []
        if original.name == "wc.c":
            # Libc-167 predates printf's j length modifier. Preserve full 64-bit
            # counts using its real ll formatter, not truncated int output.
            content = content.replace("uintmax_t", "unsigned long long").replace("%7ju", "%7llu")
            adaptations.append("64-bit uintmax_t/%ju spelling to unsigned long long/%llu for selected printf ABI")
        if original.parent.name == "mkdir":
            content = content.replace("errno == EEXIST || errno == EISDIR", "errno == EEXIST || errno == EISDIR || errno == EROFS")
            adaptations.append("mkdir -p may traverse an existing read-only RAM-root ancestor only after original stat/S_ISDIR validation; new read-only directories still fail")
        if original.name == "localtime.c":
            content = content.replace("_pthread_", "pthread_")
            for symbol in ("open", "close", "read", "fstat"):
                content = re.sub(r"\b_" + symbol + r"\b", symbol, content)
            adaptations.append("public pthread declaration spellings; original nonthreaded branch selected at compile time; no pthread implementation linked")
            extra = [*extra, "-fwrapv"]
        if original.parent.name == "sleep":
            extra = [*extra, "-Dfloor=__builtin_floor"]
            adaptations.append("floor lowered to ARM64 hardware frintm by compiler builtin; no host Libm import")
        if original.parent.name == "ls":
            extra = [*extra, "-Dfabs=__builtin_fabs"]
            adaptations.append("fabs lowered to ARM64 hardware builtin; no host Libm import")
        if original.name == "fts.c":
            for field in ("fd", "loc", "size", "buf", "len", "seek", "flags"):
                content = content.replace("->dd_" + field, "->__dd_" + field)
            adaptations.append("SDK DIR private field spellings")
        if original.name == "setmode.c":
            content = re.sub(r"static int(\s+)compress_mode", r"static void\1compress_mode", content)
            adaptations.append("compress_mode is side-effect-only; correct its old implicit unused return type")
        generated = target.with_suffix(".c")
        generated.write_text(content)
        command = ["xcrun", "clang", *flags, "-I", str(original.parent), *extra,
                   "-c", str(generated), "-o", str(target)]
        result = subprocess.run(command, capture_output=True, text=True)
        target.with_suffix(".log").write_text(result.stdout + result.stderr)
        report["sources"][str(original)] = {"sha256": sha(original), "generated_sha256": sha(generated),
                                               "adaptations": adaptations, "command": command, "exit": result.returncode}
        save()
        if result.returncode:
            raise RuntimeError(f"{original}:\n{result.stderr}")
        return target

    support_objects = []
    for i, source in enumerate(support):
        extra = []
        if source.name in ("fgetln.c", "sscanf.c", "vfscanf.c"):
            extra = ["-include", str(HERE / "runtime/apple_libc/compat.h")]
        support_objects.append(compile_source(source, out / f"support-{i}.o", extra))
    library = out / "libutility-support.a"
    run(["xcrun", "ar", "rcs", library, *support_objects])
    for name, (tag, relative_sources) in COMMANDS.items():
        directory = out / name
        directory.mkdir(exist_ok=args.resume)
        objects = [compile_source(upstream / ("apple-" + tag) / rel, directory / f"{i}.o",
                                  ["-Dmain=darwin_utility_main"]) for i, rel in enumerate(relative_sources)]
        binary = directory / name
        command = ["xcrun", "ld", "-arch", "arm64", "-platform_version", "macos", "26.0", "27.0",
                   "-static", "-e", "_start", "-dead_strip", "-no_adhoc_codesign", "-no_uuid",
                   "-alias", "_fopen", "_fopen$DARWIN_EXTSN", "-map", str(directory / "link.map"),
                   "-alias", "_strrchr", "_rindex",
                   "-o", str(binary), str(abi / "libdarwin-static-abi.a"), *map(str, objects),
                   str(library), *map(str, archives)]
        result = subprocess.run(command, text=True, capture_output=True)
        (directory / "link.log").write_text(result.stdout + result.stderr)
        record = {"link_command": command, "exit": result.returncode, "tag": tag}
        report["commands"][name] = record
        save()
        if result.returncode:
            raise RuntimeError(f"link {name}:\n{result.stderr}")
        if run(["xcrun", "nm", "-u", binary]):
            raise RuntimeError(f"unresolved imports: {name}")
        record.update({"path": str(binary), "sha256": sha(binary), "executable": inspect(binary.read_bytes())})
        save()
    notices = out / "NOTICES.txt"
    notices.write_text(
        "Apple-source Darwin utility profile. Historical releases, not macOS binaries.\n"
        "This product includes software developed by the University of California, Berkeley and its contributors.\n"
        "This product includes software developed by Winning Strategies, Inc.\n"
        "Full source copyright, license conditions and disclaimers are retained in source-bundle.tar.gz.\n"
        "Apple Libc sources include APSL notices; see the pinned source distribution and its license.\n"
        "Project build/ABI glue is BSD-2-Clause. Numeric UID/GID rendering is project glue, not Libinfo account lookup.\n")
    bundle_sources = {Path(p) for p in report["sources"]} | set(support_headers)
    # Preserve every published header/license in these small command releases,
    # as well as the exact originals, generated adaptations, and build glue.
    for tag in PINS:
        checkout = upstream / ("apple-" + tag)
        bundle_sources.update(p for p in checkout.rglob("*") if p.is_file() and ".git" not in p.parts and
                              (p.suffix == ".h" or "license" in p.name.lower() or "copying" in p.name.lower()))
    bundle_sources.update((Path(__file__), HERE / "build_darwin_abi.py", HERE / "apple-runtime.sources.lock.json"))
    for pin in lock["sources"]:
        checkout = HERE / pin["localPath"]
        bundle_sources.update(p for p in checkout.glob("*") if p.is_file() and "license" in p.name.lower())
    license_cache = HERE / "build/darwin-workload-0.1.0/licenses"
    bundle_sources.update(p for p in license_cache.iterdir() if p.is_file())
    with tarfile.open(out / "source-bundle.tar.gz", "w:gz") as bundle:
        for source in sorted(bundle_sources):
            bundle.add(source, arcname="original/" + str(source.relative_to(HERE)), recursive=False)
        for source in sorted(out.rglob("*")):
            if source.is_file() and source.suffix in (".c", ".h", ".S", ".s"):
                bundle.add(source, arcname="generated/" + str(source.relative_to(out)), recursive=False)
        bundle.add(abi / "manifest.json", arcname="abi-build.json")
    report["distribution_sha256"] = {p.name: sha(p) for p in (notices, out / "source-bundle.tar.gz")}
    report["complete"] = True
    save()
    print(json.dumps({"output": str(out), "commands": list(report["commands"])}))


if __name__ == "__main__":
    main()
