# SPDX-License-Identifier: BSD-2-Clause
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.rpi5 import pcie_access_serial_core as core
from tools.rpi5 import serial_pcie_access_trial as recorder


def fixture():
    lines=[b'RPI5XNU:ACCESS:ENTRY EL2 READONLY_CANDIDATE NO_XNU NO_CPU_ON',
        b'RPI5XNU:ACCESS:EL1 MMU_CACHE_OFF DAIF_MASKED PRIMARY_ONLY',
        b'RPI5XNU:ACCESS:ARMED WATCHDOG_15S NO_RELOAD FATAL_ONLY']
    def line(kind,values):return core.PREFIX+kind.encode()+b' '+b' '.join(k.encode()+f'=0x{v:016X}'.encode() for k,v in values.items())
    for read in range(30):
        address,width=core.REGISTERS[read%15]
        lines.append(line('READ_BEGIN',dict(PASS=read//15,INDEX=read%15,PA=address,WIDTH=width)))
        lines.append(line('READ_END',dict(PASS=read//15,INDEX=read%15,VALUE=read+1)))
    lines.extend((line('RESULT',dict(RC=0,CALLBACKS=184)),
        b'RPI5XNU:ACCESS:OBSERVED READS=30 PCIE_WRITES=0 CONFIG_ACCESS=0 DMA=0 NIC_READY=0 ELAPSED_US=0x0000000000012345',
        b'RPI5XNU:ACCESS:STOP NO_RELOAD WAIT_FOR_RESET DESTINATION_UNPROVEN'))
    return b'\r\n'.join(lines)+b'\r\n'


class AccessSerialTests(unittest.TestCase):
    def test_exact_30_pairs_without_link_network_or_reset_claim(self):
        report=core.inspect(fixture(),core.IMAGE_SHA)
        self.assertTrue(report['access_observation_pass']);self.assertEqual(report['reads'],30)
        self.assertFalse(report['nic_ready']);self.assertFalse(report['physical_reset_return_proven'])
        inventory=core.inventory(fixture());self.assertEqual(inventory['read_begins'],30);self.assertEqual(inventory['read_ends'],30)

    def test_missing_duplicate_reordered_fault_wrong_width_address_and_flags_rejected(self):
        data=fixture();lines=data.splitlines(keepends=True)
        cases=(b''.join(lines[:-1]),data+lines[3],b''.join((*lines[:3],lines[4],lines[3],*lines[5:])),
            data+core.PREFIX+b'FAULT STAGE=0x0000000000000001\r\n',
            data.replace(b'WIDTH=0x0000000000000002',b'WIDTH=0x0000000000000004',1),
            data.replace(b'PA=0x0000001001504338',b'PA=0x000000100150433C',1),
            data.replace(b'NIC_READY=0',b'NIC_READY=1'),data.replace(b'CALLBACKS=0x00000000000000B8',b'CALLBACKS=0x00000000000000B7'))
        for raw in cases:
            with self.assertRaises(ValueError):core.inspect(raw,core.IMAGE_SHA)
        with self.assertRaises(ValueError):core.inspect(data,'0'*64)

    def test_all_thirty_invalid_values_and_every_missing_pair_rejected(self):
        lines=fixture().splitlines(keepends=True)
        for read in range(30):
            wrong=list(lines);width=core.REGISTERS[read%15][1]
            wrong[4+read*2]=wrong[4+read*2].replace(f'VALUE=0x{read+1:016X}'.encode(),f'VALUE=0x{(1<<(width*8))-1:016X}'.encode())
            with self.subTest(read=read),self.assertRaises(ValueError):core.inspect(b''.join(wrong),core.IMAGE_SHA)
            with self.assertRaises(ValueError):core.inspect(b''.join(lines[:3+2*read]+lines[5+2*read:]),core.IMAGE_SHA)

    def test_actual_receive_only_loop_and_partial_inventory(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();out=root/'build/rpi5/capture';out.parent.mkdir(parents=True)
            installed=dict(preflight=dict(image_sha256=core.IMAGE_SHA));attrs=[0,0,0,0,0,0,[0]*32]
            with patch.object(recorder.staging,'ROOT',root),patch.object(recorder,'installation',return_value=installed), \
                    patch.object(recorder.staging,'source_pins',return_value={}),patch.object(recorder.os,'open',return_value=99), \
                    patch.object(recorder.os,'close'),patch.object(recorder.os,'fsync'),patch.object(recorder.os,'read',return_value=fixture()), \
                    patch.object(recorder.os,'write',side_effect=AssertionError('No serial TX')) as tx, \
                    patch.object(recorder.fcntl,'ioctl'),patch.object(recorder.termios,'tcgetattr',return_value=attrs), \
                    patch.object(recorder.termios,'tcsetattr'),patch.object(recorder.termios,'tcflush'), \
                    patch.object(recorder.select,'select',return_value=([99],[],[])), \
                    patch.object(recorder.time,'monotonic',side_effect=[0,0,0,.01,61]),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(recorder.main(['/dev/cu.usbmodemTest',str(out),'--installation',name,'--seconds','60']),0)
            tx.assert_not_called();state=json.loads((out/'state.json').read_text())
            self.assertTrue(state['diagnostic']['access_observation_pass']);self.assertEqual(state['transmitted_bytes'],0)
            self.assertEqual(state['access_inventory']['read_ends'],30)
        partial=core.inventory(b'\r\n'.join(fixture().splitlines()[:4]))
        self.assertEqual(partial['read_begins'],1);self.assertEqual(partial['read_ends'],0)


if __name__=='__main__':unittest.main()
