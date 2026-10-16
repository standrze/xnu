# SPDX-License-Identifier: BSD-2-Clause
"""Real full chain and fail-closed nested owners; explicit native doubles only."""
import re
import unittest
from tools.rpi5 import pcie_guard_composition_profile as profile
from tools.rpi5.tests import test_pcie_full_owner_accounting as full


def fault_seams(text):
    text=profile.previous.once(text,'static bool ml_at_interrupt_context(){return false;}',
        'static bool wrong_thread,interrupt_context;\n'
        'static bool ml_at_interrupt_context(){return interrupt_context;}')
    text=profile.previous.once(text,'static thread_t current_thread(){return &thread_identity;}',
        'static thread_t current_thread(){return wrong_thread?nullptr:&thread_identity;}')
    text=profile.previous.once(text,'static uint32_t rpi5_mmio_read32(vm_offset_t base,uint32_t offset)',
        'static unsigned pm_fault_ordinal,pm_ordinal,irq_fault_read,irq_typer_reads;\n'
        'static bool pm_fault_after_smc;\n'
        'static uint32_t rpi5_mmio_read32(vm_offset_t base,uint32_t offset)')
    text=profile.previous.once(text,'if(offset==RPI5_PM_RSTC)return 0x20;',
        'if(offset==RPI5_PM_RSTC){pm_ordinal++;return pm_ordinal==pm_fault_ordinal?0:0x20;}')
    text=profile.previous.once(text,'return gic_model[offset/4];',
        'if(offset==4&&++irq_typer_reads==irq_fault_read)return UINT32_MAX;\n    return gic_model[offset/4];')
    text=profile.previous.once(text,'smc_calls++;model_secure_call(fid,token,out);',
        'smc_calls++;model_secure_call(fid,token,out);\n'
        '    if(pm_fault_after_smc)pm_fault_ordinal=pm_ordinal+1;')
    return text


def fixture_setup():
    setup=full.MAIN.split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
    setup=profile.previous.once(setup,' BCM2712PCIePHYTransport s;IOService provider;IOMemoryMap maps[3];','')
    return '''static void prepare(BCM2712PCIePHYTransport &s,IOService &provider,IOMemoryMap maps[3]){
 wrong_thread=interrupt_context=pm_fault_after_smc=false;
 pm_fault_ordinal=pm_ordinal=irq_fault_read=irq_typer_reads=0;
 memset(bridge,0,sizeof bridge);memset(resets,0,sizeof resets);memset(rescal,0,sizeof rescal);
 link_released=false;link_released_at=0;
'''+setup+'''
 bcm2712_rp1_observation out={};assert(s.runBoundedRP1Trial(&out));
 s.setPhase(BCM2712_PHY_RP1_INSPECTING);
 pm_fault_ordinal=pm_ordinal=irq_fault_read=irq_typer_reads=0;
}
'''


def operation_trace(text):
    text=profile.previous.once(text,'#include <cstdio>','''#include <cstdio>
static void record(char kind,unsigned bank,unsigned offset,unsigned width,unsigned value){
 printf("OP %c %u %08x %u %08x\\n",kind,bank,offset,width,value);
}''')
    replacements={
      'uint32_t value = model_read(bank,offset);':'uint32_t value = model_read(bank,offset);record(\'r\',bank,offset,4,value);',
      'model_write(bank,offset,value);':'model_write(bank,offset,value);record(\'w\',bank,offset,4,value);',
      'uint16_t value = *reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset);':
      'uint16_t value = *reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset);record(\'r\',0,offset,2,value);',
      '*reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset) = value;':
      '*reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset) = value;record(\'w\',0,offset,2,value);',
      'uint32_t value = *reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset);':
      'uint32_t value = *reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset);record(\'r\',0,offset,4,value);',
      '*reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset) = value;':
      '*reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset) = value;record(\'w\',0,offset,4,value);',
      '*reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=value;':
      '*reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=value;record(\'w\',0,offset,4,value);',
      '*reg=before&~UINT32_C(1);':'*reg=before&~UINT32_C(1);record(\'w\',0,0x4044,4,before&~UINT32_C(1));'
    }
    for before,after in replacements.items():text=profile.previous.once(text,before,after)
    return text


class GuardCompositionTests(unittest.TestCase):
    def test_complete_real_chain_unchanged_limits_and_all_bar_restoration(self):
        main=full.MAIN.replace(' return 0;','''
 assert(ok&&s.diagGuard==0&&s.barsProbe.transactions==49&&s.barsProbe.writes_started==12);
 assert(out.bars.present==7&&s.barsProbe.state==RPI5_RP1_BARS_COMPLETE);
 assert(bridge[0x8010/4]==0xffffc000&&bridge[0x8014/4]==0xffc00000&&bridge[0x8018/4]==0xffff0000);
 unsigned total=0;for(unsigned n:s.guards)total+=n;
 assert(t.pm_checks==12+8*total&&smc_calls==2+2*total&&t.fw_sequence==1+2*total);
 assert(t.pm_checks<65536&&t.fw_sequence<65536&&t.pm_deadline-t.pm_start==12*t.fw_frequency);
 return 0;''')
        output=full.run(True,main)
        self.assertIn('OK=1 PHASE=5 LAST=5 GUARD=0 PM=45188 SMC=11296 FW=11295',output)
        self.assertIn('BARS_TXNS=49 WRITES=12',output)
        print(output,end='')

    def test_exact_guard_site_and_owner_dependency_contract(self):
        source=(profile.FROZEN/'BCM2712PCIeFWTransport.inc').read_text()
        changed=profile.guard_source(source)
        self.assertEqual(changed.count('pe_rpi5_pcie_fw_check(this,&fw)'),2)
        self.assertNotIn('if(!pe_rpi5_pcie_irq_check(this,&irq))',changed)
        self.assertIn('(!controllerMode && !pe_rpi5_watchdog_check_pcie(this))',changed)
        self.assertEqual(changed.split('bool BCM2712PCIePHYTransport::guard()')[0],source.split('bool BCM2712PCIePHYTransport::guard()')[0])
        fw=(profile.FROZEN/'rpi5_pcie_fw_owner.inc').read_text()
        irq=(profile.FROZEN/'rpi5_pcie_irq_owner.inc').read_text()
        self.assertLess(fw.index('rpi5_owner_trace.rpc_stage=5;'),fw.index('rpi5_pcie_fw_smccc(fid,token,raw);'))
        self.assertLess(fw.index('rpi5_pcie_fw_smccc(fid,token,raw);'),fw.index('rpi5_owner_trace.rpc_stage=8;'))
        self.assertIn('ok=pe_rpi5_watchdog_check_pcie(owner);',irq)
        self.assertIn('ok=pe_rpi5_watchdog_check_pcie(owner);}',irq)
        contract=profile.unchanged_contract()
        self.assertEqual(contract['cumulative_pm_limit'],65536)
        self.assertEqual(contract['deadline_seconds'],[9,10,12,15])

    def test_actual_transport_operation_trace_prefix_and_complete_restoration(self):
        old=full.run(False,mutation=operation_trace)
        new=full.run(True,mutation=operation_trace)
        old_ops=[x for x in old.splitlines() if x.startswith('OP ')]
        new_ops=[x for x in new.splitlines() if x.startswith('OP ')]
        self.assertGreater(len(old_ops),500)
        self.assertEqual(old_ops,new_ops[:len(old_ops)])
        for kind in ('r','w'):
            self.assertTrue(any(x.split()[1]==kind and x.split()[4]=='2' for x in old_ops))
        bar_writes=[x for x in new_ops if re.fullmatch(r'OP w 0 000080(?:1[048c]|2[04]) 4 [0-9a-f]{8}',x)]
        self.assertEqual(len(bar_writes),12)
        for i in range(6):
            offset=0x8010+4*i
            self.assertEqual(bar_writes[2*i],f'OP w 0 {offset:08x} 4 ffffffff')
            self.assertEqual(bar_writes[2*i+1],f'OP w 0 {offset:08x} 4 '+('ffffc000','ffc00000','ffff0000','00000000','00000000','00000000')[i])
        self.assertIn('BARS_TXNS=49 WRITES=12',new)
        print(f'ACTUAL_TRANSPORT_TRACE_PREFIX_PASS OLD={len(old_ops)} NEW={len(new_ops)} HALFWORD_PATHS=1 BAR_RESTORES=6')

    def test_real_guard_faults_on_every_nested_pm_irq_and_async_boundary(self):
        main=fixture_setup()+r'''
static unsigned callback_fault;
static int callback(IOService *provider,unsigned life){
 int rc=BCM2712PCIePHYTransport::trialAdmission(provider,life);if(rc)return rc;
 switch(callback_fault){
 case 1:pm_fault_ordinal=pm_ordinal+1;break;
 case 2:gic_model[0x114/4]|=1;break;
 case 3:phyOwner->setPhase(BCM2712_PHY_CLOCK_FINISHING);break;
 case 4:provider->opened=false;break;
 case 5:wrong_thread=true;break;
 case 6:assert(!phyOwner->guard());break; // Real callback re-entry, never cached authority.
 case 7:return -1;
 case 8:phyOwner=nullptr;break;
 }
 return 0;
}
int main(){
 unsigned cases=0;
 // Every actual nested PM and IRQ observation can independently fail.
 for(unsigned family=0;family<2;family++)for(unsigned point=1;point<=(family?4u:8u);point++){
  BCM2712PCIePHYTransport s;IOService provider;IOMemoryMap maps[3];prepare(s,provider,maps);
  if(family)irq_fault_read=2*point-1;else pm_fault_ordinal=point;
  unsigned before=smc_calls;assert(!s.guard()&&s.phase==BCM2712_PHY_FAILED);
  unsigned expected=family?(point/2):((point+1)/4);
  assert(smc_calls-before==expected);
  assert(s.diagGuard==(point<=(family?2u:4u)?4u:7u));
  assert(rpi5_pcie_fw_session.state==RPI5_FW_CLIENT_QUARANTINED);
  assert(rpi5_pcie_irq_session.state==RPI5_PCIE_IRQ_QUARANTINED);
  if(!family)assert(rpi5_pcie_wdog_lease.state==RPI5_PCIE_WDOG_QUARANTINED);
  cases++;
 }
 for(unsigned which=1;which<=8;which++){
  BCM2712PCIePHYTransport s;IOService provider;IOMemoryMap maps[3];prepare(s,provider,maps);
  callback_fault=which;s.controllerAdmission.check=callback;
  unsigned before=smc_calls;assert(!s.guard()&&s.phase==BCM2712_PHY_FAILED);
  assert(smc_calls==before+1); // First complete CHECK, then fresh callback/owner refusal.
  cases++;
 }
 // Actual returned SMC raw errors/counters/facts and post-SMC IRQ/PM changes.
 for(unsigned which=0;which<8;which++)for(unsigned ordinal=1;ordinal<=2;ordinal++){
  BCM2712PCIePHYTransport s;IOService provider;IOMemoryMap maps[3];prepare(s,provider,maps);
  unsigned before=smc_calls;
  if(which<4){corrupt_smc=before+ordinal;corrupt_field=which;
   corrupt_raw=which==0?(uint64_t)(int64_t)-5:which==1?0:which==2?rpi5_pcie_fw_session.last_counter:0;}
  if(which==4)corrupt_irq_after_smc=true;
  if(which==5)pm_fault_after_smc=true;
  if(which==6)rpi5_pcie_fw_session.deadline=model_ticks+1;
  if(which==7)rpi5_pcie_wdog_lease.last_counter=model_ticks+1000000;
  assert(!s.guard()&&s.phase==BCM2712_PHY_FAILED);
  unsigned expected=which<4?ordinal:which==7?0:1;
  assert(smc_calls==before+expected);cases++;
 }
 // Common owner/context gates and finite bounds still refuse before access.
 for(unsigned which=0;which<10;which++){
  BCM2712PCIePHYTransport s;IOService provider;IOMemoryMap maps[3];prepare(s,provider,maps);
  unsigned before=smc_calls;
  switch(which){
  case 0:provider.opened=false;break;case 1:s.claimAttempted=false;break;
  case 2:s.irqClaimed=false;break;case 3:s.fwClaimed=false;break;
  case 4:s.checkingLifecycle=true;break;case 5:s.claimingIRQ=true;break;
  case 6:phyOwner=nullptr;break;case 7:interrupt_context=true;break;
  case 8:rpi5_pcie_wdog_lease.checks=65536;break;
  case 9:rpi5_pcie_fw_session.sequence=65536;break;
  }
  assert(!s.guard()&&smc_calls==before);
  if(which==7)assert(s.phase==BCM2712_PHY_RP1_INSPECTING); // Foreign context cannot mutate owner state.
  else assert(s.phase==BCM2712_PHY_FAILED);
  cases++;
 }
 // Non-controller use retains its direct fresh PM check and no SMC.
 {
  BCM2712PCIePHYTransport s;IOService provider;IOMemoryMap maps[3];prepare(s,provider,maps);
  s.controllerMode=false;unsigned before=smc_calls,pm=rpi5_pcie_wdog_lease.checks;
  assert(s.guard()&&rpi5_pcie_wdog_lease.checks==pm+1&&smc_calls==before);
  pm_fault_ordinal=pm_ordinal+1;
  assert(!s.guard()&&s.diagGuard==1&&smc_calls==before);cases++;
 }
 printf("NESTED_GUARD_FAULTS_PASS CASES=%u ACTUAL_PM_IRQ_SMC_OWNERS=1 NO_BOARD_PROOF=1\n",cases);
 return 0;
}
'''
        output=full.run(True,main,fault_seams)
        self.assertIn('NESTED_GUARD_FAULTS_PASS CASES=47',output)
        print(output,end='')


if __name__=='__main__':unittest.main()
