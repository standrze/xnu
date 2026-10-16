# SPDX-License-Identifier: BSD-2-Clause
"""Successor transport is self-contained, distinct and still hardware-inert."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from tools.rpi5 import gem_cpu_ring_retry_media_v2 as media
from tools.rpi5 import stage_gem_cpu_ring_retry_trial_v2 as stage
from tools.rpi5 import serial_gem_cpu_ring_retry_trial_v2 as recorder
from tools.rpi5 import gem_cpu_ring_retry_evidence_v2 as evidence
from tools.rpi5 import arm_gem_cpu_ring_retry_reboot_v2 as launcher
from tools.rpi5.tests.test_gem_cpu_ring_retry_media_v1 import TripleMediaTests

class RetrySuccessorTransportTests(unittest.TestCase):
    def test_distinct_namespace_operation_profiles_and_source_closure(self):
        self.assertEqual(stage.CONTROLLER,'gem-cpu-ring-retry-successor-three-target-controller-v2')
        self.assertEqual(media.TRIAL,'gem-cpu-ring-retry-successor-triple-trial-v2')
        self.assertEqual(media.RESTORE,'gem-cpu-ring-retry-successor-triple-restore-v2')
        self.assertNotEqual(media.TRIAL,'gem-cpu-ring-retry-triple-trial-v1')
        pins=stage.source_pins()
        for module in (stage,media):self.assertEqual(pins[str(Path(module.__file__).resolve())],stage.sha(module.__file__))
        self.assertGreaterEqual(len(pins),1709)
        self.assertIs(recorder.stage,stage);self.assertIs(evidence.stage,stage);self.assertIs(launcher.stage,stage)
        self.assertIs(stage.transport(),evidence)

    def test_actual_remote_program_prefix_executes_without_host_file_access_or_media_write(self):
        fixture=TripleMediaTests()
        with fixture.fixture() as values:
            old=stage.seals.revalidate(values[8],values[9]);base=copy.deepcopy(old['media_plan'])
            base['profile']=media.TRIAL
            payload=dict(media_plan=base,history_catalog=old['history_catalog'],baseline_paths=old['baseline_paths'])
            checkpoint,pin=stage.seals.create(lambda:payload,media.source_pins())
            run=str(Path(values[7])/'successor-clean-remote')
            plan,plan_sha=media.plan_from_seal(checkpoint,pin,media.TRIAL,'42'*16,run,base)
            source=media.remote_source(checkpoint,pin,plan,plan_sha)
        boundary='print(json.dumps(gem_cpu_ring_retry_media_v2.execute('
        self.assertEqual(source.count(boundary),1)
        prefix=source[:source.index(boundary)]
        repository=str(stage.ROOT)
        guard='''import builtins,os\n_real_open=builtins.open\n_real_os_open=os.open\n_access=[]\ndef _guarded_open(path,*args,**kwargs):\n p=os.fspath(path)\n if p.startswith(%r):\n  _access.append(p);raise AssertionError("host path opened: "+p)\n return _real_open(path,*args,**kwargs)\ndef _guarded_os_open(path,*args,**kwargs):\n p=os.fspath(path)\n if p.startswith(%r):\n  _access.append(p);raise AssertionError("host path os.opened: "+p)\n return _real_os_open(path,*args,**kwargs)\nbuiltins.open=_guarded_open\nos.open=_guarded_os_open\n'''%(repository,repository)
        stop='''\nbefore=set(os.listdir('.'))\ngem_cpu_ring_retry_media_v2.validate_plan(PLAN)\nafter=set(os.listdir('.'))\nassert before==after\nassert not _access\nprint(json.dumps({"status":"validated-before-media-write","host_path_accesses":0,"filesystem_changes":0},sort_keys=True))\n'''
        with tempfile.TemporaryDirectory(prefix='ring-retry-successor-clean-') as clean:
            completed=subprocess.run([sys.executable,'-I','-c',guard+prefix+stop],cwd=clean,
                text=True,capture_output=True,timeout=60,env={'PATH':os.environ.get('PATH','')})
        self.assertEqual(completed.returncode,0,completed.stderr)
        self.assertEqual(json.loads(completed.stdout),dict(status='validated-before-media-write',host_path_accesses=0,filesystem_changes=0))

    def test_fresh_process_actual_prepare_remains_local_only(self):
        command=[sys.executable,str(Path(stage.__file__).resolve())]
        with tempfile.TemporaryDirectory(prefix='ring-retry-successor-cli-',dir=stage.ROOT/'build/rpi5') as name:
            output=Path(name);output.rmdir()
            completed=subprocess.run(command+['prepare','--baseline',str(stage.BASELINE),
                '--prior-seal-sha256',stage.BASELINE_SEAL,'--prior-plan-sha256',stage.BASELINE_PLAN,
                '--linux-boot-id',stage.BASELINE_BOOT,'--output',str(output)],cwd=stage.ROOT,
                text=True,capture_output=True,timeout=120)
            self.assertEqual(completed.returncode,0,completed.stderr)
            result=json.loads(completed.stdout);self.assertEqual(result['status'],'prepared_only')
            self.assertTrue((output/'checkpoint.json').is_file());self.assertTrue((output/'metrics.json').is_file())
            self.assertFalse((output/'dispatch-intent.json').exists())

if __name__=='__main__':unittest.main()
