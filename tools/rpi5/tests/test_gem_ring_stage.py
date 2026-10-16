# SPDX-License-Identifier: BSD-2-Clause
"""Actual staging core: RAM/provider doubles are not physical DMA authority."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / 'iokit/Kernel/rpi5_gem_ring_stage.c'


class GEMRingStageTests(unittest.TestCase):
    def test_actual_ram_codec_lifecycle_faults_sanitized(self):
        with tempfile.TemporaryDirectory(prefix='gem-ring-stage-') as directory:
            binary = Path(directory) / 'host'
            subprocess.run(['xcrun','clang','-std=c11','-O2','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-I',str(CORE.parent),
                            str(Path(__file__).with_name('gem_ring_stage_host.c')),str(CORE),
                            '-o',str(binary)],check=True,timeout=60)
            result = subprocess.run([str(binary)],capture_output=True,text=True,timeout=180)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(result.stdout,
                'GEM_RING_STAGE_PASS events=2661 owners=2708 writes=640 reads=640 held=160 NO_DMA_PROOF\n')

    def test_target_a76_no_unresolved_symbols_or_device_access(self):
        with tempfile.TemporaryDirectory(prefix='gem-ring-target-') as directory:
            obj=Path(directory)/'ring.o'
            subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                            '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin',
                            '-fno-stack-protector','-O2','-Wall','-Wextra','-Werror','-c',
                            str(CORE),'-o',str(obj)],check=True,timeout=60)
            undefined=subprocess.check_output(['xcrun','llvm-nm','--undefined-only',str(obj)],text=True)
            self.assertEqual(undefined.strip(),'')
            asm=subprocess.check_output(['xcrun','llvm-objdump','-d',str(obj)],text=True)
            self.assertIn('<rpi5_gem_ring_stage>:',asm)
            self.assertIn('<rpi5_gem_ring_stage_access_allowed>:',asm)
            instructions=re.findall(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+(\w+)',asm,re.M)
            self.assertTrue(instructions)
            self.assertFalse(set(instructions)&{'smc','hvc','mrs','msr','dc','ic'})
            # All hardware/cache authority belongs to an absent real provider.
            text=CORE.read_text()
            self.assertNotIn('volatile uint32_t *',text)

    def test_exact_primary_descriptor_prefetch_and_apple_provider_sources(self):
        metadata=json.loads((ROOT/'tools/rpi5/gem_ring_stage_sources.json').read_text())
        for row in metadata['sources']:
            data=(ROOT/row['path']).read_bytes()
            self.assertEqual(len(data),row['bytes'])
            self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256'])
        linux=(ROOT/metadata['sources'][1]['path']).read_text()
        header=(ROOT/metadata['sources'][0]['path']).read_text()
        for text in ('word 3: upper 32 bit address of Data Buffer',
                     'return macb_dma_desc_get_size(bp) * bp->tx_ring_size + bp->tx_bd_rd_prefetch;',
                     'return macb_dma_desc_get_size(bp) * bp->rx_ring_size + bp->rx_bd_rd_prefetch;',
                     'upper_32_bits(tx_dma) != upper_32_bits(tx_dma + size - 1)',
                     'upper_32_bits(rx_dma) != upper_32_bits(rx_dma + size - 1)',
                     'desc->ctrl = MACB_BIT(TX_USED);',
                     'MACB_BIT(RX_WRAP) | MACB_BIT(RX_USED)'):
            self.assertIn(text,linux)
        for name in ('rx','tx'):
            self.assertRegex(linux,rf'{name}_bd_rd_prefetch = \(2 << \(val - 1\)\) \*\s+macb_dma_desc_get_size\(bp\);')
        for name,offset in (('RX_USED',0),('RX_WRAP',1),('TX_USED',31),('TX_WRAP',30)):
            self.assertRegex(header,rf'#define\s+MACB_{name}_OFFSET\s+{offset}\b')
        for name,offset in (('TXBD_RDBUFF',12),('RXBD_RDBUFF',8),('DAW64',23)):
            self.assertRegex(header,rf'#define\s+GEM_{name}_OFFSET\s+{offset}\b')
        self.assertEqual((2<<(4-1))*16,256)
        self.assertEqual(64*16+256,1280)
        for direction in ('TX','RX'):
            self.assertRegex(linux,rf'#define\s+MIN_{direction}_RING_SIZE\s+64\b')
        rp1=linux.split('static const struct macb_config raspberrypi_rp1_config = {',1)[1].split('};',1)[0]
        self.assertNotIn('MACB_CAPS_BD_RD_PREFETCH',rp1)
        apple=(ROOT/metadata['sources'][2]['path']).read_text()
        for text in ('gen64IOVMSegments','setMemoryDescriptor','prepare','complete','may block'):
            self.assertIn(text,apple)
        buffer=(ROOT/metadata['sources'][3]['path']).read_text()
        self.assertIn('inTaskWithOptions',buffer)
        self.assertIn('kIOMapInhibitCache',buffer)
        self.assertIn('should not be called from interrupt level',buffer)


if __name__=='__main__':
    unittest.main()
