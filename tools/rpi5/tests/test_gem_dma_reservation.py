# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
import unittest
from tools.rpi5 import gem_dma_reservation_profile as profile
from tools.rpi5.tests.test_pcie_fdt import _synthetic_tree,_encode_fdt,_node,_cells
ROOT=profile.ROOT

def memory_fixture(seed=bytes(64)):
    root=_synthetic_tree()
    root['children'] += [_node('memory@0',{'device_type':b'memory\0',
        'reg':_cells(0,0,0,0x3f800000,0,0x40000000,0,0xc0000000,1,0,1,0)}),
        _node('reserved-memory',{'#address-cells':_cells(2),'#size-cells':_cells(2),'ranges':b''},
            _node('linux,cma',{'compatible':b'shared-dma-pool\0','reusable':b'',
                'size':_cells(0,0x4000000),'alignment':_cells(0,1),
                'alloc-ranges':_cells(0,0,0,0x40000000)})),
        _node('chosen',{} if seed is None else {'rng-seed':seed})]
    return _encode_fdt(root)

class GEMDMAReservationTests(unittest.TestCase):
    def test_actual_fdt_codec_kernel_body_and_original_apple_digest(self):
        with tempfile.TemporaryDirectory(prefix='reservation-kernel-host-') as d:
            folder=Path(d);data=memory_fixture();fdt=folder/'firmware.dtb';fdt.write_bytes(data)
            sources=[ROOT/'tools/rpi5/tests/reservation_kernel_host.c',ROOT/'osfmk/arm64/rpi5_reservation_kernel.c']
            sources += [ROOT/'loader/rpi5'/p for p in ('fdt.c','fdt_reg.c','ranges.c','reservations.c','reservation_record.c','firmware_seed_fdt.c')]
            sources += [ROOT/'osfmk/corecrypto'/p for p in ('ccdigest_init.c','ccdigest_update.c','ccdigest_final_64be.c',
                'ccsha256_ltc_di.c','ccsha256_ltc_compress.c','ccsha256_K.c','ccsha256_initial_state.c','cc_clear.c')]
            exe=folder/'test'
            p=subprocess.run(['xcrun','clang','-std=c11','-O1','-g','-fsanitize=address,undefined',
                '-D__STDC_WANT_LIB_EXT1__=1','-DCC_USE_ASM=0','-DCC_DIT_MAYBE_SUPPORTED=0','-I',str(ROOT),'-iquote',str(ROOT/'osfmk'),
                '-idirafter',str(ROOT/'EXTERNAL_HEADERS'),'-I',str(ROOT/'osfmk/corecrypto'),
                *map(str,sources),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stderr)
            bad=[]
            for i,seed in enumerate((bytes([1])+bytes(63),None,bytes(63),bytes(65))):
                path=folder/f'bad-seed-{i}.dtb';path.write_bytes(memory_fixture(seed));bad.append(path)
            p=subprocess.run([exe,fdt,hashlib.sha256(data).hexdigest(),*bad],capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stderr);self.assertIn('ACTUAL_FDT_KERNEL_APPLE_SHA_BIND_PASS',p.stdout);print(p.stdout,end='')

    def test_actual_overlay_and_target_boot_binding(self):
        from tools.rpi5.build_display_xnu_console import compiler_flags
        report=json.loads((profile.ARM.parent/'manifest.json').read_text())
        row=next(r for r in report['commands'] if r['log'].endswith('/arm_init-compile.log'))
        text=profile.arm(profile.ARM.read_text())
        self.assertLess(text.index('rpi5_boot_reservation_bind(reservation_wire'),text.index('\tarm_vm_init(xmaxmem, args);'))
        self.assertGreater(text.index('rpi5_boot_reservations_ready=1'),text.index('\tarm_vm_init(xmaxmem, args);'))
        self.assertIn('rpi5_display_contract.loader_start',text)
        self.assertIn('round_page(segHIGHESTKC ? segHIGHESTKC : getlastkerneladdr())',text)
        with tempfile.TemporaryDirectory(prefix='reservation-arm-') as d:
            folder=Path(d);source=folder/'arm_init.c';source.write_text(text);obj=folder/'arm.o'
            args=compiler_flags(row['command'],profile.ARM)
            p=subprocess.run(args+['-I',str(ROOT),'-I',str(ROOT/'osfmk'),'-c',str(source),'-o',str(obj)],
                cwd=row['cwd'],capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stderr)
            warnings=[s for s in p.stderr.splitlines() if 'warning:' in s]
            self.assertEqual(len(warnings),1);self.assertIn("variable 'cnt' set but not used",warnings[0])
            symbols=subprocess.check_output(['xcrun','nm','-ju',obj],text=True)
            for name in ('_ccsha256_ltc_di','_ccdigest_init','_ccdigest_update','_rpi5_reservation_kernel_validate'):
                self.assertIn(name,symbols)

if __name__=='__main__':unittest.main()
