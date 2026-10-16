#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Seal Apple's Libc-167 sscanf parser against the accepted stdio ABI."""

import json
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import tempfile

from tools.rpi5 import build_apple_ssh_perror as prior
from tools.rpi5 import prepare_pid1


ROOT, sha = prior.ROOT, prior.sha
BASE = ROOT / "build/rpi5/apple-ssh-perror-fedl96a9"
BASE_SHA = "be08baf42a4708591d75e642b80daeb8936af8210ee6155f9951124a9dd55007"
LIBC167 = prior.LIBC167
LIBC167_TAG = prior.LIBC167_TAG
LIBC167_COMMIT = prior.LIBC167_COMMIT
LIBC167_ARCHIVE_SHA = prior.LIBC167_ARCHIVE_SHA
LOCK, ARCHIVE = prior.LOCK, prior.ARCHIVE
SSCANF = LIBC167 / "stdio.subproj/sscanf.c"
VFSCANF = LIBC167 / "stdio.subproj/vfscanf.c"
SOURCE_SHA = {
    str(SSCANF): "a5d2994744baadc2cd8f2bcacd35beb4980f67ba9c4ce3410821075f01dcd015",
    str(VFSCANF): "9a08021593cdee0c1caec79460ccc3272a17f3f6928be448faaba516f2680a81",
}
HARNESS = ROOT / "tools/rpi5/tests/ssh_sscanf_host.c"
TEST = ROOT / "tools/rpi5/tests/test_apple_ssh_sscanf.py"
CLOSURE_TEST = prior.CLOSURE_TEST
EXPECTED = "APPLE_LIBC167_SSCANF PASS SSH=1 X11=1 HEX=1 TOKEN=1 SCANSET=1 EOF=1\n"
DEPENDENCIES = {
    "__DefaultRuneLocale", "___maskrune", "___srefill", "_fread", "_strlen",
    "_strtod", "_strtol", "_strtoul", "_ungetc",
}


def merge(*groups):
    result = {}
    for group in groups:
        for name, digest in group.items():
            if name in result and result[name] != digest:
                raise ValueError("Conflicting source pin " + name)
            result[name] = digest
    return result


def build():
    if sha(BASE / "manifest.json") != BASE_SHA:
        raise ValueError("Exact sealed 34-import predecessor required")
    lock = json.loads(LOCK.read_text())
    pin = next(row for row in lock["sources"] if row["tag"] == LIBC167_TAG)
    if pin["commit"] != LIBC167_COMMIT or pin["archiveSHA256"] != LIBC167_ARCHIVE_SHA:
        raise ValueError("Exact Apple Libc-167 source lock required")
    if sha(ARCHIVE) != LIBC167_ARCHIVE_SHA:
        raise ValueError("Exact Apple Libc-167 archive required")
    with tarfile.open(ARCHIVE, "r:gz") as source_archive:
        for path in (SSCANF, VFSCANF):
            member = "Libc-Libc-167/stdio.subproj/" + path.name
            archived = source_archive.extractfile(member)
            if sha(path) != SOURCE_SHA[str(path)] or archived is None or path.read_bytes() != archived.read():
                raise ValueError("Selected parser source differs from pinned Apple archive: " + path.name)

    base = json.loads((BASE / "manifest.json").read_text())
    pins = merge({str(BASE / "manifest.json"): BASE_SHA},
                 *[base[key] for key in ("source_inputs_sha256", "headers_sha256", "generated_sha256")])
    for path in (Path(__file__).resolve(), LOCK, ARCHIVE, SSCANF, VFSCANF, HARNESS,
                 TEST, CLOSURE_TEST, ROOT / "tools/rpi5/prepare_pid1.py"):
        pins = merge(pins, {str(path): sha(path)})
    tools = {
        str(Path(subprocess.check_output(["xcrun", "--find", name], text=True).strip()).resolve()): None
        for name in ("clang", "ar", "nm", "ld", "llvm-objdump")
    }
    tools[str(Path("/usr/bin/xcrun").resolve())] = None
    tools = {name: sha(name) for name in tools}
    pins = merge(pins, tools)

    def verify():
        for name, digest in pins.items():
            if sha(name) != digest:
                raise ValueError("Source drift " + name)

    verify()
    out = Path(tempfile.mkdtemp(prefix="apple-ssh-sscanf-", dir=ROOT / "build/rpi5"))
    print("OUTPUT=" + str(out), flush=True)
    commands, headers, records = [], {}, {}

    def run(args, label, allowed=False):
        args = list(map(str, args))
        proc = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=90)
        for stream in ("stdout", "stderr"):
            (out / (label + "." + stream)).write_text(getattr(proc, stream))
        commands.append({"command": args, "cwd": str(ROOT), "returncode": proc.returncode,
                         "stdout": str(out / (label + ".stdout")),
                         "stderr": str(out / (label + ".stderr"))})
        if proc.returncode and not allowed:
            raise ValueError(label + ": " + proc.stderr[-5000:])
        return proc

    def deps(text):
        return {str(Path(name).resolve()): sha(Path(name).resolve())
                for name in shlex.split(text.replace("\\\n", " ").partition(":")[2])}

    def compile_(flags, path, label):
        before = deps(run([*flags, "-M", path], label + "-scan").stdout)
        dep, obj = out / (label + ".d"), out / (label + ".o")
        run([*flags, "-MD", "-MF", dep, "-c", path, "-o", obj], label + "-compile")
        after = deps(dep.read_text())
        if before != after:
            raise ValueError("Actual compiler dependency changed")
        headers.update(after)
        records[label] = {"scanned_sha256": before, "consumed_sha256": after}
        return obj

    compiler = Path(subprocess.check_output(["xcrun", "--find", "clang"], text=True).strip()).resolve()
    sdk = Path(subprocess.check_output(["xcrun", "--show-sdk-path"], text=True).strip()).resolve()
    common = [str(compiler), "-isysroot", str(sdk), "-fno-builtin", "-fno-stack-protector",
              "-Wno-deprecated-non-prototype"]
    target = [*common, "-target", "arm64-apple-darwin", "-mcpu=cortex-a76", "-ffreestanding", "-O2"]
    native = [*common, "-O1", "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=undefined"]

    sscanf_obj = compile_(target, SSCANF, "target-sscanf")
    vfscanf_obj = compile_(target, VFSCANF, "target-vfscanf")
    host_sscanf = compile_([*native, "-Dsscanf=apple_sscanf_under_test",
                            "-D__svfscanf=apple_svfscanf_under_test"], SSCANF, "host-sscanf")
    host_vfscanf = compile_([*native, "-D__svfscanf=apple_svfscanf_under_test",
                             "-D__srefill=fixture_srefill"], VFSCANF, "host-vfscanf")
    host_harness = compile_(native, HARNESS, "host-harness")
    host = out / "sscanf-host"
    run([*native, host_sscanf, host_vfscanf, host_harness, "-o", host], "host-link")
    good = run([host], "host-run")
    if good.stdout != EXPECTED or good.stderr:
        raise ValueError("Native sscanf oracle differs")
    if run([host, "negative"], "host-negative", True).returncode != 37:
        raise ValueError("Negative oracle accepted")

    archive = out / "libapple-libc167-sscanf.a"
    run(["xcrun", "ar", "rcs", archive, sscanf_obj, vfscanf_obj], "archive")
    exports = {
        "sscanf": run(["xcrun", "nm", "-gjU", sscanf_obj], "sscanf-exports").stdout.splitlines(),
        "vfscanf": run(["xcrun", "nm", "-gjU", vfscanf_obj], "vfscanf-exports").stdout.splitlines(),
    }
    if exports != {"sscanf": ["_sscanf"], "vfscanf": ["___svfscanf"]}:
        raise ValueError("Unexpected parser exports")
    undefined = set()
    for obj, label in ((sscanf_obj, "sscanf"), (vfscanf_obj, "vfscanf")):
        undefined.update(run(["xcrun", "nm", "-u", obj], label + "-undefined").stdout.split())
    if undefined != DEPENDENCIES | {"___svfscanf"}:
        raise ValueError("Unexpected parser dependencies " + repr(sorted(undefined)))

    link = list(next(row["command"] for row in base["commands"] if row["stdout"].endswith("/target-link.stdout")))
    original_link = list(link)
    link[link.index("-o") + 1] = str(out / "NOT_RUN_ssh")
    link[link.index("-map") + 1] = str(out / "target.map")
    linked = run([*link, archive], "target-link", True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', linked.stderr, re.M)))
    duplicate = sorted(set(re.findall(r"duplicate symbol '([^']+)'", linked.stderr)))
    closed = sorted(set(base["target_missing_symbols"]) - set(missing))
    added = sorted(set(missing) - set(base["target_missing_symbols"]))
    if linked.returncode == 0 or duplicate or closed != ["_sscanf"] or added or len(missing) != 33:
        raise ValueError("Unexpected sscanf delta " + repr((closed, added, duplicate, len(missing))))

    contract = list(next(row["command"] for row in base["commands"] if row["stdout"].endswith("/contract-link.stdout")))
    contract[contract.index("-o") + 1] = str(out / "NOT_RUN_sscanf_contract")
    contract[contract.index("-map") + 1] = str(out / "contract.map")
    contract += [str(archive), "-u", "_sscanf"]
    run(contract, "contract-link")
    contract_target = out / "NOT_RUN_sscanf_contract"
    if run(["xcrun", "nm", "-ju", contract_target], "contract-undefined").stdout:
        raise ValueError("Forced parser contract unresolved")
    live = run(["xcrun", "nm", "-gjU", contract_target], "contract-exports").stdout.splitlines()
    if "_sscanf" not in live or "___svfscanf" not in live:
        raise ValueError("Parser atoms were not retained")
    mapping = (out / "contract.map").read_text()
    object_map = {int(index): name for index, name in re.findall(r"^\[\s*(\d+)\]\s+(.+)$", mapping, re.M)}
    owners = {}
    for symbol in sorted(DEPENDENCIES | {"_sscanf", "___svfscanf"}):
        for line in mapping.splitlines():
            match = re.match(r"^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+" +
                             re.escape(symbol) + r"$", line)
            if match:
                owners[symbol] = object_map[int(match.group(1))]
                break
    if set(owners) != DEPENDENCIES | {"_sscanf", "___svfscanf"}:
        raise ValueError("Complete parser dependency ownership not found")
    if not owners["_sscanf"].startswith(str(archive) + "(") or not owners["___svfscanf"].startswith(str(archive) + "("):
        raise ValueError("Provider archive does not own both parser atoms")
    for symbol in DEPENDENCIES:
        if owners[symbol].startswith(str(archive) + "("):
            raise ValueError("Accepted dependency was replaced by provider: " + symbol)
    inspection = prepare_pid1.inspect(contract_target.read_bytes())

    verify()
    if any(sha(name) != digest for name, digest in headers.items()):
        raise ValueError("Consumed header drift")
    stdio_abi = {name: digest for name, digest in headers.items()
                 if name.endswith("/stdio.h") or name.endswith("/sys/stdio.h")}
    for name, digest in stdio_abi.items():
        if base["headers_sha256"].get(name) != digest:
            raise ValueError("Provider FILE ABI header differs from predecessor")
    if len(stdio_abi) != 2:
        raise ValueError("Expected public and sys stdio ABI headers")

    report = {
        "profile": "apple-libc167-accepted-file-abi-sscanf-v1",
        "source_inputs_sha256": pins, "headers_sha256": headers, "generated_sha256": {},
        "tools_sha256": tools, "dependency_records": records, "commands": commands,
        "apple_libc167_tag": LIBC167_TAG, "apple_libc167_commit": LIBC167_COMMIT,
        "apple_libc167_archive_sha256": LIBC167_ARCHIVE_SHA,
        "original_sources_sha256": SOURCE_SHA, "original_sources_unchanged": True,
        "stdio_abi_headers_sha256": stdio_abi,
        "target_archive": str(archive), "object_exports": exports,
        "object_undefined_symbols": sorted(undefined),
        "target_dependency_symbols": sorted(DEPENDENCIES), "live_symbol_owners": owners,
        "forced_live_exports": live, "static_inspection": inspection,
        "original_full_client_link_command": original_link, "target_missing_symbols": missing,
        "target_duplicate_symbols": duplicate, "closed_symbols": closed,
        "newly_reachable_symbols": added, "previous_missing_count": 34,
        "remaining_missing_count": 33,
        "native_asan_ubsan_pass": True, "native_stdout": good.stdout,
        "native_test_boundary": "fixture_srefill returns EOF for exhausted string-backed FILE only",
        "accepted_runtime_modified": False, "provider_stubs": False,
        "optional_features_removed": False, "target_executed": False,
        "full_client_qualified": False, "resolver_notify_service_gates_unchanged": True,
        "filesystem_layout": ["/usr/bin/ssh", "/usr/sbin/sshd", "/usr/libexec", "/private/etc/ssh"],
        "remaining_provider_groups": prior.prior.prior.prior.prior.prior.categories(missing),
    }
    report["generated_sha256"] = {str(path): sha(path) for path in out.rglob("*") if path.is_file()}
    (out / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(out), "manifest_sha256": sha(out / "manifest.json"),
                      "closed": closed, "added": added, "remaining": len(missing),
                      "native_stdout": good.stdout}, indent=2))
    return out, report


if __name__ == "__main__":
    build()
