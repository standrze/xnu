# SPDX-License-Identifier: BSD-2-Clause
"""Offline qualification for the post-board CPU-ring allocation retry."""
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
import unittest
from tools.rpi5 import gem_cpu_ring_retry_profile as profile
from tools.rpi5 import build_gem_dma_batch_objects as objects

ROOT=profile.ROOT
CORE=ROOT/'iokit/Kernel/rpi5_gem_ring_only_batch.c'
HOST=Path(__file__).with_name('gem_ring_only_host.c')

class GEMCPURingRetryTests(unittest.TestCase):
    def test_actual_failure_is_pinned_and_does_not_overclaim_cause(self):
        returned=json.loads(profile.CAPTURE.read_text())
        self.assertEqual(returned['capture_sha256']['serial.bin'],
            '0c701d6e34609fae3c174c1d62bfbcb4ff862c166b80eef5879b459f6802bb53')
        d=returned['diagnostic']
        self.assertEqual(d['cpu_ring_owner'],dict(active=0,attempted=0,disabled=0,
            prepare=3,record=1,revoked=0,state=5))
        self.assertFalse(d['cpu_ring_trial_pass'])
        # Rejected is intentionally multi-cause in v8.  Zero initialized
        # mapping output cannot retrospectively identify its reject site.
        lifecycle=(ROOT/'iokit/Kernel/BCM2712GEMDMARingsLifecycle.inc').read_text()
        self.assertGreaterEqual(lifecycle.count('goto reject'),8)

    def test_successor_exact_scope_and_preparation_boundaries(self):
        files=profile.derive();h=files['BCM2712GEMDMABatch.h'].decode()
        c=files['BCM2712GEMDMABatch.cpp'].decode();progress=files['BCM2712PCIeIDTrialProgress.inc'].decode()
        self.assertIn('AllocationBytes=0x8000',h)
        self.assertNotIn('AllocationBytes=0x48000',h)
        self.assertIn('struct rpi5_gem_ring_only_io ringIO_',h)
        self.assertIn('packet_granule=0',c)
        self.assertNotIn('ringRequest_.packet[r][i]=',c)
        self.assertIn('RPI5XNU:PCIEID:DMA_PREP STEP=%u ERROR=%d BYTES=%llu PACKETS=0',progress)
        for step in range(1,18):self.assertIn(f'prepareStep_={step}',c)
        for error in range(2,15):self.assertIn(f'prepareError_=-{error}',c)
        # Existing, independently qualified RAM route remains the only enabled
        # inbound candidate.  The retry does not introduce another encoder.
        self.assertIn('rpi5_gem_ram_window_match(&binding_,plan)',c)
        self.assertIn('PREFERRED_RAM_ONLY NO_BME',files['BCM2712PCIeIDTrialProgress.inc'].decode())

    def test_ring_only_core_faults_and_target_object(self):
        with tempfile.TemporaryDirectory(prefix='gem-ring-only-') as d:
            folder=Path(d);exe=folder/'host';obj=folder/'core.o'
            p=subprocess.run(['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(CORE.parent),str(HOST),str(CORE),'-o',str(exe)],
                capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stderr)
            p=subprocess.run([exe],capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stderr);self.assertIn('GEM_RING_ONLY_PASS',p.stdout);print(p.stdout,end='')
            p=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                '-mgeneral-regs-only','-ffreestanding','-fno-builtin','-O2','-Wall','-Wextra','-Werror',
                '-I',str(CORE.parent),'-c',str(CORE),'-o',str(obj)],capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(subprocess.check_output(['xcrun','llvm-nm','--undefined-only',obj],text=True),'')

    def test_actual_iokit_transport_and_provider_compile(self):
        with tempfile.TemporaryDirectory(prefix='gem-ring-retry-a76-') as d:
            folder=Path(d);overlay=folder/'overlay';overlay.mkdir()
            for name,data in profile.derive().items():(overlay/name).write_bytes(data)
            compiled=[]
            for label,source,flags,cwd in objects.recipes(folder)[:2]:
                obj=folder/(label+'.o')
                p=subprocess.run([*flags,'-c',str(source),'-o',str(obj)],cwd=cwd,
                    capture_output=True,text=True,timeout=60)
                self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'');compiled.append(obj)
            provider=subprocess.check_output(['xcrun','llvm-objdump','-d',compiled[1]],text=True)
            self.assertIn('s1e1r',provider);self.assertIn('s1e1w',provider);self.assertIn('dsb\tosh',provider)

    def test_primary_linux_ring_allocation_and_route_pins(self):
        macb=ROOT/'build/rpi5/gem-capability-primary-80d4218-20261013/macb_main.c'
        self.assertEqual(hashlib.sha256(macb.read_bytes()).hexdigest(),
            'ec5a8df6096d3a4541e7a17821ef81264ce230aa5676afe276af3aed26cbee87')
        text=macb.read_text();body=text[text.index('static int macb_alloc_consistent'):text.index('static int macb_alloc_consistent')+2500]
        self.assertGreaterEqual(body.count('dma_alloc_coherent'),2)
        self.assertLess(body.index('tx = dma_alloc_coherent'),body.index('rx = dma_alloc_coherent'))
        route=ROOT/'build/rpi5/root-forward-primary-80d4218/pcie-brcmstb.c'
        self.assertEqual(hashlib.sha256(route.read_bytes()).hexdigest(),
            '212ec09ab522c2e7b81638be3db833bb7e3ad62b201a08f9858092f6130ec787')
        self.assertIn('set_inbound_win_registers',route.read_text())

if __name__=='__main__':unittest.main()
