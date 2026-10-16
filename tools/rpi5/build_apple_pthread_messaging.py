#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Continue real message/reply-port/CPU/thread-exit provider closure privately."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / 'tools/rpi5/build_apple_pthread_mach_linkable.py'


def build():
    wrapper = WRAPPER.read_text()
    insertion = '''extra = {
        "prefix='apple-pthread-mach-linkable-'": "prefix='apple-pthread-messaging-'",
        "for name in ('mach_host', 'mach_port'):": "for name in ('mach_host', 'mach_port', 'task'):",
        "('mach_legacy', 'mach_port', 'mach_init')]": "('mach_legacy', 'mach_port', 'mach_init', 'mach_msg', 'mig_reply_port')]",
        "(thread, 'pthread-asm', assembly_flags),": """(thread, 'pthread-asm', assembly_flags),
                (ROOT / 'libsyscall/wrappers/init_cpu_capabilities.c', 'cpu-init', flags),
                (ROOT / 'libsyscall/os/x18.c', 'original-x18', flags),
                (ROOT / 'tools/rpi5/user/pthread_exit_runtime_calls.S', 'pthread-exit-traps', assembly_flags + ['-I', str(ROOT / 'libsyscall/custom')]),
                (ROOT / 'build/rpi5/apple-libplatform-main-candidate-20261013/src/simple/asl.c', 'platform-asl', flags),
                (ROOT / 'build/rpi5/apple-libplatform-main-candidate-20261013/src/simple/string_io.c', 'platform-string-io', flags),
                (ROOT / 'build/rpi5/apple-libplatform-main-candidate-20261013/src/simple/log_simple.c', 'platform-log-simple', flags),""",
        "if label in ('pthread-asm', 'mach-traps'):": "if label in ('pthread-asm', 'mach-traps', 'pthread-exit-traps'):",
        "profile='original-apple-mach-thread-and-libkernel-provider-linkable-v3'": "profile='original-apple-pthread-messaging-provider-inventory-v1'",
        "commands, headers, units, installations, migrations = [], {}, [], {}, []": """commands, headers, units, installations, migrations = [], {}, [], {}, []
    pins[str(ROOT / 'tools/rpi5/build_apple_pthread_mach_linkable.py')] = sha(ROOT / 'tools/rpi5/build_apple_pthread_mach_linkable.py')
    numbers = {'bsdthread_terminate':361, '__disable_threadsignal':331, '__pthread_markcancel':332, 'thread_selfid':372, 'workq_kernreturn':368}
    syscall_rows = (ROOT / 'bsd/kern/syscalls.master').read_text().splitlines()
    for name, number in numbers.items():
        if not any(row.split()[0] == str(number) and name + '(' in ''.join(row.split()) for row in syscall_rows if row.split() and row.split()[0].isdigit()):
            raise ValueError('Actual thread syscall number mismatch: ' + name)""",
    }
    for old, new in extra.items():
        if raw.count(old) != 1: raise ValueError('Exact messaging source derivation changed')
        raw = raw.replace(old, new)
    scope = {'''
    if wrapper.count('scope = {') != 1: raise ValueError('Frozen wrapper changed')
    wrapper = wrapper.replace('scope = {', insertion)
    scope = {'__name__': 'private_messaging_builder', '__file__': str(Path(__file__).resolve())}
    exec(compile(wrapper, str(WRAPPER), 'exec'), scope)
    return scope['build']()


if __name__ == '__main__': build()
