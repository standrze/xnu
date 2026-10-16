# SPDX-License-Identifier: BSD-2-Clause
import unittest
from unittest.mock import patch
from tools.rpi5 import check_display_restart_init_v2 as c

class InitReportScopeTests(unittest.TestCase):
    def test_exact_actual_frozen_package_current_and_historical_scope(self):
        p=c.b.ROOT/'build/rpi5/display-restart-init-xw9wi1um'
        with patch('subprocess.run',side_effect=AssertionError('No compiler or hardware')):
            r=c.inspect(p,'c55fcd57295b24135deb7bcf1d525d0e87ca934e9e4e49723bd2f0e1780675a4')
        self.assertNotIn('root_only_added_cli',r['checks'])
        self.assertNotIn('exact_inherited_bytes',r['checks'])
        self.assertNotIn('one_loader_owner_replaced',r['copy_phase_checks'])
        self.assertTrue(r['checks']['root_only_launchd_replaced'])
        self.assertTrue(r['inherited_component_checks']['checks']['root_only_added_cli'])
        self.assertFalse(r['copy_phase_contract']['kernel_root_payload_unchanged'])
        self.assertEqual(r['root_only_replaced'],'/sbin/launchd')
        self.assertFalse(r['target_executed'])
        self.assertFalse(r['physical_psci_causality_proven'])
        self.assertEqual(r['supplemental_report_source_sha256'][c.__file__],c.b.sha(c.__file__))

    def test_actual_saved_qualified_report_and_admission_mutations(self):
        import copy,json
        from tools.rpi5 import stage_restart_init_trial as stage
        r=json.loads(stage.REPORT.read_text());self.assertTrue(stage.valid_report(r))
        self.assertEqual(stage.sha(stage.REPORT),stage.REPORT_SHA)
        pins=stage.source_pins()
        for name in ('check_display_restart_init_v2.py','tests/test_display_restart_init_report_v2.py'):
            path=stage.ROOT/'tools/rpi5'/name;self.assertEqual(pins[str(path)],stage.sha(path))
        for change in ({'report_scope':'current-root-only-added-cli'},
                {'supplemental_report_source_sha256':{}},
                {'checks':r['inherited_component_checks']['checks']},
                {'copy_phase_contract':c.b.prior.CONTRACT}):
            bad=copy.deepcopy(r);bad.update(change)
            with self.assertRaises(ValueError):stage.valid_report(bad)

if __name__=='__main__':unittest.main()
