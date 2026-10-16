# SPDX-License-Identifier: BSD-2-Clause
"""USB-specific retained Apple DMA allocation and RP1 route tests."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
PROVIDER = ROOT / "iokit/Kernel/BCM2712USBXHCIMemory.cpp"
HEADER = PROVIDER.with_suffix(".h")
ROUTE = ROOT / "iokit/Kernel/rpi5_rp1_dma_route.c"
LAYOUT = ROOT / "loader/rpi5/rp1_usb_xhci_dma_layout.c"
NOOP = ROOT / "loader/rpi5/rp1_usb_xhci_noop.c"
CONTROL = ROOT / "loader/rpi5/usb_xhci_control_transfer.c"
DEVICE = ROOT / "loader/rpi5/usb_xhci_device_context.c"
HID_SETUP = ROOT / "loader/rpi5/usb_hid_boot_setup.c"
KEYBOARD_ENDPOINT = ROOT / "loader/rpi5/usb_xhci_keyboard_endpoint.c"


class USBXHCIMemoryTests(unittest.TestCase):
    def test_complete_rp1_route_is_atomic(self):
        with tempfile.TemporaryDirectory(prefix="rp1-dma-route-") as folder:
            executable = Path(folder) / "route"
            subprocess.run([
                "xcrun", "clang", "-std=c11", "-O1", "-g", "-Wall",
                "-Wextra", "-Werror", "-fsanitize=address,undefined",
                "-I", str(ROOT / "iokit/Kernel"),
                "-I", str(ROOT / "loader/rpi5"),
                str(Path(__file__).with_name("rp1_dma_route_host.c")),
                str(ROUTE), str(ROOT / "loader/rpi5/pcie_windows.c"),
                "-o", str(executable)], check=True, timeout=60)
            result = subprocess.run([executable], capture_output=True,
                text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("NO_DMA_AUTHORITY", result.stdout)

    def test_provider_source_has_retained_apple_and_no_activation(self):
        header = HEADER.read_text()
        body = PROVIDER.read_text()
        self.assertIn("IOBufferMemoryDescriptor", header)
        self.assertIn("IODMACommand", header)
        self.assertIn("kIOMemoryPhysicallyContiguous", body)
        self.assertIn("kIOMemoryMapperNone", body)
        self.assertIn("kIOMapWriteCombineCache", body)
        self.assertIn("IODMACommand::kUnmapped", body)
        self.assertIn("rpi5_rp1_xhci_dma_layout", body)
        self.assertNotRegex(body, r"\b(write32|doorbell|USBCMD|DCBAAP|CRCR)\b")
        self.assertNotIn("rpi5_gem_dma_route", body + header)

    def test_actual_provider_methods_with_fault_injection(self):
        gem_host = Path(__file__).with_name("gem_dma_memory_host.cpp").read_text()
        support = gem_host.split("/*PROVIDER_HEADER*/", 1)[0]
        support = support.replace('"rpi5_gem_dma_route.h"',
            '"rpi5_rp1_dma_route.h"').replace("0x48000", "0x50000")
        header = "\n".join(line for line in HEADER.read_text().splitlines()
            if not line.startswith("#include <"))
        body = PROVIDER.read_text()
        body = body[body.index("static bool\ntranslated_nc("):]
        begin = body.index("static bool\ntranslated_nc(")
        end = body.index("bool\nBCM2712USBXHCIMemory::context()", begin)
        fake = '''static bool\ntranslated_nc(uint64_t virtual_address,
    uint64_t physical, uint64_t *read_proof = nullptr,
    uint64_t *write_proof = nullptr)
{
    if (read_proof) *read_proof = (UINT64_C(0x44) << 56) |
        (physical & UINT64_C(0x0000fffffffff000));
    if (write_proof) *write_proof = (UINT64_C(0x44) << 56) |
        (physical & UINT64_C(0x0000fffffffff000));
    return fake_translated_nc(virtual_address, physical);
}
'''
        body = body[:begin] + fake + body[end:]
        suffix = Path(__file__).with_name(
            "usb_xhci_memory_host_suffix.cpp").read_text()
        source = support + "static void OSSynchronizeIO() {}\n" + \
            header + "\n" + body + "\n" + suffix
        with tempfile.TemporaryDirectory(prefix="usb-xhci-memory-host-") as folder:
            folder = Path(folder)
            host = folder / "host.cpp"
            host.write_text(source)
            objects = []
            for path in (ROUTE, LAYOUT, NOOP, CONTROL, DEVICE, HID_SETUP,
                    KEYBOARD_ENDPOINT,
                    ROOT / "loader/rpi5/pcie_windows.c",
                    ROOT / "loader/rpi5/pcie_released_windows.c"):
                target = folder / (path.name + ".o")
                subprocess.run(["xcrun", "clang", "-std=c11", "-O1", "-g",
                    "-fsanitize=address,undefined", "-I",
                    str(ROOT / "iokit/Kernel"), "-I",
                    str(ROOT / "loader/rpi5"), "-c", str(path), "-o",
                    str(target)], check=True, timeout=60)
                objects.append(target)
            executable = folder / "host"
            result = subprocess.run(["xcrun", "clang++", "-std=c++17",
                "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-I", str(ROOT), "-I",
                str(ROOT / "iokit/Kernel"), "-I", str(ROOT / "osfmk"),
                "-I", str(ROOT / "loader/rpi5"), str(host),
                *map(str, objects), "-o", str(executable)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([executable], capture_output=True,
                text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("USB_XHCI_APPLE_MEMORY_PASS", result.stdout)
            self.assertIn("NO_HARDWARE_PROOF", result.stdout)

    def test_actual_a76_object_and_imports(self):
        from tools.rpi5.tests.test_gem_dma_memory import target_command
        arguments, cwd = target_command()
        source = str(PROVIDER.resolve())
        arguments = [source if value.endswith(
            "/overlay/BCM2712PCIePHYTransport.cpp") or value.endswith(
                "/iokit/Kernel/BCM2712GEMDMAMemory.cpp") else value
            for value in arguments]
        with tempfile.TemporaryDirectory(prefix="usb-xhci-memory-a76-") as folder:
            object_path = Path(folder) / "provider.o"
            result = subprocess.run(arguments + ["-o", str(object_path)],
                cwd=cwd, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            imports = subprocess.check_output(
                ["xcrun", "nm", "-ju", object_path], text=True).splitlines()
            self.assertIn("_rpi5_rp1_dma_route", imports)
            self.assertIn("_rpi5_rp1_xhci_dma_layout", imports)
            self.assertIn("_rpi5_rp1_xhci_noop_image", imports)
            self.assertIn("_rpi5_usb_k65_descriptor_batch", imports)
            self.assertIn("_rpi5_usb_xhci_enable_slot_plan", imports)
            self.assertIn("_rpi5_usb_xhci_address_k65_plan", imports)
            self.assertIn("_rpi5_usb_xhci_configure_k65_keyboard", imports)
            self.assertIn("_rpi5_usb_k65_hid_boot_setup", imports)
            self.assertIn("_rpi5_usb_k65_hid_boot_setup_idle", imports)
            self.assertIn("_rpi5_usb_xhci_k65_interrupt_plan", imports)
            self.assertIn("_rpi5_usb_xhci_k65_stream_plan", imports)
            self.assertIn("_pmap_cache_attributes", imports)
            assembly = subprocess.check_output(
                ["xcrun", "llvm-objdump", "-d", object_path], text=True)
            self.assertIn("s1e1r", assembly)
            self.assertIn("s1e1w", assembly)
            self.assertIn("PAR_EL1", assembly)
            self.assertNotIn("smc\t", assembly)
            self.assertNotIn("___cxx_global_var_init",
                subprocess.check_output(["xcrun", "nm", object_path],
                    text=True))

    def test_provider_and_pure_layout_symbols_link_together(self):
        from tools.rpi5.tests.test_gem_dma_memory import target_command
        arguments, cwd = target_command()
        with tempfile.TemporaryDirectory(prefix="usb-xhci-link-") as folder:
            folder = Path(folder)
            objects = []
            for source in (ROUTE, LAYOUT, NOOP, CONTROL, DEVICE, HID_SETUP,
                    KEYBOARD_ENDPOINT):
                target = folder / (source.name + ".o")
                result = subprocess.run([
                    "xcrun", "clang", "-target", "arm64-apple-macos11",
                    "-std=c11", "-O2", "-ffreestanding", "-fno-builtin",
                    "-I", str(ROOT / "iokit/Kernel"),
                    "-I", str(ROOT / "loader/rpi5"), "-c", str(source),
                    "-o", str(target)], capture_output=True, text=True,
                    timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                objects.append(target)
            provider = folder / "provider.o"
            source = str(PROVIDER.resolve())
            arguments = [source if value.endswith(
                "/overlay/BCM2712PCIePHYTransport.cpp") or value.endswith(
                    "/iokit/Kernel/BCM2712GEMDMAMemory.cpp") else value
                for value in arguments]
            result = subprocess.run(arguments + ["-o", str(provider)], cwd=cwd,
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            undefined = subprocess.check_output(
                ["xcrun", "nm", "-ju", provider], text=True).splitlines()
            defined = "\n".join(subprocess.check_output(
                ["xcrun", "nm", str(path)], text=True) for path in objects)
            for symbol in ("_rpi5_rp1_dma_route",
                    "_rpi5_rp1_xhci_dma_layout",
                    "_rpi5_rp1_xhci_noop_image",
                    "_rpi5_usb_k65_descriptor_batch",
                    "_rpi5_usb_xhci_enable_slot_plan",
                    "_rpi5_usb_xhci_address_k65_plan",
                    "_rpi5_usb_xhci_configure_k65_keyboard",
                    "_rpi5_usb_k65_hid_boot_setup",
                    "_rpi5_usb_k65_hid_boot_setup_idle",
                    "_rpi5_usb_xhci_k65_interrupt_plan",
                    "_rpi5_usb_xhci_k65_stream_plan"):
                self.assertIn(symbol, undefined)
                self.assertRegex(defined, r"\b" + re.escape(symbol) + r"\b")


if __name__ == "__main__":
    unittest.main()
