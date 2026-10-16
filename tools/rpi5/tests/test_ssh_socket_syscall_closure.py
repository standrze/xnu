#!/usr/bin/env python3
"""Static instruction/alias/cancellation closure, not socket runtime proof."""
import json
from pathlib import Path
import struct
import unittest
from tools.rpi5 import build_apple_ssh_socket_syscalls as build
from tools.rpi5 import check_apple_pthread_kernel_contract as macho
from tools.rpi5.tests.test_ssh_full_client_closure import actual_dependencies

PACKAGE=build.ROOT/'build/rpi5/apple-ssh-socket-syscalls-n4wc59z7'
SHA='f036194116d2048dc4102f3728191b7bd6f449cf95c5f58c78be9785662b677b'
LINKED=build.ROOT/'build/rpi5/apple-ssh-socket-contract-swo77b1n'
LINKED_SHA='876918a228b8accfa4a65c57013f99bab5bed48735d20f78cdc1bddddbbdc27f'


def bl_target(image,address):
    word=struct.unpack('<I',image.at(address,4))[0]
    if word>>26!=0b100101:raise ValueError('Not an actual BL instruction')
    offset=word&0x3ffffff
    if offset&(1<<25):offset-=1<<26
    return address+offset*4


class SocketClosure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE/'manifest.json')!=SHA or build.sha(LINKED/'manifest.json')!=LINKED_SHA:
            raise ValueError('Frozen receipt changed')
        cls.report=json.loads((PACKAGE/'manifest.json').read_text())
        cls.linked=json.loads((LINKED/'manifest.json').read_text())

    def test_actual_generated_object_instructions_aliases_errors(self):
        r=self.report;image=macho.MachO(Path(self.linked['target']))
        for name,number in build.CALLS.items():
            obj=macho.MachO(Path(r['objects'][name]));public=obj.names['_'+name]['address']
            if '___'+name in obj.names:self.assertEqual(obj.names['___'+name]['address'],public)
            words=struct.unpack('<10I',obj.at(public,40))
            self.assertEqual(words[0],0xd2800010|(number<<5))
            self.assertEqual(words[1],0xd4001001) # svc #0x80
            self.assertEqual(words[2],0x540000e3) # success skips real error path
            self.assertEqual(words[5],0x94000000) # genuine external handler relocation
            self.assertEqual(words[8:],(0xd65f03c0,0xd65f03c0))
            handler='_cerror' if name in build.CANCEL else '_cerror_nocancel'
            actual=image.names['_'+name]['address']
            self.assertEqual(bl_target(image,actual+20),image.names[handler]['address'])
            undefined=Path(PACKAGE/(name+'-undefined.stdout')).read_text().splitlines()
            self.assertEqual(undefined,[handler])
        at=image.names['_cerror']['address']
        self.assertEqual(bl_target(image,at+16),image.names['__pthread_exit_if_canceled']['address'])
        self.assertEqual(bl_target(image,at+24),image.names['_cerror_nocancel']['address'])
        errno=image.names['_cerror_nocancel']['address']
        self.assertIn(struct.pack('<I',0xd53bd068),image.at(errno,40)) # actual TPIDRRO_EL0
        with self.assertRaises(ValueError):bl_target(image,at)

    def test_all_byte_pins_and_actual_dependency_membership(self):
        for r in (self.report,self.linked):
            for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
                for n,h in r.get(key,{}).items():self.assertEqual(build.sha(n),h,n)
        actual_dependencies(self.report)
        bad=dict(self.report,headers_sha256=dict(self.report['headers_sha256']))
        bad['headers_sha256'].pop(next(iter(bad['headers_sha256'])))
        with self.assertRaises(ValueError):actual_dependencies(bad)
        self.assertEqual(self.report['generator_environment'],{'ARCHS':'arm64'})
        self.assertEqual((Path(self.report['generated_directory'])/'SYS.h').read_bytes(),
                         (build.ROOT/'libsyscall/custom/SYS.h').read_bytes())

    def test_full_client_delta_separate_from_forced_contract(self):
        r=self.report
        self.assertEqual(r['previous_missing_count'],102)
        self.assertEqual(len(r['target_missing_symbols']),90)
        self.assertEqual(r['closed_symbols'],sorted('_'+n for n in build.CALLS))
        self.assertEqual(r['target_duplicate_symbols'],[])
        self.assertFalse(r['target_link_complete'])
        self.assertFalse(r['target_executed'])
        self.assertFalse(r['kernel_sysent_rechecked'])
        self.assertTrue(self.linked['target_link_complete'])
        self.assertTrue(self.linked['not_full_client'])
        self.assertFalse(self.linked['target_executed'])
        self.assertFalse(self.linked['host_sockets_executed'])
        self.assertEqual((LINKED/'undefined.stdout').read_text(),'')


if __name__=='__main__':unittest.main()
