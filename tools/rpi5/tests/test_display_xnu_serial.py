# SPDX-License-Identifier: BSD-2-Clause
"""Actual frozen report/boot grammar and original interactive-zsh command oracle."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from tools.rpi5 import display_xnu_serial as p
ROOT=Path(__file__).resolve().parents[3]
REPORT=ROOT/'build/rpi5/display-xnu-console-qualification-20261014/checker-report.json'
def report():return json.loads(REPORT.read_text())
def boot(r=None):
    r=r or report()
    values=[p.SD,b'Read probe.bin bytes '+str(r['image_bytes']).encode()+b' hnd 0x0',
        p.zsh.ENTRY+b'0000000000000001',p.zsh.TERMINAL_LOADER,r['trial_marker'].encode(),
        b'RPI5XNU:DISPLAYXNU:ALLOCATE_BEGIN SAME_BOOT FOUR_TX_MAX ONE_ALLOCATE NO_FB_ACCESS',
        r['allocation_complete_marker'].encode(),
        b'RPI5XNU:DISPLAYXNU:OWNED START=000000003f400000 END=000000003fbec000 MANAGED_UNCHANGED NO_LOADER_DRAW RETAIN_UNTIL_RESET',
        p.DEVICE,p.FDT,p.HANDOFF,r['root_copy_marker'].encode(),r['kernel_copy_marker'].encode(),
        p.zsh.package_check.TOPOLOGY_PASS,p.zsh.TRANSFER,p.COMMIT,r['root_mount_marker'].encode(),
        p.MIRROR,p.zsh.READY,b'xnu:/# ',p.WATCHDOG,p.ROOT_READY,p.zsh.READY,b'xnu:/# ']
    return b'\r\n'.join(values)
def response(name,n):
    _,command,expected,prompt=next(v for v in p.exchanges(n) if v[0]==name)
    if name=='launch':lines=[b'DARWIN:ZSH:ENTRY',b'DARWIN:ZSH:TSD',b'DARWIN:ZSH:ENTROPY',b'DARWIN:ZSH:MAIN']*2
    else:lines=expected
    return command.encode()+b'\r\n'+b'\r\n'.join(lines)+b'\r\n'+(b'pi-zsh# ' if name in ('launch','proof') else b'xnu:/# ')

class DisplayXNUSerialTests(unittest.TestCase):
    def test_actual_report_admission_and_each_required_marker(self):
        raw=boot();self.assertTrue(p.boot_ready(raw,report()))
        for marker in (p.MIRROR,p.WATCHDOG,p.ROOT_READY,p.COMMIT,p.HANDOFF,p.DEVICE,p.FDT,report()['trial_marker'].encode()):
            with self.subTest(marker=marker):self.assertFalse(p.boot_ready(raw.replace(marker,b'MISSING'),report()))
        # The early recovery prompt cannot admit input before delayed readiness.
        self.assertFalse(p.boot_ready(raw[:raw.index(p.WATCHDOG)],report()))
        for bad in (raw+b'\r\n'+p.MIRROR+b'\r\n',raw.replace(b'NODES=32 BYTES=1916928',b'NODES=33 BYTES=1916928'),
            raw+b'\r\nRPI5XNU:DISPLAYXNU:OWNED MALFORMED\r\n',
            raw.replace(b'COMPLETED=000000000000000f',b'COMPLETED=0000000000000007'),raw+b'\r\nBoot mode: NVME (06)\r\n'):
            with self.assertRaises(ValueError):p.boot_ready(bad,report())
    def test_late_root_repeats_exactly_bounded_and_no_order_guess(self):
        raw=boot();self.assertTrue(p.boot_ready(raw+b'\r\n'+p.ROOT_READY+b'\r\n'+p.ROOT_READY+b'\r\n',report()))
        with self.assertRaises(ValueError):p.boot_ready(raw+(b'\r\n'+p.ROOT_READY+b'\r\n')*3,report())
        values=raw.replace(p.MIRROR,b'PLACEHOLDER').replace(p.WATCHDOG,p.MIRROR).replace(b'PLACEHOLDER',p.WATCHDOG)
        self.assertTrue(p.boot_ready(values,report()))
    def test_actual_four_commands_nonce_outputs_and_status_negatives(self):
        n='D'+'a'*16
        for name,command,expected,prompt in p.exchanges(n):
            raw=response(name,n);self.assertTrue(p.inspect_exchange(raw,name,n)['actual_output_verified'])
            self.assertLessEqual(len(command),1023)
            if expected:
                with self.assertRaises(ValueError):p.inspect_exchange(raw.replace(expected[-1],expected[-1]+b'X'),name,n)
        raw=response('proof',n)
        for bad in (raw.replace(b'VERSION:5.9',b'VERSION:0'),raw.replace(b'EXEC_STATUS:0',b'EXEC_STATUS:1'),
                    raw.replace(b'SMOKE_STATUS:0',b'SMOKE_STATUS:1'),raw+b'\r\nDX:'+n.encode()+b':EXTERNAL\r\n'):
            with self.assertRaises(ValueError):p.inspect_exchange(bad,'proof',n)
        with self.assertRaises(ValueError):p.exchanges("D';reboot")
    def test_actual_embedded_smoke_and_host_zsh_command_semantics(self):
        # Host zsh validates syntax/status framing only. Never execute the
        # embedded target Mach-O; the unmodified embedded script is text.
        r=report();package=Path(r['package']);packed=(package/'payload.bin').read_bytes()
        kind,flags,offset,size,digest,zero=struct.unpack_from('<IIQQ32sQ',packed,128)
        self.assertEqual((kind,flags,zero),(2,0,0));root=packed[offset:offset+size]
        self.assertEqual(hashlib.sha256(root).hexdigest(),r['root_sha256'])
        catalog=json.loads((package/'root-catalog.json').read_text())
        script=next(v for v in catalog['entries'] if v['path']=='/etc/zsh-smoke.zsh')
        self.assertEqual(script['size'],211);body=root[script['offset']:script['offset']+script['size']]
        n='D'+'a'*16;_,command,expected,_=p.exchanges(n)[1]
        with tempfile.TemporaryDirectory(prefix='display-xnu-host-zsh-') as folder:
            path=Path(folder)/'smoke.zsh';path.write_bytes(body)
            actual=command.replace('/etc/zsh-smoke.zsh',str(path))
            result=subprocess.run(['/bin/zsh','-f','-c',actual],capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,b'')
            p.exact_lines(result.stdout,expected)
            bad=subprocess.run(['/bin/zsh','-f','-c',actual.replace('/bin/echo '+ 'DX:'+n+':EXTERNAL','/usr/bin/false')],capture_output=True,timeout=10)
            with self.assertRaises(ValueError):p.exact_lines(bad.stdout,expected)
    def test_whole_tail_faults_and_pending_unknown(self):
        for tail in (b'panic(cpu0): fail',b'panic: fail',b'Debugger message: panic',b'RPI5XNU:RETURN:FAULT 1'):
            with self.assertRaises(ValueError):p.healthy(boot()+p.BOOTSYS+p.NVME+tail)
        p.pending_safe(b'\nRPI5XNU:SHELL:READY\nxnu:/# '+p.ROOT_READY+b'\n')
        with self.assertRaises(ValueError):p.pending_safe(b'Linux version1')
if __name__=='__main__':unittest.main()
