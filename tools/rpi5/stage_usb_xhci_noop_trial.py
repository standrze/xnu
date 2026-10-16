#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Guard and stage one bounded USB0 xHCI No-Op image; never reboot."""
from tools.rpi5 import check_usb_xhci_noop_trial as noop_check
from tools.rpi5 import stage_usb_xhci_caps_trial as stage


def main():
    stage.package_check = noop_check
    stage.MANIFEST_SHA = "044d6a63897f8318bbe403b2c55dd7a9836eab6b5383b4963238c0e3d5d2d6e5"
    stage.STAGE_PROFILE = "rpi5-usb-xhci-noop-stage-v1"
    return stage.main()


if __name__ == "__main__":
    raise SystemExit(main())
