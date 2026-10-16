#!/usr/bin/env python3
"""Original-source membership, actual link gaps, native parser/conversion proof."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import unittest
from tools.rpi5 import build_apple_libinfo_numeric as build

PACKAGE=build.ROOT/'build/rpi5/apple-libinfo-numeric-f893rytw'
SHA='4eabb37da4c78195671150c37342f2021582c7ad7a4194bd960d5929596d1a2c'


def dependencies(report):
    result={}
    for row in report['commands']:
        c=row['command']
        if row['returncode'] or '-MF' not in c:continue
        actual={}
        for s in shlex.split(Path(c[c.index('-MF')+1]).read_text().replace('\\\n',' ').partition(':')[2]):
            p=(Path(row['cwd'])/s).resolve();actual[str(p)]=build.sha(p)
        result.update(actual)
    return result


class LibinfoNumeric(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE/'manifest.json')!=SHA:raise ValueError('Frozen numeric receipt changed')
        cls.report=json.loads((PACKAGE/'manifest.json').read_text())
        if build.sha(build.BASE/'manifest.json')!=build.BASE_SHA:raise ValueError('Frozen inventory receipt changed')
        cls.inventory=json.loads((build.BASE/'manifest.json').read_text())

    def test_exact_source_consumed_headers_and_generated_bytes(self):
        for r in (self.report,self.inventory):
            for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
                for n,h in r[key].items():self.assertEqual(build.sha(n),h,n)
            self.assertEqual(dependencies(r),r['headers_sha256'])
            for record in r['dependency_records'].values():
                self.assertEqual(record['scanned_sha256'],record['consumed_sha256'])
        for p in self.report['original_sources']:
            root=build.SOURCE if p.startswith(str(build.SOURCE)) else build.LIBC
            self.assertEqual(Path(p).read_bytes(),subprocess.check_output(['git','-C',root,'show','HEAD:'+str(Path(p).relative_to(root))]))
        overlay=Path(self.report['exact_private_kernel_macros']).read_text()
        self.assertEqual(overlay,build.private_macros(build.KERNEL_HEADER.read_text()))
        with self.assertRaises(ValueError):build.private_macros(build.KERNEL_HEADER.read_text().replace('#define IN_DS_LITE(i)', '#define OMITTED(i)'))

    def test_actual_macos_inventory_failure_membership_and_link(self):
        r=self.inventory
        self.assertEqual(r['source_commit'],build.previous.COMMIT)
        self.assertEqual(tuple(r['original_macros']),build.previous.MACROS)
        self.assertEqual(len(r['compiled_objects']),7)
        self.assertEqual(len(r['compile_failures']),8)
        failed={str(Path(x['source']).relative_to(build.SOURCE)) for x in r['compile_failures']}
        self.assertEqual(set(r['compiled_objects'])|failed,set(build.previous.UNITS))
        self.assertFalse(set(r['compiled_objects'])&failed)
        self.assertEqual(r['closed_symbols'],['_freeifaddrs','_getifaddrs','_h_errno'])
        self.assertEqual(len(r['target_missing_symbols']),51)
        self.assertEqual(r['newly_reachable_symbols'],[])
        self.assertFalse(r['provider_stubs']);self.assertFalse(r['libinfo_macros_removed'])

    def test_numeric_actual_client_delta_without_service_claims(self):
        r=self.report
        stderr=(PACKAGE/'target-link.stderr').read_text()
        actual=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',stderr,re.M)))
        self.assertEqual(actual,r['target_missing_symbols']);self.assertEqual(len(actual),50)
        self.assertEqual(r['closed_symbols'],['_freeaddrinfo','_gai_strerror','_inet_ntoa','_inet_ntop'])
        self.assertEqual(r['newly_reachable_symbols'],['___snprintf_chk','___sprintf_chk','___strcpy_chk'])
        self.assertEqual(r['target_duplicate_symbols'],[])
        original=next(c['command'] for c in self.inventory['commands'] if c['stdout'].endswith('/target-link.stdout'))
        actual=next(c['command'] for c in r['commands'] if c['stdout'].endswith('/target-link.stdout'))
        expected=list(original)
        for flag in ('-o','-map'):expected[expected.index(flag)+1]=actual[actual.index(flag)+1]
        expected.append(r['target_archive']);self.assertEqual(expected,actual)
        for flag in ('target_link_complete','target_executed','host_account_files_accessed','dns_executed','provider_stubs','accepted_runtime_modified'):
            self.assertFalse(r[flag])
        self.assertTrue(r['original_libinfo_configuration_unchanged'])

    def test_native_original_parser_and_numeric_contract(self):
        for name,expected in build.EXPECTED.items():
            result=subprocess.run([PACKAGE/('host-'+name)],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout,expected);self.assertEqual(result.stderr,'')
            self.assertEqual(self.report['native_stdout'][name],expected)
        names=subprocess.check_output(['xcrun','nm','-U',PACKAGE/'host-numeric'],text=True)
        # inet_aton itself is unused: the original numeric helper calls the
        # stricter _inet_aton_check. gai_strerror is inlined in the included TU.
        for symbol in ('_inet_ntop','_inet_pton','__inet_aton_check','_freeaddrinfo'):
            self.assertRegex(names,r'(?m)\b'+re.escape(symbol)+r'$')
        object_names=subprocess.check_output(['xcrun','nm','-U',PACKAGE/'host-numeric.o'],text=True)
        self.assertRegex(object_names,r'(?m)\b_gai_strerror$')
        self.assertTrue(self.report['native_asan_ubsan_pass'])

    def test_configuration_hook_is_not_a_fake_service_bypass(self):
        s=(build.SOURCE/'lookup.subproj/search_module.c').read_text()
        m=(build.SOURCE/'lookup.subproj/si_module.c').read_text()
        defaults=s[s.index('const char * const modules[]'):s.index('char *check = getenv("SYSINFO_CONF_ENABLE")')]
        self.assertIn('"mdns"',defaults)
        self.assertIn('si_module_config_modules_for_category(pp, CATEGORY_DEFAULT',defaults)
        self.assertIn('{ "mdns", si_module_static_mdns, NULL }',m)
        self.assertIn('fopen(_PATH_SI_CONF, "r")',s)
        f=(build.SOURCE/'lookup.subproj/file_module.c').read_text()
        self.assertIn('if (geteuid() == 0)',f)
        self.assertIn('fopen(_PATH_MASTERPASSWD, "r")',f)
        self.assertIn('fopen(_PATH_PASSWD, "r")',f)
        self.assertIn('if (f == NULL) return NULL;',f)


if __name__=='__main__':unittest.main()
