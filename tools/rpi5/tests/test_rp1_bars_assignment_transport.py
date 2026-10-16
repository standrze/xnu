# SPDX-License-Identifier: BSD-2-Clause
"""Complete runtime/accounting through new adapter under explicit native doubles."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import rp1_bars_assignment_profile as profile
from tools.rpi5.tests import test_pcie_full_owner_accounting as full
from tools.rpi5.tests import test_pcie_guard_composition as guards
from tools.rpi5.tests import test_pcie_bounded_log as encoder


def source(folder,main,mutation=None):
    text=full.source(folder,True,main)
    text=profile.header(text)
    text=profile.transport(text)
    adapter=re.sub(r'__asm__ volatile\("[^"\n]*" ::: "memory"\);','/* host ordering double */',profile.ADAPTER)
    text=profile.util.once(text,'int main(){',adapter+'\nint main(){')
    return mutation(text) if mutation else text


def run(main,mutation=None):
    with tempfile.TemporaryDirectory(prefix='rp1-assignment-runtime-') as directory:
        folder=Path(directory);cpp=folder/'host.cpp';cpp.write_text(source(folder,main,mutation))
        flags=['-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined']
        for include in (full.FROZEN,profile.ROOT,profile.ROOT/'iokit/Kernel',profile.ROOT/'loader/rpi5',
            profile.ROOT/'tools/rpi5/tests',profile.ROOT/'tools/rpi5/tests/pcie_irq_stubs',
            profile.ROOT/'tools/rpi5/tests/fw_verifier_stubs'):
            flags+=['-I',str(include)]
        names=('pcie_reset','pcie_rescal','pcie_mdio','pcie_serdes','pcie_ubus','pcie_unused','pcie_qos','pcie_clock',
            'pcie_windows','pcie_rc','pcie_link','pcie_config','rp1_config_snapshot_checked','pcie_released_windows',
            'rp1_bars_probe','rp1_bars_plan','rp1_bars_assign','pcie_watchdog_lease','pcie_irq_mask',
            'pcie_fw_client','pcie_owner_composition_secure')
        objects=[]
        for name in names:
            path=profile.ROOT/'loader/rpi5'/(name+'.c')
            if name in ('pcie_ubus','pcie_qos','pcie_clock'):path=full.AXI/(name+'.c')
            if name in ('pcie_rc','pcie_link','rp1_config_snapshot_checked'):path=full.FROZEN/(name+'.c')
            if name=='pcie_owner_composition_secure':path=profile.ROOT/'tools/rpi5/tests'/(name+'.c')
            obj=folder/(name+'.o');objects.append(obj)
            result=subprocess.run(['xcrun','clang','-std=c11',*flags,'-c',str(path),'-o',str(obj)],capture_output=True,text=True)
            if result.returncode:raise AssertionError(result.stderr)
        exe=folder/'host'
        result=subprocess.run(['xcrun','clang++','-std=gnu++17',*flags,str(cpp),*map(str,objects),'-o',str(exe)],capture_output=True,text=True)
        if result.returncode:raise AssertionError(result.stderr)
        result=subprocess.run([exe],capture_output=True,text=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)
        return result.stdout


class AssignmentTransportTests(unittest.TestCase):
    def test_actual_full_runtime_unchanged_owner_limits_exact_restore(self):
        main=full.MAIN.replace(' return 0;',r'''
 assert(ok&&s.diagGuard==0&&s.diagAssignCall==6&&!s.assignmentActive);
 assert(s.assignment.state==RPI5_RP1_ASSIGN_RESTORED&&s.assignment.transactions==58&&s.assignment.writes_started==6);
 assert(out.assigned.bar[0]==0x410000&&out.assigned.bar[1]==0&&out.assigned.bar[2]==0x400000);
 assert(out.restored.bar[0]==0xffffc000&&out.restored.bar[1]==0xffc00000&&out.restored.bar[2]==0xffff0000);
 assert(bridge[0x8010/4]==0xffffc000&&bridge[0x8014/4]==0xffc00000&&bridge[0x8018/4]==0xffff0000);
 assert((bridge[0x8004/4]&0xffff)==0&&out.assigned.command==0&&out.restored.command==0);
 assert(out.mapping.bar1_cpu.start==0x1f00000000&&out.mapping.bar1_cpu.end==0x1f00400000);
 unsigned guards=0;for(unsigned n:s.guards)guards+=n;
 assert(t.pm_checks==12+8*guards&&t.fw_sequence==1+2*guards&&smc_calls==2+2*guards);
 assert(t.pm_checks<65536&&t.fw_sequence<65536&&t.pm_deadline-t.pm_start==12*t.fw_frequency);
 printf("ASSIGN_RUNTIME_PASS TRANSFERS=%u WRITES=%u PM=%u FW=%u NO_DECODE=1 NO_MAPPING=1 NO_HARDWARE=1\n",
 s.assignment.transactions,s.assignment.writes_started,t.pm_checks,t.fw_sequence);
 return 0;''')
        output=run(main);print(output,end='')
        self.assertIn('ASSIGN_RUNTIME_PASS TRANSFERS=58 WRITES=6 ',output)
        self.assertIn('FULL_ACCOUNTING OK=1 ',output)

    def test_instrumented_transport_only_bar_assignment_writes_after_old_prefix(self):
        def trace(text):
            needle='*reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE]+offset)=value;'
            self.assertEqual(text.count(needle),2)
            position=text.rindex(needle)
            text=text[:position]+text[position:].replace(needle,
                '*reinterpret_cast<volatile uint32_t *>(self->registers[BCM2712_PHY_BRIDGE] + offset)=value;'
                'record(\'w\',0,offset,4,value);',1)
            return guards.operation_trace(text)
        before=full.run(True,mutation=guards.operation_trace)
        after=run(full.MAIN,trace)
        old=[x for x in before.splitlines() if x.startswith('OP ')]
        new=[x for x in after.splitlines() if x.startswith('OP ')]
        self.assertEqual(old,new[:len(old)])
        endpoint=[x for x in new[len(old):] if re.fullmatch(r'OP w 0 00008[0-9a-f]{3} 4 [0-9a-f]{8}',x)]
        expected=[(0x8010,0x410000),(0x8014,0),(0x8018,0x400000),
            (0x8010,0xffffc000),(0x8014,0xffc00000),(0x8018,0xffff0000)]
        self.assertEqual(endpoint,[f'OP w 0 {offset:08x} 4 {value:08x}' for offset,value in expected])
        self.assertIn('FULL_ACCOUNTING OK=1 ',after)
        print(f'ASSIGNMENT_TRANSPORT_TRACE_PASS PREDECESSOR={len(old)} TOTAL={len(new)} EXACT_NEW_BAR_WRITES=6')

    def test_real_source_adapter_rejects_current_owner_changes_mid_assign_and_restore(self):
        setup=full.MAIN.split('int main(){',1)[1].split(' bcm2712_rp1_observation out={};',1)[0]
        main='''int main(){
 unsigned cases=0;
 for(unsigned fault=1;fault<=13;fault++)for(unsigned point=0;point<3;point++){
 memset(bridge,0,sizeof bridge);memset(resets,0,sizeof resets);memset(rescal,0,sizeof rescal);
 link_released=false;link_released_at=0;wrong_thread=false;
'''+setup+r'''
 source_fault=fault;source_point=point;source_hit=false;
 bcm2712_rp1_observation out,before;memset(&out,0xa5,sizeof out);before=out;
 assert(!s.runBoundedRP1Trial(&out)&&source_hit&&s.phase==BCM2712_PHY_FAILED);
 assert(!memcmp(&out,&before,sizeof out)&&s.assignment.state==RPI5_RP1_ASSIGN_QUARANTINED);
 assert(!s.assignment.pending_write&&!s.rp1Locked&&(bridge[0x8004/4]&0xffff)==0);
 const uint32_t originals[6]={0xffffc000,0xffc00000,0xffff0000,0,0,0};
 const uint32_t planned[6]={0x410000,0,0x400000,0,0,0};
 for(unsigned i=0;i<6;i++)assert(bridge[0x8010/4+i]==originals[i]||bridge[0x8010/4+i]==planned[i]);
 unsigned calls=smc_calls;
 assert(!s.runBoundedRP1Trial(&out)&&smc_calls==calls&&!memcmp(&out,&before,sizeof out));
 cases++;
 }
 printf("ACTUAL_ASSIGNMENT_SOURCE_FAILURES_PASS CASES=%u NO_CLEANUP_IO=1 NO_HARDWARE=1\n",cases);
 return 0;
}'''
        def fault_seam(text):
            text=profile.util.once(text,'static thread_t current_thread(){return &thread_identity;}',
                'static bool wrong_thread;static unsigned source_fault,source_point;static bool source_hit;\n'
                'static thread_t current_thread(){return wrong_thread?nullptr:&thread_identity;}')
            start=text.index('int BCM2712PCIePHYTransport::assignmentSource(')
            before,adapter=text[:start],text[start:]
            adapter=profile.util.once(adapter,'    if(!self || !self->onOwnerThread()',r'''
    bool target=self && ((source_point==0 && self->diagAssignCall==1) ||
        (source_point==1 && self->diagAssignCall==1 && self->assignment.pending_write && self->assignment.selected==1) ||
        (source_point==2 && self->diagAssignCall==4 && self->assignment.pending_write && self->assignment.selected==1));
    if(target&&!source_hit){
      source_hit=true;
      switch(source_fault){
      case 1:wrong_thread=true;break;
      case 2:self->setPhase(BCM2712_PHY_CLOCK_FINISHING);break;
      case 3:self->ownerProvider->opened=false;break;
      case 4:self->providerOpened=false;break;
      case 5:self->fwClaimed=false;break;
      case 6:self->irqClaimed=false;break;
      case 7:self->checkingLifecycle=true;break;
      case 8:phyOwner=nullptr;break;
      case 9:self->lifecyclePhase=BCM2712_CONTROLLER_HELD_RESET;break;
      case 10:config=nullptr;break;
      case 11:binding=nullptr;break;
      case 12:probe=nullptr;break;
      case 13:sizes=nullptr;break;
      }
    }
    if(!self || !self->onOwnerThread()''')
            return before+adapter
        output=run(main,fault_seam);print(output,end='')
        self.assertIn('ACTUAL_ASSIGNMENT_SOURCE_FAILURES_PASS CASES=39',output)

    def test_private_overlay_preserves_existing_frozen_inputs(self):
        with tempfile.TemporaryDirectory(prefix='rp1-assignment-overlay-') as directory:
            folder=Path(directory)/'overlay';outputs=profile.emit(folder)
            self.assertEqual(len(outputs),2)
            for name in ('BCM2712PCIeFWTransport.inc','rpi5_pcie_fw_owner.inc','rpi5_pcie_irq_owner.inc','rpi5_pcie_watchdog_owner.inc'):
                self.assertEqual((folder/name).read_bytes(),(profile.FROZEN/name).read_bytes())
            text=(folder/'BCM2712RP1AssignmentTransport.inc').read_text()
            for forbidden in ('pe_rpi5_','IODelay','clock_get','machine_'):
                self.assertNotIn(forbidden,text.split('int BCM2712PCIePHYTransport::assignmentAuthorize')[0])
            self.assertIn('self->getPhase()!=BCM2712_PHY_RP1_INSPECTING',text)
            self.assertIn('config!=&self->rp1Config',text)

    def test_all_four_passive_rows_fit_actual_apple_encoder(self):
        formats=re.findall(r'kprintf\("([^"\n]+)"',profile.diagnostic_calls())
        self.assertEqual(len(formats),4)
        lines=['int main(void){for(unsigned loc=4;loc<=8;loc+=4)for(unsigned sid=0;sid<2;sid++){','location_size=loc;subsystem=sid;']
        for fmt in formats:lines.append('assert(encode('+encoder.c_string(fmt)+','+encoder.values(fmt)+'));')
        lines+=['}assert(encoded_calls==16);printf("ASSIGN_LOG_PASS CALLS=%u MAX_BYTES=%zu\\n",encoded_calls,max_bytes);return 0;}']
        with tempfile.TemporaryDirectory(prefix='rp1-assignment-log-') as directory:
            folder=Path(directory);src=folder/'encoder.c';src.write_text(encoder.encoder_source()+'\n'.join(lines));exe=folder/'encoder'
            result=subprocess.run(['xcrun','clang','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(src),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([exe],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn('ASSIGN_LOG_PASS CALLS=16 MAX_BYTES=',result.stdout)
            self.assertLess(int(re.search(r'MAX_BYTES=(\d+)',result.stdout)[1]),100)


if __name__=='__main__':unittest.main()
