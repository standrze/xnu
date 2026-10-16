# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/rpi5'))
from capture_linux_tree import encode


class TimerBindingTests(unittest.TestCase):
    def test_four_and_five_tuple_profiles(self):
        def node(name,props,children=()):
            return dict(name=name,properties={k:v.hex() for k,v in props.items()},children=list(children))
        def blob(rows):
            gic=node('interrupt-controller@7fff9000',{
                '#interrupt-cells':struct.pack('>I',3),
                'interrupt-controller':b'', 'phandle':struct.pack('>I',1)})
            timer=node('timer',{'compatible':b'arm,armv8-timer\0',
                                'interrupts':b''.join(struct.pack('>III',*r) for r in rows)})
            return encode(node('',{'interrupt-parent':struct.pack('>I',1)},[
                node('soc@107c000000',{},[gic]),timer]))
        rows=[(1,p,0xf08) for p in (13,14,11,10,12)]
        cases=[(rows[:4],0),(rows,0),(rows[:3],-1),(rows+rows[-1:],-1)]
        for index in range(5):
            for field in range(3):
                bad=[list(r) for r in rows]; bad[index][field]^=1
                cases.append((bad,-1))
        source='#include "fdt.h"\n#include <assert.h>\nint main(void) {\n'
        for i,(case,expected) in enumerate(cases):
            data=blob(case)
            source+='unsigned char b%d[]={%s};\n'%(i,','.join(map(str,data)))
            source+=f'assert(rpi5_fdt_probe_timer(b{i},sizeof b{i})=={expected});\n'
        source+='return 0;}\n'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory); (path/'test.c').write_text(source)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                            '-I'+str(ROOT/'loader/rpi5'),str(path/'test.c'),
                            str(ROOT/'loader/rpi5/fdt.c'),str(ROOT/'loader/rpi5/fdt_reg.c'),
                            '-o',str(path/'test')],check=True)
            subprocess.run([str(path/'test')],check=True)
