# SPDX-License-Identifier: BSD-2-Clause
import ast
import unittest
from unittest.mock import patch
from tools.rpi5 import audit_gem_batch_startup_stack as b
class BatchStartupStackTests(unittest.TestCase):
    def test_only_profile_predicate_changes(self):
        _,source=b.derived_audit();text=b.Path(b.old.__file__).read_text()
        node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='audit')
        original='\n'.join(text.splitlines()[node.lineno-1:node.end_lineno])+'\n'
        self.assertEqual(source.replace(repr(b.PROFILE),repr(b.OLD_PROFILE)),original)
        self.assertNotIn('manifest_substituted',source)
    def test_changed_frozen_audit_rejected_without_compiler(self):
        with patch.object(b.old,'sha',return_value='0'*64),patch('subprocess.run',side_effect=AssertionError('No compiler')):
            with self.assertRaises(ValueError):b.derived_audit()
if __name__=='__main__':unittest.main()
