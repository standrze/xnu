#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Guard and stage the USB keyboard console candidate; never reboot."""
from tools.rpi5 import check_usb_xhci_keyboard_console_trial as console_check
from tools.rpi5 import stage_usb_xhci_caps_trial as stage


def main():
    stage.package_check = console_check
    stage.MANIFEST_SHA = \
        "8c5e9111a40399bdeb277663cda71206bd5ad5fa5ccb8c91b2917a988c0a8e3a"
    stage.STAGE_PROFILE = "rpi5-usb-xhci-keyboard-console-stage-v1"
    return stage.main()


if __name__ == "__main__":
    raise SystemExit(main())
