# SPDX-License-Identifier: BSD-2-Clause
"""RAM-only route component for future packets, not a new hardware gate.

The full-owner harness retains its explicit allocation/VM/FDT parser/time/MMIO
doubles. Real raw-FDT decode/encoding is separately executed here. No DMA engine
or queue is activated by any path; actual hardware is not accessed.
"""
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from tools.rpi5 import gem_dma_ram_profile as profile
from tools.rpi5 import build_pcie_id_trace_package as private
from tools.rpi5.tests import test_gem_dma_batch_transport as prior
from tools.rpi5.tests.test_pcie_fdt import PINNED,PINNED_SHA256,_encode_fdt,_synthetic_tree
ROOT=profile.ROOT

def integration():
    module=private.load_private(Path(prior.__file__), '_ram_only_actual_owner_host')
    original_source=module.source
    # The function's globals must belong to the private module, not prior.
    actual_native=module.native_provider
    def provider():
        old=module.profile
        module.profile=SimpleNamespace(memory=SimpleNamespace(derive=profile.derive))
        try:return actual_native()
        finally:module.profile=old
    module.native_provider=provider
    def source(folder,main,mutation=None):
        # The older full-owner fixture predates RP1's child DMA binding.
        # Populate that explicit parser-double result, never claim fresh FDT.
        main=profile.change(main,' s.binding.dma[2]={0x03000000,0xfffffff000,0x1000130000,0x1000};',
            ' s.binding.dma[2]={0x03000000,0xfffffff000,0x1000130000,0x1000};\n'
            ' s.binding.rp1_dma_count=3;s.binding.rp1_dma[0]={0x43000000,0x1000000000,0x1000000000,0x1000000000};')
        # Actual underlying transport source is composed by the frozen helper.
        text=original_source(folder,main)
        raw=profile.prior.derive();new=profile.transform(raw)
        for name in ('BCM2712PCIeControllerRun.inc','BCM2712PCIeIDTrialProgress.inc',
                     'BCM2712RP1GEMIdentifyTransport.inc'):
            old=raw[name].decode();replacement=new[name].decode()
            # Full native framework rewrites MMIO leaves in other units; each
            # changed exact statement remains available after those doubles.
            import difflib
            a=old.splitlines(keepends=True);b=replacement.splitlines(keepends=True)
            for op,i,j,k,l in difflib.SequenceMatcher(a=a,b=b,autojunk=False).get_opcodes():
                if op=='equal':continue
                before=''.join(a[i:j]);after=''.join(b[k:l])
                # Framework substitutes the diagnostic entrypoint with its
                # own test main; the sole logging-only delta is not executed.
                if before=='    kprintf("RPI5XNU:PCIEID:BEGIN INBOUND_DISABLED\\n");\n':
                    assert before not in text;continue
                text=profile.change(text,before,after)
        text='#include "rpi5_gem_ram_window.h"\n'+text
        # Compile the new C core into this standalone host TU with C linkage.
        text+='\n'+(ROOT/'iokit/Kernel/rpi5_gem_ram_window.c').read_text()
        return mutation(text) if mutation else text
    module.source=source
    return module

class GEMDMARAMTests(unittest.TestCase):
    def test_actual_decoder_encoding_and_every_field_negative(self):
        with tempfile.TemporaryDirectory(prefix='gem-ram-core-') as d:
            folder=Path(d);exe=folder/'test';dt=folder/'synthetic.dtb'
            dt.write_bytes(_encode_fdt(_synthetic_tree()))
            sources=[ROOT/'tools/rpi5/tests/gem_ram_window_host.c',ROOT/'iokit/Kernel/rpi5_gem_ram_window.c',
                     *[ROOT/'loader/rpi5'/n for n in ('fdt.c','fdt_reg.c','pcie_fdt.c','pcie_windows.c')]]
            subprocess.run(['xcrun','clang','-O1','-g','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I'+str(ROOT/'loader/rpi5'),'-I'+str(ROOT/'iokit/Kernel'),
                *map(str,sources),'-o',str(exe)],check=True,timeout=60)
            self.assertEqual(hashlib.sha256(PINNED.read_bytes()).hexdigest(),PINNED_SHA256)
            for path in (dt,PINNED):
                p=subprocess.run([exe,path],text=True,capture_output=True,timeout=20)
                self.assertEqual(p.returncode,0,p.stderr);self.assertIn('NEGATIVES=152',p.stdout)
    def test_complete_actual_controller_provider_and_unchanged_owner_budget(self):
        m=integration();main=prior.main_source()
        main=profile.change(main,
            ' for(unsigned i=0;i<3;i++)assert(!(s.windows.plan.inbound[i].bar_lo&31));',
            ''' assert(!(s.windows.plan.inbound[0].bar_lo&31) && s.windows.plan.inbound[1].bar_lo==21 &&
            !(s.windows.plan.inbound[2].bar_lo&31));
 assert(bridge[0x4034/4]==21 && bridge[0x4038/4]==16 && bridge[0x40b4/4]==1 && !bridge[0x40b8/4]);
 assert(!(bridge[0x402c/4]&31) && !(bridge[0x403c/4]&31));
 assert(!(bridge[1]&4) && !(bridge[0x8004/4]&4));
 assert(t.pm_checks==64940 && t.fw_sequence==16233);''')
        main=main.replace('NO_ACTIVE_DMA=1','RAM_VIEWPORT_ONLY=1 NO_DMA_EXECUTION=1')
        output=m.run(main);print(output,end='');self.assertIn('PM=64940',output)
    def test_actual_owner_faults_preserve_quarantine_no_unsafe_compensation(self):
        m=integration();original_source=m.source
        def source(folder,main,mutation=None):
            text=original_source(folder,main,mutation)
            # The original fault sets bit0 on a disabled0 encoding. RAM's21
            # already has bit0; flip it so this remains a real corruption.
            return text.replace('self->windows.plan.inbound[1].bar_lo|=1;',
                                'self->windows.plan.inbound[1].bar_lo^=1;')
        m.source=source
        case=m.GEMDMABatchTransportTests()
        case.test_real_caller_first_virtual_boundary_reentry_context_and_identity()
        case.test_actual_batch_owner_failure_retains_partial_cpu_ram_and_device_maps()
    def test_unexpected_endpoint_or_root_bme_never_reaches_ring_staging(self):
        m=integration();base=prior.main_source()
        base=base[:base.index(' assert(ok && s.dmaMemory->state()')]+'''\n
 assert(!ok && !s.dmaRingAttempted && !s.dmaRingsObserved.writes && !s.dmaRingsObserved.reads);
 assert(s.dmaMemory && !dma_model.releases && !dma_model.complete);
 puts("UNEXPECTED_BME_REJECTED_NO_RING_STAGE");return 0;}'''
        for assignment in ('bridge[1]|=4;','bridge[0x8004/4]|=4;'):
            main=profile.change(base,' bcm2712_rp1_observation out={};',
                ' '+assignment+'\n bcm2712_rp1_observation out={};')
            self.assertIn('UNEXPECTED_BME_REJECTED_NO_RING_STAGE',m.run(main))
    def test_exact_primary_source_register_encoding_setup_before_link(self):
        p=ROOT/'build/rpi5/root-forward-primary-80d4218/pcie-brcmstb.c'
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),
            '212ec09ab522c2e7b81638be3db833bb7e3ad62b201a08f9858092f6130ec787')
        s=p.read_text()
        body=s[s.index('static void set_inbound_win_registers'):s.index('static int brcm_pcie_setup')]
        for anchor in ('brcm_pcie_encode_ibar_size(size)','PCIE_MISC_RC_BAR1_CONFIG_LO_SIZE_MASK',
                       'PCIE_MISC_UBUS_BAR1_CONFIG_REMAP_ACCESS_EN_MASK','upper_32_bits(cpu_addr)'):
            self.assertIn(anchor,body)
        setup=s[s.index('static int brcm_pcie_setup'):s.index('static int brcm_pcie_setup')+18000]
        self.assertLess(setup.index('set_inbound_win_registers'),setup.index('pcie->cfg->perst_set(pcie, 0)'))
        # This source ordering is not a claim that every reset register has
        # identical semantics on Pi4/Pi5. Actual programmer keeps its own
        # BCM2712 held-PERST/link-down guards before each window write.
    def test_actual_a76_core_and_real_iokit_provider(self):
        from tools.rpi5 import build_gem_dma_batch_objects as b
        with tempfile.TemporaryDirectory(prefix='gem-ram-target-') as d:
            folder=Path(d);overlay=folder/'overlay';overlay.mkdir()
            for name,data in profile.derive().items():(overlay/name).write_bytes(data)
            for label,source,flags,cwd in b.recipes(folder)[:2]:
                result=subprocess.run([*flags,'-c',str(source),'-o',str(folder/(label+'.o'))],cwd=cwd,
                    capture_output=True,text=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stderr)
            core=folder/'core.o'
            subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin','-fno-stack-protector',
                '-O2','-Wall','-Wextra','-Werror','-I'+str(ROOT/'loader/rpi5'),'-I'+str(ROOT/'iokit/Kernel'),
                '-c',str(ROOT/'iokit/Kernel/rpi5_gem_ram_window.c'),'-o',str(core)],check=True,timeout=60)
            syms=subprocess.check_output(['xcrun','llvm-nm','--undefined-only',core],text=True)
            self.assertEqual(syms.split(),['U','memcpy','U','rpi5_pcie_windows_plan'])
if __name__=='__main__':unittest.main()
