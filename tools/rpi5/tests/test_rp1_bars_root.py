# SPDX-License-Identifier: BSD-2-Clause
"""Current actual BAR caller/lifecycle/config bodies with explicit MMIO doubles."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import types
import unittest
from tools.rpi5 import rp1_bars_root_profile as p
from tools.rpi5.tests import test_rp1_bars_transport as old
from tools.rpi5.tests import test_pcie_bounded_log as encoder


class BarsRootTests(unittest.TestCase):
    def test_actual_current_caller_trace_and_guard_failure_matrix(self):
        # Reuse the actual-file harness, but compile the NEW emitted caller and
        # trace snapshot body; the controller setup is explicitly a fixture.
        text=Path(old.__file__).read_text().split('    def test_actual_six_slot_authorizer_and_numeric_store')[0]
        text=p.once(text,"            body=(ROOT/'iokit/Kernel/BCM2712PCIeIDTrial.inc').read_text()",
            "            body=(PROFILE.FROZEN/'BCM2712PCIeIDTrialProgress.inc').read_text()")
        text=p.once(text,"            prefix=replace(prefix,'#include \"iokit/Kernel/BCM2712RP1ConfigTransport.inc\"',",
            "            prefix=replace(prefix,'    unsigned checks=0,failAt=0,controllerCalls=0;',\n"
            "                '    unsigned checks=0,failAt=0,controllerCalls=0;\\n'\n"
            "                '    unsigned diagIOBank=0,diagIOOffset=0,diagIODirection=0,diagIOStage=0,diagIOValue=0;\\n'\n"
            "                '    unsigned diagRP1Call=0,diagBarsCall=0;int diagRP1RC=0,diagBarsRC=0;\\n'\n"
            "                '    uint32_t diagRP1Status=0,diagRP1Selector=0;rpi5_rp1_config_trace diagRP1={};')\n"
            "            prefix=replace(prefix,'#include \"loader/rpi5/rp1_bars_plan.h\"',\n"
            "                '#include \"loader/rpi5/rp1_bars_plan.h\"\\n#include \"rp1_config_trace.h\"')\n"
            "            (directory/'rp1_config_trace.h').write_bytes((PROFILE.FROZEN/'rp1_config_trace.h').read_bytes())\n"
            "            (directory/'actual-bars-writes.inc').write_text(PROFILE.bar_transport((ROOT/'iokit/Kernel/BCM2712RP1BarsTransport.inc').read_text()))\n"
            "            prefix=replace(prefix,'#include \"iokit/Kernel/BCM2712RP1ConfigTransport.inc\"',")
        text=p.once(text,"'#include \"actual-bars-caller.inc\"\\n#include \"iokit/Kernel/BCM2712RP1BarsTransport.inc\"')",
            "'#include \"actual-bars-caller.inc\"\\n#include \"actual-bars-writes.inc\"')")
        text=p.once(text,"str(ROOT/'loader/rpi5'/(name+'.c')),'-o',str(obj)],",
            "str(PROFILE.FROZEN/(name+'.c') if name=='rp1_config_snapshot_checked' else ROOT/'loader/rpi5'/(name+'.c')),'-I',str(ROOT/'loader/rpi5'),'-o',str(obj)],")
        text=p.once(text,"'-fsanitize=address,undefined','-I',str(ROOT),'-I',str(directory),str(source),",
            "'-fsanitize=address,undefined','-I',str(ROOT),'-I',str(ROOT/'loader/rpi5'),'-I',str(directory),str(source),")
        # Exercise actual reset BAR values from the successful raw observation,
        # rather than preassigning the prospective allocation candidate.
        text=p.once(text,'s.memory[0x8010/4]=0x410000;s.memory[0x8018/4]=0x400000;',
            's.memory[0x8010/4]=0xffffc000;s.memory[0x8014/4]=0xffc00000;s.memory[0x8018/4]=0xffff0000;')
        text=p.once(text,'s.memory[0x8010/4]==0x410000&&s.memory[0x8018/4]==0x400000',
            's.memory[0x8010/4]==0xffffc000&&s.memory[0x8018/4]==0xffff0000')
        text=p.once(text,'s.memory[0x8014/4]==0&&s.memory[0x801c/4]==0',
            's.memory[0x8014/4]==0xffc00000&&s.memory[0x801c/4]==0')
        module=types.ModuleType('_current_bars_caller_test');module.__file__=old.__file__
        exec(compile(text,old.__file__,'exec'),module.__dict__)
        module.PROFILE=p
        module.builder=types.SimpleNamespace(previous=old.builder.previous,
            transport_source=lambda _:p.transport((p.FROZEN/'BCM2712RP1ConfigTransport.inc').read_text()))
        module.RP1BarsTransportTests('test_actual_integrated_all_bar_caller').test_actual_integrated_all_bar_caller()

    def test_all_seven_additional_records_fit_actual_encoder(self):
        calls=p.diagnostic_calls()
        formats=re.findall(r'kprintf\("([^"\n]+)"',calls)
        self.assertEqual(len(formats),7)
        lines=['int main(void){for(unsigned loc=4;loc<=8;loc+=4)for(unsigned sid=0;sid<2;sid++){',
            'location_size=loc;subsystem=sid;']
        for fmt in formats:lines.append('assert(encode('+encoder.c_string(fmt)+','+encoder.values(fmt)+'));')
        lines+=['}assert(encoded_calls==28);printf("BAR_LOG_PASS CALLS=%u MAX_BYTES=%zu\\n",encoded_calls,max_bytes);return 0;}']
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);source=folder/'encoder.c';source.write_text(encoder.encoder_source()+'\n'.join(lines))
            exe=folder/'encoder';r=subprocess.run(['xcrun','clang','-std=gnu11','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined',str(source),'-o',str(exe)],capture_output=True,text=True,timeout=60)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run([exe],capture_output=True,text=True,timeout=10)
            self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout,'BAR_LOG_PASS CALLS=28 MAX_BYTES=54\n')

    def test_changed_sources_exact_scope_and_published_success_not_partial_state(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'overlay';p.emit(folder)
            changed=[]
            for oldfile in p.FROZEN.iterdir():
                if oldfile.is_file() and oldfile.read_bytes()!=(folder/oldfile.name).read_bytes():changed.append(oldfile.name)
            self.assertEqual(set(changed),{'BCM2712PCIePHYTransport.cpp','BCM2712PCIePHYTransport.h',
                'BCM2712RP1ConfigTransport.inc','BCM2712PCIeIDTrialProgress.inc'})
            body=(folder/'BCM2712RP1ConfigTransport.inc').read_text()
            self.assertLess(body.index('rpi5_rp1_config_snapshot_trace('),body.index('rpi5_rp1_bars_probe('))
            self.assertLess(body.index('rpi5_rp1_bars_probe('),body.index('rpi5_rp1_bars_assignment_plan('))
            self.assertLess(body.index('rpi5_rp1_bars_assignment_plan('),body.index('*out = result;'))
            trial=(folder/'BCM2712PCIeIDTrialProgress.inc').read_text()
            self.assertEqual(trial.count('kprintf('),14)
            self.assertLess(trial.index('PCIEID:BAR5 '),trial.index('PCIEID:END '))
            self.assertNotIn('rp1BarsWrite', (folder/'BCM2712PCIeControllerRun.inc').read_text())


if __name__=='__main__':unittest.main()
