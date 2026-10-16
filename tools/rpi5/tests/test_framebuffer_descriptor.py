# SPDX-License-Identifier: BSD-2-Clause
"""Pure Pi5 framebuffer descriptor/reservation, actual C under sanitizers."""
import copy
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from tools.rpi5.tests.test_pcie_fdt import _encode_fdt, _node

ROOT=Path(__file__).resolve().parents[3]
PATH='/chosen/framebuffer@20000000'


def fixture(ac=2,sc=2):
    cells={'#address-cells':struct.pack('>I',ac),'#size-cells':struct.pack('>I',sc)}
    fb=_node('framebuffer@20000000',{'compatible':b'simple-framebuffer\0',
        'reg':(0x20000000).to_bytes(ac*4,'big')+(0x800000).to_bytes(sc*4,'big'),
        'width':struct.pack('>I',1920),'height':struct.pack('>I',1080),
        'stride':struct.pack('>I',7680),'format':b'x8r8g8b8\0'})
    root=_node('',{'compatible':b'raspberrypi,5-model-b\0brcm,bcm2712\0'},_node('chosen',cells,fb))
    return root


class FramebufferDescriptorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name)
        cls.program=cls.work/'native'
        command=['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
            '-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),
            str(Path(__file__).with_name('framebuffer_descriptor_host.c')),
            *[str(ROOT/'loader/rpi5'/name) for name in ('framebuffer_descriptor.c','fdt.c','ranges.c')],
            '-o',str(cls.program)]
        result=subprocess.run(command,capture_output=True,text=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def check(self,tree,accept=False,apple=0,path=PATH):
        blob=self.work/'fixture.dtb';blob.write_bytes(tree if isinstance(tree,bytes) else _encode_fdt(tree))
        result=subprocess.run([self.program,blob,path,'accept' if accept else 'reject',str(apple)],
                              capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stderr,'')
        self.assertEqual(result.stdout,'FRAMEBUFFER_DESCRIPTOR PASS NO_SCANOUT_CLAIM=1 NO_MMIO=1\n' if accept
                         else 'FRAMEBUFFER_REJECT ATOMIC=1 NO_MMIO=1\n')

    def test_actual_big_endian_formats_widths_and_all_truncations(self):
        for ac in (1,2):
            for sc in (1,2):self.check(fixture(ac,sc),True,1)
        for format in (b'a8r8g8b8\0',b'x8b8g8r8\0',b'a8b8g8r8\0'):
            tree=fixture();tree['children'][0]['children'][0]['properties']['format']=format
            self.check(tree,True,0)

    def test_invalid_geometry_property_duplicates_and_unsupported_contracts(self):
        changes=[('width',struct.pack('>I',1921)),('height',bytes(4)),('stride',struct.pack('>I',7679)),
                 ('reg',struct.pack('>QQ',0x20000000,1)),('reg',struct.pack('>QQ',0x20000000,2**64-1)),
                 ('format',b'r5g6b5\0'),('format',b'x8r8g8b8'),('status',b'disabled\0'),
                 ('format',b'x8r8g8b8\0extra'),('status',b'okay\0\0'),
                 ('memory-region',struct.pack('>I',1)),('clocks',b''),('power-domains',b''),
                 ('lcd-supply',struct.pack('>I',1)),('unhandled-extension',b''),
                 ('display',bytes(4)),('phandle',b'bad'),
                 ('compatible',b'simple-framebuffer\0simple-framebuffer\0')]
        for key,value in changes:
            tree=fixture();tree['children'][0]['children'][0]['properties'][key]=value
            with self.subTest(key=key,value=value):self.check(tree)
        for key in ('reg','width','height','stride','format','compatible'):
            tree=fixture();del tree['children'][0]['children'][0]['properties'][key];self.check(tree)
        tree=fixture();tree['children'][0]['children'].append(copy.deepcopy(tree['children'][0]['children'][0]));self.check(tree)
        tree=fixture();tree['children'].append(copy.deepcopy(tree['children'][0]));self.check(tree)
        tree=fixture();tree['properties']['compatible']=b'raspberrypi,4-model-b\0brcm,bcm2711\0';self.check(tree)
        for path in ('','/','/chosen/framebuffer@020000000','/chosen/framebuffer@20000001',
                     '/chosen/framebuffer@20000000/child','/soc/framebuffer@20000000'):
            self.check(fixture(),path=path)
        tree=fixture();del tree['children'][0]['properties']['#address-cells'];self.check(tree)
        tree=fixture();tree['children'][0]['properties']['ranges']=bytes(4);self.check(tree)
        tree=fixture();tree['children'][0]['properties']['status']=b'disabled\0';self.check(tree)
        tree=fixture();tree['children'][0]['children'][0]['children'].append(_node('unexpected',{}));self.check(tree)
        duplicate=_encode_fdt(fixture()).replace(b'height\0',b'width\0\0')
        self.check(duplicate)
        tree=fixture();tree['properties']['#address-cells']=struct.pack('>I',2)
        del tree['children'][0]['properties']['#address-cells'];self.check(tree)

    def test_real_geometry_and_page_exclusion_atomic_negative_cases(self):
        result=subprocess.run([self.program,'plan'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,'')
        self.assertEqual(result.stdout,'FRAMEBUFFER_PLAN PASS ATOMIC=1 FULL_ALLOCATION_RETAINED=1 NO_MAPPING=1\n')

    def test_actual_a76_freestanding_compilation(self):
        for source in ('framebuffer_descriptor.c','fdt.c','ranges.c'):
            obj=self.work/(source+'.o');dep=self.work/(source+'.d')
            command=['xcrun','clang','-target','aarch64-none-elf','-mcpu=cortex-a76',
                '-std=c11','-O2','-ffreestanding','-fno-builtin','-Wall','-Wextra','-Werror',
                '-I',str(ROOT/'loader/rpi5'),'-MD','-MF',str(dep),'-c',
                str(ROOT/'loader/rpi5'/source),'-o',str(obj)]
            result=subprocess.run(command,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(obj.stat().st_size>0)
            self.assertIn(source,dep.read_text())


if __name__=='__main__':unittest.main()
