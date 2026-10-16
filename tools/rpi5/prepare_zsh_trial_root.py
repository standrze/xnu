#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Prepare a new Pi RAM root without replacing its proven init/recovery shell."""
import argparse
import hashlib
import json
from pathlib import Path

try:
    from .check_zsh_ramroot import check, checked_hash, read_bounded
    from .ramroot import build, inspect
except ImportError:
    from check_zsh_ramroot import check, checked_hash, read_bounded
    from ramroot import build, inspect

SMOKE = b'''print -r -- "RPI5XNU:ZSH:VERSION:$ZSH_VERSION"
typeset -a ports=(pi xnu)
print -r -- "RPI5XNU:ZSH:BUILTIN:$((6*7)):${ports[2]}"
/bin/echo RPI5XNU:ZSH:EXTERNAL_EXEC || exit 126
print -r -- RPI5XNU:ZSH:SMOKE_DONE
'''


def files_from(image):
    report = inspect(image)
    return {entry["path"]: (image[entry["offset"]:entry["offset"] + entry["size"]], entry["mode"])
            for entry in report["entries"] if entry["type"] == "file"}


def prepare(pi_root, capsule_root, zsh, pi_pin, capsule_pin, zsh_pin):
    checked_hash(pi_root, pi_pin, "Pi recovery RAM root")
    check(capsule_root, zsh, capsule_pin, zsh_pin)
    original, capsule = files_from(pi_root), files_from(capsule_root)
    for path in ("/sbin/launchd", "/bin/sh", "/bin/echo", "/bin/uname"):
        if path not in original or original[path][1] != 0o555:
            raise ValueError("missing executable Pi recovery component: " + path)
    terminfo = capsule.get("/etc/terminfo/64/dumb")
    if terminfo is None or terminfo[1] != 0o444 or not terminfo[0]:
        raise ValueError("missing read-only dumb terminal capability file")
    additions = {"/bin/zsh": (zsh, 0o555),
                 "/etc/terminfo/64/dumb": terminfo,
                 "/etc/zsh-smoke.zsh": (SMOKE, 0o444)}
    if set(original) & set(additions):
        raise ValueError("trial additions would replace existing Pi files")
    image, layout = build({**original, **additions})
    actual = files_from(image)
    if any(actual[path] != record for path, record in original.items()):
        raise ValueError("Pi recovery file or mode changed")
    report = {"schema_version": 1, "scope": "unstaged RAM-root preparation only",
              "pi_root_sha256": pi_pin, "capsule_root_sha256": capsule_pin,
              "zsh_sha256": zsh_pin, "output_sha256": layout["sha256"],
              "output_bytes": len(image), "output_nodes": len(layout["entries"]),
              "preserved_files_sha256": {path: hashlib.sha256(data).hexdigest()
                                         for path, (data, _) in original.items()},
              "added_files_sha256": {path: hashlib.sha256(data).hexdigest()
                                     for path, (data, _) in additions.items()},
              "default_init_and_shell_unchanged": True,
              "vm_init_or_poweroff_imported": False,
              "pi_executed": False, "isa_and_abi_compatibility_proven": False,
              "boot_package_preflight_passed": False, "sd_actions": 0,
              "serial_actions": 0, "reboots": 0,
              "next": "Close Pi ABI/ISA review and a distinct recovery-backed boot/serial trial"}
    return image, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pi-root", "capsule-root", "zsh"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True, help="Must not exist")
    args = parser.parse_args()
    paths = {name: getattr(args, name) for name in ("pi_root", "capsule_root", "zsh")}
    inputs = {name: read_bounded(path) for name, path in paths.items()}
    image, report = prepare(inputs["pi_root"], inputs["capsule_root"], inputs["zsh"],
                            args.pi_root_sha256, args.capsule_root_sha256, args.zsh_sha256)
    for name, path in paths.items():
        if read_bounded(path) != inputs[name]:
            raise ValueError("input changed during preparation: " + name)
    report["inputs"] = {name: str(path.resolve()) for name, path in paths.items()}
    report["builder_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / "ramdisk.bin").open("xb") as output:
        output.write(image)
    with (args.output_dir / "manifest.json").open("x") as output:
        json.dump(report, output, indent=2, sort_keys=True)
        output.write("\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
