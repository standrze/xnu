# SPDX-License-Identifier: BSD-2-Clause
"""Actual root43 bytes, ten-command protocol and UART/SSH-double integration."""
import contextlib
import copy
import inspect
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import types
import unittest
from unittest.mock import patch
from tools.rpi5 import root45_entropy_evidence as evidence
from tools.rpi5 import arm_root45_entropy_reboot as launcher
from tools.rpi5 import check_root45_entropy_root as root
from tools.rpi5.tests import test_root42_ready_transport as preceding
from tools.rpi5.tests import test_root42_pthread_trial as old_fixture

recorder=evidence.recorder;stage=recorder.staging;core=recorder.core
ROOT,BOOT,DEVICE=preceding.ROOT,preceding.BOOT,preceding.DEVICE
old=preceding.old


def pins():
    names=('stage_root45_entropy_trial.py','serial_root45_entropy_trial.py','root45_entropy_trial_core.py',
        'root45_entropy_command_evidence.py','root45_entropy_evidence.py','arm_root45_entropy_reboot.py','tests/test_root45_entropy_transport.py')
    return stage.previous.source_pins()|{str(ROOT/'tools/rpi5'/n):stage.sha(ROOT/'tools/rpi5'/n) for n in names}


def entropy_lines(startup=0):
    values=(startup,12,0,4,22,0,7,1000,600,401)
    return (*core.PTHREAD_LINES,*(f'RPI5XNU:ENTROPY:COUNTER NAME={name} VALUE={value}'.encode()
        for (name,_),value in zip(core.COUNTERS,values)),core.ENTROPY_END)


def batch(files):
    value=old_fixture.batch(files).replace(b'B42:',b'B45:')
    final=('B45:'+old_fixture.NONCE+':END:0').encode()
    packet=b'\n'.join((('B45:'+old_fixture.NONCE+':packet:B').encode(),*core.PACKET_LINES,
        ('B45:'+old_fixture.NONCE+':packet:E:0').encode()))
        
    entropy=b'\n'.join((('B45:'+old_fixture.NONCE+':entropy:B').encode(),*entropy_lines(),
        ('B45:'+old_fixture.NONCE+':entropy:E:0').encode()))
    rand=b'\n'.join((('B45:'+old_fixture.NONCE+':rand:B').encode(),*core.RAND_LINES,
        ('B45:'+old_fixture.NONCE+':rand:E:0').encode()))
    return value.replace(final,packet+b'\n'+entropy+b'\n'+rand+b'\n'+final)


fixture=types.SimpleNamespace(NONCE=old_fixture.NONCE,batch=batch,identity_bytes=old_fixture.identity_bytes)
runtime_source=textwrap.dedent(inspect.getsource(preceding.ReadyTests.runtime.__wrapped__))
if runtime_source.count("b'\nB42:"):
    raise AssertionError('Expected escaped source, not a literal new line')
runtime_source=core.replace(runtime_source,"b'\\nB42:","b'\\nB45:",1)
runtime_source=core.replace(runtime_source,
    ".replace(core.prior.PTHREAD_LINES[0],row+b'\\n'+core.prior.PTHREAD_LINES[0])",
    ".replace(core.prior.PTHREAD_LINES[0],row+b'\\n'+core.prior.PTHREAD_LINES[0],1)",1)
runtime_scope=globals().copy();exec(compile(runtime_source,__file__,'exec'),runtime_scope)
launcher_source=textwrap.dedent(inspect.getsource(preceding.ReadyTests.test_actual_one_shot_launcher_uses_new_recorder_and_live_armed_schema))
launcher_source=core.replace(launcher_source,'serial_root42_ready_trial.py','serial_root45_entropy_trial.py',1)
launcher_scope=globals().copy();exec(compile(launcher_source,__file__,'exec'),launcher_scope)


class EntropyTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt=json.loads((root.PACKAGE/'manifest.json').read_text())
        cls.files=root.old.profile.files_from((root.PACKAGE/'ramdisk.bin').read_bytes())

    def context(self):
        size=len((root.PACKAGE/'ramdisk.bin').read_bytes())
        report=dict(image_bytes=20971520,root_nodes=45,root_files=33,image=str(stage.PACKAGE/'probe.bin'),image_sha256=stage.IMAGE_SHA,
            root_manifest=str(root.PACKAGE/'manifest.json'),
            root_copy_marker='RPI5XNU:FIXTURE:EXACT_ROOT_COPY',kernel_copy_marker='RPI5XNU:FIXTURE:EXACT_KERNEL_COPY',
            root_mount_marker=f'RPI5XNU:RAMROOT:MOUNT NODES=45 BYTES={size} READONLY',
            watchdog_ready_marker=core.prior.WATCHDOG.decode(),watchdog_ready_profile=core.WATCHDOG_PROFILE,
            trial_marker='RPI5XNU:BL33:ROOT45_ENTROPY_TRIAL TAG='+'a'*32+' CPUS=4 ROOT_NODES=45 WATCHDOG_READY_V2',
            handoff={k:True for k in ('required_by_kernel','linked_loader_handoff','descriptor_not_confused_with_kernel_string')},
            root_ready_marker=f'RPI5XNU:TERMINAL:ROOT_READY SECONDS=180 NODES=45 BYTES={size} READONLY',
            root_ready_max_reports=3,root_ready_requires_mounted_readonly=True,root_ready_requires_successful_reload=True)
        installed=dict(directory=str(ROOT/'build/rpi5/offline-root45-install'),checkpoint_sha256='1'*64,
            plan_sha256='2'*64,result_sha256='3'*64,preflight=report,loader_sha256=stage.IMAGE_SHA,original_linux_boot_id=BOOT)
        identity=json.loads((ROOT/'build/rpi5/root-route-restored-20261013/plan.json').read_text())['media']['identity_binding']
        return dict(installed=installed,evidence=pins(),plan={'media':{'host':stage.HOST,'linux_boot_id':BOOT,'identity_binding':identity}})

    def boot(self,report,late=True):
        raw=old_fixture.fixture.boot(report).replace(report['root_mount_marker'].encode(),b'garbled early printf')
        if late:raw=raw.replace(core.prior.WATCHDOG+b'\n',core.prior.WATCHDOG+b'\n'+report['root_ready_marker'].encode()+b'\n')
        return raw

    runtime=runtime_scope['runtime']
    test_actual_one_shot_launcher=launcher_scope['test_actual_one_shot_launcher_uses_new_recorder_and_live_armed_schema']

    def test_actual_45_node_33_file_catalog_and_twelve_outputs(self):
        core.prior.validate_root(self.receipt,self.files)
        self.assertEqual(len(self.files),33);self.assertEqual(self.receipt['output_nodes'],45)
        expected=json.loads((ROOT/'build/rpi5/apple-ssh-packet-pthread-iabcb1gr/manifest.json').read_text())['expected_target_stdout']
        self.assertEqual(b'\n'.join(core.PACKET_LINES)+b'\n',expected.encode())
        report=self.context()['installed']['preflight'];bound=core.bind(report)
        result=bound.inspect_batch(batch(self.files),fixture.NONCE,self.files)
        self.assertEqual(len(result['commands']),12)
        self.assertEqual(result['commands'][-1]['command'],'/usr/local/libexec/xnu/kernel_randprobe')
        self.assertTrue(result['actual_original_ssh_libressl_packet_cipher_diagnostic'])
        self.assertEqual((result['valid_packet_cases'],result['rejected_packet_cases']),(48,5036))
        for key in ('batch_process_exit_verified','ssh_daemon','ssh_transport','networking','entropy_qualified'):
            self.assertIs(result[key],False)

    def test_packet_body_and_old_frames_fail_closed(self):
        bound=core.bind(self.context()['installed']['preflight']);raw=batch(self.files)
        for before,after in ((b'CASES=48',b'CASES=47'),(b'REJECTED=5036',b'REJECTED=0'),
            (b'NO_TRANSPORT_OR_ENTROPY_PROOF',b'ENTROPY_OK'),(b':packet:E:0',b':packet:E:1'),
            (b'B45:',b'B42:'),(core.PACKET_LINES[-1],b'')):
            with self.subTest(before=before),self.assertRaises(ValueError):
                bound.inspect_batch(raw.replace(before,after),fixture.NONCE,self.files)
        packet_start=raw.index((':packet:B').encode());broken=raw[:packet_start]+raw[packet_start:].replace(b'PTHREAD:MAIN_READY\n',b'',1)
        with self.assertRaises(ValueError):bound.inspect_batch(broken,fixture.NONCE,self.files)
        with self.assertRaises(ValueError):bound.inspect_batch(raw+b'\nB42:old:BEGIN',fixture.NONCE,self.files)

    def test_only_exact_packet_rejection_count_has_streaming_exception(self):
        row=core.PACKET_LINES[-1]
        for offset in range(len(row)+1):self.assertFalse(core.unsafe_response(b'\n'+row[:offset]))
        self.assertFalse(core.unsafe_response(b'\n'+row+b'\n'))
        for bad in (b'REJECTED',row.replace(b'5036',b'5037'),row+b'!',b'prefix '+row,
            row+b'\nREJECTED',row+b'\npanic(cpu 0)',row+b'\nBoot mode: NVME (06)'):
            self.assertTrue(core.unsafe_response(b'\n'+bad),bad)

    def test_complete_runtime_faults_before_admission_and_inside_commands(self):
        report=self.context()['installed']['preflight'];raw=self.boot(report)
        for marker in core.RUNTIME_FAULTS:
            with self.assertRaises(RuntimeError):core.boot_ready(marker+b'\n'+raw,report)
            self.assertTrue(core.unsafe_response(b'\n'+marker+b'\n'))
            with self.assertRaises(ValueError):
                core.bind(report).inspect_batch(batch(self.files)+b'\n'+marker+b'\n',fixture.NONCE,self.files)

    def test_actual_per_byte_body_twelve_commands_exit_replay_and_return(self):
        with self.runtime() as (context,out,code,commands):
            state=json.loads((out/'state.json').read_text());self.assertEqual(code,0,state.get('error'))
            self.assertEqual(len(commands),3);self.assertEqual(len(state['batch']['commands']),12)
            self.assertTrue(state['batch']['batch_process_exit_verified'])
            _,observed,_=evidence.captured(context,out);self.assertTrue(observed['capture_valid'],observed['capture_error'])
            expected=context['plan']['media']['identity_binding']['expected']
            witness=dict(host=stage.HOST,boot_id=old.NEWBOOT,identity=dict(identity=expected,boot_id=old.NEWBOOT,hostname='kamidana'),
                root=expected['root'].split(),bootloader={'boot-mode':6,'partition':1,'tryboot':0},read_only=True,
                sd_partitions_unmounted=True,observed_utc='2026-10-13T18:04:00+00:00',installation=context['installed'],
                serial_sha256=state['serial_sha256'],return_source_sha256=evidence.source_pins(context))
            with patch.object(evidence.collect_return.__globals__['subprocess'],'run',return_value=subprocess.CompletedProcess([],0,json.dumps(witness),'')):
                result=evidence.collect_return(context,out)
            self.assertEqual(evidence.load_return(context,out)[0],result)

    def test_late_state_no_tx_and_postcommand_panic_remain_failures(self):
        with self.runtime(True) as (context,out,code,commands):
            self.assertEqual((code,commands),(1,[]));self.assertFalse(evidence.captured(context,out)[1]['capture_valid'])
        with self.runtime(panic=True) as (context,out,code,commands):
            self.assertEqual((code,len(commands)),(1,3));self.assertFalse(evidence.captured(context,out)[1]['capture_valid'])

    def test_bounded_late_snapshot_and_old_geometry_rejection(self):
        report=self.context()['installed']['preflight'];raw=self.boot(report);row=report['root_ready_marker'].encode()
        self.assertTrue(core.boot_ready(raw,report))
        for tail in (b'\n'+row.replace(b'NODES=45',b'NODES=42')+b'\n',b'\n'+(row+b'\n')*3):
            with self.assertRaises(ValueError):core.boot_ready(raw+tail,report)
        changed=copy.deepcopy(report);changed['root_nodes']=42
        with self.assertRaises(RuntimeError):core.boot_ready(raw,changed)
        with self.assertRaises(RuntimeError):core.boot_ready(row+b'\n'+raw,report)

    def test_real_parser_681_byte_batch_and_separate_exit_query(self):
        with tempfile.TemporaryDirectory(prefix='root45-parser-') as name:
            program=Path(name)/'parser'
            result=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                '-I'+str(ROOT/'tools/rpi5/user'),str(ROOT/'tools/rpi5/user/parser.c'),
                str(ROOT/'tools/rpi5/tests/root41_batch_parser_harness.c'),'-o',str(program)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            value=core.batch_command(fixture.NONCE);self.assertEqual(len(value),681)
            self.assertEqual(subprocess.check_output([program,value],text=True).splitlines(),['/bin/zsh','-f','-c',core.script(fixture.NONCE)])
            self.assertEqual(subprocess.check_output([program,core.recovery_command(fixture.NONCE)],text=True).splitlines(),
                ['echo','B45:'+fixture.NONCE+':RECOVERY_STATUS:17'])

    def test_bound_main_selects_exact_successor(self):
        context=self.context()
        with patch.object(stage,'source_pins',side_effect=pins),patch.object(recorder,'package_pins',return_value={}):
            bound=recorder.bindings(context)
            self.assertEqual(Path(bound.__globals__['__file__']).resolve(),ROOT/'tools/rpi5/serial_root45_entropy_trial.py')
        self.assertIs(stage.prior.baseline,stage.baseline)
        self.assertIs(launcher.launch.__globals__['recorder'],recorder)

    def test_exact_typed_restore_dispatch_and_package_bindings(self):
        self.assertEqual(stage.sha(stage.PACKAGE/'manifest.json'),stage.MANIFEST_SHA)
        self.assertEqual(stage.sha(stage.PACKAGE/'probe.bin'),stage.IMAGE_SHA)
        actual=json.loads((stage.PACKAGE/'manifest.json').read_text())
        self.assertEqual(core.WATCHDOG_PROFILE,actual['watchdog_ready_profile'])
        report=self.context()['installed']['preflight']
        for key in ('watchdog_ready_profile','watchdog_ready_marker','trial_marker','root_ready_marker',
            'root_ready_max_reports','root_ready_requires_mounted_readonly','root_ready_requires_successful_reload'):
            report[key]=actual[key]
        core.validate_report(report)
        self.assertTrue(core.boot_ready(self.boot(report),report))
        for key,value in (('watchdog_ready_profile','root43-state-confirmed-watchdog-kernel-v1'),
            ('root_nodes',42),('root_files',30),('handoff',{})):
            wrong=copy.deepcopy(report);wrong[key]=value
            with self.assertRaises(ValueError):core.validate_report(wrong)
        with old.fresh() as out:
            out.mkdir()
            for profile,which in ((stage.engine.RESTORE,None),(stage.base.prior.engine.RESTORE,'pair'),('unknown',None)):
                file=out/'checkpoint.json'
                if file.exists():file.unlink()
                stage.save(file,dict(payload=dict(media_plan=dict(profile=profile))))
                with patch.object(stage.previous,'restoration',return_value='loader') as loader,\
                    patch.object(stage.base.prior,'baseline',return_value='pair') as pair:
                    if which is None:
                        with self.assertRaises(ValueError):stage.baseline(out,'1'*64,'2'*64)
                        loader.assert_not_called();pair.assert_not_called()
                    else:
                        self.assertEqual(stage.baseline(out,'1'*64,'2'*64),which)
                        chosen=loader if which=='loader' else pair
                        chosen.assert_called_once_with(out,'1'*64,'2'*64)


    def test_typed_ordered_api_observations_never_quality(self):
        self.assertEqual(core.entropy_values(list(entropy_lines()))[core.COUNTERS[0][0]],0)
        self.assertEqual(core.entropy_values(list(entropy_lines(1)))[core.COUNTERS[0][0]],1)
        result=core.bind(self.context()['installed']['preflight']).inspect_batch(batch(self.files),fixture.NONCE,self.files)
        self.assertTrue(result['actual_chacha_poly1305_public_kats'])
        self.assertNotIn('actual_chacha_poly1315_public_kats',result)
        self.assertTrue(result['actual_kernel_getentropy_api_checks'])
        self.assertTrue(result['actual_libressl_rand_kernel_adapter'])
        for name in ('entropy_qualified','keys_generated','random_bytes_or_hashes_recorded'):
            self.assertIs(result[name],False)
        rows=list(entropy_lines())
        for index,limit in enumerate((1,2**32-1,0,2**32-1,2**32-1,0,2**32-1,2**64-1,2**64-1,2**64-1)):
            good=list(rows);good[3+index]=good[3+index].split(b' VALUE=')[0]+b' VALUE='+str(limit).encode()
            core.entropy_values(good)
            for value in (str(limit+1).encode(),b'-1',b'+0',b'00',b'1.0',b'NaN',b'9'*21):
                bad=list(rows);bad[3+index]=bad[3+index].split(b' VALUE=')[0]+b' VALUE='+value
                with self.subTest(index=index,value=value),self.assertRaises(ValueError):core.entropy_values(bad)
        for bad in (rows[:-1],rows+[rows[3]],rows[:3]+[rows[4],rows[3]]+rows[5:],
            [v.replace(b'UNAVAILABLE=0',b'UNAVAILABLE=1') for v in rows],
            [v.replace(b'HEALTH_FAILURE=0',b'HEALTH_FAILURE=1') for v in rows],
            [v.replace(b'QUALITY_NOT_PROVEN',b'QUALITY_PROVEN') for v in rows]):
            with self.assertRaises(ValueError):core.entropy_values(bad)
        raw=batch(self.files);bound=core.bind(self.context()['installed']['preflight'])
        for before,after in ((b':entropy:E:0',b':entropy:E:1'),(b':rand:E:0',b':rand:E:127'),
            (core.RAND_LINES[-1],b'RAND success'),(core.ENTROPY_END,b'')):
            with self.assertRaises(ValueError):bound.inspect_batch(raw.replace(before,after),fixture.NONCE,self.files)
        with self.assertRaises(ValueError):bound.inspect_batch(raw.replace(core.ENTROPY_END,b'random=0123\\n'+core.ENTROPY_END),fixture.NONCE,self.files)


if __name__=='__main__':unittest.main()
