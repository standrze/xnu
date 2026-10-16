# SPDX-License-Identifier: BSD-2-Clause
"""Receive-only recorder with explicit port/time/receipt doubles; no hardware."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools.rpi5 import serial_pcie_fw_trial as recorder
from tools.rpi5.tests.test_pcie_fw_trial_serial import fixture,TAG,IMAGE,FIRMWARE
from tools.rpi5.tests.test_pcie_fw_install import receipt,BOOT


class FirmwareRecorderTests(unittest.TestCase):
    def run_capture(self,data,disconnected=False):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();out=root/'build/rpi5/capture';out.parent.mkdir(parents=True)
            installed=dict(preflight=dict(trial_tag=TAG),pair_sha256={'probe.bin':IMAGE,'bl31.bin':FIRMWARE})
            attrs=[0,0,0,0,0,0,[0]*32];real_open,real_close=os.open,os.close
            def opened(path,*args,**kwargs):return 99 if path=='/dev/cu.usbmodemTest' else real_open(path,*args,**kwargs)
            def closed(fd):return None if fd==99 else real_close(fd)
            with patch.object(recorder.staging,'ROOT',root),patch.object(recorder,'installation',return_value=installed), \
                patch.object(recorder.staging,'source_pins',return_value={}),patch.object(recorder.lease,'hold',return_value=contextlib.nullcontext()), \
                patch.object(recorder.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','')), \
                patch.object(recorder.os,'open',side_effect=opened),patch.object(recorder.os,'close',side_effect=closed) as close, \
                patch.object(recorder.os,'fsync'),patch.object(recorder.os,'read',return_value=b'' if disconnected else data), \
                patch.object(recorder.os,'write',side_effect=AssertionError('No serial transmit')) as tx, \
                patch.object(recorder.fcntl,'ioctl'),patch.object(recorder.termios,'tcgetattr',return_value=attrs), \
                patch.object(recorder.termios,'tcsetattr'),patch.object(recorder.termios,'tcflush'), \
                patch.object(recorder.select,'select',return_value=([99],[],[])), \
                patch.object(recorder.time,'monotonic',side_effect=[0,0,0,.01,61]),contextlib.redirect_stdout(io.StringIO()):
                status=recorder.main(['/dev/cu.usbmodemTest',str(out),'--installation',name,'--seconds','60'])
            tx.assert_not_called();close.assert_any_call(99)
            return status,json.loads((out/'state.json').read_text()),(out/'serial.bin').read_bytes()

    def test_actual_receive_loop_zero_tx_and_observation_is_not_recovery(self):
        code,state,raw=self.run_capture(fixture())
        self.assertEqual(code,0);self.assertEqual(raw,fixture());self.assertEqual(state['transmitted_bytes'],0)
        self.assertTrue(state['continuous_capture']);self.assertTrue(state['diagnostic']['firmware_abi_observation_pass'])
        self.assertFalse(state['physical_reset_return_proven']);self.assertFalse(state['diagnostic']['xnu_pe_runtime_proven'])

    def test_partial_or_faulted_abi_cannot_succeed_despite_continuous_capture(self):
        for data in (b'RPi: BOOTSYS only\r\n',fixture().replace(b'RPC_END',b'RPC_BROKEN',1),
            fixture()+b'RPI5XNU:FWABI:FAULT TAG='+TAG.encode()+b'\r\n'):
            code,state,_=self.run_capture(data)
            self.assertEqual(code,1);self.assertTrue(state['continuous_capture']);self.assertIn('diagnostic_error',state)

    def test_disconnect_is_terminal_no_reopen_or_continuity_claim(self):
        code,state,_=self.run_capture(b'',True)
        self.assertEqual(code,1);self.assertFalse(state['continuous_capture']);self.assertIn('disconnected',state['error'])

    def test_existing_port_handle_or_ambiguous_lookup_refuses_before_open(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();out=root/'build/rpi5/capture';out.parent.mkdir(parents=True)
            for r in (subprocess.CompletedProcess([],0,'123\n',''),subprocess.CompletedProcess([],1,'','lookup failed')):
                with patch.object(recorder.staging,'ROOT',root),patch.object(recorder,'installation',return_value={}), \
                    patch.object(recorder.staging,'source_pins',return_value={}), \
                    patch.object(recorder.lease,'hold',return_value=contextlib.nullcontext()), \
                    patch.object(recorder.subprocess,'run',return_value=r),patch.object(recorder.os,'open') as opened:
                    with self.assertRaisesRegex(ValueError,'Port already open'):recorder.main(['/dev/cu.usbmodemTest',str(out),'--installation',name])
                    opened.assert_not_called();self.assertFalse(out.exists())

    def test_os_board_lease_not_stale_metadata_is_ownership(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();folder=root/'build/rpi5';folder.mkdir(parents=True)
            (folder/'.rpi5-board.lock').write_text('{"pid":1,"purpose":"stale metadata"}')
            with recorder.lease.hold(root,'first'):
                with self.assertRaisesRegex(ValueError,'Another live'):
                    with recorder.lease.hold(root,'second'):self.fail('Concurrent lease acquired')
            with recorder.lease.hold(root,'released/reacquired'):pass

    def test_exact_installed_pair_binding_and_not_restore_profile(self):
        stage=recorder.staging;plan=stage.load_plan(BOOT);plan['run']='/home/sandrzej/xnu-gate5-fwabi-12345678'
        with tempfile.TemporaryDirectory(prefix='fwabi-recorder-test-',dir=stage.ROOT/'build/rpi5') as name:
            directory=Path(name);(directory/'plan.json').write_text(json.dumps(plan));(directory/'result.json').write_text(json.dumps(receipt(plan)))
            r=recorder.installation(directory);self.assertEqual(r['pair_sha256']['probe.bin'],stage.IMAGE_SHA)
            self.assertEqual(r['pair_sha256']['bl31.bin'],stage.package.builder.FIRMWARE_SHA)
            bad=copy.deepcopy(plan);bad['profile']='firmware-abi-restore';(directory/'plan.json').write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,'not a restored'):recorder.installation(directory)


if __name__=='__main__':unittest.main()
