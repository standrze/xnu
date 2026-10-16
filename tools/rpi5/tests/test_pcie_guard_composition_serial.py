# SPDX-License-Identifier: BSD-2-Clause
import copy
import types
import unittest
from tools.rpi5 import pcie_guard_composition_serial_core as p
from tools.rpi5.tests import test_pcie_owner_trace_serial as old


class GuardCompositionSerialTests(unittest.TestCase):
    def fixture(self):
        data,report=old.OwnerSerialTests().fixture()
        data=data.replace(b'CHECKS=25282 CALLBACKS=101136',b'CHECKS=14452 CALLBACKS=57816')
        data=data.replace(b'PCIE_OWNER_TRACE_TRIAL',b'PCIE_GUARD_COMPOSITION_TRIAL')
        report['boot_markers']=[m.replace('PCIE_OWNER_TRACE_TRIAL','PCIE_GUARD_COMPOSITION_TRIAL') for m in report['boot_markers']]
        report['marker']=next(m for m in report['boot_markers'] if m.startswith('RPI5XNU:BL33:PCIE_GUARD_COMPOSITION_TRIAL TAG='))
        report.update(owner_trace=p.package_source.owner_contract(),trace_contract=p.package_source.trace_contract(),
                      guard_composition=p.package_source.guard_contract())
        return data,report

    def test_new_exact_marker_and_truthful_contract(self):
        data,report=self.fixture();result=p.inspect(data,report)
        self.assertTrue(result['bars_trial_pass']);self.assertFalse(result['guard_policy_unchanged'])
        self.assertFalse(result['ethernet_proven']);self.assertEqual(result['observed_field_rows'],19)
        for before,after in ((b'CHECKS=14452',b'CHECKS=65537'),(b'CHECKS=14452',b'CHECKS=14453'),(b'CALLS=3612',b'CALLS=3611'),
            (b'PCIE_GUARD_COMPOSITION_TRIAL',b'PCIE_OWNER_TRACE_TRIAL')):
            with self.assertRaises(ValueError):p.inspect(data.replace(before,after),report)
        changed=copy.deepcopy(report);changed['owner_trace']['guard_policy_unchanged']=True
        with self.assertRaises(ValueError):p.inspect(data,changed)
        changed=copy.deepcopy(report);changed['guard_composition']['cumulative_pm_limit']=65537
        with self.assertRaises(ValueError):p.inspect(data,changed)

    def test_whole_capture_health_and_required_passive_rows(self):
        data,report=self.fixture()
        for row in [r for r in data.splitlines(keepends=True) if any(r.startswith(p.PREFIX+label.encode()+b' ') for label in ('FW','RPC','PM','TIME','IRQ'))]:
            with self.assertRaises(ValueError):p.inspect(data.replace(row,b'',1),report)
            with self.assertRaises(ValueError):p.inspect(data.replace(row,row+row,1),report)
        for signature in p.prior.prior.health.SIGNATURES:
            with self.assertRaisesRegex(ValueError,'Fault in complete'):p.inspect(data+signature+b' fixture\n',report)

    def test_actual_original_complete_capture_api(self):
        method=old.old.RootRouteSerialTests.test_actual_full_inspect_capture_api_with_timed_boot_to_nvme
        types.FunctionType(method.__code__,dict(method.__globals__,p=p))(self)

    def test_nested_pm_failure_remains_failure(self):
        method=old.OwnerSerialTests.test_nested_pm_failure_stays_diagnostic_failure
        types.FunctionType(method.__code__,dict(method.__globals__,p=p))(self)


if __name__=='__main__':unittest.main()
