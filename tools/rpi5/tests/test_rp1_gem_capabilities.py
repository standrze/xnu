# SPDX-License-Identifier: BSD-2-Clause
"""Real new pure reader and retained full transport; MMIO/VM are explicit doubles."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import rp1_gem_capabilities_profile as profile
from tools.rpi5.tests import test_rp1_gem_selected_clock as selected
base=selected.prior
full=base.full


def source(folder,main,mutation=None):
    text=selected.source(folder,main)
    for name,adapt in (('rp1_gem_identify.h',profile.gem_header),('rp1_gem_identify.c',profile.gem_core)):
        path=folder/name;path.write_text(adapt(path.read_text()))
    for suffix in ('c','h'):
        path=profile.ROOT/'loader/rpi5'/('rp1_gem_capabilities.'+suffix)
        (folder/path.name).write_bytes(path.read_bytes())
    text=profile.transport_header(text);text=profile.parent_transport(text);text=profile.gem_transport(text)
    text=re.sub(r'__asm__ volatile\("[^"\n]*" ::: "memory"\);','/* explicit host ordering double */',text)
    text=profile.util.once(text,'static unsigned endpoint_reads;', 'static unsigned endpoint_reads,capability_reads;')
    text=profile.util.once(text,'gem_registers[0xfc/4]=0x00070106;endpoint_reads=0;',r'''
    gem_registers[0xfc/4]=0x00070109;endpoint_reads=capability_reads=0;
    const unsigned cap_offsets[]={0x280,0x284,0x290,0x294,0x29c,0x2a4,0x2ac};
    const uint32_t cap_values[]={0x08800000,0x03f00000,0x100,0x0a8000aa,0x01020304,0x5400,0x04000000};
    for(unsigned i=0;i<7;i++)gem_registers[cap_offsets[i]/4]=cap_values[i];''')
    text=profile.util.once(text,
        'const uint32_t value[]={0x802,1,4,0x80000001,4,20,0,0x51000,0x800,1,2,0x800,1,2,0x80000800};',
        'const uint32_t value[]={2,1,4,0x80000001,4,20,0,0x51010,0x10000800,1,1,0x10000800,1,1,0x80000800};')
    start=text.index('int BCM2712PCIePHYTransport::capabilityRead(')
    before,body=text[:start],text[start:]
    before=base.physical_route_model(before)
    body=profile.util.once(body,'    uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);',r'''
    uint32_t value=*reinterpret_cast<volatile uint32_t *>(map->getVirtualAddress()+offset);
    uint64_t pci=0x100000u+offset;
    uint64_t base=(uint64_t)(bridge[0x20/4]&0xfff0)<<16;
    uint64_t limit=(bridge[0x20/4]&0xfff00000)|0xfffff;
    if(!(bridge[1]&2) || pci<base || pci+3>limit)value=UINT32_MAX;
    capability_reads++;printf("CAPREAD %08x %08x\n",offset,value);''')
    text=before+body
    return mutation(text) if mutation else text


def run(main,mutation=None):
    # Original full native runner, not COMPLETE-state owner shims. Append only
    # the new TU; use the same emitted headers for every C and C++ consumer.
    original=base.gem.prior.prior
    text=Path(original.__file__).read_text();start=text.index('def run(');end=text.index('\n\nclass AssignmentTransportTests',start)
    body=text[start:end]
    body=profile.util.once(body,'for include in (full.FROZEN,','for include in (folder,full.FROZEN,')
    body=profile.util.once(body,"'rp1_bars_assign','pcie_watchdog_lease'",
        "'rp1_bars_assign','rp1_decode_cycle','rp1_gem_identify','pcie_root_forward','rp1_gem_capabilities','pcie_watchdog_lease'")
    body=profile.util.once(body,"            if name=='pcie_owner_composition_secure':",
        "            if name in ('rp1_decode_cycle','rp1_gem_identify','pcie_root_forward','rp1_gem_capabilities'):path=folder/(name+'.c')\n"
        "            if name=='pcie_owner_composition_secure':")
    scope=dict(vars(original),source=source,profile=profile);exec(compile(body,__file__,'exec'),scope)
    return scope['run'](main,mutation)


class GEMCapabilitiesTests(unittest.TestCase):
    def test_preserved_primary_offsets_and_decoding_contract(self):
        refs=json.loads((profile.ROOT/'tools/rpi5/rp1_gem_capabilities_sources.json').read_text())
        for row in refs['sources']:
            raw=(profile.ROOT/row['path']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256']);self.assertEqual(len(raw),row['bytes'])
        header=(profile.ROOT/refs['sources'][0]['path']).read_text()
        for token,offset in (('MACB_MID',0xfc),('GEM_DCFG1',0x280),('GEM_DCFG2',0x284),('GEM_DCFG5',0x290),
            ('GEM_DCFG6',0x294),('GEM_DCFG8',0x29c),('GEM_DCFG10',0x2a4),('GEM_DCFG12',0x2ac)):
            match=re.search(r'^#define\s+'+token+r'\s+(0x[0-9a-fA-F]+)',header,re.M)
            self.assertIsNotNone(match);self.assertEqual(int(match[1],16),offset)
        for field,offset,width in (('IRQCOR',23,1),('DBWDEF',25,3),('NO_PCS',0,1),('RX_PKT_BUFF',20,1),
            ('TX_PKT_BUFF',21,1),('RX_PBUF_ADDR',22,4),('TSU',8,1),('PBUF_LSO',27,1),('PBUF_CUTTHRU',25,1),
            ('DAW64',23,1),('T1SCR',24,8),('T2SCR',16,8),('SCR2ETH',8,8),('SCR2CMP',0,8),
            ('TXBD_RDBUFF',12,4),('RXBD_RDBUFF',8,4),('HIGH_SPEED',26,1)):
            self.assertRegex(header,rf'#define\s+GEM_{field}_OFFSET\s+{offset}\b')
            self.assertRegex(header,rf'#define\s+GEM_{field}_SIZE\s+{width}\b')
        driver=(profile.ROOT/refs['sources'][1]['path']).read_text()
        self.assertIn('*queue_mask |= readl_relaxed(mem + GEM_DCFG6) & 0xff;',driver)
        self.assertIn('bit 0 is never set but queue 0 always exists',driver)
        self.assertIn('if (GEM_BFEXT(IRQCOR, dcfg) == 0)',driver)
        self.assertIn('MACB_CAPS_ISR_CLEAR_ON_WRITE',driver)

    def test_actual_reader_decode_faults_and_a76(self):
        with tempfile.TemporaryDirectory(prefix='gem-capabilities-pure-') as name:
            folder=Path(name)/'overlay';profile.emit(folder);exe=folder/'test'
            result=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                '-I',str(folder),'-I',str(profile.ROOT/'loader/rpi5'),str(Path(__file__).with_name('rp1_gem_capabilities_host.c')),
                str(folder/'rp1_gem_capabilities.c'),str(folder/'rp1_gem_identify.c'),'-o',str(exe)],text=True,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([exe],text=True,capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr);print(result.stdout,end='')
            self.assertIn('READS=16 OWNER_CHECKS=34 FAULT_CASES=278',result.stdout)
            command=['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align','-mgeneral-regs-only',
                '-ffreestanding','-fno-builtin','-fno-stack-protector','-O2','-Wall','-Wextra','-Werror','-I',str(folder),'-I',str(profile.ROOT/'loader/rpi5')]
            for name in ('rp1_gem_capabilities','rp1_gem_identify'):
                result=subprocess.run([*command,'-c',str(folder/(name+'.c')),'-o',str(folder/(name+'.o'))],text=True,capture_output=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stderr)

    def test_actual_full_owner_clock_bracket_budget_and_restore(self):
        main=full.MAIN.replace(' bcm2712_rp1_observation out={};',
            ' bridge[1]=0xa5a50000;bridge[0x20/4]=0x0000fff0;\n bcm2712_rp1_observation out={};')
        main=main.replace(' return 0;',r'''
    assert(ok && s.capabilitySession.state==RPI5_GEM_CAP_COMPLETE && s.gemSession.stage==RPI5_GEM_COMPLETE);
    assert(capability_reads==16 && endpoint_reads==32 && out.capabilities.reads==16 && out.capabilities.id==7);
    assert(out.capabilities.bus_width_bits==128 && out.capabilities.queue_mask==0xab);
    assert(s.rootForward.state==RPI5_ROOT_FORWARD_COMPLETE && s.rootForward.reads==79 && s.rootForward.writes==4);
    assert(s.decodeCycle.state==RPI5_RP1_DECODE_COMPLETE && s.assignment.state==RPI5_RP1_ASSIGN_RESTORED);
    assert(map_created==2 && map_revoked==2 && bridge[1]==0xa5a50000 && bridge[0x20/4]==0x0000fff0);
    assert((bridge[0x8004/4]&0xffff)==0 && bridge[0x8010/4]==0xffffc000 && bridge[0x8014/4]==0xffc00000 && bridge[0x8018/4]==0xffff0000);
    unsigned guards=0;for(unsigned n:s.guards)guards+=n;
    assert(t.pm_checks==12+8*guards && t.fw_sequence==1+2*guards && t.pm_checks<65536);
    printf("GEM_CAP_RUNTIME_PASS PM=%u FW=%u GUARDS=%u IDENTITY_READS=32 CAPABILITY_READS=16 NO_HARDWARE=1\n",t.pm_checks,t.fw_sequence,guards);
    return 0;''')
        output=run(main);print(output,end='')
        rows=[line for line in output.splitlines() if line.startswith(('GEMREAD ','CAPREAD '))]
        self.assertEqual(len(rows),48)
        self.assertEqual([line.split()[0] for line in rows],['GEMREAD']*17+['CAPREAD']*16+['GEMREAD']*15)
        offsets=[0xfc,0x280,0x284,0x290,0x294,0x29c,0x2a4,0x2ac]*2
        self.assertEqual([int(row.split()[1],16) for row in rows if row.startswith('CAPREAD ')],offsets)
        self.assertIn('GEM_CAP_RUNTIME_PASS PM=63628 FW=15905 GUARDS=7952',output)

    def test_real_owner_failures_before_and_after_each_selected_read(self):
        setup=full.MAIN.split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main='''int main(){unsigned cases=0;const unsigned targets[]={1,8,16};
 for(unsigned fault=1;fault<=12;fault++){for(unsigned side=0;side<2;side++){for(unsigned target:targets){
 memset(bridge,0,sizeof bridge);memset(resets,0,sizeof resets);memset(rescal,0,sizeof rescal);
 link_released=false;link_released_at=0;map_created=map_revoked=map_call=0;initialize_endpoint();wrong_thread=false;
'''+setup+r'''
 bridge[1]=0xa5a50000;bridge[0x20/4]=0x0000fff0;
 cap_fault=fault;cap_side=side;cap_target=target;cap_hit=false;
 bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);before=out;
 assert(!s.runBoundedRP1Trial(&out)&&cap_hit&&s.phase==BCM2712_PHY_FAILED);
 assert(s.capabilitySession.state==RPI5_GEM_CAP_QUARANTINED&&s.gemSession.stage==RPI5_GEM_QUARANTINED);
 assert(s.decodeCycle.state==RPI5_RP1_DECODE_QUARANTINED&&!memcmp(&out,&before,sizeof out));
 assert(s.assignment.state==RPI5_RP1_ASSIGN_ASSIGNED&&!map_revoked&&(bridge[0x8004/4]&0xffff)==2);
 assert(capability_reads==target-(side?0:1)&&endpoint_reads==17);
 unsigned stopped=smc_calls,reads=capability_reads;
 assert(!s.runBoundedRP1Trial(&out)&&smc_calls==stopped&&capability_reads==reads);cases++;
 }}}printf("GEM_CAP_REAL_FAULTS_PASS CASES=%u NO_CLEANUP=1\n",cases);return 0;}'''
        def mutation(text):
            text=profile.util.once(text,'static thread_t current_thread(){return &thread_identity;}',
                'static bool wrong_thread,cap_hit;static unsigned cap_fault,cap_side,cap_target;\n'
                'static thread_t current_thread(){return wrong_thread?nullptr:&thread_identity;}')
            begin=text.index('int BCM2712PCIePHYTransport::capabilityRead(');before,body=text[:begin],text[begin:]
            changes=r'''
    if(!cap_hit && cap_side==SIDE && cap_target==TARGET){cap_hit=true;switch(cap_fault){
      case 1:wrong_thread=true;break;case 2:self->setPhase(BCM2712_PHY_CLOCK_FINISHING);break;
      case 3:self->fwClaimed=false;break;case 4:self->irqClaimed=false;break;
      case 5:self->checkingLifecycle=true;break;case 6:self->providerOpened=false;break;
      case 7:rpi5_pcie_wdog_lease.checks=65536;break;case 8:rpi5_pcie_fw_session.sequence=65536;break;
      case 9:rpi5_pcie_irq_session.state=RPI5_PCIE_IRQ_QUARANTINED;break;
      case 10:self->deviceBacking[0]=nullptr;break;case 11:self->deviceMaps[0]->virt=0;break;
      case 12:self->decodeCycle.state=RPI5_RP1_DECODE_UNMAPPING;break;}}
'''
            body=profile.util.once(body,'    if(!self || !out ||',changes.replace('SIDE','0').replace('TARGET','capability_reads+1')+'    if(!self || !out ||')
            body=profile.util.once(body,'    if(!self->guard() || capabilitySource',changes.replace('SIDE','1').replace('TARGET','capability_reads')+'    if(!self->guard() || capabilitySource')
            return before+body
        output=run(main,mutation);self.assertIn('GEM_CAP_REAL_FAULTS_PASS CASES=72',output);print(output.splitlines()[-1])

    def test_post_clock_failure_never_commits_staged_capabilities(self):
        setup=full.MAIN.split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main='int main(){'+setup+r'''
 bridge[1]=0xa5a50000;bridge[0x20/4]=0x0000fff0;
 bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);before=out;
 assert(!s.runBoundedRP1Trial(&out)&&s.phase==BCM2712_PHY_FAILED);
 assert(s.capabilitySession.state==RPI5_GEM_CAP_COMPLETE&&capability_reads==16);
 assert(s.gemSession.stage==RPI5_GEM_QUARANTINED&&endpoint_reads==32&&!memcmp(&out,&before,sizeof out));
 assert(s.decodeCycle.state==RPI5_RP1_DECODE_QUARANTINED&&!map_revoked);
 printf("GEM_CAP_POST_CLOCK_FAIL_PASS NO_COMMIT=1 NO_CLEANUP=1\n");return 0;}'''
        def mutation(text):
            return profile.util.once(text,'    *out=value;return 0;\n}\nint BCM2712PCIePHYTransport::gemCapabilities',
                '    if(capability_reads==16)clock_registers[0x14/4]=0;\n'
                '    *out=value;return 0;\n}\nint BCM2712PCIePHYTransport::gemCapabilities')
        output=run(main,mutation);self.assertIn('GEM_CAP_POST_CLOCK_FAIL_PASS NO_COMMIT=1',output)

    def test_distinct_overlay_exact_owner_sources_unchanged(self):
        with tempfile.TemporaryDirectory(prefix='gem-cap-overlay-') as name:
            folder=Path(name)/'overlay';profile.emit(folder)
            changed={'rp1_gem_identify.h','rp1_gem_identify.c','BCM2712PCIePHYTransport.h',
                'BCM2712RP1GEMIdentifyTransport.inc','BCM2712RP1ConfigTransport.inc'}
            for old in profile.FROZEN.iterdir():
                if old.is_file() and old.name not in changed:self.assertEqual(old.read_bytes(),(folder/old.name).read_bytes())
            adapter=(folder/'BCM2712RP1GEMIdentifyTransport.inc').read_text()
            self.assertIn('!self->guard() || capabilitySource',adapter)
            self.assertNotIn('write',profile.ADAPTER.lower())
            core=(folder/'rp1_gem_identify.c').read_text()
            self.assertLess(core.index('s->io.capabilities(s->io.context,s)'),core.index('s->stage=RPI5_GEM_CLOCK_AFTER'))
            for n in ('rpi5_pcie_watchdog_owner.inc','rpi5_pcie_fw_owner.inc','rpi5_pcie_irq_owner.inc'):
                self.assertEqual((folder/n).read_bytes(),(profile.FROZEN/n).read_bytes())

if __name__=='__main__':unittest.main()
