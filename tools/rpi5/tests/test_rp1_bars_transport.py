# SPDX-License-Identifier: BSD-2-Clause
import subprocess
import tempfile
from pathlib import Path
import unittest
from tools.rpi5 import build_rp1_bars_kernel as builder

ROOT=Path(__file__).resolve().parents[3]


class RP1BarsTransportTests(unittest.TestCase):
    def test_actual_integrated_all_bar_caller(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            prefix=Path(__file__).with_name('pcie_id_provider_host.cpp').read_text().split('int main()')[0]
            replace=builder.previous.previous.base.replace_once
            prefix=replace(prefix,'#include "loader/rpi5/pcie_released_windows.h"',
                '#include "loader/rpi5/pcie_released_windows.h"\n#include "loader/rpi5/rp1_bars_plan.h"')
            prefix=replace(prefix,'    struct rpi5_rp1_config_snapshot endpoint;',
                '    struct rpi5_rp1_config_snapshot endpoint;\n'
                '    struct rpi5_rp1_bars_size bars;\n    struct rpi5_rp1_bars_plan barsPlan;')
            prefix=replace(prefix,'    static int rp1Acquire(void *);',
                '    struct rpi5_rp1_bars_probe barsProbe={};\n'
                '    static int rp1BarsAuthorize(void *,const struct rpi5_pcie_config_request *);\n'
                '    static int rp1BarsWrite(void *,uint32_t,uint32_t,uint32_t);\n'
                '    static int rp1Acquire(void *);')
            prefix=replace(prefix,'        return result?(fail(),false):true;',
                '        /* Explicit RAM-backed device double: BAR address bits are hardwired masks. */\n'
                '        const uint32_t masks[6]={0xffffc000,0xffc00000,0xffff0000,0,0,0};\n'
                '        for(unsigned i=0;i<6;i++)if(memory[0x8010/4+i]==UINT32_MAX)memory[0x8010/4+i]=masks[i];\n'
                '        return result?(fail(),false):true;')
            prefix=replace(prefix,'#include "iokit/Kernel/BCM2712RP1ConfigTransport.inc"',
                '#include "actual-bars-caller.inc"\n#include "iokit/Kernel/BCM2712RP1BarsTransport.inc"')
            (directory/'actual-bars-caller.inc').write_text(builder.transport_source(
                (ROOT/'iokit/Kernel/BCM2712RP1ConfigTransport.inc').read_text()))
            body=(ROOT/'iokit/Kernel/BCM2712PCIeIDTrial.inc').read_text()
            (directory/'actual-id-provider.inc').write_text(body.split(
                '/* Distinct IOStartIOKit caller invokes this BEFORE any driver matching')[0])
            main=r'''
static void prepared(BCM2712PCIePHYTransport &s){
 s.prepare();s.memory[0x8010/4]=0x410000;s.memory[0x8018/4]=0x400000;
 s.binding.outbound_count=1;
 s.binding.outbound[0]={0x02000000,0,UINT64_C(0x1f00000000),0xfffffffc};
 s.binding.rp1_aperture_size=0x410000;s.binding.gem_bar_offset=0x100000;s.binding.gem_size=0x4000;
 s.binding.clock_bar_offset=0x18000;s.binding.clock_size=0x10038;
}
int main(){
 unsigned count;
 {BCM2712PCIePHYTransport s;prepared(s);bcm2712_rp1_observation out={};
  assert(s.runBoundedRP1Trial(&out));count=s.checks;
  assert(out.endpoint.header[0]==0x00011de4&&out.bars.present==7&&out.bars.transactions==49);
  assert(out.bars.bar[0].size==0x4000&&out.bars.bar[1].size==0x400000&&out.bars.bar[2].size==0x10000);
  assert(out.barsPlan.pci_base[0]==0x410000&&out.barsPlan.pci_base[1]==0&&out.barsPlan.pci_base[2]==0x400000);
  assert(s.barsProbe.writes_started==12&&s.barsProbe.state==RPI5_RP1_BARS_COMPLETE);
  assert(s.memory[0x8004/4]==0x10&&s.memory[0x8010/4]==0x410000&&s.memory[0x8018/4]==0x400000);
  assert(s.memory[0x8014/4]==0&&s.memory[0x801c/4]==0&&s.memory[0x8020/4]==0&&s.memory[0x8024/4]==0);
  assert(s.phase==BCM2712_PHY_COMPLETE&&!s.rp1Locked);
 }
 for(unsigned fault=1;fault<=count;fault++){
  BCM2712PCIePHYTransport s;prepared(s);s.failAt=fault;
  bcm2712_rp1_observation out;memset(&out,0xa5,sizeof out);auto before=out;
  assert(!s.runBoundedRP1Trial(&out)&&s.phase==BCM2712_PHY_FAILED&&s.checks==fault);
  assert(!memcmp(&out,&before,sizeof out)&&!s.rp1Locked);
  assert(!s.runBoundedRP1Trial(&out)&&s.checks==fault);
  assert(s.memory[0x8004/4]==0x10); // I/O, MEM and BME never enabled.
  if(s.barsProbe.state!=RPI5_RP1_BARS_EMPTY)assert(s.rp1Config.state==RPI5_PCIE_CONFIG_QUARANTINED);
 }
 {BCM2712PCIePHYTransport s;prepared(s);s.binding.gem_bar_offset=UINT64_MAX;
  bcm2712_rp1_observation out;memset(&out,0xa5,sizeof out);auto before=out;
  assert(!s.runBoundedRP1Trial(&out)&&!memcmp(&out,&before,sizeof out));
  assert(s.barsProbe.state==RPI5_RP1_BARS_COMPLETE&&s.rp1Config.state==RPI5_PCIE_CONFIG_QUARANTINED);
  assert(s.phase==BCM2712_PHY_FAILED&&s.memory[0x8004/4]==0x10);
 }
 printf("RP1_BARS_CALLER_PASS GUARD_FAILURES=%u ACTUAL_CORE_AND_CALLER=1 NO_HARDWARE=1\n",count);
}
'''
            source=directory/'caller.cpp';source.write_text(prefix+main);objects=[]
            for name in ('pcie_config','rp1_config_snapshot_checked','pcie_released_windows','rp1_bars_probe','rp1_bars_plan'):
                obj=directory/(name+'.o')
                result=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined','-c',str(ROOT/'loader/rpi5'/(name+'.c')),'-o',str(obj)],
                    capture_output=True,text=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stderr);objects.append(obj)
            program=directory/'caller'
            result=subprocess.run(['xcrun','clang++','-std=c++17','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(ROOT),'-I',str(directory),str(source),
                *map(str,objects),'-o',str(program)],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([program],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertRegex(result.stdout,r'^RP1_BARS_CALLER_PASS GUARD_FAILURES=\d+ ACTUAL_CORE_AND_CALLER=1 NO_HARDWARE=1\n$')

    def test_actual_six_slot_authorizer_and_numeric_store(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            original=Path(__file__).with_name('pcie_id_provider_host.cpp').read_text()
            self.assertEqual(original.count('int main()'),1)
            prefix=original.split('int main()')[0]
            prefix=prefix.replace('#include "loader/rpi5/pcie_released_windows.h"',
                '#include "loader/rpi5/pcie_released_windows.h"\n#include "loader/rpi5/rp1_bars_probe.h"')
            self.assertEqual(prefix.count('    static int rp1Acquire(void *);'),1)
            prefix=prefix.replace('    static int rp1Acquire(void *);',
                '    struct rpi5_rp1_bars_probe barsProbe={};\n'
                '    static int rp1BarsAuthorize(void *,const struct rpi5_pcie_config_request *);\n'
                '    static int rp1BarsWrite(void *,uint32_t,uint32_t,uint32_t);\n'
                '    static int rp1Acquire(void *);')
            body=(ROOT/'iokit/Kernel/BCM2712PCIeIDTrial.inc').read_text()
            boundary='/* Distinct IOStartIOKit caller invokes this BEFORE any driver matching'
            (directory/'actual-id-provider.inc').write_text(body.split(boundary)[0])
            main=r'''
#include "iokit/Kernel/BCM2712RP1BarsTransport.inc"
static void ready(BCM2712PCIePHYTransport &s,unsigned bar){
 s.ready(BCM2712_CONTROLLER_RELEASED);s.phase=BCM2712_PHY_RP1_INSPECTING;
 s.rp1Config.state=RPI5_PCIE_CONFIG_BUSY;s.rp1Locked=true;s.barsProbe.selected=bar;
 s.barsProbe.state=RPI5_RP1_BARS_PROBING;s.barsProbe.writes_started=2*bar+1;
 s.barsProbe.originals[bar]=0x400000;s.memory[0x8010/4+bar]=0x400000;
}
int main(){
 for(unsigned bar=0;bar<6;bar++){
  {BCM2712PCIePHYTransport s;ready(s,bar);
   assert(!s.rp1BarsWrite(&s,0x8010+4*bar,4,UINT32_MAX));assert(s.memory[0x8010/4+bar]==UINT32_MAX&&s.checks==2);
   s.barsProbe.state=RPI5_RP1_BARS_RESTORING;s.barsProbe.writes_started++;
   assert(!s.rp1BarsWrite(&s,0x8010+4*bar,4,0x400000));assert(s.memory[0x8010/4+bar]==0x400000&&s.checks==4);
   s.barsProbe.state=RPI5_RP1_BARS_COMPLETE;assert(s.rp1BarsWrite(&s,0x8010+4*bar,4,0x400000)&&s.checks==4);
  }
  for(unsigned failure=1;failure<=2;failure++){
   BCM2712PCIePHYTransport s;ready(s,bar);s.failAt=failure;
   assert(s.rp1BarsWrite(&s,0x8010+4*bar,4,UINT32_MAX));
   assert(s.checks==failure&&s.phase==BCM2712_PHY_FAILED);
   assert(s.memory[0x8010/4+bar]==(failure==1?0x400000:UINT32_MAX));
  }
  for(unsigned offset=0x8000;offset<0x8040;offset++)for(unsigned width=1;width<=8;width++){
   BCM2712PCIePHYTransport s;ready(s,bar);
   if(offset==0x8010+4*bar&&width==4)continue;
   assert(s.rp1BarsWrite(&s,offset,width,UINT32_MAX));assert(!s.checks&&s.memory[0x8010/4+bar]==0x400000);
  }
 }
 for(unsigned bad=0;bad<5;bad++){
  BCM2712PCIePHYTransport s;ready(s,1);
  if(bad==0)s.owner=false;if(bad==1)s.rp1Locked=false;if(bad==2)s.trialMode=false;
  if(bad==3)s.rp1Config.state=RPI5_PCIE_CONFIG_READY;if(bad==4)s.phase=BCM2712_PHY_COMPLETE;
  assert(s.rp1BarsWrite(&s,0x8014,4,UINT32_MAX)&&!s.checks&&s.memory[0x8014/4]==0x400000);
 }
 puts("RP1_BARS_TRANSPORT_PASS ACTUAL_METHODS=2 FORBIDDEN_OFFSET_WIDTH=3066 NO_HARDWARE=1");
}
'''
            source=directory/'bars.cpp';source.write_text(prefix+main)
            objects=[]
            for name in ('pcie_config','rp1_config_snapshot_checked','pcie_released_windows','rp1_bars_probe'):
                obj=directory/(name+'.o')
                result=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined','-c',str(ROOT/'loader/rpi5'/(name+'.c')),'-o',str(obj)],
                    capture_output=True,text=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stderr);objects.append(obj)
            program=directory/'bars'
            result=subprocess.run(['xcrun','clang++','-std=c++17','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(ROOT),'-I',str(directory),str(source),
                *map(str,objects),'-o',str(program)],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([program],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,'RP1_BARS_TRANSPORT_PASS ACTUAL_METHODS=2 FORBIDDEN_OFFSET_WIDTH=3066 NO_HARDWARE=1\n')


if __name__=='__main__':unittest.main()
