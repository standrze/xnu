# SPDX-License-Identifier: BSD-2-Clause
"""Final image/receipt mutation checks use independently supplied artifact pins."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch
from tools.rpi5 import check_gem_dma_batch_trial as c
from tools.rpi5 import qualify_gem_dma_batch_trial as q
from tools.rpi5.tests import test_gem_dma_batch_serial as serial_test

class BatchTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        keys=('RPI5_BATCH_PACKAGE','RPI5_BATCH_MANIFEST_SHA','RPI5_BATCH_QUALIFICATION','RPI5_BATCH_QUALIFICATION_SHA')
        if not all(os.environ.get(k) for k in keys):raise unittest.SkipTest('Final independently pinned package/qualification not supplied')
        cls.package=Path(os.environ[keys[0]]).resolve();cls.pin=os.environ[keys[1]]
        cls.qualification=Path(os.environ[keys[2]]).resolve();cls.qpin=os.environ[keys[3]]
        cls.m=json.loads((cls.package/'manifest.json').read_bytes())
        cls.receipt=json.loads(cls.qualification.read_bytes())
        with patch('subprocess.run',side_effect=AssertionError('No compiler or hardware')):
            cls.report=c.inspect(cls.package,cls.pin,cls.qualification,cls.qpin)

    def test_actual_image_and_actual_saved_report_fixture(self):
        from tools.rpi5 import gem_dma_batch_serial as p
        data,report=serial_test.BatchSerialTests().fixture(self.report)
        with patch('subprocess.run',side_effect=AssertionError('No compiler or hardware')):
            self.assertTrue(p.inspect(data,report)['cpu_ring_trial_pass'])
            self.assertTrue(self.report['software_trial_qualified'])
            self.assertFalse(self.report['physical_execution_proven'])
            with self.assertRaises(ValueError):p.inspect(data+b'panic(cpu 0): after END\n',report)

    def test_actual_commands_scans_derived_sources_and_container_mutations(self):
        expected=self.m;source=c.canonical
        with patch('subprocess.run',side_effect=AssertionError('No compiler')):
            mutations=[]
            m=copy.deepcopy(expected);m['commands'].pop();mutations.append(m)
            m=copy.deepcopy(expected);m['commands'][0]['command'].append('-O0');mutations.append(m)
            m=copy.deepcopy(expected);m['commands'][0]['cwd']=str(self.package);mutations.append(m)
            m=copy.deepcopy(expected);m['commands'][0]['returncode']=False;mutations.append(m)
            m=copy.deepcopy(expected);m['compiler_scans'].pop(next(iter(m['compiler_scans'])));mutations.append(m)
            m=copy.deepcopy(expected);next(r for r in m['commands'] if r['log'].endswith('/kernel-link.log'))['command'].append('/tmp/extra.o');mutations.append(m)
            for m in mutations:
                with self.assertRaises(ValueError):source.command_bindings(self.package,m)
            for name in ('arm_init.c','probe_main.c','overlay/BCM2712GEMDMABatch.cpp'):
                changed=c.b.derived_sources();changed[name]+=b'\n'
                with patch.object(c.b,'derived_sources',return_value=changed):
                    with self.assertRaises(ValueError):source.source_outputs(self.package,expected)
            with patch.object(c.b.old.payload_container,'encode',return_value=b'bad reserved header/padding'):
                with self.assertRaises(ValueError):source.payload(self.package)

    def test_strict_image_manifest_contract_and_stack_binding_negatives(self):
        original=Path.read_bytes;manifest=self.package/'manifest.json'
        def check_manifest(value):
            raw=json.dumps(value,sort_keys=True).encode()
            def read(path):return raw if path==manifest else original(path)
            with patch.object(Path,'read_bytes',read),patch('subprocess.run',side_effect=AssertionError('No compiler')):
                with self.assertRaises(ValueError):c.inspect_image(self.package,hashlib.sha256(raw).hexdigest())
        for key,value in (('owner_check_limit',65536.0),('ring_expected_current',True),('dma_activation',0),
            ('copy_max_renewals',3),('all_inbound_windows_disabled',1),('firmware_sha256','0'*64)):
            m=copy.deepcopy(self.m);m[key]=value;check_manifest(m)
        with patch('subprocess.run',side_effect=AssertionError('No compiler')):
            for pin in ('0'*64,'not SHA'):
                with self.assertRaises(ValueError):q.inspect(self.package,self.pin,self.qualification,pin)
            for key,value in (('package_manifest_sha256','0'*64),('measurements_sha256','0'*64),('profile','other')):
                changed=copy.deepcopy(self.receipt);changed[key]=value
                raw=json.dumps(changed,sort_keys=True).encode()
                def read(path):return raw if path==self.qualification else original(path)
                with patch.object(Path,'read_bytes',read):
                    with self.assertRaises(ValueError):q.inspect(self.package,self.pin,self.qualification,hashlib.sha256(raw).hexdigest())

class BatchLogTests(unittest.TestCase):
    def test_actual52_formats_fit_original_encoder_scalar_bound(self):
        text=c.b.profile.derive()['BCM2712PCIeIDTrialProgress.inc'].decode()
        formats=re.findall(r'kprintf\("([^"\n]+)"',text)
        self.assertEqual(len(formats),52)
        self.assertTrue(all(len(re.findall(r'%(?!%)',f))<=16 for f in formats))
        self.assertTrue(formats[-1].startswith('RPI5XNU:PCIEID:END '))
        self.assertTrue(all(len(re.findall(r'%(?!%)',f))<=8 for f in formats[-6:-1]))

if __name__=='__main__':unittest.main()
