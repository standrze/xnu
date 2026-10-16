# SPDX-License-Identifier: BSD-2-Clause
"""Whole actual owner/transport composition, with explicit VM/MMIO/PHY doubles."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import rp1_phy_reset_transport_profile as p
from tools.rpi5.tests import test_rp1_phy_gpio_observe as gpio
from tools.rpi5.tests import test_rp1_gem_mdio as mdio


def source(folder,main,mutation=None):
    text=gpio.source(folder,main)
    text=p.parent_transport(p.header(text));text=p.gem_transport(text)
    for name,fn in (('rp1_phy_gpio_observe.h',p.gpio_header),('rp1_phy_gpio_observe.c',p.gpio_core)):
        path=folder/name;path.write_text(fn(path.read_text()))
    for suffix,fn in (('h',p.timed.header),('c',p.timed.core)):
        name='rp1_gem_mdio.'+suffix;(folder/name).write_text(fn((p.timed.FROZEN/name).read_text()))
    for suffix in ('h','c'):
        name='rp1_phy_reset_cycle.'+suffix;body=(p.ROOT/'loader/rpi5'/name).read_text()
        (folder/name).write_text(p.reset_core(body) if suffix=='c' else body)
    text=re.sub(r'__asm__ volatile\("[^"\n]*" ::: "memory"\);','/* explicit host ordering double */',text)
    text=p.util.once(text,
        'const uint32_t cap_values[]={0x08800000,0x03f00000,0x100,0x0a8000aa,0x01020304,0x5400,0x04000000};',
        'const uint32_t cap_values[]={0x08508513,0x6eb13fff,0x502e5b45,0x08820000,0,0x24444444,0};')
    text=p.util.once(text,'static unsigned endpoint_reads,capability_reads;',
        'static unsigned endpoint_reads,capability_reads,mdio_reads,mdio_writes,mdio_commands,mdio_busy;\n'
        'static unsigned reset_reads,reset_writes;')
    text=p.util.once(text,'endpoint_reads=capability_reads=0;',
        'endpoint_reads=capability_reads=mdio_reads=mdio_writes=mdio_commands=reset_reads=reset_writes=0;\n'
        '    gem_registers[0]=0;gem_registers[1]=0;gem_registers[2]=4;')
    start=text.index('int BCM2712PCIePHYTransport::mdioRead(');end=text.index('int BCM2712PCIePHYTransport::phyResetAction(',start)
    before,body,after=text[:start],text[start:end],text[end:]
    body=p.util.once(body,'    uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);',r'''
    uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);
    assert((gpio_registers[0][0x24/4]&0x1f)==5 && (gpio_registers[1][0]&0x10) &&
        (gpio_registers[1][1]&0x10) && !(gpio_registers[2][0x14/4]&0x80));
    if(offset==8 && mdio_busy){value=0;mdio_busy--;}
    mdio_reads++;printf("MDIO_READ %08x %08x\n",offset,value);''')
    body=p.util.once(body,'    *reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset)=value;',r'''
    *reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset)=value;
    mdio_writes++;printf("MDIO_WRITE %08x %08x\n",offset,value);
    if(offset==0x34){const unsigned regs[]={2,3,0,1,1},values[]={0x600d,0x84a2,0x1140,0x7909,0x792d};
      assert(mdio_commands<5 && value==(0x60820000u|(regs[mdio_commands]<<18)));
      gem_registers[0x34/4]=(value&~0xffffu)|values[mdio_commands++];}''')
    start=after.index('int BCM2712PCIePHYTransport::phyResetRead(')
    pre,body2=after[:start],after[start:]
    body2=p.util.once(body2,'    uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);',r'''
    uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);
    reset_reads++;printf("RESET_READ %u %08x %08x\n",bank,offset,value);''')
    body2=p.util.once(body2,'    *reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset)=value;',r'''
    *reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset)=value;
    if(bank==1){assert(value==0x10);unsigned index=(offset&0xfff)/4;
      if((offset&0x3000)==0x2000)gpio_registers[1][index]|=value;
      else {assert((offset&0x3000)==0x3000);gpio_registers[1][index]&=~value;}
      gpio_registers[1][2]=(gpio_registers[1][2]&~0x10u)|(gpio_registers[1][0]&0x10);}
    reset_writes++;printf("RESET_WRITE %u %08x %08x\n",bank,offset,value);''')
    text=before+body+pre+body2
    return mutation(text) if mutation else text


def run(main,mutation=None):
    body=Path(mdio.__file__).read_text();body=body[body.index('def run('):body.index('\n\ndef main_source')]
    body=body.replace("'rp1_gem_mdio','pcie_fdt'", "'rp1_gem_mdio','rp1_phy_gpio_observe','rp1_phy_reset_cycle','pcie_fdt'")
    body=body.replace("'rp1_gem_capabilities','rp1_gem_mdio'):path", "'rp1_gem_capabilities','rp1_gem_mdio','rp1_phy_gpio_observe','rp1_phy_reset_cycle'):path")
    scope=dict(vars(mdio),source=source,profile=p);exec(compile(body,__file__,'exec'),scope)
    return scope['run'](main,mutation)


def main_source(extra=''):
    return gpio.main_source('''
    gpio_registers[0][0x24/4]=0x9f;gpio_registers[0][0x11c/4]=0;
    gpio_registers[1][0]=1;gpio_registers[1][1]=1;gpio_registers[1][2]=3;
    gpio_registers[2][0x14/4]=0xd6;
'''+extra)


class PHYResetTransportTests(unittest.TestCase):
    def test_actual_reset_access_faults_no_compensation_or_reuse(self):
        setup=main_source().split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main=r'''int main(){unsigned cases=0;
 for(unsigned target=1;target<=62;target++){for(unsigned mode=1;mode<=11;mode++){
 memset(bridge,0,sizeof bridge);memset(resets,0,sizeof resets);memset(rescal,0,sizeof rescal);
 link_released=false;link_released_at=0;map_created=map_revoked=map_call=0;initialize_endpoint();mdio_busy=0;
 reset_stamp_calls=0;reset_stamp_target=target;reset_stamp_mode=mode;wrong_thread=false;reset_stamp_hit=false;
'''+setup+r'''
 active_transport=&s;bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);before=out;
 assert(!s.runBoundedRP1Trial(&out)&&reset_stamp_hit&&!memcmp(&out,&before,sizeof out));
 // Mutation after the very last reset read's post-guard may leave that
 // nested core COMPLETE; the next real revoke guard rejects it. The outer
 // map/trial stays quarantined and publishes no successful observation.
 bool nested_complete=target==62&&(mode==6||mode==7);
 assert(s.phyGPIO.state==RPI5_PHY_GPIO_QUARANTINED&&s.phyReset.state==
   (nested_complete?RPI5_PHY_RESET_COMPLETE:RPI5_PHY_RESET_QUARANTINED));
 assert(s.phase==BCM2712_PHY_FAILED&&!map_revoked&&s.assignment.state==RPI5_RP1_ASSIGN_ASSIGNED);
 // Counter corruption injected inside the trusted clock helper AFTER the
 // pre-owner guard can be detected by the post-owner guard only. Exactly that
 // already-authorized access may occur; no later access/cleanup is permitted.
 unsigned one=(mode==6||mode==7)&&(target&1);
 if(reset_reads!=stopped_gpio_reads+(one&&stopped_kind==1)||reset_writes!=stopped_gpio_writes+(one&&stopped_kind==2)||
   mdio_reads!=stopped_mdio_reads||mdio_writes!=stopped_mdio_writes)
   fprintf(stderr,"TARGET%u MODE%u KIND%u GPIO%u/%u->%u/%u MDIO%u/%u->%u/%u ONE%u\n",target,mode,stopped_kind,
     stopped_gpio_reads,stopped_gpio_writes,reset_reads,reset_writes,stopped_mdio_reads,stopped_mdio_writes,mdio_reads,mdio_writes,one);
 assert(reset_reads==stopped_gpio_reads+(one&&stopped_kind==1)&&reset_writes==stopped_gpio_writes+(one&&stopped_kind==2)&&
   mdio_reads==stopped_mdio_reads&&mdio_writes==stopped_mdio_writes);
 unsigned smc=smc_calls;assert(!s.runBoundedRP1Trial(&out)&&smc_calls==smc&&!map_revoked);cases++;
 }}printf("PHY_RESET_ACTUAL_FAULTS_PASS CASES=%u NO_COMPENSATION=1 NO_HARDWARE=1\n",cases);return 0;}'''
        def mutation(text):
            text=p.util.once(text,'static thread_t current_thread(){return &thread_identity;}',
                'static bool wrong_thread;static thread_t current_thread(){return wrong_thread?nullptr:&thread_identity;}')
            text=p.util.once(text,'int main(){',r'''
static BCM2712PCIePHYTransport *active_transport;
static unsigned reset_stamp_calls,reset_stamp_target,reset_stamp_mode;
static unsigned stopped_gpio_reads,stopped_gpio_writes,stopped_mdio_reads,stopped_mdio_writes,stopped_kind;
static bool reset_stamp_hit;
int main(){''')
            text=p.util.once(text,'    uint64_t now=ns/1000;',r'''
    uint64_t now=ns/1000;auto *self=active_transport;
    if(self->phyReset.pending==1||self->phyReset.pending==2){reset_stamp_calls++;
      if(reset_stamp_calls==reset_stamp_target){reset_stamp_hit=true;
      stopped_gpio_reads=reset_reads;stopped_gpio_writes=reset_writes;
      stopped_mdio_reads=mdio_reads;stopped_mdio_writes=mdio_writes;
      stopped_kind=self->phyReset.pending;
      switch(reset_stamp_mode){
      case 1:now=previous-1;break;case 2:now=deadline;break;
      case 3:wrong_thread=true;break;case 4:self->setPhase(BCM2712_PHY_CLOCK_FINISHING);break;
      case 5:assert(rpi5_phy_reset_run(&self->phyReset,&self->phyGPIOBinding,&self->phyReset.io,&self->phyResetObserved));break;
      case 6:rpi5_pcie_wdog_lease.checks=65536;break;
      case 7:rpi5_pcie_fw_session.sequence=65536;break;
      case 8:self->phyGPIOMaps[0]->virt=0;break;
      case 9:self->capabilitySession.state=RPI5_GEM_CAP_QUARANTINED;break;
      case 10:self->firmwareFDT->bytes=nullptr;break;
      case 11:self->phyReset.pending=7;break;
      }}}
''')
            return text
        output=run(main,mutation);print(output.splitlines()[-1]);self.assertIn('CASES=682',output)

    def test_live_aspm_refusal_precedes_any_gpio_or_mdio_write(self):
        main=main_source().replace(' return 0;',r'''
    assert(!ok&&s.phyGPIO.state==RPI5_PHY_GPIO_QUARANTINED&&!reset_reads&&!reset_writes&&!mdio_writes);
    assert(!map_revoked&&map_created==5&&s.phyReset.state==RPI5_PHY_RESET_UNUSED);
    assert(!s.phyResetNoASPM&&s.phyResetActionActive);
    printf("PHY_RESET_ASPM_REFUSED NO_GPIO_OR_MDIO_WRITES=1\n");return 0;''')
        def mutation(text):
            return p.util.once(text,'    uint16_t link=*reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE]+0xbc);',
                '    uint16_t link=*reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE]+0xbc);link|=0x103;')
        output=run(main,mutation);self.assertIn('PHY_RESET_ASPM_REFUSED',output)

    def test_wait_deadline_stuck_owner_and_reentry_fail_without_deassert(self):
        setup=main_source().split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main=r'''int main(){unsigned cases=0;
 for(unsigned mode=1;mode<=7;mode++){
 memset(bridge,0,sizeof bridge);memset(resets,0,sizeof resets);memset(rescal,0,sizeof rescal);
 link_released=false;link_released_at=0;map_created=map_revoked=map_call=0;initialize_endpoint();mdio_busy=0;
 wait_mode=mode;wait_hit=false;
'''+setup+r'''
 active_transport=&s;bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);before=out;
 assert(!s.runBoundedRP1Trial(&out)&&wait_hit&&!memcmp(&out,&before,sizeof out));
 assert(s.phyReset.state==RPI5_PHY_RESET_QUARANTINED&&s.phyGPIO.state==RPI5_PHY_GPIO_QUARANTINED);
 assert(reset_writes==6&&reset_reads==12&&!mdio_reads&&!mdio_writes&&!map_revoked);
 assert(!(gpio_registers[1][0]&0x10));unsigned stopped=smc_calls;
 assert(!s.runBoundedRP1Trial(&out)&&smc_calls==stopped&&!map_revoked);cases++;
 }printf("PHY_RESET_WAIT_FAULTS_PASS CASES=%u ASSERTED_STATE_RETAINED=1 NO_HARDWARE=1\n",cases);return 0;}'''
        def mutation(text):
            text=p.util.once(text,'int main(){',
                'static BCM2712PCIePHYTransport *active_transport;static unsigned wait_mode;static bool wait_hit;\nint main(){')
            return p.util.once(text,'    uint64_t now=ns/1000;',r'''
    uint64_t now=ns/1000;auto *self=active_transport;
    if(self->phyReset.pending==4){wait_hit=true;switch(wait_mode){
      case 1:now=previous-1;break;case 2:now=deadline;break;case 3:now=previous;break;
      case 4:now=self->phyReset.last_us+6000;break;
      case 5:self->setPhase(BCM2712_PHY_CLOCK_FINISHING);break;
      case 6:assert(rpi5_phy_reset_run(&self->phyReset,&self->phyGPIOBinding,&self->phyReset.io,&self->phyResetObserved));break;
      case 7:rpi5_pcie_fw_session.sequence=65536;break;
    }}
''')
        output=run(main,mutation);self.assertIn('PHY_RESET_WAIT_FAULTS_PASS CASES=7',output);print(output.splitlines()[-1])

    def test_actual_full_owner_worst_poll_sequence_restores_gpio_and_maps(self):
        main=main_source('mdio_busy=20;').replace(' return 0;',r'''
    if(!ok)fprintf(stderr,"RESET FAIL gpio=%u/%d reset=%u/%d step%u mdio=%u/%d pm%u\n",
      s.phyGPIO.state,s.phyGPIO.error,s.phyReset.state,s.phyReset.error,s.phyReset.step,s.mdioSession.state,s.mdioSession.error,t.pm_checks);
    assert(ok&&s.phyReset.state==RPI5_PHY_RESET_COMPLETE&&out.phy.phy_id==0x600d84a2);
    assert(s.phyGPIO.state==RPI5_PHY_GPIO_COMPLETE&&!s.phyGPIO.reads&&s.phyGPIO.mapped==7&&s.phyGPIO.unmapped==7);
    assert(out.phy.polls==32&&out.phy.reads==46&&out.phy.writes==9&&out.phy.clocks==2);
    assert(out.phy_reset.ctrl_before==0x9f&&out.phy_reset.ctrl_after==0x9f&&out.phy_reset.pad_after==0xd6);
    assert(out.phy_reset.out_after==1&&out.phy_reset.oe_after==1);
    assert(out.phy_reset.reads==19&&out.phy_reset.writes==12&&reset_reads==19&&reset_writes==12);
    assert(out.phy_reset.deasserted_us>=out.phy_reset.asserted_us+5000);
    assert(gpio_registers[0][0x24/4]==0x9f&&gpio_registers[1][0]==1&&gpio_registers[1][1]==1&&gpio_registers[2][0x14/4]==0xd6);
    assert(map_revoked==5&&map_created==5&&gem_registers[0]==0&&gem_registers[1]==0);
    assert(s.assignment.state==RPI5_RP1_ASSIGN_RESTORED);
    unsigned guards=0;for(unsigned n:s.guards)guards+=n;
    assert(t.pm_checks==12+8*guards&&t.fw_sequence==1+2*guards&&t.pm_checks<65536);
    printf("PHY_RESET_FULL_PASS PM=%u FW=%u GUARDS=%u MDIO_POLLS=%u GPIO_READS=%u GPIO_WRITES=%u NO_HARDWARE=1\n",
      t.pm_checks,t.fw_sequence,guards,out.phy.polls,reset_reads,reset_writes);return 0;''')
        output=run(main);print('\n'.join(output.splitlines()[-5:]));self.assertIn('PHY_RESET_FULL_PASS',output)

    def test_default_filter_field_is_preserved_not_unknown_echo(self):
        with tempfile.TemporaryDirectory(prefix='reset-filter-core-') as name:
            folder=Path(name)/'overlay';p.emit(folder)
            text=Path(__file__).with_name('rp1_phy_reset_cycle_host.c').read_text()
            text=text.replace('m->ctrl=31;','m->ctrl=0x9f;')
            text=text.replace('m->ctrl==5','(m->ctrl&~0x80u)==5').replace('m.ctrl==5','(m.ctrl&~0x80u)==5')
            text=text.replace('m.ctrl==31','m.ctrl==0x9f').replace('&0xf01f','&0xf09f')
            text=text.replace('if(bank==0)m->ctrl=value;',
                'if(bank==0){assert((value&0x80)==(m->s.observed.ctrl_before&0x80));m->ctrl=value;}')
            host=folder/'host.c';host.write_text(text);exe=folder/'host'
            flags=['-std=c11','-Wall','-Wextra','-Werror','-I',str(folder),'-I',str(p.ROOT/'loader/rpi5')]
            r=subprocess.run(['xcrun','clang',*flags,'-fsanitize=address,undefined',str(host),str(folder/'rp1_phy_reset_cycle.c'),'-o',str(exe)],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr);r=subprocess.run([exe],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr);print(r.stdout,end='')


if __name__=='__main__':unittest.main()
