# SPDX-License-Identifier: BSD-2-Clause
import copy
import re
import types
import unittest
from tools.rpi5 import gem_dma_batch_serial as p
from tools.rpi5.tests import test_pcie_gem_capabilities_serial as cap
from tools.rpi5.tests import test_pcie_root_route_serial as full


class BatchSerialTests(unittest.TestCase):
    def fixture(self,actual_report=None):
        data,previous=cap.GEMCapabilitiesSerialTests().fixture()
        report=copy.deepcopy(actual_report) if actual_report else dict(image_bytes=19000000,tag='a'*32,
            root_copy_marker='RPI5XNU:BL33:RAMDISK_MATERIALIZED PA=0000000008200000 BYTES=00000000001d4000 VERIFIED',
            kernel_copy_marker='RPI5XNU:BL33:KERNEL_MATERIALIZED BYTES=0000000001100000 FULL_ENVELOPE_VERIFIED NO_BOOT_ARGS_WRITTEN NO_TRANSFER')
        report['marker']=p.profile.marker(report['tag'])
        report['cpu_ring_contract']=p.contracts.contract()
        report['inherited_capability_contracts']=p.contracts.inherited()
        report['boot_markers']=[report['marker'],p.contracts.HOST,p.contracts.DEVICE,p.contracts.FDT,
            report['root_copy_marker'],report['kernel_copy_marker']]
        data=data[data.index(p.TRANSFER):].replace(b'00070106',b'00070109')
        prefix=b'Boot mode: SD (01)\nRead probe.bin bytes '+str(report['image_bytes']).encode()+b' hnd 1\n'+p.ENTRY+b'2\n'
        data=prefix+b'\n'.join(v.encode() for v in report['boot_markers'])+b'\n'+data
        raw=[0x70109,0x08508513,0x6eb13fff,0x502e5b45,0x08820000,0,0x24444444,0]
        for side in ('BEFORE','AFTER'):
            for half,labels in enumerate(('MID DCFG1 DCFG2 DCFG5','DCFG6 DCFG8 DCFG10 DCFG12')):
                name='CAP_'+side+str(half)
                row=p.PREFIX+name.encode()+b' '+b' '.join(('%s=%08x'%(k,v)).encode() for k,v in zip(labels.split(),raw[half*4:half*4+4]))
                data=re.sub(p.PREFIX+name.encode()+rb' [^\r\n]*',row,data)
        rows=(
            'DMA_OWNER PREPARE=2 STATE=10 ATTEMPTED=1 ACTIVE=0 REVOKED=0 DISABLED=1 RECORD=1',
            'DMA_RECORD FIXED=3 DYNAMIC=1 MANAGED_START=100663296 MANAGED_END=268435456',
            'DMA_ROUTE PHYSICAL=201326592 PCI=68920803328 RP1=68920803328 BYTES=294912',
            'DMA_STAGE STATE=2 ERROR=0 ATTEMPTED=640 WRITTEN=640 READ=640 CALLS=81 CHECKS=164',
            'DMA_RINGS RX=68920803328 TX=68920819712 GENERATION=1000000 BYTES=1280 DESC=16 SLOTS=64 TAIL=256 OWNED=160')
        data=data.replace(p.PREFIX+b'END ',b'\n'.join(p.PREFIX+v.encode() for v in rows)+b'\n'+p.PREFIX+b'END ')
        return data,report

    def test_complete_fixture_and_each_ring_field_negative(self):
        data,report=self.fixture();r=p.inspect(data,report)
        self.assertTrue(r['cpu_ring_trial_pass']);self.assertEqual(r['observed_field_rows'],52)
        self.assertFalse(r['dma']);self.assertFalse(r['queue_publication']);self.assertFalse(r['dma_addressability_qualified'])
        for before,after in ((b'PREPARE=2 STATE=10',b'PREPARE=1 STATE=10'),(b'DISABLED=1',b'DISABLED=0'),
            (b'RECORD=1',b'RECORD=0'),(b'DYNAMIC=1',b'DYNAMIC=0'),(b'PHYSICAL=201326592',b'PHYSICAL=201326593'),
            (b'PCI=68920803328',b'PCI=201326592'),(b'BYTES=294912',b'BYTES=294911'),
            (b'WRITTEN=640',b'WRITTEN=624'),(b'READ=640',b'READ=624'),(b'CALLS=81 CHECKS=164',b'CALLS=80 CHECKS=164'),
            (b'CHECKS=164',b'CHECKS=163'),(b'RX=68920803328',b'RX=201326592'),
            (b'TX=68920819712',b'TX=68920803328'),(b'GENERATION=1000000',b'GENERATION=0'),
            (b'BYTES=1280 DESC=16',b'BYTES=1024 DESC=16'),(b'OWNED=160',b'OWNED=128')):
            with self.subTest(before=before),self.assertRaises(ValueError):p.inspect(data.replace(before,after,1),report)
        for name in p.ADDITIONS:
            row=re.search(p.PREFIX+name.encode()+rb' [^\r\n]*\n',data).group()
            with self.assertRaises(ValueError):p.inspect(data.replace(row,b'',1),report)
            with self.assertRaises(ValueError):p.inspect(data.replace(row,row+row,1),report)
        for value in (1,1.0):
            changed=copy.deepcopy(report);changed['cpu_ring_contract']['cpu_owned_descriptors']=value
            with self.assertRaises(ValueError):p.inspect(data,changed)

    def test_full_capture_api_zero_tx_and_whole_tail_faults(self):
        method=full.RootRouteSerialTests.test_actual_full_inspect_capture_api_with_timed_boot_to_nvme
        types.FunctionType(method.__code__,dict(method.__globals__,p=p))(self)
        data,report=self.fixture()
        for fault in p.health.SIGNATURES:
            for at in (0,data.index(p.PREFIX+b'END'),len(data)):
                with self.assertRaises(ValueError):p.inspect(data[:at]+fault+data[at:],report)

    def test_minus7_propagation_and_partial_memory_never_committed(self):
        data,report=self.fixture()
        data=data.replace(b'OK=1 PHASE=5 LAST=5',b'OK=0 PHASE=6 LAST=14')
        data=data.replace(b'BARS_PRESENT=07',b'BARS_PRESENT=00')
        for i in range(6):
            data=re.sub(p.PREFIX+f'BAR{i} '.encode()+rb'[^\r\n]*',p.PREFIX+f'BAR{i} ORIGINAL=00000000 MASK=00000000 SIZE=00000000 PLAN=00000000 CPU_START=0 CPU_END=0'.encode(),data)
        for name in ('ASSIGNED_BARS','RESTORED_BARS'):
            data=re.sub(p.PREFIX+name.encode()+rb'[^\r\n]*',p.PREFIX+name.encode()+b' '+b' '.join(f'BAR{i}=00000000'.encode() for i in range(6)),data)
        data=re.sub(p.PREFIX+rb'MAPPING [^\r\n]*',p.PREFIX+b'MAPPING BAR1_START=0 BAR1_END=0 GEM_START=0 GEM_END=0 CLOCK_START=0 CLOCK_END=0',data)
        data=data.replace(b'ENABLED=0002',b'ENABLED=0000')
        data=data.replace(b'GEM CALL=2 RC=0 STAGE=5',b'GEM CALL=1 RC=-7 STAGE=6')
        data=data.replace(b'COMMITTED=00070109 HZ=200000000',b'COMMITTED=00000000 HZ=0')
        data=data.replace(b'DECODE CALL=3 RC=0 STATE=8',b'DECODE CALL=1 RC=-7 STATE=9')
        data=data.replace(b'ROOT_MEM CALL=2 RC=0 STAGE=7',b'ROOT_MEM CALL=1 RC=-7 STAGE=8')
        data=data.replace(b'DMA_OWNER PREPARE=2 STATE=10 ATTEMPTED=1 ACTIVE=0',b'DMA_OWNER PREPARE=2 STATE=6 ATTEMPTED=1 ACTIVE=1')
        data=data.replace(b'DMA_STAGE STATE=2 ERROR=0 ATTEMPTED=640 WRITTEN=640 READ=640 CALLS=81 CHECKS=164',
            b'DMA_STAGE STATE=3 ERROR=-5 ATTEMPTED=32 WRITTEN=16 READ=0 CALLS=2 CHECKS=6')
        data=re.sub(p.PREFIX+rb'DMA_RINGS [^\r\n]*',p.PREFIX+b'DMA_RINGS RX=0 TX=0 GENERATION=0 BYTES=0 DESC=0 SLOTS=0 TAIL=0 OWNED=0',data)
        r=p.inspect(data,report)
        self.assertFalse(r['cpu_ring_trial_pass']);self.assertFalse(r['root_memory_forwarding_restored'])
        self.assertEqual(r['root_forward_progress']['rc'],-7)
        self.assertEqual(r['gem_progress']['rc'],-7)
        self.assertEqual(r['decode_telemetry']['rc'],-7)
        with self.assertRaises(ValueError):p.inspect(data.replace(b'ROOT_MEM CALL=1 RC=-7',b'ROOT_MEM CALL=1 RC=-5'),report)
        with self.assertRaises(ValueError):p.inspect(data.replace(b'DMA_RINGS RX=0',b'DMA_RINGS RX=100'),report)
        with self.assertRaises(ValueError):p.inspect(data.replace(b'RC=-7',b'RC=-6'),report)


if __name__=='__main__':unittest.main()
