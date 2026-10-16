# SPDX-License-Identifier: BSD-2-Clause
"""Actual traced owner failure branches, unchanged composition and encoder."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import pcie_owner_trace_profile as p
from tools.rpi5.tests import test_pcie_owner_composition as composed
from tools.rpi5.tests import test_pcie_bounded_log as encoder


class OwnerTraceTests(unittest.TestCase):
    def test_instrumentation_preserves_actual_success_counts(self):
        expected=composed.run_composition(composed.MAIN)
        actual=composed.run_composition(composed.MAIN,True)
        self.assertEqual(actual,expected)
        self.assertIn('PM_CHECKS=25282 SMC_CALLS=3612 FW_SEQUENCE=3611 ',actual)

    def test_real_nested_failure_snapshots_not_new_diagnostic_access(self):
        prefix=composed.MAIN.split('int main(){')[0]
        main=r'''
static void snapshot(BCM2712PCIePHYTransport &s,rpi5_pcie_owner_trace &t){
 unsigned calls=smc_calls,ns=ns_reads,secure=secure_reads;uint64_t now=model_ticks;
 assert(!pe_rpi5_pcie_owner_trace(&s,&t)&&t.available==1);
 assert(calls==smc_calls&&ns==ns_reads&&secure==secure_reads&&now==model_ticks);
 auto saved=t;assert(pe_rpi5_pcie_owner_trace(nullptr,&t)&&!memcmp(&saved,&t,sizeof t));
}
static void full(BCM2712PCIePHYTransport &s){
 prepared(s);bcm2712_rp1_observation out={};assert(s.runBoundedRP1Trial(&out));
 s.phase=BCM2712_PHY_RP1_INSPECTING;
}
int main(){
 for(unsigned mode=0;mode<5;mode++){
  BCM2712PCIePHYTransport s;full(s);unsigned calls=smc_calls;
  if(mode==0)rpi5_pcie_wdog_lease.checks=65532;
  if(mode==1){corrupt_smc=calls+1;corrupt_field=0;corrupt_raw=(uint64_t)(int64_t)-5;}
  if(mode==2){corrupt_smc=calls+1;corrupt_field=2;corrupt_raw=rpi5_pcie_fw_session.last_counter;}
  if(mode==3)corrupt_irq_after_smc=true;
  if(mode==4)rpi5_pcie_fw_session.deadline=model_ticks+1;
  assert(!s.guard()&&s.diagGuard==4&&s.phase==BCM2712_PHY_FAILED);
  rpi5_pcie_owner_trace t={};snapshot(s,t);
  assert(t.fw_stage==6&&t.fw_rc==-1&&t.fw_state==RPI5_FW_CLIENT_QUARANTINED);
  if(mode==0){
   assert(smc_calls==calls&&t.rpc_stage==5&&t.pm_checks==65536&&t.pm_stage==6&&t.pm_rc==-1);
   assert(t.pm_state==RPI5_PCIE_WDOG_QUARANTINED&&t.irq_stage==8&&t.irq_state==RPI5_PCIE_IRQ_QUARANTINED);
   for(unsigned i=0;i<4;i++)assert(t.rpc_raw[i]==0);
  }else{
   assert(smc_calls==calls+1&&t.pm_state==RPI5_PCIE_WDOG_ARMED);
   if(mode==3){assert(t.rpc_stage==8&&t.irq_stage==7&&t.irq_rc==-1&&t.irq_state==RPI5_PCIE_IRQ_QUARANTINED);}
   else{assert(t.rpc_stage==9&&t.irq_stage==9&&t.irq_state==RPI5_PCIE_IRQ_MASKED);}
   if(mode==1)assert(t.rpc_raw[0]==(uint64_t)(int64_t)-5);
   if(mode==2)assert(t.rpc_raw[2]==t.fw_last);
   if(mode==4)assert(t.rpc_raw[2]>=t.fw_deadline);
  }
 }
 puts("OWNER_TRACE_PASS ACTUAL_FAILURE_MODES=5 EXTRA_ACCESS=0 DEADLINES_UNCHANGED=1 NO_BOARD_CAUSE_CLAIM=1");return 0;
}
'''
        stdout=composed.run_composition(prefix+main,True)
        self.assertEqual(stdout,'OWNER_TRACE_PASS ACTUAL_FAILURE_MODES=5 EXTRA_ACCESS=0 DEADLINES_UNCHANGED=1 NO_BOARD_CAUSE_CLAIM=1\n')

    def test_five_records_fit_actual_apple_encoder(self):
        formats=re.findall(r'kprintf\("([^"\n]+)"',p.trace_calls())
        self.assertEqual(len(formats),5)
        lines=['int main(void){for(unsigned loc=4;loc<=8;loc+=4)for(unsigned sid=0;sid<2;sid++){','location_size=loc;subsystem=sid;']
        for fmt in formats:lines.append('assert(encode('+encoder.c_string(fmt)+','+encoder.values(fmt)+'));')
        lines+=['}assert(encoded_calls==20);printf("OWNER_LOG_PASS CALLS=%u MAX_BYTES=%zu\\n",encoded_calls,max_bytes);return 0;}']
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);src=folder/'host.c';src.write_text(encoder.encoder_source()+'\n'.join(lines));exe=folder/'host'
            r=subprocess.run(['xcrun','clang','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(src),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run([exe],capture_output=True,text=True,timeout=10)
            self.assertEqual(r.returncode,0,r.stderr);self.assertIn('OWNER_LOG_PASS CALLS=20 MAX_BYTES=',r.stdout)
            self.assertLess(int(re.search(r'MAX_BYTES=(\d+)',r.stdout)[1]),100)


if __name__=='__main__':unittest.main()
