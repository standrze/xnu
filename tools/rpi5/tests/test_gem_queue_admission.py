# SPDX-License-Identifier: BSD-2-Clause
"""Default-off queue-base admission candidate; no BME, DMA, IRQ or packets."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "iokit/Kernel/rpi5_gem_queue_admission.c"
HEADER = ROOT / "iokit/Kernel/rpi5_gem_queue_admission.h"
HOST = ROOT / "tools/rpi5/tests/gem_queue_admission_host.c"
SOURCES = ROOT / "tools/rpi5/gem_queue_admission_sources.json"


class GEMQueueAdmissionTests(unittest.TestCase):
    def test_sanitized_sequence_rejections_and_all_callback_faults(self):
        with tempfile.TemporaryDirectory(prefix="gem-queue-admission-") as name:
            executable = Path(name) / "host"
            result = subprocess.run(
                [
                    "xcrun", "clang", "-std=c11", "-O1", "-g", "-Wall",
                    "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    "-I", str(CORE.parent), str(CORE), str(HOST), "-o",
                    str(executable),
                ],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run(
                [executable], capture_output=True, text=True, timeout=60
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                result.stdout,
                "GEM_QUEUE_ADMISSION_PASS DEFAULT_OFF BME0 RE0 TE0 IRQ0 "
                "DMA0 PACKETS0\n",
            )

    def test_a76_object_is_self_contained_and_has_no_activation_instruction(self):
        with tempfile.TemporaryDirectory(prefix="gem-queue-admission-a76-") as name:
            obj = Path(name) / "queue.o"
            subprocess.run(
                [
                    "xcrun", "clang", "--target=aarch64-none-elf",
                    "-mcpu=cortex-a76", "-mstrict-align",
                    "-mgeneral-regs-only", "-ffreestanding", "-fno-builtin",
                    "-fno-stack-protector", "-std=c11", "-O2", "-Wall",
                    "-Wextra", "-Werror", "-I", str(CORE.parent), "-c",
                    str(CORE), "-o", str(obj),
                ],
                check=True, capture_output=True, timeout=60,
            )
            undefined = subprocess.check_output(
                ["xcrun", "llvm-nm", "--undefined-only", obj], text=True
            )
            self.assertEqual(undefined, "")
            assembly = subprocess.check_output(
                ["xcrun", "llvm-objdump", "-d", obj], text=True
            )
            instructions = set(re.findall(
                r"^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+(\w+)", assembly, re.M
            ))
            self.assertFalse(instructions & {"smc", "hvc", "mrs", "msr", "dc", "ic"})

    def test_primary_sources_and_no_production_wiring(self):
        metadata = json.loads(SOURCES.read_text())
        self.assertEqual(metadata["format"], "rpi5-gem-queue-admission-v1")
        self.assertFalse(metadata["bus_master_enabled"])
        self.assertFalse(metadata["dma_enabled"])
        self.assertFalse(metadata["interrupts_enabled"])
        self.assertFalse(metadata["packets"])
        self.assertEqual(metadata["provider_bytes_required"], 0x48000)
        self.assertEqual(metadata["packet_spans_required"], 128)
        for row in metadata["sources"]:
            data = (ROOT / row["path"]).read_bytes()
            self.assertEqual(len(data), row["bytes"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), row["sha256"])
        linux_header = (ROOT / metadata["sources"][0]["path"]).read_text()
        for symbol, offset in (
            ("MACB_NCR", "0x0000"), ("MACB_RBQP", "0x0018"),
            ("MACB_TBQP", "0x001c"), ("MACB_IMR", "0x0030"),
            ("MACB_TBQPH", "0x04C8"), ("MACB_RBQPH", "0x04D4"),
        ):
            self.assertRegex(
                linux_header, rf"#define\s+{symbol}\s+{offset}\b"
            )
        text = HEADER.read_text() + CORE.read_text()
        self.assertNotIn("SET_BME", text)
        self.assertNotIn("set_bus_master", text)
        self.assertIn("provider_bytes != UINT32_C(0x48000)", CORE.read_text())
        users = []
        for top in ("bsd", "iokit", "libkern", "osfmk", "pexpert", "security"):
            for path in (ROOT / top).rglob("*"):
                if not path.is_file() or path in (CORE, HEADER):
                    continue
                if path.suffix not in (".c", ".cpp", ".h", ".inc"):
                    continue
                if "rpi5_gem_queue_admission.h" in path.read_text(errors="ignore"):
                    users.append(str(path.relative_to(ROOT)))
        self.assertEqual(users, [])


if __name__ == "__main__":
    unittest.main()
