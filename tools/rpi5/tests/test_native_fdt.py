# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest
import struct

ROOT = Path(__file__).resolve().parents[3]


class NativeFDTTests(unittest.TestCase):
    def test_compatible_inventory(self):
        harness='#include "fdt.h"\n#include <assert.h>\nint main(void) { uint32_t count;\n'
        cases=[(b'simple-framebuffer\0',0,1),(b'other\0simple-framebuffer\0',0,1),
               (b'other\0',0,0),(b'simple-framebuffer',-1,99),(b'',-1,99)]
        for i,(value,status,count) in enumerate(cases):
            body=struct.pack('>II',1,0)+struct.pack('>III',3,len(value),0)+value+bytes(-len(value)%4)+struct.pack('>II',2,9)
            names=b'compatible\0'
            blob=struct.pack('>10I',0xd00dfeed,56+len(body)+len(names),56,56+len(body),40,17,16,0,len(names),len(body))+bytes(16)+body+names
            harness+='const unsigned char b%d[]={%s};\n'%(i,','.join(map(str,blob)))
            harness+=f'count=99; assert(rpi5_fdt_compatible_count(b{i},sizeof b{i},"simple-framebuffer",&count)=={status}); assert(count=={count});\n'
        harness+='}\n'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(harness)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                '-I'+str(ROOT/'loader/rpi5'),str(p/'test.c'),str(ROOT/'loader/rpi5/fdt.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)

    def test_mmu_off_be64_uses_byte_loads(self):
        # Host execution accepts unaligned Normal-memory loads and therefore
        # cannot catch the board's MMU-off alignment fault. Inspect target code.
        import re
        self.assertIn('"-mstrict-align"', (ROOT/'tools/rpi5/build_probe.py').read_text())
        with tempfile.TemporaryDirectory() as d:
            obj=Path(d)/'fdt.o'
            subprocess.run(['xcrun','clang','--target=aarch64-none-elf',
                '-mcpu=cortex-a76','-mstrict-align','-mgeneral-regs-only',
                '-ffreestanding','-fno-stack-protector','-O2','-Wall','-Wextra','-Werror',
                '-c',str(ROOT/'loader/rpi5/fdt.c'),'-o',str(obj)],check=True)
            assembly=subprocess.check_output(['xcrun','llvm-objdump','-d',
                '--disassemble-symbols=be64',str(obj)],text=True)
            self.assertIn('<be64>:',assembly)
            self.assertEqual(len(re.findall(r'\bldrb\s',assembly)),8)
            self.assertNotRegex(assembly,r'\b(?:ldr|ldur|ldp|ldrh)\s')

    def test_firmware_nonzero_property_padding(self):
        import sys
        sys.path.insert(0,str(ROOT/'tools/rpi5'))
        from fdt import parse
        harness='#include "fdt.h"\n#include <assert.h>\nint main(void) { struct rpi5_fdt_property p;\n'
        for n in (1,2,3):
            value=b'x'*n
            body=struct.pack('>II',1,0)+struct.pack('>III',3,n,0)+value+b'\xa5'*(4-n)+struct.pack('>II',2,9)
            data=struct.pack('>10I',0xd00dfeed,56+len(body)+2,56,56+len(body),40,17,16,0,2,len(body))+bytes(16)+body+b'p\0'
            self.assertEqual(parse(data)['root']['properties']['p'],value)
            harness+='const unsigned char b%d[]={%s};\n'%(n,','.join(map(str,data)))
            harness+=f'assert(!rpi5_fdt_structure(b{n},sizeof b{n})); assert(!rpi5_fdt_property(b{n},sizeof b{n},"/","p",&p)); assert(p.length=={n});\n'
            harness+=f'for(unsigned i=0;i<sizeof b{n};i++) assert(rpi5_fdt_structure(b{n},i)==-1);\n'
        harness+='}\n'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'test.c').write_text(harness)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                '-I'+str(ROOT/'loader/rpi5'),str(p/'test.c'),str(ROOT/'loader/rpi5/fdt.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)

    def test_exact_property_lookup(self):
        def blob(duplicate_node=False, duplicate_property=False):
            begin=lambda n: struct.pack(">I",1)+(n.encode()+b"\0").ljust((len(n)+4)//4*4,b"\0")
            prop=struct.pack(">III",3,4,0)+b"abcd"
            child=begin("uart@10")+prop+(prop if duplicate_property else b"")+struct.pack(">I",2)
            data=begin("")+begin("soc")+child+(child if duplicate_node else b"")+struct.pack(">III",2,2,9)
            strings=b"reg\0"
            return struct.pack(">10I",0xd00dfeed,56+len(data)+len(strings),56,56+len(data),40,17,16,0,len(strings),len(data))+bytes(16)+data+strings
        harness='#include "fdt.h"\n#include <assert.h>\n#include <string.h>\nint main(void) { struct rpi5_fdt_property out, prior={123,456,789};\n'
        for i,data in enumerate((blob(),blob(True),blob(False,True))):
            harness+='const unsigned char b%d[]={%s}; out=prior;\n'%(i,','.join(map(str,data)))
            if i:
                harness+=f'assert(rpi5_fdt_property(b{i},sizeof b{i},"/soc/uart@10","reg",&out)==-1 && !memcmp(&out,&prior,sizeof out));\n'
            else:
                harness+='assert(!rpi5_fdt_property(b0,sizeof b0,"/soc/uart@10","reg",&out)); assert(out.length==4 && !memcmp(b0+out.offset,"abcd",4));\n'
                harness+='out=prior; assert(rpi5_fdt_property(b0,sizeof b0,"/soc/uart@10","missing",&out)==-2 && !memcmp(&out,&prior,sizeof out));\n'
                harness+='assert(rpi5_fdt_property(b0,sizeof b0,"/soc/uart@10/","reg",&out)==-1);\n'
                harness+='assert(rpi5_fdt_property(b0,sizeof b0,"/other/uart@10","reg",&out)==-2);\n'
        harness+='return 0;}\n'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory); (path/"test.c").write_text(harness)
            subprocess.run(["xcrun","clang","-Wall","-Wextra","-Werror","-fsanitize=address,undefined","-I"+str(ROOT/"loader/rpi5"),str(path/"test.c"),str(ROOT/"loader/rpi5/fdt.c"),"-o",str(path/"test")],check=True)
            subprocess.run([str(path/"test")],check=True)

    def test_dynamic_reservation_decode(self):
        def blob(size, alignment=16384, fixed=False):
            names=bytearray()
            def prop(name,value):
                off=len(names); names.extend(name.encode()+b"\0")
                return struct.pack(">III",3,len(value),off)+value+bytes(-len(value)%4)
            def begin(name):
                value=struct.pack(">I",1)+name.encode()+b"\0"
                return value+bytes(-len(value)%4)
            cells=lambda: prop("#address-cells",struct.pack(">I",2))+prop("#size-cells",struct.pack(">I",2))
            data=begin("")+cells()+begin("reserved-memory")+cells()+prop("ranges",b"")+begin("pool")
            data+=prop("size",size)+prop("alignment",struct.pack(">Q",alignment))+prop("alloc-ranges",struct.pack(">QQ",0,1<<30))
            if fixed: data+=prop("reg",struct.pack(">QQ",0x80000,0x4000))
            data+=struct.pack(">IIII",2,2,2,9)
            return struct.pack(">10I",0xd00dfeed,56+len(data)+len(names),56,56+len(data),40,17,16,0,len(names),len(data))+bytes(16)+data+names
        cases=[(blob(struct.pack(">Q",1<<26)),0), (blob(struct.pack(">I",1<<26)),-1),
               (blob(struct.pack(">Q",1<<26),3),-1), (blob(b"ignored",fixed=True),1)]
        harness='#include "fdt.h"\n#include <assert.h>\n#include <string.h>\nint main(void) { struct rpi5_reservation_plan out, prior; memset(&prior,0xa5,sizeof prior);\n'
        for i,(data,expected) in enumerate(cases):
            harness+='const unsigned char b%d[]={%s}; out=prior;\n'%(i,','.join(map(str,data)))
            if expected==-1:
                harness+=f'assert(rpi5_fdt_reservation_plan(b{i},sizeof b{i},&out)==-1); assert(!memcmp(&out,&prior,sizeof out));\n'
            else:
                harness+=f'assert(!rpi5_fdt_reservation_plan(b{i},sizeof b{i},&out));\n'
                if expected==0:
                    harness+='assert(out.count==1 && !out.fixed.count && out.request[0].size==(1u<<26) && out.request[0].alignment==16384 && out.request[0].window_count==1 && out.request[0].window[0].end==(1u<<30));\n'
                else:
                    harness+='assert(!out.count && out.fixed.count==1 && out.fixed.extent[0].start==0x80000 && out.fixed.extent[0].end==0x84000);\n'
        harness+='return 0;}\n'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory); (path/"test.c").write_text(harness)
            subprocess.run(["xcrun","clang","-Wall","-Wextra","-Werror","-fsanitize=address,undefined","-I"+str(ROOT/"loader/rpi5"),str(path/"test.c"),str(ROOT/"loader/rpi5/fdt.c"),"-o",str(path/"test")],check=True)
            subprocess.run([str(path/"test")],check=True)

    def test_memory_ranges(self):
        def blob(ranges, cells=2, status=None, duplicate=False):
            strings = bytearray()
            def prop(name, value):
                offset = len(strings); strings.extend(name.encode() + b"\0")
                return struct.pack(">III", 3, len(value), offset) + value + bytes(-len(value) % 4)
            data = struct.pack(">I", 1) + bytes(4)
            data += prop("#address-cells", struct.pack(">I", cells)) + prop("#size-cells", struct.pack(">I", cells))
            data += struct.pack(">I", 1) + b"memory@0\0" + bytes(3)
            data += prop("device_type", b"memory\0")
            raw = b"".join(a.to_bytes(cells * 4, "big") + n.to_bytes(cells * 4, "big") for a, n in ranges)
            data += prop("reg", raw)
            if duplicate: data += prop("reg", raw)
            if status is not None: data += prop("status", status)
            data += struct.pack(">III", 2, 2, 9)
            return struct.pack(">10I", 0xd00dfeed, 56 + len(data) + len(strings), 56,
                               56 + len(data), 40, 17, 16, 0, len(strings), len(data)) + bytes(16) + data + strings
        cases = [
            (blob([(0, 4096)], 1), [(0, 4096)]),
            (blob([(1 << 32, 4096), (0, 8192)]), [(0, 8192), (1 << 32, (1 << 32) + 4096)]),
            (blob([(0, 4096), (4096, 4096)]), [(0, 4096), (4096, 8192)]),
            (blob([((1 << 40) - 4096, 4096)]), [((1 << 40) - 4096, 1 << 40)]),
            (blob([(0, 0)]), None),
            (blob([(1 << 40, 1)]), None),
            (blob([((1 << 40) - 1, 2)]), None),
            (blob([(0, (1 << 64) - 1)]), None),
            (blob([(0, 8192), (4096, 8192)]), None),
            (blob([(0, 4096), (0, 4096)]), None),
            (blob([(0, 4096)], duplicate=True), None),
            (blob([(0, 4096)], status=b"disabled\0"), None),
            (blob([(0, 4096)], status=b"fail\0"), None),
            (blob([(i * 8192, 4096) for i in range(8)]), [(i * 8192, i * 8192 + 4096) for i in range(8)]),
            (blob([(i * 8192, 4096) for i in range(9)]), None),
        ]
        harness = '#include "fdt.h"\n#include <assert.h>\n#include <string.h>\nint main(void) {\n'
        harness += 'struct rpi5_fdt_memory out, prior; memset(&prior,0xa5,sizeof prior);\n'
        for i, (data, expected) in enumerate(cases):
            harness += 'const unsigned char b%d[] = {%s}; out=prior;\n' % (i, ','.join(map(str, data)))
            if expected is None:
                harness += f'assert(rpi5_fdt_memory(b{i},sizeof b{i},&out)==-1); assert(!memcmp(&out,&prior,sizeof out));\n'
            else:
                harness += f'assert(!rpi5_fdt_memory(b{i},sizeof b{i},&out)); assert(out.count=={len(expected)});\n'
                for n, (start, end) in enumerate(expected):
                    harness += f'assert(out.start[{n}]=={start}ull && out.end[{n}]=={end}ull);\n'
        harness += 'return 0; }\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.c").write_text(harness)
            subprocess.run(["xcrun", "clang", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-I" + str(ROOT / "loader/rpi5"), str(path / "test.c"), str(ROOT / "loader/rpi5/fdt.c"), "-o", str(path / "test")], check=True)
            subprocess.run([str(path / "test")], check=True)

    def test_cpu_binding_cases(self):
        def cpu(name, affinity, cells=1, status=None, extra=()):
            props = [("device_type", b"cpu\0"), ("compatible", b"arm,cortex-a76\0"),
                     ("reg", affinity.to_bytes(cells * 4, "big")), ("enable-method", b"psci\0")]
            if status is not None:
                props.append(("status", status))
            return (name, props + list(extra), [])

        def blob(cpus, cells=1, extra=()):
            names = bytearray()
            def emit(node):
                name, props, children = node
                body = struct.pack(">I", 1) + name.encode() + b"\0"
                body += bytes(-len(body) % 4)
                for key, value in props:
                    offset = len(names)
                    names.extend(key.encode() + b"\0")
                    body += struct.pack(">III", 3, len(value), offset) + value
                    body += bytes(-len(body) % 4)
                for child in children:
                    body += emit(child)
                return body + struct.pack(">I", 2)
            container = ("cpus", [("#address-cells", struct.pack(">I", cells)),
                                  ("#size-cells", bytes(4))] + list(extra), cpus)
            data = emit(("", [], [container])) + struct.pack(">I", 9)
            return struct.pack(">10I", 0xd00dfeed, 56 + len(data) + len(names), 56,
                               56 + len(data), 40, 17, 16, 0, len(names), len(data)) + bytes(16) + data + names

        cases = [
            (blob([cpu("cpu@0", 0), cpu("cpu@1", 256)]), [0, 256], 3),
            (blob([cpu("cpu@0", 0, 2), cpu("cpu@1", 256, 2)], 2), [0, 256], 3),
            (blob([cpu("cpu@0", 0), cpu("cpu@1", 256, status=b"disabled\0")]), [0, 256], 1),
            (blob([cpu("cpu@0", 0, status=b"disabled\0")]), None, 0),
            (blob([cpu("cpu@0", 0), cpu("cpu@1", 0)]), None, 0),
            (blob([cpu("cpu@0", 0), cpu("cpu@0", 256)]), None, 0),
            (blob([cpu("cpu@0", 0, extra=[("reg", bytes(4))])]), None, 0),
            (blob([cpu("cpu@0", 0, extra=[("enable-method", b"psci\0")])]), None, 0),
            (blob([cpu("cpu@0", 1 << 24)]), None, 0),
            (blob([cpu("cpu", 0)]), None, 0),
            (blob([cpu("cpu@0", 0, status=b"fail\0")]), None, 0),
            (blob([cpu("cpu@0", 0)], extra=[("#address-cells", struct.pack(">I", 1))]), None, 0),
            (blob([cpu("cpu@0", 0)], cells=2), None, 0),
            (blob([cpu("cpu@" + str(i), i * 256) for i in range(5)]), None, 0),
        ]
        harness = '#include "fdt.h"\n#include <assert.h>\n#include <string.h>\nint main(void) {\n'
        harness += 'struct rpi5_fdt_cpus out, prior; memset(&prior,0xa5,sizeof prior);\n'
        for i, (data, affinities, mask) in enumerate(cases):
            harness += 'const unsigned char b%d[] = {%s};\n' % (i, ','.join(map(str, data)))
            harness += 'out=prior;\n'
            if affinities is None:
                harness += f'assert(rpi5_fdt_cpus(b{i},sizeof b{i},&out)==-1); assert(!memcmp(&out,&prior,sizeof out));\n'
            else:
                harness += f'assert(!rpi5_fdt_cpus(b{i},sizeof b{i},&out)); assert(out.count=={len(affinities)} && out.enabled_mask=={mask});\n'
                for n, affinity in enumerate(affinities):
                    harness += f'assert(out.affinity[{n}]=={affinity});\n'
        harness += 'return 0; }\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.c").write_text(harness)
            subprocess.run(["xcrun", "clang", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-I" + str(ROOT / "loader/rpi5"), str(path / "test.c"), str(ROOT / "loader/rpi5/fdt.c"), "-o", str(path / "test")], check=True)
            subprocess.run([str(path / "test")], check=True)

    def test_framing_and_bounds(self):
        harness = r'''
#include "fdt.h"
#include <assert.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
static void put(uint8_t *p, uint32_t n) { p[0]=n>>24; p[1]=n>>16; p[2]=n>>8; p[3]=n; }
static void fixture(uint8_t *b) {
    memset(b,0,72); put(b,0xd00dfeed); put(b+4,72); put(b+8,56);
    put(b+12,72); put(b+16,40); put(b+20,17); put(b+24,16); put(b+36,16);
    put(b+56,1); put(b+64,2); put(b+68,9);
}
int main(int argc, char **argv) {
    uint8_t b[72]; struct rpi5_fdt_layout out, untouched;
    memset(&untouched,0xa5,sizeof untouched); fixture(b);
    assert(!rpi5_fdt_layout(b,72,&out)); assert(out.total==72 && out.reservations_size==16);
    assert(!rpi5_fdt_structure(b,72));
    struct rpi5_ranges reserved_out, reserved_prior;
    memset(&reserved_prior,0xa5,sizeof reserved_prior);
    assert(!rpi5_fdt_reservations(b,72,&reserved_out) && reserved_out.count==0);
    uint8_t reserved_blob[88]={0}; fixture(reserved_blob);
    memmove(reserved_blob+72,reserved_blob+56,16); memset(reserved_blob+40,0,32);
    put(reserved_blob+4,88); put(reserved_blob+8,72); put(reserved_blob+12,88);
    put(reserved_blob+44,0x1000); put(reserved_blob+52,0x2000);
    assert(!rpi5_fdt_reservations(reserved_blob,88,&reserved_out));
    assert(reserved_out.count==1 && reserved_out.extent[0].start==0x1000 && reserved_out.extent[0].end==0x3000);
    assert(rpi5_fdt_psci_smc(b,72)==-1);
    struct rpi5_fdt_cpus cpus, prior;
    memset(&prior,0xa5,sizeof prior); cpus=prior;
    assert(rpi5_fdt_cpus(b,72,&cpus)==-1 && !memcmp(&cpus,&prior,sizeof cpus));
    for (size_t n=0;n<72;n++) {
        uint8_t *shortbuf=malloc(n ? n : 1); memcpy(shortbuf,b,n); out=untouched;
        assert(rpi5_fdt_layout(shortbuf,n,&out)==-1);
        assert(rpi5_fdt_structure(shortbuf,n)==-1);
        assert(!memcmp(&out,&untouched,sizeof out)); free(shortbuf);
    }
    const uint32_t mutations[][2] = {
        {0,0},{4,73},{8,57},{8,UINT32_MAX},{12,73},{16,41},{16,56},
        {20,16},{24,18},{32,1},{36,0},{36,UINT32_MAX}
    };
    for (size_t i=0;i<sizeof mutations/sizeof mutations[0];i++) {
        fixture(b); put(b+mutations[i][0],mutations[i][1]); out=untouched;
        assert(rpi5_fdt_layout(b,72,&out)==-1);
        assert(!memcmp(&out,&untouched,sizeof out));
    }
    fixture(b); put(b+12,60); put(b+32,4); assert(rpi5_fdt_layout(b,72,&out)==-1);
    fixture(b); put(b+40,1); assert(rpi5_fdt_layout(b,72,&out)==-1); /* zero-sized reservation */
    fixture(b); put(b+48,1); assert(rpi5_fdt_layout(b,72,&out)==-1); /* no terminator before structure */
    assert(rpi5_fdt_layout(NULL,72,&out)==-1); assert(rpi5_fdt_layout(b,72,NULL)==-1);
    fixture(b); put(b+56,2); assert(rpi5_fdt_structure(b,72)==-1);
    fixture(b); put(b+64,9); assert(rpi5_fdt_structure(b,72)==-1);
    fixture(b); put(b+68,4); assert(rpi5_fdt_structure(b,72)==-1);
    fixture(b); put(b+64,3); assert(rpi5_fdt_structure(b,72)==-1);
    fixture(b); b[60]='a'; assert(rpi5_fdt_structure(b,72)==-1);
    fixture(b); b[61]=1; assert(rpi5_fdt_structure(b,72)==-1);
    uint8_t property[90]={0}; fixture(property);
    put(property+4,90); put(property+12,88); put(property+32,2); put(property+36,32);
    put(property+64,3); put(property+68,1); put(property+72,0);
    property[76]=42; put(property+80,2); put(property+84,9); property[88]='x';
    assert(!rpi5_fdt_structure(property,90));
    property[77]=1; assert(!rpi5_fdt_structure(property,90)); property[77]=0;
    property[89]='y'; assert(rpi5_fdt_structure(property,90)==-1); property[89]=0;
    put(property+72,2); assert(rpi5_fdt_structure(property,90)==-1); put(property+72,0);
    put(property+68,UINT32_MAX); assert(rpi5_fdt_structure(property,90)==-1);
    if (argc==2) {
        FILE *f=fopen(argv[1],"rb"); assert(f); assert(!fseek(f,0,SEEK_END));
        long n=ftell(f); assert(n>0); rewind(f); uint8_t *blob=malloc((size_t)n);
        assert(fread(blob,1,(size_t)n,f)==(size_t)n); fclose(f);
        assert(!rpi5_fdt_layout(blob,(size_t)n,&out));
        assert(!rpi5_fdt_structure(blob,(size_t)n));
        reserved_out=reserved_prior;
        assert(rpi5_fdt_reservations(blob,(size_t)n,&reserved_out)==-1); /* malformed four-byte CMA size */
        assert(!memcmp(&reserved_out,&reserved_prior,sizeof reserved_out));
        struct rpi5_fdt_memory memory;
        assert(!rpi5_fdt_memory(blob,(size_t)n,&memory));
        assert(memory.count==1 && memory.start[0]==0 && memory.end[0]==0x28000000);
        assert(!rpi5_fdt_psci_smc(blob,(size_t)n));
        unsigned conduit_changed=0;
        for (size_t i=0;i+4<=(size_t)n;i++) {
            if (!memcmp(blob+i,"smc",4)) {
                memcpy(blob+i,"hvc",4); assert(rpi5_fdt_psci_smc(blob,(size_t)n)==-1);
                memcpy(blob+i,"smc",4); conduit_changed=1; break;
            }
        }
        assert(conduit_changed);
        assert(!rpi5_fdt_cpus(blob,(size_t)n,&cpus));
        assert(cpus.count==4 && cpus.enabled_mask==15);
        for (unsigned i=0;i<4;i++) assert(cpus.affinity[i]==(uint64_t)i*256);
        unsigned changed=0;
        for (size_t i=0;i+14<=(size_t)n;i++) {
            if (!memcmp(blob+i,"arm,cortex-a76",14)) {
                blob[i]='x'; cpus=prior;
                assert(rpi5_fdt_cpus(blob,(size_t)n,&cpus)==-1);
                assert(!memcmp(&cpus,&prior,sizeof cpus)); blob[i]='a'; changed++; break;
            }
        }
        assert(changed); free(blob);
    }
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.c").write_text(harness)
            subprocess.run(["xcrun", "clang", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-I" + str(ROOT / "loader/rpi5"), str(path / "test.c"), str(ROOT / "loader/rpi5/fdt.c"), "-o", str(path / "test")], check=True)
            blob = ROOT / "build/rpi5/bcm2712-rpi-5-b-2768f610.dtb"
            subprocess.run([str(path / "test"), *([str(blob)] if blob.exists() else [])], check=True)
