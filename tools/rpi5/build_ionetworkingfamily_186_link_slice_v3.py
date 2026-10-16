#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compile all unchanged Apple IONetworkingFamily-186 units, default-off."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rpi5 import build_ionetworkingfamily_186_link_slice as prior


ROOT = Path(__file__).resolve().parents[2]
TARGET_CONDITIONALS = (
    ROOT / "build/rpi5/sdk/MacOSX26.5.sdk/usr/include/TargetConditionals.h"
)
OBJECT_ROOT = ROOT / "build/rpi5/obj/DEVELOPMENT_ARM64_BCM2712"
BASE_BUILD_RECEIPT = ROOT / "build/rpi5/run-uki6z6df/manifest.json"
BASE_BUILD_RECEIPT_SHA256 = "25d217c70b5f1fedb00b686bbc55f15979ce1e528fe066962a62b32e7ff0d67e"
CRYPTO_PROVIDER_SHA256 = "84216ddc3b650bba04e330f162e4d1d192bce280a76bcc0f79b7537f9e76c8f0"
ALL_UNITS = tuple(json.loads(prior.PIN.read_text())["implementation_sources"])
COMPAT_PREINCLUDE = """\
#ifndef RPI5_IONETWORKINGFAMILY_186_CXX_COMPAT_H
#define RPI5_IONETWORKINGFAMILY_186_CXX_COMPAT_H
/*
 * IONetworkingFamily-186 wraps these C headers in extern \"C\".  Current XNU
 * headers contain C++ templates, so include the guarded headers once with C++
 * linkage before the unchanged historical source opens its linkage block.
 */
#ifndef _IP_VHL
#define _IP_VHL
#endif
#include <IOKit/assert.h>
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/mbuf.h>
#include <sys/socket.h>
#include <sys/sockio.h>
#include <net/if.h>
#include <net/if_media.h>
#include <net/dlil.h>
#include <net/if_dl.h>
#include <net/kpi_interface.h>
#include <net/ethernet.h>
#include <sys/kern_event.h>
#include <netinet/ip.h>
#include <netinet/ip_icmp.h>
#include <sys/_types/_timeval32.h>
#endif
"""


def command_for(base: list[str], old_source: str, source: Path,
                output: Path, include_root: Path,
                preinclude: Path) -> list[str]:
    command = prior.command_for(base, old_source, source, output, include_root)
    command.extend(("-I", str(preinclude.parent), "-include", str(preinclude),
                    "-Wno-shadow-field", "-Wno-error=shadow-field",
                    "-Wno-gnu-variable-sized-type-not-at-end"))
    return command


def link_kernel(output: Path, objects: list[Path]) -> dict[str, object]:
    """Attempt one distinct, direct-object kernel link; never install it."""
    filelist = output / "kernel.filelist"
    original = (OBJECT_ROOT / "link.filelist").read_text().splitlines()
    filelist.write_text("\n".join(original + list(map(str, objects))) + "\n")
    flags = shlex.split((OBJECT_ROOT / ".LDFLAGS").read_text().rstrip("\0\n"))
    extras = [OBJECT_ROOT / name for name in (
        "lastkerneldataconst.o", "lastkernelconstructor.o", "nonlto.o", "version.o"
    )]
    if prior.sha(BASE_BUILD_RECEIPT) != BASE_BUILD_RECEIPT_SHA256:
        raise SystemExit("exact successful baseline build receipt changed")
    receipt = json.loads(BASE_BUILD_RECEIPT.read_text())
    if (receipt.get("exit_code") != 0 or
            receipt.get("source_unchanged_during_build") is not True or
            receipt.get("fresh_kernel_outputs") is not True):
        raise SystemExit("baseline build receipt is not a fresh successful build")
    providers = [value.split("=", 1)[1] for value in receipt["command"]
                 if value.startswith("RPI5_CRYPTO_CANDIDATE_OBJECT=")]
    if len(providers) != 1:
        raise SystemExit("baseline crypto provider is ambiguous")
    crypto_provider = Path(providers[0])
    if prior.sha(crypto_provider) != CRYPTO_PROVIDER_SHA256:
        raise SystemExit("baseline crypto provider changed")
    extras.append(crypto_provider)
    archive_args = shlex.split((
        OBJECT_ROOT / "kernel.development.bcm2712.link/"
        "kernel.development.bcm2712.linkarchives"
    ).read_text())
    kernel = output / "kernel.ionetworkingfamily186.unstripped"
    command = [*flags, "-filelist", str(filelist), *map(str, extras),
               "-o", str(kernel), *archive_args]
    result = prior.run(command, cwd=ROOT)
    log = output / "kernel-link.log"
    log.write_text(result.stdout + result.stderr)
    row: dict[str, object] = {
        "attempted": True,
        "command": list(map(str, command)),
        "returncode": result.returncode,
        "diagnostics": prior.normalized_diagnostics(
            result.stdout + result.stderr, ROOT, output),
        "production_file_list_modified": False,
        "installed": False,
        "baseline_build_receipt_sha256": BASE_BUILD_RECEIPT_SHA256,
        "baseline_crypto_provider_sha256": CRYPTO_PROVIDER_SHA256,
    }
    if result.returncode == 0:
        unresolved = subprocess.check_output(
            ["xcrun", "nm", "-ju", str(kernel)], text=True).strip()
        if unresolved:
            raise SystemExit("successful kernel link has unresolved symbols")
        row.update({
            "complete": True,
            "path": kernel.name,
            "sha256": prior.sha(kernel),
            "bytes": kernel.stat().st_size,
            "unresolved_symbols": 0,
        })
    else:
        row["complete"] = False
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite {output}")
    pins = json.loads(prior.PIN.read_text())
    expected = pins["implementation_sources"]
    if tuple(expected) != ALL_UNITS or len(ALL_UNITS) != 12:
        raise SystemExit("exact twelve-unit source pin set required")
    for name, digest in expected.items():
        if not (source / name).is_file() or prior.sha(source / name) != digest:
            raise SystemExit(f"source pin mismatch: {name}")
    if not TARGET_CONDITIONALS.is_file():
        raise SystemExit("exact target SDK TargetConditionals.h is unavailable")

    copied = output / "IONetworkingFamily-186"
    objects_dir = output / "objects"
    network_headers = output / "include/IOKit/network"
    compat_dir = output / "compat"
    objects_dir.mkdir(parents=True)
    compat_dir.mkdir(parents=True)
    shutil.copytree(source, copied)
    network_headers.mkdir(parents=True)
    for header in copied.glob("*.h"):
        shutil.copy2(header, network_headers / header.name)
    target_copy = compat_dir / "TargetConditionals.h"
    shutil.copy2(TARGET_CONDITIONALS, target_copy)
    preinclude = compat_dir / "IONetworkingFamily186CXXCompat.h"
    preinclude.write_text(COMPAT_PREINCLUDE)

    base, cwd, old_source = prior.base_compile()
    compiled: dict[str, dict[str, object]] = {}
    object_paths: list[Path] = []
    for name in ALL_UNITS:
        object_path = objects_dir / f"{name}.o"
        result = prior.run(command_for(
            base, old_source, copied / name, object_path,
            network_headers.parent.parent, preinclude), cwd=cwd)
        diagnostics = prior.normalized_diagnostics(
            result.stderr + result.stdout, copied, output)
        if result.returncode:
            raise SystemExit(f"unexpected compile failure for {name}:\n" +
                             "\n".join(diagnostics))
        object_paths.append(object_path)
        compiled[name] = {
            "source_sha256": prior.sha(copied / name),
            "object_sha256": prior.sha(object_path),
            "diagnostics": diagnostics,
        }

    archive = output / "libIONetworkingFamily186-default-off.a"
    libtool = subprocess.check_output(["xcrun", "--find", "libtool"], text=True).strip()
    env = os.environ.copy()
    env["ZERO_AR_DATE"] = "1"
    archived = subprocess.run(
        [libtool, "-static", "-o", str(archive), *map(str, object_paths)],
        cwd=cwd, capture_output=True, text=True, timeout=120, env=env, check=False)
    if archived.returncode:
        raise SystemExit(archived.stderr)
    listing = subprocess.check_output(
        ["xcrun", "llvm-nm", "--defined-only", str(archive)], text=True)
    required = (
        "__ZN20IOEthernetController10initializeEv",
        "__ZN19IONetworkController4initEP12OSDictionary",
        "__ZN18IONetworkInterface9metaClassE",
        "__ZN14IONetworkStack9metaClassE",
        "__ZN18IOMbufMemoryCursor9metaClassE",
    )
    if not all(symbol in listing for symbol in required):
        raise SystemExit("archive lacks required all-family symbols")

    kernel_link = link_kernel(output, object_paths)
    copied_source_hashes = {name: prior.sha(copied / name) for name in ALL_UNITS}
    if copied_source_hashes != expected:
        raise SystemExit("copied Apple implementation bytes changed")
    report = {
        "schema_version": 1,
        "profile": "apple-ionetworkingfamily-186-default-off-complete-compile-v3",
        "release": pins["release"],
        "catalog_xnu_tag": pins["catalog_xnu_tag"],
        "workspace_xnu_tag": pins["workspace_xnu_tag"],
        "workspace_xnu_commit": pins["workspace_xnu_commit"],
        "compile_database_sha256": prior.sha(prior.COMPILE_DB),
        "manifest_sha256": prior.sha(prior.PIN),
        "compatibility": {
            "strategy": "generated forced preinclude plus exact target SDK header export",
            "preinclude_path": str(preinclude.relative_to(output)),
            "preinclude_sha256": prior.sha(preinclude),
            "target_conditionals_source": str(TARGET_CONDITIONALS.relative_to(ROOT)),
            "target_conditionals_sha256": prior.sha(target_copy),
        },
        "compiled_original_units": compiled,
        "archive": {
            "path": archive.name,
            "sha256": prior.sha(archive),
            "required_defined_symbols": list(required),
        },
        "kernel_link": kernel_link,
        "claims": {
            "original_apple_source_modified": False,
            "all_twelve_original_units_compiled": True,
            "default_off": True,
            "production_file_list_modified": False,
            "service_catalogue_modified": False,
            "kernel_link_complete": bool(kernel_link.get("complete")),
            "interface_registered": False,
            "networking": False,
            "ssh": False,
            "hardware_access": False,
        },
        "next_blocker": (
            "Keep the archive default-off; separately qualify production composition, "
            "catalogue ownership, controller attachment and runtime registration."
        ),
    }
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps({
        "status": "default_off_complete_compile",
        "compiled_units": len(compiled),
        "archive_sha256": report["archive"]["sha256"],
        "kernel_link_complete": report["claims"]["kernel_link_complete"],
        "report_sha256": prior.sha(report_path),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
