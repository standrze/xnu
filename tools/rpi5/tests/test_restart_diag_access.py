# SPDX-License-Identifier: BSD-2-Clause
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import restart_diag_access_profile as p
from tools.rpi5 import build_display_xnu_console as flags_helper

class RestartDiagnosticAccessTests(unittest.TestCase):
    def test_exact_original_owner_derivation_and_single_ready_hook(self):
        serial=p.SERIAL.read_text();fiq=p.FIQ.read_text()
        self.assertEqual(hashlib.sha256(serial.encode()).hexdigest(),p.SERIAL_SHA)
        self.assertEqual(hashlib.sha256(fiq.encode()).hexdigest(),p.FIQ_SHA)
        self.assertEqual(p.serial_source(serial).removesuffix('\n#include "pexpert/arm/rpi5_restart_diag_uart.inc"\n'),serial)
        restored=p.fiq_source(fiq).removeprefix('#include "pexpert/arm/rpi5_restart_diag_api.h"\n').removesuffix('\n#include "pexpert/arm/rpi5_restart_diag_pm.inc"\n')
        self.assertEqual(restored.replace('\n\t\trpi5_restart_diagnostic_boot_ready();','',1),fiq)
        self.assertEqual(restored.count('rpi5_restart_diagnostic_boot_ready();'),1)
        self.assertIn('#define RPI5_TERMINAL_WDOG_SECONDS 180U',restored)
        for fn,raw in ((p.serial_source,serial),(p.fiq_source,fiq)):
            with self.assertRaises(ValueError):fn(raw+' ')
        for path in p.sources():self.assertTrue(path.is_file())

    def test_actual_accessor_bodies_native_faults_and_hard_poll_limit(self):
        with tempfile.TemporaryDirectory(prefix='restart-diag-access-') as directory:
            binary=Path(directory)/'host'
            subprocess.run(['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-I',str(p.ROOT),str(Path(__file__).with_name('restart_diag_access_host.c')),
                '-o',str(binary)],check=True,capture_output=True,timeout=60)
            r=subprocess.run([binary],capture_output=True,text=True,timeout=30)
            self.assertEqual((r.returncode,r.stdout,r.stderr),(0,
                'RESTART_DIAG_ACCESS PASS ACTUAL_BODIES RAM_ONLY NO_PM_WRITES NO_CONSOLE_LOCKS RATE_BOUND_UNKNOWN\n',''))

    def test_no_console_irq_or_pm_write_path_in_new_accessors(self):
        uart=(p.ROOT/'pexpert/arm/rpi5_restart_diag_uart.inc').read_text()
        pm=(p.ROOT/'pexpert/arm/rpi5_restart_diag_pm.inc').read_text()
        for raw in (uart,pm):
            for forbidden in ('kprintf(', 'printf(', 'console_write(', 'uart_putc(',
                              'ml_set_interrupts_enabled(', 'lck_', 'rpi5_mmio_write32('):
                self.assertNotIn(forbidden,raw)
        self.assertEqual(uart.count('held->uartdr.raw ='),1)
        self.assertIn('rpi5_pcie_watchdog_gate_service',pm)
        self.assertNotIn('rpi5_pcie_watchdog_gate_claim',pm)
        self.assertNotIn('rpi5_wdog_deadline =',pm)
        self.assertIn('watchdog_rate_bound_proven = 0',pm)

    def test_actual_a76_whole_owner_tus_and_nominal_primary_source(self):
        self.assertEqual(hashlib.sha256(p.PRIMARY.read_bytes()).hexdigest(),p.PRIMARY_SHA)
        primary=p.PRIMARY.read_text()
        self.assertIn('#define PM_WDOG_TIME_SET\t\t0x000fffff',primary)
        self.assertIn('#define WDOG_TICKS_TO_SECS(x) ((x) >> 16)',primary)
        self.assertIn('return WDOG_TICKS_TO_SECS(ret & PM_WDOG_TIME_SET);',primary)
        from tools.rpi5 import check_apple_pthread_kernel_contract as audit_macho
        database=json.loads(flags_helper.DATABASE.read_text())
        serial=next(row for row in database if row['file']==str(p.SERIAL))
        fiq_manifest=json.loads((p.FIQ.parent/'manifest.json').read_text())
        fiq=next(row for row in fiq_manifest['commands'] if row['log'].endswith('/pe_fiq-compile.log'))
        with tempfile.TemporaryDirectory(prefix='restart-diag-owner-') as directory:
            out=Path(directory)
            rows=[('serial',p.SERIAL,serial['arguments'],Path(serial['directory']),p.serial_source),
                  ('fiq',p.FIQ,fiq['command'],Path(fiq['cwd']),p.fiq_source)]
            for label,original,command,cwd,derive in rows:
                source=out/(label+'.c');source.write_text(derive(original.read_text()))
                flags=flags_helper.compiler_flags(command,original)+['-I',str(p.ROOT)]
                obj=out/(label+'.o')
                compiled=subprocess.run([*flags,'-c',str(source),'-o',str(obj)],cwd=cwd,capture_output=True,text=True,timeout=90)
                self.assertEqual(compiled.returncode,0,compiled.stderr[-6000:])
                m=audit_macho.MachO(obj)
                symbol='_rpi5_restart_diag_uart' if label=='serial' else '_rpi5_restart_diag_snapshot'
                self.assertIn(symbol,m.names)
                calls=[r[2] for r in m.function(symbol)['relocations']]
                for name in calls:
                    if isinstance(name,str):
                        self.assertFalse(any(n in name for n in ('_kprintf','_printf','_console_write','_lck_','_ml_set_interrupts_enabled','_uart_putc')))
                if label=='fiq':self.assertIn('_rpi5_restart_diagnostic_boot_ready',subprocess.check_output(['xcrun','nm','-ju',obj],text=True))

if __name__=='__main__':unittest.main()
