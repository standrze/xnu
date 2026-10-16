#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Restore the exact normal zsh loader after the USB keyboard trial."""
from tools.rpi5 import restore_usb_xhci_caps_trial as restore


def main():
    restore.CANDIDATE_SHA = "1465c35d1aff61618009efb824a998ea7c5a9ea2d977460d9243bf673a9dbf11"
    restore.RESTORE_PROFILE = "rpi5-usb-xhci-keyboard-restore-v1"
    return restore.main()


if __name__ == "__main__":
    raise SystemExit(main())
