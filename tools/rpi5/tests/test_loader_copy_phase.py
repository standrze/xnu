# SPDX-License-Identifier: BSD-2-Clause
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import loader_copy_phase_profile as p

BASE=p.ROOT/'build/rpi5/display-restart-diagnostic-gb38kpad'
class LoaderCopyPhaseTests(unittest.TestCase):
    def test_actual_body_phase_faults_and_old_gap_native(self):
        raw=p.BODY.read_text()
        clock='__asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(now));'
        barrier='__asm__ volatile("dsb sy" ::: "memory");'
        self.assertEqual(raw.count(clock),2);self.assertEqual(raw.count(barrier),1)
        native=raw.replace(clock,'now=fake_now;').replace(barrier,'barriers++;')
        with tempfile.TemporaryDirectory(prefix='copy-phase-') as d:
            out=Path(d);(out/'copy_phase_native.inc').write_text(native)
            cmd=['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(p.ROOT),'-I',str(out),
                str(Path(__file__).with_name('loader_copy_phase_host.c')),'-o',str(out/'host')]
            subprocess.run(cmd,check=True,capture_output=True,timeout=60)
            r=subprocess.run([out/'host'],capture_output=True,text=True,timeout=20)
            self.assertEqual(r.returncode,0,r.stderr);self.assertFalse(r.stderr)
            self.assertIn('TWO_RENEWALS OLD_GAP_REPRODUCED',r.stdout)

    def test_actual_source_dominance_omission_order_and_exact_limits(self):
        raw=(BASE/'probe_main.c').read_text();new=p.transform(raw)
        self.assertLess(new.index('rpi5_resolved_tree_handoff(validated_kernel'),new.index('copy_watchdog_checkpoint(1,&handoff,0)'))
        self.assertLess(new.index('copy_watchdog_checkpoint(1,&handoff,0)'),new.index('rpi5_macho_materialize(validated_kernel'))
        self.assertLess(new.index('copied.destination[i]!=handoff.kernel.destination[i]'),new.index('copy_watchdog_checkpoint(2,&handoff,&copied)'))
        self.assertIn('__asm__ volatile("dsb sy" ::: "memory");\n    if (!copy_watchdog_checkpoint(2',new)
        self.assertLess(new.index('copy_watchdog_checkpoint(2,&handoff,&copied)'),new.index('rpi5_macho_verify_materialized(validated_kernel'))
        self.assertEqual(new.count('copy_watchdog_checkpoint('),2)
        for broken in (raw.replace('copy_watchdog_checkpoint(1);','copy_watchdog_checkpoint(2);'),
                       raw.replace('now+60*frequency','now+61*frequency'),raw.replace(p.OLD,p.OLD+p.OLD)):
            with self.assertRaises(ValueError):p.transform(broken)

    def test_actual_captured_timing_and_preserved_failure(self):
        directory=p.ROOT/'build/rpi5/display-xnu-visible-capture-20261014'
        raw=(directory/'serial.bin').read_bytes()
        events=[json.loads(line) for line in (directory/'receive-events.jsonl').read_text().splitlines()]
        def received(marker):
            offset=raw.index(marker)+len(marker)
            return next(e['monotonic'] for e in events if e['offset']+e['bytes']>=offset)
        start=received(b'PHYSICAL_READBACK_BEGIN CNTVCT=')
        transfer=received(b'RPI5XNU:BL33:XNU_TRANSFER_PENDING WATCHDOG_15S SEED_COMMIT_NEXT')
        self.assertGreater(transfer-start,7);self.assertLess(transfer-start,15)
        failed=p.ROOT/'build/rpi5/restart-diagnostic-capture-v2-20261014/serial.bin'
        self.assertEqual(hashlib.sha256(failed.read_bytes()).hexdigest(),'1d05df4905c84b49cdb7681e8a5f1d320120db8ea3071546421b73697f8340f8')
        self.assertNotIn(b'RPI5XNU:BL33:KERNEL_MATERIALIZED',failed.read_bytes())
        print('Accepted readback-start to transfer marker seconds:',transfer-start)

    def test_actual_a76_full_loader_tu(self):
        from tools.rpi5 import build_display_xnu_console as flags
        m=json.loads((BASE/'manifest.json').read_text())
        row=next(r for r in m['commands'] if r['label']=='loader-main-compile')
        with tempfile.TemporaryDirectory(prefix='copy-phase-a76-') as d:
            out=Path(d);src=out/'probe_main.c';src.write_text(p.transform((BASE/'probe_main.c').read_text()))
            command=flags.compiler_flags(row['command'],BASE/'probe_main.c')
            result=subprocess.run([*command,'-c',str(src),'-o',str(out/'main.o')],cwd=row['cwd'],capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stderr);self.assertNotIn('warning:',result.stderr)
            self.assertIn('-mcpu=cortex-a76',command)

if __name__=='__main__':unittest.main()
