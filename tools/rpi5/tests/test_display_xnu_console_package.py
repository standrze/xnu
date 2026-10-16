# SPDX-License-Identifier: BSD-2-Clause
"""Explicit final linked candidate only; byte admission never invokes compilers."""
import copy
import json
import os
from pathlib import Path
import subprocess
from unittest import mock
import unittest
from .. import check_display_xnu_console as check
class DisplayXNUConsolePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        name=os.environ.get('RPI5_DISPLAY_XNU_PACKAGE')
        if not name:raise unittest.SkipTest('Explicit RPI5_DISPLAY_XNU_PACKAGE required')
        cls.package=Path(name).resolve();cls.pin=check.b.sha(cls.package/'manifest.json')
        cls.raw=(cls.package/'manifest.json').read_text();cls.record=json.loads(cls.raw)
    def inspect(self):
        with mock.patch.object(subprocess,'run',side_effect=AssertionError('Compiler/process forbidden')), \
            mock.patch.object(subprocess,'check_output',side_effect=AssertionError('Process forbidden')), \
            mock.patch.object(subprocess,'Popen',side_effect=AssertionError('Process forbidden')):
            return check.inspect(self.package,self.pin)
    def mutate(self,change):
        value=copy.deepcopy(self.record);change(value);original=json.loads
        with mock.patch.object(check.json,'loads',side_effect=lambda text,*a,**kw:value if text==self.raw else original(text,*a,**kw)):
            with self.assertRaises((ValueError,KeyError)):self.inspect()
    def test_actual_linked_package_byte_only(self):
        report=self.inspect();self.assertTrue(all(report['checks'].values()));self.assertFalse(report['physical_visibility_proven'])
    def test_omitted_scan_label_and_changed_command_rejected(self):
        def omit(m):
            label=next(iter(m['compiler_scans']));del m['compiler_scans'][label]
        self.mutate(omit)
        self.mutate(lambda m:m['commands'][0]['command'].append('-DUNREVIEWED=1'))
        self.mutate(lambda m:m['commands'][0].update(cwd='/tmp'))
    def test_exact_object_owners_and_required_header_closure(self):
        def wrong(m):
            key=next(iter(m['replaced_objects']));value=m['replaced_objects'].pop(key)
            m['replaced_objects'][str(check.b.OBJ/'osfmk/DEVELOPMENT/io_map.o')]=value
        self.mutate(wrong)
        self.mutate(lambda m:m['actual_headers_sha256'].pop(next(iter(m['actual_headers_sha256']))))
        self.mutate(lambda m:m['inputs_sha256'].pop(str(check.b.ROOT/'loader/rpi5/display_xnu_record.h')))
    def test_type_sensitive_contract_and_bounded_watchdog(self):
        for name,value in (('terminal_watchdog_seconds',True),('watchdog_countdown_seconds',15.0),('watchdog_deadline_extended',0),
            ('published_mapping_retained_until_reset',1),('managed_span',[0x6000000,float(0x10000000)]),('physical_execution',0)):
            self.mutate(lambda m,n=name,v=value:m.update({n:v}))
    def test_wrong_tag_expected_pin_image_and_stack(self):
        with self.assertRaises(ValueError):check.inspect(self.package,'0'*64)
        self.mutate(lambda m:m.update(tag='0'*32))
        self.mutate(lambda m:m.update(image_sha256='0'*64))
        self.mutate(lambda m:m['stack_budget'].update(conservative_bytes=0))
if __name__=='__main__':unittest.main()
