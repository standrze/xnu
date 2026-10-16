# SPDX-License-Identifier: BSD-2-Clause
"""Distinct source-only bounded UART/PM accessors; no frozen owner mutation."""
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SERIAL=ROOT/'pexpert/arm/pe_serial.c'
SERIAL_SHA='e603267e9b6948f8eedd59afb199d38a33621e44e91ba7a39f7aa42986cbd6b2'
FIQ=ROOT/'build/rpi5/root42-confirmed-kernel-20261013-final/pe_fiq.c'
FIQ_SHA='c73847b1963ddb47b7d362fda20b85e577203c2fe37ecc709553bb12749ba74a'
PRIMARY=ROOT/'tools/rpi5/primary/restart_diag_linux_v6_12_bcm2835_wdt.c'
PRIMARY_SHA='ad001fbe5429463918526011531a910c43af2df8bd6f7e8f3dbb34e1ca82d9d3'
PRIMARY_URL='https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/watchdog/bcm2835_wdt.c'
READY='''\t\tkprintf("\\nRPI5XNU:TERMINAL:WATCHDOG_READY SECONDS=%u\\n",
\t\t    RPI5_TERMINAL_WDOG_SECONDS);'''

def checked(raw,pin):
    if hashlib.sha256(raw.encode()).hexdigest()!=pin:raise ValueError('Exact accepted owner source required')
    return raw

def serial_source(raw):
    return checked(raw,SERIAL_SHA)+'\n#include "pexpert/arm/rpi5_restart_diag_uart.inc"\n'

def fiq_source(raw):
    checked(raw,FIQ_SHA)
    if raw.count(READY)!=1:raise ValueError('Exact delayed successful-reload READY branch required')
    return '#include "pexpert/arm/rpi5_restart_diag_api.h"\n'+raw.replace(READY,READY+'\n\t\trpi5_restart_diagnostic_boot_ready();',1)+\
        '\n#include "pexpert/arm/rpi5_restart_diag_pm.inc"\n'

def sources():
    if hashlib.sha256(PRIMARY.read_bytes()).hexdigest()!=PRIMARY_SHA:raise ValueError('Original nominal PM encoding source changed')
    return [Path(__file__),PRIMARY,ROOT/'pexpert/arm/rpi5_restart_diag_api.h',
            ROOT/'pexpert/arm/rpi5_restart_diag_uart.inc',ROOT/'pexpert/arm/rpi5_restart_diag_pm.inc',
            ROOT/'tools/rpi5/tests/restart_diag_access_host.c',ROOT/'tools/rpi5/tests/test_restart_diag_access.py']
