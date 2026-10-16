# SPDX-License-Identifier: BSD-2-Clause
"""Full frozen controller/caller/owners under explicit fast RAM/clock doubles.

Unlike the earlier post-link fixture, no reset/SerDes/controller session is
fabricated COMPLETE. Mapping/FDT/IOKit scheduling are not executed; this is
transaction accounting, not a physical timing or budget-adequacy claim.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import rp1_bars_root_profile as util

ROOT=util.ROOT
FROZEN=ROOT/'build/rpi5/pcie-owner-trace-kernel-20261013-v1/overlay'
AXI=ROOT/'build/rpi5/pcie-axi-trace-kernel-20261013-v2/overlay'


def expand(path):
    text=path.read_text()
    def include(m):
        name=m[1]
        if not name.endswith('.inc'):return m[0]
        if name=='BCM2712FirmwareFDTTransport.inc':return ''
        target=FROZEN/name
        if not target.exists():target=ROOT/'iokit/Kernel'/name
        value=expand(target)
        if name=='BCM2712PCIeIDTrialProgress.inc':
            value=value.split('/* Distinct IOStartIOKit caller invokes this BEFORE any driver matching')[0]
        return value
    return re.sub(r'#include "([^"]+\.inc)"',include,text)


def source(folder,composed=False,main=None,mutation=None):
    env=(ROOT/'tools/rpi5/tests/pcie_owner_composition_env.inc').read_text()
    for name in ('rpi5_pcie_watchdog_owner.inc','rpi5_pcie_irq_owner.inc','rpi5_pcie_fw_owner.inc'):
        env=util.once(env,'#include "pexpert/arm/'+name+'"','#include "'+str(FROZEN/name)+'"')
    header=(FROZEN/'BCM2712PCIePHYTransport.h').read_text()
    header=re.sub(r'#include <IOKit/[^>]+>\n','',header).replace('private:','public:').replace('protected:','public:')
    header=header.replace('"../../loader/','"'+str(ROOT)+'/loader/').replace('"../../pexpert/','"'+str(ROOT)+'/pexpert/')
    header=util.once(header,'    bool guard();','    bool guard(); bool actualGuard();\n    unsigned guards[32]={};')
    body=expand(FROZEN/'BCM2712PCIePHYTransport.cpp')
    body=body[body.index('bool BCM2712PCIePHYTransport::onOwnerThread()'):]
    # Exclude preparation/map/destruction, never any claimed runtime method.
    start=body.index('bool BCM2712PCIePHYTransport::mapBanks()')
    end=body.index('int BCM2712PCIePHYTransport::read32(',start)
    body=body[:start]+body[end:]
    if composed:
        from tools.rpi5 import pcie_guard_composition_profile
        body=pcie_guard_composition_profile.guard_source(body)
    body=body.replace('bool BCM2712PCIePHYTransport::guard()', 'bool BCM2712PCIePHYTransport::actualGuard()')
    body=re.sub(r'__asm__ volatile\("[^"\n]*" ::: "memory"\);','/* host ordering double */',body)
    body=util.once(body,'uint32_t value = *reinterpret_cast<volatile uint32_t *>(registers[bank] + offset);',
        'uint32_t value = model_read(bank,offset);')
    body=util.once(body,'*reinterpret_cast<volatile uint32_t *>(registers[bank] + offset) = value;',
        'model_write(bank,offset,value);')
    text=env+STUBS+header+'\nstatic BCM2712PCIePHYTransport *phyOwner;\n'+body+WRAPPER+(main or MAIN)
    return mutation(text) if mutation else text


STUBS=r'''
#include <cstdio>
#define RPI5_PCIE_ID_TRIAL 1
#define RPI5_RP1_CONFIG_DIAGNOSTIC 1
#define RPI5_PCIE_UBUS_DIAGNOSTIC 1
#define RPI5_PCIE_UNUSED_DIAGNOSTIC 1
#define RPI5_PCIE_PROFILE_QOS_DIAGNOSTIC 1
#define RPI5_PCIE_CLOCK_DIAGNOSTIC 1
#define OSDeclareDefaultStructors(x)
struct OSData{};struct IOMemoryMap{};
struct IOService {bool opened=true;bool isOpen(const void*)const{return opened;}void retain(){};virtual void free(){}};
static unsigned ml_get_cpu_count(){return 1;}
static bool ml_set_interrupts_enabled(bool){return false;}
static void clock_get_uptime(uint64_t *v){*v=model_ticks;}
static void absolutetime_to_nanoseconds(uint64_t v,uint64_t *out){*out=v*1000000000/model_frequency;}
static void IODelay(uint32_t us){model_ticks+=(uint64_t)us*model_frequency/1000000;}
static uint32_t bridge[0x9310/4],resets[0x30/4],rescal[4];
static bool link_released;static uint64_t link_released_at;
static uint32_t model_read(unsigned bank,uint32_t off){
 if(bank==2)return resets[off/4];if(bank==1)return off==8?1:rescal[off/4];
 if(off==0x1104)return bridge[off/4]&0xffff;
 if(off==0x4068&&link_released&&model_ticks-link_released_at>=model_frequency/10)bridge[off/4]=0x3e0b0;
 return bridge[off/4];
}
static void model_write(unsigned bank,uint32_t off,uint32_t v){
 if(bank==2){if(off==0x18)resets[8]|=v;else if(off==0x1c)resets[8]&=~v;else assert(false);return;}
 if(bank==1){rescal[off/4]=v;return;}
 if(off==0x416c)v&=~0x3800u; // Explicit observed C1 RES0 field model.
 if(off==0x4064&&(v&4)){link_released=true;link_released_at=model_ticks;}
 bridge[off/4]=v;
}
'''


WRAPPER=r'''
void BCM2712PCIePHYTransport::free(){}
bool BCM2712PCIePHYTransport::guard(){
 unsigned p=getPhase();assert(p<32);guards[p]++;
 bool ok=actualGuard();
 const uint32_t masks[6]={0xffffc000,0xffc00000,0xffff0000,0,0,0};
 for(unsigned i=0;i<6;i++)if(bridge[0x8010/4+i]==UINT32_MAX)bridge[0x8010/4+i]=masks[i];
 return ok;
}
'''


MAIN=r'''
int main(){
 fresh_owner_composition();model_frequency=54000000;
 BCM2712PCIePHYTransport s;IOService provider;IOMemoryMap maps[3];
 s.ownerProvider=&provider;s.ownerThread=current_thread();s.providerOpened=true;phyOwner=&s;
 for(unsigned i=0;i<3;i++)s.maps[i]=&maps[i];
 s.registers[0]=(uintptr_t)bridge;s.registers[1]=(uintptr_t)rescal;s.registers[2]=(uintptr_t)resets;
 s.binding.bridge_regs={0x1000120000,0x1000129310};
 s.binding.rescal_regs={0x1000119500,0x1000119510};
 s.binding.bridge_reset_regs={0x1001504318,0x1001504348};
 s.binding.bridge_reset_id=44;s.binding.gic_phandle=1;
 s.binding.bridge_intid[0]=265;s.binding.bridge_intid[1]=266;
 s.binding.mip_intid_base=160;s.binding.mip_intid_count=64;
 for(unsigned i=0;i<4;i++)s.binding.intx_intid[i]=261+i;
 s.binding.mip_regs={0x1000130000,0x10001300c0};s.binding.mip_target={0xfffffff000,0x10000000000};
 s.binding.outbound_count=2;s.binding.dma_count=3;
 s.binding.outbound[0]={0x02000000,0,0x1f00000000,0xfffffffc};
 s.binding.outbound[1]={0x43000000,0x400000000,0x1c00000000,0x300000000};
 s.binding.dma[0]={0x02000000,0,0x1f00000000,0x400000};
 s.binding.dma[1]={0x43000000,0x1000000000,0,0x1000000000};
 s.binding.dma[2]={0x03000000,0xfffffff000,0x1000130000,0x1000};
 s.binding.rp1_aperture_size=0x410000;s.binding.gem_bar_offset=0x100000;s.binding.gem_size=0x4000;
 s.binding.clock_bar_offset=0x18000;s.binding.clock_size=0x10038;
 // Declared stock-tree profile; this is not a fresh firmware-tree observation.
 s.profile={2,4,0,1,2,0xbbaa9888};s.setPhase(BCM2712_PHY_PREPARED);
 bridge[0]=0x271214e4;bridge[3]=0x00010000;
 bridge[0x4068/4]=0x3e080;bridge[0x416c/4]=0x60;
 bridge[0x04dc/4]=0x81000c43;bridge[0x184c/4]=0x80000012;
 bridge[0x4304/4]=0x40000000;bridge[0xbc/4]=0x30420543;
 bridge[0xdc/4]=0x1234b5a3;bridge[0x04f8/4]=0xa5a502ff;
 bridge[0x4078/4]=bridge[0x407c/4]=0x0000fff0;
 bridge[0x8000/4]=0x00011de4;bridge[0x8010/4]=0xffffc000;
 bridge[0x8014/4]=0xffc00000;bridge[0x8018/4]=0xffff0000;
 bcm2712_rp1_observation out={};bool ok=s.runBoundedRP1Trial(&out);
 rpi5_pcie_owner_trace t={};assert(!pe_rpi5_pcie_owner_trace(&s,&t));
 printf("FULL_ACCOUNTING OK=%u PHASE=%u LAST=%u GUARD=%u PM=%u SMC=%u FW=%u BARS_TXNS=%u WRITES=%u\n",
 ok,s.phase,s.trialLastPhase,s.diagGuard,t.pm_checks,smc_calls,t.fw_sequence,s.barsProbe.transactions,s.barsProbe.writes_started);
 for(unsigned i=0;i<32;i++)if(s.guards[i])printf("PHASE_%u_GUARDS=%u\n",i,s.guards[i]);
 printf("OWNER_STAGES FW=%u RPC=%u PM=%u IRQ=%u NS_READS=%u SECURE_READS=%u\n",t.fw_stage,t.rpc_stage,t.pm_stage,t.irq_stage,ns_reads,secure_reads);
 puts("NO_BOARD_TIMING_OR_CAUSE_CLAIM=1 FULL_REAL_RUNTIME_SEQUENCE=1");
 return 0;
}
'''


def run(composed=False,main=None,mutation=None):
    with tempfile.TemporaryDirectory(prefix='pcie-full-owner-') as name:
        folder=Path(name);cpp=folder/'host.cpp';cpp.write_text(source(folder,composed,main,mutation))
        flags=['-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined']
        for include in (FROZEN,ROOT,ROOT/'iokit/Kernel',ROOT/'loader/rpi5',ROOT/'tools/rpi5/tests',ROOT/'tools/rpi5/tests/pcie_irq_stubs',ROOT/'tools/rpi5/tests/fw_verifier_stubs'):
            flags+=['-I',str(include)]
        names=('pcie_reset','pcie_rescal','pcie_mdio','pcie_serdes','pcie_ubus','pcie_unused','pcie_qos','pcie_clock',
            'pcie_windows','pcie_rc','pcie_link','pcie_config','rp1_config_snapshot_checked','pcie_released_windows',
            'rp1_bars_probe','rp1_bars_plan','pcie_watchdog_lease','pcie_irq_mask','pcie_fw_client','pcie_owner_composition_secure')
        objects=[]
        for n in names:
            path=ROOT/'loader/rpi5'/(n+'.c')
            if n in ('pcie_ubus','pcie_qos','pcie_clock'):path=AXI/(n+'.c')
            if n in ('pcie_rc','pcie_link','rp1_config_snapshot_checked'):path=FROZEN/(n+'.c')
            if n=='pcie_owner_composition_secure':path=ROOT/'tools/rpi5/tests'/(n+'.c')
            obj=folder/(n+'.o');objects.append(obj)
            result=subprocess.run(['xcrun','clang','-std=c11',*flags,'-c',str(path),'-o',str(obj)],capture_output=True,text=True)
            if result.returncode:raise AssertionError(result.stderr)
        exe=folder/'host';result=subprocess.run(['xcrun','clang++','-std=gnu++17',*flags,str(cpp),*map(str,objects),'-o',str(exe)],capture_output=True,text=True)
        if result.returncode:raise AssertionError(result.stderr)
        result=subprocess.run([exe],capture_output=True,text=True,timeout=20)
        if result.returncode:raise AssertionError(result.stderr)
        return result.stdout


class FullOwnerAccountingTests(unittest.TestCase):
    def test_actual_entire_runtime_sequence_with_explicit_ram_doubles(self):
        output=run();print(output,end='')
        self.assertIn('FULL_ACCOUNTING ',output)
        self.assertIn('FULL_REAL_RUNTIME_SEQUENCE=1',output)
        self.assertIn('OK=0 PHASE=6 LAST=14 GUARD=4 PM=65536 SMC=9362 FW=9361',output)
        self.assertIn('OWNER_STAGES FW=6 RPC=5 PM=6 IRQ=8',output)


if __name__=='__main__':unittest.main()
