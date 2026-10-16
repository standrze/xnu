# SPDX-License-Identifier: BSD-2-Clause
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import watchdog_recovery_serial_core as core
from tools.rpi5 import serial_watchdog_recovery_trial as recorder

TAG = 'ccee459ca4bb49e4a45c1cfeffe8aeef'


def fixture():
    def line(name, tail): return core.PREFIX+name.encode()+b' TAG='+TAG.encode()+b' '+tail+b'\r\n'
    def numbers(values): return b' '.join(k.encode()+f'=0x{v:016X}'.encode() for k,v in values.items())
    values = dict(FREQUENCY=54000000, START=54000000, DEADLINE=702000000, SAMPLED=54000100,
        ROUTE=0x20, PRIOR=10 << 16, ARMED=15 << 16, FINAL=15 << 16, WAITED=0, CHECKS=0)
    return b''.join((line('ENTRY',b'EL2 NO_XNU NO_CPU_ON PCIE_MMIO=0 DMA=0'),
        line('EL1',b'MMU_CACHE_OFF DAIF_MASKED PRIMARY_ONLY'), line('ARMED',numbers(values)),
        line('CHECKED',numbers(dict(values, FINAL=(15 << 16)-200, WAITED=108000, CHECKS=1))),
        line('RESULT',numbers(dict(RC=0, WRITE_ATTEMPTS=1, LEASE_CALLBACKS=12))),
        line('STOP',b'NO_RELOAD WAIT_FOR_RESET PCIE_MMIO=0 DMA=0 RESET_RETURN_PROVEN=0')))


class RecoverySerialTests(unittest.TestCase):
    def test_exact_protocol_pass_never_claims_physical_recovery(self):
        for data in (fixture(), fixture()+b'  4.43 RPi: BOOTLOADER release VERSION:6219bf00\r\n'):
            result = core.inspect(data, TAG)
            self.assertTrue(result['diagnostic_pass']); self.assertFalse(result['physical_reset_return_proven'])
            self.assertFalse(result['watchdog_destination_proven'])
        self.assertTrue(result['firmware_bootloader_banner_after_stop'])

    def test_stale_wrong_tag_missing_duplicate_reordered_fault_and_nonservicing_violation(self):
        raw = fixture(); lines = raw.splitlines(keepends=True)
        changes = (raw.replace(TAG.encode(), b'0'*32), b''.join(lines[:-1]), raw+lines[2],
            b''.join((lines[1], lines[0], *lines[2:])), raw+core.PREFIX+b'FAULT TAG='+TAG.encode()+b' fault\r\n',
            raw.replace(b'NO_RELOAD',b'RELOAD'), raw.replace(b'LEASE_CALLBACKS=0x000000000000000C',b'LEASE_CALLBACKS=0x000000000000000D'))
        for data in changes:
            with self.subTest(data=data[-100:]), self.assertRaises(ValueError): core.inspect(data,TAG)

    def test_arithmetic_route_countdown_wait_and_result_failures_rejected(self):
        raw = fixture()
        changes = (('DEADLINE',702000000,702000001),('ROUTE',0x20,0x10),('PRIOR',10 << 16,2 << 16),
            ('ARMED',15 << 16,13 << 16),('WAITED',108000,107999),('CHECKS',1,0),('RC',0,0xffffffffffffffff),
            ('WRITE_ATTEMPTS',1,2),('FINAL',(15 << 16)-200,15 << 16))
        for key,old,new in changes:
            data = raw.replace(f'{key}=0x{old:016X}'.encode(),f'{key}=0x{new:016X}'.encode())
            with self.subTest(key=key), self.assertRaises(ValueError): core.inspect(data,TAG)

    def test_actual_recorder_loop_is_zero_tx_and_journals_continuous_bytes(self):
        with tempfile.TemporaryDirectory(prefix='recovery-recorder-test-', dir=recorder.staging.ROOT/'build/rpi5') as name:
            out = Path(name)/'build/rpi5/capture'; out.parent.mkdir(parents=True)
            installed = dict(preflight=dict(trial_tag=TAG))
            attrs = [0,0,0,0,0,0,[0]*32]
            with patch.object(recorder.staging,'ROOT',Path(name)), \
                    patch.object(recorder,'installation',return_value=installed), \
                    patch.object(recorder.staging,'source_pins',return_value={}), \
                    patch.object(recorder.os,'open',return_value=99), patch.object(recorder.os,'close'), \
                    patch.object(recorder.os,'fsync'), patch.object(recorder.os,'read',return_value=fixture()), \
                    patch.object(recorder.os,'write',side_effect=AssertionError('Serial TX forbidden')) as tx, \
                    patch.object(recorder.fcntl,'ioctl'), patch.object(recorder.termios,'tcgetattr',return_value=attrs), \
                    patch.object(recorder.termios,'tcsetattr'), patch.object(recorder.termios,'tcflush'), \
                    patch.object(recorder.select,'select',return_value=([99],[],[])), \
                    patch.object(recorder.time,'monotonic',side_effect=[0,0,0,.01,61]), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(recorder.main(['/dev/cu.usbmodemTest',str(out),'--installation',name,'--seconds','60']),0)
            tx.assert_not_called(); state = json.loads((out/'state.json').read_text())
            self.assertEqual((out/'serial.bin').read_bytes(), fixture()); self.assertEqual(state['transmitted_bytes'],0)
            self.assertTrue(state['continuous_capture']); self.assertFalse(state['reset_return_proven'])
            self.assertTrue(state['diagnostic']['diagnostic_pass'])
            event = json.loads((out/'receive-events.jsonl').read_text())
            self.assertEqual(event['offset'],0); self.assertEqual(event['bytes'],len(fixture()))


if __name__ == '__main__': unittest.main()
