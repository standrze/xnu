# SPDX-License-Identifier: BSD-2-Clause
"""Software-only tests for the future Apple Ethernet family boundary."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "iokit/Kernel/rpi5_gem_network_adapter.c"
HOST = ROOT / "tools/rpi5/tests/gem_network_adapter_host.c"
MANIFEST = ROOT / "tools/rpi5/ionetworkingfamily_186_sources.json"


class GEMNetworkAdapterTests(unittest.TestCase):
    def test_native_ownership_gate_and_faults(self):
        with tempfile.TemporaryDirectory(prefix="gem-network-adapter-") as d:
            exe = Path(d) / "adapter"
            subprocess.run(
                [
                    "xcrun", "clang", "-std=c11", "-O1", "-g", "-Wall",
                    "-Wextra", "-Werror", "-fsanitize=address,undefined",
                    "-I" + str(ROOT / "iokit/Kernel"), str(CORE), str(HOST),
                    "-o", str(exe),
                ],
                check=True, timeout=60,
            )
            result = subprocess.run([exe], text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("DEFAULT_OFF OWNERSHIP_EXACT NO_HARDWARE", result.stdout)

    def test_a76_freestanding_object_has_only_callback_indirection(self):
        with tempfile.TemporaryDirectory(prefix="gem-network-a76-") as d:
            obj = Path(d) / "adapter.o"
            subprocess.run(
                [
                    "xcrun", "clang", "--target=aarch64-none-elf",
                    "-mcpu=cortex-a76", "-mstrict-align", "-mgeneral-regs-only",
                    "-ffreestanding", "-fno-builtin", "-fno-stack-protector",
                    "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I" + str(ROOT / "iokit/Kernel"), "-c", str(CORE),
                    "-o", str(obj),
                ],
                check=True, timeout=60,
            )
            undefined = subprocess.check_output(
                ["xcrun", "llvm-nm", "--undefined-only", obj], text=True
            )
            self.assertEqual(undefined.strip(), "")

    def test_installed_apple_kernel_headers_match_boundary(self):
        sdk = subprocess.check_output(["xcrun", "--show-sdk-path"], text=True).strip()
        headers = Path(sdk) / (
            "System/Library/Frameworks/Kernel.framework/Headers"
        )
        source = ROOT / "tools/rpi5/tests/gem_ionetwork_api_compile.cpp"
        subprocess.run(
            [
                "xcrun", "clang++", "-std=c++17", "-fsyntax-only",
                "-Werror", "-Wno-deprecated-declarations", "-DKERNEL",
                "-isysroot", sdk,
                "-I" + str(headers), str(source),
            ],
            check=True, timeout=60,
        )

    def test_apple_api_pin_and_no_activation_wiring(self):
        data = json.loads(MANIFEST.read_text())
        self.assertEqual(data["release"], "IONetworkingFamily-186")
        self.assertEqual(data["catalog_xnu_tag"], "xnu-12377.1.9")
        self.assertEqual(data["workspace_xnu_tag"], "xnu-12377.121.6")
        self.assertFalse(data["whole_family_compatibility_proven"])
        self.assertEqual(data["bsd_name_prefix"], "en")
        self.assertEqual(data["ethernet_mtu"], 1500)
        self.assertEqual(data["max_packet_including_fcs"], 1518)
        self.assertEqual(data["output_return_codes"], {
            "accepted": 0, "dropped": 1, "retry_stall": 258
        })
        for source in data["sources"]:
            self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(source["url"].startswith(
                "https://github.com/apple-oss-distributions/IONetworkingFamily/"
            ))
        # No production source includes this boundary yet.  Activation must be
        # an explicit later composition step after hardware acceptance.
        users = []
        for top in ("bsd", "iokit", "libkern", "osfmk", "pexpert", "security"):
            for path in (ROOT / top).rglob("*"):
                if not path.is_file():
                    continue
                if path in (CORE, ROOT / "iokit/Kernel/rpi5_gem_network_adapter.h"):
                    continue
                if path.suffix not in (".c", ".cpp", ".h", ".inc"):
                    continue
                try:
                    if "rpi5_gem_network_adapter.h" in path.read_text(errors="ignore"):
                        users.append(str(path.relative_to(ROOT)))
                except OSError:
                    pass
        self.assertEqual(users, [])


if __name__ == "__main__":
    unittest.main()
