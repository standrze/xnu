import unittest
from pathlib import Path

from tools.rpi5 import stage_usb_xhci_caps_trial as stage


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "build/rpi5/usb-xhci-caps-candidate-20261014-v4"


class USBXHCICapabilityStageTests(unittest.TestCase):
    def test_plan_is_exact_and_does_not_reboot(self):
        value = stage.plan(PACKAGE, "b78ce2fc-b053-4277-a2e9-34cada155cda")
        self.assertEqual(value["candidate_sha256"],
                         "4435959ce5181d810a9e1638e6b68eabf94fe2c35c59685b63a4d380f74f0782")
        self.assertTrue(value["no_reboot"])
        self.assertTrue(value["normal_config_preserved"])
        self.assertTrue(value["normal_firmware_preserved"])
        self.assertEqual(value["firmware_sha256"], stage.TRIAL_FIRMWARE_SHA)
        self.assertEqual(value["config_sha256"], stage.TRIAL_CONFIG_SHA)
        self.assertEqual(value["replace_only"], ["probe.bin", "bl31.bin", "config.txt"])
        self.assertNotIn("['reboot'", stage.REMOTE)
        self.assertNotIn("['shutdown'", stage.REMOTE)

    def test_wrong_boot_id_fails(self):
        with self.assertRaises(ValueError):
            stage.plan(PACKAGE, "not-a-uuid")


if __name__ == "__main__":
    unittest.main()
