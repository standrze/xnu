#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bounded zero-transmit recorder for one RP1 USB0 xHCI No-Op boot."""
from tools.rpi5 import check_usb_xhci_noop_trial as noop_check
from tools.rpi5 import parse_usb_xhci_noop_trial as noop_evidence
from tools.rpi5 import record_usb_xhci_caps_trial as recorder


def main():
    recorder.package_check = noop_check
    recorder.evidence = noop_evidence
    recorder.MARKER_PREFIX = "RPI5XNU:USB_XHCI_NOOP:ENTRY TAG="
    recorder.ARMED_MESSAGE = "USB_XHCI_NOOP_CAPTURE_ARMED ZERO_SERIAL_TX"
    return recorder.main()


if __name__ == "__main__":
    raise SystemExit(main())
