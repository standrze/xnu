# SPDX-License-Identifier: BSD-2-Clause
"""Source/native/static spawn qualification, never target process execution."""
import copy
import json
from pathlib import Path
import re
import subprocess
import unittest
from tools.rpi5 import check_apple_ssh_spawn_contract as b
from tools.rpi5.tests.test_apple_pthread_startup_contract import validate_closure

PACKAGE=b.ROOT/'build/rpi5/apple-ssh-spawn-contract-o1r3nnno'
PIN='08e28e13a755e593ce315df0b0454b53339455675aedd81b05006ef6f85b09eb'


def validate_members(report):
    expected={str(Path(b.__file__).resolve()):b.sha(b.__file__),str(b.HARNESS):b.sha(b.HARNESS),
              str(b.TRAP):b.sha(b.TRAP),str(b.SPEC):b.sha(b.SPEC),
              str(Path(b.prepare_pid1.__file__).resolve()):b.sha(b.prepare_pid1.__file__)}
    for directory,digest in ((b.audit.BASE,b.audit.BASE_SHA),(b.INVENTORY,b.INVENTORY_SHA)):
        path=directory/'manifest.json'
        if b.sha(path)!=digest:raise ValueError('Exact predecessor changed')
        expected[str(path)]=digest;parent=json.loads(path.read_text())
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for name,h in parent[key].items():
                if name in expected and expected[name]!=h:raise ValueError('Parent conflict')
                expected[name]=h
    for path in (b.LIBC/'xcodescripts/variants.xcconfig',b.LIBC/'xcodescripts/libc.xcconfig',
                 b.LIBC/'stdlib/FreeBSD/system.3',b.ROOT/'libsyscall/Platforms/syscall.map',
                 b.ROOT/'experiments/darwin-container/userland/build_apple_runtime.py'):
        expected[str(path)]=b.sha(path)
    if expected!=report['source_inputs_sha256']:raise ValueError('Exact source membership differs')


class AppleSpawnContractTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(b.sha(PACKAGE/'manifest.json'),PIN)
        self.m=json.loads((PACKAGE/'manifest.json').read_text())

    def test_complete_input_generated_and_actual_header_closure(self):
        validate_members(self.m);validate_closure(PACKAGE,self.m)
        for record in self.m['dependency_records'].values():
            self.assertEqual(record['scanned_sha256'],record['consumed_sha256'])
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            altered=copy.deepcopy(self.m);altered[key].pop(next(iter(altered[key])))
            with self.assertRaises(ValueError):validate_members(altered);validate_closure(PACKAGE,altered)
            altered=copy.deepcopy(self.m);altered[key][next(iter(altered[key]))]='0'*64
            with self.assertRaises(ValueError):validate_members(altered);validate_closure(PACKAGE,altered)
        inventory=json.loads((b.INVENTORY/'manifest.json').read_text())
        for name,source in inventory['header_copies'].items():
            self.assertEqual((b.INVENTORY/'include'/name).read_bytes(),(b.ROOT/source).read_bytes())

    def test_exact_derived_error_repair_and_original_negative(self):
        c=self.m['system_errno_correction'];original=Path(c['original']).read_text()
        self.assertEqual(c['exact_old'],b.OLD);self.assertEqual(c['exact_new'],b.NEW)
        self.assertEqual(original.count(b.OLD),1)
        self.assertEqual(Path(c['derived']).read_text(),original.replace(b.OLD,b.NEW))
        self.assertEqual(b.NEW.replace('\t\terrno = err;\n',''),b.OLD)
        self.assertEqual(b.sha(c['original']),c['original_sha256'])
        self.assertEqual(b.sha(c['derived']),c['derived_sha256'])
        for executable,arg,status,stdout in (
            ('spawn-original-host','original-errno',0,b.ORIGINAL_EXPECTED),
            ('spawn-original-host','require-errno',32,''),
            ('spawn-host','require-errno',0,''),
            ('spawn-host','original-errno',32,'')):
            result=subprocess.run([PACKAGE/executable,arg],capture_output=True,text=True,timeout=15)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(status,stdout,''))
        self.assertFalse(self.m['original_units_unchanged'])
        self.assertTrue(self.m['original_spawn_and_trap_bodies_unchanged'])
        self.assertIn('errno=ENOMEM', (b.HARNESS.read_text().replace(' ','')))

    def test_native_api_descriptor_signal_restore_concurrency_and_oracle_negative(self):
        result=subprocess.run([PACKAGE/'spawn-host'],capture_output=True,text=True,timeout=15)
        self.assertEqual((result.returncode,result.stdout,result.stderr),(0,b.EXPECTED,''))
        bad=subprocess.run([PACKAGE/'spawn-host','bad-expected'],capture_output=True,text=True,timeout=15)
        self.assertEqual((bad.returncode,bad.stderr),(31,''))
        for label in ('host-system-original','host-system_errno_checked','host-posix_spawn','host-harness'):
            command=next(c['command'] for c in self.m['commands'] if c['stdout'].endswith('/'+label+'-compile.stdout'))
            self.assertIn('-fsanitize=address,undefined',command)
            self.assertIn('-fno-sanitize-recover=undefined',command)
            if label!='host-harness':self.assertIn(str(PACKAGE/'native_names.h'),command)
        for index in range(3):
            undefined=(PACKAGE/('host-undefined-'+str(index)+'.stdout')).read_text().splitlines()
            for name in b.CALLBACKS:self.assertNotIn('_'+name,undefined)
            exports=re.findall(r'^[0-9a-f]+ [A-Z] (_\S+)$',(PACKAGE/('host-defined-'+str(index)+'.stdout')).read_text(),re.M)
            self.assertTrue(exports)
            self.assertTrue(all(n.startswith('_fixture_') or n=='____asan_globals_registered' for n in exports))

    def test_full_client_delta_static_owners_and_original_cancellation_traps(self):
        m=self.m
        self.assertEqual(m['closed_symbols'],['_system']);self.assertEqual(len(m['target_missing_symbols']),41)
        self.assertEqual(m['newly_reachable_symbols'],[]);self.assertEqual(m['target_duplicate_symbols'],[])
        base=json.loads((b.audit.BASE/'manifest.json').read_text())
        link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
        link[link.index('-o')+1]=str(PACKAGE/'NOT_RUN_ssh');link[link.index('-map')+1]=str(PACKAGE/'target.map')
        link.append(m['target_archive'])
        self.assertEqual(link,next(c['command'] for c in m['commands'] if c['stdout'].endswith('/target-link.stdout')))
        members=subprocess.check_output(['xcrun','ar','t',m['target_archive']],text=True).splitlines()
        self.assertEqual(members,['__.SYMDEF SORTED','system.o','posix_spawn.o','spawn-trap.o'])
        target=Path(m['target']);self.assertEqual(b.sha(target),m['target_sha256'])
        self.assertEqual(subprocess.check_output(['xcrun','nm','-ju',target],text=True),'')
        self.assertEqual(b.prepare_pid1.inspect(target.read_bytes()),m['static_inspection'])
        self.assertEqual(set(m['live_symbol_owners']),set(b.FORCE))
        for symbol,owner in m['live_symbol_owners'].items():
            member='system.o' if symbol=='_system' else 'spawn-trap.o' if symbol=='___posix_spawn' else 'posix_spawn.o'
            self.assertEqual(owner,m['target_archive']+'('+member+')')
        dis=(PACKAGE/'target-disassembly.stdout').read_text()
        trap=dis.split('(spawn-trap.o):',1)[1]
        self.assertRegex(trap,r'mov\s+x16, #0xf4\b');self.assertEqual(trap.count('svc\t#0x80'),1)
        self.assertIn('ARM64_RELOC_BRANCH26\t_cerror\n',trap)
        self.assertNotIn('_cerror_nocancel',trap)
        system=dis.split('(system.o):',1)[1].split('(posix_spawn.o):',1)[0]
        self.assertIn('ARM64_RELOC_BRANCH26\t_pthread_testcancel\n',system)
        self.assertIn('ARM64_RELOC_BRANCH26\t_wait4\n',system)
        syscall_map=(b.ROOT/'libsyscall/Platforms/syscall.map').read_text()
        self.assertRegex(syscall_map,r'(?m)^_wait4\s+___wait4_nocancel')
        mapping=(PACKAGE/'contract.map').read_text()
        self.assertRegex(mapping,r'(?m)^0x[^\n]+\[\s*3\]\s+_cerror$')
        self.assertIn('private-abi-runtime.a(2-errno.o)',mapping)
        self.assertNotRegex(mapping,r'fixture_|__asan|__ubsan')
        compile_cmd=next(c['command'] for c in m['commands'] if c['stdout'].endswith('/system-compile.stdout'))
        self.assertIn('-DVARIANT_CANCELABLE',compile_cmd);self.assertIn('-D__DARWIN_NON_CANCELABLE=0',compile_cmd)
        self.assertNotIn(str(PACKAGE/'native_names.h'),compile_cmd)

    def test_unqualified_popen_and_execution_limits_remain_explicit(self):
        m=self.m;inventory=json.loads((b.INVENTORY/'manifest.json').read_text())
        self.assertEqual(inventory['compile_failures'],{})
        self.assertEqual(inventory['newly_reachable_symbols'],['___posix_spawn','_fwide'])
        self.assertEqual(len(inventory['target_missing_symbols']),42)
        self.assertIn('Libc-167',m['modern_popen_excluded_reason'])
        self.assertIn('_popen',m['target_missing_symbols']);self.assertIn('_pclose',m['target_missing_symbols'])
        self.assertNotIn('_fwide',m['target_missing_symbols'])
        for key in ('target_executed','full_client_qualified','provider_stubs','accepted_runtime_modified'):
            self.assertIs(m[key],False)
        self.assertIs(m['original_openssh_config_unchanged'],True)
        self.assertIs(m['host_process_io_signal_boundaries_are_doubles'],True)


if __name__=='__main__':unittest.main()
