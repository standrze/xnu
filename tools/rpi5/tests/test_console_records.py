# SPDX-License-Identifier: BSD-2-Clause
"""Opt-in actual Apple owner bodies; native doubles never enter target objects."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import console_record_profile as p
from tools.rpi5 import build_display_xnu_console as compiler


def function(raw, name):
    matches=list(re.finditer(r'\b'+re.escape(name)+r'\([^;{}\n]*\)\n\{',raw))
    if len(matches)!=1: raise ValueError('Unique actual function '+name)
    start=matches[0].start();cursor=raw.index('{',start);depth=1;end=cursor+1
    # Selected functions contain no brace literals; reject comments/strings
    # only if the balanced extraction disagrees with a complete closing line.
    while depth:
        if raw[end]=='{':depth+=1
        elif raw[end]=='}':depth-=1
        end+=1
    if raw[end-2:end]!='\n}':raise ValueError('Actual function closing boundary')
    return raw[start:end]+'\n'


def generated_native():
    console=p.console(p.CONSOLE.read_text());general=(p.ROOT/'osfmk/console/serial_general.c').read_text()
    bodies=[]
    for name,result in [('console_io_allowed','static inline bool'),('console_ring_reserve_space','static inline char *'),
                        ('console_ring_unreserve_space','static inline void'),('console_ring_put','static inline void')]:
        bodies.append(result+'\n'+function(console,name))
    bodies.append('#include "osfmk/console/rpi5_console_records.inc"\n')
    bodies.append('static void\n'+function(console,'console_ring_try_empty'))
    bodies.append('void\n'+function(console,'console_write'))
    for name in ('console_printbuf_state_init','console_printbuf_putc','console_printbuf_clear'):
        bodies.append('void\n'+function(general,name))
    kprintf='void\n'+function(p.kprintf(p.KPRINTF.read_text()),'kprintf').replace('kprintf(', 'candidate_kprintf(',1)
    sleh=p.sleh(p.SLEH.read_text())
    callout='bool\n'+function(sleh,'rpi5_terminal_console_thread_owner')
    callout+='static void\n'+function(sleh,'rpi5_terminal_watchdog_callout')
    callout+='bool\n'+function(sleh,'rpi5_terminal_watchdog_start')
    return {'actual_console_bodies.inc':'\n'.join(bodies),'actual_kprintf.inc':kprintf,'actual_callout.inc':callout}


def units():
    return p.compiler_units()


class ConsoleRecordTests(unittest.TestCase):
    def test_concise_actual_init_state_remains_full_policy_and_one_empty_tty_chunk(self):
        raw=(p.INIT/'init.c').read_text();new=p.init_source()
        self.assertEqual(new.replace(p.READY,p.OLD_READY),raw)
        km=(p.ROOT/'bsd/dev/arm/km.c').read_text()
        self.assertRegex(km,r'unsigned char\s+buf\[80\]')
        old=('\n'+p.OLD_READY+'\n').replace('\n','\r\n').encode()
        new=('\n'+p.READY+'\n').replace('\n','\r\n').encode()
        self.assertGreater(len(old),80);self.assertLess(len(new),80)
        # An unrelated complete ring record can split the old TTY chunks.
        interposed=b'KERNEL:record\r\n'
        self.assertNotIn(p.OLD_READY.encode(),old[:80]+interposed+old[80:])
        self.assertIn(p.READY.encode(),new+interposed)
        # This is an empty-TTY-buffer bound, not a promise for arbitrarily
        # backlogged stdout or characters emitted by exceptional raw writers.

    def test_actual_terminal_service_and_gate_no_irq_unarmed_missing_owner_reload(self):
        from tools.rpi5.tests.test_root42_confirmation_service import body
        raw=p.fiq(p.FIQ.read_text())
        declarations=raw.split('static vm_offset_t rpi5_gicd_base;',1)[1].split('static uint32_t\nrpi5_mmio_read32',1)[0]
        declarations=declarations.replace('static vm_offset_t rpi5_gicc_base;\n','')
        defines='\n'.join(line for line in raw.splitlines() if re.match(r'#define RPI5_(?:PM_(?:RSTC|WDOG|FULL_RESET)|WDOG_(?:PASSWORD|INTERVAL|MAX_RELOADS)|TERMINAL_WDOG_SECONDS)\b',line))
        service=body(raw,'rpi5_watchdog_service_unlocked(bool healthy)')
        wrapper=body((p.ROOT/'pexpert/arm/rpi5_pcie_watchdog_owner.inc').read_text(),'pe_rpi5_watchdog_timer_tick(bool healthy)')
        with tempfile.TemporaryDirectory(prefix='console-watchdog-') as directory:
            out=Path(directory)
            (out/'actual_watchdog_globals.inc').write_text(defines+'\n'+declarations)
            (out/'actual_watchdog_service.inc').write_text('static void rpi5_watchdog_service_unlocked(bool healthy)'+service+'\nstatic void pe_rpi5_watchdog_timer_tick(bool healthy)'+wrapper)
            result=subprocess.run(['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                '-I',str(p.ROOT),'-I',str(out),str(Path(__file__).with_name('console_record_watchdog_host.c')),'-o',str(out/'host')],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([out/'host'],capture_output=True,text=True,timeout=30)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(0,'CONSOLE_WATCHDOG PASS ACTUAL_SERVICE_GATE IRQ_UNARMED_MISSING_OWNER_NO_FEED EPOCH_UNCHANGED MAX3 NO_HARDWARE\n',''))

    def test_exact_transform_and_preserved_exception_deadline_bodies(self):
        for name,source,transform,flags,cwd in units():
            del flags,cwd
            transformed=transform(source.read_text())
            with self.assertRaises(ValueError,msg=name):transform(source.read_text()+' ')
            self.assertTrue(transformed)
        normal=p.kprintf(p.KPRINTF.read_text())
        self.assertLess(normal.index('rpi5_console_kprintf_record(fmt, listp)'),normal.index('state = ml_set_interrupts_enabled(FALSE)'))
        original=p.KPRINTF.read_text();a=original.index('\t\t/*\n\t\t * Spin');b=original.index('\t\tva_end(listp);')
        self.assertIn(original[a:b],normal)
        policy=p.policy(p.POLICY.read_text())
        self.assertEqual(function(policy,'rpi5_restart_diagnostic_reset'),function(p.POLICY.read_text(),'rpi5_restart_diagnostic_reset'))
        fiq=p.fiq(p.FIQ.read_text())
        self.assertEqual(function(fiq,'pe_rpi5_watchdog_enable_terminal'),function(p.FIQ.read_text(),'pe_rpi5_watchdog_enable_terminal'))
        self.assertEqual(fiq.count('rpi5_terminal_console_thread_owner()'),1)
        start=function(p.sleh(p.SLEH.read_text()),'rpi5_terminal_watchdog_start')
        self.assertLess(start.index('os_atomic_store(&rpi5_terminal_console_call_armed, true, release);'),
            start.index('thread_call_enter_delayed(rpi5_terminal_watchdog_call, deadline);'))
        source=(p.ROOT/'osfmk/kern/thread_call.c').read_text()
        self.assertIn('return thread_call_enter_delayed_internal(call, NULL, 0, 0, deadline, 0, 0);',source)
        self.assertIn('Returns TRUE if the call was\n *\talready on a queue.',source)

    def test_actual_ring_printbuf_dispatch_concurrency_irq_recursion_and_callout(self):
        with tempfile.TemporaryDirectory(prefix='console-record-native-') as directory:
            out=Path(directory)
            for name,data in generated_native().items():(out/name).write_text(data)
            binary=out/'host'
            command=['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                '-Wno-unknown-pragmas','-fsanitize=address,undefined','-pthread','-I',str(p.ROOT),'-I',str(out),
                str(Path(__file__).with_name('console_record_host.c')),'-o',str(binary)]
            result=subprocess.run(command,capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([binary],capture_output=True,text=True,timeout=30)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(0,
                'CONSOLE_RECORD PASS ACTUAL_RING_PRINTBUF_DISPATCH HOST_ONLY_MMIO_FORMATTER_CLOCK NO_HARDWARE\n',''))

    def test_actual_six_a76_owner_tus_and_new_leaf_relocations(self):
        from tools.rpi5.check_apple_pthread_kernel_contract import MachO
        with tempfile.TemporaryDirectory(prefix='console-record-a76-') as directory:
            out=Path(directory)
            for name,source,transform,flags,cwd in units():
                generated=out/(name+'.c');generated.write_text(transform(source.read_text()));obj=out/(name+'.o')
                result=subprocess.run([*flags,'-c','-MD','-MF',str(out/(name+'.d')),str(generated),'-o',str(obj)],
                    cwd=cwd,capture_output=True,text=True,timeout=120)
                self.assertEqual(result.returncode,0,name+': '+result.stderr[-6000:])
                m=MachO(obj)
                if name=='console':
                    for symbol in ('_rpi5_console_kprintf_record','_rpi5_console_write_record'):
                        self.assertIn(symbol,m.names)
                    calls={r[2] for r in m.function('_rpi5_console_kprintf_record')['relocations']}
                    self.assertIn('___doprnt',calls)
                if name=='kprintf':
                    calls={r[2] for r in m.function('_kprintf')['relocations']}
                    self.assertIn('_rpi5_console_kprintf_record',calls)
                if name=='policy':
                    ready={r[2] for r in m.function('_rpi5_restart_diagnostic_ready')['relocations']}
                    self.assertIn('_rpi5_console_write_record',ready);self.assertNotIn('_rpi5_restart_diag_uart',ready)
                    reset={r[2] for r in m.function('_rpi5_restart_diagnostic_reset')['relocations']}
                    self.assertIn('_rpi5_restart_diag_uart',reset);self.assertNotIn('_console_write',reset)
                if name=='serial':
                    undefined=subprocess.check_output(['xcrun','nm','-ju',obj],text=True)
                    self.assertNotIn('___atomic',undefined)
                    result=subprocess.run([*flags,'-S',str(generated),'-o',str(out/'serial.s')],cwd=cwd,capture_output=True,text=True,timeout=120)
                    self.assertEqual(result.returncode,0,result.stderr)
                    assembly=(out/'serial.s').read_text();self.assertRegex(assembly,r'\b(casa|casal|ldaxr)\b')

if __name__=='__main__':unittest.main()
