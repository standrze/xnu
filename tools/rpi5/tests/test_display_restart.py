# SPDX-License-Identifier: BSD-2-Clause
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools.rpi5 import build_display_restart as b
from tools.rpi5 import check_display_restart as c

class DisplayRestartTests(unittest.TestCase):
    def test_actual_cli_and_original_wrapper_native_only(self):
        with tempfile.TemporaryDirectory(prefix='restart-cli-native-') as name:
            out=Path(name);objects=[]
            for source,extra,label in [(b.ROOT/'tools/rpi5/user/reboot_cli.c',['-Dreboot=rpi5_test_reboot','-Dwrite=rpi5_test_write'],'cli'),
                (b.ROOT/'libsyscall/wrappers/reboot.c',['-Dreboot=rpi5_test_reboot','-Dreboot_np=rpi5_test_reboot_np','-D__reboot=rpi5_test_reboot_trap'],'wrapper'),
                (b.ROOT/'tools/rpi5/tests/reboot_cli_host.c',[],'host')]:
                obj=out/(label+'.o');subprocess.run(['xcrun','clang','-fsanitize=address,undefined','-g','-O1',*extra,'-c',str(source),'-o',str(obj)],check=True,capture_output=True);objects.append(str(obj))
            exe=out/'host';subprocess.run(['xcrun','clang','-fsanitize=address,undefined',*objects,'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True,capture_output=True)
    def test_exact_only_loader_literals_and_frozen_platform(self):
        raw=(b.BASE/'probe_main.c').read_text();derived=b.derive_main(raw)
        self.assertEqual(derived.replace(b.BOOT+' rpi5_psci_restart=1',b.BOOT).replace(b.MARKER,'RPI5XNU:DISPLAYXNU:ENTRY TAG='),raw)
        with self.assertRaises(ValueError):b.derive_main(raw.replace(b.BOOT,'different'))
        self.assertEqual(b.policy.derive(b.policy.ORIGINAL.read_text()),(b.RESET/'IOPlatformExpert.restart.cpp').read_text())
    @unittest.skipUnless(os.environ.get('RPI5_RESTART_PACKAGE'),'Distinct built package required')
    def test_actual_full_package_byte_check_and_negative_closure(self):
        p=Path(os.environ['RPI5_RESTART_PACKAGE']).resolve();m=b.document(p/'manifest.json')
        with patch.object(subprocess,'run',side_effect=AssertionError('checker must be byte-only')):
            report=c.inspect(p,b.sha(p/'manifest.json'));self.assertTrue(all(report['checks'].values()))
            for change in ('omit','flags','type','scope'):
                bad=json.loads(json.dumps(m))
                if change=='omit':bad['inputs_sha256'].pop(str(b.ROOT/'tools/rpi5/user/reboot_cli.c'))
                if change=='flags':next(r for r in bad['commands'] if r['label']=='policy-compile')['command'].remove('-mcpu=cortex-a76')
                if change=='type':bad['original_watchdog_seconds']=180.0
                if change=='scope':bad['scope']['physical_restart_proven']=True
                with patch.object(b,'document',side_effect=lambda path:bad if Path(path)==p/'manifest.json' else json.loads(Path(path).read_text())):
                    with self.assertRaises(ValueError):c.inspect(p)
    @unittest.skipUnless(os.environ.get('RPI5_RESTART_PACKAGE'),'Distinct built package required')
    def test_actual_native_kernel_root_container_and_post_cma_loader(self):
        from tools.rpi5 import display_restart_native
        result=display_restart_native.inspect(Path(os.environ['RPI5_RESTART_PACKAGE']))
        self.assertTrue(result['exact_same_image_bytes']);self.assertFalse(result['target_executed'])
