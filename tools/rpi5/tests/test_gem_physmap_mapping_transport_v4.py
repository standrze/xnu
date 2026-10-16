# SPDX-License-Identifier: BSD-2-Clause
"""Catalog500 physmap v4 transport stays self-contained and hardware-inert offline."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.rpi5 import gem_physmap_mapping_media_v1 as media
from tools.rpi5 import gem_physmap_mapping_serial_v4 as protocol
from tools.rpi5 import remote_namespace_audit_v1 as namespace
from tools.rpi5 import stage_gem_physmap_mapping_trial_v4 as stage


class PhysmapMappingTransportV4Tests(unittest.TestCase):
    def report(self):
        return stage.checker.inspect(stage.PACKAGE, stage.MANIFEST_SHA)

    def capture(self):
        raw = (stage.ROOT / "build/rpi5/gem-cpu-ring-retry-successor-capture-20261014/serial.bin").read_bytes()
        old = stage.checker.b.retry.trial.marker("304dd3f376024efab8ef4d63ef1dad80").encode()
        new = stage.checker.b.retry.trial.marker(stage.TAG).encode()
        self.assertEqual(raw.count(old), 1)
        raw = raw.replace(old, new, 1)
        old_size = b"Read probe.bin bytes 20169920 hnd "
        new_size = b"Read probe.bin bytes " + str(stage.case.IMAGE_BYTES).encode() + b" hnd "
        self.assertEqual(raw.count(old_size), 1)
        raw = raw.replace(old_size, new_size, 1)
        old_prep = b"RPI5XNU:PCIEID:DMA_PREP STEP=14 ERROR=-13 BYTES=32768 PACKETS=0\r\n"
        new_prep = b"RPI5XNU:PCIEID:DMA_PREP STEP=16 ERROR=0 BYTES=32768 PACKETS=0\r\n"
        self.assertEqual(raw.count(old_prep), 1)
        raw = raw.replace(old_prep, new_prep, 1)
        old_owner = (b"RPI5XNU:PCIEID:DMA_OWNER PREPARE=3 STATE=5 ATTEMPTED=0 ACTIVE=0 "
            b"REVOKED=0 DISABLED=0 RECORD=1\r\n")
        new_owner = old_owner.replace(b"PREPARE=3 STATE=5", b"PREPARE=2 STATE=8")
        self.assertEqual(raw.count(old_owner), 1)
        raw = raw.replace(old_owner, new_owner, 1)
        base = 0x6100000
        rows = [b"RPI5XNU:PCIEID:DMA_MAP REASON=41 PAGE=0 ATTR=0 VA=0 PA=0 PAR_R=0 PAR_W=0\r\n"]
        for page in range(2):
            pa = base + page * 0x4000
            par = (0x44 << 56) | pa | 0xB00
            for va in (1, 2):
                rows.append(("RPI5XNU:PCIEID:DMA_ALIAS PAGE=%d VA=%d CACHE=6 PA=%d PAR_R=%d "
                    "PAR_W=%d ATTR_R=68 ATTR_W=68 VALID=1\r\n" %
                    (page, va, pa, par, par)).encode())
        rows.append(b"RPI5XNU:PCIEID:DMA_PGTABLE START=50331648 END=50364416 BYTES=32768 "
            b"PAGES=2 MAX=257 PAGE_BYTES=16384 MAPPED=8589934592 RESERVATION_CLEAR=1\r\n")
        self.assertEqual(raw.count(new_owner), 1)
        return raw.replace(new_owner, b"".join(rows) + new_owner, 1)

    def prepared(self, folder):
        completed = subprocess.run([
            sys.executable, str(Path(stage.__file__).resolve()), "prepare",
            "--baseline", str(stage.BASELINE),
            "--prior-seal-sha256", stage.BASELINE_SEAL,
            "--prior-plan-sha256", stage.BASELINE_PLAN,
            "--linux-boot-id", stage.BASELINE_BOOT,
            "--output", str(folder),
        ], cwd=stage.ROOT, text=True, capture_output=True, timeout=180)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "prepared_only")
        return json.loads((folder / "checkpoint.json").read_text()), result["checkpoint_sha256"]

    def remote(self, checkpoint, pin):
        base = checkpoint["payload"]["media_plan"]
        plan, plan_sha = media.plan_from_seal(checkpoint, pin, media.TRIAL, "52" * 16,
            "/home/sandrzej/xnu-physmap-v4-offline", base)
        return media.remote_source(checkpoint, pin, plan, plan_sha), plan, plan_sha

    def test_catalog500_package_and_source_closure(self):
        self.assertEqual(stage.BASELINE_CATALOG, 500)
        self.assertEqual(stage.BASELINE_CATALOG_SHA,
            "3fb9b00235759812efa3627104c9dd5158551c3ea981d47b540d333fe0e02186")
        self.assertEqual(stage.BASELINE_BOOT, "a6c96368-1ef6-4c34-be8e-7efdd97a9395")
        self.assertEqual(stage.CONTROLLER, "gem-physmap-mapping-three-target-controller-v4")
        self.assertEqual(stage.DESCRIPTOR, "gem-physmap-mapping-fixed59")
        self.assertEqual(media.TRIAL, "gem-physmap-mapping-v4-triple-trial-v1")
        self.assertEqual(media.RESTORE, "gem-physmap-mapping-v4-triple-restore-v1")
        self.assertTrue(stage.valid_report(self.report()))
        pins = stage.source_pins()
        for module in (stage, media, protocol):
            self.assertEqual(pins[str(Path(module.__file__).resolve())], stage.sha(module.__file__))
        self.assertGreaterEqual(len(pins), 1600)

    def test_four_aliases_pgtable_discard_and_mutations(self):
        raw = self.capture()
        result = protocol.inspect(raw, self.report())
        self.assertTrue(result["physmap_mapping_verification_pass"])
        self.assertEqual([(r["page"], r["va"]) for r in result["aliases"]],
            [(0, 1), (0, 2), (1, 1), (1, 2)])
        self.assertEqual(result["mapping_predicate"]["reason"], 41)
        self.assertEqual(result["cpu_ring_owner"]["state"], 8)
        self.assertTrue(result["discard_before_route_observed"])
        self.assertFalse(any(result[k] for k in
            ("bme", "dma", "irq_delivery", "queue_publication", "ethernet_proven")))
        alias = b"RPI5XNU:PCIEID:DMA_ALIAS PAGE=0 VA=1 "
        line = raw[raw.index(alias):raw.index(b"\n", raw.index(alias)) + 1]
        mutations = (
            raw.replace(line, b"", 1),
            raw.replace(alias, b"RPI5XNU:PCIEID:DMA_ALIAS PAGE=1 VA=1 ", 1),
            raw.replace(b"CACHE=6", b"CACHE=2", 1),
            raw.replace(b"ATTR_R=68", b"ATTR_R=255", 1),
            raw.replace(b"BYTES=32768 PAGES=2", b"BYTES=16384 PAGES=2", 1),
            raw.replace(b"RESERVATION_CLEAR=1", b"RESERVATION_CLEAR=0", 1),
            raw.replace(b"PREPARE=2 STATE=8", b"PREPARE=2 STATE=5", 1),
            raw.replace(b"PHYSICAL=0 PCI=0", b"PHYSICAL=1 PCI=0", 1),
        )
        for mutated in mutations:
            with self.assertRaises(ValueError):
                protocol.inspect(mutated, self.report())

    def test_subprocess_prepare_remote_plan_and_namespace_audit(self):
        with tempfile.TemporaryDirectory(prefix="physmap-v4-cli-", dir=stage.ROOT / "build/rpi5") as name:
            folder = Path(name)
            folder.rmdir()
            checkpoint, pin = self.prepared(folder)
            source, plan, plan_sha = self.remote(checkpoint, pin)
            nodes = ast.parse(source).body
            expected = {}
            for index in range(9):
                module = nodes[1 + index * 6].targets[0].id
                text = ast.literal_eval(nodes[5 + index * 6].value)
                expected[module] = namespace.sha(text.encode())
            result = namespace.inspect(source, namespace.sha(source.encode()), expected, plan_sha)
            self.assertTrue(result["bootstrap_no_io"] and result["pure_plan_no_io"])
            self.assertTrue(result["actual_execute_to_identity"])
            self.assertFalse(result["device_access"] or result["publication_tested"])
            code = ("import hashlib,json,sys;sys.path.insert(0," + repr(str(stage.ROOT)) +
                ");from pathlib import Path;from tools.rpi5 import gem_physmap_mapping_media_v1 as m;" +
                "from tools.rpi5 import trial_checkpoint_v2 as seals;" +
                "d=Path(" + repr(str(folder)) + ");c=json.loads((d/'checkpoint.json').read_text());" +
                "p=seals.digest(c);base=c['payload']['media_plan'];plan,h=m.plan_from_seal(c,p,m.TRIAL,'53'*16," +
                "'/home/sandrzej/xnu-physmap-v4-subprocess',base);s=m.remote_source(c,p,plan,h);" +
                "print(json.dumps({'plan':h,'remote':hashlib.sha256(s.encode()).hexdigest(),'tx':0}))")
            completed = subprocess.run([sys.executable, "-I", "-c", code], cwd=stage.ROOT,
                text=True, capture_output=True, timeout=90, env={"PATH": os.environ.get("PATH", "")})
            self.assertEqual(completed.returncode, 0, completed.stderr)
            emitted = json.loads(completed.stdout)
            self.assertEqual(emitted["tx"], 0)
            self.assertRegex(emitted["plan"], r"^[0-9a-f]{64}$")
            self.assertRegex(emitted["remote"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()

