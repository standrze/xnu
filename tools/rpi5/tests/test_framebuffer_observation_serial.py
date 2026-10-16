# SPDX-License-Identifier: BSD-2-Clause
"""Actual native C log to strict serial oracle, no fabricated hardware proof."""
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from .test_framebuffer_observation import ROOT,SOURCES,fixture,_encode_fdt
from tools.rpi5 import framebuffer_observation_serial as protocol
TAG='0123456789abcdef0123456789abcdef'
def capture(body,size,report=None):
    report=report or dict(tag=TAG,loader_live=dict(start=0x9000000,end=0x9040000))
    tag=report['tag'];live=report['loader_live']
    head=(f'RPI5XNU:FBOBS:ENTRY TAG={tag} EL2 NO_XNU NO_CPU_ON ZERO_SERIAL_INPUT\r\n'
        'RPI5XNU:FBOBS:ARMED WATCHDOG=15 SOFTWARE=8 NO_RELOAD\r\n'
        'RPI5XNU:FBOBS:EL1 SCTLR=0x0000000030C50830 DAIF=0x00000000000003C0 CPU_MMU_CACHE_OFF SCANOUT_CACHE_CONTRACT_UNKNOWN\r\n'
        f'RPI5XNU:FBOBS:LIVE LOADER_START=0x{live["start"]:016X} LOADER_END=0x{live["end"]:016X} FDT_START=0x0000000008000000 FDT_BYTES=0x{size:016X} TF_A_POLICY_EXCLUSION_END=0x0000000000080000\r\n')
    tail=(f'RPI5XNU:FBOBS:RESULT TAG={tag} RC=0x0000000000000000 FRAMEBUFFER_ACCESSES=0 MAILBOX_REQUESTS=0 DRAW=0 MIRROR=0\r\n'
        f'RPI5XNU:FBOBS:STOP TAG={tag} NO_RELOAD DESTINATION_UNPROVEN\r\n')
    return head.encode()+body+tail.encode(),report
class FramebufferObservationSerialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name);cls.program=cls.work/'native'
        r=subprocess.run(['xcrun','clang','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
            '-I',str(ROOT/'loader/rpi5'),str(Path(__file__).with_name('framebuffer_observation_host.c')),
            *[str(ROOT/'loader/rpi5'/s) for s in SOURCES],'-o',str(cls.program)],capture_output=True,timeout=40)
        if r.returncode:raise AssertionError(r.stderr)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def actual(self,tree=None,report=None):
        data=_encode_fdt(tree or fixture());f=self.work/'fixture';f.write_bytes(data)
        r=subprocess.run([self.program,f,'accept'],capture_output=True,timeout=10)
        self.assertEqual((r.returncode,r.stderr),(0,b''))
        return capture(r.stdout,len(data),report)
    def test_actual_native_formatter_is_admitted_without_ownership_claim(self):
        for simple,mailbox in ((True,True),(True,False),(False,True),(False,False)):
            data,report=self.actual(fixture(simple,mailbox));result=protocol.inspect(data,report)
            self.assertTrue(result['diagnostic_pass']);self.assertFalse(result['ownership_proven']);self.assertFalse(result['scanout_cache_contract_proven'])
            self.assertEqual(len(result['nodes']),int(simple)+int(mailbox))
    def test_corrupted_reordered_missing_extra_and_fault_rows_rejected(self):
        data,report=self.actual()
        mutations=[data.replace(TAG.encode(),b'0'*32),data.replace(b'NO_RELOAD',b'RELOAD'),
            data.replace(b'MAILBOX_REQUESTS=0',b'MAILBOX_REQUESTS=1'),data.replace(b'OWNERSHIP_PROVEN=0',b'OWNERSHIP_PROVEN=1'),
            data.replace(b'SIMPLE=0x0000000000000001',b'SIMPLE=0x0000000000000002'),
            data.replace(b'DAIF=0x00000000000003C0',b'DAIF=0x0000000000000000'),
            data.replace(b'PATH=/soc/fb',b'PATH=/soc/fb\nEVIL'),
            data.replace(b'RPI5XNU:FBOBS:RESULT',b'panic: failing\nRPI5XNU:FBOBS:RESULT'),data[:-10],
            data.replace(b'RPI5XNU:FBOBS:RESULT',b'unexpected other output\nRPI5XNU:FBOBS:RESULT'),
            data.replace(b'RESULT TAG=',b'FAULT TAG='),data+data,
            data.replace(b'WORDS=0x0000000000000004',b'WORDS=0x0000000000000005')]
        rows=data.splitlines(keepends=True);mutations+=[b''.join(rows[:4]+rows[5:]),b''.join(rows[:5]+[rows[6],rows[5]]+rows[7:])]
        for n,raw in enumerate(mutations):
            with self.subTest(n=n),self.assertRaises(ValueError):protocol.inspect(raw,report)
        bad=copy.deepcopy(report);bad['loader_live']['end']+=1
        with self.assertRaises(ValueError):protocol.inspect(data,bad)
if __name__=='__main__':unittest.main()
