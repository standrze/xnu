#!/usr/bin/env python3
"""Build the pinned Apple-source, single-thread static libc slice (no host link)."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
OLD = HERE / "upstream/Libc-Libc-167"
ALLOC = HERE / "upstream/Libc-Libc-391"
MODERN = HERE / "upstream/apple-Libc-1752.120.2"
PLATFORM = HERE / "upstream/apple-libplatform-375.120.2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=HERE / "build/apple-runtime")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    generated = output / "generated"
    generated.mkdir(exist_ok=True)
    sdk = Path(subprocess.check_output(["xcrun", "--sdk", "macosx", "--show-sdk-path"], text=True).strip())
    # Libc-167 predates the _up -> _extra FILE extension. Both are pointer-sized
    # at the same ABI offset. All selected old stdio code uses this old layout;
    # public leading FILE fields remain compatible with zsh's SDK headers.
    stdio = (sdk / "usr/include/_stdio.h").read_text()
    stdio = stdio.replace("struct __sFILEX *_extra;", "unsigned char *_up;")
    (generated / "_stdio.h").write_text(stdio)
    for header in ("ctype.h", "_ctype.h"):
        text = (MODERN / "include" / header).read_text()
        text = text.replace('#include "xlocale_private.h"', '').replace('#include "mblocal.h"', '')
        text = text.replace("__current_lc_ctype->_CurrentRuneLocale", "_CurrentRuneLocale")
        (generated / header).write_text(text)
    records = []
    jobs = []
    stdio_names = "clrerr fclose fdopen feof ferror fflush fgetc fgets fileno findfp flags fopen fprintf fpurge fputc fputs fread freopen fseek ftell funopen fvwrite fwalk fwrite getc getchar makebuf printf putc putchar puts refill rget setbuf setbuffer setvbuf snprintf sprintf stdio ungetc vfprintf vprintf vsnprintf vsprintf wbuf wsetup".split()
    stdlib_names = "atoi atol bsearch getenv putenv qsort rand setenv strtod strtol strtoul atexit exit merge".split()
    string_names = "memchr memcmp memset strcasecmp strchr strcoll strcspn strdup strerror strpbrk strsep strspn strstr".split()
    for folder, names in (("stdio.subproj", stdio_names), ("stdlib.subproj", stdlib_names), ("string.subproj", string_names)):
        for name in names:
            jobs.append((OLD / folder / (name + ".c"), folder + "-" + name, []))
    for name in ("strlen", "strnlen", "strcmp", "strncmp", "strcpy", "strncpy", "memmove", "strlcpy", "strlcat"):
        jobs.append((PLATFORM / "src/string/generic" / (name + ".c"), "platform-" + name, []))
    for name in ("table", "runetype", "tolower", "toupper", "none", "nomacros"):
        jobs.append((ALLOC / "locale/FreeBSD" / (name + ".c"), "locale-" + name, []))
    for name in ("lconv", "localeconv"):
        jobs.append((OLD / "locale.subproj" / (name + ".c"), "locale-" + name, []))
    for name in ("closedir", "opendir", "readdir", "telldir", "seekdir", "ctime", "difftime", "errlst", "time"):
        jobs.append((OLD / "gen.subproj" / (name + ".c"), "gen-" + name, []))
    jobs.append((ALLOC / "gen/scalable_malloc.c", "scalable_malloc", []))
    for rel in ("string/strcat.c", "string/strncat.c", "gen/FreeBSD/fmtcheck.c", "stdio/FreeBSD/open_memstream.c"):
        jobs.append((MODERN / rel, "modern-" + Path(rel).stem, []))
    for source in sorted((HERE / "runtime/apple_libc").glob("*.c")):
        jobs.append((source, "glue-" + source.stem, []))
    flags = ["-target", "arm64-apple-macosx13.0", "-isysroot", str(sdk), "-std=gnu89", "-Os", "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-fno-common", "-D_FORTIFY_SOURCE=0", "-DIEEE_LITTLE_ENDIAN=1", "-include", str(HERE / "runtime/apple_libc/compat.h"), "-I" + str(generated), "-I" + str(HERE / "runtime/apple_libc/include"), "-I" + str(OLD / "headers.subproj"), "-I" + str(OLD / "stdio.subproj"), "-I" + str(PLATFORM / "include"), "-Wno-deprecated-non-prototype", "-Wno-incompatible-pointer-types", "-Werror=implicit-function-declaration", "-Werror=int-conversion", "-Wno-deprecated-declarations", "-Wno-unknown-pragmas", "-Wno-macro-redefined", "-Wno-nullability-completeness"]
    failed = []
    for original, name, extra in jobs:
        source = original
        text = source.read_text()
        # The old source's allocation and FILE operations remain intact. These
        # are build/ABI spellings, recorded as generated-source hashes below.
        if source.name == "vfprintf.c":
            # Apple arm64 va_list is a stack cursor, not an lvalue va_arg.
            text = re.sub(r"\(void \*\) &va_arg \(ap, ([^)]+)\)", r"({ void *slot = (void *)ap; (void)va_arg(ap, \1); slot; })", text)
        if source.name == "scalable_malloc.c":
            text = text.replace("#define vm_page_size\t4096", "#define vm_page_size\t16384")
            text = text.replace("#define vm_page_shift\t12", "#define vm_page_shift\t14")
        if "_platform_" in text:
            for symbol in ("strlen", "strnlen", "strcmp", "strncmp", "strcpy", "strncpy", "memmove", "strlcpy", "strlcat"):
                text = text.replace("_platform_" + symbol, symbol)
        if source.name == "fgets.c":
            text = text.replace("register size_t n;", "register int n;")
        if source.name == "setenv.c":
            text = text.replace("void\nunsetenv(name)", "int\nunsetenv(name)")
            text = text.rstrip()[:-1] + "\n\treturn 0;\n}\n"
        if source.name == "nomacros.c":
            text = "#define __LIBC__ 1\n" + text
        if source.name == "fmtcheck.c":
            text = text.replace("__weak_reference(__fmtcheck, fmtcheck);", "").replace("__fmtcheck", "fmtcheck")
        if source.name == "open_memstream.c":
            text = text.replace("fwide(fp, -1);", "/* Selected Libc-167 streams are byte-oriented only. */")
        if source.name in ("opendir.c", "readdir.c"):
            text = text.replace("getdirentries(", "apple_getdirentries64(")
        if source.name == "opendir.c":
            # SDK DIR's offsets are size_t; retain signed syscall error check.
            text = text.replace("(DIR *)malloc(sizeof(DIR))", "(DIR *)calloc(1, sizeof(DIR))")
        if source.name == "readdir.c":
            text = text.replace("dirp->__dd_size = apple_getdirentries64", "long read_size = apple_getdirentries64")
            text = text.replace("if (dirp->__dd_size <= 0)", "dirp->__dd_size = read_size > 0 ? read_size : 0;\n\t\t\tif (read_size <= 0)")
        text = text.replace("_platform_memset", "memset")
        for field in ("fd", "loc", "size", "buf", "len", "seek", "flags"):
            text = text.replace("->dd_" + field, "->__dd_" + field)
        text = text.replace("->dd_rewind", "->__padding")
        target_source = generated / (name + ".c")
        target_source.write_text(text)
        command = ["xcrun", "clang", *flags, "-I" + str(original.parent), *extra, "-c", str(target_source), "-o", str(output / (name + ".o"))]
        result = subprocess.run(command, capture_output=True, text=True)
        (output / (name + ".log")).write_text(result.stdout + result.stderr)
        record = {"source": str(original.relative_to(HERE)), "sourceSHA256": sha(original), "generatedSHA256": sha(target_source), "command": command, "exit": result.returncode}
        if result.returncode:
            failed.append(name)
            print(name + ": " + result.stderr[:1800])
        else:
            record["objectSHA256"] = sha(output / (name + ".o"))
        records.append(record)
    report = {"target": "arm64-apple-macosx13.0", "sdkHeadersOnly": str(sdk), "hostRuntimeLinked": False, "sources": records, "failed": failed,
              "generatorSHA256": sha(Path(__file__)),
              "projectHeaderSHA256": {str(path.relative_to(HERE)): sha(path) for path in sorted((HERE / "runtime/apple_libc").rglob("*.h"))},
              "generatedHeaderSHA256": {path.name: sha(path) for path in sorted(generated.glob("*.h"))}}
    if not failed:
        objects = [str(output / (name + ".o")) for _, name, _ in jobs]
        archive = output / "libapple-runtime.a"
        if archive.exists():
            archive.unlink()  # Generated archive only; avoid obsolete members.
        subprocess.run(["xcrun", "ar", "-rcs", str(archive), *objects], check=True)
        report["archiveSHA256"] = sha(archive)
        nm = subprocess.check_output(["xcrun", "nm", "-g", str(archive)], text=True)
        (output / "symbols.txt").write_text(nm)
        undefined, defined = set(), set()
        for line in nm.splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[-2] in ("U", "T", "D", "S", "B", "C"):
                (undefined if fields[-2] == "U" else defined).add(fields[-1])
        report["undefined"] = sorted(undefined - defined)
        (output / "undefined.txt").write_text("\n".join(report["undefined"]) + "\n")
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"objects": len(jobs) - len(failed), "failed": failed, "undefined": report.get("undefined")}))
    return bool(failed)


if __name__ == "__main__":
    raise SystemExit(main())
