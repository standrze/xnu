# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import rp1_gem_mdio_timed_profile as p
from tools.rpi5 import build_pcie_gem_mdio_id_kernel as kernel
from tools.rpi5.tests import test_rp1_gem_mdio as prior


def runtime(main,mutation=None):
    t=kernel.private.load_private(Path(prior.__file__).resolve(),'_mdio_timed_native')
    previous=t.source
    def source(folder,main,unused=None):
        text=previous(folder,main)
        (folder/'rp1_gem_mdio.c').write_text(p.core((p.FROZEN/'rp1_gem_mdio.c').read_text()))
        (folder/'rp1_gem_mdio.h').write_text(p.header((p.FROZEN/'rp1_gem_mdio.h').read_text()))
        text=p.transport(p.transport_header(text))
        text=re.sub(r'__asm__ volatile\("[^"\n]*" ::: "memory"\);','/* explicit host ordering double */',text)
        start=text.index('int BCM2712PCIePHYTransport::mdioRead(')
        before,body=text[:start],text[start:]
        body=p.util.once(body,'    uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);',r'''
    uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);
    if(offset==8 && mdio_busy){value=0;mdio_busy--;}
    mdio_reads++;printf("MDIO_READ %08x %08x\n",offset,value);''')
        body=p.util.once(body,'    *reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset)=value;',r'''
    *reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset)=value;
    mdio_writes++;printf("MDIO_WRITE %08x %08x\n",offset,value);
    if(offset==0x34){
      const unsigned regs[]={2,3,0,1,1},values[]={0x600d,0x84a2,0x1140,0x7909,0x792d};
      assert(mdio_commands<5 && value==(0x60820000u|(regs[mdio_commands]<<18)));
      gem_registers[0x34/4]=(value&~0xffffu)|values[mdio_commands++];
    }''')
        text=before+body
        return mutation(text) if mutation else text
    t.source=source
    return t.run(main)


class GEMMDIOTimedTests(unittest.TestCase):
    def test_actual_access_stamp_faults_before_after_mmio_no_retry(self):
        setup=prior.main_source().split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main=r'''int main(){unsigned cases=0;
 for(unsigned target=1;target<=70;target++){for(unsigned mode=1;mode<=5;mode++){
 memset(bridge,0,sizeof bridge);memset(resets,0,sizeof resets);memset(rescal,0,sizeof rescal);
 link_released=false;link_released_at=0;map_created=map_revoked=map_call=0;initialize_endpoint();mdio_busy=0;
 stamp_calls=0;stamp_target=target;stamp_mode=mode;wrong_thread=false;stamp_hit=false;
'''+setup+r'''
 active_transport=&s;bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);before=out;
 assert(!s.runBoundedRP1Trial(&out)&&stamp_hit&&!memcmp(&out,&before,sizeof out));
 assert(s.mdioSession.state==RPI5_GEM_MDIO_QUARANTINED&&s.phase==BCM2712_PHY_FAILED);
 assert(mdio_reads==stamp_reads&&mdio_writes==stamp_writes&&!map_revoked);
 // A pre-access deadline failure has no data access; a post-access failure
 // retains that performed write and never pretends to restore its side effect.
 if(target==7&&mode<=2)assert(mdio_writes==0&&gem_registers[1]==0);
 if(target==8&&mode<=2)assert(mdio_writes==1&&gem_registers[1]==0x140000);
 unsigned r=mdio_reads,w=mdio_writes,c=smc_calls;
 assert(!s.runBoundedRP1Trial(&out)&&mdio_reads==r&&mdio_writes==w&&smc_calls==c);cases++;
 }}printf("TIMED_MDIO_ACTUAL_STAMP_FAULTS=%u NO_COMPENSATING_IO=1 NO_HARDWARE=1\n",cases);return 0;}'''
        def mutation(text):
            text=p.util.once(text,'static thread_t current_thread(){return &thread_identity;}',
                'static bool wrong_thread;static thread_t current_thread(){return wrong_thread?nullptr:&thread_identity;}')
            text=p.util.once(text,'int main(){',
                'static BCM2712PCIePHYTransport *active_transport;\n'
                'static unsigned stamp_calls,stamp_target,stamp_mode,stamp_reads,stamp_writes;static bool stamp_hit;\n'
                'int main(){')
            text=p.util.once(text,'    uint64_t now=ns/1000;',r'''
    uint64_t now=ns/1000;stamp_calls++;
    if(stamp_calls==stamp_target){stamp_hit=true;stamp_reads=mdio_reads;stamp_writes=mdio_writes;
      switch(stamp_mode){
      case 1:now=previous-1;break;case 2:now=deadline;break;
      case 3:active_transport->setPhase(BCM2712_PHY_CLOCK_FINISHING);break;
      case 4:wrong_thread=true;break;
      case 5:assert(rpi5_gem_mdio_run(&active_transport->mdioSession,&active_transport->capabilitySession,
          &active_transport->binding,&active_transport->mdioSession.io,&active_transport->mdioObserved));break;}}
''')
            return text
        output=runtime(main,mutation);self.assertIn('TIMED_MDIO_ACTUAL_STAMP_FAULTS=350',output)
        print(output.splitlines()[-1])

    def test_actual_owner_full_worst_poll_budget_and_same_mmio(self):
        main=prior.main_source('mdio_busy=20;')
        main=main.replace(' return 0;',r'''
 assert(ok&&s.mdioSession.state==RPI5_GEM_MDIO_COMPLETE&&out.phy.phy_id==0x600d84a2);
 assert(out.phy.polls==32&&out.phy.reads==46&&out.phy.writes==9&&out.phy.clocks==2);
 assert(s.assignment.state==RPI5_RP1_ASSIGN_RESTORED&&map_revoked==2);
 assert(gem_registers[0]==0&&gem_registers[1]==0&&mdio_commands==5);
 unsigned guards=0;for(unsigned n:s.guards)guards+=n;
 assert(t.pm_checks==12+8*guards&&t.fw_sequence==1+2*guards&&t.pm_checks<65536);
 printf("TIMED_MDIO_FULL_PASS PM=%u FW=%u GUARDS=%u POLLS=%u READS=%u WRITES=%u NO_HARDWARE=1\n",
 t.pm_checks,t.fw_sequence,guards,out.phy.polls,out.phy.reads,out.phy.writes);return 0;''')
        output=runtime(main);print(output.splitlines()[-1])
        self.assertIn('PM=64540 FW=16133 GUARDS=8066 POLLS=32 READS=46 WRITES=9',output)
        original=prior.run(prior.main_source('mdio_busy=20;'))
        rows=lambda out:[row for row in out.splitlines() if row.startswith(('GEMREAD ','CAPREAD ','MDIO_READ ','MDIO_WRITE '))]
        self.assertEqual(rows(output),rows(original))

    def test_actual_core_faults_typed_completions_and_a76(self):
        with tempfile.TemporaryDirectory(prefix='mdio-timed-core-') as name:
            folder=Path(name)/'overlay';p.emit(folder)
            text=Path(prior.__file__).with_name('rp1_gem_mdio_host.c').read_text().split('int main(void)',1)[0]
            text=text.replace('unsigned busy_extra,','unsigned stamp,stamp_bad,stamp_mode;unsigned busy_extra,')
            anchor='static void setup(struct model *m)'
            wrappers=r'''
static int stamp(struct model *m,uint64_t previous,uint64_t deadline,uint64_t *out)
{
 m->stamp++;m->time++;uint64_t now=m->time;
 if(m->stamp==m->stamp_bad){if(m->stamp_mode==1)now=previous-1;else now=deadline;}
 if(now<previous||now>=deadline)return -5;*out=now;return 0;
}
static int read_timed(void *v,uint32_t off,uint64_t previous,uint64_t deadline,uint32_t *out,uint64_t *done)
{
 struct model *m=v;uint64_t before,after;if(stamp(m,previous,deadline,&before))return -5;
 uint32_t value;int rc=read_reg(v,off,&value);if(rc)return rc;
 if(stamp(m,before,deadline,&after))return -5;*out=value;*done=after;return 0;
}
static int write_timed(void *v,uint32_t off,uint32_t value,uint64_t previous,uint64_t deadline,uint64_t *done)
{
 struct model *m=v;uint64_t before,after;if(stamp(m,previous,deadline,&before))return -5;
 int rc=write_reg(v,off,value);if(rc)return rc;
 if(stamp(m,before,deadline,&after))return -5;*done=after;return 0;
}
'''
            text=p.util.once(text,anchor,wrappers+anchor)
            text=p.util.once(text,'{m,current,read_reg,write_reg,clock_us}','{m,current,read_timed,write_timed,clock_us}')
            text+=r'''
int main(void){struct model m;setup(&m);assert(!run(&m));
 assert(m.s.clocks==2&&m.s.reads==26&&m.s.writes==9&&m.stamp==70&&m.events==37);
 unsigned events=m.events,owners=m.owners,stamps=m.stamp,cases=0;
 for(unsigned i=1;i<=events;i++){
  setup(&m);m.event_fail=i;failed(&m);assert(m.events==i);cases++;
  for(unsigned mode=1;mode<=12;mode++){setup(&m);m.mutation=mode;m.mutation_at=i;failed(&m);cases++;}}
 for(unsigned i=1;i<=owners;i++){
  setup(&m);m.owner_fail=i;failed(&m);cases++;
  setup(&m);m.owner_mutate=i;failed(&m);cases++;
  setup(&m);m.owner_reenter=i;failed(&m);cases++;}
 for(unsigned i=1;i<=stamps;i++)for(unsigned mode=1;mode<=2;mode++){
  setup(&m);m.stamp_bad=i;m.stamp_mode=mode;failed(&m);assert(m.s.error==-5&&m.stamp==i);cases++;}
 setup(&m);m.busy_extra=20;assert(!run(&m));assert(m.s.polls==32&&m.s.reads==46&&m.s.clocks==2&&m.stamp==110);
 setup(&m);m.busy_extra=21;failed(&m);assert(m.s.polls==32);
 setup(&m);m.time=UINT64_MAX-10;failed(&m);assert(!m.reads&&!m.writes);
 for(unsigned upper=0;upper<8;upper++){setup(&m);uint32_t id=(upper<<29)|0x1fffffff;
 m.reply[0]=id>>16;m.reply[1]=id&0xffff;failed(&m);assert(m.ncr==0&&m.ncfgr==0);}
 printf("TIMED_MDIO_CORE_PASS EVENTS=%u OWNERS=%u FAULTS=%u STAMPS=%u NO_HARDWARE=1\n",events,owners,cases,stamps);return 0;}
'''
            host=folder/'host.c';host.write_text(text);exe=folder/'host'
            flags=['-std=c11','-Wall','-Wextra','-Werror','-I',str(folder),'-I',str(p.ROOT/'loader/rpi5')]
            r=subprocess.run(['xcrun','clang',*flags,'-fsanitize=address,undefined',str(host),
                str(folder/'rp1_gem_mdio.c'),str(folder/'rp1_gem_identify.c'),'-o',str(exe)],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run([exe],capture_output=True,text=True,timeout=30);self.assertEqual(r.returncode,0,r.stderr);print(r.stdout,end='')
            r=subprocess.run(['xcrun','clang',*flags,'--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align',
                '-mgeneral-regs-only','-ffreestanding','-fno-builtin','-O2','-c',str(folder/'rp1_gem_mdio.c'),'-o',str(folder/'core.o')],
                capture_output=True,text=True,timeout=30);self.assertEqual(r.returncode,0,r.stderr)

    def test_only_typed_timed_access_delta_and_original_limits(self):
        with tempfile.TemporaryDirectory(prefix='mdio-timed-overlay-') as name:
            folder=Path(name)/'overlay';p.emit(folder)
            changed={'rp1_gem_mdio.h','rp1_gem_mdio.c','BCM2712PCIePHYTransport.h','BCM2712RP1GEMIdentifyTransport.inc'}
            for source in p.FROZEN.iterdir():
                if source.is_file() and source.name not in changed:self.assertEqual(source.read_bytes(),(folder/source.name).read_bytes())
            text=(folder/'BCM2712RP1GEMIdentifyTransport.inc').read_text()
            for name in ('mdioRead','mdioWrite'):
                start=text.index('int BCM2712PCIePHYTransport::'+name+'(');end=text.index('\nint BCM2712PCIePHYTransport::',start+1)
                body=text[start:end];self.assertEqual(body.count('self->guard()'),2)
                self.assertEqual(body.count('mdioAccessStamp('),2)
            header=(folder/'rp1_gem_mdio.h').read_text()
            self.assertIn('#define RPI5_GEM_MDIO_POLLS 32u',header);self.assertIn('#define RPI5_GEM_MDIO_US 20000u',header)


if __name__=='__main__':unittest.main()
