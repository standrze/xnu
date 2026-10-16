# SPDX-License-Identifier: BSD-2-Clause
"""Linked table checks and refusal cases; no runtime network acceptance."""
import copy
import struct
import unittest

from tools.rpi5 import audit_apple_network_kernel as audit


class LinkedSysentTests(unittest.TestCase):
    def fixture(self):
        raw = bytearray(16000)
        struct.pack_into('<I', raw, 0, 557)
        audit.ENTRY.pack_into(raw, 8, 0x20000, 0, 1, 0, 0)
        audit.ENTRY.pack_into(raw, 8+97*24, 0x20004, 0x20008, 1, 3, 12)
        segments = [dict(vmaddr=0x10000, fileoff=0, filesize=15000, initprot=1),
                    dict(vmaddr=0x20000, fileoff=15000, filesize=1000, initprot=5)]
        symbols = '\n'.join(f'{addr:016x} external {name}' for addr,name in
                            ((0x10000,'_nsysent'), (0x10008,'_sysent'),
                             (0x20000,'_nosys'), (0x20004,'_socket'), (0x20008,'_munge_www')))
        return raw, segments, symbols

    def test_actual_pointer_not_symbol_presence_drives_acceptance(self):
        args = self.fixture()
        report = audit.linked_calls(*args, [97])
        self.assertEqual(report['calls'][0]['handler_symbols'], ['_socket'])
        self.assertEqual(report['calls'][0]['argument_count'], 3)
        self.assertFalse(report['calls'][0]['runtime_semantics_proven'])
        for target in (0x20000, 0x20008, 0, 0x10000):
            raw = args[0].copy()
            struct.pack_into('<Q', raw, 8+97*24, target)
            with self.subTest(target=target), self.assertRaises(ValueError):
                audit.linked_calls(raw, *args[1:], [97])

    def test_invalid_count_negative_control_layout_and_fields(self):
        raw, segments, symbols = self.fixture()
        changes = [(0,'<I',500),(0,'<I',1024),(8,'<Q',0),
                   (8+97*24+8,'<Q',0x10000),(8+97*24+16,'<i',8),
                   (8+97*24+20,'<h',9),(8+97*24+22,'<H',65)]
        for offset,fmt,value in changes:
            changed = raw.copy(); struct.pack_into(fmt,changed,offset,value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                audit.linked_calls(changed,segments,symbols,[97])
        for numbers in ([0],[-1],[557],[True],['97']):
            with self.subTest(numbers=numbers), self.assertRaises(ValueError):
                audit.linked_calls(raw,segments,symbols,numbers)

    def test_ambiguous_missing_ranges_symbols_and_truncation(self):
        raw, segments, symbols = self.fixture()
        for listing in ('',symbols+'\n'+symbols, symbols.replace('_socket','_other')):
            with self.assertRaises(ValueError): audit.linked_calls(raw,segments,listing,[97])
        for mutation in ('overlap','protection','file-end','table-end'):
            changed = copy.deepcopy(segments)
            if mutation == 'overlap': changed.append(changed[0].copy())
            if mutation == 'protection': changed[1]['initprot'] = 1
            if mutation == 'file-end': changed[1]['fileoff'] = len(raw)
            if mutation == 'table-end': changed[0]['filesize'] = 100
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                audit.linked_calls(raw,changed,symbols,[97])
        with self.assertRaises(ValueError): audit.linked_calls(raw[:4],segments,symbols,[97])

    def test_preserved_kernel_real_command_inventories(self):
        result = audit.audit()
        self.assertEqual(len(result['linked_sysent']['calls']),36)
        self.assertEqual(result['trap_counts'],dict(ifconfig=37,route=40))
        self.assertTrue(result['network_syscalls_bound_to_real_handlers'])
        for field in ('pi_utilities_executed','socket_semantics_proven','nic_ready',
                      'mach_traps_platform_calls_and_isa_qualified','serial_actions','sd_actions','reboots'):
            self.assertFalse(result[field],field)


if __name__ == '__main__': unittest.main()
