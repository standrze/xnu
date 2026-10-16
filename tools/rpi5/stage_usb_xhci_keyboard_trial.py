#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Guard and stage one bounded USB0 K65 first-report image; never reboot."""
from tools.rpi5 import check_usb_xhci_keyboard_trial as keyboard_check
from tools.rpi5 import stage_usb_xhci_caps_trial as stage


def main():
    stage.package_check = keyboard_check
    stage.MANIFEST_SHA = "4b73b5f4888665238fe9a4e2c666d5dc70f542ec42eda9b29ca3f960cca737fe"
    stage.STAGE_PROFILE = "rpi5-usb-xhci-keyboard-stage-v1"
    return stage.main()


if __name__ == "__main__":
    raise SystemExit(main())
