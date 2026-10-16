#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Guard and stage one bounded USB0 K65 enumeration image; never reboot."""
from tools.rpi5 import check_usb_xhci_enumerate_trial as enumeration_check
from tools.rpi5 import stage_usb_xhci_caps_trial as stage


def main():
    stage.package_check = enumeration_check
    stage.MANIFEST_SHA = "5928699eab7e62f07d2bc061bf37fbe11585afaeae2ae9c2fb4a9da900ab4dcb"
    stage.STAGE_PROFILE = "rpi5-usb-xhci-enumerate-stage-v1"
    return stage.main()


if __name__ == "__main__":
    raise SystemExit(main())
