#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Restore the exact normal zsh loader after the USB enumeration trial."""
from tools.rpi5 import restore_usb_xhci_caps_trial as restore


def main():
    restore.CANDIDATE_SHA = "202a336986fed5d5b53ebc624dc481499ee99c0204906cb7eb59f1bc604c1ab3"
    restore.RESTORE_PROFILE = "rpi5-usb-xhci-enumerate-restore-v1"
    return restore.main()


if __name__ == "__main__":
    raise SystemExit(main())
