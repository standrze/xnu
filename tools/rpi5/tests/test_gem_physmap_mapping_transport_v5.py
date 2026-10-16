# SPDX-License-Identifier: BSD-2-Clause
"""Catalog512 corrected physmap v5 transport is self-contained and hardware-inert."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.rpi5 import gem_physmap_mapping_media_v5 as media
from tools.rpi5 import gem_physmap_mapping_serial_v5 as protocol
from tools.rpi5 import remote_namespace_audit_v1 as namespace
from tools.rpi5 import stage_gem_physmap_mapping_trial_v5 as stage


class PhysmapMappingTransportV5Tests(unittest.TestCase):
    def report(self):
        return stage.checker.inspect(stage.PACKAGE, stage.MANIFEST_SHA)

    def capture(self):
        raw = (stage.ROOT / "build/rpi5/gem-cpu-ring-retry-successor-capture-20261014/serial.bin").read_bytes()
        old = stage.checker.b.retry.trial.marker("304dd3f376024efab8ef4d63ef1dad80").encode()
        new = self.report()["trial_marker"].encode()
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
        rows.append(b"RPI5XNU:PCIEID:DMA_PGTABLE START=50331648 END=50413568 BYTES=81920 "
            b"PAGES=5 MAX=259 EDGE=2 UPPER=1 PAGE_BYTES=16384 MAPPED=100597760 "
            b"RESERVATION_CLEAR=1\r\n")
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
        return (json.loads((folder / "checkpoint.json").read_text()),
            result["checkpoint_sha256"], result["metrics"])

    def remote(self, checkpoint, pin):
        base = checkpoint["payload"]["media_plan"]
        plan, plan_sha = media.plan_from_seal(checkpoint, pin, media.TRIAL, "52" * 16,
            "/home/sandrzej/xnu-physmap-v5-offline", base)
        return media.remote_source(checkpoint, pin, plan, plan_sha), plan, plan_sha

    def test_catalog512_v10_package_and_enabled_unit_closure(self):
        self.assertEqual(stage.BASELINE_CATALOG, 512)
        self.assertEqual(stage.BASELINE_SEAL,
            "6b55bf9cf939bb70a58e3781cf1f54eb0633167a95bde75db6bc663df6bdb2b3")
        self.assertEqual(stage.BASELINE_PLAN,
            "f77a4e94248d6df7b215086ff32aa18acf94ad570509e48a3d384b7cd9a0ce37")
        self.assertEqual(stage.BASELINE_RESULT,
            "20345faa425243b43f1578aa30f1c0c3983192cd21fde92a9906ee2555f38298")
        self.assertEqual(stage.BASELINE_CATALOG_SHA,
            "8f7be2df370eb5a6951e645fca95d0609db141cf07ac53da020e7bcd26964566")
        self.assertEqual(stage.BASELINE_BOOT, "5a1f5c04-c3d6-463a-8785-d737a3d59935")
        self.assertEqual(stage.MANIFEST_SHA,
            "a73188d0234348025b151bc66ee7f5cb7763efd867871d23a4c5379eba7df141")
        self.assertEqual(stage.IMAGE_SHA,
            "5fad73f69c09f05431ece249204c7ae52b07e2f6df45b12370019f26ed1a39df")
        self.assertEqual(stage.TAG, "96a5f52e3bd546fc8687f63e9b6459e9")
        self.assertEqual(stage.CONTROLLER, "gem-physmap-mapping-three-target-controller-v5")
        self.assertEqual(stage.DESCRIPTOR, "gem-physmap-mapping-fixed59-v5")
        self.assertEqual(media.TRIAL, "gem-physmap-mapping-v5-triple-trial-v1")
        self.assertEqual(media.RESTORE, "gem-physmap-mapping-v5-triple-restore-v1")
        report = self.report()
        self.assertTrue(stage.valid_report(report))
        self.assertEqual(report["marker"], report["trial_marker"])
        self.assertEqual(report["maximum_page_table_pages"], 259)
        self.assertEqual(report["maximum_page_table_bytes"], 4243456)
        self.assertEqual(report["preallocated_upper_pages"], 1)
        image = (stage.PACKAGE / "probe.bin").read_bytes()
        self.assertEqual(image.count(report["trial_marker"].encode()), 1)
        manifest = json.loads((stage.PACKAGE / "manifest.json").read_text())
        replaced = {Path(value).name for value in manifest["replaced_objects"].values()}
        self.assertTrue({"pmap-enabled.o", "arm_vm_init-enabled.o", "loose_ends-enabled.o"} <= replaced)
        flagged = []
        for item in manifest["commands"]:
            command = item["command"]
            if any("RPI5_GEM_PAGE_GRANULAR_PHYSMAP=1" in arg for arg in command):
                flagged.extend(Path(arg).name for arg in command if arg.endswith((".c", ".cpp")))
        self.assertEqual(sorted(flagged), ["arm_vm_init.c", "loose_ends.c", "pmap.c"])
        pins = stage.source_pins()
        for module in (stage, media, protocol):
            self.assertEqual(pins[str(Path(module.__file__).resolve())], stage.sha(module.__file__))
        self.assertGreaterEqual(len(pins), 1600)

    def test_four_aliases_accounting_discard_and_mutations(self):
        raw = self.capture()
        result = protocol.inspect(raw, self.report())
        self.assertTrue(result["physmap_mapping_verification_pass"])
        self.assertEqual([(row["page"], row["va"]) for row in result["aliases"]],
            [(0, 1), (0, 2), (1, 1), (1, 2)])
        self.assertTrue(all(row["attr_r"] == row["attr_w"] == 0x44 for row in result["aliases"]))
        self.assertEqual(result["mapping_predicate"]["reason"], 41)
        self.assertEqual(result["page_table_accounting"]["edge"], 2)
        self.assertEqual(result["page_table_accounting"]["upper"], 1)
        self.assertEqual(result["cpu_ring_owner"]["state"], 8)
        self.assertTrue(result["discard_before_route_observed"])
        self.assertFalse(any(result[key] for key in
            ("bme", "dma", "irq_delivery", "queue_publication", "ethernet_proven")))
        alias = b"RPI5XNU:PCIEID:DMA_ALIAS PAGE=0 VA=1 "
        line = raw[raw.index(alias):raw.index(b"\n", raw.index(alias)) + 1]
        marker = self.report()["trial_marker"].encode()
        mismatched_report = dict(self.report(), trial_marker="wrong")
        with self.assertRaises(ValueError):
            protocol.inspect(raw, mismatched_report)
        mutations = (
            raw.replace(line, b"", 1),
            raw.replace(alias, b"RPI5XNU:PCIEID:DMA_ALIAS PAGE=1 VA=1 ", 1),
            raw.replace(b"CACHE=6", b"CACHE=2", 1),
            raw.replace(b"ATTR_R=68", b"ATTR_R=255", 1),
            raw.replace(b"MAX=259", b"MAX=4", 1),
            raw.replace(b"MAX=259", b"MAX=260", 1),
            raw.replace(b"EDGE=2", b"EDGE=3", 1),
            raw.replace(b"UPPER=1", b"UPPER=0", 1),
            raw.replace(b"BYTES=81920", b"BYTES=65536", 1),
            raw.replace(b"RESERVATION_CLEAR=1", b"RESERVATION_CLEAR=0", 1),
            raw.replace(b"REASON=41", b"REASON=26", 1),
            raw.replace(b"PREPARE=2 STATE=8", b"PREPARE=2 STATE=5", 1),
            raw.replace(b"PHYSICAL=0 PCI=0", b"PHYSICAL=1 PCI=0", 1),
            raw.replace(marker, b"RPI5XNU:CPU_RINGS:ENTRY TAG=6db66759d35d47789e3dc1c21a3481f9 CPUS=1 NO_CPU_ON NO_QUEUE NO_DMA", 1),
            raw + marker,
        )
        for mutated in mutations:
            with self.assertRaises(ValueError):
                protocol.inspect(mutated, self.report())

    def test_captured_v9_wrong_marker_and_max4_is_rejected(self):
        captured = (stage.ROOT / "build/rpi5/gem-physmap-mapping-v4-capture/serial.bin").read_bytes()
        self.assertIn(b"TAG=6db66759d35d47789e3dc1c21a3481f9", captured)
        self.assertIn(b"PAGES=5 MAX=4", captured)
        with self.assertRaises(ValueError):
            protocol.inspect(captured, self.report())

    def test_subprocess_prepare_remote_plan_and_namespace_audit(self):
        with tempfile.TemporaryDirectory(prefix="physmap-v5-cli-", dir=stage.ROOT / "build/rpi5") as name:
            folder = Path(name)
            folder.rmdir()
            checkpoint, pin, metrics = self.prepared(folder)
            self.assertEqual(checkpoint["payload"]["media_plan"]["controller"], stage.CONTROLLER)
            self.assertTrue(checkpoint["payload"]["media_plan"]["no_reboot"])
            self.assertFalse(checkpoint["hardware_admission"])
            self.assertTrue(metrics["recorder_admission"]["modem_gate_bound_before_arm"])
            self.assertTrue(metrics["recorder_admission"]["recorder_namespace_bound_without_serial"])
            self.assertEqual(metrics["recorder_admission"]["transmitted_bytes"], 0)
            source, _plan, plan_sha = self.remote(checkpoint, pin)
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
                ");from pathlib import Path;from tools.rpi5 import gem_physmap_mapping_media_v5 as m;" +
                "from tools.rpi5 import trial_checkpoint_v2 as seals;" +
                "d=Path(" + repr(str(folder)) + ");c=json.loads((d/'checkpoint.json').read_text());" +
                "p=seals.digest(c);base=c['payload']['media_plan'];plan,h=m.plan_from_seal(c,p,m.TRIAL,'53'*16," +
                "'/home/sandrzej/xnu-physmap-v5-subprocess',base);s=m.remote_source(c,p,plan,h);" +
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
