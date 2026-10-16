# SPDX-License-Identifier: BSD-2-Clause
"""Execute the actual new loader handoff block, with real FDT/ADT/map cores."""
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import build_gem_dma_batch_trial as b
from tools.rpi5.tests.test_pcie_fdt import _synthetic_tree, _encode_fdt, _cells


class BatchLoaderTests(unittest.TestCase):
    def test_actual_derived_handoff_and_kernel_decoder(self):
        text=b.derived_sources()['probe_main.c'].decode()
        start=text.index('    static struct rpi5_memory_types pcie_types;')
        end=text.index('    types=rp1_types;',start)+len('    types=rp1_types;')
        block=text[start:end]
        self.assertEqual(block.count('rpi5_pcie_device_handoff('),1)
        self.assertEqual(block.count('rpi5_rp1_device_handoff('),1)
        self.assertLess(end,text.index('rpi5_display_xnu_types',end))
        # Function parameters name the actual local variables. The block itself
        # is byte-for-byte the generated loader body, not a hand-written model.
        function='''\nstatic int actual_loader_map(uintptr_t fdt_pa,size_t fdt_length,
            struct rpi5_memory_types types,struct rpi5_memory_types *result) {
        '''+block+'''\n *result=types;return 1; }\n'''
        host=(b.ROOT/'tools/rpi5/tests/rp1_device_handoff_host.c').read_text()
        host=host.replace('static void reject_rp1',function+'\nstatic void reject_rp1',1)
        anchor='assert(!rpi5_rp1_device_handoff(data+4,length,&host,&out));'
        self.assertEqual(host.count(anchor),1)
        host=host.replace(anchor,'assert(actual_loader_map((uintptr_t)(data+4),length,in,&out));',1)
        # Retain original real-map decoder negatives and additionally serialize
        # the actual derived result through the actual Apple device tree.
        anchor='assert(!rpi5_memory_types_encode(&out,encoded,sizeof encoded,&written));'
        extra='''
    struct rpi5_board_tree tree;const uint64_t affinities[1]={0};
    assert(!rpi5_board_tree_init(affinities,1,0,54000000,
        (struct rpi5_range){0x107d001000,0x107d001200},0,0x200000000,&tree));
    assert(!rpi5_board_tree_memory_map(&tree,&out));
    unsigned char adt[16384];size_t adt_bytes=0;
    assert(!rpi5_adt_encode(&tree.root,adt,sizeof adt,&adt_bytes));
    unsigned hits=0;
    for(size_t i=0;i+written<=adt_bytes;i++)if(!memcmp(adt+i,encoded,written))hits++;
    assert(hits==1);
'''
        host=host.replace(anchor,anchor+extra,1)
        tree=_synthetic_tree();bad=copy.deepcopy(tree)
        bad['children'][1]['children'][0]['properties']['num-lanes']=_cells(1)
        with tempfile.TemporaryDirectory(prefix='batch-loader-map-') as directory:
            work=Path(directory);source=work/'host.c';source.write_text(host);exe=work/'host'
            names=('rp1_device_handoff','pcie_device_handoff','pcie_fdt','fdt','fdt_reg',
                'memory_type','board_tree','cpu_tree','serial_tree','apple_dt')
            p=subprocess.run(['xcrun','clang','-std=c11','-O2','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(b.ROOT/'loader/rpi5'),
                '-I',str(b.ROOT/'tools/rpi5/tests'),str(source),
                *[str(b.ROOT/'loader/rpi5'/(n+'.c')) for n in names],'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stderr)
            for i,(raw,mode) in enumerate(((_encode_fdt(tree),'accept'),(_encode_fdt(bad),'reject'),(b'bad fdt','reject'))):
                data=work/(str(i)+'.dtb');data.write_bytes(raw)
                p=subprocess.run([exe,data,mode],capture_output=True,text=True,timeout=10)
                self.assertEqual(p.returncode,0,p.stderr)

    def test_loader_owner_order_and_no_secondary_cpu(self):
        text=b.derived_sources()['probe_main.c'].decode()
        self.assertNotIn('rpi5_psci_cpu_on',text)
        self.assertNotIn('start_secondaries',text)
        self.assertIn('command_line = "'+b.profile.BOOTARGS+'";',text)
        self.assertLess(text.index('rpi5_pcie_device_handoff('),text.index('rpi5_rp1_device_handoff('))
        self.assertIn('rpi5_reservation_record_finalize',b.derived_sources()['firmware_seed_tree.c'].decode())
        self.assertIn('RPI5XNU:BL33:RP1_DEVICE_HANDOFF RANGES=2 PAGES=6',text)


if __name__=='__main__':unittest.main()
