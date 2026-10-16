# SPDX-License-Identifier: BSD-2-Clause
import subprocess
import tempfile
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[3]


class RP1BARTransportTests(unittest.TestCase):
    def test_real_authorizer_and_ordered_store_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            original=(Path(__file__).with_name('pcie_id_provider_host.cpp')).read_text()
            self.assertEqual(original.count('int main()'),1)
            prefix=original.split('int main()')[0]
            prefix=prefix.replace('#include "loader/rpi5/pcie_released_windows.h"',
                '#include "loader/rpi5/pcie_released_windows.h"\n#include "loader/rpi5/rp1_bar1_probe.h"')
            self.assertEqual(prefix.count('    static int rp1Acquire(void *);'),1)
            prefix=prefix.replace('    static int rp1Acquire(void *);',
                '    struct rpi5_rp1_bar1_probe barProbe={};\n'
                '    static int rp1BarAuthorize(void *,const struct rpi5_pcie_config_request *);\n'
                '    static int rp1BarWrite(void *,uint32_t,uint32_t,uint32_t);\n'
                '    static int rp1Acquire(void *);')
            body=(ROOT/'iokit/Kernel/BCM2712PCIeIDTrial.inc').read_text()
            boundary='/* Distinct IOStartIOKit caller invokes this BEFORE any driver matching'
            (directory/'actual-id-provider.inc').write_text(body.split(boundary)[0])
            main=r'''
#include "iokit/Kernel/BCM2712RP1BARTransport.inc"
static void ready(BCM2712PCIePHYTransport &s){
 s.ready(BCM2712_CONTROLLER_RELEASED);s.phase=BCM2712_PHY_RP1_INSPECTING;
 s.rp1Config.state=RPI5_PCIE_CONFIG_BUSY;s.rp1Locked=true;
 s.barProbe.state=RPI5_RP1_BAR1_PROBING;s.barProbe.writes_started=1;
 s.barProbe.original_bar1=0x400000;s.memory[0x8014/4]=0x400000;
}
int main(){
 {BCM2712PCIePHYTransport s;ready(s);
  assert(!s.rp1BarWrite(&s,0x8014,4,UINT32_MAX));assert(s.memory[0x8014/4]==UINT32_MAX&&s.checks==2);
  s.barProbe.state=RPI5_RP1_BAR1_RESTORING;s.barProbe.writes_started=2;
  assert(!s.rp1BarWrite(&s,0x8014,4,0x400000));assert(s.memory[0x8014/4]==0x400000&&s.checks==4);
  s.barProbe.state=RPI5_RP1_BAR1_COMPLETE;assert(s.rp1BarWrite(&s,0x8014,4,0x400000)&&s.checks==4);
 }
 for(unsigned failure=1;failure<=2;failure++){
  BCM2712PCIePHYTransport s;ready(s);s.failAt=failure;
  assert(s.rp1BarWrite(&s,0x8014,4,UINT32_MAX));
  assert(s.checks==failure&&s.phase==BCM2712_PHY_FAILED);
  assert(s.memory[0x8014/4]==(failure==1?0x400000:UINT32_MAX));
 }
 for(unsigned offset=0x8000;offset<0x8040;offset++)for(unsigned width=1;width<=8;width++){
  BCM2712PCIePHYTransport s;ready(s);
  if(offset==0x8014&&width==4)continue;
  assert(s.rp1BarWrite(&s,offset,width,UINT32_MAX));assert(!s.checks&&s.memory[0x8014/4]==0x400000);
 }
 for(unsigned bad=0;bad<5;bad++){
  BCM2712PCIePHYTransport s;ready(s);
  if(bad==0)s.owner=false;if(bad==1)s.rp1Locked=false;if(bad==2)s.trialMode=false;
  if(bad==3)s.rp1Config.state=RPI5_PCIE_CONFIG_READY;if(bad==4)s.phase=BCM2712_PHY_COMPLETE;
  assert(s.rp1BarWrite(&s,0x8014,4,UINT32_MAX)&&!s.checks&&s.memory[0x8014/4]==0x400000);
 }
 puts("RP1_BAR_TRANSPORT_PASS ACTUAL_METHODS=2 ENDPOINT_STORE32=1 FORBIDDEN_OFFSET_WIDTH=511 NO_HARDWARE=1");
}
'''
            source=directory/'bar.cpp';source.write_text(prefix+main)
            objects=[]
            for name in ('pcie_config','rp1_config_snapshot_checked','pcie_released_windows','rp1_bar1_probe'):
                obj=directory/(name+'.o')
                result=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined','-c',str(ROOT/'loader/rpi5'/(name+'.c')),'-o',str(obj)],
                    capture_output=True,text=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stderr);objects.append(obj)
            program=directory/'bar'
            result=subprocess.run(['xcrun','clang++','-std=c++17','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(ROOT),'-I',str(directory),str(source),
                *map(str,objects),'-o',str(program)],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([program],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,'RP1_BAR_TRANSPORT_PASS ACTUAL_METHODS=2 ENDPOINT_STORE32=1 FORBIDDEN_OFFSET_WIDTH=511 NO_HARDWARE=1\n')


if __name__=='__main__':unittest.main()
