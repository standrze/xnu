# SPDX-License-Identifier: BSD-2-Clause
"""Exact delayed-report grammar across admission, proof, pending and reboot."""
import copy
import json
import unittest
from tools.rpi5 import restart_late_serial as p, stage_restart_late_trial as stage
from tools.rpi5.tests import test_display_xnu_serial as old
from tools.rpi5.tests.test_restart_diagnostic_serial import trace

def boot(report):
    return old.boot(report).replace(old.p.ROOT_READY,p.ROOT_READY)+b'\r\n'+p.READY+b'\r\n'+p.INIT_READY+b'\r\n'+p.zsh.READY+b'\r\nxnu:/# '

class RestartLateSerialTests(unittest.TestCase):
    def setUp(self):self.report=json.loads(stage.REPORT.read_text());self.n='D0123456789abcdef'
    def test_actual_report_one_through_three_ready_before_prompt(self):
        raw=boot(self.report)
        for count in (1,2,3):
            data=raw.replace(p.INIT_READY,b'\n'.join([p.INIT_READY]*count))
            self.assertTrue(p.boot_ready(data,self.report));p.healthy(data)
        for value in (True,3.0,4):
            report=copy.deepcopy(self.report);report['init_shutdown_ready_max_reports']=value
            with self.assertRaises(ValueError):p.boot_ready(raw,report)
        self.assertFalse(p.boot_ready(raw.replace(p.INIT_READY,b'MISSING'),self.report))

    def test_repeats_during_proof_pending_and_reboot_preserve_raw(self):
        row=b'\n'+p.INIT_READY+b'\n'
        response=old.response('proof',self.n)
        for offset in (0,response.index(b'\nDX:')+1,response.rfind(b'pi-zsh# ')):
            modified=response[:offset]+row+response[offset:]
            result=p.inspect_exchange(modified,'proof',self.n)
            self.assertEqual(result['response_sha256'],p.hashlib.sha256(modified).hexdigest())
            p.healthy(boot(self.report)+modified+row)
        p.pending_safe(row);p.pending_safe(row+row)
        for suffix in (b'unknown\n',b'panic(cpu0): bad\n'):
            with self.assertRaises(ValueError):p.pending_safe(row+suffix)
        reboot=trace(self.n)
        for offset in (0,reboot.index(b'PTHREAD:KERNEL_READY'),reboot.index(p.PRE_PREFIX)):
            modified=reboot[:offset]+row+reboot[offset:]
            self.assertTrue(p.reboot_observation(modified,self.n,100,102)['nominal_early_return'])
            p.healthy(boot(self.report)+modified)

    def test_fourth_malformed_corruption_faults_and_post_reset_never_admitted(self):
        base=boot(self.report);row=b'\n'+p.INIT_READY+b'\n'
        for wrong in (p.INIT_READY+b' EXTRA',p.INIT_READY.replace(b'BLOCKED',b'UNBLOCKED'),
                b'xnu:/# '+p.INIT_READY,p.INIT_READY.replace(b'POLLED',b'POLL?D'),
                p.INIT_READY.replace(b'SHUTDOWN_READY',b'SHUTDOWN_RE?DY')):
            data=base+b'\n'+wrong+b'\n'+row
            with self.assertRaises(ValueError):p.healthy(data)
            with self.assertRaises(ValueError):p.pending_safe(b'\n'+wrong+b'\n')
        with self.assertRaises(ValueError):p.healthy(base+row*3)
        with self.assertRaises(ValueError):p.healthy(base+row*2+b'\n'+p.INIT_PREFIX)
        for anchor in (p.STOP_PREFIX,p.PRE_PREFIX,p.BOOTSYS):
            with self.assertRaises(ValueError):p.healthy(base+anchor+b' anything\n'+row)
        for cut in range(len(p.INIT_PREFIX),len(p.INIT_READY)):
            partial=b'\n'+p.INIT_READY[:cut]
            p.healthy(base+partial)
            with self.assertRaises(ValueError):p.pending_safe(partial)
        with self.assertRaises(ValueError):p.healthy(base+row+b'panic(cpu0): still fatal\n')

    def test_actual_failed_early_publication_capture_is_not_reclassified(self):
        path=stage.ROOT/'build/rpi5/restart-init-capture-20261014/serial.bin'
        self.assertEqual(stage.sha(path),'e2d89873cb76701c12e23c1b51d78b486d8a3ab950e13edd184745034d32e31c')
        raw=path.read_bytes();self.assertNotIn(p.INIT_READY,raw)
        with self.assertRaises(ValueError):p.boot_ready(raw,self.report)

if __name__=='__main__':unittest.main()
