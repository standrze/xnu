# SPDX-License-Identifier: BSD-2-Clause
"""Exact, opt-in normal-console serialization; never edits accepted sources."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KPRINTF = ROOT/'pexpert/arm/pe_kprintf.c'
CONSOLE = ROOT/'build/rpi5/display-xnu-console-5cd94fg_/serial_console.c'
SERIAL = ROOT/'build/rpi5/display-restart-diagnostic-gb38kpad/pe_serial.c'
SLEH = ROOT/'osfmk/arm64/sleh.c'
FIQ = ROOT/'build/rpi5/display-restart-diagnostic-gb38kpad/pe_fiq.c'
POLICY = ROOT/'loader/rpi5/psci_restart_diagnostic.c'
INIT = ROOT/'build/rpi5/init-shutdown-late-framed-5roryvz5'
INIT_SHA = '5c17c8e1e496a55b6f9e459e0e1482ea9a74176c1093ce331bef95540b62ec31'
OLD_READY = 'RPI5XNU:INIT:SHUTDOWN_READY SIGTERM_BLOCKED POLLED NO_RESPAWN_AFTER_OBSERVATION'
READY = 'RPI5XNU:INIT:SHUTDOWN_READY MASKED POLLED STOP_LATCH'
PINS = {
    KPRINTF: '435665a3aa8147297abaa1731b97eed8c5e516e42d20290c2b952843e194d956',
    CONSOLE: '88617b4fb2913da99004d173a17d7e6eb39801faf040a5002b67d5879585c6f4',
    SERIAL: 'f5c5f5fb410a005ba24541473855dd3209e7ab1edeabf5aaab86b6cda23fa055',
    SLEH: 'fc03874c1472da789a4c28c6a577f171e1fe4dead4cbdf3bca6f319e275e7be1',
    POLICY: '79c0aa940e027f7753a5b625c0fca06dca992e90c8ebacd51cf5549835e6ca87',
    FIQ: 'ab803798b60f8558e25315b069e977c67c4f37d7e76688df4ec8f14303d43b6b',
}

def once(raw, before, after):
    if raw.count(before) != 1: raise ValueError('Exact console owner boundary: '+before[:70])
    return raw.replace(before, after, 1)

def checked(raw, path):
    if hashlib.sha256(raw.encode()).hexdigest() != PINS[path]: raise ValueError('Frozen console input changed')
    return raw

def kprintf(raw):
    raw = checked(raw, KPRINTF)
    raw = once(raw, '#include <stdarg.h>', '#include <stdarg.h>\n#include "osfmk/console/rpi5_console_records.h"')
    raw = once(raw, '\t\tva_copy(listp2, listp);', '\t\tva_copy(listp2, listp);\n\t\tif (rpi5_console_kprintf_record(fmt, listp)) goto rpi5_record_done;')
    return once(raw, '\t\tml_set_interrupts_enabled(state);\n\t\tva_end(listp);',
        '\t\tml_set_interrupts_enabled(state);\nrpi5_record_done:\n\t\tva_end(listp);')

def console(raw):
    raw = checked(raw, CONSOLE)
    raw = once(raw, '#include <kern/thread.h>', '#include <kern/thread.h>\n#include <kern/debug.h>')
    raw = once(raw, '/**\n * Attempt to drain the console ring buffer if no other CPUs are already doing',
        'extern int __doprnt(const char *, va_list, void (*)(int, void *), void *, int, int);\n'
        '#include "osfmk/console/rpi5_console_records.inc"\n\n/**\n * Attempt to drain the console ring buffer if no other CPUs are already doing')
    return once(raw, '\t\t\t_cnputs(flush_buf, nchars_out, console_suspended);',
        '\t\t\tif (!in_debugger) __atomic_store_n(&rpi5_console_drain_thread, (uintptr_t)current_thread(), __ATOMIC_RELEASE);\n'
        '\t\t\t_cnputs(flush_buf, nchars_out, console_suspended);\n'
        '\t\t\tif (!in_debugger) __atomic_store_n(&rpi5_console_drain_thread, 0, __ATOMIC_RELEASE);')

def serial(raw):
    raw = checked(raw, SERIAL)
    raw = once(raw, 'static inline void\nuart_putc_device(',
        '#include "pexpert/arm/rpi5_console_uart.inc"\n\nstatic inline void\nuart_putc_device(')
    raw = once(raw, '\twhile (!fns->transmit_ready()) {\n\t\tif (irq_available_and_ready(fns) && !poll) {',
        '\twhile (!rpi5_console_uart_try(c, fns)) {\n\t\tif (irq_available_and_ready(fns) && !poll) {')
    return once(raw, '\tfns->transmit_data((uint8_t)c);\n}', '}')

def sources():
    return [Path(__file__).resolve(), ROOT/'osfmk/console/rpi5_console_records.h',
        ROOT/'osfmk/console/rpi5_console_records.inc', ROOT/'pexpert/arm/rpi5_console_uart.inc',
        ROOT/'tools/rpi5/tests/console_record_host.c', ROOT/'tools/rpi5/tests/console_record_watchdog_host.c',
        ROOT/'tools/rpi5/tests/test_console_records.py']

def init_source():
    # The whole immutable policy remains, including actual mask and pending
    # checks before every report; only its human-readable state label shrinks.
    import json
    if hashlib.sha256((INIT/'manifest.json').read_bytes()).hexdigest()!=INIT_SHA:raise ValueError('Exact PID1 parent')
    m=json.loads((INIT/'manifest.json').read_text());source=INIT/'init.c'
    if hashlib.sha256(source.read_bytes()).hexdigest()!=m['generated_sha256'][str(source)]:raise ValueError('Actual PID1 source')
    return once(source.read_text(), OLD_READY, READY)

def compiler_units():
    import json
    from . import build_display_xnu_console as compiler
    db=json.loads(compiler.DATABASE.read_text())
    diagnostic=json.loads((SERIAL.parent/'manifest.json').read_text())
    rows=[]
    for name,source,transform,original in (
        ('kprintf',KPRINTF,kprintf,KPRINTF),('console',CONSOLE,console,ROOT/'osfmk/console/serial_console.c'),
        ('serial',SERIAL,serial,None),('sleh',SLEH,sleh,SLEH),('watchdog',FIQ,fiq,None),('policy',POLICY,policy,None)):
        if original:
            rec=next(r for r in db if r['file']==str(original));args=rec['arguments'];cwd=Path(rec['directory'])
        else:
            rec=next(r for r in diagnostic['commands'] if r['label']==name+'-compile')
            args=rec['command'];cwd=Path(rec['cwd']);original=source
        flags=compiler.compiler_flags(args,original)
        rows.append((name,source,transform,flags+['-DRPI5_CONSOLE_RECORDS=1','-I',str(ROOT),'-iquote',str(source.parent)],cwd))
    return rows

def policy(raw):
    raw = checked(raw, POLICY)
    raw = once(raw, '#include "pexpert/arm/rpi5_restart_diag_api.h"',
        '#include "pexpert/arm/rpi5_restart_diag_api.h"\n#include "osfmk/console/rpi5_console_records.h"')
    # ONLY boot readiness becomes a normal admitted console record. The entire
    # post-halt snapshot, PRE_SMC and returned-call path remains byte-for-byte.
    return once(raw, 'return rpi5_restart_diag_uart(ready, sizeof(ready)-1) == 0;',
        'return rpi5_console_write_record(ready, sizeof(ready)-1);')

def sleh(raw):
    raw = checked(raw, SLEH)
    raw = once(raw, 'static thread_call_t rpi5_terminal_watchdog_call;',
        'static thread_call_t rpi5_terminal_watchdog_call;\n'
        'static _Atomic bool rpi5_terminal_console_call_armed;\n'
        'bool rpi5_terminal_console_thread_owner(void);\n'
        '/* A completed enter_delayed queues the actual allocated call; its\n'
        ' * boolean result means previously queued, NOT success/failure. */\n'
        'bool rpi5_terminal_console_thread_owner(void)\n{\n'
        '\treturn os_atomic_load(&rpi5_terminal_watchdog_enabled, acquire) &&\n'
        '\t    os_atomic_load(&rpi5_terminal_console_call_armed, acquire) &&\n'
        '\t    rpi5_terminal_watchdog_call != NULL && current_thread() != THREAD_NULL &&\n'
        '\t    ml_get_interrupts_enabled() && !ml_at_interrupt_context() &&\n'
        '\t    get_preemption_level() == 0;\n}\n')
    raw = once(raw, '\tif (!pe_rpi5_watchdog_terminal_active()) {',
        '\tif (!rpi5_terminal_console_thread_owner() || !pe_rpi5_watchdog_terminal_active()) {')
    raw = once(raw, '\tthread_call_enter_delayed(rpi5_terminal_watchdog_call, deadline);\n\treturn true;',
        '/* Publish the owner before the call becomes runnable.  The call API\n'
        ' * has no enqueue-failure result: TRUE means already queued. */\n'
        '\tos_atomic_store(&rpi5_terminal_console_call_armed, true, release);\n'
        '\tthread_call_enter_delayed(rpi5_terminal_watchdog_call, deadline);\n\treturn true;')
    return once(raw, '\t\tif (cdp->cpu_number == 0 &&\n\t\t    !os_atomic_load(&rpi5_gate3_soak_enabled, acquire)) {',
        '\t\tif (cdp->cpu_number == 0 &&\n\t\t    !os_atomic_load(&rpi5_gate3_soak_enabled, acquire) &&\n'
        '\t\t    !os_atomic_load(&rpi5_terminal_watchdog_enabled, acquire)) {')

def fiq(raw):
    # The immutable diagnostic parent is also pinned by the full builder.
    # Keep the entire deadline establishment/reload/report/counter body intact.
    raw = checked(raw, FIQ)
    raw = '#include <stdbool.h>\nextern bool rpi5_terminal_console_thread_owner(void);\n'+raw
    return once(raw, '{\n\tif (rpi5_pm_base == 0 || rpi5_wdog_deadline == 0 ||\n\t    (rpi5_wdog_soak_seconds == 0 && !rpi5_wdog_terminal_enabled &&',
        '{\n\t/* Terminal mode never publishes from IRQ, early start gap, or a\n'
        '\t * missing callout. Refusal never moves its deadline or feeds PM. */\n'
        '\tif (rpi5_wdog_terminal_enabled && !rpi5_terminal_console_thread_owner()) return;\n'
        '\tif (rpi5_pm_base == 0 || rpi5_wdog_deadline == 0 ||\n\t    (rpi5_wdog_soak_seconds == 0 && !rpi5_wdog_terminal_enabled &&')
