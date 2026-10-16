#!/usr/bin/env python3
"""Build a default-off Apple IONetworkingFamily compatibility slice.

This deliberately produces an uninstalled static archive.  It neither adds the
family to the XNU file list nor creates an IOService catalogue entry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PIN = ROOT / "tools/rpi5/ionetworkingfamily_186_sources.json"
COMPILE_DB = ROOT / "build/rpi5/obj/DEVELOPMENT_ARM64_BCM2712/compile_commands.json"
BUILDABLE = (
    "IOEthernetController.cpp",
    "IOEthernetInterface.cpp",
    "IOKernelDebugger.cpp",
    "IONetworkController.cpp",
    "IONetworkData.cpp",
    "IONetworkMedium.cpp",
    "IONetworkUserClient.cpp",
    "IOOutputQueue.cpp",
    "IOPacketQueue.cpp",
)
BLOCKED = {
    "IOMbufMemoryCursor.cpp": ("templates must have C++ linkage",),
    "IONetworkInterface.cpp": (
        "templates must have C++ linkage",
        "TargetConditionals.h' file not found",
    ),
    "IONetworkStack.cpp": ("templates must have C++ linkage",),
}
HISTORICAL_SOURCE_FLAGS = (
    "-std=gnu++17",
    "-D", "__PRIVATE_SPI__",
    "-D", "BSD_BUILD",
    "-Wno-zero-as-null-pointer-constant",
    "-Wno-documentation",
    "-Wno-documentation-html",
    "-Wno-old-style-cast",
    "-Wno-reserved-identifier",
    "-Wno-extra-semi-stmt",
    "-Wno-c++98-compat",
    "-Wno-c++98-compat-pedantic",
    "-Wno-missing-prototypes",
    "-Wno-unused-function",
    "-Wno-unused-variable",
    "-Wno-unused-parameter",
    "-Wno-cast-qual",
    "-Wno-sign-conversion",
    "-Wno-shorten-64-to-32",
    "-Wno-cast-function-type-mismatch",
    "-Wno-implicit-int-conversion",
    "-Wno-misleading-indentation",
    "-Wno-cast-align",
    "-g0",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(argv: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, text=True, capture_output=True,
                          timeout=120, check=False)


def base_compile() -> tuple[list[str], Path, str]:
    entries = json.loads(COMPILE_DB.read_text())
    entry = next(item for item in entries if item["file"].endswith("IOService.cpp"))
    return entry["arguments"], Path(entry["directory"]), entry["file"]


def command_for(base: list[str], old_source: str, source: Path,
                output: Path | None, include: Path) -> list[str]:
    command: list[str] = []
    skip = False
    for arg in base:
        if skip:
            skip = False
            continue
        if arg == "-o":
            skip = True
            continue
        if arg == old_source:
            command.append(str(source))
        elif arg != "-c":
            command.append(arg)
    if output is None:
        command.append("-fsyntax-only")
    else:
        command.extend(("-c", "-o", str(output)))
    command.extend(("-I", str(include), "-I", str(source.parent),
                    "-I", str(ROOT / "bsd")))
    command.extend(HISTORICAL_SOURCE_FLAGS)
    return command


def normalized_diagnostics(text: str, source_root: Path, output: Path) -> list[str]:
    text = text.replace(str(ROOT), "$ROOT")
    text = text.replace(str(source_root), "$SOURCE")
    text = text.replace(str(output), "$OUTPUT")
    return [line for line in text.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite {output}")

    pins = json.loads(PIN.read_text())
    expected = pins["implementation_sources"]
    if set(expected) != set(BUILDABLE) | set(BLOCKED):
        raise SystemExit("implementation source pin set does not match probe set")
    for name, digest in expected.items():
        candidate = source / name
        if not candidate.is_file() or sha(candidate) != digest:
            raise SystemExit(f"source pin mismatch: {name}")
    for entry in pins["sources"]:
        candidate = source / entry["path"]
        if not candidate.is_file() or sha(candidate) != entry["sha256"]:
            raise SystemExit(f"public source pin mismatch: {entry['path']}")

    source_copy = output / "IONetworkingFamily-186"
    objects = output / "objects"
    include = output / "include/IOKit/network"
    objects.mkdir(parents=True)
    shutil.copytree(source, source_copy)
    include.mkdir(parents=True)
    for header in source_copy.glob("*.h"):
        shutil.copy2(header, include / header.name)

    base, cwd, old_source = base_compile()
    compiled: dict[str, dict[str, object]] = {}
    for name in BUILDABLE:
        object_path = objects / f"{name}.o"
        command = command_for(base, old_source, source_copy / name,
                              object_path, include.parent.parent)
        result = run(command, cwd=cwd)
        if result.returncode:
            raise SystemExit(f"unexpected compile failure for {name}:\n{result.stderr}")
        compiled[name] = {
            "source_sha256": sha(source_copy / name),
            "object_sha256": sha(object_path),
            "diagnostics": normalized_diagnostics(
                result.stderr + result.stdout, source_copy, output),
        }

    blocked: dict[str, dict[str, object]] = {}
    for name, markers in BLOCKED.items():
        command = command_for(base, old_source, source_copy / name, None,
                              include.parent.parent)
        result = run(command, cwd=cwd)
        diagnostics = normalized_diagnostics(
            result.stderr + result.stdout, source_copy, output)
        joined = "\n".join(diagnostics)
        if result.returncode == 0 or not all(marker in joined for marker in markers):
            raise SystemExit(f"unexpected blocker frontier for {name}")
        blocked[name] = {
            "source_sha256": sha(source_copy / name),
            "required_diagnostic_markers": list(markers),
            "diagnostics": diagnostics,
        }

    archive = output / "libIONetworkingFamily186-default-off.a"
    libtool = subprocess.check_output(["xcrun", "--find", "libtool"],
                                      text=True).strip()
    env = os.environ.copy()
    env["ZERO_AR_DATE"] = "1"
    archive_result = subprocess.run(
        [libtool, "-static", "-o", str(archive),
         *[str(objects / f"{name}.o") for name in BUILDABLE]],
        cwd=cwd, text=True, capture_output=True, timeout=120, env=env,
        check=False)
    if archive_result.returncode:
        raise SystemExit(archive_result.stderr)

    nm = subprocess.check_output(
        ["xcrun", "llvm-nm", "--defined-only", str(archive)], text=True)
    required_symbols = (
        "__ZN20IOEthernetController10initializeEv",
        "__ZN19IONetworkController4initEP12OSDictionary",
        "__ZN13IONetworkData9metaClassE",
        "__ZN15IONetworkMedium9metaClassE",
    )
    if not all(symbol in nm for symbol in required_symbols):
        raise SystemExit("archive lacks required Apple class symbols")

    report = {
        "schema_version": 1,
        "profile": "apple-ionetworkingfamily-186-default-off-link-slice-v1",
        "release": pins["release"],
        "catalog_xnu_tag": pins["catalog_xnu_tag"],
        "workspace_xnu_tag": pins["workspace_xnu_tag"],
        "workspace_xnu_commit": pins["workspace_xnu_commit"],
        "compile_database_sha256": sha(COMPILE_DB),
        "manifest_sha256": sha(PIN),
        "compiled_original_units": compiled,
        "blocked_original_units": blocked,
        "archive": {
            "path": archive.name,
            "sha256": sha(archive),
            "required_defined_symbols": list(required_symbols),
        },
        "claims": {
            "original_apple_source_modified": False,
            "default_off": True,
            "production_file_list_modified": False,
            "service_catalogue_modified": False,
            "whole_family_compiled": False,
            "kernel_link_complete": False,
            "interface_registered": False,
            "networking": False,
            "ssh": False,
            "hardware_access": False,
        },
        "next_blocker": (
            "Resolve the three exact source/header compatibility failures, "
            "then link all twelve original units into a distinct default-off kernel successor."
        ),
    }
    (output / "report.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps({
        "status": "default_off_partial_archive_built",
        "compiled_units": len(compiled),
        "blocked_units": len(blocked),
        "archive_sha256": report["archive"]["sha256"],
        "report_sha256": sha(output / "report.json"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
