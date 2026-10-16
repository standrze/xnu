# SPDX-License-Identifier: BSD-2-Clause
"""Independent actual packet/startup linkage and narrow ABI/caps contracts.

Only host harnesses execute. The selected static Mach-O is never executed on
the Mac, and no result here establishes Pi pthreads, entropy or an SSH daemon.
"""
import copy
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess
import tempfile
import unittest
from tools.rpi5.check_apple_pthread_kernel_contract import MachO
from tools.rpi5.tests.test_apple_pthread_startup_contract import sha, validate_closure
from tools.rpi5 import prepare_pid1

ROOT=Path(__file__).resolve().parents[3]
PACKAGE=ROOT/'build/rpi5/apple-ssh-packet-pthread-iabcb1gr'
MANIFEST='b1ca5bec6b327284fd8df985753ac5a10bcd324295ab981c946cc7ebb4d3cef3'
TARGET='7934dcd0b9882e1ad9a22834bc3f76af805283c8cdb264d26e885c0275879d1b'
LIBRE=ROOT/'build/rpi5/libressl-4.3.3-input-X8xG1B/libressl-4.3.3'
APPLE=ROOT/'build/rpi5/apple-libpthread-main-candidate-20261013/include'


def same_abi(first,second):
    if first!=second:raise ValueError('Actual SDK/original pthread ABI or initializer differs')


def command(report,suffix):
    rows=[c['command'] for c in report['commands'] if c['stdout'].endswith('/'+suffix+'.stdout')]
    if len(rows)!=1:raise ValueError('Exact command required: '+suffix)
    return rows[0]


class PacketPthreadContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((PACKAGE/'manifest.json').read_text())
        cls.image=MachO(cls.report['target'])

    def test_full_actual_closure_and_negative_membership(self):
        self.assertEqual(sha(PACKAGE/'manifest.json'),MANIFEST)
        validate_closure(PACKAGE,self.report)
        for key in ('headers_sha256','generated_sha256'):
            bad=copy.deepcopy(self.report);bad[key].pop(next(iter(bad[key])))
            with self.assertRaisesRegex(ValueError,'membership mismatch'):validate_closure(PACKAGE,bad)
        pins={k:v for field in ('source_inputs_sha256','headers_sha256','generated_sha256') for k,v in self.report[field].items()}
        for argument in command(self.report,'target-link'):
            p=Path(argument)
            if p.is_absolute() and p.suffix in ('.o','.a'):
                self.assertEqual(pins.get(str(p)),sha(p),str(p))
        self.assertEqual(sha(self.report['target']),TARGET)
        self.assertEqual(prepare_pid1.inspect(Path(self.report['target']).read_bytes()),self.report['macho_audit'])

    def test_exact_startup_ctor_pointers_and_real_provider_owners(self):
        image=self.image;ctors=next(s for s in image.sections if s['name']=='__DATA,__mod_init_func')
        expected=('_initialized_constructor','_openssl_init_crypto_constructor')
        self.assertEqual(ctors['size'],16)
        self.assertEqual(struct.unpack('<2Q',image.at(ctors['address'],16)),tuple(image.names[n]['address'] for n in expected))
        self.assertEqual(self.report['actual_constructor_order'],list(expected))
        text=(PACKAGE/'target-startup-disassembly.stdout').read_text()
        start=text.split('<_darwin_static_start>:',1)[1].split('\n\n',1)[0]
        ordered=['<___libkernel_init>','<___pthread_init>','<_malloc>','<_free>',
                 '<___pthread_late_init>','<_rpi5_run_initializers>','<_rpi5_pthread_smoke_main>']
        positions=[start.index(p) for p in ordered];self.assertEqual(positions,sorted(positions))
        workload=text.split('<_rpi5_pthread_smoke_main>:',1)[1].split('\n\n',1)[0]
        self.assertLess(workload.index('<_rpi5_packet_pthread_prerequisite>'),workload.index('<_darwin_network_command_main>'))
        self.assertRegex(workload,r'cbz\s+w0,')
        mapping=(PACKAGE/'target.map').read_text();owners={int(n):p for n,p in re.findall(r'^\[\s*(\d+)\]\s+(.+)$',mapping,re.M)}
        required={'_pthread_equal':'pthread-private.o','_pthread_self':'pthread-pthread_tsd.o',
            '_pthread_mutex_lock':'pthread-pthread_mutex.o','_pthread_mutex_unlock':'pthread-pthread_mutex.o',
            '_sysctlbyname':'leaf-target.o','_crypto_cpu_caps_init':'crypto_cpu_caps_darwin.c.o',
            '_openssl_init_crypto_constructor':'crypto_init.c.o'}
        for name,member in required.items():
            row=re.search(r'^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+'+re.escape(name)+r'$',mapping,re.M)
            self.assertIsNotNone(row,name);self.assertTrue(owners[int(row[1])].endswith('('+member+')'),owners[int(row[1])])
        self.assertEqual(subprocess.check_output(['xcrun','nm','-u',self.report['target']],text=True).strip(),'')
        for cmd in (0xc,0xe,0x80000018,0x80000028):self.assertNotIn(cmd,image.commands)
        self.assertIn(5,image.commands)

    def test_debug_metadata_removal_preserves_all_actual_section_bytes(self):
        old=MachO(self.report['unstripped_target']);new=self.image
        self.assertEqual(old.sections,new.sections)
        for section in old.sections:
            if section['offset'] and section['size']:
                self.assertEqual(old.at(section['address'],section['size']),new.at(section['address'],section['size']))
        self.assertEqual(command(self.report,'target-strip-debug')[:3],['xcrun','strip','-S'])

    def test_actual_sdk_original_target_abi_and_mutex_initializer(self):
        flags=command(self.report,'target-pthread-prerequisite-compile')
        flags=flags[:flags.index('-MD')]
        flags=[v for v in flags if not v.startswith('-Drpi5_pthread_smoke_main=')]
        startup=json.loads((ROOT/'build/rpi5/apple-pthread-static-complete-gm82fjkz/manifest.json').read_text())
        original_flags=command(startup,'startup-compile');original_flags=original_flags[:original_flags.index('-MD')]
        source=ROOT/'tools/rpi5/tests/libressl_pthread_abi_contract.c'
        with tempfile.TemporaryDirectory(prefix='packet-pthread-abi-') as name:
            blobs=[]
            # Use the actual frozen original startup flags/Availability header
            # set, not a reconstructed approximation of Apple's source build.
            for label,selected in (('sdk',flags),('original',original_flags)):
                out=Path(name)/(label+'.o');dep=Path(name)/(label+'.d')
                result=subprocess.run(selected+['-Werror','-MD','-MF',str(dep),'-c',str(source),'-o',str(out)],capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stderr)
                paths=shlex.split(dep.read_text().replace('\\\n',' ').partition(':')[2])
                expected=APPLE/'pthread/pthread.h' if label=='original' else Path(flags[flags.index('-isysroot')+1])/'usr/include/pthread/pthread.h'
                self.assertIn(str(expected),paths)
                obj=MachO(out);symbol=obj.names['_rpi5_pthread_abi']
                section=obj.sections[symbol['section']-1]
                blobs.append(obj.at(symbol['address'],section['address']+section['size']-symbol['address']))
            same_abi(*blobs)
            fields=struct.unpack('<12Q',blobs[0][:96]);self.assertEqual(fields[:6],(8,8,64,8,0,8))
            mutex=blobs[0][96:160];self.assertEqual(mutex,struct.pack('<Q',0x32aaaba7)+bytes(56))
            with self.assertRaises(ValueError):same_abi(blobs[0],bytes([blobs[1][0]^1])+blobs[1][1:])

    def test_original_cpu_caps_source_all_feature_and_missing_sysctl_subsets(self):
        source=LIBRE/'crypto/arch/aarch64/crypto_cpu_caps_darwin.c'
        harness=ROOT/'tools/rpi5/tests/libressl_caps_contract.c'
        with tempfile.TemporaryDirectory(prefix='packet-caps-') as name:
            exe=Path(name)/'host-caps'
            result=subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror','-O1',
                '-fsanitize=address,undefined','-Dsysctlbyname=rpi5_contract_sysctlbyname',
                '-I'+str(source.parent),str(source),str(harness),'-o',str(exe)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([exe],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,'')
            self.assertEqual(result.stdout,'LIBRESSL_CAPS PASS CASES=4096 QUERIES=24576 REAL_SOURCE HOST_SYSCTL_DOUBLE TARGET_NOT_RUN\n')
            negative=subprocess.run([exe,'wrong-expectation'],capture_output=True,text=True,timeout=10)
            self.assertEqual(negative.returncode,33)

    def test_combined_host_oracle_and_explicit_unproven_target_boundary(self):
        exe=PACKAGE/'sshpacket-pthread-host'
        result=subprocess.run([exe],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,'')
        self.assertEqual(result.stdout,self.report['native_stdout'])
        self.assertIn('THREADS=4 JOIN=4 MUTEX=2048 TSD_DTORS=4 ONCE=1 ERRNO=4 ALLOC=2048',result.stdout)
        self.assertEqual(self.report['valid_packet_cases'],48);self.assertEqual(self.report['rejected_packet_cases'],5036)
        for key in ('pi_executed','installed','entropy_qualified','live_keys','ssh_transport','constructors_executed_on_target'):
            self.assertIs(self.report[key],False)
        self.assertEqual(self.report['target_missing_symbols'],[]);self.assertEqual(self.report['target_duplicate_symbols'],[])


if __name__=='__main__':unittest.main()
