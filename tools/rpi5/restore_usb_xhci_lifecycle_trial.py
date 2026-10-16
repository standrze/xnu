#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Restore the exact normal zsh loader after the USB lifecycle trial."""
from tools.rpi5 import restore_usb_xhci_caps_trial as restore


def main():
    restore.CANDIDATE_SHA = "c36773d70f8f6eb9760200fbc87150c9620c5e039f08d58bc8ffaf536ae2bfb9"
    restore.RESTORE_PROFILE = "rpi5-usb-xhci-lifecycle-restore-v1"
    return restore.main()


if __name__ == "__main__":
    raise SystemExit(main())
