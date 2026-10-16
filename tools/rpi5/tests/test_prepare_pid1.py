# SPDX-License-Identifier: BSD-2-Clause
"""Strict RAM-backed PID 1 package contract tests."""

import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

module_path = Path(__file__).parents[1] / "prepare_pid1.py"
spec = importlib.util.spec_from_file_location("prepare_pid1", module_path)
pid1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pid1)


def fixture():
    data = bytearray(512)
    struct.pack_into("<8I", data, 0, 0xFEEDFACF, 0x0100000C, 0, 2, 2, 360, 0, 0)
    struct.pack_into("<2I16s4Q4I", data, 32, 0x19, 72, b"__TEXT", 0x100000000,
                     0x4000, 0, 512, 5, 5, 0, 0)
    struct.pack_into("<4I", data, 104, 5, 288, 6, 68)
    struct.pack_into("<Q", data, 104 + 16 + 256, 0x100000190)
    return data


def process_literal_fixture():
    data = fixture() + bytearray(1536)
    struct.pack_into("<II", data, 16, 3, 384)
    struct.pack_into("<Q", data, 32 + 48, len(data))
    struct.pack_into("<6I", data, 392, 2, 24, 512, 6, 640, 256)
    strx = 1
    for index, (name, literal) in enumerate(pid1.PROCESS_LITERALS.items()):
        encoded = name.encode() + b"\0"
        data[640 + strx:640 + strx + len(encoded)] = encoded
        fileoff = 1024 + index * 64
        struct.pack_into("<IBBHQ", data, 512 + 16 * index,
                         strx, 0xE, 1, 0, 0x100000000 + fileoff)
        data[fileoff:fileoff + len(literal) + 1] = literal + b"\0"
        strx += len(encoded)
    return data


class PreparePid1Tests(unittest.TestCase):
    def test_linked_process_literal_addresses(self):
        result = pid1.inspect_process_literals(process_literal_fixture())
        self.assertEqual(result["_process_cmd"]["value"], "process")
        self.assertEqual(result["_process_cmd"]["address"], 0x100000400)
        self.assertEqual(result["_crlf"]["value"], "\r\n")

    def test_rejects_literal_coalescing_even_when_word_is_present(self):
        data = process_literal_fixture()
        data[1024:1035] = b"\n\r\nprocess\0"
        self.assertIn(b"process\0", data)
        with self.assertRaisesRegex(ValueError, "linked literal _process_cmd"):
            pid1.inspect_process_literals(data)

    @unittest.skipUnless(shutil.which("xcrun"), "requires the macOS Xcode toolchain")
    def test_opt_in_terminal_build_is_static_and_separate(self):
        source = Path(__file__).parents[1] / "pid1_terminal.S"
        build_script = Path(__file__).parents[1] / "build_pid1.py"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            subprocess.run([sys.executable, str(build_script), "--source", str(source),
                            "--output-dir", str(output)], check=True, capture_output=True)
            result = pid1.inspect((output / "pid1").read_bytes())
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(result["ramdisk_size"], len((output / "ramdisk.bin").read_bytes()))
            self.assertEqual(manifest["source"], str(source))
            self.assertIn(b"xnu-rpi5> ", (output / "pid1").read_bytes())

    def test_raw_entry_aligns_sp_before_syscalls(self):
        source = (Path(__file__).parents[1] / "pid1.S").read_text()
        entry = source.split("_start:", 1)[1].split("_timer_loop:", 1)[0]
        self.assertLess(entry.index("mov x9, sp"), entry.index("and x9, x9, #~15"))
        self.assertLess(entry.index("and x9, x9, #~15"), entry.index("mov sp, x9"))
        self.assertLess(entry.index("mov sp, x9"), entry.index("svc #0x80"))

    def test_cli_creates_raw_image_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "pid1"
            output = Path(directory) / "ramdisk.bin"
            manifest = Path(directory) / "manifest.json"
            source.write_bytes(fixture())
            subprocess.run([sys.executable, str(module_path), str(source), str(output),
                            "--manifest", str(manifest)], check=True, capture_output=True)
            self.assertEqual(output.read_bytes(), bytes(fixture()) + bytes(16384 - 512))
            self.assertEqual(json.loads(manifest.read_text())["ramdisk_size"], 16384)

    def test_static_executable_and_padding(self):
        raw = bytes(fixture())
        result = pid1.inspect(raw)
        self.assertEqual(result["entry_pc"], 0x100000190)
        self.assertEqual(result["ramdisk_size"], 16384)
        image = raw + bytes(result["ramdisk_size"] - len(raw))
        self.assertEqual(len(image), 16384)
        self.assertEqual(image[512:], bytes(16384 - 512))

    def test_rejects_wrong_architecture_and_type(self):
        for off, value in [(4, 0x1000007), (8, 2), (12, 6), (24, 4), (28, 1)]:
            data = fixture()
            struct.pack_into("<I", data, off, value)
            with self.subTest(offset=off), self.assertRaises(ValueError):
                pid1.inspect(data)

    def test_rejects_dynamic_and_signature_commands(self):
        for cmd in (0xE, 0xC, 0x80000018, 0x1D, 0x2C, 0x80000028, 0x80000034):
            data = fixture()
            struct.pack_into("<I", data, 104, cmd)
            with self.subTest(command=cmd), self.assertRaisesRegex(ValueError, "dynamic"):
                pid1.inspect(data)

    def test_rejects_bad_thread_state_and_entry(self):
        for off, value in [(104 + 8, 1), (104 + 12, 67)]:
            data = fixture()
            struct.pack_into("<I", data, off, value)
            with self.subTest(offset=off), self.assertRaises(ValueError):
                pid1.inspect(data)
        data = fixture()
        struct.pack_into("<Q", data, 104 + 16 + 256, 0)
        with self.assertRaisesRegex(ValueError, "entry PC"):
            pid1.inspect(data)

    def test_rejects_undefined_symbols(self):
        data = fixture()
        struct.pack_into("<I", data, 16, 3)
        struct.pack_into("<I", data, 20, 384)
        struct.pack_into("<6I", data, 392, 2, 24, 448, 1, 464, 8)
        struct.pack_into("<IBBHQ", data, 448, 1, 1, 0, 0, 0)
        data[464:470] = b"\0_foo\0"
        with self.assertRaisesRegex(ValueError, "undefined"):
            pid1.inspect(data)

    def test_rejects_truncation_and_bad_segments(self):
        for length in (0, 31, 32, 100, 391):
            with self.subTest(length=length), self.assertRaises(ValueError):
                pid1.inspect(bytes(fixture()[:length]))
        data = fixture()
        struct.pack_into("<Q", data, 32 + 8 + 16 + 8 * 3, 513)
        with self.assertRaises(ValueError):
            pid1.inspect(data)


if __name__ == "__main__":
    unittest.main()
