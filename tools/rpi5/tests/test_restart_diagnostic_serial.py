# SPDX-License-Identifier: BSD-2-Clause
import copy
import unittest
from tools.rpi5 import restart_diagnostic_serial as p
from tools.rpi5.tests import test_display_xnu_serial as old

def report():
    value=old.report();value.update(trial_marker=value['trial_marker'].replace('DISPLAYXNU:ENTRY','DISPLAYRESTART_DIAG:ENTRY'),
        root_ready_marker=p.ROOT_READY.decode(),restart_ready_marker=p.READY.decode())
    return value

def boot():
    return old.boot(report()).replace(old.p.ROOT_READY,p.ROOT_READY)+b'\n'+p.READY+b'\n'+p.zsh.READY+b'\nxnu:/# '

def trace(n='D'+'a'*16):
    return (p.restart_command(n).encode()+b'\nDR:'+n.encode()+b':EXEC_REBOOT\nPTHREAD:KERNEL_READY\nPTHREAD:MAIN_READY\n'
        b'RPI5XNU:RESTART:PRE_SMC COUNT=000e0000 COUNTER=0000000000000066 FREQ=0000000000000064 DEADLINE=0000000000004650 NOMINAL_HZ=00010000 RATE_BOUND=0\n'+
        p.BOOTSYS+b' new\n')

class RestartDiagnosticSerialTests(unittest.TestCase):
    def test_fresh_root33_mirror_and_restart_ready_before_prompt(self):
        self.assertTrue(p.boot_ready(boot(),report()))
        self.assertFalse(p.boot_ready(boot().replace(p.READY,b'MISSING'),report()))
        for bad in (boot()+b'\n'+p.READY+b'\n',boot().replace(p.ROOT_READY,old.p.ROOT_READY)):
            with self.assertRaises(ValueError):p.boot_ready(bad,report())
        self.assertFalse(p.boot_ready(boot().split(p.READY)[0]+p.READY,report()))
    def test_ordered_actual_path_and_nominal_only_timing(self):
        result=p.reboot_observation(trace(),'D'+'a'*16,100,105)
        self.assertTrue(result['ordered_real_reboot_path_observed']);self.assertTrue(result['nominal_early_return'])
        self.assertFalse(result['physical_psci_causality_proven']);self.assertFalse(result['unconditional_not_watchdog_proven'])
        self.assertFalse(p.reboot_observation(trace(),'D'+'a'*16,100,113)['nominal_early_return'])
        # A buffered pre-SMC marker cannot reduce the interval; the argument
        # is the retained TX START, not a timestamp attached to that marker.
        self.assertFalse(p.reboot_observation(trace(),'D'+'a'*16,100,200)['nominal_early_return'])
    def test_echo_return_missing_and_malformed_never_claim_path(self):
        raw=trace();n='D'+'a'*16
        failures=[raw.replace(b'\nDR:'+n.encode()+b':EXEC_REBOOT\n',b'\n'),
            raw+b'RPI5XNU:RESTART:RETURNED NO_RESET_PROVEN\n',raw+b'panic(cpu0): bad\n',
            raw.replace(b'COUNT=000e0000',b'COUNT=00100000'),raw.replace(b'RATE_BOUND=0',b'RATE_BOUND=1'),
            raw.replace(b'PTHREAD:MAIN_READY',b'MISSING'),raw.replace(p.BOOTSYS,b'MISSING'),
            raw.replace(p.PRE_PREFIX,b'MISSING'),raw+b'DR:'+n.encode()+b':RETURNED:0\n']
        for bad in failures:
            with self.assertRaises(ValueError):p.reboot_observation(bad,n,100,105)
        with self.assertRaises(ValueError):p.reboot_observation(raw,n,True,105)
