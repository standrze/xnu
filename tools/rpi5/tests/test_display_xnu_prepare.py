# SPDX-License-Identifier: BSD-2-Clause
"""Pinned directory-metadata exception; optional operator-owned real preparation."""
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from tools.rpi5 import prepare_display_xnu_trial_v2 as subject
stage=subject.stage
BASELINE=stage.ROOT/'build/rpi5/display-compact-repeat-restored-20261014'
SEAL='f998989aa3ecd0fa51642e9fb3862195cc10f76b6c2745977c584070e12ad503'
PLAN='96ece5e1e42dcba5e9e25d0e82c62308db07fb893227ccd3c444923b39ff51f4'
BOOT='388349d4-3664-4ac1-9488-7d59cc4f6566'


class DisplayXNUPrepareTests(unittest.TestCase):
    def test_exact_document_adjacent_option_literal_and_directory(self):
        args=['cc','-I',subject.INCLUDE_LITERAL]
        subject.include_directory(subject.COMPILER_DOCUMENT,subject.COMPILER_SHA,args,2)
        for document,pin,words,index in (
            (subject.COMPILER_DOCUMENT.with_name('foreign.json'),subject.COMPILER_SHA,args,2),
            (subject.COMPILER_DOCUMENT,'0'*64,args,2),
            (subject.COMPILER_DOCUMENT,subject.COMPILER_SHA,['cc','-o',subject.INCLUDE_LITERAL],2),
            (subject.COMPILER_DOCUMENT,subject.COMPILER_SHA,['cc','-I',str(stage.ROOT)+'/osfmk/../file'],2),
            (subject.COMPILER_DOCUMENT,subject.COMPILER_SHA,args,1)):
            with self.assertRaises(ValueError):subject.include_directory(document,pin,words,index)
        with patch.object(Path,'is_dir',return_value=False),self.assertRaises(ValueError):
            subject.include_directory(subject.COMPILER_DOCUMENT,subject.COMPILER_SHA,args,2)

    def test_actual_pinned_new_graph_preserves_all_literal_file_pins(self):
        prior=json.loads((BASELINE/'checkpoint.json').read_text())['evidence_sha256']
        with patch.object(subprocess,'run',side_effect=AssertionError('No compiler or transport')):
            graph=subject.package_graph(stage.PACKAGE,prior)
        self.assertEqual({name:graph[name] for name in prior},prior)
        m=json.loads((stage.PACKAGE/'manifest.json').read_text())
        for key in ('inputs_sha256','actual_headers_sha256','generated_sha256'):
            for name,value in m[key].items():self.assertEqual(graph.get(name),value,name)
        self.assertNotIn(subject.INCLUDE_LITERAL,graph)
        self.assertEqual(graph[str(subject.COMPILER_DOCUMENT)],subject.COMPILER_SHA)
        bad=dict(prior);bad[str(subject.COMPILER_DOCUMENT)]='0'*64
        # Prior sealed file drift still fails ordinary byte validation; there
        # is no auto-refresh of an existing pin by the directory exception.
        with self.assertRaises(ValueError):stage.seals.check_pins(subject.package_graph(stage.PACKAGE,bad))

    def test_only_private_preparation_binding_changes(self):
        self.assertIs(subject.main.__code__,stage.main.__code__)
        self.assertIs(subject.main.__globals__['dispatch'],stage.dispatch)
        self.assertIs(subject.main.__globals__['launch'],stage.launch)
        self.assertIs(subject.main.__globals__['prepare_restore'],stage.prepare_restore)
        pins=subject.source_pins()
        for path in (Path(subject.__file__).resolve(),Path(__file__).resolve()):self.assertEqual(pins[str(path)],stage.sha(path))

    @unittest.skipUnless(os.environ.get('RPI5_DISPLAY_XNU_PREPARE_OUTPUT'),'Operator owns the sole saved preparation')
    def test_real_prepare_seal_and_actual_recorder_admission_once(self):
        with patch.object(stage.checker,'inspect',wraps=stage.checker.inspect) as checker,\
            patch.object(subprocess,'run',side_effect=AssertionError('No compiler/transport')):
            checkpoint,pin,metrics=subject.prepare_install(BASELINE,SEAL,PLAN,BOOT)
        self.assertEqual(checker.call_count,1);self.assertEqual(metrics['prior_catalog_count'],374)
        self.assertEqual(metrics['package_compiler_audit_calls'],0)
        with patch.object(stage.checker,'inspect',side_effect=AssertionError('No checker replay')),\
            patch.object(stage.previous_compact,'restoration',side_effect=AssertionError('No history replay')):
            stage.seals.revalidate(checkpoint,pin);admission=stage.admit(checkpoint)
        out=stage.local(Path(os.environ['RPI5_DISPLAY_XNU_PREPARE_OUTPUT']));out.mkdir(exist_ok=False)
        stage.seals.save_new(out/'checkpoint.json',checkpoint,pin)
        stage.save(out/'metrics.json',metrics);stage.save(out/'admission.json',admission)
        print(json.dumps({'prepared_only':True,'directory':str(out),'checkpoint_sha256':pin,'admission':admission}))


if __name__=='__main__':unittest.main()
