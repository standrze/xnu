#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Seal Apple's Libc-167 FILE-free perror with its real writev syscall."""

import json
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import tempfile

from tools.rpi5 import build_apple_ssh_localtime_r as prior


ROOT, sha = prior.ROOT, prior.sha
BASE = ROOT / "build/rpi5/apple-ssh-localtime-r-5apxxhjz"
BASE_SHA = "0093975e99016eca90282e2e9dd68264855d40a0bf3c9230d570cc671f3c11c1"
LIBC167 = ROOT / "experiments/darwin-container/userland/upstream/Libc-Libc-167"
LIBC167_COMMIT = "630404129b7029c30def14e0a5150c4b93d7458c"
LIBC167_TAG = "Libc-167"
LIBC167_ARCHIVE_SHA = "abb1bc021fbe61622148fad98b5ef955e5f7bf56c804895a14cac6b4132d183b"
SOURCE_SHA = "865d899138df678496ef4479b96479c059c9271140ea85d01aba844f254280d5"
LOCK = ROOT / "experiments/darwin-container/userland/apple-runtime.sources.lock.json"
ARCHIVE = ROOT / "experiments/darwin-container/userland/upstream/Libc-167.tar.gz"
SOURCE = LIBC167 / "stdio.subproj/perror.c"
SYSCALL = ROOT / "tools/rpi5/user/apple_writev_runtime_call.S"
HARNESS = ROOT / "tools/rpi5/tests/ssh_perror_host.c"
TEST = ROOT / "tools/rpi5/tests/test_apple_ssh_perror.py"
CLOSURE_TEST = prior.CLOSURE_TEST
EXPECTED = "APPLE_LIBC167_PERROR PASS PREFIX=1 EMPTY=1 NULL=1 WRITEV_FAILURE=1 ABI=NO_FILE\n"


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
        raise ValueError("Exact sealed 35-import predecessor required")
    lock = json.loads(LOCK.read_text())
    pin = next(row for row in lock["sources"] if row["tag"] == LIBC167_TAG)
    if pin["commit"] != LIBC167_COMMIT or pin["archiveSHA256"] != LIBC167_ARCHIVE_SHA:
        raise ValueError("Exact Apple Libc-167 source lock required")
    if sha(ARCHIVE) != LIBC167_ARCHIVE_SHA or sha(SOURCE) != SOURCE_SHA:
        raise ValueError("Exact Apple Libc-167 archive and perror source required")
    with tarfile.open(ARCHIVE, "r:gz") as source_archive:
        archived = source_archive.extractfile("Libc-Libc-167/stdio.subproj/perror.c")
        if archived is None or SOURCE.read_bytes() != archived.read():
            raise ValueError("Extracted perror source differs from pinned Apple archive")
    base = json.loads((BASE / "manifest.json").read_text())
    pins = merge({str(BASE / "manifest.json"): BASE_SHA}, *[base[k] for k in ("source_inputs_sha256", "headers_sha256", "generated_sha256")])
    for path in (Path(__file__).resolve(), LOCK, ARCHIVE, SOURCE, SYSCALL, HARNESS, TEST, CLOSURE_TEST, ROOT / "tools/rpi5/prepare_pid1.py"):
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
    out = Path(tempfile.mkdtemp(prefix="apple-ssh-perror-", dir=ROOT / "build/rpi5"))
    print("OUTPUT=" + str(out), flush=True)
    commands, headers, records = [], {}, {}

    def run(args, label, allowed=False):
        args = list(map(str, args))
        proc = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=90)
        for stream in ("stdout", "stderr"):
            (out / (label + "." + stream)).write_text(getattr(proc, stream))
        commands.append({"command": args, "cwd": str(ROOT), "returncode": proc.returncode,
                         "stdout": str(out / (label + ".stdout")), "stderr": str(out / (label + ".stderr"))})
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
    common = [str(compiler), "-isysroot", str(sdk), "-fno-builtin", "-fno-stack-protector", "-Wno-deprecated-non-prototype"]
    target = [*common, "-target", "arm64-apple-darwin", "-mcpu=cortex-a76", "-ffreestanding", "-O2"]
    native = [*common, "-O1", "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=undefined"]
    asm = [str(compiler), "-isysroot", str(sdk), "-target", "arm64-apple-darwin", "-mcpu=cortex-a76",
           "-I", str(ROOT / "libsyscall/custom"), "-x", "assembler-with-cpp"]

    perror_obj = compile_(target, SOURCE, "target-perror")
    writev_obj = compile_(asm, SYSCALL, "target-writev")
    host_perror = compile_([*native, "-Dperror=apple_perror_under_test", "-Dwritev=fixture_writev", "-Dstrerror=fixture_strerror"], SOURCE, "host-perror")
    host_harness = compile_(native, HARNESS, "host-harness")
    host = out / "perror-host"
    run([*native, host_perror, host_harness, "-o", host], "host-link")
    good = run([host], "host-run")
    if good.stdout != EXPECTED or good.stderr:
        raise ValueError("Native perror oracle differs")
    if run([host, "negative"], "host-negative", True).returncode != 37:
        raise ValueError("Negative oracle accepted")

    archive = out / "libapple-libc167-perror.a"
    run(["xcrun", "ar", "rcs", archive, perror_obj, writev_obj], "archive")
    perror_exports = run(["xcrun", "nm", "-gjU", perror_obj], "perror-exports").stdout.splitlines()
    writev_exports = run(["xcrun", "nm", "-gjU", writev_obj], "writev-exports").stdout.splitlines()
    if perror_exports != ["_perror"] or writev_exports != ["_writev"]:
        raise ValueError("Unexpected provider exports")

    link = list(next(c["command"] for c in base["commands"] if c["stdout"].endswith("/target-link.stdout")))
    original_link = list(link)
    link[link.index("-o") + 1] = str(out / "NOT_RUN_ssh")
    link[link.index("-map") + 1] = str(out / "target.map")
    linked = run([*link, archive], "target-link", True)
    missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', linked.stderr, re.M)))
    duplicate = sorted(set(re.findall(r"duplicate symbol '([^']+)'", linked.stderr)))
    closed = sorted(set(base["target_missing_symbols"]) - set(missing))
    added = sorted(set(missing) - set(base["target_missing_symbols"]))
    if linked.returncode == 0 or duplicate or closed != ["_perror"] or added or len(missing) != 34:
        raise ValueError("Unexpected perror delta " + repr((closed, added, duplicate, len(missing))))

    contract = list(next(c["command"] for c in base["commands"] if c["stdout"].endswith("/contract-link.stdout")))
    contract[contract.index("-o") + 1] = str(out / "NOT_RUN_perror_contract")
    contract[contract.index("-map") + 1] = str(out / "contract.map")
    contract += [str(archive), "-u", "_perror"]
    run(contract, "contract-link")
    contract_target = out / "NOT_RUN_perror_contract"
    if run(["xcrun", "nm", "-ju", contract_target], "contract-undefined").stdout:
        raise ValueError("Forced provider contract unresolved")
    live = run(["xcrun", "nm", "-gjU", contract_target], "contract-exports").stdout.splitlines()
    if "_perror" not in live or "_writev" not in live:
        raise ValueError("Provider atoms were not retained")
    mapping = (out / "contract.map").read_text()
    object_map = {int(i): name for i, name in re.findall(r"^\[\s*(\d+)\]\s+(.+)$", mapping, re.M)}
    owners = {}
    for symbol in ("_perror", "_writev"):
        for line in mapping.splitlines():
            match = re.match(r"^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+" + re.escape(symbol) + r"$", line)
            if match:
                owners[symbol] = object_map[int(match.group(1))]
    if set(owners) != {"_perror", "_writev"} or not all(owner.startswith(str(archive) + "(") for owner in owners.values()):
        raise ValueError("Provider archive does not own both live atoms")
    inspection = prior.prior.prior.prior.prepare_pid1.inspect(contract_target.read_bytes())

    verify()
    if any(sha(name) != digest for name, digest in headers.items()):
        raise ValueError("Consumed header drift")
    report = {
        "profile": "apple-libc167-file-free-perror-v1",
        "source_inputs_sha256": pins, "headers_sha256": headers, "generated_sha256": {},
        "tools_sha256": tools, "dependency_records": records, "commands": commands,
        "apple_libc167_tag": LIBC167_TAG, "apple_libc167_commit": LIBC167_COMMIT,
        "apple_libc167_archive_sha256": LIBC167_ARCHIVE_SHA,
        "original_source": str(SOURCE), "original_source_sha256": SOURCE_SHA,
        "original_source_unchanged": True, "source_accesses_FILE": False,
        "writev_wrapper": str(SYSCALL), "writev_semantics": "original Apple generated syscall macro with cerror_nocancel",
        "target_archive": str(archive), "object_exports": {"perror": perror_exports, "writev": writev_exports},
        "forced_live_exports": live, "live_symbol_owners": owners, "static_inspection": inspection,
        "original_full_client_link_command": original_link, "target_missing_symbols": missing,
        "target_duplicate_symbols": duplicate, "closed_symbols": closed, "newly_reachable_symbols": added,
        "previous_missing_count": 35, "remaining_missing_count": 34,
        "native_asan_ubsan_pass": True, "native_stdout": good.stdout,
        "native_boundaries": ["errno", "strerror", "writev capture"],
        "accepted_runtime_dependencies": ["__error", "strerror", "strlen", "cerror_nocancel"],
        "accepted_runtime_modified": False, "provider_stubs": False, "optional_features_removed": False,
        "target_executed": False, "full_client_qualified": False,
        "resolver_notify_service_gates_unchanged": True,
        "filesystem_layout": ["/usr/bin/ssh", "/usr/sbin/sshd", "/usr/libexec", "/private/etc/ssh"],
        "remaining_provider_groups": prior.prior.prior.prior.prior.categories(missing),
    }
    report["generated_sha256"] = {str(path): sha(path) for path in out.rglob("*") if path.is_file()}
    (out / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(out), "manifest_sha256": sha(out / "manifest.json"),
                      "closed": closed, "added": added, "remaining": len(missing),
                      "native_stdout": good.stdout}, indent=2))
    return out, report


if __name__ == "__main__":
    build()
