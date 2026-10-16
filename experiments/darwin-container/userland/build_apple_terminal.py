#!/usr/bin/env python3
"""Build pinned Apple ncurses terminal support, without host runtime libraries."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "upstream/apple-ncurses"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    commands = []

    def run(command, name):
        commands.append(command)
        with (out / name).open("w") as log:
            subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True)

    configure = ["/bin/sh", str(SOURCE / "ncurses/configure"), "--without-shared",
                 "--without-debug", "--without-ada", "--without-cxx", "--without-cxx-binding",
                 "--without-tests", "--without-manpages", "--without-curses-h", "--without-dlsym",
                 "--disable-widec", "--disable-ext-colors", "--disable-largefile", "--disable-home-terminfo",
                 "--disable-root-environ", "--without-pthread", "--enable-termcap", "--disable-db-install",
                 "--with-termlib", "--with-default-terminfo-dir=/usr/share/terminfo", "CC=clang",
                 "CFLAGS=-Os -ffreestanding -fno-builtin -fno-stack-protector -D_FORTIFY_SOURCE=0"]
    if not (out / "Makefile").exists():
        run(configure, "configure.log")
    run(["make", "-C", "include"], "headers.log")
    # Apple's dylib multi-ABI declaration insertion is irrelevant to a static archive.
    header = out / "include/curses.h"
    header.write_text(header.read_text().replace("@@ABIDECLS@@", ""))
    config = out / "include/ncurses_cfg.h"
    config.write_text(re.sub(r"^#define GCC_PRINTFLIKE\(fmt,var\).*$", "#define GCC_PRINTFLIKE(fmt,var)", config.read_text(), flags=re.M))
    run(["make", "-j4", "libs"], "build.log")
    # These are source-built HOST build tools, never included in the guest image.
    run(["make", "-C", "progs", "-j4", "tic", "infocmp"], "tools-build.log")
    run([str(out / "progs/tic"), "-e", "dumb,vt100", "-o", str(out / "terminfo"),
         str(SOURCE / "ncurses/misc/terminfo.src")], "terminfo-build.log")
    archives = sorted((out / "lib").glob("*.a"))
    if subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True).strip() != "1d2f7b26157890a542d967be0d1236e7a97f8f5b":
        raise RuntimeError("Apple ncurses source pin drift")
    manifest = {"repository": "https://github.com/apple-oss-distributions/ncurses",
                "tag": "ncurses-79", "commit": "1d2f7b26157890a542d967be0d1236e7a97f8f5b",
                "tree": subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD^{tree}"], text=True).strip(),
                "configuration_requested": configure,
                "configuration_log_sha256": hashlib.sha256((out / "config.log").read_bytes()).hexdigest(),
                "implementation_source_modified": bool(subprocess.check_output(["git", "-C", str(SOURCE), "status", "--porcelain"], text=True).strip()),
                "commands": commands, "generated_header_adaptation": "Remove @@ABIDECLS@@ dylib-ABI marker; disable incorrect SCREEN-extended printf annotation",
                "archives": {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in archives},
                "guest_terminfo": {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((out / "terminfo").rglob("*")) if p.is_file()},
                "terminfo_source_sha256": hashlib.sha256((SOURCE / "ncurses/misc/terminfo.src").read_bytes()).hexdigest(),
                "scope": "Source-built arm64 static archives. No tests or guest boot. Host tools are not guest runtime."}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest["archives"]))


if __name__ == "__main__":
    main()
