# SPDX-License-Identifier: BSD-2-Clause
"""Compiler command text is not an OS path and never gets executed."""
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch
from tools.rpi5 import prepare_root42_pthread_trial_v2 as prepare


class GraphTests(unittest.TestCase):
    def test_actual_compile_database_shape_resolves_files_and_preserves_command(self):
        with tempfile.TemporaryDirectory(prefix='root42-graph-',dir=prepare.stage.ROOT/'build/rpi5') as name:
            package=Path(name);(package/'crypto').mkdir();(package/'include').mkdir()
            source=package/'source with spaces.c';source.write_text('int genuine;')
            compiler=package/'compiler';compiler.write_text('never execute this file')
            header=package/'include/header.h';header.write_text('int header;')
            command=shlex.join([str(compiler),'-I'+str(package/'crypto/../include'),'-c',str(source),'-o','object.o'])
            commands=package/'compile_commands.json';commands.write_text(json.dumps([{'directory':str(package),'command':command,'file':str(source)}]))
            (package/'manifest.json').write_text(json.dumps({'commands':str(commands),'headers':{str(package/'crypto/../include/header.h'):'expected'}}))
            pins=prepare.package_graph(package,{})
            for p in (compiler,source,header,commands,package/'manifest.json'):self.assertEqual(pins[str(p)],prepare.stage.sha(p))
            self.assertNotIn(command,pins);self.assertFalse(any('/../' in p for p in pins))
            commands.write_text(json.dumps([{'command':command+' -DCHANGED'}]))
            with self.assertRaisesRegex(ValueError,'evidence bytes'):prepare.stage.seals.check_pins(pins)

    def test_prior_graph_is_not_reinterpreted_and_repeated_files_are_hashed_once(self):
        with tempfile.TemporaryDirectory(prefix='root42-graph-',dir=prepare.stage.ROOT/'build/rpi5') as name:
            package=Path(name);old=package/'prior.json';old.write_text('{"retained":true}')
            source=package/'source.c';source.write_text('int x;')
            (package/'manifest.json').write_text(json.dumps({'prior':str(old),'repeated':[str(source)]*20}))
            retained={str(old):prepare.stage.sha(old)};real=prepare.stage.sha;calls=[]
            def sha(path):calls.append(str(path));return real(path)
            with patch.object(prepare.stage,'sha',side_effect=sha):pins=prepare.package_graph(package,retained)
            self.assertNotIn(str(old),calls);self.assertEqual(calls.count(str(source)),1)
            self.assertEqual(pins[str(old)],retained[str(old)])

    def test_malformed_command_document_rejected_not_silently_ignored(self):
        with tempfile.TemporaryDirectory(prefix='root42-graph-',dir=prepare.stage.ROOT/'build/rpi5') as name:
            package=Path(name);(package/'manifest.json').write_text(json.dumps({'command':'/compiler "unterminated'}))
            with self.assertRaises(ValueError):prepare.package_graph(package,{})
