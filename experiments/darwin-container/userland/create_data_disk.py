#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Create and format a NEW private regular RAW workload image, never existing media."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--size-mib", type=int, default=128)
    args = parser.parse_args()
    if not 64 <= args.size_mib <= 4096:
        parser.error("size must be 64..4096 MiB")
    output = args.output.absolute()
    if not output.parent.is_dir() or output.parent.is_symlink() or str(output).startswith("/dev/"):
        parser.error("output must be a new regular image in an existing local directory, not a device")
    fd = os.open(output, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    # hdiutil formats only its freshly created temporary image. newfs_hfs itself
    # accepts device names, not regular files; never point it at arbitrary /dev media.
    # Host tools only: no installed macOS runtime binary enters the guest.
    with os.fdopen(fd, "wb") as destination:
        with tempfile.TemporaryDirectory(prefix="darwin-new-hfs-", dir="/private/tmp") as directory:
            source = Path(directory) / "data.cdr"
            command = ["/usr/bin/hdiutil", "create", "-size", f"{args.size_mib}m", "-type", "UDTO",
                       "-layout", "NONE", "-fs", "Journaled HFS+", "-volname", "DarwinWorkload", str(source)]
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(f"formatting NEW image failed; partial file retained at {output}: {result.stderr}")
            if source.stat().st_size != args.size_mib * 1024 * 1024:
                raise RuntimeError("formatted RAW image has an unexpected size")
            with source.open("rb") as image:
                image.seek(1024)
                if image.read(2) not in (b"H+", b"HX"):
                    raise RuntimeError("formatted whole-volume image is not RAW HFS+")
                image.seek(0)
                shutil.copyfileobj(image, destination)
        destination.flush()
        os.fsync(destination.fileno())
    with output.open("rb") as image:
        image.seek(1024)
        signature = image.read(2)
    if signature not in (b"H+", b"HX"):
        raise RuntimeError("new image does not contain an HFS+ volume header")
    manifest = {"format": "RAW, whole-volume journaled HFS+", "bytes": output.stat().st_size,
        "formatter": command, "formatter_stdout": result.stdout,
        "formatter_sha256": hashlib.sha256(Path(command[0]).read_bytes()).hexdigest(),
        "image_sha256_at_creation": hashlib.sha256(output.read_bytes()).hexdigest(),
        "scope": "host formatting only; guest mount/durability not proven"}
    output.with_suffix(output.suffix + ".creation.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"image": str(output), "bytes": manifest["bytes"], "format": manifest["format"]}))


if __name__ == "__main__":
    main()
