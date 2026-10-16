# SPDX-License-Identifier: BSD-2-Clause
"""Current476, strict53-row, zero-TX and exact restoration transport tests."""
import contextlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import stage_gem_cpu_ring_retry_trial_v1 as stage
from tools.rpi5 import serial_gem_cpu_ring_retry_trial_v1 as recorder
from tools.rpi5 import gem_cpu_ring_retry_evidence_v1 as evidence
from tools.rpi5 import arm_gem_cpu_ring_retry_reboot_v1 as launcher
from tools.rpi5.tests.test_gem_cpu_ring_retry_serial import RetrySerialTests

class RetryTransportTests(unittest.TestCase):
    def fixture(self):return RetrySerialTests().fixture(json.loads(stage.REPORT.read_bytes()))
    def context(self):
        raw,report=self.fixture();installed=dict(directory=str(stage.ROOT/'build/rpi5/offline-ring-retry-native'),preflight=report,
            pair_sha256={'probe.bin':stage.IMAGE_SHA,'bl31.bin':stage.case.FIRMWARE_SHA},
            triple_sha256={'config.txt':stage.engine.TRIAL_CONFIG_SHA,'probe.bin':stage.IMAGE_SHA,'bl31.bin':stage.case.FIRMWARE_SHA},
            original_linux_boot_id=stage.BASELINE_BOOT)
        return raw,dict(installed=installed,descriptor=stage.get_descriptor(stage.DESCRIPTOR),evidence=stage.source_pins())
    def test_exact_report_package_sources_and_current476_baseline(self):
        stage.valid_report(json.loads(stage.REPORT.read_bytes()));pins=stage.source_pins()
        self.assertEqual(pins[str(stage.PACKAGE/'manifest.json')],stage.MANIFEST_SHA)
        self.assertEqual(stage.sha(stage.PACKAGE/'probe.bin'),stage.IMAGE_SHA)
        with patch.object(subprocess,'run',side_effect=AssertionError('No compiler/SSH/hardware')):
            accepted=stage.baseline(stage.BASELINE,stage.BASELINE_SEAL,stage.BASELINE_PLAN)
        self.assertEqual(len(accepted['result']['next_catalog']),476)
        self.assertEqual(accepted['result']['publication']['identity']['boot_id'],stage.BASELINE_BOOT)
        for bad in ((stage.BASELINE,'0'*64,stage.BASELINE_PLAN),(stage.BASELINE,stage.BASELINE_SEAL,'0'*64)):
            with self.assertRaises(ValueError):stage.baseline(*bad)
        with self.assertRaises(ValueError):stage.prepare_install(stage.BASELINE,stage.BASELINE_SEAL,stage.BASELINE_PLAN,'0'*36)
    def test_fresh_process_cli_help_and_local_prepare_stop_before_hardware(self):
        command=[__import__('sys').executable,str(Path(stage.__file__).resolve())]
        help_run=subprocess.run(command+['--help'],cwd=stage.ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(help_run.returncode,0,help_run.stderr)
        self.assertIn('{prepare,publish,launch,return,restore,replay}',help_run.stdout)
        with tempfile.TemporaryDirectory(prefix='ring-retry-cli-',dir=stage.ROOT/'build/rpi5') as name:
            output=Path(name);output.rmdir()
            prepared=subprocess.run(command+['prepare','--baseline',str(stage.BASELINE),
                '--prior-seal-sha256',stage.BASELINE_SEAL,'--prior-plan-sha256',stage.BASELINE_PLAN,
                '--linux-boot-id',stage.BASELINE_BOOT,'--output',str(output)],cwd=stage.ROOT,
                text=True,capture_output=True,timeout=120)
            self.assertEqual(prepared.returncode,0,prepared.stderr)
            result=json.loads(prepared.stdout)
            self.assertEqual(result['status'],'prepared_only')
            self.assertEqual(Path(result['output']),output.resolve())
            self.assertTrue((output/'checkpoint.json').is_file())
            self.assertTrue((output/'metrics.json').is_file())
            self.assertFalse((output/'dispatch-intent.json').exists())
    def test_byte_only_recorder_admission_and_three_exact_targets(self):
        report=json.loads(stage.REPORT.read_bytes())
        media=dict(profile=stage.engine.TRIAL,descriptor=stage.DESCRIPTOR,preflight=report,files=[],
            protected_files={stage.engine.original.REUSED_ZSH_BACKUP:stage.engine.original.GOOD_ZSH_SHA})
        new={'config.txt':(stage.engine.TRIAL_CONFIG_SHA,len(stage.engine.TRIAL_CONFIG)),
            'bl31.bin':(stage.case.FIRMWARE_SHA,stage.case.FIRMWARE_BYTES),'probe.bin':(stage.IMAGE_SHA,stage.engine.IMAGE_BYTES)}
        for name,(_,digest,size) in stage.GOOD.items():
            h,n=new[name];media['files'].append(dict(target=name,candidate='candidate-'+name,
                old_sha256=digest,old_bytes=size,new_sha256=h,new_bytes=n))
        checkpoint=dict(payload={'media_plan':media},evidence_sha256=stage.source_pins())
        with patch.object(stage.checker,'inspect',side_effect=AssertionError('No package replay')),patch.object(subprocess,'run',side_effect=AssertionError('No process')):
            admitted=stage.admit(checkpoint)
        self.assertTrue(admitted['modem_gate_bound_before_arm']);self.assertEqual(admitted['transmitted_bytes'],0)
        self.assertEqual([r['target'] for r in media['files']],list(stage.engine.TARGETS))
        bad=json.loads(json.dumps(checkpoint));bad['evidence_sha256'].pop(str(Path(stage.__file__).resolve()))
        with self.assertRaises(ValueError):stage.admit(bad)
    def test_strict53_capture_and_zero_tx_native_receiver(self):
        raw,context=self.context();parts=raw.splitlines(keepends=True)
        with tempfile.TemporaryDirectory(prefix='ring-retry-rx-',dir=stage.ROOT/'build/rpi5') as name,tempfile.TemporaryFile() as uart:
            output=Path(name);output.rmdir();fn=recorder.bindings(context);g=fn.__globals__;original_open=os.open
            required=recorder.termios.TIOCM_DTR|recorder.termios.TIOCM_RTS
            with patch.object(g['lease'],'hold',return_value=contextlib.nullcontext()), \
                patch.object(g['subprocess'],'run',return_value=subprocess.CompletedProcess([],1,'','')), \
                patch.object(g['os'],'open',side_effect=lambda p,*a,**k:os.dup(uart.fileno()) if p=='/dev/cu.usbmodemTEST' else original_open(p,*a,**k)), \
                patch.object(g['os'],'read',side_effect=lambda *_:parts.pop(0)), \
                patch.object(g['os'],'write',side_effect=AssertionError('No UART TX')), \
                patch.object(g['fcntl'],'ioctl',return_value=struct.pack('=I',required)), \
                patch.object(g['termios'],'tcgetattr',side_effect=lambda _:[0,0,0,0,0,0,[0]*32]), \
                patch.object(g['termios'],'tcsetattr'),patch.object(g['termios'],'tcflush'), \
                patch.object(g['select'],'select',side_effect=lambda fd,*_:(fd,[],[])), \
                contextlib.redirect_stdout(__import__('io').StringIO()):
                self.assertEqual(fn(['/dev/cu.usbmodemTEST',str(output),'--installation',context['installed']['directory'],'--seconds','600']),0)
            state,observed,_=evidence.captured(context,output)
            self.assertEqual(state['transmitted_bytes'],0);self.assertEqual(observed['diagnostic']['observed_field_rows'],53)
            self.assertEqual(observed['diagnostic']['preparation'],dict(step=17,error=0,bytes=32768,packets=0))
            self.assertTrue(observed['diagnostic']['automatic_watchdog_return_observed'])
            self.assertEqual((observed['diagnostic']['descriptor_writes'],observed['diagnostic']['descriptor_readbacks'],observed['diagnostic']['packet_spans']),(640,640,0))
    def test_recorder_launcher_namespaces_and_chain_replay(self):
        self.assertIs(recorder.bindings.__code__,recorder.original.bindings.__code__)
        self.assertIs(recorder.main.__globals__['stage'],recorder.stage);self.assertIs(evidence.captured.__globals__['stage'],evidence.stage)
        self.assertIs(launcher.launch.__code__,stage.publisher.launch.__code__)
        checkpoint={'typed':'retry-restoration'};context={'plan':{'historical_catalog':[None]*476},'result':{'next_catalog':[None]*482}}
        returned={'capture_valid':True,'diagnostic':{'cpu_ring_retry_trial_pass':True},'capture_error':None}
        restored={'checkpoint':checkpoint,'result':{'next_catalog':[None]*488,'publication':{'identity':{'boot_id':'retry-return'}}}}
        with patch.object(stage,'transport',return_value=evidence), \
            patch.object(stage,'load_installation',return_value=context), \
            patch.object(evidence,'load_return',return_value=(returned,'retry-return')), \
            patch.object(stage,'prepare_restore',return_value=(checkpoint,'restore-seal',{})), \
            patch.object(stage,'restoration',return_value=restored), \
            patch.object(subprocess,'run',side_effect=AssertionError('No process/hardware')):
            value=stage.replay('install','seal','plan','capture','restore','restore-seal','restore-plan')
        self.assertEqual(value['historical_catalog_counts'],[476,482,488]);self.assertTrue(value['original_config_firmware_and_loader_restored'])
        self.assertTrue(value['normal_firmware_restored']);self.assertTrue(value['independent_normal_nvme_linux_return_verified'])

if __name__=='__main__':unittest.main()
