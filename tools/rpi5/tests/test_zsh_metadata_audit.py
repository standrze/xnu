# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic replay/fault tests and saved physical evidence; no Pi/serial access."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.rpi5 import audit_zsh_metadata_trial as audit
from tools.rpi5.tests.test_zsh_metadata_serial import boot, observations
from tools.rpi5.tests import test_zsh_metadata_stage as stage_fixtures

trial = audit.trial


def diagnostic(rows):
    lines = [trial.diagnostic.BEGIN]
    def field(key,value): lines.append(('STATPROBE:'+key+'='+str(value)).encode())
    def metadata(key,value):
        field(key,value['rc']); field('RAW',value['raw_hex']); field('GUARDS',value['guards'])
        if value['rc'] == 0:
            field('MODE',value['mode']); field('ISREG',int(value['is_regular'])); field('ISDIR',int(value['is_directory']))
    for row in rows['paths']:
        field('PATH',row['path']); field('ACCESS_F_OK',row['access_f_ok']); field('ACCESS_R_OK',row['access_r_ok'])
        metadata('STAT64',row['stat']); metadata('LSTAT64',row['lstat'])
        for opened in row['opens']:
            field('OPEN_FLAGS',opened['flags']); field('OPEN',opened['fd']); metadata('FSTAT64',opened['fstat'])
            field('F_GETFD',opened['getfd']); field('F_GETFL',opened['getfl']); field('F_DUPFD_10',opened['duplicate'])
            field('DUP_READ',opened['duplicate_read']['rc']); field('DUP_DATA',opened['duplicate_read']['hex'])
            field('DUP_CLOSE',opened['duplicate_close']); field('ORIGINAL_READ',opened['original_read']['rc'])
            field('ORIGINAL_DATA',opened['original_read']['hex']); field('ORIGINAL_CLOSE',opened['original_close'])
    field('BUFFER_DAMAGE',0); lines.append(trial.diagnostic.END)
    return b'\n'.join(lines)


def fixture():
    files = trial.files_from(trial.package_check.previous.INIT.read_bytes())
    rows = observations(files)
    nonce = 'Z0123456789abcdef'
    def response(lines,prompt=b'xnu:/# '): return b'\n'+b'\n'.join(lines)+b'\n'+prompt
    raw = boot()+response([nonce.encode()])+response([diagnostic(rows)])+response([b'0'])
    raw += response(trial.t.SMOKE_LINES)+response([b'0'])
    raw += response([b'DARWIN:ZSH:MAIN',b'DARWIN:ZSH:MAIN'],trial.t.ZPROMPT)
    raw += response([b'PI_ZSH:5.9'],trial.t.ZPROMPT)
    raw += response([b'PI_BUILTINS:xnu:42'],trial.t.ZPROMPT)
    raw += response([('PI_EXEC_'+nonce).encode()],trial.t.ZPROMPT)
    raw += response([])+response([('RECOVERED_'+nonce).encode()])
    report = dict(image_sha256=trial.IMAGE_SHA,image_bytes=trial.IMAGE_BYTES,
                  root_mount_marker=trial.ROOT_MARKER.decode(),kernel_sha256=trial.package_check.KERNEL_SHA,
                  init_sha256=trial.package_check.previous.INIT_SHA,preflight_pass=True,checks={'synthetic':True})
    installed = dict(directory='/synthetic/not/a/physical/install',plan_sha256='a'*64,result_sha256='b'*64)
    state = dict(status='passed',checks=trial.CHECKS.copy(),script_file_acceptance=True,baud=115200,
                 device='/dev/cu.usbmodem102',preflight=report,installation=installed,bytes=len(raw),
                 serial_sha256=hashlib.sha256(raw).hexdigest(),full_gate6_exit=False,networking=False,durability=False,
                 started_utc='2026-10-12T19:00:00+00:00',ended_utc='2026-10-12T19:02:00+00:00',nonce=nonce,
                 transmitted_bytes=sum(len(c)+1 for c in audit.commands(nonce)),observations=rows,
                 metadata_acceptance=trial.accept_metadata(rows,files))
    return state,raw,report,installed,files


class MetadataAuditTests(unittest.TestCase):
    def test_optional_saved_physical_corrective_trial(self):
        directory = trial.staging.ROOT/'build/rpi5/mac-zsh-metadata-trial-20261012'
        pins = {
            'serial.bin':'5ad1778eb5d1c062df0c1eef60d5f68e62f0d06cc56df881b7fe1ad5e0ff4ecd',
            'state.json':'91d99dd462df04118df2999702a4608449b78e421374857e43a7feea64453e5a',
            'validation.json':'26ef9cadd6c871239db0592581a3fcf14f9a66c7cd9443cc81106a227cbd2cc1',
        }
        if not all((directory/name).is_file() for name in pins):
            self.skipTest('Optional preserved physical corrective capture absent')
        for name,expected in pins.items():
            self.assertEqual(hashlib.sha256((directory/name).read_bytes()).hexdigest(),expected)
        actual = audit.audit(directory)
        self.assertEqual(actual,json.loads((directory/'validation.json').read_text()))
        self.assertTrue(actual['strict_mounted_root_trial_passed'])
        self.assertTrue(actual['metadata_acceptance']['raw_metadata_accepted'])
        self.assertTrue(actual['original_zsh_script_acceptance'])
        self.assertTrue(actual['interactive_zsh_and_recovery_acceptance'])
        for field in ('abi_root_cause_proven','full_gate6_exit','networking','durability'):
            self.assertFalse(actual[field])

    def test_file_entrypoint_rechecks_actual_package_and_receipt_hashes(self):
        state,raw,_,_,_ = fixture()
        package = trial.staging.ROOT/'build/rpi5/bl33-probe-wdmzdtem'
        report = trial.package_check.inspect(package)
        helper = stage_fixtures.MetadataStageTests()
        plan = helper.plan()
        plan.update(preflight=report,new_image_sha256=trial.IMAGE_SHA,candidate=report['image'],
                    run='/home/sandrzej/xnu-gate6-metadata-abcdefgh')
        result = helper.result(plan)
        result['image_sha256'] = trial.IMAGE_SHA
        result['protected_files_sha256']['probe.bin'] = trial.IMAGE_SHA
        with tempfile.TemporaryDirectory(prefix='synthetic-metadata-audit-',dir=trial.staging.ROOT/'build/rpi5') as temporary:
            directory = Path(temporary); installed = directory/'installation'; installed.mkdir()
            for name,value in (('plan.json',plan),('result.json',result)):
                (installed/name).write_text(json.dumps(value))
            state.update(preflight=report,installation=trial.installation(installed,report))
            (directory/'serial.bin').write_bytes(raw)
            (directory/'state.json').write_text(json.dumps(state))
            self.assertEqual(audit.audit(directory)['status'],'corrective_zsh_transcript_audited')
            # A semantically equivalent rewritten receipt is still not the
            # exact receipt bound when the recorder armed.
            (installed/'result.json').write_text(json.dumps(result,indent=2))
            with self.assertRaises(ValueError): audit.audit(directory)

    def test_replay_requires_raw_evidence_without_broader_acceptance(self):
        result = audit.replay(*fixture())
        self.assertTrue(result['original_zsh_script_acceptance'])
        self.assertTrue(result['interactive_zsh_and_recovery_acceptance'])
        for field in ('abi_root_cause_proven','full_gate6_exit','networking','durability'):
            self.assertFalse(result[field])

    def test_changed_missing_or_broader_state_claims_rejected(self):
        original,raw,report,installed,files = fixture()
        for key,value in [('status','failed'),('checks',[]),('script_file_acceptance',False),
                          ('preflight',{}),('installation',{}),('bytes',0),('serial_sha256','0'*64),
                          ('nonce','Zwrong'),('transmitted_bytes',0),('observations',{}),
                          ('metadata_acceptance',{}),('full_gate6_exit',True),('networking',True),
                          ('durability',True),('error','hidden failure'),('serial_restore_error','failed'),
                          ('ended_utc','2026-10-12T18:00:00+00:00'),
                          ('started_utc','2026-10-12T19:00:00')]:
            changed = copy.deepcopy(original); changed[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError): audit.replay(changed,raw,report,installed,files)

    def test_rehashed_transcript_mutations_still_fail_raw_replay(self):
        state,raw,report,installed,files = fixture()
        mutations = [raw.replace(trial.COPY,b'wrong kernel root copy'),
                     raw.replace(trial.ROOT_MARKER,b'torn mount line'),
                     raw.replace(b'18908864',b'18057920'),raw+trial.t.ENTRY,
                     raw+b'panic(cpu 0)',raw+b'RPI5XNU:HFSWRITE:',
                     raw.replace(b'RPI5XNU:ZSH:SMOKE_DONE\n',b''),
                     raw.replace(b'PI_ZSH:5.9\n',b'PI_ZSH:5.8\n'),
                     raw.replace(b'PI_BUILTINS:xnu:42\n',b'PI_BUILTINS:xnu:41\n'),
                     raw.replace(b'PI_EXEC_Z0123456789abcdef\n',b'wrong executable\n'),
                     raw.replace(b'RECOVERED_Z0123456789abcdef\n',b'NOT_RECOVERED\n'),
                     raw.replace(b'DARWIN:ZSH:MAIN\nDARWIN:ZSH:MAIN',b'DARWIN:ZSH:MAIN'),
                     raw.replace(b'PI_ZSH:5.9\npi-zsh# ',b'PI_ZSH:5.9\nxnu:/# '),
                     raw.replace(b'\n0\nxnu:/# ',b'\n1\nxnu:/# ',1),
                     raw.replace(b'PI_ZSH:5.9\n',b'PI_ZSH:5.9\nPI_ZSH:5.9\n'),
                     raw.replace(b'\nPI_ZSH:5.9\n',b'\npi-zsh# \nPI_ZSH:5.9\n'),
                     raw.replace(b'PI_ZSH:5.9\npi-zsh# \nPI_BUILTINS:xnu:42',
                                 b'PI_BUILTINS:xnu:42\npi-zsh# \nPI_ZSH:5.9'),
                     raw+b'extra command output\n']
        for index,changed in enumerate(mutations):
            claim = copy.deepcopy(state); claim['bytes'] = len(changed)
            claim['serial_sha256'] = hashlib.sha256(changed).hexdigest()
            with self.subTest(mutation=index), self.assertRaises((ValueError,RuntimeError)):
                audit.replay(claim,changed,report,installed,files)

    def test_forged_metadata_claim_matching_raw_still_rejected_semantically(self):
        state,raw,report,installed,files = fixture()
        rows = copy.deepcopy(state['observations'])
        value = rows['paths'][0]['stat']
        value.update(rc=-45,raw_hex='a5'*144)
        for key in ('mode','is_regular','is_directory'): del value[key]
        changed = raw.replace(diagnostic(state['observations']),diagnostic(rows))
        state.update(observations=rows,bytes=len(changed),serial_sha256=hashlib.sha256(changed).hexdigest())
        with self.assertRaises(ValueError): audit.replay(state,changed,report,installed,files)


if __name__ == '__main__':
    unittest.main()
