# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic budget-boundary diagnosis; not a claimed physical failure cause.

Reuse the independent actual owner/secure composition without editing it. Only
the finite PM check count is seeded after its genuine full fixture succeeds.
"""
import unittest
from unittest.mock import patch
from tools.rpi5.tests import test_pcie_owner_composition as composition


class OwnerBudgetBoundaryTests(unittest.TestCase):
    def test_first_firmware_guard_can_fail_pm_budget_without_smc(self):
        prefix = composition.MAIN.split('int main()')[0]
        main = prefix + r'''
int main(){
 BCM2712PCIePHYTransport s;prepared(s);bcm2712_rp1_observation out={};
 assert(s.runBoundedRP1Trial(&out));
 unsigned natural=rpi5_pcie_wdog_lease.checks;
 /* Explicit synthetic state injection; no hardware counter is observed. */
 s.phase=BCM2712_PHY_RP1_INSPECTING;
 rpi5_pcie_wdog_lease.checks=65532;
 unsigned smcs_before=smc_calls;
 assert(!s.guard());
 assert(s.diagGuard==4 && rpi5_pcie_wdog_lease.checks==65536);
 assert(rpi5_pcie_wdog_lease.state==RPI5_PCIE_WDOG_QUARANTINED);
 assert(rpi5_pcie_irq_session.state==RPI5_PCIE_IRQ_QUARANTINED);
 assert(rpi5_pcie_fw_session.state==RPI5_FW_CLIENT_QUARANTINED);
 assert(smc_calls==smcs_before);
 printf("OWNER_COMPOSITION_PASS SEEDED_PM_CHECKS=65532 FINAL_PM_CHECKS=%u GUARD=%u ADDITIONAL_SMC=%u NATURAL_COMPLETE_PM_CHECKS=%u NO_BOARD_CAUSE_CLAIM\n",
 rpi5_pcie_wdog_lease.checks,s.diagGuard,smc_calls-smcs_before,natural);
 return 0;
}
'''
        with patch.object(composition, 'MAIN', main):
            composition.OwnerCompositionTests('test_real_guard_owners_cores_and_bar_caller').test_real_guard_owners_cores_and_bar_caller()


if __name__ == '__main__':
    unittest.main()
