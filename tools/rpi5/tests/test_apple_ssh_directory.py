# SPDX-License-Identifier: BSD-2-Clause
"""Current directory-family source/static/native evidence, never target execution."""
import copy
import json
from pathlib import Path
import re
import struct
import subprocess
import unittest
from tools.rpi5 import build_apple_ssh_directory as b
from tools.rpi5.tests.test_apple_pthread_startup_contract import validate_closure

PACKAGE=b.ROOT/'build/rpi5/apple-ssh-directory-5vnm2xih'
PIN='a31b1f23788746c51ba590d5a560eb61155618fb49ffcdf95af0142d1b359cd9'


def source_members(m):
    expected={str(b.BASE/'manifest.json'):b.BASE_SHA,str(Path(b.__file__).resolve()):b.sha(b.__file__)}
    original=json.loads((b.BASE/'manifest.json').read_text())
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
        for name,digest in original[key].items():
            if name in expected and expected[name]!=digest:raise ValueError('Source conflict')
            expected[name]=digest
    tool_paths={str(Path(subprocess.check_output(['xcrun','--find',n],text=True).strip()).resolve())
                for n in ('clang','ld','ar','llvm-objdump','nm')}
    tool_paths.update(str(Path(n).resolve()) for n in ('/usr/bin/perl','/usr/bin/xcrun'))
    tools={n:b.sha(n) for n in tool_paths}
    if tools!=m['tools_sha256']:raise ValueError('Exact tool membership differs')
    expected.update(tools)
    paths=(b.FLAGS,b.SYSCALLS,b.CLIENT,b.OLD,b.FRAGMENTS,b.HARNESS,b.ABI_SOURCE,
           b.ROOT/'libsyscall/xcodescripts/create-syscalls.pl',b.ROOT/'bsd/kern/syscalls.master',
           *(b.ROOT/'libsyscall/custom').iterdir(),b.ROOT/'libsyscall/Platforms/syscall.map',
           b.ROOT/'libsyscall/Platforms/MacOSX/arm64/syscall.map',*[b.LIBC/n for n in b.UNITS],
           b.LIBC/'gen/__dirent.h',b.LIBC/'gen/FreeBSD/telldir.h',b.ROOT/'bsd/sys/dirent_private.h')
    for p in paths:
        if p.is_file():expected[str(p)]=b.sha(p)
    if expected!=m['source_inputs_sha256']:raise ValueError('Source membership differs')


class AppleDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(b.sha(PACKAGE/'manifest.json'),PIN)
        self.m=json.loads((PACKAGE/'manifest.json').read_text())

    def test_source_header_output_tool_membership_and_mutations(self):
        source_members(self.m);validate_closure(PACKAGE,self.m)
        for group in ('source_inputs_sha256','headers_sha256','generated_sha256','tools_sha256'):
            for mutation in ('omit','wrong'):
                altered=copy.deepcopy(self.m);name=next(iter(altered[group]))
                if mutation=='omit':altered[group].pop(name)
                else:altered[group][name]='0'*64
                with self.subTest(group=group,mutation=mutation),self.assertRaises(ValueError):
                    source_members(altered);validate_closure(PACKAGE,altered)
        for record in self.m['dependency_records'].values():
            self.assertEqual(record['scanned_sha256'],record['consumed_sha256'])

    def test_exact_original_units_two_frees_and_offsetof_only(self):
        self.assertEqual(self.m['original_libc_commit'],b.LIBC_COMMIT)
        for n in b.UNITS:
            self.assertEqual((b.LIBC/n).read_bytes(),subprocess.check_output(['git','-C',b.LIBC,'show',b.LIBC_COMMIT+':'+n]))
        original=(b.LIBC/b.UNITS[0]).read_text()
        expected=original.replace('\t\tif (n < 0) {\n\t\t\tsaved_errno = errno;\n',
                                  '\t\tif (n < 0) {\n\t\t\tsaved_errno = errno;\n\t\t\tfree(buf);\n',1)
        expected=expected.replace('\tdirp->dd_buf = buf;','\tfree(dirp->dd_buf);\n\tdirp->dd_buf = buf;',1)
        self.assertEqual(Path(self.m['derived_opendir']).read_text(),expected)
        compat=(b.LIBC/'fbsdcompat/_fbsd_compat_.h').read_text()
        self.assertEqual(Path(self.m['derived_compat_header']).read_text(),compat.replace(
            '(unsigned long)&((struct dirent *)0)->d_name','(unsigned long)__builtin_offsetof(struct dirent, d_name)',1))
        for function,text in ((b.checked_opendir,original),(b.checked_compat,compat)):
            with self.assertRaises(ValueError):function(function(text))
        for n in b.UNITS:
            row=next(c for c in self.m['commands'] if c['stdout'].endswith('/'+Path(n).stem+'-compile.stdout'))
            expected_source=self.m['derived_opendir'] if n==b.UNITS[0] else str(b.LIBC/n)
            self.assertIn(expected_source,row['command']);self.assertIn('-mcpu=cortex-a76',row['command'])
            self.assertFalse(any('fixture_' in word or 'sanitize' in word for word in row['command']))
            self.assertIn(str(b.ROOT/'bsd/sys/dirent_private.h'),self.m['dependency_records'][Path(n).stem]['consumed_sha256'])

    def test_actual_client_sdk_directory_abi_identical(self):
        values=[136,8,0,8,16,24,32,40,56,64,128,64,64,1048,8,0,8,16,18,20,21,1024]
        expected=struct.pack('<22Q',*values)
        self.assertEqual(b.const_bytes(PACKAGE/'client-dir-abi.o'),expected)
        self.assertEqual(b.const_bytes(PACKAGE/'provider-dir-abi.o'),expected)
        self.assertEqual(self.m['directory_abi'],values)
        client=json.loads(b.CLIENT.read_text())
        original=next(c['command'] for c in client['commands'] if c['stdout'].endswith('/086-ssh-compile.stdout'))
        row=next(c['command'] for c in self.m['commands'] if c['stdout'].endswith('/client-dir-abi-compile.stdout'))
        self.assertEqual(row[:row.index('-MD')],original[:original.index('-MD')])
        provider=self.m['dependency_records']['provider-dir-abi']['consumed_sha256']
        consumer=self.m['dependency_records']['client-dir-abi']['consumed_sha256']
        self.assertIn(str(b.LIBC/'include/dirent.h'),provider)
        self.assertNotIn(str(b.LIBC/'include/dirent.h'),consumer)
        sdk=Path(original[original.index('-isysroot')+1])
        self.assertIn(str((sdk/'usr/include/dirent.h').resolve()),consumer)

    def test_actual_forced_16_owners_no_undefined_and_original_trap_policy(self):
        target=PACKAGE/'NOT_RUN_directory_contract'
        self.assertEqual(b.prepare_pid1.inspect(target.read_bytes()),self.m['static_inspection'])
        self.assertEqual(subprocess.check_output(['xcrun','nm','-ju',target],text=True),'')
        self.assertEqual(self.m['forced_apis'],list(b.FORCE));self.assertEqual(len(b.FORCE),16)
        mapping=(PACKAGE/'contract-link.map').read_text();self.assertNotRegex(mapping,r'fixture_|__asan|__ubsan')
        for symbol in b.FORCE:
            self.assertTrue(self.m['live_symbol_owners'][symbol].startswith(self.m['target_archive']+'('))
        self.assertTrue(self.m['live_symbol_owners']['_pthread_mutex_lock'].endswith('(pthread-pthread_mutex.o)'))
        for name in ('_open$NOCANCEL','_openat$NOCANCEL'):
            self.assertTrue(self.m['live_symbol_owners'][name].endswith('/libapple-ssh-nocancel-io.a(open-base.o)'))
        self.assertTrue(self.m['live_symbol_owners']['_cerror_nocancel'].endswith('/private-abi-runtime.a(2-errno.o)'))
        raw=(PACKAGE/'generated/___getdirentries64.s').read_text()
        self.assertIn('SYSCALL_NONAME(getdirentries64, 4, cerror_nocancel)',raw)
        self.assertIn('ZERO_EXTEND(2)',raw)
        dis=(PACKAGE/'getdirentries64-disassembly.stdout').read_text()
        self.assertIn('mov\tx16, #0x158',dis);self.assertIn('svc\t#0x80',dis)
        self.assertEqual(subprocess.check_output(['xcrun','nm','-ju',PACKAGE/'getdirentries64.o'],text=True),'_cerror_nocancel\n')
        self.assertRegex((b.ROOT/'bsd/kern/syscalls.master').read_text(),r'(?m)^344\s+[^\n]*getdirentries64\(')

    def test_full_client_41_to40_and_no_legacy_dir_owners(self):
        base=json.loads((b.BASE/'manifest.json').read_text())
        row=next(c for c in self.m['commands'] if c['stdout'].endswith('/target-link.stdout'))
        expected=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
        expected[expected.index(str(b.OLD))]=self.m['private_archive']
        expected[expected.index('-o')+1]=str(PACKAGE/'NOT_RUN_ssh')
        expected[expected.index('-map')+1]=str(PACKAGE/'target-link.map')
        expected.extend([str(b.FRAGMENTS),self.m['target_archive']]);self.assertEqual(row['command'],expected)
        imports=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',Path(row['stderr']).read_text(),re.M)))
        self.assertEqual(imports,self.m['target_missing_symbols']);self.assertEqual(len(imports),40)
        self.assertEqual(set(base['target_missing_symbols'])-set(imports),{'_readdir_r'})
        self.assertEqual(set(imports)-set(base['target_missing_symbols']),set())
        self.assertEqual(self.m['target_duplicate_symbols'],[])
        original=subprocess.check_output(['xcrun','ar','t',b.OLD],text=True).splitlines()
        actual=subprocess.check_output(['xcrun','ar','t',self.m['private_archive']],text=True).splitlines()
        self.assertEqual(actual,[n for n in original if n not in b.MEMBERS])
        for name in actual:
            if name=='__.SYMDEF SORTED':continue
            self.assertEqual(subprocess.check_output(['xcrun','ar','p',b.OLD,name]),
                             subprocess.check_output(['xcrun','ar','p',self.m['private_archive'],name]))
        for key in ('target_executed','target_directory_syscall_executed','full_client_qualified','provider_stubs','accepted_runtime_modified'):
            self.assertIs(self.m[key],False)

    def test_native_original_negative_and_corrected_whole_family(self):
        original=PACKAGE/'original-directory-host';derived=PACKAGE/'directory-host'
        failure=subprocess.run([original],capture_output=True,text=True,timeout=30)
        self.assertNotEqual(failure.returncode,0);self.assertIn('member access within null pointer',failure.stderr)
        self.assertIn('readdir.c:167',failure.stderr)
        cases=((original,['original-leaks'],0,'APPLE_DIRECTORY LEAKS=2 ORIGINAL_ERRNO_PRESERVED\n'),
               (original,['leak-oracle'],38,''),(derived,[],0,b.EXPECTED),
               (derived,['bad-expectation'],37,''),(derived,['leak-oracle'],0,'APPLE_DIRECTORY LEAKS=0 ORIGINAL_ERRNO_PRESERVED\n'),
               (derived,['original-leaks'],38,''))
        for program,args,status,output in cases:
            with self.subTest(program=program.name,args=args):
                result=subprocess.run([program,*args],capture_output=True,text=True,timeout=30)
                self.assertEqual((result.returncode,result.stdout,result.stderr),(status,output,''))


if __name__=='__main__':unittest.main()
