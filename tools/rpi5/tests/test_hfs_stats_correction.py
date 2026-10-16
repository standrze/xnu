# SPDX-License-Identifier: BSD-2-Clause
"""Corrective installer evidence guards; synthetic captures, no hardware."""
import copy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stage_hfs_stats_correction as correction


class HFSStatsCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def failed_bundle(self):
        original = self.base / 'original'; original.mkdir(exist_ok=True)
        (original/'serial.bin').write_bytes(b'preserved torn boot bytes\r\n')
        (original/'state.json').write_text('{}')
        metadata = dict(continuation_of=str((original/'state.json').resolve()),
                        previous_state_sha256=correction.boot.trial.sha256(original/'state.json'),
                        previous_raw_sha256=correction.boot.trial.sha256(original/'serial.bin'),
                        previous_raw_bytes=(original/'serial.bin').stat().st_size,
                        capture_segments=2,closed_port_interval_observed=False,encoding_ready_banner_observed=False)
        reports = dict(preflight=dict(image_sha256='a'*64))
        hashes = dict(reference='b'*64)
        raw = (original/'serial.bin').read_bytes()+b'xnu:/# hfsro mount /dev/disk0s2\r\r\nhfsro statfs64: errno 45\r\r\nxnu:/# '
        state = dict(status='failed',error='shell command did not complete: hfsro mount /dev/disk0s2',
                     checks=['fresh_repeated_shell_readiness_after_explicit_capture_gap',
                             'fresh_distinct_hfs_loader_sd_capacity_hfs_services_and_shell_ready',
                             'fresh_shell_nonce','real_bsd_second_partition_node'],
                     reads=[],mount_cycles_completed=0,sd_data_write_commands=0,transmitted_bytes=56,
                     image_sha256='a'*64,evidence_sha256=hashes,partition='/dev/disk0s2',
                     device='/dev/cu.usbmodem102',baud=115200,bytes=len(raw),
                     serial_sha256=hashlib.sha256(raw).hexdigest(),started_utc='2026-10-12T02:12:08+00:00',**metadata)
        path = self.base/'state.json'; path.write_text(json.dumps(state))
        (self.base/'serial.bin').write_bytes(raw)
        return path,state,raw,reports,hashes,((original/'serial.bin').read_bytes(),metadata)

    def test_exact_failure_and_original_prefix_binding(self):
        path,state,raw,reports,hashes,resume=self.failed_bundle()
        with patch.object(correction.boot.trial,'load_zero_tx_resume',return_value=resume):
            result=correction.validate_failure(path,reports,hashes)
        self.assertEqual(result['failed_serial'],hashlib.sha256(raw).hexdigest())

    def test_partial_mount_ambiguous_response_tamper_and_wrong_images_reject(self):
        for fault in ('mounted','read','writes','tx','image','binding','bytes','digest','raw-panic',
                      'raw-mounted','wrong-error','extra-output','duplicate','prefix','original','gap'):
            path,state,raw,reports,hashes,resume=self.failed_bundle()
            if fault=='mounted': state['mount_cycles_completed']=1
            if fault=='read': state['reads']=[{}]
            if fault=='writes': state['sd_data_write_commands']=1
            if fault=='tx': state['transmitted_bytes']=57
            if fault=='image': state['image_sha256']='c'*64
            if fault=='binding': state['evidence_sha256']={}
            if fault=='bytes': state['bytes']+=1
            if fault=='digest': state['serial_sha256']='0'*64
            if fault=='raw-panic': raw+=b'panic(cpu'
            if fault=='raw-mounted': raw+=b'RPI5XNU:HFSRO:MOUNTED'
            if fault=='wrong-error': raw=raw.replace(b'errno 45',b'errno 5')
            if fault=='extra-output': raw=raw.replace(b'errno 45',b'errno 45\r\nUNKNOWN')
            if fault=='duplicate': raw+=b'hfsro mount /dev/disk0s2'
            if fault=='prefix': raw=b'changed'+raw
            if fault=='original': state['previous_state_sha256']='0'*64
            if fault=='gap': state['closed_port_interval_observed']=True
            if fault.startswith('raw-') or fault in ('wrong-error','extra-output','duplicate','prefix'):
                state.update(bytes=len(raw),serial_sha256=hashlib.sha256(raw).hexdigest())
                (self.base/'serial.bin').write_bytes(raw)
            path.write_text(json.dumps(state))
            with self.subTest(fault=fault), patch.object(correction.boot.trial,'load_zero_tx_resume',return_value=resume), \
                    self.assertRaises(ValueError):
                correction.validate_failure(path,reports,hashes)

    def test_prior_install_must_be_complete_typed_and_exact(self):
        plan=dict(run='/home/sandrzej/xnu-gate4-hfs-boot-abcdefgh',new_image_sha256='a'*64,old_image_sha256='b'*64)
        result=dict(status='installed',run=plan['run'],image_sha256='a'*64,preserved_sd_image_sha256='b'*64,
                    hfs_partition_unchanged=True,protected_boot_files_unchanged=True,boot_unmounted=True,
                    no_hfs_mount=True,no_partition_change=True,no_config_change=True,no_reboot=True,
                    sd_backup='probe.sd-read-passed-20261012.bin',temporary_published=True,power_loss_atomicity_claimed=False)
        correction.validate_installed(result,plan)
        for field in result:
            bad=copy.deepcopy(result); bad[field]=None
            with self.subTest(field=field), self.assertRaises(ValueError):
                correction.validate_installed(bad,plan)

    def argv(self, output, execute=False):
        flags=('fixture','sd-baseline-reference','reference','preflight','sd-trial',
               'staging-plan','staging-result','prior-plan','prior-result','prior-reference',
               'prior-preflight','failed-state')
        args=['stage_hfs_stats_correction.py','--output',str(output)]
        for name in flags: args+=['--'+name,str(self.base/(name+'.json'))]
        return args+(['--execute'] if execute else [])

    def test_local_default_and_rejected_evidence_never_connect(self):
        output=self.base/'local'
        with patch.object(sys,'argv',self.argv(output)), \
                patch.object(Path,'is_relative_to',return_value=True), \
                patch.object(correction,'load_plan',return_value=dict(no_reboot=True)), \
                patch.object(correction.subprocess,'run') as network, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(correction.main(),0)
        network.assert_not_called()
        output=self.base/'rejected'
        with patch.object(sys,'argv',self.argv(output,True)), \
                patch.object(Path,'is_relative_to',return_value=True), \
                patch.object(correction,'load_plan',side_effect=ValueError('stale or unbound evidence')), \
                patch.object(correction.subprocess,'run') as network, self.assertRaises(ValueError):
            correction.main()
        network.assert_not_called(); self.assertFalse(output.exists())

    def test_remote_timeout_retains_exact_run_and_partial_output_without_retry(self):
        output=self.base/'unknown'
        plan=dict(candidate='candidate.bin',expected={},fixture_sha256='a'*64)
        responses=[SimpleNamespace(stdout=json.dumps(dict(run='/home/sandrzej/xnu-gate4-hfs-stats-abcdefgh'))),
                   SimpleNamespace(returncode=0),correction.subprocess.TimeoutExpired('ssh',300,output=b'partial',stderr=b'error')]
        with patch.object(sys,'argv',self.argv(output,True)), \
                patch.object(Path,'is_relative_to',return_value=True), \
                patch.object(correction,'load_plan',side_effect=lambda _:copy.deepcopy(plan)), \
                patch.object(correction.subprocess,'run',side_effect=responses) as network, \
                self.assertRaises(correction.subprocess.TimeoutExpired):
            correction.main()
        self.assertEqual(network.call_count,3)
        self.assertEqual((output/'remote.stdout').read_bytes(),b'partial')
        self.assertTrue((output/'outcome-unknown.txt').exists())
        self.assertFalse((output/'result.json').exists())
        self.assertEqual(json.loads((output/'plan.json').read_text())['run'],'/home/sandrzej/xnu-gate4-hfs-stats-abcdefgh')


if __name__=='__main__':
    unittest.main()
