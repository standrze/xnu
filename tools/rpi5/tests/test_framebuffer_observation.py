# SPDX-License-Identifier: BSD-2-Clause
"""Actual read-only FDT inventory under ASan/UBSan, no emulated scanout."""
import copy
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from .test_pcie_fdt import _node,_encode_fdt
from .test_framebuffer_descriptor import fixture as descriptor_fixture
ROOT=Path(__file__).resolve().parents[3]
DTB=ROOT/'build/rpi5/bcm2712-rpi-5-b-2768f610.dtb'
DTB_SHA='399caff4dcf03c55e20b6a4a7907dd8bd1c0cc42a9fc79e0b3b2ad4f7511585a'
SOURCES=('framebuffer_observation.c','framebuffer_descriptor.c','fdt.c','ranges.c')
def fixture(simple=True,mailbox=True):
    root=descriptor_fixture();root['properties'].update({'#address-cells':struct.pack('>I',2),'#size-cells':struct.pack('>I',2)})
    root['children'][0]['properties']['rng-seed']=b'SECRET_VALUE_DO_NOT_LOG'
    if not simple:root['children'][0]['children']=[]
    root['children'].append(_node('memory@0',{'device_type':b'memory\0','reg':struct.pack('>QQ',0,0x40000000)}))
    if mailbox:root['children'].append(_node('soc',{},_node('fb',{'compatible':b'brcm,bcm2708-fb\0','firmware':struct.pack('>I',3)})))
    return root

class FramebufferObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name);cls.program=cls.work/'observe'
        result=subprocess.run(['xcrun','clang','-O1','-g','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
            '-I',str(ROOT/'loader/rpi5'),str(Path(__file__).with_name('framebuffer_observation_host.c')),
            *[str(ROOT/'loader/rpi5'/s) for s in SOURCES],'-o',str(cls.program)],capture_output=True,text=True,timeout=40)
        if result.returncode:raise AssertionError(result.stderr)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def check(self,tree,accept=True):
        p=self.work/'case.dtb';p.write_bytes(tree if isinstance(tree,bytes) else _encode_fdt(tree))
        r=subprocess.run([self.program,p,'accept' if accept else 'reject'],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'');self.assertNotIn('SECRET_VALUE',r.stdout)
        if not accept:self.assertEqual(r.stdout,'REJECT ATOMIC=1\n')
        return r.stdout
    def test_actual_descriptor_mailbox_distinction_absence_and_pinned_pi5_dtb(self):
        value=self.check(fixture());self.assertIn('SIMPLE=0x0000000000000001 MAILBOX_FB=0x0000000000000001',value)
        self.assertIn('PATH=/soc/fb',value);self.assertIn('APPLE_XRGB=0x0000000000000001 LIVE_OVERLAP=0x0000000000000001',value)
        self.assertIn('NO_MAPPING NO_DRAW NO_OWNERSHIP_CLAIM',value)
        self.assertIn('OWNERSHIP_PROVEN=0 CACHE_CONTRACT_PROVEN=0',value)
        self.assertNotIn('GEOMETRY',self.check(fixture(False,True)))
        self.assertIn('NODES=0x0000000000000000',self.check(fixture(False,False)))
        self.assertEqual(hashlib.sha256(DTB.read_bytes()).hexdigest(),DTB_SHA)
        actual=self.check(DTB.read_bytes());self.assertIn('PATH=/soc@107c000000/fb',actual);self.assertNotIn('FBOBS:GEOMETRY',actual)
    def test_unsupported_geometry_cells_and_raw_contracts_remain_observations(self):
        for key,value in [('format',b'a8r8g8b8\0'),('format',b'r5g6b5\0'),('format',b'x8r8g8b8'),
            ('status',b'disabled\0'),('width',b'x'),('reg',b'abc'),('reg',struct.pack('>QQ',0x20000000,1))]:
            tree=fixture();tree['children'][0]['children'][0]['properties'][key]=value
            result=self.check(tree);self.assertIn('APPLE_XRGB=0x0000000000000000',result)
            if value!=b'a8r8g8b8\0':self.assertNotIn('FBOBS:GEOMETRY',result)
        tree=fixture();del tree['children'][0]['properties']['#address-cells'];self.assertNotIn('FBOBS:GEOMETRY',self.check(tree))
        tree=fixture();tree['children'][0]['children'].append(_node('framebuffer@30000000',{'compatible':b'simple-framebuffer\0'}))
        self.assertNotIn('FBOBS:GEOMETRY',self.check(tree))
        tree=fixture();tree['children'].append(_node('reserved-memory',{'#address-cells':struct.pack('>I',2),'#size-cells':struct.pack('>I',2),'ranges':b''},
            _node('firmware@20000000',{'reg':struct.pack('>QQ',0x20000000,0x800000)})))
        self.assertIn('FIXED_OVERLAP=0x0000000000000001',self.check(tree))
    def test_malformed_capacity_paths_atomic_and_formatter_failure(self):
        raw=_encode_fdt(fixture())
        for n in (0,1,4,39,40,len(raw)-1):self.check(raw[:n],False)
        tree=fixture();tree['properties']['compatible']=b'raspberrypi,4-model-b\0brcm,bcm2711\0';self.check(tree,False)
        tree=fixture();tree['children'].append(_node('bad\nnode',{}));self.check(tree,False)
        tree=fixture();tree['children'].append(_node('x'*128,{}));self.check(tree,False)
        tree=fixture();tree['children'].extend(_node('fb'+str(i),{'compatible':b'brcm,bcm2708-fb\0'}) for i in range(4));self.check(tree,False)
        tree=fixture();tree['children'][0]['children'][0]['properties']['compatible']=b'simple-framebuffer\0brcm,bcm2708-fb\0';self.check(tree,False)
        tree=fixture();tree['children'][0]['children'][0]['properties']['compatible']=b'simple-framebuffer';self.check(tree,False)
        r=subprocess.run([self.program,'formatter'],capture_output=True,text=True,timeout=10)
        self.assertEqual((r.returncode,r.stdout,r.stderr),(0,'FORMATTER PASS BOUNDED=1 FAIL_STOP=1\n',''))
    def test_actual_a76_freestanding_compilation(self):
        for name in SOURCES:
            result=subprocess.run(['xcrun','clang','-target','aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align',
                '-ffreestanding','-fno-builtin','-mgeneral-regs-only','-O2','-Wall','-Wextra','-Werror','-c',
                str(ROOT/'loader/rpi5'/name),'-o',str(self.work/(name+'.o'))],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
if __name__=='__main__':unittest.main()
