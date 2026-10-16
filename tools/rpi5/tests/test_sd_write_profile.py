# SPDX-License-Identifier: BSD-2-Clause
"""Sealed persistence-media profile generation; no device or network access."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.rpi5 import build_sd_write_profile as builder


ROOT = Path(__file__).resolve().parents[3]
SD = ROOT / "build/rpi5/hfs-linux-reference-xk6euh6j/reference.json"
FIXTURE = ROOT / "build/rpi5/hfs-read-fixture-h9wpku5p/reference.json"


class SDWriteProfileTests(unittest.TestCase):
    def test_existing_references_generate_compilable_external_profile(self):
        if not SD.is_file() or not FIXTURE.is_file():
            self.skipTest("pinned physical references unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / "profile"
            subprocess.run(["python3", str(ROOT / "tools/rpi5/build_sd_write_profile.py"),
                "--sd-reference", str(SD), "--fixture-reference", str(FIXTURE),
                "--output", str(out)], check=True, capture_output=True, text=True)
            report = json.loads((out / "profile.json").read_text())
            self.assertEqual(report["format"], "rpi5-sd-write-profile-v1")
            self.assertFalse(report["cache_state_proven"])
            self.assertFalse(report["write_authorized"])
            self.assertFalse(report["durability_verified"])
            check = root / "check.c"
            check.write_text('''
#include "rpi5_sd_write_policy.h"
#include <assert.h>
int main(void) {
    const struct rpi5_sd_write_profile *p=rpi5_sd_write_selected_profile();
    assert(rpi5_sd_write_profile_valid(p));
    assert(p->sectors==UINT64_C(250347520));
    assert(p->start==UINT64_C(1050624) && p->blocks==UINT64_C(262144));
    return 0;
}
''')
            binary = root / "check"
            subprocess.run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-DRPI5_SD_WRITE_EXTERNAL_PROFILE=1", "-I", str(ROOT / "iokit/Kernel"),
                str(check), str(out / "rpi5_sd_write_external_profile.c"),
                str(ROOT / "iokit/Kernel/rpi5_sd_write_policy.c"), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_rejects_changed_read_hash_geometry_and_write_taint(self):
        if not SD.is_file() or not FIXTURE.is_file():
            self.skipTest("pinned physical references unavailable")
        base = json.loads(SD.read_text())
        fixture = json.loads(FIXTURE.read_text())
        mutations = []
        changed = json.loads(json.dumps(base)); changed["partition_reads"][1]["sha256"] = "0" * 64
        mutations.append(changed)
        changed = json.loads(json.dumps(base)); changed["identity"]["partition_sectors"] += 1
        mutations.append(changed)
        changed = json.loads(json.dumps(base)); changed["sd_write_operations"] = 1
        mutations.append(changed)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_path = root / "fixture.json"
            fixture_path.write_text(json.dumps(fixture, sort_keys=True))
            # Bind each mutated reference to this temporary fixture so the
            # intended mutation, not an unrelated source-hash mismatch, fails.
            import hashlib
            fixture_hash = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
            for index, value in enumerate(mutations):
                value["fixture_reference_sha256"] = fixture_hash
                path = root / f"sd-{index}.json"
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    builder.build(path, fixture_path)


if __name__ == "__main__":
    unittest.main()
