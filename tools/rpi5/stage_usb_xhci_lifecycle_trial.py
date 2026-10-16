#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Guard and stage one bounded USB0 xHCI lifecycle image; never reboot."""
from tools.rpi5 import check_usb_xhci_lifecycle_trial as lifecycle_check
from tools.rpi5 import stage_usb_xhci_caps_trial as stage


def main():
    stage.package_check = lifecycle_check
    stage.MANIFEST_SHA = "9d9b7e1624409d77ffd5fe0dec3c43b963356143946c6abd11ea269f51c3851b"
    stage.STAGE_PROFILE = "rpi5-usb-xhci-lifecycle-stage-v1"
    return stage.main()


if __name__ == "__main__":
    raise SystemExit(main())
