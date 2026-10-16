# SPDX-License-Identifier: BSD-2-Clause
"""Byte-only independent stack receipt checks; never invokes a compiler."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from tools.rpi5 import audit_reservation_kernel_stack as audit
ROOT=audit.ROOT
RECEIPT=ROOT/'build/rpi5/reservation-kernel-stack-audit-20261014-v5/audit.json'
SHA='3af083d3e5c267432d775437db33c8872a5a5ffb2ee28cf701f9781d68e9af2a'
class ReservationKernelStackAuditTests(unittest.TestCase):
    def test_actual_receipt_byte_closure_exact_owner_code_and_stack(self):
        self.assertEqual(audit.sha(RECEIPT),SHA);r=json.loads(RECEIPT.read_bytes())
        for key in ('inputs_sha256','generated_sha256'):
            for p,digest in r[key].items():self.assertEqual(audit.sha(p),digest,p)
        self.assertEqual(r['maximum_conservative_bytes'],11312)
        self.assertEqual(r['stack_bytes'],16384);self.assertEqual(r['minimum_remaining_bytes'],5072)
        self.assertLess(r['maximum_conservative_bytes']+r['required_margin_bytes'],r['stack_bytes'])
        self.assertEqual(r['scalar_final_vla_bound_bytes'],112)
        self.assertFalse(r['hardware_executed'])
        for row in r['commands']:
            self.assertEqual(row['returncode'],0);self.assertEqual(audit.sha(row['log']),row['log_sha256'])
            cmd=row['command'];measured=Path(cmd[cmd.index('-o')+1]);name=measured.stem
            old=audit.PHY/'fdt.c.o' if name=='fdt' else audit.display.OBJ/'osfmk/DEVELOPMENT'/(name+'.o')
            self.assertEqual(audit.text_bytes(measured),audit.text_bytes(old))
    def test_section_reader_rejects_bad_magic_or_out_of_bounds(self):
        original=(audit.PHY/'fdt.c.o').read_bytes()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.o'
            for bad in (b'',bytes(32),original[:33]):
                p.write_bytes(bad)
                with self.assertRaises((ValueError, __import__('struct').error)):audit.text_bytes(p)
    def test_stack_parser_rejects_missing_negative_or_duplicate_frames(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.su'
            for bad in ('','x.c:1:bad\t-1\tstatic\n','x.c:1:bad\t16\tstatic\nx.c:2:bad\t16\tstatic\n'):
                p.write_text(bad)
                with self.assertRaises(ValueError):audit.frames(p)
if __name__=='__main__':unittest.main()
