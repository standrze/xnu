# SPDX-License-Identifier: BSD-2-Clause
"""Actual project PID1 body and frozen source/kernel ABI; no target execution."""
import json
import os
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5 import init_shutdown_late_framed_profile as p, build_init_shutdown_late_framed as b

class InitShutdownLateFramedTests(unittest.TestCase):
    def test_exact_original_shutdown_signal_and_nonexiting_policy(self):
        raw=p.ORIGINAL.read_text();new=p.derive(raw)
        self.assertNotIn('rt_call(48',raw);self.assertNotIn('rt_call(52',raw)
        self.assertEqual(new[new.index('_Noreturn void user_start'):],raw[raw.index('_Noreturn void user_start'):])
        with self.assertRaises(ValueError):p.derive(raw+'\n')
        shutdown=(p.ROOT/'bsd/kern/kern_shutdown.c').read_text()
        self.assertIn('p = proc_find(1);\n\tif (p && p != self) {\n\t\tpsignal(p, SIGTERM);',shutdown)
        self.assertIn('task_suspend_internal(proc_task(initproc));',shutdown)
        self.assertIn('if (p == initproc) {\n\t\t/* Always panic for launchd */\n\t\treturn true;', (p.ROOT/'bsd/kern/kern_exit.c').read_text())
        self.assertNotIn('SIG_IGN',re.sub(r'/\*.*?\*/','',p.BODY.read_text(),flags=re.S))

    def test_late_reports_exact_derived_boundaries(self):
        body=p.body();self.assertEqual(body.count(p.READY),1)
        self.assertIn('rt_put(1, "\\n'+p.READY+'\\n");',body)
        self.assertIn('while (!init_successful_sleeps) init_pause();',body)
        self.assertLess(body.index('while (!init_successful_sleeps)'),body.index('long shell = rt_fork();'))
        self.assertIn('if (result == 0)',body)
        self.assertIn('actual != init_expected_mask',body)
        self.assertEqual(body.count('init_ready_reports++'),1)
        self.assertIn('if (init_ready_reports < 3)',body)

    def test_actual_darwin_abi_constants_and_pending_thread_route(self):
        source=(p.ROOT/'bsd/kern/kern_sig.c').read_text()
        self.assertIn('error = copyin(uap->mask, &nmask, sizeof(sigset_t));',source)
        self.assertIn('pendlist = ut->uu_siglist & (~sigcantmask);',source)
        self.assertIn('uth->uu_siglist |= mask;',source)
        master=(p.ROOT/'bsd/kern/syscalls.master').read_text()
        self.assertRegex(master,r'(?m)^48\s+[^\n]*int sigprocmask\(int how, user_addr_t mask, user_addr_t omask\)')
        self.assertRegex(master,r'(?m)^52\s+[^\n]*int sigpending\(struct sigvec \*osv\)')
        signal=(p.ROOT/'bsd/sys/signal.h').read_text()
        for name,value in [('SIGTERM',15),('SIG_BLOCK',1),('SIG_SETMASK',3)]:self.assertRegex(signal,r'#define\s+'+name+r'\s+'+str(value)+r'\b')
        self.assertRegex((p.ROOT/'bsd/sys/wait.h').read_text(),r'#define\s+WNOHANG\s+0x00000001')

    def test_actual_saved_native_a76_source_object_and_static_link(self):
        package=os.environ.get('RPI5_INIT_SHUTDOWN_LATE_FRAMED_PACKAGE');pin=os.environ.get('RPI5_INIT_SHUTDOWN_LATE_FRAMED_MANIFEST_SHA256')
        if not package or not pin:self.fail('Supply exact saved init-shutdown package and manifest SHA')
        out=Path(package).resolve();self.assertEqual(p.sha(out/'manifest.json'),pin)
        m=json.loads((out/'manifest.json').read_text())
        self.assertEqual(set(m['generated_sha256']),{str(f) for f in out.iterdir() if f.is_file() and f.name!='manifest.json'})
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for name,h in m[key].items():self.assertEqual(p.sha(name),h,name)
        self.assertEqual((out/'init.c').read_text(),p.derive(p.ORIGINAL.read_text()))
        self.assertEqual((out/'original-init.o').read_bytes(),(b.BASE/'init.o').read_bytes())
        self.assertEqual(subprocess.check_output(['xcrun','nm','-ju',out/'NOT_RUN_launchd'],text=True),'')
        self.assertEqual(b.prepare_pid1.inspect((out/'NOT_RUN_launchd').read_bytes()),m['target_inspection'])
        self.assertIn('-mcpu=cortex-a76',next(r['command'] for r in m['commands'] if r['label']=='shutdown-init-compile'))
        r=subprocess.run([out/'init-host'],capture_output=True,text=True,timeout=15)
        self.assertEqual((r.returncode,r.stdout,r.stderr),(0,m['native_stdout'],''))
        self.assertEqual(subprocess.run([out/'init-host','bad-expectation'],capture_output=True,timeout=15).returncode,37)
        self.assertIs(m['arrival_fork_atomicity_claimed'],False)
        self.assertIs(m['kernel_panic_modified'],False)
        self.assertIs(m['target_executed'],False)
        self.assertEqual(m['readiness_max_reports'],3)
        self.assertTrue(m['readiness_full_mask_and_pending_revalidated'])
        self.assertFalse(m['uart_line_atomicity_claimed'])

if __name__=='__main__':unittest.main()


