#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bounded zero-transmit recorder for one RP1 USB0 xHCI lifecycle boot."""
from tools.rpi5 import check_usb_xhci_lifecycle_trial as lifecycle_check
from tools.rpi5 import parse_usb_xhci_lifecycle_trial as lifecycle_evidence
from tools.rpi5 import record_usb_xhci_caps_trial as recorder


def main():
    recorder.package_check = lifecycle_check
    recorder.evidence = lifecycle_evidence
    recorder.MARKER_PREFIX = "RPI5XNU:USB_XHCI_LIFECYCLE:ENTRY TAG="
    recorder.ARMED_MESSAGE = "USB_XHCI_LIFECYCLE_CAPTURE_ARMED ZERO_SERIAL_TX"
    return recorder.main()


if __name__ == "__main__":
    raise SystemExit(main())
