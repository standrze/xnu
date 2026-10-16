# SPDX-License-Identifier: BSD-2-Clause
"""Actual guard -> PE owners -> client/verifier -> BAR caller composition."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import rp1_bars_root_profile as old

ROOT=old.ROOT
FROZEN=ROOT/'build/rpi5/rp1-bars-root-kernel-20261013-v2/overlay'


def source(folder):
    p=(ROOT/'tools/rpi5/tests/pcie_id_provider_host.cpp').read_text().split('int main()')[0]
    p=old.once(p,'#include "iokit/Kernel/BCM2712RP1ConfigPolicy.h"',
        '#include "pcie_owner_composition_env.inc"\n#include "iokit/Kernel/BCM2712RP1ConfigPolicy.h"')
    p=old.once(p,'#include "loader/rpi5/pcie_released_windows.h"',
        '#include "loader/rpi5/pcie_released_windows.h"\n#include "loader/rpi5/rp1_bars_plan.h"\n#include "rp1_config_trace.h"')
    p=old.once(p,'    struct rpi5_rp1_config_snapshot endpoint;',
        '    struct rpi5_rp1_config_snapshot endpoint;\n    rpi5_rp1_bars_size bars; rpi5_rp1_bars_plan barsPlan;')
    start=p.index('    bool guard()\n');end=p.index('    int admission(',start)
    p=p[:start]+'''    bool actualGuard();
    bool controllerMode=true,claimingIRQ=false,claimingFW=false;
    bcm2712_controller_admission controllerAdmission={trialAdmission};
    unsigned diagGuard=0,diagIOBank=0,diagIOOffset=0,diagIODirection=0,diagIOStage=0,diagIOValue=0;
    unsigned diagRP1Call=0,diagBarsCall=0;int diagRP1RC=0,diagBarsRC=0;
    uint32_t diagRP1Status=0,diagRP1Selector=0;rpi5_rp1_config_trace diagRP1={};
    bool guard(){
        checks++;bool ok=actualGuard();
        /* Explicit endpoint RAM double applies hardwired BAR size bits. */
        const uint32_t masks[6]={0xffffc000,0xffc00000,0xffff0000,0,0,0};
        for(unsigned i=0;i<6;i++)if(memory[0x8010/4+i]==UINT32_MAX)memory[0x8010/4+i]=masks[i];
        return ok;
    }
'''+p[end:]
    p=old.once(p,'        claimAttempted=irqClaimed=fwClaimed=true;', '''        claimAttempted=true;
        rpi5_pcie_watchdog_observation wd;rpi5_pcie_irq_observation irq;rpi5_fw_observation fw;
        assert(pe_rpi5_watchdog_claim_pcie(this,&wd));
        assert(pe_rpi5_pcie_irq_claim(this,&binding,&irq));irqClaimed=true;
        assert(pe_rpi5_pcie_fw_claim(this,&fw));fwClaimed=true;''')
    p=old.once(p,'    static int rp1Acquire(void *);', '''    struct rpi5_rp1_bars_probe barsProbe={};
    static int rp1BarsAuthorize(void *,const rpi5_pcie_config_request *);
    static int rp1BarsWrite(void *,uint32_t,uint32_t,uint32_t);
    static int rp1Acquire(void *);''')
    p=old.once(p,'        cpus=1;phyOwner=this;', '''        fresh_owner_composition();cpus=1;phyOwner=this;
        binding.bridge_reset_id=44;binding.gic_phandle=1;
        binding.bridge_intid[0]=265;binding.bridge_intid[1]=266;
        binding.mip_intid_base=160;binding.mip_intid_count=64;
        for(unsigned i=0;i<4;i++)binding.intx_intid[i]=261+i;''')
    p=old.once(p,'#include "iokit/Kernel/BCM2712RP1ConfigTransport.inc"',
        '#include "actual-guard.inc"\n#include "BCM2712RP1ConfigTransport.inc"\n#include "BCM2712RP1BarsTransport.inc"')
    for name in ('rp1_config_trace.h','BCM2712RP1ConfigTransport.inc','BCM2712RP1BarsTransport.inc'):
        (folder/name).write_bytes((FROZEN/name).read_bytes())
    (folder/'actual-id-provider.inc').write_text((FROZEN/'BCM2712PCIeIDTrialProgress.inc').read_text().split(
        '/* Distinct IOStartIOKit caller invokes this BEFORE any driver matching')[0])
    guard=(FROZEN/'BCM2712PCIeFWTransport.inc').read_text().split('bool BCM2712PCIePHYTransport::guard()',1)[1]
    (folder/'actual-guard.inc').write_text('bool BCM2712PCIePHYTransport::actualGuard()'+guard)
    return p


MAIN=r'''
static void prepared(BCM2712PCIePHYTransport &s){
 s.prepare();s.memory[0x8004/4]=0;s.memory[0x8010/4]=0xffffc000;
 s.memory[0x8014/4]=0xffc00000;s.memory[0x8018/4]=0xffff0000;
 s.binding.outbound_count=1;s.binding.outbound[0]={0x02000000,0,UINT64_C(0x1f00000000),0xfffffffc};
 s.binding.rp1_aperture_size=0x410000;s.binding.gem_bar_offset=0x100000;s.binding.gem_size=0x4000;
 s.binding.clock_bar_offset=0x18000;s.binding.clock_size=0x10038;
}
int main(){
 BCM2712PCIePHYTransport s;prepared(s);bcm2712_rp1_observation out={};
 assert(s.runBoundedRP1Trial(&out));
 assert(!s.diagGuard&&s.diagBarsCall==5&&s.barsProbe.transactions==49&&s.barsProbe.writes_started==12);
 assert(out.bars.present==7&&pm_writes==1&&rpi5_pcie_wdog_lease.state==RPI5_PCIE_WDOG_ARMED);
 assert(s.memory[0x8010/4]==0xffffc000&&s.memory[0x8014/4]==0xffc00000&&s.memory[0x8018/4]==0xffff0000);
 printf("OWNER_COMPOSITION_PASS GUARDS=%u PM_CHECKS=%u SMC_CALLS=%u FW_SEQUENCE=%u TICKS=%llu BAR_TXNS=%u BAR_WRITES=%u\n",
 s.checks,rpi5_pcie_wdog_lease.checks,smc_calls,rpi5_pcie_fw_session.sequence,
 (unsigned long long)model_ticks,s.barsProbe.transactions,s.barsProbe.writes_started);
 return 0;
}
'''


def run_composition(main,trace=False):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);cpp=folder/'host.cpp';cpp.write_text(source(folder)+main)
            if trace:
                from tools.rpi5 import pcie_owner_trace_profile as profile
                env=(ROOT/'tools/rpi5/tests/pcie_owner_composition_env.inc').read_text()
                for name,fn in (('rpi5_pcie_watchdog_owner.inc',profile.pm_source),
                                ('rpi5_pcie_irq_owner.inc',profile.irq_source),('rpi5_pcie_fw_owner.inc',profile.fw_source)):
                    (folder/name).write_text(fn((ROOT/'pexpert/arm'/name).read_text()))
                    env=profile.once(env,'#include "pexpert/arm/'+name+'"','#include "'+str(folder/name)+'"')
                (folder/'pcie_owner_composition_env.inc').write_text(env)
            flags=['-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                '-I',str(ROOT),'-I',str(ROOT/'loader/rpi5'),'-I',str(folder),
                '-I',str(ROOT/'tools/rpi5/tests'),'-I',str(ROOT/'tools/rpi5/tests/pcie_irq_stubs'),
                '-I',str(ROOT/'tools/rpi5/tests/fw_verifier_stubs')]
            objects=[]
            for name in ('pcie_config','rp1_config_snapshot_checked','pcie_released_windows',
                         'rp1_bars_probe','rp1_bars_plan','pcie_watchdog_lease','pcie_irq_mask','pcie_fw_client','pcie_owner_composition_secure'):
                obj=folder/(name+'.o');src=FROZEN/(name+'.c') if name=='rp1_config_snapshot_checked' else ROOT/'loader/rpi5'/(name+'.c')
                if name=='pcie_owner_composition_secure':src=ROOT/'tools/rpi5/tests'/(name+'.c')
                r=subprocess.run(['xcrun','clang','-std=c11',*flags,'-c',str(src),'-o',str(obj)],capture_output=True,text=True,timeout=60)
                if r.returncode:raise AssertionError(r.stderr)
                objects.append(obj)
            exe=folder/'host';r=subprocess.run(['xcrun','clang++','-std=gnu++17',*flags,str(cpp),*map(str,objects),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            if r.returncode:raise AssertionError(r.stderr)
            r=subprocess.run([exe],capture_output=True,text=True,timeout=60)
            if r.returncode:raise AssertionError(r.stderr)
            return r.stdout


class OwnerCompositionTests(unittest.TestCase):
    def test_real_guard_owners_cores_and_bar_caller(self):
        stdout=run_composition(MAIN)
        self.assertIn('OWNER_COMPOSITION_PASS ',stdout)
        print(stdout.strip())


if __name__=='__main__':unittest.main()
