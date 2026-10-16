# SPDX-License-Identifier: BSD-2-Clause
"""Actual observer + whole controller/owner runtime with explicit VM/MMIO doubles."""
from pathlib import Path
import copy
import hashlib
import json
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import rp1_phy_gpio_observe_profile as profile
from tools.rpi5.tests import test_rp1_gem_capabilities as cap
from tools.rpi5.tests import test_pcie_fdt as fdt
full=cap.full

def fixture_tree():
    tree=fdt._synthetic_tree()
    def visit(n):
        if n['name']=='rp1':
            n['children'].append(fdt._node('gpio@d0000',{
                'compatible':b'raspberrypi,rp1-gpio\0','phandle':fdt._cells(8),'#gpio-cells':fdt._cells(2),
                'gpio-controller':b'','reg':fdt._cells(0xc0,0x400d0000,0,0xc000,0xc0,0x400e0000,0,0xc000,0xc0,0x400f0000,0,0xc000)}))
        if n['name']=='ethernet@100000':n['properties'].update({'phy-reset-gpios':fdt._cells(8,32,1),'phy-reset-duration':fdt._cells(5)})
        for c in n['children']:visit(c)
    visit(tree);return tree

def source(folder,main,mutation=None):
    text=cap.source(folder,main)
    for suffix in ('c','h'):
        path=profile.ROOT/'loader/rpi5'/('rp1_phy_gpio_observe.'+suffix);(folder/path.name).write_bytes(path.read_bytes())
    text=profile.header(text);text=profile.parent_transport(text);text=profile.gem_transport(text)
    text=re.sub(r'__asm__ volatile\("[^"\n]*" ::: "memory"\);','/* explicit host ordering double */',text)
    text=profile.util.once(text,'struct OSData{};',r'''struct OSData {
        const void *bytes;size_t length;
        const void *getBytesNoCopy()const{return bytes;}
        size_t getLength()const{return length;}
    };''')
    tree=fdt._encode_fdt(fixture_tree())
    text=profile.util.once(text,'int main(){','static const unsigned char gpio_fdt[]={'+','.join(map(str,tree))+'};\nint main(){')
    text=text.replace('mapped_devices[2]','mapped_devices[5]').replace('descriptors[2]','descriptors[5]').replace('assert(map_created<2)','assert(map_created<5)')
    text=profile.util.once(text,'static IOMemoryMap mapped_devices[5];',
        'alignas(16384) static uint32_t gpio_registers[3][0x4000/4];\nstatic unsigned gpio_reads;\nstatic IOMemoryMap mapped_devices[5];')
    text=profile.util.once(text,'(address==0x1f00018000&&bytes==0x14000)',
        '(address==0x1f00018000&&bytes==0x14000)||(bytes==0x4000&&(address==0x1f000d4000||address==0x1f000e4000||address==0x1f000f4000))')
    text=profile.util.once(text,'(begin==0x1f00018000&&end==0x1f0002c000)',
        '(begin==0x1f00018000&&end==0x1f0002c000)||(end-begin==0x4000&&(begin==0x1f000d4000||begin==0x1f000e4000||begin==0x1f000f4000))')
    text=profile.util.once(text,'m->virt=reinterpret_cast<uint64_t>(n?clock_registers:gem_registers);',
        'm->virt=reinterpret_cast<uint64_t>(n>=2?gpio_registers[n-2]:n?clock_registers:gem_registers);')
    start=text.index('int BCM2712PCIePHYTransport::phyGPIORead(');before,body=text[:start],text[start:]
    body=profile.util.once(body,'    *out=value;return 0;',
        '    gpio_reads++;printf("GPIO_READ %u %08x %08x\\n",i,offset,value);\n    *out=value;return 0;')
    return mutation(before+body) if mutation else before+body

def run(main,mutation=None):
    body=Path(cap.__file__).read_text();body=body[body.index('def run('):body.index('\n\nclass GEMCapabilitiesTests')]
    body=body.replace("'rp1_gem_capabilities','pcie_watchdog_lease'","'rp1_gem_capabilities','rp1_phy_gpio_observe','pcie_fdt','fdt','fdt_reg','pcie_watchdog_lease'")
    body=body.replace("'pcie_root_forward','rp1_gem_capabilities'):path", "'pcie_root_forward','rp1_gem_capabilities','rp1_phy_gpio_observe'):path")
    scope=dict(vars(cap),source=source,profile=profile);exec(compile(body,__file__,'exec'),scope)
    return scope['run'](main,mutation)

def main_source(extra=''):
    return full.MAIN.replace(' bcm2712_rp1_observation out={};',r'''
    OSData firmware={gpio_fdt,sizeof gpio_fdt};s.firmwareFDT=&firmware;
    assert(!rpi5_fdt_pcie_rp1(gpio_fdt,sizeof gpio_fdt,&s.binding));
    bridge[1]=0xa5a50000;bridge[0x20/4]=0x0000fff0;
    gpio_reads=0;memset(gpio_registers,0,sizeof gpio_registers);
    gpio_registers[0][0x20/4]=0x32200;gpio_registers[0][0x24/4]=5;
    gpio_registers[1][0]=gpio_registers[1][1]=gpio_registers[1][2]=16;
    gpio_registers[2][0x14/4]=0x56;
'''+extra+'\n bcm2712_rp1_observation out={};')

class PHYGPIOObserveTests(unittest.TestCase):
    def test_preserved_source_contract_and_frozen_predecessor(self):
        refs=json.loads((profile.ROOT/'tools/rpi5/rp1_phy_gpio_sources.json').read_text())
        for item in refs['sources']:
            raw=(profile.ROOT/item['path']).read_bytes()
            self.assertEqual(len(raw),item['bytes']);self.assertEqual(hashlib.sha256(raw).hexdigest(),item['sha256'])
        board=(profile.ROOT/refs['sources'][0]['path']).read_text()
        self.assertIn('phy-reset-gpios = <&rp1_gpio 32 GPIO_ACTIVE_LOW>;',board)
        driver=(profile.ROOT/refs['sources'][1]['path']).read_text()
        self.assertIn('{ 28,  6, 0x4000, 0x411c, 0x4124, 0x4000, 0x4004 }',driver)
        self.assertIn('pin->offset = j;',driver);self.assertIn('j * sizeof(u32) * 2',driver)
        self.assertIn('j * sizeof(u32);',driver)
        with tempfile.TemporaryDirectory(prefix='gpio-owner-unchanged-') as name:
            folder=Path(name)/'overlay';profile.emit(folder)
            changed={'BCM2712PCIePHYTransport.h','BCM2712RP1GEMIdentifyTransport.inc','BCM2712RP1ConfigTransport.inc'}
            for old in profile.FROZEN.iterdir():
                if old.is_file() and old.name not in changed:self.assertEqual(old.read_bytes(),(folder/old.name).read_bytes())
        self.assertNotIn('volatile uint32_t *>(map->getVirtualAddress()+offset)=',profile.ADAPTER)

    def test_full_owner_observer_restores_all_five_maps_no_gpio_writes(self):
        main=main_source().replace(' return 0;',r'''
    if(!ok)fprintf(stderr,"GPIO diagnostic state=%u error=%d reads=%u maps=%u/%u cap=%u gem=%u pm=%u\n",s.phyGPIO.state,s.phyGPIO.error,s.phyGPIO.reads,map_created,map_revoked,s.capabilitySession.state,s.gemSession.stage,t.pm_checks);
    assert(ok&&s.phyGPIO.state==RPI5_PHY_GPIO_COMPLETE&&s.phyGPIO.reads==12);
    assert(s.phyGPIO.mapped==7&&s.phyGPIO.unmapped==7&&map_created==5&&map_revoked==5&&gpio_reads==12);
    const uint32_t wanted[]={0x32200,5,16,16,16,0x56};
    for(unsigned p=0;p<2;p++)for(unsigned i=0;i<6;i++)assert(out.phy_gpio.raw[p][i]==wanted[i]);
    assert(s.rootForward.state==RPI5_ROOT_FORWARD_COMPLETE&&s.decodeCycle.state==RPI5_RP1_DECODE_COMPLETE);
    assert(s.assignment.state==RPI5_RP1_ASSIGN_RESTORED&&bridge[1]==0xa5a50000&&bridge[0x20/4]==0xfff0);
    unsigned guards=0;for(unsigned n:s.guards)guards+=n;
    assert(t.pm_checks==12+8*guards&&t.pm_checks<65536);
    printf("GPIO_OBSERVER_FULL_PASS PM=%u FW=%u GUARDS=%u READS=%u MAPS=%u UNMAPS=%u NO_HARDWARE=1\n",
       t.pm_checks,t.fw_sequence,guards,gpio_reads,map_created,map_revoked);return 0;''')
        output=run(main);print('\n'.join(output.splitlines()[-14:]));self.assertIn('GPIO_OBSERVER_FULL_PASS',output)
        self.assertEqual(len([x for x in output.splitlines() if x.startswith('GPIO_READ ')]),12)

    def test_actual_mapping_faults_never_force_cleanup(self):
        setup=main_source().split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main=r'''int main(){unsigned cases=0;
        for(unsigned fault=1;fault<=14;fault++){for(unsigned target=2;target<5;target++){
        memset(bridge,0,sizeof bridge);memset(resets,0,sizeof resets);memset(rescal,0,sizeof rescal);
        link_released=false;link_released_at=0;map_created=map_revoked=map_call=0;initialize_endpoint();
'''+setup+r'''
        map_fault=fault;map_target=target;
        bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);before=out;
        assert(!s.runBoundedRP1Trial(&out)&&!memcmp(&out,&before,sizeof out));
        assert(s.phyGPIO.state==RPI5_PHY_GPIO_QUARANTINED&&s.phase==BCM2712_PHY_FAILED);
        assert(s.decodeCycle.state==RPI5_RP1_DECODE_QUARANTINED&&s.assignment.state==RPI5_RP1_ASSIGN_ASSIGNED);
        unsigned r=map_revoked,c=map_created,reads=gpio_reads,smc=smc_calls;
        assert(!s.runBoundedRP1Trial(&out)&&map_revoked==r&&map_created==c&&gpio_reads==reads&&smc_calls==smc);
        cases++;}}printf("GPIO_MAP_FAULTS_PASS CASES=%u\n",cases);return 0;}'''
        output=run(main);self.assertIn('GPIO_MAP_FAULTS_PASS CASES=42',output);print(output.splitlines()[-1])

    def test_real_read_owner_mutation_and_reentrancy_fail_closed(self):
        setup=main_source().split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main=r'''int main(){unsigned cases=0;
        for(unsigned fault=1;fault<=14;fault++){for(unsigned side=0;side<2;side++){for(unsigned target=1;target<=12;target++){
        memset(bridge,0,sizeof bridge);memset(resets,0,sizeof resets);memset(rescal,0,sizeof rescal);
        link_released=false;link_released_at=0;map_created=map_revoked=map_call=0;initialize_endpoint();wrong_thread=false;gpio_hit=false;
'''+setup+r'''
        gpio_fault=fault;gpio_side=side;gpio_target=target;
        bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);before=out;
        assert(!s.runBoundedRP1Trial(&out)&&gpio_hit&&!memcmp(&out,&before,sizeof out));
        assert(s.phyGPIO.state==RPI5_PHY_GPIO_QUARANTINED&&!map_revoked&&s.phase==BCM2712_PHY_FAILED);
        assert(s.decodeCycle.state==RPI5_RP1_DECODE_QUARANTINED&&s.assignment.state==RPI5_RP1_ASSIGN_ASSIGNED);
        if(gpio_reads!=target-1)fprintf(stderr,"FAULT %u SIDE %u TARGET %u READS %u\n",fault,side,target,gpio_reads);
        assert(gpio_reads==target-1);
        unsigned smc=smc_calls;assert(!s.runBoundedRP1Trial(&out)&&smc_calls==smc&&gpio_reads==target-1);cases++;
        }}}printf("GPIO_OWNER_FAULTS_PASS CASES=%u NO_COMPENSATION=1\n",cases);return 0;}'''
        def mutate(text):
            text=profile.util.once(text,'static thread_t current_thread(){return &thread_identity;}',
                'static bool wrong_thread,gpio_hit;static unsigned gpio_fault,gpio_side,gpio_target;\n'
                'static thread_t current_thread(){return wrong_thread?nullptr:&thread_identity;}')
            begin=text.index('int BCM2712PCIePHYTransport::phyGPIORead(');before,body=text[:begin],text[begin:]
            fault=r'''
            if(!gpio_hit&&gpio_side==SIDE&&gpio_reads+1==gpio_target){gpio_hit=true;switch(gpio_fault){
            case 1:wrong_thread=true;break;case 2:self->setPhase(BCM2712_PHY_CLOCK_FINISHING);break;
            case 3:self->fwClaimed=false;break;case 4:self->irqClaimed=false;break;
            case 5:self->checkingLifecycle=true;break;case 6:self->providerOpened=false;break;
            case 7:rpi5_pcie_wdog_lease.checks=65536;break;case 8:rpi5_pcie_fw_session.sequence=65536;break;
            case 9:self->phyGPIOMaps[i]->virt=0;break;case 10:self->phyGPIOBacking[i]=nullptr;break;
            case 11:self->firmwareFDT->bytes=nullptr;break;case 12:self->capabilitySession.state=RPI5_GEM_CAP_QUARANTINED;break;
            case 13:self->phyGPIO.page[i].start+=0x4000;break;
            case 14:assert(rpi5_phy_gpio_run(&self->phyGPIO,&self->capabilitySession,&self->phyGPIOBinding,&self->phyGPIO.io,&self->phyGPIOObserved));break;
            }}
            '''
            body=profile.util.once(body,'    if(!self || !out ||',fault.replace('SIDE','0')+'    if(!self || !out ||')
            body=profile.util.once(body,'    if(!self->guard() || phyGPIOSource',fault.replace('SIDE','1')+'    if(!self->guard() || phyGPIOSource')
            return before+body
        output=run(main,mutate);self.assertIn('GPIO_OWNER_FAULTS_PASS CASES=336',output);print(output.splitlines()[-1])

    def test_fdt_exact_reset_graph_and_atomic_negatives(self):
        trees=[fixture_tree()]
        def node(t,name):
            if t['name']==name:return t
            for c in t['children']:
                got=node(c,name)
                if got:return got
        variants=[('ethernet@100000','phy-reset-gpios',fdt._cells(8,31,1)),
            ('ethernet@100000','phy-reset-gpios',fdt._cells(8,32,0)),
            ('ethernet@100000','phy-reset-gpios',fdt._cells(7,32,1)),
            ('ethernet@100000','phy-reset-duration',fdt._cells(10)),
            ('gpio@d0000','status',b'disabled\0'),('gpio@d0000','#gpio-cells',fdt._cells(3)),
            ('gpio@d0000','compatible',b'other\0'),('gpio@d0000','reg',fdt._cells(0xc0,0x400d0000,0,0xc000)),
            ('ethernet@100000','pinctrl-0',fdt._cells(8))]
        for target,key,value in variants:
            t=copy.deepcopy(trees[0]);node(t,target)['properties'][key]=value;trees.append(t)
        with tempfile.TemporaryDirectory(prefix='phy-gpio-fdt-') as name:
            folder=Path(name)/'overlay';profile.emit(folder)
            raw='\n'.join(f'static const unsigned char tree{i}[]={{'+','.join(map(str,fdt._encode_fdt(t)))+'};' for i,t in enumerate(trees))
            source_c='#include <assert.h>\n#include <string.h>\n#include "rp1_phy_gpio_observe.h"\n'+raw+r'''
            int main(void){struct rpi5_phy_gpio_binding out,before;
            assert(!rpi5_phy_gpio_fdt(tree0,sizeof tree0,&out));assert(out.pin==32&&out.bank_offset[2]==0xf4000);
            memset(&out,0xa5,sizeof out);before=out;
            '''+'\n'.join(f'assert(rpi5_phy_gpio_fdt(tree{i},sizeof tree{i},&out));assert(!memcmp(&out,&before,sizeof out));' for i in range(1,len(trees)))+'return 0;}'
            (folder/'test.c').write_text(source_c)
            flags=['-std=c11','-Wall','-Wextra','-Werror','-I',str(folder),'-I',str(profile.ROOT/'loader/rpi5')]
            files=[folder/'test.c',folder/'rp1_phy_gpio_observe.c',folder/'rp1_gem_identify.c',
                *[profile.ROOT/'loader/rpi5'/(n+'.c') for n in ('pcie_fdt','fdt','fdt_reg')]]
            exe=folder/'test';r=subprocess.run(['xcrun','clang',*flags,'-fsanitize=address,undefined',*[str(x) for x in files],'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr);r=subprocess.run([exe],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run(['xcrun','clang',*flags,'--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin','-O2','-c',str(folder/'rp1_phy_gpio_observe.c'),'-o',str(folder/'core.o')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)

if __name__=='__main__':unittest.main()
