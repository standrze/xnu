# SPDX-License-Identifier: BSD-2-Clause
"""Actual five-command receiver/return/launcher under explicit I/O doubles.

The embedded CLI/SMC target is never executed on the host. The original first
four interactive responses and real host receiver code are reused unchanged.
"""
import contextlib
import copy
from datetime import datetime,timedelta,timezone
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import textwrap
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import stage_restart_diagnostic_trial as stage
from tools.rpi5 import serial_restart_diagnostic_trial as recorder
from tools.rpi5 import restart_diagnostic_evidence as evidence
from tools.rpi5 import arm_restart_diagnostic_trial as launcher
from tools.rpi5.tests import test_display_xnu_transport as old
from tools.rpi5.tests import test_display_xnu_serial as old_serial
from tools.rpi5.tests.test_restart_diagnostic_serial import trace
ROOT=stage.ROOT;DEVICE=old.DEVICE;BOOT=old.BOOT;RETURN=old.RETURN
response=old_serial.response

def boot(report):
    return old_serial.boot(report).replace(old_serial.p.ROOT_READY,recorder.protocol.ROOT_READY)+b'\r\n'+recorder.protocol.READY+b'\r\n'+recorder.protocol.zsh.READY+b'\r\nxnu:/# '

# Execute the exact previous actual-recorder double, extending only its fifth
# command input/response and its relative reboot-return timing/failure modes.
_runtime=textwrap.dedent(inspect.getsource(old.DisplayXNUTransportTests.runtime))
_changes=(
    ("if fault=='missingroot':initial=initial.replace(p.ROOT_READY,b'MISSING_ROOT')",
     "if fault=='missingroot':initial=initial.replace(p.ROOT_READY,b'MISSING_ROOT')\n    if fault=='missingrestart':initial=initial.replace(p.READY,b'MISSING_RESTART')"),
    ("name,expected,_,_=p.exchanges(n)[step[0]];self.assertEqual(line.decode().rstrip('\\n'),expected)",
     "name,expected,_,_=(p.exchanges(n)+[('restart',p.restart_command(n),[],p.PROMPT)])[step[0]];self.assertEqual(line.decode().rstrip('\\n'),expected)"),
    ("answer=response(name,n)","""answer=response(name,n) if name!='restart' else trace(n).split(p.BOOTSYS)[0]
            if name=='restart':
                if fault=='rebootecho':answer=expected.encode()+b'\\r\\n'
                if fault=='smcreturn':answer+=b'RPI5XNU:RESTART:RETURNED NO_RESET_PROVEN\\n'
                if fault=='snapshot':answer=answer.replace(b'COUNT=000e0000',b'COUNT=00000000')
                delay=16 if fault=='watchdog' else 2
                chunks[:]=[(clock[0]+delay,tail)]"""),
)
for _before,_after in _changes:
    if _runtime.count(_before)!=1:raise ValueError('Exact actual receiver-fixture seam changed')
    _runtime=_runtime.replace(_before,_after)
exec(compile(_runtime,__file__,'exec'),globals())
_dispatch_code=old.DisplayXNUTransportTests.test_actual_dispatch_upload_and_unknown_failures_never_retry.__code__
if _dispatch_code.co_consts.count('display-xnu-fixed32')!=1:raise ValueError('Exact old dispatch fixture descriptor boundary')
_dispatch_code=_dispatch_code.replace(co_consts=tuple(stage.DESCRIPTOR if value=='display-xnu-fixed32' else value for value in _dispatch_code.co_consts))

class RestartDiagnosticTransportTests(unittest.TestCase):
    runtime=runtime
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads(stage.REPORT.read_text());cls.package=json.loads((stage.PACKAGE/'manifest.json').read_text())
    def context(self):
        stage.transport();pins=stage.source_pins()|{str(stage.PACKAGE/'manifest.json'):stage.MANIFEST_SHA}
        for key in ('inputs_sha256','headers_sha256','generated_sha256'):pins=stage.prior.merge_pins(pins,self.package[key])
        binding=json.loads((ROOT/'build/rpi5/pcie-phy-reset-restored-20261014/plan.json').read_text())['media']['identity_binding']
        return dict(installed=dict(directory=str(ROOT/'build/rpi5/offline-restart-installation'),checkpoint_sha256='1'*64,plan_sha256='2'*64,
            result_sha256='3'*64,preflight=self.report,loader_sha256=stage.IMAGE_SHA,config_sha256=stage.engine.TRIAL_CONFIG_SHA,original_linux_boot_id=BOOT),
            evidence=pins,plan={'media':{'host':stage.HOST,'linux_boot_id':BOOT,'identity_binding':binding}})
    media=types.FunctionType(old.DisplayXNUTransportTests.media.__code__,globals())
    test_modem_low_read_error_never_arm_receive_or_reboot=types.FunctionType(old.DisplayXNUTransportTests.test_modem_low_read_error_never_arm_receive_or_reboot.__code__,globals())
    test_continuously_readable_rx_stops_tx_at_absolute_deadline=types.FunctionType(old.DisplayXNUTransportTests.test_continuously_readable_rx_stops_tx_at_absolute_deadline.__code__,globals())
    test_one_shot_launcher_exact_actual_armed_schema=types.FunctionType(old.DisplayXNUTransportTests.test_one_shot_launcher_exact_actual_armed_schema.__code__,globals())
    test_actual_dispatch_upload_and_unknown_failures_never_retry=types.FunctionType(_dispatch_code,globals())
    def test_actual_report_receiver_and_package_admission(self):
        context=self.context();seal=dict(payload={'media_plan':self.media()},evidence_sha256=context['evidence'])
        with patch.object(stage.checker,'inspect',side_effect=AssertionError('No compile or package replay')):
            checked=stage.admit(seal)
        self.assertTrue(checked['actual_report_bound']);self.assertFalse(checked['physical_psci_causality_proven'])
        self.assertTrue(recorder.protocol.boot_ready(boot(self.report),self.report))
        for changes in ({'root_nodes':32},{'terminal_watchdog_seconds':180.0},
                {'watchdog_rate_bound_proven':True},{'restart_ready_marker':'OTHER'},{'physical_psci_causality_proven':True}):
            bad=copy.deepcopy(seal);bad['payload']['media_plan']['preflight'].update(changes)
            with self.assertRaises(ValueError):stage.admit(bad)
        for path in (Path(recorder.protocol.__file__),Path(recorder.__file__),Path(stage.__file__)):
            bad=copy.deepcopy(seal);bad['evidence_sha256'].pop(str(path.resolve()))
            with self.assertRaises(ValueError):stage.admit(bad)
    def test_actual_five_commands_ordered_nominal_result_and_independent_return(self):
        context=self.context()
        with tempfile.TemporaryDirectory(prefix='restart-real-body-',dir=ROOT/'build/rpi5') as name:
            directory=Path(name);directory.rmdir();rc,sent=self.runtime(context,directory)
            state=json.loads((directory/'state.json').read_text());self.assertEqual(rc,0,state)
            state,observed,_=evidence.captured(context,directory);self.assertTrue(observed['capture_valid'])
            self.assertEqual(len(state['exchanges']),4);self.assertEqual(len(sent),state['transmitted_bytes'])
            self.assertTrue(sent.endswith((recorder.protocol.restart_command(state['nonce'])+'\n').encode()))
            diagnostic=observed['diagnostic'];self.assertTrue(diagnostic['nominal_early_return'])
            self.assertTrue(diagnostic['ordered_real_reboot_path_observed']);self.assertFalse(diagnostic['physical_psci_causality_proven'])
            expected=context['plan']['media']['identity_binding']['expected'];pins=evidence.source_pins(context)
            returned=dict(host=stage.HOST,boot_id=RETURN,identity=dict(identity=expected,boot_id=RETURN,hostname='kamidana'),
                root=expected['root'].split(),bootloader={'boot-mode':6,'partition':1,'tryboot':0},sd_partitions_unmounted=True,read_only=True,
                observed_utc='2026-10-14T20:10:00+00:00',installation=context['installed'],serial_sha256=state['serial_sha256'],return_source_sha256=pins)
            with patch.object(evidence.scope['subprocess'],'run',return_value=subprocess.CompletedProcess([],0,json.dumps(returned),'')) as called:
                result=evidence.collect_return(context,directory);self.assertEqual(called.call_count,1)
            self.assertTrue(result['capture_valid']);self.assertEqual(evidence.load_return(context,directory)[1],RETURN)
            for change in ({'boot_id':BOOT},{'root':['/dev/mmcblk0p2','ext4','wrong']},{'sd_partitions_unmounted':False}):
                with self.assertRaises(ValueError):evidence.inspect_return(returned|change,context,observed)
            with self.assertRaises(ValueError):evidence.collect_return(context,directory)
    def test_echo_return_snapshot_fallback_and_full_tail_failure_do_not_pass(self):
        context=self.context()
        for fault in ('rebootecho','smcreturn','snapshot','watchdog','tailpanic','returnfault'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(prefix='restart-fault-',dir=ROOT/'build/rpi5') as name:
                directory=Path(name);directory.rmdir();rc,sent=self.runtime(context,directory,fault)
                state,observed,_=evidence.captured(context,directory)
                self.assertEqual(rc,1);self.assertFalse(observed['capture_valid']);self.assertTrue(state['normal_nvme_boot_observed'])
                self.assertEqual(sent.count((recorder.protocol.restart_command(state['nonce'])+'\n').encode()),1)
    def test_missing_readiness_no_input_and_mid_input_reset_no_retry(self):
        context=self.context()
        for fault in ('oldtag','missingmirror','missingroot','missingrestart','resetduringtx','echoonly','status1'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(prefix='restart-gate-',dir=ROOT/'build/rpi5') as name:
                directory=Path(name);directory.rmdir();rc,sent=self.runtime(context,directory,fault)
                state,observed,_=evidence.captured(context,directory);self.assertEqual(rc,1);self.assertFalse(observed['capture_valid'])
                if fault.startswith('missing') or fault=='oldtag':self.assertEqual(sent,b'')
                elif fault=='resetduringtx':self.assertEqual(len(sent),12)
                self.assertNotIn(b'/sbin/reboot',sent)
    def test_actual_completed_phy414_only_byte_intake(self):
        path=ROOT/'build/rpi5/pcie-phy-reset-restored-20261014'
        seal='9db245ae4b843afcd07108024169411469d3c3532a48c45b518d374add8ad7a9'
        plan='b012548fdefc92a152ed278ab761f137b02cdb07ac95d53d2ab6b589b8362838'
        self.assertEqual(stage.sha(path/'result.json'),'235ae47daced02d0eec58d9155ecd4244aecc4548a7e9eb1b05426bc90c5a891')
        with patch.object(subprocess,'run',side_effect=AssertionError('No compiler, remote, or hardware')):
            context=stage.baseline(path,seal,plan)
            self.assertEqual(len(context['result']['next_catalog']),414)
            self.assertEqual(context['result']['publication']['identity']['boot_id'],'5893543b-80df-4594-bef7-9e6c4833a8b4')
            for s,p in (('0'*64,plan),(seal,'0'*64)):
                with self.assertRaises(ValueError):stage.baseline(path,s,p)
        for name in ('config.txt','bl31.bin','probe.bin'):
            bad=copy.deepcopy(context);bad['result']['publication']['protected_files_sha256'][name]='0'*64
            with patch.object(stage.phy,'completed_restore',return_value=bad),self.assertRaises(ValueError):stage.baseline(path,seal,plan)
    def test_exact_graph_and_publisher_identity(self):
        self.assertIs(stage._dispatch.__code__,stage.publisher.dispatch.__code__)
        self.assertIs(stage._package_graph.__code__,stage.graph.package_graph.__code__)
        self.assertIs(stage._graph_scope['stage'],stage)
        self.assertEqual(stage.get_descriptor(stage.DESCRIPTOR),{'hardware_allowed':True})
        with self.assertRaises(ValueError):stage.get_descriptor('display-xnu-fixed32')
    def test_source_inventory_cache_still_rechecks_actual_bytes(self):
        pins=stage.source_pins();actual=stage.sha;target=str(Path(stage.__file__).resolve())
        with patch.object(stage,'sha',side_effect=lambda path:'0'*64 if str(path)==target else actual(path)):
            with self.assertRaisesRegex(ValueError,'source changed after inventory'):stage.source_pins()
        self.assertEqual(stage.source_pins(),pins)

if __name__=='__main__':unittest.main()
