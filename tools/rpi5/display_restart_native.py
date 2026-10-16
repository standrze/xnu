# SPDX-License-Identifier: BSD-2-Clause
"""Real loader C audit using an exact temporary view of the new image bytes."""
import json
from pathlib import Path
import tempfile
from . import root_capacity_native as native
from . import check_display_restart as check

def inspect(package):
    package=Path(package).resolve();report=check.inspect(package)
    with tempfile.TemporaryDirectory(prefix='display-restart-native-') as directory:
        view=Path(directory)
        # Existing native checker requires its old filenames/metadata. These
        # are exact copies, not a separately built image or a relaxed parser.
        for source,target in (('probe.bin','probe.bin'),('display_restart.elf','probe.elf'),('payload.bin','payload.bin')):
            (view/target).write_bytes((package/source).read_bytes())
        (view/'manifest.json').write_text(json.dumps(dict(entry=0x9000000,embedded_init=check.b.rootfs.inspect((package/'ramdisk.bin').read_bytes()))))
        result=native.compare(package/'kernel.display-restart',view)
    return dict(package_manifest_sha256=report['manifest_sha256'],actual_loader_comparison=result,
        exact_same_image_bytes=True,temporary_filename_adapter_only=True,target_executed=False)
