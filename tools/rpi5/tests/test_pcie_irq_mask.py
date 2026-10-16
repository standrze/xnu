# SPDX-License-Identifier: BSD-2-Clause
"""Selective masking models plus actual pexpert compile and full kernel link."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import build_pcie_irq_kernel as builder


class PCIeIRQMaskTests(unittest.TestCase):
    def test_sanitized_core_and_actual_pe_body_models(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            for name, marker in (("pcie_irq_mask_host.c", b"BEGIN_FAILURES=106 CHECK_FAILURES=61"),
                                 ("pcie_irq_owner_host.c", b"ACTUAL_PE_BODY=1 THREAD_WDOG_ATOMIC_OUTPUT=1")):
                program = work / name
                command = ["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                           "-fsanitize=address,undefined", "-I", str(builder.ROOT),
                           "-I", str(builder.ROOT / "loader/rpi5"),
                           "-I", str(Path(__file__).with_name("pcie_irq_stubs")),
                           str(Path(__file__).with_name(name)), str(builder.CORE), "-o", str(program)]
                compile = subprocess.run(command, capture_output=True, timeout=60)
                self.assertEqual(compile.returncode, 0, compile.stderr.decode())
                result = subprocess.run([str(program)], capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertIn(marker, result.stdout)
                self.assertIn(b"NO_MMIO=1", result.stdout)

    def test_freestanding_core_only_standard_kernel_memory_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            obj = Path(directory) / "irq.o"
            subprocess.run(["xcrun", "clang", "--target=aarch64-none-elf", "-mcpu=cortex-a76",
                            "-mstrict-align", "-mgeneral-regs-only", "-ffreestanding", "-fno-builtin",
                            "-fno-stack-protector", "-O2", "-Wall", "-Wextra", "-Werror", "-c",
                            str(builder.CORE), "-o", str(obj)], check=True, capture_output=True, timeout=60)
            undefined = builder.audit.read_command(["xcrun", "llvm-nm", "--undefined-only", obj])
            self.assertLessEqual({line.split()[-1] for line in undefined.splitlines()}, {"memcpy", "memset"})
            # Standard C aggregate copies/zero initialization may emit these;
            # the complete actual XNU link below must resolve every dependency.

    def test_real_complete_kernel_opt_in_original_pins_and_no_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "irq-kernel"
            report = builder.build(out)
            for key in ("complete_kernel_link_proven", "actual_existing_gic_mapping_reused",
                        "actual_existing_watchdog_lease_reused", "claim_bound_to_thread",
                        "claim_nonblocking", "exact_w1c_masks", "nonsecure_view_only"):
                self.assertTrue(report[key], key)
            for key in ("nvme_bits_written", "release_restore_cleanup_implemented", "secure_firmware_ownership_proven",
                        "concrete_lifecycle_provider_added", "provider_personality_added", "boot_caller_added",
                        "new_mapped_pages", "initializer_runtime_executed", "physical_recovery_proven",
                        "irq_dma_authorized", "installed", "pi_executed", "ethernet_proven",
                        "loader_package_created", "sd_actions", "serial_actions", "reboots"):
                self.assertFalse(report[key], key)
            self.assertEqual(len(report["link"]["irq_implementations"]), 5)
            self.assertEqual(len(report["link"]["added_initializers"]), 7)
            self.assertEqual(report["new_linker_warnings"], [])
            for row in report["compiles"]:
                self.assertEqual(row["returncode"], 0); self.assertEqual(row["warning_count"], 0)
            for name, digest in {**report["inputs_sha256"], **report["generated_sha256"]}.items():
                self.assertEqual(builder.audit.sha(Path(name)), digest, name)
            before = (out / "manifest.json").read_bytes()
            with self.assertRaises(FileExistsError): builder.build(out)
            self.assertEqual(before, (out / "manifest.json").read_bytes())
            args = [a for a in report["compiles"][0]["command"][:-2] if a != "-c"]
            restricted = subprocess.run(args + ["-UDEVELOPMENT", "-DDEVELOPMENT=0", "-fsyntax-only"],
                                        cwd=builder.audit.OBJ / "pexpert/DEVELOPMENT", capture_output=True, timeout=60)
            self.assertNotEqual(restricted.returncode, 0)
            self.assertIn(b"opt-in BCM2712 DEVELOPMENT", restricted.stderr)
            # Macro disabled changes no original watchdog owner's preprocessed
            # behavior (including subsequent panic line numbers).
            common = [a for a in args if a != "-DRPI5_PCIE_IRQ_MASK=1"] + ["-DRPI5_PCIE_IRQ_MASK=0", "-E", "-P",
                "-Wno-builtin-macro-redefined", '-D__TIME__="00:00:00"', '-D__DATE__="Jan 01 2000"']
            actual = subprocess.run(common, cwd=builder.audit.OBJ / "pexpert/DEVELOPMENT", capture_output=True, timeout=60)
            expected = subprocess.run([str(builder.OWNER / "pe_fiq.c") if a == str(out / "pe_fiq.c") else a for a in common],
                                      cwd=builder.audit.OBJ / "pexpert/DEVELOPMENT", capture_output=True, timeout=60)
            self.assertEqual(actual.returncode, 0, actual.stderr.decode())
            self.assertEqual(expected.returncode, 0, expected.stderr.decode())
            normalize = lambda data: [line.strip() for line in data.splitlines() if line.strip()]
            self.assertEqual(normalize(actual.stdout), normalize(expected.stdout))

    def test_preserved_receipt_and_unsafe_output_refused(self):
        with patch.object(builder, "BASE_SHA", "0" * 64):
            with self.assertRaisesRegex(ValueError, "controller receipt changed"): builder.inputs()
        for parent in (builder.ROOT / "pexpert", builder.ROOT / "loader", builder.BASE, builder.audit.OBJ, builder.audit.SDK):
            out = parent / "must-not-create-irq-kernel"
            with self.assertRaisesRegex(ValueError, "separate fresh"): builder.build(out)
            self.assertFalse(out.exists())


if __name__ == "__main__": unittest.main()
