# SPDX-License-Identifier: BSD-2-Clause
"""Actual pure resolver under ASan/UBSan; synthetic FDT is not same-boot proof."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from tools.rpi5.tests.test_pcie_fdt import _encode_fdt, _node

ROOT=Path(__file__).resolve().parents[3]
def cells(*values):return struct.pack('>'+len(values)*'I',*values)
def fixture(bus='soc@107c000000'):
    return _node('',{'compatible':b'raspberrypi,5-model-b\0brcm,bcm2712\0',
        '#address-cells':cells(2),'#size-cells':cells(2)},
        _node(bus,{'compatible':b'simple-bus\0','#address-cells':cells(1),'#size-cells':cells(1),
            'ranges':cells(0,0x10,0,0x80000000)},
            _node('fb',{'compatible':b'brcm,bcm2708-fb\0','firmware':cells(0x55)}),
            _node('firmware',{'compatible':b'raspberrypi,bcm2835-firmware\0simple-mfd\0',
                '#address-cells':cells(1),'#size-cells':cells(1),'dma-ranges':b'',
                'mboxes':cells(0x22),'phandle':cells(0x55)},
                _node('clocks',{'compatible':b'raspberrypi,firmware-clocks\0','#clock-cells':cells(1)})),
            _node('mailbox@7c013880',{'compatible':b'brcm,bcm2835-mbox\0','reg':cells(0x7c013880,0x40),
                'interrupts':cells(0,33,4),'#mbox-cells':cells(0),'phandle':cells(0x22)})))

class DisplayMailboxFdtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name);cls.program=cls.work/'native'
        cmd=['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
            '-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5'),
            str(Path(__file__).with_name('display_mailbox_fdt_host.c')),
            *[str(ROOT/'loader/rpi5'/p) for p in ('display_mailbox_fdt.c','fdt.c','fdt_reg.c')],
            '-o',str(cls.program)]
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
        if r.returncode:raise AssertionError(r.stderr)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def check(self,tree,accept=False):
        p=self.work/'case.dtb';p.write_bytes(tree if isinstance(tree,bytes) else _encode_fdt(tree))
        r=subprocess.run([self.program,p,'accept' if accept else 'reject'],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'')
        self.assertEqual(r.stdout,'MAILBOX_FDT PASS PHANDLE_CHAIN=1 MMIO_TRANSLATION=1 NO_TRANSPORT=1 NO_BUFFER_AUTHORITY=1\n' if accept else 'MAILBOX_FDT REJECT ATOMIC=1\n')
    def test_supported_topology_phandle_aliases_names_and_every_truncation(self):
        self.check(fixture(),True);self.check(fixture('soc'),True)
        t=fixture();s=t['children'][0];s['children'][0]['name']='display-reference'
        s['children'][1]['name']='coprocessor';s['children'][2]['name']='mailbox-renamed'
        for x in s['children'][1:]:x['properties']['linux,phandle']=x['properties'].pop('phandle')
        for x in [t,s,*s['children']]:x['properties']['status']=b'okay\0'
        self.check(t,True)
        t=fixture();t['children'].append(_node('other-device',{'compatible':b'other\0','iommus':cells(999),'dma-coherent':b''}))
        self.check(t,True)  # not a participant or ancestor
    def test_duplicate_disabled_and_malformed_links_fail_atomically(self):
        for i in range(3):
            t=fixture();s=t['children'][0];other=copy.deepcopy(s['children'][i]);other['name']+='-duplicate'
            other['properties']['status']=b'disabled\0';s['children'].append(other);self.check(t)
        for key,values,index in (
            ('firmware',[cells(0),cells(0xffffffff),cells(0x22),cells(0x55,0),b'bad'],0),
            ('mboxes',[cells(0),cells(0x55),cells(0x22,0),b'bad'],1),
            ('phandle',[cells(0),cells(0xffffffff),cells(0x55),b'bad'],2),
            ('#mbox-cells',[cells(1),b'',b'bad'],2),
            ('compatible',[b'brcm,bcm2835-mbox',b'brcm,bcm2835-mbox\0extra\0',b'brcm,bcm2835-mbox\0brcm,bcm2835-mbox\0'],2)):
            for v in values:
                t=fixture();t['children'][0]['children'][index]['properties'][key]=v;self.check(t)
        for index,key in ((0,'firmware'),(1,'mboxes'),(1,'phandle'),(2,'#mbox-cells'),(2,'phandle')):
            t=fixture();del t['children'][0]['children'][index]['properties'][key];self.check(t)
        t=fixture();t['children'][0]['children'][1]['properties']['linux,phandle']=cells(0x66);self.check(t)
        t=fixture();t['children'].append(_node('unrelated',{'phandle':cells(0x22)}));self.check(t)
        t=fixture();t['children'][0]['children'].append(copy.deepcopy(t['children'][0]['children'][0]));self.check(t)
        # An unrelated string-table property name is changed to an existing consumed name.
        t=fixture();t['children'][0]['children'][0]['properties']['xxxxxxxx']=cells(0x55)
        self.check(_encode_fdt(t).replace(b'xxxxxxxx\0',b'firmware\0'))
    def test_exact_profile_no_inherited_cells_or_guessed_address(self):
        changes=[('reg',cells(0x7c013880,0x44)),('reg',cells(0x7c013880,0)),
            ('reg',cells(0x7c013881,0x40)),('reg',cells(0x7c013880,0x40,0x7c014000,0x40)),
            ('reg',struct.pack('>QQ',0x107c013880,0x40)),('clocks',cells(1)),('resets',cells(1)),
            ('reg-names',b'mailbox\0'),('new-resource',b'')]
        for k,v in changes:
            t=fixture();t['children'][0]['children'][2]['properties'][k]=v;self.check(t)
        for v in (b'',cells(0,0x11,0,0x80000000),cells(0,0x10,0,0xffffffff),
                  cells(0,0x10,0,0x80000000)*2,cells(0x7c013880,0x10,0x7c013880,0x40)):
            t=fixture();t['children'][0]['properties']['ranges']=v;self.check(t)
        for location in range(5):
            for status in (b'disabled\0',b'okay',b'okay\0junk',b'reserved\0'):
                t=fixture();s=t['children'][0];[t,s,*s['children']][location]['properties']['status']=status;self.check(t)
        for location in (0,1,3):
            for key in ('#address-cells','#size-cells'):
                t=fixture();s=t['children'][0];x=[t,s,*s['children']][location];del x['properties'][key];self.check(t)
        for target in ('raspberrypi,4-model-b\0brcm,bcm2711\0','raspberrypi,5-model-b\0brcm,bcm2712'):
            t=fixture();t['properties']['compatible']=target.encode();self.check(t)
        t=fixture();t['children'][0]['name']='otherbus';self.check(t)
        t=fixture();s=t['children'][0];m=s['children'].pop();s['children'].append(_node('nested',{'compatible':b'simple-bus\0'},m));self.check(t)
    def test_dma_iommu_coherency_overrides_and_firmware_sibling_are_not_authority(self):
        keys=('dma-ranges','dma-coherent','dma-noncoherent','dma-parent','dma-mask','dma-address-bits',
            'iommus','iommu-map','iommu-map-mask','#iommu-cells','memory-region','memory-region-names',
            'interconnects','interconnect-names','secure-status')
        for where in range(5):
            for key in keys:
                if where==3 and key=='dma-ranges':continue
                t=fixture();s=t['children'][0];[t,s,*s['children']][where]['properties'][key]=b'';self.check(t)
        for data in (cells(0),cells(0,0,0x80000000)):
            t=fixture();t['children'][0]['children'][1]['properties']['dma-ranges']=data;self.check(t)
        t=fixture();del t['children'][0]['children'][1]['properties']['dma-ranges'];self.check(t)
        for where in (0,2):
            t=fixture();t['children'][0]['children'][where]['children'].append(_node('consumer',{}));self.check(t)
    def test_a76_no_mmio_and_preserved_primary_bytes(self):
        for source in ('display_mailbox_fdt.c','fdt.c','fdt_reg.c'):
            o=self.work/(source+'.o');dep=self.work/(source+'.d')
            cmd=['xcrun','clang','-target','aarch64-none-elf','-mcpu=cortex-a76','-std=c11','-O2',
                '-ffreestanding','-fno-builtin','-Wall','-Wextra','-Werror','-I',str(ROOT/'loader/rpi5'),
                '-MD','-MF',str(dep),'-c',str(ROOT/'loader/rpi5'/source),'-o',str(o)]
            r=subprocess.run(cmd,capture_output=True,text=True,timeout=20);self.assertEqual(r.returncode,0,r.stderr)
            self.assertGreater(o.stat().st_size,0);self.assertIn(source,dep.read_text())
        p=ROOT/'tools/rpi5/display_mailbox_fdt_sources.json';metadata=json.loads(p.read_text())
        self.assertEqual(metadata['commit'],'80d4218cb877ccb07d09a9f21f0678e78d8b36f5')
        expected={'arch/arm64/boot/dts/broadcom/bcm2712.dtsi','arch/arm64/boot/dts/broadcom/bcm2712-rpi.dtsi',
            'drivers/mailbox/bcm2835-mailbox.c','drivers/firmware/raspberrypi.c','include/linux/dma-direct.h',
            'drivers/of/device.c','drivers/of/address.c','arch/arm64/mm/dma-mapping.c',
            'kernel/dma/direct.c','drivers/base/platform.c','arch/arm64/Kconfig'}
        self.assertEqual(len(metadata['sources']),11);self.assertEqual({s['path'] for s in metadata['sources']},expected)
        for item in metadata['sources']:
            data=(ROOT/metadata['directory']/item['path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),item['sha256']);self.assertEqual(len(data),item['bytes'])
            self.assertEqual(item['url'],'https://github.com/raspberrypi/linux/blob/'+metadata['commit']+'/'+item['path'])
        self.assertIs(metadata['hardware_claim'],False);self.assertIs(metadata['sources_compiled_into_helper'],False)

if __name__=='__main__':unittest.main()
