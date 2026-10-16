# SPDX-License-Identifier: BSD-2-Clause
"""Full real owner/controller path; endpoint registers/VM remain explicit doubles."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import rp1_gem_identify_profile as profile
from tools.rpi5.tests import test_rp1_decode_transport as prior
full=prior.full

REGISTERS=r'''
alignas(16384) static uint32_t gem_registers[0x4000/4],clock_registers[0x14000/4];
static unsigned endpoint_reads;
static void initialize_endpoint(){
 memset(gem_registers,0,sizeof gem_registers);memset(clock_registers,0,sizeof clock_registers);
 const unsigned offset[]={0x14,0x18,0x20,0x8000,0x8004,0x8008,0x800c,0x8010,0x64,0x68,0x70,0x134,0x138,0x140,0x8014};
 const uint32_t value[]={0x802,1,4,0x80000001,4,20,0,0x51000,0x800,1,2,0x800,1,2,0x80000800};
 for(unsigned i=0;i<15;i++)clock_registers[offset[i]/4]=value[i];
 gem_registers[0xfc/4]=0x00070106;endpoint_reads=0;
}
'''


def source(folder,main,mutation=None):
    for name,adapt in (('rp1_decode_cycle.h',profile.decode_header),('rp1_decode_cycle.c',profile.decode_core)):
        (folder/name).write_text(adapt((profile.FROZEN/name).read_text()))
    for name in ('rp1_gem_identify.h','rp1_gem_identify.c'):
        (folder/name).write_bytes((profile.ROOT/'loader/rpi5'/name).read_bytes())
    text=prior.source(folder,main)
    text=profile.header(text);text=profile.transport(text)
    text=profile.util.once(text,'static unsigned map_fault,',REGISTERS+'\nstatic unsigned map_fault,')
    text=profile.util.once(text,'m->virt=0x1000000+n*0x20000;',
        'm->virt=reinterpret_cast<uint64_t>(n?clock_registers:gem_registers);')
    adapter=re.sub(r'__asm__ volatile\("[^"\n]*" ::: "memory"\);','/* host ordering double */',profile.ADAPTER)
    adapter=profile.util.once(adapter,
        'uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);',
        'uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);\n'
        '    endpoint_reads++;printf("GEMREAD %u %08x %08x\\n",index,offset,value);')
    text=profile.util.once(text,'int main(){',adapter+'\nint main(){initialize_endpoint();')
    return mutation(text) if mutation else text


def run(main,mutation=None):
    text=Path(prior.prior.__file__).read_text();start=text.index('def run(');end=text.index('\n\nclass AssignmentTransportTests',start)
    body=text[start:end]
    for old,new in (("'rp1_bars_assign','pcie_watchdog_lease'","'rp1_bars_assign','rp1_decode_cycle','rp1_gem_identify','pcie_watchdog_lease'"),
        ('for include in (full.FROZEN,','for include in (folder,full.FROZEN,'),
        ("            if name=='pcie_owner_composition_secure':",
         "            if name in ('rp1_decode_cycle','rp1_gem_identify'):path=folder/(name+'.c')\n"
         "            if name=='pcie_owner_composition_secure':")):
        body=profile.util.once(body,old,new)
    scope=dict(vars(prior.prior),source=source,profile=profile);exec(compile(body,__file__,'exec'),scope)
    return scope['run'](main,mutation)


class GEMTransportTests(unittest.TestCase):
    def test_predecessor_operations_identical_plus_exact_read_only_addition(self):
        def trace(text):
            needle='*reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=value;'
            self.assertEqual(text.count(needle),2);position=text.rindex(needle)
            text=text[:position]+text[position:].replace(needle,
                '*reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset)=value;'
                'record(\'w\',0,offset,4,value);',1)
            text=profile.util.once(text,
                '*reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=(uint16_t)value;',
                '*reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=(uint16_t)value;'
                'record(\'w\',0,offset,2,value);')
            return prior.prior.guards.operation_trace(text)
        before=prior.run(full.MAIN,trace);after=run(full.MAIN,trace)
        old=[v for v in before.splitlines() if v.startswith('OP ')]
        new=[v for v in after.splitlines() if v.startswith('OP ')]
        self.assertEqual(old,new);self.assertEqual(len(old),2167)
        self.assertEqual(len([v for v in after.splitlines() if v.startswith('GEMREAD ')]),32)
        self.assertIn('OP w 0 00008004 2 00000002',new)
        self.assertIn('OP w 0 00008004 2 00000000',new)
        print('GEM_TRANSPORT_PARITY_PASS EXISTING=2167 EXACT_NEW_READS=32 NO_NEW_WRITES=1')

    def test_real_owner_failures_before_and_after_register_reads(self):
        setup=full.MAIN.split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main='''int main(){unsigned cases=0;const unsigned targets[]={1,16,32};
 for(unsigned fault=1;fault<=12;fault++){for(unsigned side=0;side<2;side++){for(unsigned target: targets){
 memset(bridge,0,sizeof bridge);memset(resets,0,sizeof resets);memset(rescal,0,sizeof rescal);
 link_released=false;link_released_at=0;map_created=map_revoked=map_call=0;initialize_endpoint();wrong_thread=false;
'''+setup+r'''
 gem_fault=fault;gem_side=side;gem_target=target;gem_hit=false;
 bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);before=out;
 assert(!s.runBoundedRP1Trial(&out)&&gem_hit&&s.phase==BCM2712_PHY_FAILED);
 assert(s.gemSession.stage==RPI5_GEM_QUARANTINED&&s.decodeCycle.state==RPI5_RP1_DECODE_QUARANTINED);
 assert(!memcmp(&out,&before,sizeof out)&&s.assignment.state==RPI5_RP1_ASSIGN_ASSIGNED);
 assert(!map_revoked&&(bridge[0x8004/4]&0xffff)==2&&bridge[0x8010/4]==0x410000);
 assert(endpoint_reads==target-(side?0:1));unsigned stopped=smc_calls,stopped_reads=endpoint_reads;
 assert(!s.runBoundedRP1Trial(&out)&&smc_calls==stopped&&endpoint_reads==stopped_reads);
 cases++;
 }}}printf("GEM_REAL_OWNER_FAILURES_PASS CASES=%u NO_COMPENSATION=1\n",cases);return 0;}'''
        def mutation(text):
            text=profile.util.once(text,'static thread_t current_thread(){return &thread_identity;}',
                'static bool wrong_thread,gem_hit;static unsigned gem_fault,gem_side,gem_target;\n'
                'static thread_t current_thread(){return wrong_thread?nullptr:&thread_identity;}')
            function=text.index('int BCM2712PCIePHYTransport::gemRead(')
            before,body=text[:function],text[function:]
            changes=r'''
    if(!gem_hit && gem_side==SIDE && gem_target==TARGET){
      gem_hit=true;
      switch(gem_fault){
      case 1:wrong_thread=true;break;case 2:self->setPhase(BCM2712_PHY_CLOCK_FINISHING);break;
      case 3:self->fwClaimed=false;break;case 4:self->irqClaimed=false;break;
      case 5:self->checkingLifecycle=true;break;case 6:self->providerOpened=false;break;
      case 7:rpi5_pcie_wdog_lease.checks=65536;break;
      case 8:rpi5_pcie_fw_session.sequence=65536;break;
      case 9:rpi5_pcie_irq_session.state=RPI5_PCIE_IRQ_QUARANTINED;break;
      case 10:self->deviceBacking[0]=nullptr;break;
      case 11:self->deviceMaps[0]->virt=0;break;
      case 12:self->decodeCycle.state=RPI5_RP1_DECODE_UNMAPPING;break;
      }
    }
'''
            body=profile.util.once(body,'    if(!self || !out || index>1',
                changes.replace('SIDE','0').replace('TARGET','endpoint_reads+1')+'    if(!self || !out || index>1')
            body=profile.util.once(body,'    if(!self->guard() || gemSource',
                changes.replace('SIDE','1').replace('TARGET','endpoint_reads')+'    if(!self->guard() || gemSource')
            return before+body
        output=run(main,mutation);self.assertIn('GEM_REAL_OWNER_FAILURES_PASS CASES=72',output)

    def test_full_actual_owner_cost_mapping_and_restore(self):
        main=full.MAIN.replace(' return 0;',r'''
 assert(ok&&s.diagGemCall==2&&s.diagGemRC==0&&s.gemSession.stage==RPI5_GEM_COMPLETE);
 assert(s.decodeCycle.state==RPI5_RP1_DECODE_COMPLETE&&s.assignment.state==RPI5_RP1_ASSIGN_RESTORED);
 assert(endpoint_reads==32&&s.gemSession.reads==32&&out.gem.mid==0x00070106&&out.gem.system_hz==200000000);
 assert(map_created==2&&map_revoked==2&&!s.deviceMaps[0]&&!s.deviceMaps[1]);
 assert((bridge[0x8004/4]&0xffff)==0&&bridge[0x8010/4]==0xffffc000&&bridge[0x8014/4]==0xffc00000);
 assert(bridge[0x8018/4]==0xffff0000);
 unsigned guards=0;for(unsigned n:s.guards)guards+=n;
 assert(t.pm_checks==12+8*guards&&t.fw_sequence==1+2*guards&&t.pm_checks<65536);
 printf("GEM_RUNTIME_PASS PM=%u FW=%u GUARDS=%u ENDPOINT_READS=%u NO_REGISTER_WRITES=1 NO_HARDWARE=1\n",
  t.pm_checks,t.fw_sequence,guards,endpoint_reads);return 0;''')
        output=run(main);print(output,end='');self.assertIn('GEM_RUNTIME_PASS ',output)
        rows=[v for v in output.splitlines() if v.startswith('GEMREAD ')]
        offsets=[0x14,0x18,0x20,0x8000,0x8004,0x8008,0x800c,0x8010,0x64,0x68,0x70,0x134,0x138,0x140,0x8014]
        self.assertEqual([(int(v.split()[1]),int(v.split()[2],16)) for v in rows],
            [(1,n) for n in offsets]+[(0,0xfc),(0,0xfc)]+[(1,n) for n in offsets])

    def test_bad_clock_and_mid_fail_without_unmap_or_compensation(self):
        setup=full.MAIN.split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main='''int main(){for(unsigned fault=0;fault<3;fault++){
 memset(bridge,0,sizeof bridge);memset(resets,0,sizeof resets);memset(rescal,0,sizeof rescal);
 link_released=false;link_released_at=0;map_created=map_revoked=map_call=0;initialize_endpoint();
'''+setup+r'''
 if(fault==0)clock_registers[0x14/4]&=~(1u<<11);
 if(fault==1)clock_registers[0x8000/4]&=~(1u<<31);
 if(fault==2)gem_registers[0xfc/4]=UINT32_MAX;
 bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);before=out;
 assert(!s.runBoundedRP1Trial(&out)&&s.phase==BCM2712_PHY_FAILED);
 assert(s.gemSession.stage==RPI5_GEM_QUARANTINED&&s.decodeCycle.state==RPI5_RP1_DECODE_QUARANTINED);
 assert(!memcmp(&out,&before,sizeof out)&&s.assignment.state==RPI5_RP1_ASSIGN_ASSIGNED);
 assert(map_created==2&&!map_revoked&&s.deviceMaps[0]&&s.deviceMaps[1]);
 assert((bridge[0x8004/4]&0xffff)==2&&bridge[0x8010/4]==0x410000&&bridge[0x8014/4]==0);
 assert(endpoint_reads==(fault==2?32:15));unsigned stopped=smc_calls;
 assert(!s.runBoundedRP1Trial(&out)&&smc_calls==stopped);
 }printf("GEM_INVALID_PROFILE_PASS CASES=3 NO_COMPENSATION=1\n");return 0;}'''
        output=run(main);self.assertIn('GEM_INVALID_PROFILE_PASS CASES=3',output)

    def test_actual_logger_bounded_fields(self):
        encoder=prior.prior.encoder
        formats=re.findall(r'kprintf\("([^"\n]+)"',profile.diagnostic_calls());self.assertEqual(len(formats),10)
        lines=['int main(void){for(unsigned loc=4;loc<=8;loc+=4)for(unsigned sid=0;sid<2;sid++){','location_size=loc;subsystem=sid;']
        for fmt in formats:lines.append('assert(encode('+encoder.c_string(fmt)+','+encoder.values(fmt)+'));')
        lines+=['}assert(encoded_calls==40);printf("GEM_LOG_PASS CALLS=%u MAX_BYTES=%zu\\n",encoded_calls,max_bytes);return 0;}']
        with tempfile.TemporaryDirectory(prefix='rp1-gem-log-') as directory:
            folder=Path(directory);src=folder/'encoder.c';src.write_text(encoder.encoder_source()+'\n'.join(lines));exe=folder/'encoder'
            result=subprocess.run(['xcrun','clang','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(src),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([exe],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr);print(result.stdout,end='')


if __name__=='__main__':unittest.main()
