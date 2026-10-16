#!/usr/bin/env python3
"""Full original public file-backend fixture and explicit Pi configuration."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from tools.rpi5 import build_libinfo_pi_files_checked as checked
from tools.rpi5 import libinfo_pi_files_profile as profile
from tools.rpi5.tests.test_apple_libinfo_numeric import dependencies

ROOT,sha=checked.ROOT,checked.sha
PACKAGE=ROOT/'build/rpi5/pi-libinfo-files-wj7_spx1'
SHA='544943437813436add20988cbbca221f4aafb37da3b6815244a0d2c664a5bc9e'


class PiFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sha(PACKAGE/'manifest.json')!=SHA:raise ValueError('Pi file-backed receipt changed')
        cls.r=json.loads((PACKAGE/'manifest.json').read_text())

    def test_all_source_generated_bytes_and_exact_consumed_headers(self):
        r=self.r
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for n,h in r[key].items():self.assertEqual(sha(n),h,n)
        self.assertEqual(dependencies(r),r['headers_sha256'])
        for d in r['dependency_records'].values():self.assertEqual(d['scanned_sha256'],d['consumed_sha256'])
        self.assertEqual(set(r['source_transforms']),set(checked.original.UNITS)|{'darwin_directory_enabled.h'})
        for name,d in r['source_transforms'].items():
            self.assertEqual(Path(d['overlay']).read_text(),profile.transform(name,Path(d['source']).read_text()))

    def test_explicit_modules_real_stat_and_target_accounts(self):
        self.assertEqual(tuple(self.r['target_macros']),profile.MACROS)
        module=(PACKAGE/'overlay/si_module.c').read_text()
        self.assertNotIn('{ "mdns", si_module_static_mdns, NULL }',module)
        self.assertIn('errno = ENOTSUP;\n\treturn NULL;',module)
        self.assertNotIn('"mdns",',(PACKAGE/'overlay/search_module.c').read_text())
        self.assertIn('if (RPI5_LIBINFO_FILE_STAT_VALIDATION || pp->notify_token[vtype] < 0)',(PACKAGE/'overlay/file_module.c').read_text())
        for n,t in profile.FIXTURES.items():self.assertEqual((PACKAGE/'fixtures'/n).read_text(),t)
        self.assertIn('root:*:0:0::0:0:System Administrator:/var/root:/bin/zsh',profile.FIXTURES['master.passwd'])
        self.assertIn('/Users/sandrzej:/bin/zsh',profile.FIXTURES['passwd'])
        self.assertEqual(self.r['profile'],'pi-libinfo600-static-files-stat-validation-no-native-dlopen-v2')
        self.assertTrue(self.r['original_macos_profile_unchanged']);self.assertFalse(self.r['provider_stubs'])

    def test_actual_public_native_fixture_no_dynamic_service_loading(self):
        r=subprocess.run([PACKAGE/'host-pi-files'],capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout,checked.original.EXPECTED);self.assertEqual(r.stderr,'')
        self.assertTrue(self.r['native_dynamic_loading_forbidden']);self.assertEqual(self.r['native_named_host_flags'],'AI_PASSIVE')
        names=subprocess.check_output(['xcrun','nm','-U',PACKAGE/'host-pi-files'],text=True)
        for symbol in ('_getpwnam','_getpwuid','_getgrnam','_getgrgid','_getaddrinfo','_getnameinfo','_LI_set_thread_item','_rpi5_forbidden_dlopen'):
            self.assertRegex(names,r'(?m)\b'+re.escape(symbol)+r'$')
        # The fixture must never be mistaken for genuine target libdispatch.
        self.assertIn('libdispatch',self.r['native_host_runtime_boundary']);self.assertFalse(self.r['target_executed'])

    def test_actual_full_client_delta_and_real_runtime_requirements(self):
        r=self.r;stderr=(PACKAGE/'target-link.stderr').read_text()
        missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',stderr,re.M)))
        self.assertEqual(missing,r['target_missing_symbols']);self.assertEqual(len(missing),67)
        self.assertEqual(r['target_duplicate_symbols'],[])
        self.assertEqual(r['closed_symbols'],['_getaddrinfo','_getnameinfo','_getpwnam','_getpwuid','_getservbyname','_initgroups'])
        for s in ('_dispatch_once','__NSConcreteGlobalBlock','__NSConcreteStackBlock','_notify_check','_si_destination_compare','___initgroups'):
            self.assertIn(s,missing)
        self.assertFalse(r['target_link_complete']);self.assertFalse(r['accepted_runtime_modified'])

    def test_exact_packing_fix_and_original_failure_320_cases(self):
        out=Path(tempfile.mkdtemp(prefix='libinfo-alignment-contract-',dir=ROOT/'build/rpi5'))
        old=next(c['command'] for c in self.r['commands'] if c['stdout'].endswith('/host-ils-compile.stdout'))
        flags=old[:old.index('-MD')]
        caller=ROOT/'tools/rpi5/tests/libinfo_payload_alignment_host.c'
        for label,source in (('fixed',PACKAGE/'overlay/ils.c'),('original',profile.SOURCE/'lookup.subproj/ils.c')):
            binary=out/label;command=flags+[str(caller),str(source),'-Wl,-dead_strip','-o',str(binary)]
            made=subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertEqual(made.returncode,0,made.stderr)
            result=subprocess.run([binary],capture_output=True,text=True,timeout=15)
            (out/(label+'.stdout')).write_text(result.stdout);(out/(label+'.stderr')).write_text(result.stderr)
            if label=='fixed':
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout,'LIBINFO_PAYLOAD_ALIGNMENT PASS CASES=320 PREFIX_LENGTHS=64 FORMATS=5\n')
                self.assertEqual(result.stderr,'')
            else:
                self.assertNotEqual(result.returncode,0);self.assertIn('Assertion failed',result.stderr)
        # The real public caller failure predates this fix and remains preserved.
        failure=(ROOT/'build/rpi5/pi-libinfo-files-v3oq5pjg/host-run.stderr').read_text()
        self.assertIn('load of misaligned address',failure)


if __name__=='__main__':unittest.main()
