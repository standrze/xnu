# SPDX-License-Identifier: BSD-2-Clause
"""Mapping v3 transport is distinct, self-contained and hardware-inert offline."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.rpi5 import gem_mapping_predicate_media_v1 as media
from tools.rpi5 import gem_mapping_predicate_serial_v3 as protocol
from tools.rpi5 import remote_namespace_audit_v1 as namespace
from tools.rpi5 import stage_gem_mapping_predicate_trial_v3 as stage

class MappingPredicateTransportV3Tests(unittest.TestCase):
    def report(self):return stage.checker.inspect(stage.PACKAGE,stage.MANIFEST_SHA)

    def capture(self):
        raw=(stage.ROOT/'build/rpi5/gem-cpu-ring-retry-successor-capture-20261014/serial.bin').read_bytes()
        old=stage.checker.b.retry.trial.marker('304dd3f376024efab8ef4d63ef1dad80').encode()
        new=stage.checker.b.retry.trial.marker(stage.TAG).encode()
        self.assertEqual(raw.count(old),1);raw=raw.replace(old,new,1)
        old_size=b'Read probe.bin bytes 20169920 hnd '
        new_size=b'Read probe.bin bytes '+str(stage.case.IMAGE_BYTES).encode()+b' hnd '
        self.assertEqual(raw.count(old_size),1);raw=raw.replace(old_size,new_size,1)
        owner=b'RPI5XNU:PCIEID:DMA_OWNER '
        row=(b'RPI5XNU:PCIEID:DMA_MAP REASON=33 PAGE=0 ATTR=2 VA=1 '
             b'PA=101711872 PAR_R=4899916495612301312 PAR_W=4899916495612301312\r\n')
        self.assertEqual(raw.count(owner),1);return raw.replace(owner,row+owner,1)

    def prepared(self,folder):
        completed=subprocess.run([sys.executable,str(Path(stage.__file__).resolve()),'prepare',
            '--baseline',str(stage.BASELINE),'--prior-seal-sha256',stage.BASELINE_SEAL,
            '--prior-plan-sha256',stage.BASELINE_PLAN,'--linux-boot-id',stage.BASELINE_BOOT,
            '--output',str(folder)],cwd=stage.ROOT,text=True,capture_output=True,timeout=180)
        self.assertEqual(completed.returncode,0,completed.stderr)
        result=json.loads(completed.stdout);self.assertEqual(result['status'],'prepared_only')
        return json.loads((folder/'checkpoint.json').read_text()),result['checkpoint_sha256']

    def remote(self,checkpoint,pin):
        base=checkpoint['payload']['media_plan'];run='/home/sandrzej/xnu-mapping-v3-offline'
        plan,plan_sha=media.plan_from_seal(checkpoint,pin,media.TRIAL,'42'*16,run,base)
        source=media.remote_source(checkpoint,pin,plan,plan_sha)
        return source,plan,plan_sha

    def test_distinct_namespace_package_and_source_closure(self):
        self.assertEqual(stage.CONTROLLER,'gem-mapping-predicate-three-target-controller-v3')
        self.assertEqual(stage.DESCRIPTOR,'gem-mapping-predicate-fixed54')
        self.assertEqual(media.TRIAL,'gem-mapping-predicate-v3-triple-trial-v1')
        self.assertEqual(media.RESTORE,'gem-mapping-predicate-v3-triple-restore-v1')
        self.assertNotIn('ring-retry',media.TRIAL)
        self.assertTrue(stage.valid_report(self.report()))
        pins=stage.source_pins()
        for module in (stage,media,protocol):
            self.assertEqual(pins[str(Path(module.__file__).resolve())],stage.sha(module.__file__))
        self.assertGreaterEqual(len(pins),1600)

    def test_exact_one_bounded_mapping_row_and_zero_activation(self):
        raw=self.capture();result=protocol.inspect(raw,self.report())
        self.assertTrue(result['mapping_predicate_diagnostic_pass'])
        self.assertEqual(result['mapping_predicate']['reason'],33)
        self.assertEqual(result['preparation'],dict(step=14,error=-13,bytes=32768,packets=0))
        self.assertEqual(result['dma_candidate_route'],dict(physical=0,pci=0,rp1=0,bytes=0))
        self.assertFalse(any(result[k] for k in ('bme','dma','irq_delivery','queue_publication','ethernet_proven')))
        row=b'RPI5XNU:PCIEID:DMA_MAP '
        full=raw[raw.index(row):raw.index(b'\n',raw.index(row))+1]
        with self.assertRaisesRegex(ValueError,'Exactly 54'):
            protocol.inspect(raw.replace(b'RPI5XNU:PCIEID:DMA_OWNER ',full+b'RPI5XNU:PCIEID:DMA_OWNER ',1),self.report())
        with self.assertRaisesRegex(ValueError,'Bounded mapping'):
            protocol.inspect(raw.replace(b'REASON=33',b'REASON=99',1),self.report())
        with self.assertRaisesRegex(ValueError,'Bounded mapping'):
            protocol.inspect(raw.replace(b'REASON=33',b'REASON=41',1),self.report())
        with self.assertRaisesRegex(ValueError,'activated'):
            protocol.inspect(raw.replace(b'PHYSICAL=0 PCI=0',b'PHYSICAL=1 PCI=0',1),self.report())

    def test_subprocess_prepare_remote_plan_and_namespace_audit(self):
        with tempfile.TemporaryDirectory(prefix='mapping-v3-cli-',dir=stage.ROOT/'build/rpi5') as name:
            folder=Path(name);folder.rmdir();checkpoint,pin=self.prepared(folder)
            source,plan,plan_sha=self.remote(checkpoint,pin)
            nodes=ast.parse(source).body;expected={}
            for index in range(9):
                module=nodes[1+index*6].targets[0].id
                text=ast.literal_eval(nodes[5+index*6].value)
                expected[module]=namespace.sha(text.encode())
            result=namespace.inspect(source,namespace.sha(source.encode()),expected,plan_sha)
            self.assertTrue(result['bootstrap_no_io'] and result['pure_plan_no_io'])
            self.assertTrue(result['actual_execute_to_identity'])
            self.assertFalse(result['device_access'] or result['publication_tested'])
            code=('import hashlib,json,sys;sys.path.insert(0,'+repr(str(stage.ROOT))+
                ');from pathlib import Path;from tools.rpi5 import gem_mapping_predicate_media_v1 as m;'
                'from tools.rpi5 import trial_checkpoint_v2 as seals;'
                'd=Path('+repr(str(folder))+');c=json.loads((d/"checkpoint.json").read_text());'
                'p=seals.digest(c);base=c["payload"]["media_plan"];plan,h=m.plan_from_seal(c,p,m.TRIAL,"43"*16,'
                '"/home/sandrzej/xnu-mapping-v3-subprocess",base);s=m.remote_source(c,p,plan,h);'
                'print(json.dumps({"plan":h,"remote":hashlib.sha256(s.encode()).hexdigest(),"tx":0}))')
            completed=subprocess.run([sys.executable,'-I','-c',code],cwd=stage.ROOT,
                text=True,capture_output=True,timeout=90,env={'PATH':os.environ.get('PATH','')})
            self.assertEqual(completed.returncode,0,completed.stderr)
            emitted=json.loads(completed.stdout)
            self.assertEqual(emitted['tx'],0);self.assertRegex(emitted['plan'],r'^[0-9a-f]{64}$')
            self.assertRegex(emitted['remote'],r'^[0-9a-f]{64}$')

if __name__=='__main__':unittest.main()
