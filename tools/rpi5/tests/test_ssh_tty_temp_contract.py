# SPDX-License-Identifier: BSD-2-Clause
"""Real current Apple path/TTY providers, not SSH or target execution."""
import copy
import json
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5 import check_apple_ssh_tty_temp_contract as b
from tools.rpi5.tests.test_apple_pthread_startup_contract import validate_closure

PACKAGE=b.ROOT/'build/rpi5/apple-ssh-tty-temp-contract-bicg15ou'
PIN='9f55971e5feb4d9b25a48419a279f19ff9c2aa5d18003eb79dd1d3abb92552df'


def validate_source_members(report):
    expected={str(Path(b.__file__).resolve()):b.sha(b.__file__),str(b.HARNESS):b.sha(b.HARNESS),
              str(Path(b.prepare_pid1.__file__).resolve()):b.sha(b.prepare_pid1.__file__)}
    for directory,pin in ((b.BASE,b.BASE_SHA),(b.NATIVE_LOCALE,b.NATIVE_SHA),(b.CLOCK,b.CLOCK_SHA),(b.IO,b.IO_SHA)):
        path=directory/'manifest.json'
        if b.sha(path)!=pin:raise ValueError('Parent manifest differs')
        expected[str(path)]=pin;parent=json.loads(path.read_text())
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for name,digest in parent.get(key,{}).items():
                if name in expected and expected[name]!=digest:raise ValueError('Parent conflict')
                expected[name]=digest
    for name in b.TRAPS:expected[str(b.GENERATED/name)]=b.sha(b.GENERATED/name)
    if report['source_inputs_sha256']!=expected:raise ValueError('Exact source membership differs')


class AppleTtyTempContractTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(b.sha(PACKAGE/'manifest.json'),PIN)
        self.report=json.loads((PACKAGE/'manifest.json').read_text())

    def test_actual_sources_headers_outputs_and_omission_negatives(self):
        validate_source_members(self.report);validate_closure(PACKAGE,self.report)
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            altered=copy.deepcopy(self.report);altered[key].pop(next(iter(altered[key])))
            with self.assertRaises(ValueError):
                validate_source_members(altered);validate_closure(PACKAGE,altered)
        altered=copy.deepcopy(self.report)
        altered['headers_sha256'][next(iter(altered['headers_sha256']))]='0'*64
        with self.assertRaises(ValueError):validate_closure(PACKAGE,altered)

    def test_full_original_client_delta_and_forced_static_owners(self):
        m=self.report
        self.assertEqual(m['closed_symbols'],['_devname_r','_mkdtemp','_readpassphrase','_statfs'])
        self.assertEqual(len(m['target_missing_symbols']),42)
        self.assertEqual(m['newly_reachable_symbols'],[]);self.assertEqual(m['target_duplicate_symbols'],[])
        for key in ('target_executed','full_client_qualified','host_terminal_or_filesystem_access','provider_stubs','accepted_runtime_modified'):
            self.assertIs(m[key],False)
        self.assertIs(m['original_openssh_config_unchanged'],True)
        precursor=json.loads((b.BASE/'manifest.json').read_text())
        old=list(next(c['command'] for c in precursor['commands'] if c['stdout'].endswith('/target-link.stdout')))
        self.assertEqual(old.pop(),precursor['target_archive'])
        old[old.index('-o')+1]=str(PACKAGE/'NOT_RUN_ssh');old[old.index('-map')+1]=str(PACKAGE/'target.map')
        old.append(m['target_archive'])
        self.assertEqual(old,next(c['command'] for c in m['commands'] if c['stdout'].endswith('/target-link.stdout')))
        target=Path(m['target']);self.assertEqual(b.sha(target),m['target_sha256'])
        self.assertEqual(b.prepare_pid1.inspect(target.read_bytes()),m['static_inspection'])
        self.assertEqual(subprocess.check_output(['xcrun','nm','-ju',target],text=True),'')
        self.assertEqual(set(m['live_symbol_owners']),set(b.FORCE))
        expected={'_mkdtemp':'mktemp.o','_readpassphrase':'readpassphrase.o','_devname_r':'devname.o',
                  '_statfs':'_statfs64.o','_fstatat':'_fstatat64.o','_mkdirat':'_mkdirat.o','_write$NOCANCEL':'___write_nocancel.o'}
        for symbol,name in expected.items():self.assertEqual(m['live_symbol_owners'][symbol],m['target_archive']+'('+name+')')
        dis=(PACKAGE/'target-disassembly.stdout').read_text()
        for filename,number in (('_fstatat64.o',470),('_mkdirat.o',475),('___write_nocancel.o',397),('_statfs64.o',345)):
            block=dis.split(str(PACKAGE/filename)+':',1)[1].split('file format mach-o arm64',1)[1]
            block=block.split('\n/Users/',1)[0]
            self.assertRegex(block,r'mov\s+x16, #'+hex(number)+r'\b')
            self.assertEqual(block.count('svc\t#0x80'),1)
            self.assertIn('ARM64_RELOC_BRANCH26\t_cerror_nocancel',block)
            self.assertNotIn('ARM64_RELOC_BRANCH26\t_cerror\n',block)
        mapping=(PACKAGE/'contract.map').read_text()
        self.assertIn('private-abi-runtime.a(2-errno.o)',mapping)
        self.assertRegex(mapping,r'(?m)^0x[^\n]+\[\s*3\]\s+_cerror_nocancel$')
        self.assertNotRegex(mapping,r'fixture_|__asan|__ubsan')

    def test_actual_native_path_tty_restore_and_device_boundaries(self):
        p=subprocess.run([PACKAGE/'tty-temp-host'],capture_output=True,text=True,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'')
        self.assertEqual(p.stdout,self.report['native_stdout'])
        bad=subprocess.run([PACKAGE/'tty-temp-host','bad-expected'],capture_output=True,text=True,timeout=15)
        self.assertEqual(bad.returncode,29)
        self.assertIn('TEMP=7 TTY=15 DEVICE=5 IO_SIGNAL_ENTROPY_DOUBLES',p.stdout)
        for source in ('mktemp','readpassphrase','devname'):
            row=next(c for c in self.report['commands'] if c['stdout'].endswith('/host-'+source+'-compile.stdout'))
            self.assertIn('-fsanitize=address,undefined',row['command'])
            self.assertIn('-fno-sanitize-recover=undefined',row['command'])
            self.assertIn(str(PACKAGE/'native_names.h'),row['command'])
            undefined=(PACKAGE/('host-'+source+'-undefined.stdout')).read_text().splitlines()
            for name in b.CALLBACKS:
                self.assertNotIn('_'+name,undefined);self.assertNotIn('_'+name+'$NOCANCEL',undefined)

    def test_unqualified_current_stdio_first_failure_is_not_hidden(self):
        first=b.ROOT/'build/rpi5/apple-ssh-stdio-audit-_hdujkup'
        m=json.loads((first/'manifest.json').read_text())
        self.assertEqual(m['compile_failures'],{'stdio/FreeBSD/vfprintf.c':'compile'})
        self.assertFalse(m['mixed_stdio_abi_qualified']);self.assertFalse(m['full_client_qualified'])
        self.assertFalse(m['accepted_runtime_modified']);self.assertFalse(m['target_executed'])
        self.assertEqual(len(m['target_missing_symbols']),52)
        errors=(first/'vfprintf-compile.stderr').read_text()
        self.assertIn("error: call to undeclared function 'os_log_send_and_compose'",errors)
        self.assertIn("error: use of undeclared identifier '_COMM_PAGE_ATM_DIAGNOSTIC_CONFIG'",errors)
        source=(b.audit.LIBC/'stdio/FreeBSD/vfprintf.c').read_text()
        self.assertIn('OS_CRASH_ENABLE_EXPERIMENTAL_LIBTRACE 1',source)
        self.assertIn('__printf_is_memory_read_only',source)
        self.assertEqual(m['target_duplicate_symbols'],[])


if __name__=='__main__':unittest.main()
