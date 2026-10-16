# SPDX-License-Identifier: BSD-2-Clause
import ctypes as C
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/rpi5"))
from boot_args import encode_with_physical_tree


class Input(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in ("virt_base", "phys_base", "mem_size", "top", "tree_pa", "kernel_end", "mem_actual")] + [("tree_length", C.c_uint32)]


class NativeBootArgsTests(unittest.TestCase):
    def test_host_equivalence_and_rejections(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)/"args.dylib"
            subprocess.run(["xcrun", "clang", "-dynamiclib", "-Wall", "-Wextra", "-Werror",
                            str(ROOT/"loader/rpi5/boot_args.c"), "-o", str(library)], check=True)
            encode = C.CDLL(str(library)).rpi5_boot_args_encode
            encode.argtypes = [C.POINTER(Input), C.c_char_p, C.c_size_t, C.c_void_p, C.c_size_t]
            encode.restype = C.c_int
            args = Input(0xfffffe0006000000,0x2000000,0x26000000,0x5004000,0x5000000,0x4800000,0x40000000,128)
            for command in (b"", b"rd=md0 -v", b"x"*1023):
                output = C.create_string_buffer(1152)
                self.assertEqual(encode(C.byref(args),command,len(command),output,1152),0)
                expected = encode_with_physical_tree(virt_base=args.virt_base, phys_base=args.phys_base,
                    mem_size=args.mem_size, top_of_kernel_data=args.top, device_tree_pa=args.tree_pa,
                    kernel_end_pa=args.kernel_end, mem_size_actual=args.mem_actual,
                    device_tree_length=args.tree_length, command_line=command.decode())
                self.assertEqual(output.raw,expected)
            for command in (b"x"*1024,b"a\0b",b"\xff"):
                output = C.create_string_buffer(b"\xa5"*1152,1152)
                self.assertEqual(encode(C.byref(args),command,len(command),output,1152),-1)
                self.assertEqual(output.raw,b"\xa5"*1152)
            for field, value in (("tree_pa",0x4700000),("top",0x5000001),("tree_length",0),("mem_size",2**64-1)):
                bad = Input.from_buffer_copy(args)
                setattr(bad,field,value)
                self.assertEqual(encode(C.byref(bad),b"",0,output,1152),-1)
                self.assertEqual(output.raw,b"\xa5"*1152)
