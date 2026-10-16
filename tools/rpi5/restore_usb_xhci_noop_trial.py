#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Restore the exact normal zsh loader after the USB No-Op trial."""
from tools.rpi5 import restore_usb_xhci_caps_trial as restore


def main():
    restore.CANDIDATE_SHA = "87443667ab25cc2a047e3b23a2719e6fc232bd67a7feff03ac3ad36b1973dcc5"
    restore.RESTORE_PROFILE = "rpi5-usb-xhci-noop-restore-v1"
    return restore.main()


if __name__ == "__main__":
    raise SystemExit(main())
