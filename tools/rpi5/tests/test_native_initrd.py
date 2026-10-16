# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


def blob(properties):
    names = bytearray()
    data = bytearray(struct.pack(">I", 1) + bytes(4))
    data += struct.pack(">I", 1) + b"chosen\0\0"
    for name, value in properties:
        offset = len(names)
        names += name.encode() + b"\0"
        data += struct.pack(">III", 3, len(value), offset) + value + bytes(-len(value) % 4)
    data += struct.pack(">III", 2, 2, 9)
    return struct.pack(">10I", 0xd00dfeed, 56+len(data)+len(names), 56,
                       56+len(data), 40, 17, 16, 0, len(names), len(data)) + bytes(16) + data + names


class InitrdTests(unittest.TestCase):
    def test_bounded_pair_and_atomic_failure(self):
        start, end = "linux,initrd-start", "linux,initrd-end"
        def pair(a, b, width=8):
            return [(start, a.to_bytes(width, "big")), (end, b.to_bytes(width, "big"))]
        cases = [(pair(0x90000, 0xa0000, w), 0) for w in (4, 8)]
        cases += [([], 1), (pair(0x90000, 0xa0000)[:1], -1),
                  (pair(0x90000, 0xa0000)[1:], -1),
                  (pair(0xa0000, 0x90000), -1), (pair(7, 7), -1),
                  (pair(0x90000, (1 << 40)+1), -1),
                  ([(start, b"123"), (end, b"456")], -1),
                  ([(start, bytes(4)), (end, (10).to_bytes(8, "big"))], -1),
                  (pair(0x90000, 0xa0000) + pair(0x90000, 0xa0000)[:1], -1)]
        source = '#include "fdt.h"\n#include <assert.h>\n#include <string.h>\nint main(void) {\n'
        source += 'struct rpi5_range out, prior={123,456};\n'
        for i, (properties, expected) in enumerate(cases):
            source += 'const unsigned char b%d[]={%s}; out=prior;\n' % (i, ','.join(map(str, blob(properties))))
            source += f'assert(rpi5_fdt_initrd(b{i},sizeof b{i},&out)=={expected});\n'
            source += ('assert(out.start==0x90000 && out.end==0xa0000);\n' if expected == 0
                       else 'assert(!memcmp(&out,&prior,sizeof out));\n')
        source += 'return 0;}\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.c').write_text(source)
            subprocess.run(['xcrun', 'clang', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-I'+str(ROOT/'loader/rpi5'),
                            str(path/'test.c'), str(ROOT/'loader/rpi5/fdt.c'),
                            '-o', str(path/'test')], check=True)
            subprocess.run([str(path/'test')], check=True)
