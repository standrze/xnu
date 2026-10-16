#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Current488 to the self-contained mapping diagnostic and exact restoration."""
import hashlib
import json
from pathlib import Path
import types

_parent=Path(__file__).with_name('stage_gem_cpu_ring_retry_trial_v2.py')
_raw=_parent.read_bytes()
_PARENT_SHA='32bca55bffed390617fef31706ef66e0fd7f9ce0ae06ed02d283aca081fc980a'
if hashlib.sha256(_raw).hexdigest()!=_PARENT_SHA:raise ValueError('Frozen successor controller changed')
_text=_raw.decode()
for _old,_new in (
    ('stage_gem_cpu_ring_retry_trial_v2.py','stage_gem_mapping_predicate_trial_v3.py'),
    ('serial_gem_cpu_ring_retry_trial_v2.py','serial_gem_mapping_predicate_trial_v3.py'),
    ('gem_cpu_ring_retry_evidence_v2.py','gem_mapping_predicate_evidence_v3.py'),
    ('arm_gem_cpu_ring_retry_reboot_v2.py','arm_gem_mapping_predicate_reboot_v3.py'),
    ('serial_gem_cpu_ring_retry_trial_v2','serial_gem_mapping_predicate_trial_v3'),
    ('gem_cpu_ring_retry_evidence_v2','gem_mapping_predicate_evidence_v3'),
    ('arm_gem_cpu_ring_retry_reboot_v2','arm_gem_mapping_predicate_reboot_v3'),
    ('gem_cpu_ring_retry_media_v2','gem_mapping_predicate_media_v1'),
    ('gem_cpu_ring_retry_case_v1','gem_mapping_predicate_case_v1'),
    ('check_gem_cpu_ring_retry_trial','gem_mapping_predicate_check_v3'),
    ('gem_cpu_ring_retry_serial','gem_mapping_predicate_serial_v3'),
    ('gem_cpu_ring_retry_profile','gem_mapping_predicate_profile'),
    ('build_gem_cpu_ring_retry_trial','build_gem_mapping_predicate_trial'),
    ('test_gem_cpu_ring_retry_successor_transport_v2.py','test_gem_mapping_predicate_transport_v3.py'),
    ('gem-cpu-ring-retry-successor-three-target-controller-v2','gem-mapping-predicate-three-target-controller-v3'),
    ('gem-cpu-ring-retry-successor-three-target-v2','gem-mapping-predicate-three-target-v3'),
    ('gem-cpu-ring-retry-successor-independent-return-v2','gem-mapping-predicate-independent-return-v3'),
    ('rpi5-gem-cpu-ring-retry-successor-three-target-chain-v2','rpi5-gem-mapping-predicate-three-target-chain-v3'),
    ('gem-cpu-ring-retry-successor','gem-mapping-predicate-v3'),
    ('gem_cpu_ring_retry','gem_mapping_predicate'),
    ('ring-only retry successor','mapping-predicate v3'),
    ('gem-cpu-ring-retry-fixed53','gem-mapping-predicate-fixed54')):
    if _old not in _text:raise ValueError('Exact mapping controller derivation boundary changed: '+_old)
    _text=_text.replace(_old,_new)
_parent_main="if __name__=='__main__':raise SystemExit(main())"
if _text.count(_parent_main)!=2 or not _text.rstrip().endswith(_parent_main):
    raise ValueError('Successor controller main boundary changed')
_head,_tail=_text.rsplit(_parent_main,1)
_text=_head+"if False:raise SystemExit(main())"+_tail
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
__doc__=("One bounded mapping-predicate diagnostic, three guarded SD targets and zero UART TX. "
    "The exact current488 restoration is the only intake. Package/source/report and the "
    "self-contained remote namespace are audited before staging; unknown publication or reboot "
    "outcomes are never retried, and all three originals are explicitly restored.")
_mapping_prepare_install_base=_generated_prepare_install

for _name in ('inventory','PREPARED','PREPARED_PREFIX','return_positions','health'):
    if not hasattr(protocol,_name):setattr(protocol,_name,getattr(protocol.old,_name))

def transport():
    if __package__:
        from . import serial_gem_mapping_predicate_trial_v3
        from . import gem_mapping_predicate_evidence_v3
        from . import arm_gem_mapping_predicate_reboot_v3
    else:
        import serial_gem_mapping_predicate_trial_v3
        import gem_mapping_predicate_evidence_v3
        import arm_gem_mapping_predicate_reboot_v3
    return gem_mapping_predicate_evidence_v3

BASELINE=ROOT/'build/rpi5/gem-cpu-ring-retry-successor-restored-20261014'
BASELINE_SEAL='d3751ac4c8791613692471f7d65a0a9169a47a02d90d1cd15d4f5e7dd104f704'
BASELINE_PLAN='15726c9e86af5347642a58b2c6c5469f8dadd49e884812a4a9cd7a5197fb7400'
BASELINE_RESULT='aeba4a995433569b1dc0c32f5db40d96bec26251e06c38d19745ec22d0a9b1cb'
BASELINE_BOOT='42df0d0d-da35-442d-9514-d4f05bada5e7'
BASELINE_CATALOG=488
BASELINE_CATALOG_SHA='f0c29048e8227b9748aeab08286e01dd63a7cfc09bb5b43701df94fa8156ea1a'
CONTROLLER='gem-mapping-predicate-three-target-controller-v3'
DESCRIPTOR='gem-mapping-predicate-fixed54'
_SOURCE_EXPECTATIONS=None

def source_pins():
    global _SOURCE_EXPECTATIONS
    if _SOURCE_EXPECTATIONS is not None:
        if any(sha(n)!=h for n,h in _SOURCE_EXPECTATIONS.items()):raise ValueError('Mapping transport source changed after inventory')
        return dict(_SOURCE_EXPECTATIONS)
    names=('stage_gem_mapping_predicate_trial_v3.py','serial_gem_mapping_predicate_trial_v3.py',
        'gem_mapping_predicate_evidence_v3.py','arm_gem_mapping_predicate_reboot_v3.py',
        'gem_mapping_predicate_media_v1.py','gem_mapping_predicate_case_v1.py',
        'gem_mapping_predicate_check_v3.py','gem_mapping_predicate_serial_v3.py',
        'build_gem_mapping_predicate_trial.py','check_gem_mapping_predicate_trial.py',
        'gem_mapping_predicate_profile.py','remote_namespace_audit_v1.py',
        'qualify_gem_mapping_predicate_transport_v3.py',
        'tests/test_gem_mapping_predicate_transport_v3.py')
    if __package__:
        from . import stage_gem_cpu_ring_retry_trial_v2 as baseline_stage
    else:
        import stage_gem_cpu_ring_retry_trial_v2 as baseline_stage
    _SOURCE_EXPECTATIONS=(preceding.source_pins()|baseline_stage.source_pins()|engine.source_pins()|{str(_parent):_PARENT_SHA}|
        {str(ROOT/'tools/rpi5'/name):sha(ROOT/'tools/rpi5'/name) for name in names}|
        {str(CONFIG):engine.TRIAL_CONFIG_SHA,str(GOOD['config.txt'][0]):engine.ORIGINAL_CONFIG_SHA,
         str(case.REPORT):case.REPORT_SHA,str(PACKAGE/'manifest.json'):MANIFEST_SHA})
    if any(sha(n)!=h for n,h in _SOURCE_EXPECTATIONS.items()):raise ValueError('Mapping source inventory differs')
    return dict(_SOURCE_EXPECTATIONS)

def valid_report(report):
    expected=checker.inspect(PACKAGE,MANIFEST_SHA)
    if case.FROZEN is not True or sha(case.REPORT)!=case.REPORT_SHA or not engine.same(report,expected):
        raise ValueError('Exact separately retained mapping diagnostic report required')
    required=dict(profile=checker.b.PROFILE,package=str(PACKAGE),manifest_sha256=MANIFEST_SHA,
        image_sha256=IMAGE_SHA,image_bytes=case.IMAGE_BYTES,tag=TAG,
        marker=checker.b.retry.trial.marker(TAG),trial_marker=checker.b.retry.trial.marker(TAG),
        bootargs=checker.b.retry.trial.BOOTARGS,mapping_predicate_diagnostic=True,
        mapping_steps=41,allocation_bytes=32768,packet_spans=0,bme=False,dma=False,
        irq=False,queues=False,queue_publication=False,physical_execution_proven=False,
        automatic_watchdog_return_required=True,complete_capture_health_required=True)
    if any(not engine.same(report.get(k),v) for k,v in required.items()):
        raise ValueError('Exact54-row passive mapping diagnostic required')
    return True

def baseline(directory,seal_sha,plan_sha):
    if (Path(directory).resolve(),seal_sha,plan_sha)!=(BASELINE,BASELINE_SEAL,BASELINE_PLAN):
        raise ValueError('Exact current488 restoration required')
    if sha(BASELINE/'result.json')!=BASELINE_RESULT:raise ValueError('Current488 result changed')
    if __package__:
        from . import stage_gem_cpu_ring_retry_trial_v2 as baseline_stage
    else:
        import stage_gem_cpu_ring_retry_trial_v2 as baseline_stage
    accepted=baseline_stage.restoration(directory,seal_sha,plan_sha)
    publication=accepted['result']['publication'];files=publication['protected_files_sha256']
    if (publication['identity']['boot_id']!=BASELINE_BOOT or len(accepted['result']['next_catalog'])!=BASELINE_CATALOG or
        accepted['result']['next_catalog_sha256']!=BASELINE_CATALOG_SHA or
        any(files.get(name)!=value[1] for name,value in GOOD.items())):
        raise ValueError('Current488 normal config/firmware/loader restoration required')
    return accepted

def prepare_install(directory,prior_seal,prior_plan,boot):
    if boot!=BASELINE_BOOT:raise ValueError('Exact current Linux boot witness required')
    return _mapping_prepare_install_base(directory,prior_seal,prior_plan,boot)

_scope=globals()
for _name in ('sealed_operation','load_installation','prepare_restore','restoration','dispatch','launch','replay','main'):
    _fn=_scope[_name]
    if hasattr(_fn,'__code__'):_scope[_name]=types.FunctionType(_fn.__code__,_scope,argdefs=_fn.__defaults__)

if __name__=='__main__':raise SystemExit(main())
