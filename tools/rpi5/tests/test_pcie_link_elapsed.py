# SPDX-License-Identifier: BSD-2-Clause
"""Actual private C/C++ bodies, deterministic time/guard models, no hardware."""
import subprocess
import tempfile
from pathlib import Path
import unittest
from tools.rpi5 import pcie_link_elapsed_profile as profile


class LinkElapsedTests(unittest.TestCase):
    def run_native(self,folder,source,language='c'):
        source_path=folder/('test.'+('cpp' if language=='c++' else 'c'))
        source_path.write_text(source);program=folder/'test'
        r=subprocess.run(['xcrun','clang++' if language=='c++' else 'clang',
            '-std=c++17' if language=='c++' else '-std=c11','-Wall','-Wextra','-Werror',
            '-fsanitize=address,undefined','-I',str(folder),'-I',str(profile.ROOT/'loader/rpi5'),
            str(source_path),'-o',str(program)],capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        r=subprocess.run([program],capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr)
        return r.stdout

    def test_actual_old_and_new_delay_bodies_guard_cost_and_faults(self):
        text=(profile.FROZEN/'BCM2712PCIePHYTransport.cpp').read_text()
        start=text.index('int BCM2712PCIePHYTransport::delayUS(')
        end=text.index('bool BCM2712PCIePHYTransport::runInitialPHY(',start)
        old=text[start:end].replace('BCM2712PCIePHYTransport','OldTransport')
        host=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
static constexpr unsigned BCM2712_PHY_LINK_TRAINING=12;
struct Model {
 uint64_t ns=1000000000,guard_ns=0,overshoot_ns=0;
 unsigned guards=0,fail_guard=0,delays=0,clocks=0,clock_fault=0,mode=0;
 unsigned max_chunk=0,clock_mode=0;
} m;
static void clock_get_uptime(uint64_t *out){
 m.clocks++;*out=m.ns;
 if(m.clocks==m.clock_fault)*out=m.clock_mode==1?0:UINT64_MAX;
 if(m.mode==1)*out=1000000000; // Stuck clock.
 if(m.mode==2)*out=1000000000+m.clocks; // Progress below actual requested interval.
}
static void absolutetime_to_nanoseconds(uint64_t time,uint64_t *ns){*ns=time;}
static void IODelay(uint32_t us){
 assert(us&&us<=1000);m.delays++;if(us>m.max_chunk)m.max_chunk=us;
 m.ns+=uint64_t(us)*1000+m.overshoot_ns;
}
struct Base {
 bool owner=true,controllerMode=true;unsigned phase=12,failures=0;
 bool onOwnerThread(){return owner;}unsigned getPhase(){return phase;}
 int fail(){failures++;return -1;}
 bool guard(){m.guards++;m.ns+=m.guard_ns;return m.guards!=m.fail_guard;}
};
struct BCM2712PCIePHYTransport:Base{static int delayUS(void*,uint32_t);};
struct OldTransport:Base{static int delayUS(void*,uint32_t);};
'''
        main=r'''
int main(){
 for(unsigned requested:{1u,999u,1000u,1001u}){
  m={};BCM2712PCIePHYTransport s;assert(!s.delayUS(&s,requested));
  assert(m.ns-1000000000==uint64_t(requested)*1000);
  assert(m.delays==(requested+999)/1000&&m.max_chunk<=1000);
 }
 for(unsigned requested:{5000u,100000u})for(uint64_t cost:{0ull,1000ull,64000ull,200000ull}){
  m={};m.guard_ns=cost;OldTransport old;
  assert(!OldTransport::delayUS(&old,requested));uint64_t old_elapsed=m.ns-1000000000;
  assert(old_elapsed==uint64_t(requested)*1000+2*(requested/1000)*cost);
  m={};m.guard_ns=cost;BCM2712PCIePHYTransport s;
  assert(!s.delayUS(&s,requested));
  assert(m.ns-1000000000>=uint64_t(requested)*1000);
  assert(m.ns-1000000000<=uint64_t(requested)*1000+3*cost+1000);
  assert(m.max_chunk<=1000&&m.delays<=requested/1000);
  if(requested==100000&&cost==64000){assert(old_elapsed>110000000);assert(m.ns-1000000000<110000000);}
 }
 m={};BCM2712PCIePHYTransport success;assert(!success.delayUS(&success,100000));
 unsigned guards=m.guards;assert(guards==201);
 for(unsigned at=1;at<=guards;at++){
  m={};m.fail_guard=at;BCM2712PCIePHYTransport s;
  assert(s.delayUS(&s,100000));assert(m.guards==at&&m.delays<=100);
 }
 for(unsigned mode:{1u,2u}){
  m={};m.mode=mode;BCM2712PCIePHYTransport s;
  assert(s.delayUS(&s,100000));assert(s.failures==1&&m.delays<=100&&m.clocks<=201);
 }
 // Each available clock point can go backwards; no continued delay follows.
 for(unsigned at=2;at<=201;at++){
  m={};m.clock_fault=at;m.clock_mode=1;BCM2712PCIePHYTransport s;
  assert(s.delayUS(&s,100000));assert(s.failures==1&&m.clocks==at);
 }
 // Forward overshoot remains visible to the unchanged enclosing core ceiling.
 m={};m.overshoot_ns=60000000;BCM2712PCIePHYTransport over;
 assert(!over.delayUS(&over,100000));assert(m.ns-1000000000>110000000);
 for(unsigned request:{0u,100001u}){
  m={};BCM2712PCIePHYTransport s;assert(s.delayUS(&s,request));assert(!m.guards&&!m.delays);
 }
 m={};BCM2712PCIePHYTransport foreign;foreign.owner=false;
 assert(foreign.delayUS(&foreign,100000));assert(!m.guards&&!m.delays&&!foreign.failures);
 m={};BCM2712PCIePHYTransport not_controller;not_controller.controllerMode=false;
 assert(not_controller.delayUS(&not_controller,100000));assert(!m.guards&&!m.delays);
 for(unsigned us:{1u,100u,101u}){
  m={};BCM2712PCIePHYTransport s;s.phase=2;
  assert(bool(s.delayUS(&s,us))==(us>100));assert(m.guards==(us>100?0u:2u));
 }
 puts("LINK_DELAY_PASS GUARD_FAULTS=201 BACKWARD=200 BOUNDED_STUCK=1 CEILING_UNCHANGED=1");
}
'''
        with tempfile.TemporaryDirectory() as d:
            stdout=self.run_native(Path(d),host+old+profile.DELAY+main,'c++')
            self.assertIn('GUARD_FAULTS=201 BACKWARD=200',stdout)

    def test_original_core_fault_matrix_and_exact_partial_telemetry(self):
        source=(profile.ROOT/'loader/rpi5/pcie_link.c').read_text()
        harness=profile.ROOT/'tools/rpi5/tests/pcie_link_host.c'
        extra=r'''
#define main original_suite_main
#include "HARNESS"
#undef main
int main(void){
 assert(!original_suite_main());
 struct fixture f;struct rpi5_pcie_link_observation out,prior;
 struct rpi5_pcie_link_elapsed_trace trace;
 prepare(&f,1);assert(!rpi5_pcie_link_train_elapsed_trace(&f.link,&out,&trace));
 assert(trace.step==14&&trace.reset_start_us==1000000&&trace.reset_end_us==1100000);
 assert(trace.reset_wait_us==100000&&trace.poll_reads==1&&!trace.poll_elapsed_us);
 unsigned delay=0;for(unsigned i=0;i<f.m.calls;i++)if(f.m.events[i].kind==DELAY){delay=i+1;break;}
 assert(delay);
 for(unsigned mode=1;mode<=5;mode++){
  prepare(&f,1);f.m.delay_at=delay;f.m.delay_mode=mode;memset(&out,0xa5,sizeof out);prior=out;
  int rc=rpi5_pcie_link_train_elapsed_trace(&f.link,&out,&trace);
  if(mode==4){assert(!rc&&trace.step==14&&trace.reset_wait_us==110000);continue;}
  assert(rc==(mode==3?RPI5_PCIE_LINK_TIMEOUT:RPI5_PCIE_LINK_CLOCK));
  assert(trace.step==6&&!trace.poll_reads&&!trace.poll_elapsed_us);
  assert(!memcmp(&out,&prior,sizeof out));
  if(mode==3)assert(trace.reset_wait_us==111001);
 }
 prepare(&f,1);f.m.fail_at=delay;
 assert(rpi5_pcie_link_train_elapsed_trace(&f.link,&out,&trace)==RPI5_PCIE_LINK_IO);
 assert(trace.step==4&&!trace.reset_end_us&&!trace.reset_wait_us&&!trace.poll_reads);
 prepare(&f,21);assert(!rpi5_pcie_link_train_elapsed_trace(&f.link,&out,&trace));
 assert(trace.step==14&&trace.poll_reads==21&&trace.poll_elapsed_us==100000);
 puts("LINK_PARTIAL_TRACE_PASS ORIGINAL_MATRIX=1 RESET_BOUNDARIES=5 NO_EXTRA_CALLBACKS=1");
 return 0;
}
'''.replace('HARNESS',str(harness))
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);(folder/'pcie_link_elapsed_trace.h').write_text(profile.HEADER)
            stdout=self.run_native(folder,profile.core(source)+extra)
            self.assertIn('LINK_PARTIAL_TRACE_PASS',stdout)

    def test_transforms_retain_permissions_deadlines_and_guard_order(self):
        source=(profile.ROOT/'loader/rpi5/pcie_link.c').read_text();changed=profile.core(source)
        for token in ('#define RESET_WAIT UINT32_C(100000)','#define RESET_LIMIT UINT64_C(110000)',
                      '#define POLL_WAIT UINT32_C(5000)','#define POLL_LIMIT UINT64_C(100000)',
                      'STEP(io->','READ(','READ16(','WRITE(','session->io.check_lifecycle('):
            self.assertEqual(source.count(token),changed.count(token))
        original=(profile.ROOT/'iokit/Kernel/BCM2712PCIeControllerRun.inc').read_text()
        transformed=profile.controller(original)
        self.assertEqual(original.count('guard()'),transformed.count('guard()'))
        self.assertEqual(original.count('rpi5_pcie_link_init('),transformed.count('rpi5_pcie_link_init('))
        self.assertNotIn('rpi5_pcie_link_train(',transformed)
        text=(profile.FROZEN/'BCM2712PCIePHYTransport.cpp').read_text();modified=profile.transport(text)
        for token in ('*reinterpret_cast<volatile uint32_t *>','pe_rpi5_watchdog_check_pcie(',
                      'bcm2712_controller_access_allowed('):self.assertEqual(text.count(token),modified.count(token))
        trial=profile.trial((profile.FROZEN/'BCM2712PCIeIDTrialProgress.inc').read_text())
        self.assertEqual(trial.count('kprintf('),3)
        self.assertIn('LINK_RC=%d',trial);self.assertIn('RESET_US=%llu',trial)


if __name__=='__main__':unittest.main()
