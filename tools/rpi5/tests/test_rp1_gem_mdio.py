# SPDX-License-Identifier: BSD-2-Clause
"""Actual C22 core and complete owner composition, explicit MMIO/PHY doubles."""
from pathlib import Path
import re
import hashlib
import json
import subprocess
import tempfile
import unittest
from tools.rpi5 import rp1_gem_mdio_profile as profile
from tools.rpi5.tests import test_rp1_gem_capabilities as cap
from tools.rpi5.tests import test_pcie_fdt as fdt
full=cap.full


def source(folder,main,mutation=None):
    text=cap.source(folder,main)
    for suffix in ('c','h'):
        path=profile.ROOT/'loader/rpi5'/('rp1_gem_mdio.'+suffix)
        (folder/path.name).write_bytes(path.read_bytes())
    text=profile.header(text);text=profile.parent_transport(text);text=profile.gem_transport(text)
    text=re.sub(r'__asm__ volatile\("[^"\n]*" ::: "memory"\);','/* explicit host ordering double */',text)
    text=profile.util.once(text,'struct OSData{};',r'''struct OSData {
        const void *bytes;size_t length;
        const void *getBytesNoCopy()const{return bytes;}
        size_t getLength()const{return length;}
    };''')
    tree=fdt._encode_fdt(fdt._synthetic_tree())
    text=profile.util.once(text,'int main(){',
        'static const unsigned char mdio_fdt[]={'+','.join(str(x) for x in tree)+'};\nint main(){')
    text=profile.util.once(text,
        'const uint32_t cap_values[]={0x08800000,0x03f00000,0x100,0x0a8000aa,0x01020304,0x5400,0x04000000};',
        'const uint32_t cap_values[]={0x08508513,0x6eb13fff,0x502e5b45,0x08820000,0,0x24444444,0};')
    text=profile.util.once(text,'static unsigned endpoint_reads,capability_reads;',
        'static unsigned endpoint_reads,capability_reads,mdio_reads,mdio_writes,mdio_commands,mdio_busy;')
    text=profile.util.once(text,'endpoint_reads=capability_reads=0;',
        'endpoint_reads=capability_reads=mdio_reads=mdio_writes=mdio_commands=0;\n'
        '    gem_registers[0]=0;gem_registers[1]=0;gem_registers[2]=4;')
    start=text.index('int BCM2712PCIePHYTransport::mdioRead(')
    before,body=text[:start],text[start:]
    body=profile.util.once(body,'    uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);',r'''
    uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);
    if(offset==8 && mdio_busy){value=0;mdio_busy--;}
    mdio_reads++;printf("MDIO_READ %08x %08x\n",offset,value);''')
    body=profile.util.once(body,'    *reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset)=value;',r'''
    *reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset)=value;
    mdio_writes++;printf("MDIO_WRITE %08x %08x\n",offset,value);
    if(offset==0x34){
      const unsigned regs[]={2,3,0,1,1},values[]={0x600d,0x84a2,0x1140,0x7909,0x792d};
      assert(mdio_commands<5 && value==(0x60820000u|(regs[mdio_commands]<<18)));
      gem_registers[0x34/4]=(value&~0xffffu)|values[mdio_commands++];
    }''')
    return mutation(before+body) if mutation else before+body


def run(main,mutation=None):
    original=cap.base.gem.prior.prior
    text=Path(original.__file__).read_text();start=text.index('def run(');end=text.index('\n\nclass AssignmentTransportTests',start)
    body=text[start:end]
    body=profile.util.once(body,'for include in (full.FROZEN,','for include in (folder,full.FROZEN,')
    body=profile.util.once(body,"'rp1_bars_assign','pcie_watchdog_lease'",
        "'rp1_bars_assign','rp1_decode_cycle','rp1_gem_identify','pcie_root_forward','rp1_gem_capabilities','rp1_gem_mdio','pcie_fdt','fdt','fdt_reg','pcie_watchdog_lease'")
    body=profile.util.once(body,"            if name=='pcie_owner_composition_secure':",
        "            if name in ('rp1_decode_cycle','rp1_gem_identify','pcie_root_forward','rp1_gem_capabilities','rp1_gem_mdio'):path=folder/(name+'.c')\n"
        "            if name=='pcie_owner_composition_secure':")
    scope=dict(vars(original),source=source,profile=profile);exec(compile(body,__file__,'exec'),scope)
    return scope['run'](main,mutation)


def main_source(extra=''):
    return full.MAIN.replace(' bcm2712_rp1_observation out={};',r'''
    OSData firmware={mdio_fdt,sizeof mdio_fdt};s.firmwareFDT=&firmware;
    assert(!rpi5_fdt_pcie_rp1(mdio_fdt,sizeof mdio_fdt,&s.binding));
    bridge[1]=0xa5a50000;bridge[0x20/4]=0x0000fff0;
'''+extra+'\n bcm2712_rp1_observation out={};')


class GEMMDIOTests(unittest.TestCase):
    def test_pinned_primary_management_abi(self):
        refs=json.loads((profile.ROOT/'tools/rpi5/rp1_gem_mdio_sources.json').read_text())
        for row in refs['sources']:
            raw=(profile.ROOT/row['path']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256']);self.assertEqual(len(raw),row['bytes'])
        header=(profile.ROOT/refs['sources'][0]['path']).read_text()
        for token,value in (('MACB_NCR',0),('MACB_NCFGR',4),('MACB_NSR',8),('MACB_MAN',0x34)):
            match=re.search(r'^#define\s+'+token+r'\s+(0x[0-9a-fA-F]+)',header,re.M)
            self.assertIsNotNone(match);self.assertEqual(int(match[1],16),value)
        for field,offset,width in (('MPE',4,1),('IDLE',2,1),('DATA',0,16),('CODE',16,2),
            ('REGA',18,5),('PHYA',23,5),('RW',28,2),('SOF',30,2)):
            self.assertRegex(header,rf'#define\s+MACB_{field}_OFFSET\s+{offset}\b')
            self.assertRegex(header,rf'#define\s+MACB_{field}_SIZE\s+{width}\b')
        self.assertRegex(header,r'#define\s+GEM_CLK_OFFSET\s+18\b')
        self.assertRegex(header,r'#define\s+GEM_CLK_DIV96\s+5\b')
        driver=(profile.ROOT/refs['sources'][1]['path']).read_text()
        self.assertIn('pclk_hz <= 240000000',driver);self.assertIn('GEM_BF(CLK, GEM_CLK_DIV96)',driver)
        feature=driver[driver.index('macb_set_rxcsum_feature('):driver.index('macb_set_rxcsum_feature(')+1000]
        self.assertIn('gem_readl(bp, NCFGR)',feature);self.assertIn('gem_writel(bp, NCFGR, val)',feature)
        mdio=(profile.ROOT/refs['sources'][5]['path']).read_text();self.assertIn('defined 2.5MHz',mdio)

    def test_actual_core_faults_and_a76(self):
        with tempfile.TemporaryDirectory(prefix='gem-mdio-core-') as name:
            folder=Path(name)/'overlay';profile.emit(folder);exe=folder/'test'
            flags=['-std=c11','-Wall','-Wextra','-Werror','-I',str(folder),'-I',str(profile.ROOT/'loader/rpi5')]
            result=subprocess.run(['xcrun','clang',*flags,'-fsanitize=address,undefined',
                str(Path(__file__).with_name('rp1_gem_mdio_host.c')),str(folder/'rp1_gem_mdio.c'),
                str(folder/'rp1_gem_identify.c'),'-o',str(exe)],text=True,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([exe],text=True,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr);print(result.stdout,end='')
            self.assertIn('MAX_EVENTS=112 NO_PHY_WRITES=1',result.stdout)
            result=subprocess.run(['xcrun','clang',*flags,'--target=aarch64-none-elf','-mcpu=cortex-a76',
                '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin','-fno-stack-protector',
                '-O2','-c',str(folder/'rp1_gem_mdio.c'),'-o',str(folder/'mdio.o')],text=True,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_actual_full_owner_phy_roundtrip_and_worst_poll_budget(self):
        main=main_source('mdio_busy=20;')
        main=main.replace(' return 0;',r'''
    assert(ok && s.mdioSession.state==RPI5_GEM_MDIO_COMPLETE && s.gemSession.stage==RPI5_GEM_COMPLETE);
    assert(out.phy.phy_id==0x600d84a2 && out.phy.link==1 && out.phy.autoneg_complete==1);
    assert(out.phy.polls==32 && out.phy.reads==46 && out.phy.writes==9 && out.phy.clocks==57);
    assert(mdio_commands==5 && mdio_reads==46 && mdio_writes==9 && gem_registers[0]==0 && gem_registers[1]==0);
    assert(s.rootForward.state==RPI5_ROOT_FORWARD_COMPLETE && s.decodeCycle.state==RPI5_RP1_DECODE_COMPLETE);
    assert(s.assignment.state==RPI5_RP1_ASSIGN_RESTORED && map_revoked==2 && bridge[1]==0xa5a50000 && bridge[0x20/4]==0xfff0);
    unsigned guards=0;for(unsigned n:s.guards)guards+=n;
    assert(t.pm_checks==12+8*guards && t.fw_sequence==1+2*guards && t.pm_checks<65536);
    printf("GEM_MDIO_FULL_PASS PM=%u FW=%u GUARDS=%u MDIO_READS=%u MDIO_WRITES=%u POLLS=%u NO_HARDWARE=1\n",
        t.pm_checks,t.fw_sequence,guards,mdio_reads,mdio_writes,s.mdioSession.polls);
    return 0;''')
        output=run(main);print('\n'.join(output.splitlines()[-8:]))
        self.assertIn('GEM_MDIO_FULL_PASS PM=65420 FW=16353 GUARDS=8176',output)
        rows=[line for line in output.splitlines() if line.startswith(('GEMREAD ','CAPREAD ','MDIO_'))]
        self.assertEqual([x.split()[0] for x in rows[:33]],['GEMREAD']*17+['CAPREAD']*16)
        self.assertEqual([x.split()[0] for x in rows[-15:]],['GEMREAD']*15)
        writes=[x for x in rows if x.startswith('MDIO_WRITE')]
        self.assertEqual(writes,[f'MDIO_WRITE {off:08x} {value:08x}' for off,value in (
            (4,0x140000),(0,0x10),(0x34,0x608a0000),(0x34,0x608e0000),(0x34,0x60820000),
            (0x34,0x60860000),(0x34,0x60860000),(0,0),(4,0))])

    def test_actual_adapter_failures_preserve_global_owner_and_quarantine(self):
        setup=main_source().split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main=r'''int main(){unsigned cases=0;const unsigned targets[]={1,9,19,69,70,71};
 for(unsigned fault=1;fault<=16;fault++){for(unsigned side=0;side<2;side++){for(unsigned target:targets){
 memset(bridge,0,sizeof bridge);memset(resets,0,sizeof resets);memset(rescal,0,sizeof rescal);
 link_released=false;link_released_at=0;map_created=map_revoked=map_call=0;initialize_endpoint();wrong_thread=false;
 mdio_callback_count=0;mdio_fault_hit=false;mdio_busy=0;
'''+setup+r'''
 mdio_fault=fault;mdio_fault_side=side;mdio_fault_target=target;
 bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);before=out;
 assert(!s.runBoundedRP1Trial(&out)&&mdio_fault_hit&&s.phase==BCM2712_PHY_FAILED);
 assert(s.mdioSession.state==RPI5_GEM_MDIO_QUARANTINED&&s.gemSession.stage==RPI5_GEM_QUARANTINED);
 assert(s.decodeCycle.state==RPI5_RP1_DECODE_QUARANTINED&&!map_revoked&&!memcmp(&out,&before,sizeof out));
 // A mutation after nowUS's completed guard pair can be detected by the next
 // time callback's actual owner guard. It must never admit another data IO.
 assert(mdio_callback_count>=target&&mdio_callback_count<=target+1&&s.assignment.state==RPI5_RP1_ASSIGN_ASSIGNED);
 assert(mdio_reads==mdio_fault_reads&&mdio_writes==mdio_fault_writes);
 unsigned stopped=smc_calls,r=mdio_reads,w=mdio_writes;
 assert(!s.runBoundedRP1Trial(&out)&&smc_calls==stopped&&mdio_reads==r&&mdio_writes==w);cases++;
 }}}printf("GEM_MDIO_ACTUAL_FAILURES_PASS CASES=%u NO_COMPENSATING_IO=1\n",cases);return 0;}'''
        def mutation(text):
            text=profile.util.once(text,'static thread_t current_thread(){return &thread_identity;}',
                'static bool wrong_thread,mdio_fault_hit;static unsigned mdio_fault,mdio_fault_side,mdio_fault_target,mdio_callback_count,mdio_fault_reads,mdio_fault_writes;\n'
                'static thread_t current_thread(){return wrong_thread?nullptr:&thread_identity;}')
            changes=r'''
    if(!mdio_fault_hit && mdio_fault_side==SIDE && mdio_callback_count==mdio_fault_target){
      mdio_fault_hit=true;mdio_fault_reads=mdio_reads;mdio_fault_writes=mdio_writes;switch(mdio_fault){
      case 1:wrong_thread=true;break;case 2:self->setPhase(BCM2712_PHY_CLOCK_FINISHING);break;
      case 3:self->fwClaimed=false;break;case 4:self->irqClaimed=false;break;
      case 5:self->checkingLifecycle=true;break;case 6:self->providerOpened=false;break;
      case 7:rpi5_pcie_wdog_lease.checks=65536;break;case 8:rpi5_pcie_fw_session.sequence=65536;break;
      case 9:rpi5_pcie_irq_session.state=RPI5_PCIE_IRQ_QUARANTINED;break;
      case 10:self->deviceBacking[0]=nullptr;break;case 11:self->deviceMaps[0]->virt=0;break;
      case 12:self->decodeCycle.state=RPI5_RP1_DECODE_UNMAPPING;break;
      case 13:self->firmwareFDT->bytes=nullptr;break;case 14:self->binding.phy_address=2;break;
      case 15:self->capabilitySession.state=RPI5_GEM_CAP_QUARANTINED;break;
      case 16:assert(rpi5_gem_mdio_run(&self->mdioSession,&self->capabilitySession,&self->binding,
          &self->mdioSession.io,&self->mdioObserved));break;}}
'''
            for name,tail in (('mdioRead','    if(!self->guard() || mdioSource'),
                ('mdioWrite','    return self->guard() &&'),('mdioTime','    if(rc || mdioSource')):
                start=text.index('int BCM2712PCIePHYTransport::'+name+'(')
                end=text.find('\nint BCM2712PCIePHYTransport::',start+1)
                if end<0:end=len(text)
                before,body,after=text[:start],text[start:end],text[end:]
                needle='    auto *self=static_cast<BCM2712PCIePHYTransport *>(context);'
                body=profile.util.once(body,needle,needle+'\n    mdio_callback_count++;\n'+changes.replace('SIDE','0'))
                body=profile.util.once(body,tail,changes.replace('SIDE','1')+tail)
                text=before+body+after
            return text
        output=run(main,mutation);self.assertIn('GEM_MDIO_ACTUAL_FAILURES_PASS CASES=192',output)
        print(output.splitlines()[-1])

    def test_private_profile_preserves_all_owner_and_transport_dependencies(self):
        with tempfile.TemporaryDirectory(prefix='gem-mdio-overlay-') as name:
            folder=Path(name)/'overlay';profile.emit(folder)
            changed={'BCM2712PCIePHYTransport.h','BCM2712RP1GEMIdentifyTransport.inc','BCM2712RP1ConfigTransport.inc'}
            for old in profile.FROZEN.iterdir():
                if old.is_file() and old.name not in changed:self.assertEqual(old.read_bytes(),(folder/old.name).read_bytes())
            adapter=(folder/'BCM2712RP1GEMIdentifyTransport.inc').read_text()
            self.assertIn('rpi5_fdt_pcie_rp1(self->mdioFDTBytes,self->mdioFDTLength,&fresh)',adapter)
            self.assertIn('self->firmwareFDT->getBytesNoCopy()!=self->mdioFDTBytes',adapter)
            self.assertIn('self->firmwareFDT->getLength()!=self->mdioFDTLength',adapter)

    def test_actual_adapter_reparses_original_fdt_before_any_management_io(self):
        def node(tree,name):
            if tree['name']==name:return tree
            for child in tree['children']:
                found=node(child,name)
                if found:return found
        mode=fdt._synthetic_tree();node(mode,'ethernet@100000')['properties']['phy-mode']=b'rgmii\0'
        handle=fdt._synthetic_tree()
        node(handle,'ethernet@100000')['properties']['phy-handle']=fdt._cells(8)
        node(handle,'ethernet-phy@1')['properties']['phandle']=fdt._cells(8)
        arrays='\n'.join('static const unsigned char mdio_fdt_'+name+'[]={'+','.join(str(x) for x in fdt._encode_fdt(tree))+'};'
            for name,tree in (('mode',mode),('handle',handle)))
        setup=main_source().split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main='int main(){for(unsigned kind=0;kind<3;kind++){'+r'''
 memset(bridge,0,sizeof bridge);memset(resets,0,sizeof resets);memset(rescal,0,sizeof rescal);
 link_released=false;link_released_at=0;map_created=map_revoked=map_call=0;initialize_endpoint();mdio_busy=0;
'''+setup+r'''
 if(kind==0)s.firmwareFDT=nullptr;
 if(kind==1){firmware.bytes=mdio_fdt_mode;firmware.length=sizeof mdio_fdt_mode;}
 if(kind==2){firmware.bytes=mdio_fdt_handle;firmware.length=sizeof mdio_fdt_handle;}
 bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);before=out;
 assert(!s.runBoundedRP1Trial(&out)&&s.capabilitySession.state==RPI5_GEM_CAP_COMPLETE&&capability_reads==16);
 assert(!memcmp(&out,&before,sizeof out)&&s.mdioSession.state==RPI5_GEM_MDIO_UNUSED&&!mdio_reads&&!mdio_writes);
 assert(s.gemSession.stage==RPI5_GEM_QUARANTINED&&!map_revoked&&endpoint_reads==17);
 }puts("GEM_MDIO_ACTUAL_FDT_PASS CASES=3 NO_MANAGEMENT_IO=1");return 0;}'''
        output=run(main,lambda text:profile.util.once(text,'int main(){',arrays+'\nint main(){'))
        self.assertIn('GEM_MDIO_ACTUAL_FDT_PASS CASES=3',output)


if __name__=='__main__':unittest.main()
