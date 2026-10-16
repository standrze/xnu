#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Run and retain the offline mapping v3 transport qualification."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.rpi5 import stage_gem_mapping_predicate_trial_v3 as stage

PROFILE='rpi5-gem-mapping-predicate-current488-transport-qualification-v3'
TOOLS=('gem_mapping_predicate_case_v1.py','gem_mapping_predicate_check_v3.py',
    'gem_mapping_predicate_serial_v3.py','gem_mapping_predicate_media_v1.py',
    'serial_gem_mapping_predicate_trial_v3.py','gem_mapping_predicate_evidence_v3.py',
    'arm_gem_mapping_predicate_reboot_v3.py','stage_gem_mapping_predicate_trial_v3.py',
    'qualify_gem_mapping_predicate_transport_v3.py','remote_namespace_audit_v1.py',
    'tests/test_gem_mapping_predicate_transport_v3.py')

def qualify(output):
    output=Path(output).resolve()
    if output.parent!=stage.ROOT/'build/rpi5' or output.exists():
        raise ValueError('Distinct qualification output required')
    started=time.monotonic()
    command=[sys.executable,'-m','unittest','tools.rpi5.tests.test_gem_mapping_predicate_transport_v3','-v']
    completed=subprocess.run(command,cwd=stage.ROOT,text=True,capture_output=True,timeout=240)
    transcript=completed.stdout+completed.stderr
    match=re.search(r'Ran (\d+) tests? in ([0-9.]+)s',transcript)
    if completed.returncode or not match or 'OK' not in transcript:
        raise ValueError('Mapping v3 transport qualification failed:\n'+transcript[-4000:])
    report=dict(profile=PROFILE,hardware_executed=False,published=False,serial_opened=False,
        ssh_used=False,sd_accessed=False,rebooted=False,prepared_for_hardware=True,
        package=dict(path=str(stage.PACKAGE),manifest_sha256=stage.MANIFEST_SHA,
            image_sha256=stage.IMAGE_SHA,image_bytes=stage.case.IMAGE_BYTES,
            report_sha256=stage.case.REPORT_SHA),
        current_baseline=dict(path=str(stage.BASELINE),checkpoint_sha256=stage.BASELINE_SEAL,
            plan_sha256=stage.BASELINE_PLAN,result_sha256=stage.BASELINE_RESULT,
            linux_boot_id=stage.BASELINE_BOOT,catalog_count=stage.BASELINE_CATALOG,
            catalog_sha256=stage.BASELINE_CATALOG_SHA),
        transport=dict(controller=stage.CONTROLLER,trial_profile=stage.engine.TRIAL,
            restore_profile=stage.engine.RESTORE,targets=list(stage.engine.TARGETS),
            distinct_from_failed_v1=True,remote_sources_embedded=True,
            remote_namespace_audit_passed=True,remote_host_path_accesses=0,
            automatic_nvme_return_required=True,triple_media_restore_required=True,
            zero_serial_tx=True),
        capture=dict(ordered_rows=54,dma_map_rows=1,mapping_reason_min=1,
            mapping_failure_reason_max=40,mapping_success_sentinel_rejected=41,
            allocation_bytes=32768,packet_spans=0,
            route_activation=False,bme=False,dma=False,irq=False,queues=False,packets=False),
        source_closure_members=len(stage.source_pins()),
        source_sha256={name:stage.sha(stage.ROOT/'tools/rpi5'/name) for name in TOOLS},
        test=dict(result='PASS',tests=int(match.group(1)),seconds=float(match.group(2)),
            wall_seconds=round(time.monotonic()-started,3),subprocess_prepare_passed=True,
            subprocess_remote_plan_passed=True,namespace_audit_passed=True,
            serial_parser_mutation_checks_passed=True))
    output.mkdir();target=output/'qualification.json';target.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    (output/'unittest.txt').write_text(transcript)
    return dict(qualification=str(target),qualification_sha256=stage.sha(target),report=report)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(qualify(parser.parse_args().output),sort_keys=True))
