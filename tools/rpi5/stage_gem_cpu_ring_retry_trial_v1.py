#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Current476 -> sealed ring-only retry -> exact three-target restoration.

This is a software-only controller definition.  Importing it never prepares,
publishes, opens serial, connects over SSH, reboots, or accesses an SD card.
"""
import hashlib
import json
from pathlib import Path
_parent=Path(__file__).with_name('stage_gem_cpu_batch_trial_v1.py');_raw=_parent.read_bytes()
_PARENT_SHA='56d1d6a9f03cb66621c86d8de43f7c23a667faaf133e3f3b071698302a3a8789'
if hashlib.sha256(_raw).hexdigest()!=_PARENT_SHA:raise ValueError('Frozen three-target controller changed')
_text=_raw.decode()
for _old,_new in (('stage_restart_late_trial as preceding','stage_console_records_trial_v1 as preceding'),
    ('gem_cpu_batch','gem_cpu_ring_retry'),('gem-cpu-batch','gem-cpu-ring-retry'),
    ('CPU-batch','ring-only retry'),('gem_dma_batch_serial','gem_cpu_ring_retry_serial'),
    ('check_gem_dma_batch_trial','check_gem_cpu_ring_retry_trial'),
    ('.b.profile','.b.retry.trial'),('fixed52','fixed53')):
    if _old not in _text:raise ValueError('Exact controller derivation boundary changed: '+_old)
    _text=_text.replace(_old,_new)
# Direct execution gives this wrapper ``__name__ == '__main__'``.  The frozen
# controller must be loaded as a library first; otherwise its own entry point
# runs before the retry-specific source closure and baseline are installed.
_parent_main="if __name__=='__main__':raise SystemExit(main())"
if _text.count(_parent_main)!=1:raise ValueError('Frozen controller main boundary changed')
_text=_text.replace(_parent_main,"if False:raise SystemExit(main())",1)
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
# The receive-only transport needs the unchanged bounded row inventory helper;
# semantic acceptance remains the strict retry parser above.
for _name in ('inventory','PREPARED','PREPARED_PREFIX','return_positions','health'):
    if not hasattr(protocol,_name):setattr(protocol,_name,getattr(protocol.old,_name))

BASELINE=ROOT/'build/rpi5/console-records-restored-20261014'
BASELINE_SEAL='17dfae2197f4c3a148b5685fb341a5fbb5c5ab8c9b54903005c21cdb644f847f'
BASELINE_PLAN='0dcd6eced552fd60a53793117b742c40b22619db82398714c131b181a97a03b1'
BASELINE_RESULT='9659258ab80063e2e8136c646cdfda79c908e1fc14f5ead1926bbc8fede0190e'
BASELINE_BOOT='7a4004bf-b0eb-4b89-9b70-b8c9f1db12b6'
BASELINE_CATALOG=476
CONTROLLER='gem-cpu-ring-retry-three-target-controller-v1'
DESCRIPTOR='gem-cpu-ring-retry-fixed53'
_generated_prepare_install=prepare_install
_generated_source_pins=source_pins
_SOURCE_EXPECTATIONS=None

def source_pins():
    global _SOURCE_EXPECTATIONS
    if _SOURCE_EXPECTATIONS is not None:
        if any(sha(n)!=h for n,h in _SOURCE_EXPECTATIONS.items()):raise ValueError('Retry transport source changed after inventory')
        return dict(_SOURCE_EXPECTATIONS)
    names=('stage_gem_cpu_ring_retry_trial_v1.py','serial_gem_cpu_ring_retry_trial_v1.py',
        'gem_cpu_ring_retry_evidence_v1.py','arm_gem_cpu_ring_retry_reboot_v1.py',
        'gem_cpu_ring_retry_media_v1.py','gem_cpu_ring_retry_case_v1.py',
        'build_gem_cpu_ring_retry_trial.py','check_gem_cpu_ring_retry_trial.py',
        'qualify_gem_cpu_ring_retry_trial.py','gem_cpu_ring_retry_completeness_v1.py',
        'gem_cpu_ring_retry_serial.py','gem_cpu_ring_retry_profile.py','gem_dma_batch_contract.py',
        'tests/test_gem_cpu_ring_retry_transport_v1.py','tests/test_gem_cpu_ring_retry_media_v1.py')
    _SOURCE_EXPECTATIONS=preceding.source_pins()|engine.source_pins()|qualification_pins()|{
        str(_parent):_PARENT_SHA}|{str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}|{
        str(CONFIG):engine.TRIAL_CONFIG_SHA,str(GOOD['config.txt'][0]):engine.ORIGINAL_CONFIG_SHA,
        str(REPORT):REPORT_SHA,str(case.QUALIFICATION):case.QUALIFICATION_SHA}
    if any(sha(n)!=h for n,h in _SOURCE_EXPECTATIONS.items()):raise ValueError('Retry source inventory differs')
    return dict(_SOURCE_EXPECTATIONS)

def valid_report(report):
    if case.FROZEN is not True or sha(REPORT)!=REPORT_SHA or not engine.same(report,json.loads(REPORT.read_text())):raise ValueError('Exact retained retry report required')
    expected=dict(profile=checker.b.PROFILE,package=str(PACKAGE),manifest_sha256=MANIFEST_SHA,image_sha256=IMAGE_SHA,
        image_bytes=engine.IMAGE_BYTES,tag=TAG,marker=checker.b.retry.trial.marker(TAG),trial_marker=checker.b.retry.trial.marker(TAG),
        bootargs=checker.b.retry.trial.BOOTARGS,qualification_sha256='3461e0c10d4bcea8ba5a725f2abc1df57c0b4763896e9a572555c6885fbc92c7',
        target_stack_qualification_sha256=case.QUALIFICATION_SHA,software_trial_qualified=True,physical_execution_proven=False,
        allocation_bytes=32768,preparation_steps=17,packet_spans=0,expected_writes=640,expected_readbacks=640,
        preferred_ram_route_only=True,bme=False,dma=False,irq=False,queues=False,packets=False,
        complete_capture_health_required=True,automatic_watchdog_return_required=True)
    if any(not engine.same(report.get(k),v) for k,v in expected.items()):raise ValueError('Exact53-row qualified retry report required')
    stack=report.get('target_stack',{})
    if (stack.get('target_stack_receipts_bound') is not True or stack.get('whole_kernel_stack_proven') is not False or
        stack.get('compiler_replayed') is not False or stack.get('hardware_executed') is not False):raise ValueError('Exact retry target-stack receipts required')
    return True

def baseline(directory,seal_sha,plan_sha):
    if (Path(directory).resolve(),seal_sha,plan_sha)!=(BASELINE,BASELINE_SEAL,BASELINE_PLAN):raise ValueError('Exact current476 console restoration required')
    if sha(BASELINE/'result.json')!=BASELINE_RESULT:raise ValueError('Current476 result changed')
    accepted=preceding.restoration(directory,seal_sha,plan_sha);publication=accepted['result']['publication']
    files=publication['protected_files_sha256']
    if (publication['identity']['boot_id']!=BASELINE_BOOT or len(accepted['result']['next_catalog'])!=BASELINE_CATALOG or
        any(files.get(n)!=v[1] for n,v in GOOD.items())):raise ValueError('Current476 normal config/firmware/loader restoration required')
    return accepted

def prepare_install(directory,prior_seal,prior_plan,boot):
    if boot!=BASELINE_BOOT:raise ValueError('Exact current Linux boot witness required')
    return _generated_prepare_install(directory,prior_seal,prior_plan,boot)

# Rebind every derived controller function that consults globals at call time.
# The generated implementations retain their original code objects while
# resolving these strict current-baseline/report/source functions.
_scope=globals()
for _name in ('sealed_operation','load_installation','prepare_restore','restoration','dispatch','launch','replay','main'):
    _fn=_scope[_name]
    if hasattr(_fn,'__code__'):_scope[_name]=types.FunctionType(_fn.__code__,_scope,argdefs=_fn.__defaults__)

if __name__=='__main__':raise SystemExit(main())
