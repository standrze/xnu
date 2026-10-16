import importlib.util
from pathlib import Path
import sys
import unittest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location('isa_inventory', TOOLS / 'inventory_isa.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class IsaInventoryTests(unittest.TestCase):
    def test_labels_do_not_imply_code_or_compatibility(self):
        report = module.inventory('''Disassembly of section __TEXT_EXEC,__text:
fffffe0000001000 <function>:
fffffe0000001000: ret
fffffe0000001004: <unknown>
fffffe0000001008 <constant>:
fffffe0000001008: subg x0, x0, #0x10, #1
Disassembly of section __TEXT_EXEC,__hib_text:
fffffe0000002000: <unknown>
'''.splitlines())
        self.assertEqual(report['status'], 'manual_review_required')
        self.assertEqual(report['decoded_words'], 4)
        self.assertEqual(report['mnemonics']['subg'], 1)
        self.assertEqual(report['unknown_words'][0]['nearest_label']['name'], 'function')
        self.assertIsNone(report['unknown_words'][1]['nearest_label'])

    def test_no_silent_empty_success(self):
        with self.assertRaisesRegex(ValueError, 'No disassembly'):
            module.inventory(['file format mach-o arm64'])
        with self.assertRaisesRegex(ValueError, 'outside'):
            module.inventory(['1000: ret'])

    def test_control_operands_retained_without_compatibility_claim(self):
        report = module.inventory('''Disassembly of section __TEXT_EXEC,__text:
1000 <entry>:
1000: mrs x0, S3_0_C15_C0_0
1004: msr CPACR_EL1, x1
1008: tlbi vmalle1is
100c: hint #0x19
1010: eret
1014: ret
'''.splitlines())
        self.assertEqual(report['status'], 'manual_review_required')
        self.assertEqual(len(report['control_words']), 5)
        self.assertEqual(report['control_words'][0]['operands'], 'x0, S3_0_C15_C0_0')
        self.assertEqual(report['control_words'][2]['operands'], 'vmalle1is')
        self.assertEqual(report['control_words'][4]['operands'], '')
        self.assertEqual(report['control_words'][0]['nearest_label']['name'], 'entry')
