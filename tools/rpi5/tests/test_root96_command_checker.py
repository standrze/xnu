# SPDX-License-Identifier: BSD-2-Clause
"""Read-only actual-package admission and in-memory negative controls."""
import copy
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
from tools.rpi5 import check_root96_command_package as checker


class CommandPackageCheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package=checker.PACKAGE
        cls.record=json.loads((cls.package/'manifest.json').read_text())

    def reject_record(self,change,reason):
        record=copy.deepcopy(self.record);change(record)
        with self.assertRaisesRegex(ValueError,reason):checker.inspect_record(self.package,record)

    def test_actual_fixed_candidate_and_honest_runtime_requirements(self):
        result=checker.inspect(self.package)
        self.assertTrue(result['preflight_pass'])
        self.assertEqual((result['root_nodes'],result['root_files'],result['generated_count']),(41,29,37))
        self.assertEqual(result['actual_dependency_counts'],{'init':11,'shell':12,'identity':153})
        self.assertEqual(result['reconstructed_command_count'],11)
        self.assertFalse(result['limits']['build_time_tool_identity_pinned'])
        self.assertFalse(result['limits']['legacy_recovery_full_source_reproducible'])
        self.assertTrue(result['limits']['legacy_recovery_object_byte_replay'])
        self.assertTrue(result['limits']['canonical_uname_wc_hexdump_are_recovery_multicall'])
        self.assertIn('/bin/pwd -P',result['required_future_trial_commands'])
        for name in ('/usr/bin/uname','/usr/bin/wc /etc/motd','/usr/bin/hexdump /etc/motd'):
            self.assertIn(name,result['required_future_trial_commands'])
        self.assertFalse(result['pi_executed']);self.assertFalse(result['ssh_daemon'])

    def test_generated_and_source_omissions_are_rejected_without_manifest_pin(self):
        # Exercise reconstruction itself, not merely the immutable-manifest hash.
        self.reject_record(lambda m:m['generated_sha256'].pop(str(self.package/'shell.o')),'generated closure')
        self.reject_record(lambda m:m['inputs_sha256'].pop(str(checker.builder.SOURCE/'runtime.h')),'input closure')
        self.reject_record(lambda m:m['inputs_sha256'].pop(str(self.package/'rootidentity_catalog.h')),'input closure')

    def test_actual_dependency_scan_drift_is_rejected(self):
        path=self.package/'shell-dependencies.stdout';read=Path.read_text
        def altered(p,*args,**kwargs):
            value=read(p,*args,**kwargs)
            return value.replace(str(checker.builder.SOURCE/'parser.h'),'') if p==path else value
        with patch.object(Path,'read_text',altered),self.assertRaisesRegex(ValueError,'dependency closure'):
            checker.inspect_record(self.package,self.record)

    def test_compile_link_and_catalog_or_alias_mutations_reject(self):
        self.reject_record(lambda m:m['commands'][2]['command'].append('-DRPI5_UNREVIEWED=1'),'compiler/link')
        self.reject_record(lambda m:m['commands'][5]['command'].remove('-static'),'compiler/link')
        self.reject_record(lambda m:m['identity_catalog'].pop(),'namespace/catalog')
        self.reject_record(lambda m:m['compatibility_regular_files'].update({'/usr/bin/wc':'/bin/cat'}),'namespace/catalog')
        self.reject_record(lambda m:m.update(pi_executed=1),'namespace/catalog')

    def test_actual_generated_byte_mutation_rejects(self):
        path=self.package/'recovery';read=Path.read_bytes
        def altered(p,*args,**kwargs):
            value=read(p,*args,**kwargs)
            return value[:-1]+bytes([value[-1]^1]) if p==path else value
        with patch.object(Path,'read_bytes',altered),self.assertRaisesRegex(ValueError,'generated closure'):
            checker.inspect_record(self.package,self.record)
        original=Path.is_symlink
        with patch.object(Path,'is_symlink',lambda p:p==path or original(p)),self.assertRaisesRegex(ValueError,'non-symlink'):
            checker.inspect_record(self.package,self.record)

    def test_entry_pc_and_actual_startup_branch_mutations_reject(self):
        original=(self.package/'recovery').read_bytes();raw=bytearray(original);offset=32;entry_offset=None;file_entry=None
        entry=checker.builder.inspect_macho(original)['entry_pc']
        for _ in range(struct.unpack_from('<I',raw,16)[0]):
            cmd,size=struct.unpack_from('<II',raw,offset)
            if cmd==5:entry_offset=offset+16+256
            if cmd==0x19:
                vm,_,fileoff,filesize=struct.unpack_from('<4Q',raw,offset+24)
                if vm<=entry<vm+filesize:file_entry=fileoff+entry-vm
            offset+=size
        self.assertIsNotNone(entry_offset);self.assertIsNotNone(file_entry)
        struct.pack_into('<Q',raw,entry_offset,entry+4)
        with self.assertRaisesRegex(ValueError,'entry mismatch'):checker.static_entry(bytes(raw),'_user_start')
        raw=bytearray(original);struct.pack_into('<I',raw,file_entry+16,0xd503201f)
        with self.assertRaisesRegex(ValueError,'startup call'):checker.static_entry(bytes(raw),'_user_start')


if __name__=='__main__':unittest.main()
