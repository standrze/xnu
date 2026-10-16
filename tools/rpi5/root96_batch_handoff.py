#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Actual retained-FDT/root-tree geometry with the new kernel and loader extent.

Host buffers and a synthetic complete 8-GiB FDT only; never a board admission.
Reuse the frozen native retained-tree exercise, replacing its tiny toy-kernel
geometry with the actual kernel and root extents in a private generated source.
"""
import hashlib
from pathlib import Path
import shlex
import subprocess
import tempfile
try:
    from . import pcie_id_handoff_contract as ancestor
except ImportError:
    import pcie_id_handoff_contract as ancestor

ROOT=ancestor.ROOT
TEMPLATE=ROOT/'tools/rpi5/tests/firmware_fdt_host.c'
CORES=ancestor.CORES


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def source(kernel_end,root_bytes,loader_end):
    text=('#include "pcie_device_handoff.h"\n#include "'+
        str(ROOT/'osfmk/arm64/rpi5_memory_map.h')+'"\n'+TEMPLATE.read_text())
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('Native retained-root fixture boundary changed')
        text=text.replace(old,new)
    args=(kernel_end+0x3fff)&~0x3fff;root=args+0x8000
    replace('size > 0 && size < 256 * 1024','size > 0 && size < 32 * 1024 * 1024')
    anchor='        assert(!rpi5_board_tree_memory_map(&tree, &types));'
    replace(anchor,'''        types.device.count=3;
        types.device.extent[0]=(struct rpi5_range){0x107d000000,0x107d004000};
        types.device.extent[1]=(struct rpi5_range){0x107d200000,0x107d204000};
        types.device.extent[2]=(struct rpi5_range){0x107fff8000,0x107fffc000};
        struct rpi5_memory_types with_device;
        assert(!rpi5_pcie_device_handoff(source,bytes,&types,&with_device));
        assert(with_device.device.count==6);types=with_device;
'''+anchor)
    replace('        struct rpi5_range live[] = {{0x9000000, 0x9004000}, {0xb000000, 0xb000000 + bytes}};',
        '        struct rpi5_macho_placement actual;\n'
        '        assert(!rpi5_macho_placement(image,image_bytes,0x7004000,0x6000000,0x10000000,&actual));\n'
        f'        assert(actual.end==UINT64_C({kernel_end}));\n'
        f'        assert(!rpi5_board_tree_ramdisk(&tree,UINT64_C({root}),UINT64_C({root_bytes})));\n'
        f'        struct rpi5_range live[] = {{{{0x9000000,UINT64_C({loader_end})}},'
        f'{{0xb000000,0xb000000+bytes}},{{UINT64_C({root}),UINT64_C({root+root_bytes})}}}};\n'
        '        assert(live[2].end<=live[0].start&&live[0].end<=live[1].start);')
    replace('live, 2, &resolved','live, 3, &resolved')
    replace('.args_pa = 0x8000000, .tree_pa = 0x8004000',
        f'.args_pa = UINT64_C({args}), .tree_pa = UINT64_C({args+0x4000})')
    replace('&tree.root, 16384, live, 2, "serial=3", 8, &handoff)',
        '&tree.root, 16384, live, 3, "serial=3", 8, &handoff)')
    anchor='        assert(span.physical == live[1].start && span.bytes == bytes);'
    replace(anchor,anchor+'''
        /* Exact live root/loader/FDT conflicts must fail with unchanged output. */
        struct rpi5_handoff_plan saved=handoff;
        for(unsigned bad=0;bad<3;bad++) {
            struct rpi5_handoff_input overlap=input;
            if(bad==0)overlap.args_pa=live[2].start;
            if(bad==1)overlap.tree_pa=live[0].start;
            if(bad==2)overlap.tree_pa=live[1].start;
            assert(rpi5_resolved_tree_handoff(image,image_bytes,&overlap,&resolved,&types,
                &tree.root,16384,live,3,"serial=3",8,&handoff));
            assert(!memcmp(&saved,&handoff,sizeof saved));
        }
''')
    anchor='        assert(found == 1);'
    replace(anchor,anchor+'''
        unsigned roots=0;
        for(size_t i=0;i+16<=written;i++)if(!memcmp(apple+i,tree.ramdisk_record,16))roots++;
        assert(roots==1&&tree.image_memory_map.property_count==1);
        unsigned maps=0;const uint8_t *serialized=0;
        size_t map_bytes=tree.chosen_props[2].length;
        for(size_t i=0;i+map_bytes<=written;i++)if(!memcmp(apple+i,tree.memory_map,map_bytes)) {maps++;serialized=apple+i;}
        assert(maps==1);
        struct rpi5_kernel_memory_map decoded;
        assert(!rpi5_map_decode(serialized,map_bytes,&decoded));
        assert(rpi5_map_type(&decoded,span.physical,span.physical+span.bytes)==1);
        const struct rpi5_range regions[]={before.bridge_regs,before.rescal_regs,before.bridge_reset_regs};
        for(unsigned i=0;i<3;i++)assert(rpi5_map_type(&decoded,regions[i].start,regions[i].end)==2);
''')
    return text


def audit(loader,kernel,kernel_end,root_bytes,loader_end):
    text=source(kernel_end,root_bytes,loader_end)
    with tempfile.TemporaryDirectory(prefix='root96-live-handoff-') as temporary:
        work=Path(temporary);host=work/'host.c';host.write_text(text)
        sources=[host,loader/'firmware_seed_tree.c']+[ROOT/'loader/rpi5'/(name+'.c') for name in CORES]
        flags=['xcrun','clang','-std=c11','-O2','-Wall','-Wextra','-Werror',
               '-DRPI5_FIRMWARE_FDT_HANDOFF=1','-fsanitize=address,undefined',
               '-I',str(ROOT/'loader/rpi5')]
        def capture():
            pins={str(TEMPLATE):sha(TEMPLATE),str(Path(__file__).resolve()):sha(Path(__file__))}
            for path in sources:
                r=subprocess.run(flags+['-M',str(path)],cwd=ROOT,text=True,capture_output=True,timeout=30)
                if r.returncode or r.stderr:raise ValueError('Native retained-root dependencies failed')
                for token in shlex.split(r.stdout.replace('\\\n',' ').partition(':')[2]):
                    p=Path(token).resolve()
                    if p!=host.resolve():pins[str(p)]=sha(p)
            return pins
        pins=capture();program=work/'host'
        r=subprocess.run(flags+list(map(str,sources))+['-o',str(program)],cwd=ROOT,
                         text=True,capture_output=True,timeout=60)
        if r.returncode or r.stderr:raise ValueError('Native retained-root compile failed: '+r.stderr)
        tree=ancestor._synthetic_tree()
        tree['children'].append(ancestor._node('chosen',{'rng-seed':bytes(range(64))}))
        fixture=work/'fixture.dtb';fixture.write_bytes(ancestor._encode_fdt(tree))
        r=subprocess.run([str(program),str(fixture),str(kernel),'accept'],text=True,capture_output=True,timeout=30)
        expected='FIRMWARE_FDT_PASS SEEDS=1 RETAINED=1 APPLE_TREE=1 PCIE_DECODE=1 NO_MMIO=1\n'
        if r.returncode or r.stderr or r.stdout!=expected:
            raise ValueError('Actual-kernel retained-root geometry rejected: '+repr(r))
        if pins!=capture():raise ValueError('Native retained-root dependencies changed')
        return dict(native_pass=True,asan_ubsan=True,actual_kernel_sha256=sha(kernel),
            root_bytes=root_bytes,kernel_end=kernel_end,loader_end=loader_end,
            raw_fdt_pa=0xb000000,root_serialized_once=True,retained_fdt_serialized_once=True,
            emitted_device_resources=3,actual_kernel_map_decoder=True,
            live_overlap_rejections=3,unchanged_output_on_rejection=True,
            adapted_host_sha256=hashlib.sha256(text.encode()).hexdigest(),
            fixture_sha256=sha(fixture),inputs_sha256=pins,stdout=r.stdout,
            physical_execution=False,scope='Actual kernel and loader extents; synthetic complete RAM/FDT; no physical load proof')
