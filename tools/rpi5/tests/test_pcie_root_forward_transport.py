# SPDX-License-Identifier: BSD-2-Clause
"""Actual full owner/transport path; root/GEM registers and VM remain doubles."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import pcie_root_forward_profile as profile
from tools.rpi5.tests import test_rp1_gem_known as prior
gem=prior.prior
full=gem.full


def source(folder,main,mutation=None):
    text=prior.source(folder,main)
    for suffix in ('c','h'):
        path=profile.ROOT/'loader/rpi5'/('pcie_root_forward.'+suffix)
        (folder/path.name).write_bytes(path.read_bytes())
    text=profile.header(text);text=profile.caller(text);text=profile.gem_adapter(text)
    adapter=re.sub(r'__asm__ volatile\("[^"\n]*" ::: "memory"\);','/* host ordering double */',profile.ADAPTER)
    text=profile.util.once(text,'int main(){',adapter+'\nint main(){')
    return mutation(text) if mutation else text


def run(main,mutation=None):
    text=Path(gem.__file__).read_text();start=text.index('def run(');end=text.index('\n\nclass GEMTransportTests',start)
    body=profile.util.once(text[start:end],"'rp1_decode_cycle','rp1_gem_identify','pcie_watchdog_lease'",
        "'rp1_decode_cycle','rp1_gem_identify','pcie_root_forward','pcie_watchdog_lease'")
    body=profile.util.once(body,"if name in ('rp1_decode_cycle','rp1_gem_identify'):",
        "if name in ('rp1_decode_cycle','rp1_gem_identify','pcie_root_forward'):")
    scope=dict(vars(gem),source=source,profile=profile);exec(compile(body,__file__,'exec'),scope)
    return scope['run'](main,mutation)


def physical_route_model(text):
    # Explicit PCI bridge forwarding model, not an emulation/hardware claim.
    return profile.util.once(text,
        'uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);',
        '''uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);
    uint64_t pci=(index?0x18000u:0x100000u)+offset;
    uint64_t base=(uint64_t)(bridge[0x20/4]&0xfff0)<<16;
    uint64_t limit=(bridge[0x20/4]&0xfff00000)|0xfffff;
    if(!(bridge[1]&2) || pci<base || pci+3>limit)value=UINT32_MAX;''')


class RootForwardTransportTests(unittest.TestCase):
    def test_real_owner_failures_before_and_after_root_accesses(self):
        setup=full.MAIN.split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main='''int main(){unsigned cases=0;const unsigned targets[]={1,16,33,65,67,83};
 for(unsigned fault=1;fault<=10;fault++){for(unsigned side=0;side<2;side++){for(unsigned target:targets){
 memset(bridge,0,sizeof bridge);memset(resets,0,sizeof resets);memset(rescal,0,sizeof rescal);
 link_released=false;link_released_at=0;map_created=map_revoked=map_call=0;initialize_endpoint();wrong_thread=false;
'''+setup+r'''
 bridge[1]=0xa5a50000;bridge[0x20/4]=0x0000fff0;
 root_fault=fault;root_side=side;root_target=target;root_hit=false;root_ops=0;
 bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);before=out;
 assert(!s.runBoundedRP1Trial(&out)&&root_hit&&s.phase==BCM2712_PHY_FAILED);
 assert(s.rootForward.state==RPI5_ROOT_FORWARD_QUARANTINED&&s.decodeCycle.state==RPI5_RP1_DECODE_QUARANTINED);
 assert(!memcmp(&out,&before,sizeof out)&&s.assignment.state==RPI5_RP1_ASSIGN_ASSIGNED);
 assert(!map_revoked&&(bridge[0x8004/4]&0xffff)==2&&(bridge[1]&0xffff0000)==0xa5a50000);
 assert(!(bridge[1]&5)&&s.rootForward.reads<=79&&s.rootForward.writes<=4&&root_ops==target);
 unsigned stopped=smc_calls,stopped_reads=endpoint_reads,stopped_ops=root_ops;
 assert(!s.runBoundedRP1Trial(&out)&&smc_calls==stopped&&endpoint_reads==stopped_reads&&root_ops==stopped_ops);
 cases++;
 }}}printf("ROOT_FORWARD_REAL_FAULTS_PASS CASES=%u NO_COMPENSATION=1\n",cases);return 0;}'''
        def mutation(text):
            text=physical_route_model(text)
            text=profile.util.once(text,'static thread_t current_thread(){return &thread_identity;}',
                'static bool wrong_thread,root_hit;static unsigned root_fault,root_side,root_target,root_ops;\n'
                'static thread_t current_thread(){return wrong_thread?nullptr:&thread_identity;}')
            changes=r'''
    if(!root_hit && root_side==SIDE && root_ops==root_target){
      root_hit=true;
      switch(root_fault){
      case 1:wrong_thread=true;break;case 2:self->setPhase(BCM2712_PHY_CLOCK_FINISHING);break;
      case 3:self->fwClaimed=false;break;case 4:self->irqClaimed=false;break;
      case 5:rpi5_pcie_wdog_lease.checks=65536;break;case 6:rpi5_pcie_fw_session.sequence=65536;break;
      case 7:rpi5_pcie_irq_session.state=RPI5_PCIE_IRQ_QUARANTINED;break;
      case 8:self->providerOpened=false;break;case 9:self->decodeActive=false;break;
      case 10:self->deviceMaps[0]->virt=0;break;
      }
    }
'''
            start=text.index('int BCM2712PCIePHYTransport::rootForwardRead(')
            end=text.index('int BCM2712PCIePHYTransport::gemIdentify(',start)
            a,body,b=text[:start],text[start:end],text[end:]
            needle='    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);'
            self.assertEqual(body.count(needle),2)
            body=body.replace(needle,needle+'\n    root_ops++;\n'+changes.replace('SIDE','0'))
            body=profile.util.once(body,'    if(!self->guard() || rootForwardSource',
                changes.replace('SIDE','1')+'    if(!self->guard() || rootForwardSource')
            body=profile.util.once(body,'    return self->guard() && !rootForwardSource',
                changes.replace('SIDE','1')+'    return self->guard() && !rootForwardSource')
            return a+body+b
        output=run(main,mutation);print(output.splitlines()[-1]);self.assertIn('ROOT_FORWARD_REAL_FAULTS_PASS CASES=120',output)

    def test_all_prior_transport_operations_and_gem_reads_retained(self):
        def trace(text):
            if 'int BCM2712PCIePHYTransport::rootForwardRead(' in text:
                start=text.index('int BCM2712PCIePHYTransport::rootForwardRead(')
                end=text.index('int BCM2712PCIePHYTransport::gemIdentify(',start)
                a,body,b=text[:start],text[start:end],text[end:]
                body=body.replace('self->registers[BCM2712_PHY_BRIDGE]+offset','self->registers[BCM2712_PHY_BRIDGE] + offset')
                body=profile.util.once(body,'    *out=value;return 0;',
                    '    printf("ROOTOP r %08x %u %08x\\n",offset,width,value);\n    *out=value;return 0;')
                body=profile.util.once(body,'    return self->guard() && !rootForwardSource',
                    '    printf("ROOTOP w %08x %u %08x\\n",offset,width,value);\n    return self->guard() && !rootForwardSource')
                text=a+body+b
            needle='*reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=value;'
            self.assertEqual(text.count(needle),2);position=text.rindex(needle)
            text=text[:position]+text[position:].replace(needle,
                '*reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset)=value;'
                'record(\'w\',0,offset,4,value);',1)
            text=profile.util.once(text,'*reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=(uint16_t)value;',
                '*reinterpret_cast<volatile uint16_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=(uint16_t)value;record(\'w\',0,offset,2,value);')
            return gem.prior.prior.guards.operation_trace(text)
        before=prior.run(full.MAIN,trace);after=run(full.MAIN,trace)
        self.assertEqual([x for x in before.splitlines() if x.startswith(('OP ','GEMREAD '))],
            [x for x in after.splitlines() if x.startswith(('OP ','GEMREAD '))])
        root=[x for x in after.splitlines() if x.startswith('ROOTOP ')];self.assertEqual(len(root),83)
        self.assertEqual([x for x in root if x.startswith('ROOTOP w')],
            ['ROOTOP w 00000020 4 00400000','ROOTOP w 00000004 2 00000002',
             'ROOTOP w 00000004 2 00000000','ROOTOP w 00000020 4 00000000'])
        print('ROOT_FORWARD_OPERATION_PARITY_PASS PRIOR_TRANSPORT=2167 GEM_READS=32 ADDED_ROOT_ACCESSES=83')

    def test_full_actual_owner_cost_complete_root_endpoint_restore(self):
        main=full.MAIN.replace(' bcm2712_rp1_observation out={};',
            ' bridge[1]=0xa5a50000;bridge[0x20/4]=0x0000fff0;\n bcm2712_rp1_observation out={};')
        main=main.replace(' return 0;',r'''
 assert(ok&&s.diagRootForwardCall==2&&s.diagRootForwardRC==0);
 assert(s.rootForward.state==RPI5_ROOT_FORWARD_COMPLETE&&s.rootForward.reads==79&&s.rootForward.writes==4);
 assert(s.gemSession.stage==RPI5_GEM_COMPLETE&&endpoint_reads==32&&out.gem.mid==0x00070106);
 assert(out.rootForward.before.command==0&&out.rootForward.live.command==2&&out.rootForward.after.command==0);
 assert(out.rootForward.before.window==0xfff0&&out.rootForward.live.window==0x00400000&&out.rootForward.after.window==0xfff0);
 assert(bridge[1]==0xa5a50000&&bridge[0x20/4]==0x0000fff0);
 assert(map_created==2&&map_revoked==2&&(bridge[0x8004/4]&0xffff)==0);
 assert(bridge[0x8010/4]==0xffffc000&&bridge[0x8014/4]==0xffc00000&&bridge[0x8018/4]==0xffff0000);
 unsigned guards=0;for(unsigned n:s.guards)guards+=n;
 assert(t.pm_checks==12+8*guards&&t.fw_sequence==1+2*guards&&t.pm_checks<65536);
 printf("ROOT_FORWARD_RUNTIME_PASS PM=%u FW=%u GUARDS=%u ROOT_READS=79 ROOT_WRITES=4 GEM_READS=32 NO_HARDWARE=1\n",
   t.pm_checks,t.fw_sequence,guards);return 0;''')
        output=run(main,physical_route_model);print(output,end='')
        self.assertIn('ROOT_FORWARD_RUNTIME_PASS PM=63372 FW=15841 GUARDS=7920',output)

    def test_old_path_cannot_bypass_explicit_root_forwarding_model(self):
        setup=full.MAIN.split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main='int main(){'+setup+r'''
 bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);before=out;
 assert(!s.runBoundedRP1Trial(&out)&&!memcmp(&out,&before,sizeof out));
 assert(s.gemSession.stage==RPI5_GEM_QUARANTINED&&s.gemSession.reads==15&&!s.gemSession.clocks_ready);
 for(unsigned i=0;i<15;i++)assert(s.gemSession.before[i]==UINT32_MAX);
 assert(endpoint_reads==15&&s.gemSession.mid[0]==0&&map_revoked==0);
 printf("OLD_FORWARDING_MODEL_FAILS_CLOSED READS=15 NO_BOARD_CAUSE_CLAIM=1\n");return 0;}'''
        output=prior.run(main,physical_route_model);print(output,end='')
        self.assertIn('OLD_FORWARDING_MODEL_FAILS_CLOSED',output)

    def test_bounded_root_records_actual_apple_encoder(self):
        encoder=gem.prior.prior.encoder
        formats=re.findall(r'kprintf\("([^"\n]+)"',profile.diagnostic_calls());self.assertEqual(len(formats),7)
        lines=['int main(void){for(unsigned loc=4;loc<=8;loc+=4)for(unsigned sid=0;sid<2;sid++){','location_size=loc;subsystem=sid;']
        for fmt in formats:lines.append('assert(encode('+encoder.c_string(fmt)+','+encoder.values(fmt)+'));')
        lines+=['}assert(encoded_calls==28);printf("ROOT_FORWARD_LOG_PASS CALLS=%u MAX_BYTES=%zu\\n",encoded_calls,max_bytes);return 0;}']
        with tempfile.TemporaryDirectory(prefix='root-forward-log-') as directory:
            folder=Path(directory);src=folder/'encoder.c';src.write_text(encoder.encoder_source()+'\n'.join(lines));exe=folder/'encoder'
            result=subprocess.run(['xcrun','clang','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(src),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([exe],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr);print(result.stdout,end='')


if __name__=='__main__':unittest.main()
