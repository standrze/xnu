# SPDX-License-Identifier: BSD-2-Clause
"""Host register/binding models, not physical SD storage acceptance."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent


class SDHCITests(unittest.TestCase):
    def test_kernel_binding_request_bounds_and_serial_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "sd-contract"
            subprocess.run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", "-I", str(ROOT / "iokit/Kernel"),
                            str(HERE / "sd_contract_host.c"), str(ROOT / "iokit/Kernel/rpi5_sd_contract.c"),
                            "-o", str(binary)], check=True)
            result = subprocess.run([str(binary)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b"SD_CONTRACT_PASS\n")

    def test_native_endian_root_node_attachment(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "sdhci-tree"
            subprocess.run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", "-I", str(ROOT / "loader/rpi5"),
                            "-I", str(ROOT / "iokit/Kernel"), str(ROOT / "iokit/Kernel/rpi5_sd_contract.c"),
                            str(HERE / "sdhci_tree_host.c"),
                            *[str(ROOT / "loader/rpi5" / name) for name in
                              ("board_tree.c", "cpu_tree.c", "serial_tree.c", "apple_dt.c", "memory_type.c")],
                            "-o", str(binary)], check=True)
            result = subprocess.run([str(binary)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b"SDHCI_TREE_PASS\n")

    def test_freestanding_cortex_a76_transport_compile(self):
        with tempfile.TemporaryDirectory() as directory:
            for source, symbols in (("rpi5_sdhci_core", ("rpi5_sd_read_sector", "rpi5_sd_start")),
                                    ("rpi5_sd_handoff", ("rpi5_sd_handoff",)),
                                    ("rpi5_sd_contract", ("rpi5_sd_binding_decode", "rpi5_sd_queue_push"))):
                obj = Path(directory) / (source + ".o")
                subprocess.run(["xcrun", "clang", "--target=aarch64-none-elf", "-mcpu=cortex-a76",
                                "-mstrict-align", "-mgeneral-regs-only", "-ffreestanding", "-fno-builtin",
                                "-fno-stack-protector", "-O2", "-Wall", "-Wextra", "-Werror",
                                "-c", str(ROOT / "iokit/Kernel" / (source + ".c")), "-o", str(obj)], check=True)
                assembly = subprocess.check_output(["xcrun", "llvm-objdump", "-d", str(obj)], text=True)
                for symbol in symbols:
                    self.assertIn("<" + symbol + ">:", assembly)

    def test_digital_power_handoff_masks_order_and_faults(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "sd-handoff"
            subprocess.run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", "-I", str(ROOT / "iokit/Kernel"),
                            str(HERE / "sd_handoff_host.c"),
                            str(ROOT / "iokit/Kernel/rpi5_sd_handoff.c"),
                            "-o", str(binary)], check=True)
            result = subprocess.run([str(binary)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b"SD_HANDOFF_PASS\n")

    def test_pio_protocol_capacity_timeouts_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "sdhci-core"
            subprocess.run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", "-I", str(ROOT / "iokit/Kernel"),
                            str(HERE / "sdhci_core_host.c"),
                            str(ROOT / "iokit/Kernel/rpi5_sdhci_core.c"),
                            "-o", str(binary)], check=True)
            result = subprocess.run([str(binary)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b"SDHCI_CORE_PASS\n")

    def test_pinned_removable_slot_binding_and_mutations(self):
        blob = ROOT / "build/rpi5/bcm2712-rpi-5-b-2768f610.dtb"
        if not blob.exists():
            self.skipTest("pinned firmware DTB not downloaded")
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "sdhci-fdt"
            subprocess.run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", "-I", str(ROOT / "loader/rpi5"),
                            str(HERE / "sdhci_fdt_host.c"),
                            str(ROOT / "loader/rpi5/fdt.c"), str(ROOT / "loader/rpi5/fdt_reg.c"),
                            "-o", str(binary)], check=True)
            result = subprocess.run([str(binary), str(blob)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b"SDHCI_FDT_PASS\n")


if __name__ == "__main__":
    unittest.main()
