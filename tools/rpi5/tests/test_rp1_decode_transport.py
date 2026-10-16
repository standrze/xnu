# SPDX-License-Identifier: BSD-2-Clause
"""Actual new adapter/full owner chain with explicit Device/IOKit doubles."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import rp1_decode_profile as profile
from tools.rpi5.tests import test_rp1_bars_assignment_transport as prior
full=prior.full

MAP_STUBS=r'''
using IOByteCount=uint64_t;
enum {kIODirectionNone=0,kIOMemoryMapperNone=1,kIOMemoryHostOnly=2,kIOInhibitCache=1,
 kIOMemoryBufferCacheShift=8,kIOMapAnywhere=1,kIOMapInhibitCache=0x100,kIOMapCacheMask=0xf00,
 kIOMapStatic=0x1000000,kIOMapReference=0x2000000,kIOMapUnique=0x4000000,kIOReturnSuccess=0};
static unsigned map_fault,map_target,map_created,map_revoked,map_call;
struct IOMemoryDescriptor;
struct IOMemoryMap {
 uint64_t physical=0,length=0,virt=0;unsigned options=0,index=0;
 IOMemoryDescriptor *backing=nullptr;
 IOMemoryDescriptor *getMemoryDescriptor(){return backing;}
 uint64_t getVirtualAddress(){return virt;}uint64_t getLength(){return length;}
 unsigned getMapOptions(){return options;}
 uint64_t getPhysicalSegment(unsigned off,uint64_t *bytes,unsigned){assert(!off);*bytes=length;return physical;}
 int unmap(){map_call++;if(map_fault==11&&index==map_target)return -1;virt=0;map_revoked++;
  if(map_fault==12&&index==map_target)return -1;return 0;}
 void release(){assert(!virt);}
};
static IOMemoryMap mapped_devices[2];
struct IOMemoryDescriptor {
 uint64_t address=0,bytes=0;
 static IOMemoryDescriptor *withAddressRange(uint64_t address,uint64_t bytes,unsigned opts,void *task){
  assert(!task&&opts==(kIODirectionNone|kIOMemoryMapperNone|kIOMemoryHostOnly|(kIOInhibitCache<<kIOMemoryBufferCacheShift)));
  assert((address==0x1f00100000&&bytes==0x4000)||(address==0x1f00018000&&bytes==0x14000));
  if(map_fault==1&&map_created==map_target)return nullptr;
  static IOMemoryDescriptor descriptors[2];auto &d=descriptors[map_created];d.address=address;d.bytes=bytes;return &d;
 }
 IOMemoryMap *map(unsigned opts){
  assert(opts==(kIOMapAnywhere|kIOMapInhibitCache));assert(map_created<2);
  unsigned n=map_created++;if(map_fault==2&&n==map_target)return nullptr;
  IOMemoryMap *m=&mapped_devices[n];*m={};m->physical=address;m->length=bytes;m->virt=0x1000000+n*0x20000;m->options=opts;m->index=n;m->backing=this;
  if(n==map_target)switch(map_fault){
   case 3:m->virt=0;break;case 4:m->virt++;break;case 5:m->length+=0x4000;break;
   case 6:m->physical+=0x4000;break;case 7:m->options^=kIOMapInhibitCache;break;
   case 8:m->options^=kIOMapUnique;break;case 9:m->virt=UINT64_MAX-0x3fff;break;
   case 10:if(n)m->virt=mapped_devices[0].virt;break;
   case 14:m->backing=nullptr;break;
  }
  return m;
 }
 void release(){}
};
static unsigned rpi5_physical_memory_type(uint64_t begin,uint64_t end){
 assert((begin==0x1f00100000&&end==0x1f00104000)||(begin==0x1f00018000&&end==0x1f0002c000));
 return map_fault==13&&map_created==map_target?0:2;
}
'''


def source(folder,main,mutation=None):
    text=prior.source(folder,main)
    text=profile.header(text);text=profile.transport(text)
    text=profile.util.once(text,'struct OSData{};struct IOMemoryMap{};','struct OSData{};\n'+MAP_STUBS)
    adapter=re.sub(r'__asm__ volatile\("[^"\n]*" ::: "memory"\);','/* host ordering double */',profile.ADAPTER)
    text=profile.util.once(text,'int main(){',adapter+'\nint main(){')
    return mutation(text) if mutation else text


def run(main,mutation=None):
    # Same immutable actual full-runtime compilation list plus this one core.
    text=Path(prior.__file__).read_text();start=text.index('def run(');end=text.index('\n\nclass AssignmentTransportTests',start)
    body=text[start:end].replace("'rp1_bars_assign','pcie_watchdog_lease'","'rp1_bars_assign','rp1_decode_cycle','pcie_watchdog_lease'")
    if body==text[start:end]:raise AssertionError('Exact prior native source list changed')
    scope=dict(vars(prior),source=source);exec(compile(body,__file__,'exec'),scope)
    return scope['run'](main,mutation)


class RP1DecodeTransportTests(unittest.TestCase):
    def test_real_source_and_owner_failures_at_every_transition(self):
        setup=full.MAIN.split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main='''int main(){unsigned cases=0;
 for(unsigned fault=1;fault<=15;fault++)for(unsigned point=0;point<5;point++){
 memset(bridge,0,sizeof bridge);memset(resets,0,sizeof resets);memset(rescal,0,sizeof rescal);
 link_released=false;link_released_at=0;map_created=map_revoked=map_call=0;wrong_thread=false;
'''+setup+r'''
 decode_fault=fault;decode_point=point;decode_hit=false;
 bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);before=out;
 assert(!s.runBoundedRP1Trial(&out)&&decode_hit&&s.phase==BCM2712_PHY_FAILED);
 assert(s.decodeCycle.state==RPI5_RP1_DECODE_QUARANTINED&&!s.decodeCycle.pending_map&&!s.decodeCycle.pending_write);
 assert(!memcmp(&out,&before,sizeof out)&&s.assignment.state==RPI5_RP1_ASSIGN_ASSIGNED);
 assert((bridge[0x8004/4]&0xffff)==0||(bridge[0x8004/4]&0xffff)==2);
 assert(bridge[0x8010/4]==0x410000&&bridge[0x8014/4]==0&&bridge[0x8018/4]==0x400000);
 unsigned stopped=smc_calls,stopped_maps=map_call;
 assert(!s.runBoundedRP1Trial(&out)&&smc_calls==stopped&&stopped_maps==map_call);
 cases++;
 }
 printf("DECODE_REAL_SOURCE_FAILURES_PASS CASES=%u NO_FORCED_CLEANUP=1\n",cases);return 0;}'''
        def mutation(text):
            text=profile.util.once(text,'static thread_t current_thread(){return &thread_identity;}',
                'static bool wrong_thread,decode_hit;static unsigned decode_fault,decode_point;\n'
                'static thread_t current_thread(){return wrong_thread?nullptr:&thread_identity;}')
            start=text.index('int BCM2712PCIePHYTransport::decodeSource(')
            a,b=text[:start],text[start:]
            b=profile.util.once(b,'    if(!self || !self->decodeActive',r'''
    bool target=self && ((decode_point==0 && s->state==RPI5_RP1_DECODE_CHECKING) ||
        (decode_point==1 && s->state==RPI5_RP1_DECODE_ENABLING && s->pending_write) ||
        (decode_point==2 && s->state==RPI5_RP1_DECODE_MAPPING && s->pending_map) ||
        (decode_point==3 && s->state==RPI5_RP1_DECODE_UNMAPPING && s->pending_map) ||
        (decode_point==4 && s->state==RPI5_RP1_DECODE_DISABLING && s->pending_write));
    if(target&&!decode_hit){
      decode_hit=true;
      switch(decode_fault){
      case 1:wrong_thread=true;break;case 2:self->setPhase(BCM2712_PHY_CLOCK_FINISHING);break;
      case 3:self->ownerProvider->opened=false;break;case 4:self->providerOpened=false;break;
      case 5:self->fwClaimed=false;break;case 6:self->irqClaimed=false;break;
      case 7:self->checkingLifecycle=true;break;case 8:phyOwner=nullptr;break;
      case 9:self->lifecyclePhase=BCM2712_CONTROLLER_HELD_RESET;break;
      case 10:s=nullptr;break;case 11:a=nullptr;break;case 12:self->decodeActive=false;break;
      case 13:rpi5_pcie_wdog_lease.checks=65536;break;
      case 14:rpi5_pcie_fw_session.sequence=65536;break;
      case 15:rpi5_pcie_irq_session.state=RPI5_PCIE_IRQ_QUARANTINED;break;
      }
    }
    if(!self || !self->decodeActive''')
            return a+b
        output=run(main,mutation);print(output,end='');self.assertIn('CASES=75',output)

    def test_exact_transport_prefix_only_command_halfwords_inserted(self):
        def trace(text):
            needle='*reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=value;'
            self.assertEqual(text.count(needle),2)
            position=text.rindex(needle)
            text=text[:position]+text[position:].replace(needle,
                '*reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset)=value;'
                'record(\'w\',0,offset,4,value);',1)
            if 'decodeWrite(void' in text:
                text=profile.util.once(text,
                    '*reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=(uint16_t)value;',
                    '*reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=(uint16_t)value;'
                    'record(\'w\',0,offset,2,value);')
            return prior.guards.operation_trace(text)
        before=prior.run(full.MAIN,trace);after=run(full.MAIN,trace)
        old=[x for x in before.splitlines() if x.startswith('OP ')]
        new=[x for x in after.splitlines() if x.startswith('OP ')]
        common=next(i for i,(a,b) in enumerate(zip(old,new)) if a!=b)
        self.assertGreater(common,1500)
        added=len(new)-len(old);self.assertGreater(added,100)
        self.assertEqual(old[common:],new[common+added:])
        writes=[x for x in new[common:common+added] if x.startswith('OP w 0 00008')]
        self.assertEqual(writes,['OP w 0 00008004 2 00000002','OP w 0 00008004 2 00000000'])
        print(f'DECODE_TRANSPORT_TRACE_PASS BEFORE={len(old)} AFTER={len(new)} INSERTED={added} HALFWORD_WRITES=2')

    def test_two_passive_records_fit_actual_apple_encoder(self):
        encoder=prior.encoder
        formats=re.findall(r'kprintf\("([^"\n]+)"',profile.diagnostic_calls())
        self.assertEqual(len(formats),2)
        lines=['int main(void){for(unsigned loc=4;loc<=8;loc+=4)for(unsigned sid=0;sid<2;sid++){','location_size=loc;subsystem=sid;']
        for fmt in formats:lines.append('assert(encode('+encoder.c_string(fmt)+','+encoder.values(fmt)+'));')
        lines+=['}assert(encoded_calls==8);printf("DECODE_LOG_PASS CALLS=%u MAX_BYTES=%zu\\n",encoded_calls,max_bytes);return 0;}']
        with tempfile.TemporaryDirectory(prefix='rp1-decode-log-') as directory:
            folder=Path(directory);src=folder/'encoder.c';src.write_text(encoder.encoder_source()+'\n'.join(lines));exe=folder/'encoder'
            result=subprocess.run(['xcrun','clang','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(src),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([exe],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn('DECODE_LOG_PASS CALLS=8 MAX_BYTES=',result.stdout)
            self.assertLess(int(re.search(r'MAX_BYTES=(\d+)',result.stdout)[1]),100)

    def test_entire_runtime_actual_owner_cost_and_private_unmap(self):
        main=full.MAIN.replace(' return 0;',r'''
 assert(ok&&s.diagDecodeCall==3&&!s.decodeActive&&s.decodeCycle.state==RPI5_RP1_DECODE_COMPLETE);
 assert(s.decodeCycle.transactions==34&&s.decodeCycle.writes_started==2&&map_created==2&&map_revoked==2);
 assert(out.decode.command_before==0&&out.decode.command_enabled==2&&out.decode.command_after==0);
 assert(!s.deviceMaps[0]&&!s.deviceMaps[1]&&out.decode.mapped==3&&out.decode.unmapped==3);
 assert(bridge[0x8010/4]==0xffffc000&&bridge[0x8014/4]==0xffc00000&&bridge[0x8018/4]==0xffff0000);
 assert((bridge[0x8004/4]&0xffff)==0);
 unsigned guards=0;for(unsigned n:s.guards)guards+=n;
 assert(t.pm_checks==12+8*guards&&t.fw_sequence==1+2*guards&&t.pm_checks<65536);
 printf("DECODE_RUNTIME_PASS PM=%u FW=%u GUARDS=%u MAPS=%u UNMAPS=%u NO_NIC_ACCESS=1 NO_HARDWARE=1\n",
  t.pm_checks,t.fw_sequence,guards,map_created,map_revoked);
 return 0;''')
        output=run(main);print(output,end='');self.assertIn('DECODE_RUNTIME_PASS ',output)

    def test_real_adapter_rejects_bad_device_mappings_without_cleanup(self):
        setup=full.MAIN.split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main='''int main(){unsigned cases=0;
 for(unsigned fault=1;fault<=14;fault++)for(unsigned target=0;target<2;target++){
 if(fault==10&&!target)continue;
 memset(bridge,0,sizeof bridge);memset(resets,0,sizeof resets);memset(rescal,0,sizeof rescal);
 link_released=false;link_released_at=0;map_created=map_revoked=map_call=0;
'''+setup+r'''
 map_fault=fault;map_target=target;
 bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);before=out;
 assert(!s.runBoundedRP1Trial(&out)&&s.phase==BCM2712_PHY_FAILED);
 assert(s.decodeCycle.state==RPI5_RP1_DECODE_QUARANTINED&&!s.decodeCycle.pending_map&&!s.decodeCycle.pending_write);
 assert(!memcmp(&out,&before,sizeof out)&&s.assignment.state==RPI5_RP1_ASSIGN_ASSIGNED);
 assert((bridge[0x8004/4]&0xffff)==2); /* no forced disable after mapping failure */
 assert(bridge[0x8010/4]==0x410000&&bridge[0x8014/4]==0&&bridge[0x8018/4]==0x400000);
 unsigned stopped=smc_calls,stopped_maps=map_call;
 assert(!s.runBoundedRP1Trial(&out)&&smc_calls==stopped&&stopped_maps==map_call);
 cases++;
 }
 printf("DECODE_REAL_MAP_FAILURES_PASS CASES=%u NO_FORCED_CLEANUP=1\n",cases);return 0;}'''
        output=run(main);print(output,end='');self.assertIn('CASES=27',output)

    def test_frozen_owners_and_original_sources_unchanged(self):
        with tempfile.TemporaryDirectory(prefix='decode-overlay-') as directory:
            path=Path(directory)/'overlay';profile.emit(path)
            for name in ('BCM2712PCIeFWTransport.inc','rpi5_pcie_fw_owner.inc','rpi5_pcie_irq_owner.inc',
                'rpi5_pcie_watchdog_owner.inc','BCM2712RP1AssignmentTransport.inc','rp1_bars_assign.c'):
                self.assertEqual((path/name).read_bytes(),(profile.FROZEN/name).read_bytes())


if __name__=='__main__':unittest.main()
