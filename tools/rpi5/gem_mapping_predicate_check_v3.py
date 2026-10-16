# SPDX-License-Identifier: BSD-2-Clause
"""Strict mapping package intake plus the inherited bounded-capture contract."""
import copy
import json
from pathlib import Path
import types

from tools.rpi5 import build_gem_mapping_predicate_trial as build
from tools.rpi5 import check_gem_mapping_predicate_trial as package_check
from tools.rpi5 import gem_cpu_ring_retry_case_v1 as parent_case
from tools.rpi5 import gem_mapping_predicate_case_v1 as case

b=types.SimpleNamespace(PROFILE=build.PROFILE,
    retry=types.SimpleNamespace(trial=build.profile.parent.trial))

def inspect(package,manifest_sha256,*_unused):
    """Return a deterministic full report without weakening package checking."""
    checked=package_check.inspect(package,manifest_sha256)
    if (Path(package).resolve()!=case.PACKAGE or manifest_sha256!=case.MANIFEST_SHA or
        package_check.b.sha(case.REPORT)!=case.REPORT_SHA or
        checked!=json.loads(case.REPORT.read_text())):
        raise ValueError('Exact retained mapping predicate package/report required')
    parent=json.loads(parent_case.REPORT.read_text())
    marker=build.profile.parent.trial.marker(case.TAG)
    report=copy.deepcopy(parent)
    report.update(checked)
    report.update(image_bytes=case.IMAGE_BYTES,tag=case.TAG,marker=marker,
        trial_marker=marker,bootargs=build.profile.parent.trial.BOOTARGS,
        qualification=str(case.QUALIFICATION),qualification_sha256=case.QUALIFICATION_SHA,
        mapping_predicate_diagnostic=True,mapping_steps=41,
        automatic_watchdog_return_required=True,complete_capture_health_required=True,
        physical_execution_proven=False,hardware_execution=False,hardware_executed=False,
        queue_publication=False,bme=False,dma=False,irq=False,queues=False,
        packets=False,packet_spans=0,preferred_ram_route_only=True)
    markers=list(report['boot_markers']);markers[0]=marker;report['boot_markers']=markers
    return report
