# SPDX-License-Identifier: BSD-2-Clause
"""Supplemental interface regression; real raw capture, no network or hardware."""
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest
from tools.rpi5 import rp1_config_return_compat_v1 as adapter
from tools.rpi5 import rp1_config_trace_serial_core as protocol

ROOT = adapter.original_stage.ROOT
SCRIPT = ROOT/'tools/rpi5/rp1_config_return_compat_v1.py'
INSTALL = ROOT/'build/rpi5/rp1-config-v3-installed-20261013'
CAPTURE = ROOT/'build/rpi5/rp1-config-v3-serial-20261013'
SEAL = '7654eb7a38cb3d7ffd4d6db62272768c6a27f364ff3672a0b3b643c9dd07afa5'
PLAN = '92aa2ced5df5db70fe3935bfdca58554a45e77ff27595eca7975da717eacf316'


class SupplementalTests(unittest.TestCase):
    def test_only_missing_constant_exposed_without_module_mutation(self):
        before = dict(vars(protocol))
        result = adapter.facade(protocol)
        self.assertEqual(set(vars(result)) - set(before), {'PREPARED_PREFIX'})
        self.assertEqual(result.PREPARED_PREFIX, protocol.prior.PREPARED_PREFIX)
        for key, value in before.items():
            self.assertIs(getattr(result, key), value)
        self.assertEqual(vars(protocol), before)

    def test_wrong_parent_prefix_or_existing_export_rejected(self):
        for change in ({'PREPARED_PREFIX': adapter.PREFIX}, {'PREFIX': b'wrong'},
                       {'prior': types.SimpleNamespace(__file__=protocol.prior.__file__, PREPARED_PREFIX=b'wrong')}):
            with self.assertRaises(ValueError):
                adapter.facade(types.SimpleNamespace(**(vars(protocol) | change)))

    def test_unapproved_adapter_rejected_before_intake(self):
        with self.assertRaisesRegex(ValueError, 'supplemental adapter digest'):
            adapter.controller('0'*64, INSTALL, SEAL, PLAN, CAPTURE)

    def test_actual_capture_return_and_restore_seal_with_ssh_double(self):
        # A clean interpreter prevents this NEW test module from masquerading
        # as a source that belonged to the original installation seal.
        program = r'''
import json,runpy,shutil,subprocess,tempfile,types
from pathlib import Path
from unittest.mock import patch
ns=runpy.run_path(SCRIPT)
stage=ns['original_stage'];root=stage.ROOT
with tempfile.TemporaryDirectory(prefix='rp1-compat-fixture-',dir=root/'build/rpi5') as name:
    directory=Path(name).resolve()
    for n in ('armed.json','state.json','serial.bin','receive-events.jsonl'):
        shutil.copyfile(CAPTURE/n,directory/n)
    bound=ns['controller'](stage.sha(SCRIPT),INSTALL,SEAL,PLAN,directory)
    state,observed,_=bound.captured(bound.context,directory)
    assert observed['trace_capture_valid'] is True
    assert observed['diagnostic']['rp1_id_trial_pass'] is False
    assert observed['diagnostic']['telemetry']['rp1_reads']==32
    assert observed['terminal_to_bootsys_seconds']<45
    assert observed['transfer_to_bootsys_seconds']<150
    assert str(Path(SCRIPT)) not in bound.context['checkpoint']['evidence_sha256']
    bound.ensure_record(write=True)
    calls=[]
    def ssh(command,**kw):
        assert command==stage.SSH+['sudo -n python3 -']
        calls.append(command)
        ctx=bound.context;identity=ctx['plan']['media']['identity_binding']['expected']
        value=dict(host=stage.HOST,boot_id='11111111-1111-4111-8111-111111111111',
            identity=dict(identity=identity,boot_id='11111111-1111-4111-8111-111111111111',hostname='kamidana'),
            root=identity['root'].split(),bootloader={'boot-mode':6,'partition':1,'tryboot':0},
            read_only=True,sd_partitions_unmounted=True,observed_utc='2099-01-01T00:00:00+00:00',
            installation=ctx['installed'],serial_sha256=state['serial_sha256'],
            return_source_sha256=bound.evidence.return_source_pins())
        return subprocess.CompletedProcess(command,0,json.dumps(value),'')
    with patch.object(subprocess,'run',side_effect=ssh):
        returned=bound.evidence.collect_return(bound.context,directory)
    assert len(calls)==1 and returned['capture_valid'] is True
    assert returned['diagnostic']['rp1_id_trial_pass'] is False
    assert bound.evidence.load_return(bound.context,directory)[0]==returned
    with patch.object(subprocess,'run',side_effect=AssertionError('No further SSH')):
        checkpoint,pin,metrics=bound.prepare_restore(INSTALL,SEAL,PLAN,directory)
    assert len(checkpoint['payload']['history_catalog'])==143
    assert checkpoint['evidence_sha256'][str(Path(SCRIPT))]==stage.sha(SCRIPT)
    assert checkpoint['evidence_sha256'][str(directory/'protocol-compatibility.json')]==stage.sha(directory/'protocol-compatibility.json')
    assert checkpoint['payload']['media_plan']['profile']==stage.engine.RESTORE
    assert not json.loads((directory/'protocol-compatibility.json').read_text())['supplemental_was_in_original_installation_seal']
    with patch.object(subprocess,'run',side_effect=AssertionError('No repeated return')):
        try:bound.evidence.collect_return(bound.context,directory)
        except ValueError:pass
        else:raise AssertionError('Existing receipt was accepted for overwrite')
    provenance=json.loads((directory/'protocol-compatibility.json').read_text())
    provenance['value_ascii']='wrong'
    (directory/'protocol-compatibility.json').write_text(json.dumps(provenance))
    try:bound.evidence.load_return(bound.context,directory)
    except ValueError:pass
    else:raise AssertionError('Tampered supplemental receipt accepted')
    print(json.dumps(dict(raw_capture_replayed=True,complete_guards=True,diagnostic_failed_preserved=True,
        synthetic_return_only=True,restoration_sealed_only=True,prior_catalog=143,ssh_doubles=len(calls))))
'''
        prefix = 'from pathlib import Path\n' + '\n'.join(
            f'{key}=Path({str(value)!r})' for key, value in
            (('SCRIPT', SCRIPT), ('INSTALL', INSTALL), ('CAPTURE', CAPTURE)))
        prefix += f'\nSEAL={SEAL!r}\nPLAN={PLAN!r}\n'
        result = subprocess.run([sys.executable, '-c', prefix + program], cwd=ROOT,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['diagnostic_failed_preserved'])


if __name__ == '__main__':
    unittest.main()
