# SPDX-License-Identifier: BSD-2-Clause
import sys
from pathlib import Path
import struct
import unittest
import platform
import subprocess
import tempfile
from test_kernel_contracts import function_text

sys.path.insert(0, str(Path(__file__).parents[1]))
from apple_dt import encode


def node(name="device-tree", properties=None, children=None):
    return {"name": name, "properties": properties or {}, "children": children or []}


class AppleDTTests(unittest.TestCase):
    @unittest.skipUnless(platform.system() == "Darwin", "requires native compiler")
    def test_xnu_property_lookup_reads_encoded_payloads(self):
        root = Path(__file__).parents[3]
        header = (root / "pexpert/pexpert/device_tree.h").read_text()
        declarations = header[header.index("#define kPropNameLength"):header.index("typedef struct DTSavedScope")]
        functions = function_text("pexpert/gen/device_tree.c", "next_prop_region", "static DeviceTreeNodeProperty const *")
        functions += "\n" + function_text("pexpert/gen/device_tree.c", "SecureDTGetPropertyInternal", "static int")
        blob = encode(node(properties={"odd": b"abc", "wide": struct.pack("<Q", 0x123456789abcdef0)}))
        source = r'''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <assert.h>
typedef uintptr_t vm_offset_t;
typedef size_t vm_size_t;
#define kSuccess 0
#define kError -1
#define panic(...) __builtin_trap()
#define ASSERT_HEADER_IN_DT_REGION(start,end,p,size) assert((uintptr_t)(p) >= (start) && (uintptr_t)(p) <= (end) && (size) <= (end)-(uintptr_t)(p))
#define os_add3_overflow(a,b,c,out) (__builtin_add_overflow((uintptr_t)(a),(uintptr_t)(b),(out)) || __builtin_add_overflow(*(out),(uintptr_t)(c),(out)))
''' + declarations + r'''
typedef RealDTEntry DTEntry;
static void assert_prop_in_dt_region(uintptr_t start, uintptr_t end, const DeviceTreeNodeProperty *p) {
    ASSERT_HEADER_IN_DT_REGION(start,end,p,sizeof(*p));
    assert(p->length <= end - (uintptr_t)(p+1));
}
''' + functions + "\nstatic const unsigned char blob[] __attribute__((aligned(4))) = {" + ",".join(map(str, blob)) + r'''};
int main(void) {
    const void *value = NULL; unsigned int size = 0;
    DTEntry entry = (DTEntry)blob;
    assert(SecureDTGetPropertyInternal(entry,"odd",&value,&size,(uintptr_t)blob,sizeof(blob)) == kSuccess);
    assert(size == 3 && memcmp(value,"abc",3) == 0);
    assert(SecureDTGetPropertyInternal(entry,"wide",&value,&size,(uintptr_t)blob,sizeof(blob)) == kSuccess);
    uint64_t wide; memcpy(&wide,value,8);
    assert(size == 8 && wide == UINT64_C(0x123456789abcdef0));
    assert(SecureDTGetPropertyInternal(entry,"missing",&value,&size,(uintptr_t)blob,sizeof(blob)) == kError);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "probe.c"
            path.write_text(source)
            executable = Path(directory) / "probe"
            result = subprocess.run(["xcrun", "clang", str(path), "-o", str(executable)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(executable)], check=True)

    def test_wire_layout_and_padding(self):
        data = encode(node(properties={"test": b"abc"}, children=[node("chosen")]))
        self.assertEqual(struct.unpack_from("<II", data), (2, 1))
        self.assertEqual(data[8:40], b"name" + bytes(28))
        self.assertEqual(struct.unpack_from("<I", data, 40)[0], 12)
        self.assertEqual(data[44:56], b"device-tree\0")
        self.assertEqual(data[56:88], b"test" + bytes(28))
        self.assertEqual(data[88:96], b"\x03\0\0\0abc\0")
        self.assertEqual(struct.unpack_from("<II", data, 96), (1, 0))
        self.assertEqual(data[-8:], b"chosen\0\0")

    def test_rejects_ambiguous_or_invalid_input(self):
        bad = [node(properties={"x": 1}), node(properties={"name": b"other"}),
               node("a/b"), node("x" * 64), node(properties={"x" * 32: b""}),
               node(children=[node("same"), node("same")])]
        cycle = node()
        cycle["children"].append(cycle)
        bad.append(cycle)
        for value in bad:
            with self.subTest(value=str(value)[:80]), self.assertRaises(ValueError):
                encode(value)
        with self.assertRaisesRegex(ValueError, "size limit"):
            encode(node(), max_bytes=8)
