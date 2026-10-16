#!/usr/bin/env python3
"""Actual complete-client composition, without running ssh or suppressing gaps."""
import json
from pathlib import Path
import re
import unittest
from tools.rpi5 import link_apple_ssh_runtime_groups as build

PACKAGE=build.ROOT/'build/rpi5/apple-ssh-runtime-groups-12k4lp6u'
SHA='b1bc88e185700a8cfd0c55f6ccc3fa81fb5072f7e242b458026ca081924eb552'


class RuntimeGroups(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if build.sha(PACKAGE/'manifest.json')!=SHA:raise ValueError('Frozen composition receipt changed')
        cls.report=json.loads((PACKAGE/'manifest.json').read_text())

    def test_all_actual_group_bytes_and_receipt_membership(self):
        r=self.report
        expected={str(build.ROOT/'build/rpi5'/d/'manifest.json'):h for d,h in build.RECEIPTS.values()}
        self.assertEqual(r['group_receipts_sha256'],expected)
        for key in ('source_inputs_sha256','generated_sha256'):
            for n,h in r[key].items():self.assertEqual(build.sha(n),h,n)
        for n,h in expected.items():self.assertEqual(r['source_inputs_sha256'][n],h)
        for old,new in r['runtime_replacements'].items():
            self.assertIn(old,r['source_inputs_sha256']);self.assertIn(new,r['source_inputs_sha256'])
        for archive in r['appended_provider_archives']:self.assertIn(archive,r['source_inputs_sha256'])

    def test_exact_link_composition_no_feature_or_main_changes(self):
        r=self.report
        base=json.loads((build.ROOT/'build/rpi5'/build.RECEIPTS['base'][0]/'manifest.json').read_text())
        command=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
        actual=r['commands'][0]['command']
        command[command.index('-o')+1]=actual[actual.index('-o')+1]
        command[command.index('-map')+1]=actual[actual.index('-map')+1]
        for old,new in r['runtime_replacements'].items():build.replace_once(command,old,new)
        for symbol in r['removed_diagnostic_only_forced_symbols']:
            i=command.index(symbol);self.assertEqual(command[i-1],'-u');del command[i-1:i+1]
        command+=r['appended_provider_archives'];self.assertEqual(command,actual)
        with self.assertRaises(ValueError):build.replace_once(['old','old'],'old','new')
        with self.assertRaises(ValueError):build.replace_once([],'old','new')
        self.assertEqual(r['actual_original_translation_units'],176)
        self.assertEqual(len(r['removed_legacy_locale_members']),8)
        self.assertTrue(r['original_client_main']);self.assertTrue(r['original_openssh_config_unchanged'])
        self.assertFalse(r['optional_features_removed'])

    def test_actual_linker_delta_and_nonoverlapping_remaining_groups(self):
        r=self.report;stderr=(PACKAGE/'target-link.stderr').read_text()
        missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',stderr,re.M)))
        self.assertEqual(missing,r['target_missing_symbols']);self.assertEqual(len(missing),54)
        self.assertEqual(r['previous_missing_count'],77);self.assertEqual(len(r['closed_symbols']),25)
        self.assertEqual(r['newly_reachable_symbols'],['__os_crash','_reallocf'])
        self.assertEqual(r['target_duplicate_symbols'],[])
        groups=r['remaining_provider_groups']
        self.assertEqual(sum(map(len,groups.values())),54)
        self.assertEqual(set().union(*map(set,groups.values())),set(missing))
        self.assertEqual(groups['random_api'],[]);self.assertEqual(groups['enabled_zlib_compression'],[])
        for flag in ('target_executed','ssh_version_executed','target_link_complete','live_keys','network_access',
                     'entropy_qualified','provider_stubs','accepted_runtime_modified'):
            self.assertFalse(r[flag])


if __name__=='__main__':unittest.main()
