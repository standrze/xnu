# SPDX-License-Identifier: BSD-2-Clause
"""Current466 intake, strict five-command receiver and pair restoration."""
import contextlib,copy,io,json,os,struct,subprocess,tempfile,types,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from tools.rpi5 import stage_console_records_trial_v1 as stage
from tools.rpi5 import serial_console_records_trial_v1 as recorder
from tools.rpi5 import console_records_evidence_v1 as evidence
from tools.rpi5 import console_records_serial as protocol
from tools.rpi5.tests import test_display_xnu_serial as old_serial
from tools.rpi5.tests import test_restart_late_transport as old
from tools.rpi5.tests.test_restart_diagnostic_serial import trace

ROOT=stage.ROOT;DEVICE=old.DEVICE;BOOT=stage.BASELINE_BOOT;RETURN='22222222-2222-2222-2222-222222222222'
response=old_serial.response
def boot(report):
    return (old_serial.boot(report).replace(old_serial.p.ROOT_READY,protocol.ROOT_READY)+b'\r\n'+protocol.READY+b'\r\n'+
        protocol.INIT_READY+b'\r\n'+protocol.zsh.READY+b'\r\nxnu:/# ')
runtime=types.FunctionType(old.RestartLateTransportTests.runtime.__code__,globals(),
    argdefs=old.RestartLateTransportTests.runtime.__defaults__)

class ConsoleRecordsTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads(stage.REPORT.read_text());cls.manifest=json.loads((stage.PACKAGE/'manifest.json').read_text())
    def context(self):
        pins=stage.source_pins()|{str(stage.PACKAGE/'manifest.json'):stage.MANIFEST_SHA}
        for key in ('inputs_sha256','headers_sha256','generated_sha256'):pins=stage.preceding.merge_pins(pins,self.manifest[key])
        accepted=stage.baseline(stage.BASELINE,stage.BASELINE_SEAL,stage.BASELINE_PLAN)
        binding=copy.deepcopy(accepted['plan']['media']['identity_binding'])
        installed=dict(directory=str(ROOT/'build/rpi5/offline-console-records'),checkpoint_sha256='1'*64,plan_sha256='2'*64,
            result_sha256='3'*64,preflight=self.report,loader_sha256=stage.IMAGE_SHA,
            config_sha256=stage.engine.TRIAL_CONFIG_SHA,original_linux_boot_id=BOOT)
        return dict(installed=installed,evidence=pins,plan={'media':{'host':stage.HOST,'linux_boot_id':BOOT,'identity_binding':binding}})
    def media(self):
        current={'bl31.bin':stage.engine.GOOD_FW_SHA}
        files=[dict(target='config.txt',candidate='candidate-config.txt',old_sha256=stage.engine.ORIGINAL_CONFIG_SHA,
            old_bytes=len(stage.engine.ORIGINAL_CONFIG),new_sha256=stage.engine.TRIAL_CONFIG_SHA,new_bytes=len(stage.engine.TRIAL_CONFIG)),
            dict(target='probe.bin',candidate='candidate-probe.bin',old_sha256=stage.GOOD['probe.bin'][1],old_bytes=stage.GOOD['probe.bin'][2],
                new_sha256=stage.IMAGE_SHA,new_bytes=stage.engine.IMAGE_BYTES)]
        return dict(profile=stage.engine.TRIAL,descriptor=stage.DESCRIPTOR,preflight=copy.deepcopy(self.report),files=files,
            protected_files=current,candidates={'config.txt':str(stage.CONFIG),'probe.bin':str(stage.PACKAGE/'probe.bin')})
    def test_exact_current466_intake_prepare_and_two_target_admission(self):
        accepted=stage.baseline(stage.BASELINE,stage.BASELINE_SEAL,stage.BASELINE_PLAN)
        self.assertEqual(len(accepted['result']['next_catalog']),466)
        self.assertEqual(accepted['result']['publication']['identity']['boot_id'],BOOT)
        for args in ((stage.BASELINE,'0'*64,stage.BASELINE_PLAN),(stage.BASELINE,stage.BASELINE_SEAL,'0'*64),
                (ROOT/'build/rpi5/restart-late-restored-20261014',stage.BASELINE_SEAL,stage.BASELINE_PLAN)):
            with self.assertRaises(ValueError):stage.baseline(*args)
        checkpoint,pin,metrics=stage.prepare_install(stage.BASELINE,stage.BASELINE_SEAL,stage.BASELINE_PLAN,BOOT)
        self.assertRegex(pin,r'^[0-9a-f]{64}$');self.assertEqual(metrics['full_audit_calls'],1)
        with patch.object(stage.checker,'inspect',side_effect=AssertionError('No package replay')):admitted=stage.admit(checkpoint)
        self.assertTrue(admitted['clean_pid1_reports_required']);self.assertTrue(admitted['clean_watchdog_readiness_required'])
        self.assertEqual([r['target'] for r in checkpoint['payload']['media_plan']['files']],['config.txt','probe.bin'])
        protected=checkpoint['payload']['media_plan']['protected_files']
        self.assertEqual(protected['bl31.bin'],stage.engine.GOOD_FW_SHA)
        self.assertNotIn('config.txt',protected);self.assertNotIn('probe.bin',protected)
        tag='0123456789abcdef0123456789abcdef';run=str(ROOT/'build/rpi5/offline-console-record-pair-run')
        plan,plan_pin=stage.engine.plan_from_seal(checkpoint,pin,stage.engine.TRIAL,tag,run,checkpoint['payload']['media_plan'])
        code=stage.engine.remote_source(checkpoint,pin,plan,plan_pin)
        compile(code,'<sealed-console-pair-remote>','exec')
        self.assertEqual([r['target'] for r in plan['media']['files']],['config.txt','probe.bin'])
        self.assertEqual(plan['media']['protected_files']['bl31.bin'],stage.engine.GOOD_FW_SHA)
        for boot_id in ('33333333-3333-3333-3333-333333333333',True):
            with self.assertRaises(ValueError):stage.prepare_install(stage.BASELINE,stage.BASELINE_SEAL,stage.BASELINE_PLAN,boot_id)
    def test_strict_clean_pid1_watchdog_and_restart_grammar(self):
        raw=boot(self.report);self.assertTrue(protocol.boot_ready(raw,self.report))
        for bad in (raw.replace(protocol.INIT_READY,b'MISSING'),raw.replace(protocol.WATCHDOG,b'MISSING'),
            raw.replace(protocol.INIT_READY,protocol.INIT_READY+b' CORRUPT'),
            raw.replace(protocol.WATCHDOG,protocol.WATCHDOG+b' PICOND:S1E0'),raw+(b'\n'+protocol.INIT_READY)*4):
            try:ready=protocol.boot_ready(bad,self.report)
            except ValueError:ready=False
            self.assertFalse(ready)
        n='D'+'a'*16
        observed=protocol.reboot_observation(trace(n),n,100,102)
        self.assertTrue(observed['ordered_real_reboot_path_observed']);self.assertTrue(observed['nominal_early_return'])
        for bad in (trace(n).replace(protocol.PRE_PREFIX,b'MISSING'),trace(n)+b'RPI5XNU:RESTART:RETURNED NO_RESET_PROVEN\n',
                trace(n)+b'panic(cpu0): bad\n'):
            with self.assertRaises(ValueError):protocol.reboot_observation(bad,n,100,102)
    def test_actual_five_commands_capture_and_independent_return(self):
        context=self.context()
        with tempfile.TemporaryDirectory(prefix='console-record-rx-',dir=ROOT/'build/rpi5') as name:
            directory=Path(name);directory.rmdir();rc,sent=runtime(self,context,directory)
            state,observed,_=evidence.captured(context,directory)
            self.assertEqual(rc,0,state.get('error'));self.assertTrue(observed['capture_valid']);self.assertEqual(len(state['exchanges']),4)
            self.assertTrue(sent.endswith((protocol.restart_command(state['nonce'])+'\n').encode()))
            self.assertTrue(observed['diagnostic']['ordered_real_reboot_path_observed'])
            expected=context['plan']['media']['identity_binding']['expected'];pins=evidence.source_pins(context)
            returned=dict(host=stage.HOST,boot_id=RETURN,identity=dict(identity=expected,boot_id=RETURN,hostname='kamidana'),
                root=expected['root'].split(),bootloader={'boot-mode':6,'partition':1,'tryboot':0},sd_partitions_unmounted=True,
                read_only=True,observed_utc='2026-10-14T20:10:00+00:00',installation=context['installed'],
                serial_sha256=state['serial_sha256'],return_source_sha256=pins)
            with patch.object(evidence.scope['subprocess'],'run',return_value=subprocess.CompletedProcess([],0,json.dumps(returned),'')):
                value=evidence.collect_return(context,directory)
            self.assertTrue(value['capture_valid']);self.assertEqual(evidence.load_return(context,directory)[1],RETURN)
            with self.assertRaises(ValueError):evidence.inspect_return(returned|{'boot_id':BOOT},context,observed)
    def test_receiver_faults_never_weaken_or_reboot_twice(self):
        context=self.context()
        for fault in ('missinginit','rebootecho','smcreturn','watchdog','tailpanic','initerror','late-fourth','late-corrupt'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(prefix='console-record-fault-',dir=ROOT/'build/rpi5') as name:
                directory=Path(name);directory.rmdir();rc,sent=runtime(self,context,directory,fault)
                _,observed,_=evidence.captured(context,directory);self.assertEqual(rc,1);self.assertFalse(observed['capture_valid'])
                self.assertLessEqual(sent.count((protocol.restart_command('D'+'0'*16)+'\n').encode()),1)
    def test_pair_restore_and_replay_require_exact_derived_receipt(self):
        checkpoint={'typed':'console-restore'}
        context={'plan':{'historical_catalog':[None]*466},'result':{'next_catalog':[None]*470}}
        returned={'capture_valid':True,'diagnostic':{'ordered_real_reboot_path_observed':True},'capture_error':None}
        restored={'checkpoint':checkpoint,'result':{'next_catalog':[None]*474,'publication':{'identity':{'boot_id':RETURN}}}}
        with patch.object(stage,'transport',return_value=evidence),patch.object(stage,'load_installation',return_value=context),\
            patch.object(evidence,'load_return',return_value=(returned,RETURN)),patch.object(stage,'prepare_restore',return_value=(checkpoint,'restore-seal',{})),\
            patch.object(stage,'restoration',return_value=restored),patch.object(subprocess,'run',side_effect=AssertionError('No hardware')):
            value=stage.replay('install','seal','plan','capture','restore','restore-seal','restore-plan')
        self.assertTrue(value['original_config_and_loader_restored']);self.assertTrue(value['normal_firmware_unchanged'])
        self.assertTrue(value['independent_normal_nvme_linux_return_verified']);self.assertEqual(value['historical_catalog_counts'],[466,470,474])
        self.assertFalse(value['visual_confirmation_required'])
        bad=copy.deepcopy(restored);bad['checkpoint']={'other':True}
        with patch.object(stage,'transport',return_value=evidence),patch.object(stage,'load_installation',return_value=context),\
            patch.object(evidence,'load_return',return_value=(returned,RETURN)),patch.object(stage,'prepare_restore',return_value=(checkpoint,'restore-seal',{})),\
            patch.object(stage,'restoration',return_value=bad),self.assertRaises(ValueError):
            stage.replay('install','seal','plan','capture','restore','restore-seal','restore-plan')

if __name__=='__main__':unittest.main()
