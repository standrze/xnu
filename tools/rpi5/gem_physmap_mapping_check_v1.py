# SPDX-License-Identifier: BSD-2-Clause
"""Strict corrected package intake plus the inherited bounded-capture contract."""
import hashlib
import json
from pathlib import Path
import types

from tools.rpi5 import check_gem_physmap_mapping_verification as package_check
from tools.rpi5 import gem_mapping_predicate_check_v3 as parent
from tools.rpi5 import gem_physmap_mapping_case_v1 as case

b = types.SimpleNamespace(
    PROFILE="bcm2712-gem-page-granular-mapping-verification-v1",
    retry=parent.b.retry,
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect(package, manifest_sha256, *_unused):
    package = Path(package).resolve()
    if sha(package / "manifest.json") != manifest_sha256:
        raise ValueError("Exact corrected manifest digest required")
    checked = package_check.check(package)
    manifest = json.loads((package / "manifest.json").read_text())
    marker = parent.b.retry.trial.marker(case.TAG)
    if (Path(package).resolve() != case.PACKAGE or
            manifest_sha256 != case.MANIFEST_SHA or
            manifest.get("tag") != case.TAG or
            manifest.get("trial_marker") != marker or
            checked["status"] != "pass" or
            checked["image_sha256"] != case.IMAGE_SHA or
            checked["maximum_page_table_bytes"] != 4243456):
        raise ValueError("Exact retained corrected physmap verification package required")
    return dict(
        profile=b.PROFILE,
        package=str(case.PACKAGE),
        manifest_sha256=case.MANIFEST_SHA,
        image_sha256=case.IMAGE_SHA,
        image_bytes=case.IMAGE_BYTES,
        kernel_sha256=checked["kernel_sha256"],
        package_checker_sha256=sha(package_check.__file__),
        tag=case.TAG,
        marker=marker,
        trial_marker=marker,
        bootargs=parent.b.retry.trial.BOOTARGS,
        page_granular_physmap=True,
        mapping_verification_only=True,
        mapping_success_reason=41,
        alias_rows=4,
        page_table_rows=1,
        allocation_bytes=32768,
        maximum_page_table_pages=259,
        maximum_page_table_bytes=4243456,
        preallocated_upper_pages=1,
        discard_before_route=True,
        packet_spans=0,
        bme=False,
        dma=False,
        irq=False,
        queues=False,
        packets=False,
        queue_publication=False,
        physical_execution_proven=False,
        hardware_execution=False,
        hardware_executed=False,
        automatic_watchdog_return_required=True,
        complete_capture_health_required=True,
    )

