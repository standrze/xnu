#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build a default-off current-Apple FILEX stream-lock target candidate.

The target contract uses one coherent current Libc FILE/__sFILEX definition,
the unchanged current fwide and _flock_stub translation units, and the genuine
Apple pthread mutex provider.  It is linked but never executed here.  The host
oracle executes the same two Apple source files against host pthread only and
is explicitly not Raspberry Pi evidence.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
LIBC = ROOT / "build/rpi5/apple-libc-main-candidate-20261013"
PTHREAD = ROOT / "build/rpi5/apple-libpthread-main-candidate-20261013"
PREREQUISITE = ROOT / "build/rpi5/apple-pthread-filex-gate-gj99o8li/manifest.json"
INVENTORY = ROOT / "build/rpi5/apple-ssh-spawn-group-e7hiad29/manifest.json"
STATIC_COMPLETE = ROOT / "build/rpi5/apple-pthread-static-complete-gm82fjkz/manifest.json"
PRIVATE_ABI = ROOT / "build/rpi5/apple-pthread-static-complete-gm82fjkz/private-abi-runtime.a"
PROFILE = "apple-current-filex-stream-lock-default-off-v1"
LIBC_COMMIT = "71bbe350ab79eef58113991d817ccc6165061a64"
PTHREAD_COMMIT = "42d026df5b07825070f60134b980a1ec2552dfee"
HOST_STDOUT = (
    "APPLE_FILEX_HOST PASS THREADS=6 ITERATIONS=4096 RECURSIVE=3 "
    "ORIENTATION=1 ERRNO=1 HOST_ONLY\n"
)

FROZEN = {
    PREREQUISITE: "9c0d30fe853dd864e78035293b74880b2fb1a2b63f60cdba551a9f5c1706bca3",
    INVENTORY: "268e2b11873129cd5a367eeb0829e705ca90cc2ceeedbdfe48d62ba07d6c08b3",
    STATIC_COMPLETE: "4a22b183000378e842d59c643ed1f8a80a520e1e77d62370880a7c095adfc35a",
    PRIVATE_ABI: "0af98677059dcbf697faea642698a2704ffedbba65349afdb392ffddd273ab9f",
    ROOT / "build/rpi5/apple-pthread-memory-4idfg5qr/libapple-pthread-platform-scoped.a":
        "162e135968d0b3922ce03aa884f2f2c4beaec92dd2d7835eba3436e346311031",
    ROOT / "build/rpi5/apple-pthread-wait-if5o744t/libapple-pthread-wait.a":
        "15faea40b073a196e9fcc37ab465b47cd757d59b584f26b7640b0c9693b04923",
    ROOT / "build/rpi5/apple-pthread-bcm2712-check-kgbwgqa0/libapple-abort-reason.a":
        "0f43c3d3fd011e50c22f30e0aca68c210f1356110843fb0dac0cb65ffdc746b2",
    ROOT / "build/rpi5/apple-pthread-memory-4idfg5qr/libapple-pthread-memory.a":
        "876ccfd72b548dab4788d24669f1624d2beed82299529c5f7ce9f02e6461c85e",
    ROOT / "build/rpi5/apple-pthread-dyld-threads-zmg7gxfj/libapple-pthread-mach-dyld-bootstrap.a":
        "8d46d9990bcd668b9006af5982f26aa82f7a92cdc9462ea4e3b7099b2f82b744",
    ROOT / "build/rpi5/apple-pthread-log-clock-m3ct69va/libapple-pthread-log.a":
        "a8ace4b6f48d07f483a91d33b3a527164fa75f771401f370b20645781fc08eda",
    ROOT / "build/rpi5/apple-pthread-join-wait-ri8lyyub/libapple-pthread-create-join.a":
        "63953cf23b398dcfe7cb280048cf58ea62795d50e4fce5de3a1ff2a1b735e8f2",
}

APPLE_SOURCES = {
    LIBC / "APPLE_LICENSE": "e5881019d8766c1e88a5fe1dbca4ba40c78011d41fcb18f6e9f50df60182685b",
    LIBC / "include/_stdio.h": "e5484b74077bfc3a1228171435bf0a74b8e6c23d48c5c1c1f1409c487397a72d",
    LIBC / "include/stdio.h": "d2220614f42d3cb678ae0de176ba0ab3256e15fb45b3efdb5d17b8ac1f6a4b54",
    LIBC / "stdio/FreeBSD/local.h": "88526319ee5d11f374ba3e4da8c59ea3b6a5aee803700574a1dfd21e66b13705",
    LIBC / "stdio/FreeBSD/_flock_stub.c": "9bc78e2a871139a3a9f23811d396814cf8d1ae9d65d10864668ef494361e6d59",
    LIBC / "stdio/FreeBSD/fwide.c": "2235f1132485c71234e2c7be31438b868074a9a6d632947d5c619d80d99f1a66",
}

TARGET_HARNESS = ROOT / "tools/rpi5/user/apple_filex_stream_lock_target.c"
HOST_HARNESS = ROOT / "tools/rpi5/tests/apple_filex_stream_lock_host.c"
TARGET_ARCHIVES = [
    ROOT / "build/rpi5/apple-sysctl-runtime-nfhrya57/libapple-sysctl-runtime.a",
    ROOT / "build/rpi5/apple-pthread-memory-4idfg5qr/libapple-pthread-platform-scoped.a",
    ROOT / "build/rpi5/apple-pthread-wait-if5o744t/libapple-pthread-wait.a",
    ROOT / "build/rpi5/apple-pthread-bcm2712-check-kgbwgqa0/libapple-abort-reason.a",
    ROOT / "build/rpi5/apple-pthread-memory-4idfg5qr/libapple-pthread-memory.a",
    ROOT / "build/rpi5/apple-pthread-dyld-threads-zmg7gxfj/libapple-pthread-mach-dyld-bootstrap.a",
    ROOT / "build/rpi5/apple-pthread-log-clock-m3ct69va/libapple-pthread-log.a",
    ROOT / "build/rpi5/apple-pthread-dyld-threads-zmg7gxfj/libapple-pthread-mach-dyld-bootstrap.a",
    ROOT / "build/rpi5/apple-pthread-join-wait-ri8lyyub/libapple-pthread-create-join.a",
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exact_git_blob(repository, path):
    relative = path.relative_to(repository)
    return subprocess.check_output(
        ["git", "-C", repository, "show", "HEAD:" + str(relative)]
    )


def require_inputs():
    pins = {}
    for path, expected in {**FROZEN, **APPLE_SOURCES}.items():
        actual = sha(path)
        if actual != expected:
            raise ValueError(f"frozen input drift: {path}: {actual}")
        pins[str(path)] = actual
    for repository, expected in ((LIBC, LIBC_COMMIT), (PTHREAD, PTHREAD_COMMIT)):
        commit = subprocess.check_output(
            ["git", "-C", repository, "rev-parse", "HEAD"], text=True
        ).strip()
        if commit != expected:
            raise ValueError(f"Apple revision drift: {repository}: {commit}")
    for path in APPLE_SOURCES:
        if path.name != "APPLE_LICENSE" and exact_git_blob(LIBC, path) != path.read_bytes():
            raise ValueError("Apple source differs from pinned git blob: " + str(path))
    for path in (TARGET_HARNESS, HOST_HARNESS, Path(__file__).resolve()):
        pins[str(path)] = sha(path)
    return pins


def run(command, output, label, commands, allowed=False, env=None, cwd=None):
    command = list(map(str, command))
    result = subprocess.run(
        command,
        cwd=cwd or ROOT,
        text=True,
        capture_output=True,
        timeout=120,
        env=env,
    )
    stdout = output / f"{label}.stdout"
    stderr = output / f"{label}.stderr"
    stdout.write_text(result.stdout)
    stderr.write_text(result.stderr)
    commands.append(
        dict(
            command=command,
            cwd=str(cwd or ROOT),
            returncode=result.returncode,
            stdout=str(stdout),
            stderr=str(stderr),
        )
    )
    if result.returncode and not allowed:
        raise ValueError(f"{label} failed: {result.stderr[-5000:]}")
    return result


def dependencies(raw):
    names = shlex.split(raw.replace("\\\n", " ").partition(":")[2])
    return {str(Path(name).resolve()): sha(Path(name).resolve()) for name in names}


def compile_unit(flags, source, output, label, commands, headers, extra=()):
    scan = run([*flags, *extra, "-M", source], output, label + "-scan", commands)
    before = dependencies(scan.stdout)
    obj = output / (label + ".o")
    dep = output / (label + ".d")
    run(
        [*flags, *extra, "-MD", "-MF", dep, "-c", source, "-o", obj],
        output,
        label + "-compile",
        commands,
    )
    after = dependencies(dep.read_text())
    if before != after:
        raise ValueError("scanned/consumed dependency mismatch: " + label)
    headers.update(before)
    return obj, dict(scanned_sha256=before, consumed_sha256=after)


def map_owners(mapping, symbols):
    text = mapping.read_text()
    table = {int(index): owner for index, owner in re.findall(r"(?m)^\[\s*(\d+)\]\s+(.+)$", text)}
    owners = {}
    for symbol in symbols:
        matches = re.findall(
            r"(?m)^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+"
            + re.escape(symbol)
            + r"$",
            text,
        )
        if len(matches) != 1:
            raise ValueError("expected one live map owner for " + symbol)
        owners[symbol] = table[int(matches[0])]
    return owners


def build():
    pins = require_inputs()
    output = Path(
        tempfile.mkdtemp(prefix="apple-filex-stream-lock-", dir=ROOT / "build/rpi5")
    )
    print("OUTPUT=" + str(output), flush=True)
    commands = []
    headers = {}
    records = {}

    inventory = json.loads(INVENTORY.read_text())
    popen_command = next(
        entry["command"]
        for entry in inventory["commands"]
        if entry["stdout"].endswith("/popen-compile.stdout")
    )
    target_flags = popen_command[: popen_command.index("-MD")]

    sources = {
        "flock": LIBC / "stdio/FreeBSD/_flock_stub.c",
        "fwide": LIBC / "stdio/FreeBSD/fwide.c",
        "target-harness": TARGET_HARNESS,
    }
    target_objects = []
    for label, source in sources.items():
        obj, record = compile_unit(
            target_flags, source, output, "target-" + label, commands, headers
        )
        target_objects.append(obj)
        records["target-" + label] = record

    # Extract only the genuine trap and errno owners needed by this contract.
    # Linking the entire private ABI archive would pull its unrelated _start.
    run(
        ["xcrun", "ar", "-x", PRIVATE_ABI, "0-syscalls.o", "2-errno.o"],
        output,
        "abi-extract",
        commands,
        cwd=output,
    )
    extracted = []
    for name in ("0-syscalls.o", "2-errno.o"):
        destination = output / name
        if not destination.is_file():
            raise ValueError("expected extracted ABI member absent: " + name)
        extracted.append(destination)

    target = output / "NOT_RUN_apple_filex_stream_lock"
    mapping = output / "target.map"
    link = [
        "xcrun", "ld", "-arch", "arm64", "-platform_version", "macos", "26.0", "27.0",
        "-static", "-e", "_apple_filex_candidate_start", "-dead_strip",
        "-no_adhoc_codesign", "-no_uuid", "-o", target,
        "-u", "_apple_filex_file_size", "-u", "_apple_filex_extra_size",
        "-u", "_apple_filex_extra_offset", "-u", "_apple_filex_mutex_offset",
        *TARGET_ARCHIVES,
        *extracted,
        *target_objects,
        "-map", mapping,
    ]
    run(link, output, "target-link", commands)
    undefined = run(["xcrun", "nm", "-ju", target], output, "target-undefined", commands)
    if undefined.stdout:
        raise ValueError("target contract retained undefined symbols")
    symbols = run(["xcrun", "nm", "-g", target], output, "target-symbols", commands)
    disassembly = run(
        ["xcrun", "llvm-objdump", "-d", "-r", target],
        output,
        "target-disassembly",
        commands,
    )
    required_symbols = {
        "_apple_filex_candidate_start", "_apple_filex_candidate_result",
        "_apple_filex_file_size", "_apple_filex_extra_size", "_apple_filex_extra_offset",
        "_apple_filex_mutex_offset", "_flockfile", "_ftrylockfile", "_funlockfile",
        "_fwide", "_pthread_mutex_lock", "_pthread_mutex_trylock", "_pthread_mutex_unlock",
    }
    actual_symbols = set(re.findall(r"(?m)^[0-9a-f]+ [A-Z] (\S+)$", symbols.stdout))
    if not required_symbols <= actual_symbols:
        raise ValueError("target symbols absent: " + repr(sorted(required_symbols - actual_symbols)))
    owners = map_owners(mapping, required_symbols)
    for symbol in ("_flockfile", "_ftrylockfile", "_funlockfile"):
        if "target-flock.o" not in owners[symbol]:
            raise ValueError("wrong current flock owner: " + symbol)
    if "target-fwide.o" not in owners["_fwide"]:
        raise ValueError("wrong current fwide owner")
    for symbol in ("_pthread_mutex_lock", "_pthread_mutex_trylock", "_pthread_mutex_unlock"):
        if "libapple-pthread-platform-scoped.a" not in owners[symbol]:
            raise ValueError("wrong genuine pthread owner: " + symbol)
    forbidden = ("private-apple-runtime.a", "Libc-167", "stdio.subproj-")
    if any(item in mapping.read_text() for item in forbidden):
        raise ValueError("incompatible or legacy FILE owner entered target map")
    if "wfe" not in disassembly.stdout:
        raise ValueError("nonreturning link-only target terminator absent")

    host_flags = list(target_flags)
    index = host_flags.index("-target")
    if host_flags[index + 1] != "arm64-apple-darwin":
        raise ValueError("unexpected inherited compiler target flag")
    del host_flags[index:index + 2]
    host_flags.remove("-mcpu=cortex-a76")
    host_flags.remove("-ffreestanding")
    host_flags.extend(
        ["-O1", "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-pthread"]
    )
    renames = [
        "-D_flockfile=apple_candidate_flockfile",
        "-Dflockfile=apple_candidate_flockfile",
        "-D_flockfile_debug_stub=apple_candidate_flockfile_debug_stub",
        "-D_flockfile_debug=apple_candidate_flockfile_debug",
        "-D_ftrylockfile=apple_candidate_ftrylockfile",
        "-Dftrylockfile=apple_candidate_ftrylockfile",
        "-D_funlockfile=apple_candidate_funlockfile",
        "-Dfunlockfile=apple_candidate_funlockfile",
    ]
    host_flock, record = compile_unit(
        host_flags, sources["flock"], output, "host-flock", commands, headers, renames
    )
    records["host-flock"] = record
    host_fwide, record = compile_unit(
        host_flags,
        sources["fwide"],
        output,
        "host-fwide",
        commands,
        headers,
        ["-Dfwide=apple_candidate_fwide", *renames],
    )
    records["host-fwide"] = record
    host_harness, record = compile_unit(
        host_flags, HOST_HARNESS, output, "host-harness", commands, headers
    )
    records["host-harness"] = record
    host = output / "filex-host-oracle"
    run(
        [*host_flags, host_harness, host_flock, host_fwide, "-o", host],
        output,
        "host-link",
        commands,
    )
    host_run = run([host], output, "host-run", commands)
    if host_run.stdout != HOST_STDOUT or host_run.stderr:
        raise ValueError("host current-source oracle output changed")

    for path, digest in {**pins, **headers}.items():
        if sha(path) != digest:
            raise ValueError("source/header input drift after build: " + path)

    license_copy = output / "APPLE_LICENSE"
    license_copy.write_bytes((LIBC / "APPLE_LICENSE").read_bytes())
    receipts = output / "SOURCE-RECEIPTS.json"
    receipt_document = {
        "repository": "https://github.com/apple-oss-distributions/Libc.git",
        "commit": LIBC_COMMIT,
        "license": {"path": str(LIBC / "APPLE_LICENSE"), "sha256": sha(LIBC / "APPLE_LICENSE")},
        "sources": {str(path): digest for path, digest in APPLE_SOURCES.items()},
        "source_bodies_unchanged": True,
        "compile_time_symbol_renames_host_only": renames,
    }
    receipts.write_text(json.dumps(receipt_document, indent=2, sort_keys=True) + "\n")

    report = {
        "profile": PROFILE,
        "default_off": True,
        "admitted": False,
        "gate_open": False,
        "target_executed": False,
        "pi_executed": False,
        "target_image_changed": False,
        "accepted_runtime_modified": False,
        "source_inputs_sha256": pins,
        "headers_sha256": headers,
        "dependency_records": records,
        "apple_source_receipts": receipt_document,
        "license_copy": str(license_copy),
        "target": str(target),
        "target_sha256": sha(target),
        "target_zero_undefined": True,
        "target_symbols": sorted(required_symbols),
        "live_symbol_owners": owners,
        "current_file_abi_only": True,
        "forbidden_legacy_map_inputs": list(forbidden),
        "legacy_file_abi_mixed": False,
        "filex_stream_lock_candidate_linked": True,
        "filex_stream_lock_target_qualified": False,
        "host_oracle": {
            "actual_apple_sources": [str(sources["flock"]), str(sources["fwide"])],
            "asan_ubsan": True,
            "concurrent_threads": 6,
            "iterations_per_thread": 4096,
            "recursive_depth": 3,
            "orientation_sticky": True,
            "errno_thread_local_preserved": True,
            "stdout": host_run.stdout,
            "target_evidence": False,
            "host_pthread_only": True,
        },
        "remaining_blocker": (
            "execute this exact linked current-FILEX candidate on the Pi with the genuine Apple "
            "pthread provider; host concurrency and static linking are not target behavior"
        ),
        "next_prerequisite": "target FILEX recursive-lock/orientation execution trial",
        "commands": commands,
    }
    report["generated_sha256"] = {
        str(path): sha(path) for path in output.rglob("*") if path.is_file()
    }
    manifest = output / "manifest.json"
    manifest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "package": str(output),
                "manifest_sha256": sha(manifest),
                "target_sha256": report["target_sha256"],
                "target_zero_undefined": True,
                "host": host_run.stdout.rstrip(),
                "gate_open": False,
                "next_prerequisite": report["next_prerequisite"],
            },
            indent=2,
        )
    )
    return output, report


def check(package):
    package = Path(package).resolve()
    report = json.loads((package / "manifest.json").read_text())
    require_inputs()
    if report.get("profile") != PROFILE or report.get("default_off") is not True:
        raise ValueError("not a current FILEX default-off candidate")
    for field in ("admitted", "gate_open", "target_executed", "pi_executed",
                  "target_image_changed", "accepted_runtime_modified",
                  "filex_stream_lock_target_qualified", "legacy_file_abi_mixed"):
        if report.get(field) is not False:
            raise ValueError("default-off/target-evidence boundary changed: " + field)
    if report.get("filex_stream_lock_candidate_linked") is not True or \
       report.get("target_zero_undefined") is not True or \
       report.get("current_file_abi_only") is not True:
        raise ValueError("static current-FILEX contract changed")
    if report.get("host_oracle", {}).get("target_evidence") is not False or \
       report.get("host_oracle", {}).get("stdout") != HOST_STDOUT:
        raise ValueError("host/target evidence separation changed")
    target = Path(report["target"])
    if package not in target.parents or sha(target) != report["target_sha256"]:
        raise ValueError("linked target drift")
    undefined = subprocess.check_output(["xcrun", "nm", "-ju", target], text=True)
    if undefined:
        raise ValueError("linked target is no longer closed")
    mapping = package / "target.map"
    if any(item in mapping.read_text() for item in report["forbidden_legacy_map_inputs"]):
        raise ValueError("legacy FILE ABI entered map")
    for name, digest in report["generated_sha256"].items():
        path = Path(name)
        if package not in path.parents or path.name == "manifest.json" or sha(path) != digest:
            raise ValueError("generated artifact drift: " + name)
    if sha(package / "APPLE_LICENSE") != APPLE_SOURCES[LIBC / "APPLE_LICENSE"]:
        raise ValueError("license receipt drift")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", type=Path)
    arguments = parser.parse_args()
    if arguments.check:
        checked = check(arguments.check)
        print(
            json.dumps(
                {
                    "profile": checked["profile"],
                    "target_sha256": checked["target_sha256"],
                    "target_zero_undefined": checked["target_zero_undefined"],
                    "gate_open": checked["gate_open"],
                    "next_prerequisite": checked["next_prerequisite"],
                },
                indent=2,
            )
        )
    else:
        build()
