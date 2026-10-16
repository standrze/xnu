# SPDX-License-Identifier: BSD-2-Clause
"""Preserved failure and filesystem-independent publisher bootstrap fixtures."""
import ast
import copy
import json
from pathlib import Path
import unittest
from tools.rpi5 import remote_namespace_audit_v1 as audit

ROOT=Path(__file__).resolve().parents[3]
FAILED=ROOT/'build/rpi5/gem-cpu-ring-retry-installed-20261014'
REMOTE_SHA='67e6f427383ba6cc01fb6bbead5e7894900580323b6280bc70363db81f441e75'
SEAL_SHA='2a6d147e532f21f7c24b2d14a6dbb539ac241997d8db89cf77a8c6d2b8295cd2'
PLAN_SHA='73dd16891e0e61c70632baa2def68cccf9058c638224106775435d8f9cc88c9e'
PARENT=ROOT/'tools/rpi5/gem_cpu_batch_media_v1.py'
PARENT_SHA='51ff5b30a9ca2edc27b442dd4432569ff1d7f195e401a45623d370bfea0a551b'

def preserved():
    source=(FAILED/'remote-program.py').read_text()
    if audit.sha(source.encode())!=REMOTE_SHA:raise ValueError('Preserved failed program changed')
    checkpoint=json.loads((FAILED/'checkpoint.json').read_text())
    if audit.sha(audit.canonical(checkpoint))!=SEAL_SHA:raise ValueError('Preserved failed seal changed')
    nodes=ast.parse(source).body;pins={}
    for i in range(9):
        name=nodes[1+i*6].targets[0].id;path=ast.literal_eval(nodes[3+i*6].value)
        pins[name]=checkpoint['evidence_sha256'][path]
    return source,pins

def emit(rows,plan):
    source='import types,sys,json\n'
    for row in rows:
        name=row['name'];text=row['source'];filename=row['filename']
        source+=f'{name}=types.ModuleType({name!r})\nsys.modules[{name!r}]={name}\n'
        source+=f'{name}.__file__={filename!r}\n{name}.__package__=""\n{name}._active_window_source={text!r}\n'
        source+=f'exec({text!r},{name}.__dict__)\n'
    digest=audit.sha(audit.canonical(plan))
    source+='PLAN=json.loads('+repr(json.dumps(plan))+')\n'
    source+=f'print(json.dumps({rows[-1]["name"]}.execute(PLAN,{digest!r},capture,helper,snapshots,reference,guarded)))\n'
    return source,{r['name']:audit.sha(r['source'].encode()) for r in rows},digest

def standalone_fixture():
    """Test-only projection, not a new production publisher or retry receipt.

    Fold the exact frozen parent text locally and make source-path constants
    lexical. Leave the actual publisher, validation and execution bodies alone.
    All embedded source identifiers are deliberately nonexistent host paths.
    The owner must separately implement/pin/review its production generator.
    """
    source,pins=preserved();rows,plan=audit.unpack(source,REMOTE_SHA,pins,PLAN_SHA)
    parent=PARENT.read_bytes()
    if audit.sha(parent)!=PARENT_SHA:raise ValueError('Frozen original parent changed')
    text=parent.decode()
    for old,new in (('gem_cpu_batch_case_v1','gem_cpu_ring_retry_case_v1'),
        ('gem_cpu_batch_media_v1','gem_cpu_ring_retry_media_v1'),
        ('gem-cpu-batch','gem-cpu-ring-retry'),('cpubatch','ringretry'),('CPU-batch','ring-only retry')):
        if old not in text:raise ValueError('Exact test derivation changed')
        text=text.replace(old,new)
    text=text.replace('SOURCE=Path(original.__file__).resolve()','SOURCE=Path(original.__file__)')
    rows[-1]['source']=text
    rows[-2]['source']=rows[-2]['source'].replace('ROOT=Path(__file__).resolve().parents[2]',
                                                'ROOT=Path(__file__).parents[2]')
    for row in rows:row['filename']='/nonexistent-host-files/workspace/tools/rpi5/'+row['name']+'.py'
    return rows,plan

class RemoteNamespaceAuditTests(unittest.TestCase):
    def test_preserved_actual_failure_source_and_hidden_read_inventory(self):
        source,pins=preserved();rows,plan=audit.unpack(source,REMOTE_SHA,pins,PLAN_SHA)
        sites=audit.hazards(rows)
        self.assertTrue(any(r['module']=='gem_cpu_ring_retry_media_v1' and
            r['scope']=='<module>' and r['call']=='_parent.read_bytes' for r in sites))
        self.assertIn('gem_cpu_batch_media_v1.py',(FAILED/'remote.stderr').read_text())
        self.assertEqual((FAILED/'remote.stdout').read_bytes(),b'')
        with self.assertRaisesRegex(audit.DependencyViolation,'resolve'):
            audit.inspect(source,REMOTE_SHA,pins,PLAN_SHA)
        # Skip only the earlier metadata path-resolution hazard so that the
        # original wrapper failure itself is independently reproduced locally.
        rows[-2]['source']=rows[-2]['source'].replace('.resolve()','')
        candidate,pins,digest=emit(rows,plan)
        with self.assertRaisesRegex(audit.DependencyViolation,'io.open'):
            audit.inspect(candidate,audit.sha(candidate.encode()),pins,digest)

    def test_flattened_exact_runtime_passes_without_any_files_or_target_calls(self):
        rows,plan=standalone_fixture()
        for restore in (False,True):
            with self.subTest(restore=restore):
                trial=copy.deepcopy(plan)
                if restore:
                    trial['media']['profile']=trial['media']['profile'].replace('-trial-','-restore-')
                    for row in trial['media']['files']:
                        row['old_sha256'],row['new_sha256']=row['new_sha256'],row['old_sha256']
                        row['old_bytes'],row['new_bytes']=row['new_bytes'],row['old_bytes']
                source,pins,digest=emit(rows,trial)
                result=audit.inspect(source,audit.sha(source.encode()),pins,digest)
                self.assertTrue(result['bootstrap_no_io'] and result['pure_plan_no_io'])
                self.assertTrue(result['actual_execute_to_identity'])
                self.assertFalse(result['publication_tested'] or result['whole_runtime_path_proven'])

    def test_late_source_fallback_runtime_read_and_unembedded_import_rejected(self):
        for mode in ('missing-source','plan-read','extra-import','path-resolution','source-pins'):
            with self.subTest(mode=mode):
                rows,plan=standalone_fixture()
                if mode=='missing-source':rows[5]['source']+='\ndel _active_window_source\n'
                elif mode=='plan-read':rows[-1]['source']=rows[-1]['source'].replace(
                    'def validate_plan(plan):','def validate_plan(plan):\n    SOURCE.read_bytes()')
                elif mode=='extra-import':rows[-1]['source']='import tools.rpi5.gem_cpu_batch_media_v1\n'+rows[-1]['source']
                elif mode=='path-resolution':rows[-1]['source']=rows[-1]['source'].replace(
                    'SOURCE=Path(original.__file__)','SOURCE=Path(original.__file__).resolve()')
                else:rows[-1]['source']=rows[-1]['source'].replace(
                    'def validate_plan(plan):','def validate_plan(plan):\n    source_pins()')
                source,pins,digest=emit(rows,plan)
                with self.assertRaises(audit.DependencyViolation):
                    audit.inspect(source,audit.sha(source.encode()),pins,digest)

    def test_envelope_source_plan_and_final_dispatch_cannot_be_substituted(self):
        rows,plan=standalone_fixture();source,pins,digest=emit(rows,plan);original=audit.sha(source.encode())
        for mode in ('remote','source','missing-source','plan','module-identity','exec-source','extra-tail','dispatch'):
            with self.subTest(mode=mode):
                text=source;expected=original;p=copy.deepcopy(pins);pd=digest
                if mode=='remote':expected='0'*64
                elif mode=='source':p[rows[-1]['name']]='0'*64
                elif mode=='missing-source':p.pop(rows[0]['name'])
                elif mode=='plan':pd='0'*64
                elif mode=='module-identity':text=text.replace("capture=types.ModuleType('capture')","capture=types.ModuleType('foreign')",1)
                elif mode=='exec-source':text=text.replace('exec(',"exec('pass #'+",1)
                elif mode=='extra-tail':text+='open("/dev/null")\n'
                else:text=text.replace('.execute(PLAN,','.execute({},',1)
                if text!=source:expected=audit.sha(text.encode())
                with self.assertRaises((ValueError,SyntaxError)):
                    audit.inspect(text,expected,p,pd)

if __name__=='__main__':unittest.main()
