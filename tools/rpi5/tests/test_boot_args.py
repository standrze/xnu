# SPDX-License-Identifier: BSD-2-Clause
import importlib.util
from pathlib import Path
import platform
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[3]
spec = importlib.util.spec_from_file_location("boot_args", ROOT / "tools/rpi5/boot_args.py")
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)


def arguments():
    return dict(virt_base=0xfffffe0006000000, phys_base=0, mem_size=1 << 30,
                top_of_kernel_data=0x3000000, device_tree_pointer=0x2800000,
                device_tree_length=4096, command_line="-v", mem_size_actual=1 << 30)


class BootArgsTests(unittest.TestCase):
    def test_physical_tree_becomes_initial_kernel_virtual_pointer(self):
        args = arguments()
        del args["device_tree_pointer"]
        data = abi.encode_with_physical_tree(device_tree_pa=0x2800000,
                                             kernel_end_pa=0x2000000, **args)
        self.assertEqual(struct.unpack_from("<Q", data, 96)[0],
                         args["virt_base"] + 0x2800000)
        for pa, end in [(0x1000000, 0x2000000), (0x3000000, 0x2000000),
                        (0x2800001, 0x2000000), (1 << 40, 0x2000000)]:
            with self.subTest(pa=pa), self.assertRaises(ValueError):
                abi.encode_with_physical_tree(device_tree_pa=pa, kernel_end_pa=end, **args)

    @unittest.skipUnless(platform.system() == "Darwin", "requires native LP64 compiler")
    def test_layout_against_pinned_c_declarations(self):
        header = (ROOT / "pexpert/pexpert/arm64/boot.h").read_text()
        # Exact upstream declarations, without unrelated kernel include graph.
        declarations = header[header.index("struct Boot_Video {"):header.index("#define SOC_DEVICE_TYPE_BUFFER_SIZE")]
        source = "#include <stddef.h>\n#include <stdint.h>\n#define BOOT_LINE_LENGTH 1024\n" + declarations
        source += f'\n_Static_assert(sizeof(boot_args) == {abi.SIZE}, "size");\n'
        for field, offset in abi.OFFSETS.items():
            source += f'_Static_assert(offsetof(boot_args, {field}) == {offset}, "{field}");\n'
        source += "int main(void) { return 0; }\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "abi.c"
            path.write_text(source)
            result = subprocess.run(["xcrun", "clang", "-arch", "arm64", "-fsyntax-only", str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_representation(self):
        data = abi.encode(**arguments())
        self.assertEqual(len(data), abi.SIZE)
        self.assertEqual(struct.unpack_from("<HH", data), (2, 2))
        self.assertEqual(data[108:111], b"-v\0")
        self.assertEqual(data[40:96], bytes(56))
        self.assertEqual(struct.unpack_from("<Q", data, 96)[0], 0x2800000)
        self.assertEqual(data[1132:1144], bytes(12))

    def test_rejects_truncation_and_invalid_values(self):
        for changes in [dict(command_line="x" * 1024), dict(command_line="x\0y"),
                        dict(mem_size=1 << 64), dict(phys_base=-1),
                        dict(device_tree_length=1 << 32), dict(device_tree_pointer=0)]:
            args = arguments()
            args.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                abi.encode(**args)
