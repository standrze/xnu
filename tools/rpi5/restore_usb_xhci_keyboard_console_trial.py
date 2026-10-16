#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Restore the exact normal zsh image after the USB console trial."""
from tools.rpi5 import restore_usb_xhci_caps_trial as restore


def main():
    restore.CANDIDATE_SHA = \
        "d3b6b4736d61893fe6709fb81f6aecdd529087dae05bd18a9451d6672edc6a84"
    restore.RESTORE_PROFILE = "rpi5-usb-xhci-keyboard-console-restore-v1"
    return restore.main()


if __name__ == "__main__":
    raise SystemExit(main())
