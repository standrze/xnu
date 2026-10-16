# SPDX-License-Identifier: BSD-2-Clause
"""Actual controller, owners, retained Apple-method provider and CPU-only batch.

Apple allocation/VA/AT, FDT delivery/profile/memory/reservation/initrd parsers,
immutable kernel-record lookup and hardware registers/time are native doubles.
Actual raw-FDT/SHA/record binding is separately tested. Neither released
controller sessions nor capability COMPLETE states are seeded here.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import gem_dma_batch_transport_profile as profile
from tools.rpi5.tests import test_gem_dma_batch as provider
from tools.rpi5.tests import test_rp1_gem_capabilities as cap
ROOT=profile.ROOT

def native_provider():
    outputs=profile.memory.derive()
    source=provider.host_source(outputs['BCM2712GEMDMABatch.h'].decode(),outputs['BCM2712GEMDMABatch.cpp'].decode())
    begin=source.index('static void setup(');body=source.index('{',begin)
    finish=source.index('    w={};',body)
    setup='static void dma_setup()\n'+source[body:finish]+'}\n'
    source=source[:source.index('static BCM2712GEMDMABatch *active;')]
    source=re.sub(r'static bool ml_at_interrupt_context\(\)\{[^\n]+\}\n','',source)
    source=re.sub(r'static void \*current_thread\(\)\{[^\n]+\}\n','',source)
    source=source.replace('    kIOMemoryMapperNone=0x100,kIOMapWriteCombineCache=0x200;',
        '    kIOMapWriteCombineCache=0x200;')
    source=source.replace('static constexpr int kIOReturnSuccess=0;\n','')
    source=source.replace('rpi5_physical_memory_type','dma_physical_memory_type')
    source+=setup
    source=re.sub(r'\bmodel\b','dma_model',source)
    source=re.sub(r'\bevent\b','dma_event',source)
    source=re.sub(r'\bfixture\b','dma_fixture',source)
    return source

def source(folder,main,mutation=None):
    text=cap.source(folder,main)
    text=profile.header(text);text=profile.admission(text);text=profile.gem(text)
    text=text.replace('#include "BCM2712GEMDMABatch.h"\n','')
    # Real provider methods share the exact current thread and owner callback
    # with the full controller. Allocation/VM, FDT delivery and parser/profile
    # results, and immutable-record lookup remain explicit doubles above.
    text=profile.change(text,'struct OSData{};\n','')
    at=text.index('class BCM2712PCIePHYTransport')
    text=text[:at]+native_provider()+'\n'+text[at:]
    text=profile.change(text,
        'const uint32_t cap_values[]={0x08800000,0x03f00000,0x100,0x0a8000aa,0x01020304,0x5400,0x04000000};',
        'const uint32_t cap_values[]={0x08508513,0x6eb13fff,0x502e5b45,0x08820000,0,0x24444444,0};')
    return mutation(text) if mutation else text

def run(main,mutation=None):
    with tempfile.TemporaryDirectory(prefix='dma-batch-full-owner-') as name:
        folder=Path(name);outputs=profile.memory.derive()
        for n,data in outputs.items():(folder/n).write_bytes(data)
        cpp=folder/'host.cpp';cpp.write_text(source(folder,main,mutation))
        flags=['-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined']
        for inc in (folder,cap.full.FROZEN,ROOT,ROOT/'tools/rpi5/tests/pcie_irq_stubs',
                    ROOT/'tools/rpi5/tests/fw_verifier_stubs',ROOT/'osfmk',ROOT/'iokit/Kernel',ROOT/'loader/rpi5',
                    ROOT/'tools/rpi5/tests'):
            flags+=['-I',str(inc)]
        names=('pcie_reset','pcie_rescal','pcie_mdio','pcie_serdes','pcie_ubus','pcie_unused','pcie_qos','pcie_clock',
            'pcie_windows','pcie_rc','pcie_link','pcie_config','rp1_config_snapshot_checked','pcie_released_windows',
            'rp1_bars_probe','rp1_bars_plan','rp1_bars_assign','rp1_decode_cycle','rp1_gem_identify','pcie_root_forward',
            'rp1_gem_capabilities','pcie_watchdog_lease','pcie_irq_mask','pcie_fw_client','pcie_owner_composition_secure',
            'reservation_record','ranges','reservations')
        paths=[]
        for n in names:
            path=ROOT/'loader/rpi5'/(n+'.c')
            if n in ('pcie_ubus','pcie_qos','pcie_clock'):path=cap.full.AXI/(n+'.c')
            if n in ('pcie_rc','pcie_link','rp1_config_snapshot_checked'):path=cap.full.FROZEN/(n+'.c')
            if n in ('rp1_decode_cycle','rp1_gem_identify','pcie_root_forward','rp1_gem_capabilities'):path=folder/(n+'.c')
            if n=='pcie_owner_composition_secure':path=ROOT/'tools/rpi5/tests'/(n+'.c')
            paths.append(path)
        paths += [ROOT/'iokit/Kernel/rpi5_gem_dma_route.c',ROOT/'iokit/Kernel/rpi5_gem_ring_batch.c',
                  ROOT/'osfmk/arm64/rpi5_reservation_kernel.c']
        objects=[]
        for path in paths:
            obj=folder/(path.name+'.o');objects.append(obj)
            result=subprocess.run(['xcrun','clang','-std=c11',*flags,'-c',path,'-o',obj],capture_output=True,text=True,timeout=60)
            if result.returncode:raise AssertionError(result.stderr)
        exe=folder/'host'
        result=subprocess.run(['xcrun','clang++','-std=gnu++17',*flags,cpp,*objects,'-o',exe],capture_output=True,text=True,timeout=60)
        if result.returncode:raise AssertionError(result.stderr)
        result=subprocess.run([exe],capture_output=True,text=True,timeout=60)
        if result.returncode:raise AssertionError(result.stderr)
        return result.stdout

def main_source():
    main=cap.full.MAIN.replace(' bcm2712_rp1_observation out={};',
        ''' bridge[1]=0xa5a50000;bridge[0x20/4]=0x0000fff0;
 dma_setup();assert(!pm_writes && !smc_calls);assert(s.prepareCPUOwnedRings());
 assert(s.dmaPreparePhase==2 && s.dmaMemory->state()==BCM2712GEMDMABatch::Prepared);
 assert(!pm_writes && !smc_calls);memset(allocation,0xa5,sizeof allocation);
 bcm2712_rp1_observation out={};''')
    return main.replace(' return 0;',r'''
 assert(ok && s.dmaMemory->state()==BCM2712GEMDMABatch::RingsHeld && !s.dmaRingActive);
 assert(s.dmaRingsObserved.writes==640 && s.dmaRingsObserved.reads==640);
 assert(s.dmaRingsObserved.cpu_owned_descriptors==160 && s.capabilitySession.state==RPI5_GEM_CAP_COMPLETE);
 assert(s.rootForward.state==RPI5_ROOT_FORWARD_COMPLETE && s.decodeCycle.state==RPI5_RP1_DECODE_COMPLETE);
 assert(s.assignment.state==RPI5_RP1_ASSIGN_RESTORED && map_created==2 && map_revoked==2);
 assert(bridge[1]==0xa5a50000 && bridge[0x20/4]==0x0000fff0 && (bridge[0x8004/4]&0xffff)==0);
 for(unsigned i=0;i<3;i++)assert(!(s.windows.plan.inbound[i].bar_lo&31));
 for(unsigned r=0;r<2;r++)for(unsigned n=1280;n<0x4000;n++)assert(allocation[r*0x4000+n]==0xa5);
 for(unsigned n=0x8000;n<sizeof allocation;n++)assert(allocation[n]==0xa5);
 assert(!dma_model.releases && !dma_model.complete);
 unsigned guards=0;for(unsigned n:s.guards)guards+=n;
 assert(t.pm_checks==12+8*guards && t.fw_sequence==1+2*guards && t.pm_checks<65536);
 printf("DMA_BATCH_FULL_OWNER_PASS PM=%u FW=%u GUARDS=%u WRITES=640 READBACKS=640 HELD=160 NO_ACTIVE_DMA=1\n",
 t.pm_checks,t.fw_sequence,guards);return 0;''')

class GEMDMABatchTransportTests(unittest.TestCase):
    def test_actual_full_controller_provider_and_batch_budget(self):
        output=run(main_source());print(output,end='')
        self.assertIn('DMA_BATCH_FULL_OWNER_PASS',output)

    def test_real_caller_first_virtual_boundary_reentry_context_and_identity(self):
        setup=cap.full.MAIN.split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main='''int main(){unsigned cases=0;
 for(unsigned fault=1;fault<=7;fault++){
'''+setup+r'''
 dma_setup();prepare_fault=fault;prepare_hit=false;prepare_target=&s;
 assert(!s.prepareCPUOwnedRings() && prepare_hit && s.dmaPreparePhase==3 && !s.dmaMemory);
 assert(!s.prepareCPUOwnedRings() && !dma_model.calls && !smc_calls && !pm_writes);cases++;
 }printf("DMA_CALLER_FIRST_BOUNDARY_PASS CASES=%u NO_ALLOCATION=1\n",cases);return 0;}'''
        def mutation(text):
            text=profile.change(text,'static thread_t current_thread(){return &thread_identity;}',
                'static bool wrong_thread;static thread_t current_thread(){return wrong_thread?nullptr:&thread_identity;}')
            text=profile.change(text,'struct IOService {bool opened=true;bool isOpen(const void*)const{return opened;}',
                'static void prepare_event(const void *);\n'
                'struct IOService {bool opened=true;bool isOpen(const void *p)const{prepare_event(p);return opened;}')
            hook=r'''
static unsigned prepare_fault;static bool prepare_hit;static BCM2712PCIePHYTransport *prepare_target;
static void prepare_event(const void *p){
 if(!prepare_target || p!=prepare_target || prepare_target->dmaPreparePhase!=1 || prepare_hit)return;
 prepare_hit=true;auto *s=prepare_target;
 switch(prepare_fault){
 case1:assert(!s->prepareCPUOwnedRings());break;
 case2:wrong_thread=true;break;
 case3:s->ownerProvider=nullptr;break;
 case4:s->providerOpened=false;break;
 case5:s->claimAttempted=true;break;
 case6:s->setPhase(BCM2712_PHY_FAILED);break;
 case7:s->trialMode=true;break;
 }}
'''.replace('case','case ')
            text=profile.change(text,'int main(){',hook+'\nint main(){')
            text=profile.change(text,' for(unsigned fault=1;fault<=7;fault++){',
                ' for(unsigned fault=1;fault<=7;fault++){wrong_thread=false;prepare_target=nullptr;')
            return text
        output=run(main,mutation);self.assertIn('DMA_CALLER_FIRST_BOUNDARY_PASS CASES=7',output)

    def test_actual_batch_owner_failure_retains_partial_cpu_ram_and_device_maps(self):
        setup=cap.full.MAIN.split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main='''int main(){unsigned cases=0;
 for(unsigned fault=1;fault<=13;fault++){for(unsigned side=0;side<2;side++){for(unsigned at:{1u,3u,164u}){
 memset(bridge,0,sizeof bridge);memset(resets,0,sizeof resets);memset(rescal,0,sizeof rescal);
 link_released=false;link_released_at=0;map_created=map_revoked=map_call=0;
 wrong_thread=false;initialize_endpoint();
'''+setup+r'''
 bridge[1]=0xa5a50000;bridge[0x20/4]=0x0000fff0;
 dma_setup();assert(s.prepareCPUOwnedRings());memset(allocation,0xa5,sizeof allocation);
 ring_fault=fault;ring_side=side;ring_target=at;ring_count=0;ring_hit=false;
 bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);memcpy(&before,&out,sizeof out);
 assert(!s.runBoundedRP1Trial(&out) && ring_hit && s.phase==BCM2712_PHY_FAILED);
 /* Deliberately mutate a private PE counter AFTER the final genuine guard:
  * CPU staging may already finish, but the original next restoration guard
  * rejects. This is retained CPU success + whole-trial failure, not rollback
  * or stale authority for device DMA. All earlier checkpoints quarantine. */
 bool post_final_budget=(fault==9 || fault==10) && side==1 && at==164;
 assert(s.dmaMemory->state()==(post_final_budget?BCM2712GEMDMABatch::RingsHeld:BCM2712GEMDMABatch::Quarantined));
 assert(!memcmp(&out,&before,sizeof out));
 assert(s.dmaRingActive==!post_final_budget && !map_revoked && s.assignment.state==RPI5_RP1_ASSIGN_ASSIGNED);
 assert((bridge[0x8004/4]&0xffff)==2 && (bridge[1]&2));
 if(at==1)for(unsigned n=0;n<sizeof allocation;n++)assert(allocation[n]==0xa5);
 else assert(*(uint32_t *)(void *)allocation!=0xa5a5a5a5);
 for(unsigned n=0x8000;n<sizeof allocation;n++)assert(allocation[n]==0xa5);
 unsigned stopped=smc_calls,events=dma_model.calls;
 assert(!s.runBoundedRP1Trial(&out) && smc_calls==stopped && dma_model.calls==events);
 assert(!s.dmaMemory->discardBeforeAdmission() && !dma_model.complete && !dma_model.releases);cases++;
 }}}printf("DMA_FULL_OWNER_FAULTS_PASS CASES=%u NO_COMPENSATING_CLEANUP=1\n",cases);return 0;}'''
        def mutation(text):
            text=profile.change(text,'static thread_t current_thread(){return &thread_identity;}',
                'static bool wrong_thread;static thread_t current_thread(){return wrong_thread?nullptr:&thread_identity;}')
            text=profile.change(text,'int main(){',
                'static unsigned ring_fault,ring_side,ring_target,ring_count;static bool ring_hit;\n'
                'int main(){')
            first=text.index('int BCM2712PCIePHYTransport::dmaRingCurrent(')
            end=text.index('bool BCM2712PCIePHYTransport::stagePreparedCPUOwnedRings()',first)
            before,body,tail=text[:first],text[first:end],text[end:]
            inject=r'''
    if(!ring_hit && ring_side==SIDE && ring_count==ring_target){ring_hit=true;
    switch(ring_fault){
    case1:wrong_thread=true;break;case2:self->setPhase(BCM2712_PHY_CLOCK_FINISHING);break;
    case3:self->providerOpened=false;break;case4:self->fwClaimed=false;break;
    case5:self->irqClaimed=false;break;case6:self->windows.plan.inbound[1].bar_lo|=1;break;
    case7:self->capabilitySession.words[0][1]^=1;break;
    case8:self->deviceMaps[0]->virt=0;break;
    case9:rpi5_pcie_wdog_lease.checks=65536;break;
    case10:rpi5_pcie_fw_session.sequence=65536;break;
    case11:assert(!self->stagePreparedCPUOwnedRings());break;
    case12:model_ticks+=model_frequency;break;
    case13:self->dmaLive.generation++;break;}}
'''.replace('case','case ')
            body=profile.change(body,'    if(!self || memory!=self->dmaMemory',
                '    ring_count++;\n'+inject.replace('SIDE','0')+'    if(!self || memory!=self->dmaMemory')
            body=profile.change(body,'    /* Actual existing guard contains',
                inject.replace('SIDE','1')+'    /* Actual existing guard contains')
            return before+body+tail
        output=run(main,mutation);self.assertIn('DMA_FULL_OWNER_FAULTS_PASS CASES=78',output)
if __name__=='__main__':unittest.main()
