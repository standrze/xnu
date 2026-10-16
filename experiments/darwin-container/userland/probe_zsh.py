#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One bounded source/object dependency probe; not a guest build or test suite."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import shutil
import hashlib

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "upstream/apple-zsh/zsh"
ROOT = HERE.parents[2]
CORE_FLAGS = "-Os -ffreestanding -fno-builtin -fno-stack-protector -D_FORTIFY_SOURCE=0"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--target-minimum", action="store_true",
                        help="disable optional SDK-only features in generated config.h")
    parser.add_argument("--objects-only", action="store_true",
                        help="compile the complete core without attempting its final runtime link")
    parser.add_argument("--terminal", action="store_true",
                        help="Separate real-PTY profile: job control and static Apple ZLE module")
    args = parser.parse_args()
    pin = json.loads((HERE / "apple-zsh-source.json").read_text())
    checkout = SOURCE.parent
    commit = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain"], text=True).strip()
    if commit != pin["commit"] or dirty:
        raise RuntimeError("requires the clean pinned official Apple zsh source checkout")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    deadline = time.monotonic() + 60
    commands = []
    headers = {}
    for original, staged in (("bsd/sys/codesign.h", "System/sys/codesign.h"),
                             ("osfmk/kern/cs_blobs.h", "kern/cs_blobs.h")):
        source_header = ROOT / original
        target_header = output / "include" / staged
        target_header.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_header, target_header)
        headers[original] = hashlib.sha256(source_header.read_bytes()).hexdigest()

    def run(name, command):
        commands.append(command)
        result = subprocess.run(command, cwd=output, text=True, capture_output=True,
                                timeout=max(1, deadline - time.monotonic()))
        (output / name).write_text(result.stdout + result.stderr)
        return result

    configure = ["/bin/sh", str(SOURCE / "configure"), "CC=clang", f"CFLAGS={CORE_FLAGS}",
                 f"CPPFLAGS=-I{output / 'include'}",
                 "--disable-dynamic", "--disable-locale", "--disable-multibyte", "--disable-dynamic-nss",
                 "--disable-pcre", "--disable-cap", "--disable-gdbm", "--disable-etcdir", "--disable-fndir",
                 "--disable-site-fndir", "--disable-runhelpdir", "--enable-custom-patchlevel=darwin-source-probe"]
    configure.append("--with-tcsetpgrp" if args.terminal else "--without-tcsetpgrp")
    result = run("configure.log", configure)
    report = {"configure_exit": result.returncode, "commands": commands, "xnu_header_sha256": headers,
              "scope": "host SDK configured source/object closure only; no guest-ready libc or executable",
              "terminal_profile": args.terminal, "apple_source_pin": pin}
    if result.returncode == 0:
        if args.target_minimum:
            config = output / "config.h"
            disabled = ("HAVE_ICONV", "HAVE_ICONV_H", "HAVE_NL_LANGINFO", "HAVE_SETUPTERM", "HAVE_OPEN_MEMSTREAM",
                        "HAVE_CLOCK_GETTIME", "REALPATH_ACCEPTS_NULL", "HAVE__MKTEMP")
            content = config.read_text()
            for feature in disabled:
                content = content.replace(f"#define {feature} 1", f"/* #undef {feature} -- minimal source-built guest */")
            config.write_text(content)
            report["disabled_optional_features"] = list(disabled)
        modules = output / "config.modules"
        lines = []
        for line in modules.read_text().splitlines():
            if args.terminal and line.startswith("name=zsh/zle "):
                line = " ".join("link=static" if field.startswith("link=") else
                                "load=yes" if field.startswith("load=") else
                                "auto=yes" if field.startswith("auto=") else field for field in line.split(" "))
            elif line.startswith("name=") and not line.startswith("name=zsh/main "):
                line = " ".join("link=no" if field.startswith("link=") else
                                "load=no" if field.startswith("load=") else
                                "auto=no" if field.startswith("auto=") else field for field in line.split(" "))
            lines.append(line)
        modules.write_text("\n".join(lines) + "\n")
        targets = ["stamp-modobjs", "main.o"] if args.objects_only else ["bin"]
        result = run("core-build.log", ["make", "-C", "Src", "-j4", *targets, "LDFLAGS=-nostdlib -Wl,-static", "LIBS="])
        report["core_build_exit"] = result.returncode
        report["symbol_inventory_partial"] = not (output / "Src/stamp-modobjs").exists()
        objects = sorted((output / "Src").glob("*.o"))
        if args.terminal:
            objects += sorted((output / "Src/Zle").glob("*.o"))
        undefined, defined = set(), set()
        for obj in objects:
            result = subprocess.run(["nm", "-g", str(obj)], text=True, capture_output=True, check=True,
                                    timeout=max(1, deadline - time.monotonic()))
            for line in result.stdout.splitlines():
                fields = line.split()
                if len(fields) >= 2:
                    (undefined if fields[-2] == "U" else defined).add(fields[-1])
        closure = sorted(undefined - defined)
        (output / "undefined-external-symbols.txt").write_text("\n".join(closure) + "\n")
        if not report["symbol_inventory_partial"]:
            subprocess.run(["ar", "rcs", str(output / "libapple-zsh-core.a"), *map(str, objects)], check=True)
        report.update({"objects": len(objects), "undefined_external_symbols": closure})
        report["object_sha256"] = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in objects}
        report["config_sha256"] = hashlib.sha256((output / "config.h").read_bytes()).hexdigest()
        report["modules_sha256"] = hashlib.sha256(modules.read_bytes()).hexdigest()
    (output / "probe.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key not in ("commands", "undefined_external_symbols")}))


if __name__ == "__main__":
    main()
