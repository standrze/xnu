#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bounded zero-transmit recorder for one USB0 K65 first-report boot."""
from tools.rpi5 import check_usb_xhci_keyboard_trial as keyboard_check
from tools.rpi5 import parse_usb_xhci_keyboard_trial as keyboard_evidence
from tools.rpi5 import record_usb_xhci_caps_trial as recorder


def main():
    recorder.package_check = keyboard_check
    recorder.evidence = keyboard_evidence
    recorder.MARKER_PREFIX = "RPI5XNU:USB_XHCI_KBD:ENTRY TAG="
    recorder.ARMED_MESSAGE = "USB_XHCI_KBD_CAPTURE_ARMED ZERO_SERIAL_TX"
    return recorder.main()


if __name__ == "__main__":
    raise SystemExit(main())
