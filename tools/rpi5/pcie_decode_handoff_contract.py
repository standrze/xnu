# SPDX-License-Identifier: BSD-2-Clause
"""Actual emitted no-init tree and kernel decoders with six RP1 Device pages."""
from pathlib import Path
import shlex
import subprocess
import tempfile
from tools.rpi5 import pcie_id_handoff_contract as prior
ROOT=prior.ROOT
EXPECTED=prior.EXPECTED.replace('DEVICE_RESOURCES=3','DEVICE_RESOURCES=5 RP1_PAGES=6')


def host_source():
    source=(ROOT/'tools/rpi5/tests/pcie_id_handoff_host.c').read_text()
    changes={
      '#include "firmware_fdt_host.c"':'#include "'+str(ROOT/'tools/rpi5/tests/firmware_fdt_host.c')+'"',
      '#include "../../../osfmk/arm64/rpi5_memory_map.h"':'#include "'+str(ROOT/'osfmk/arm64/rpi5_memory_map.h')+'"\n#include "rp1_device_handoff.h"',
      '    assert(types.device.count == 6);':'''    assert(types.device.count == 6);
    struct rpi5_memory_types rp1_types;
    assert(!rpi5_rp1_device_handoff(fdt, bytes, &types, &rp1_types));
    types=rp1_types;assert(types.device.count==8);''',
      '    /* Descriptor may not name Device memory or overlap the loaded kernel. */':'''    assert(rpi5_map_type(&map,0x1f00100000,0x1f00104000)==2);
    assert(rpi5_map_type(&map,0x1f00018000,0x1f0002c000)==2);
    assert(rpi5_map_type(&map,0x1f00104000,0x1f00108000)==0);
    assert(rpi5_map_type(&map,0x1f00014000,0x1f00018000)==0);
    assert(rpi5_map_type(&map,0x1f0002c000,0x1f00030000)==0);
    /* Descriptor may not name Device memory or overlap the loaded kernel. */''',
      'DEVICE_RESOURCES=3':'DEVICE_RESOURCES=5 RP1_PAGES=6'}
    for old,new in changes.items():
        if source.count(old)!=1:raise ValueError('Exact original emitted-tree fixture changed: '+old)
        source=source.replace(old,new)
    return source


def audit(loader):
    sources=[loader/'firmware_seed_tree.c']+[ROOT/'loader/rpi5'/(name+'.c') for name in prior.CORES+('rp1_device_handoff',)]
    flags=['xcrun','clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-DRPI5_FIRMWARE_FDT_HANDOFF=1',
        '-fsanitize=address,undefined','-I',str(ROOT/'loader/rpi5')]
    with tempfile.TemporaryDirectory(prefix='rp1-decode-tree-') as temporary:
        work=Path(temporary).resolve();host=work/'host.c';host.write_text(host_source())
        def capture():
            result={str(Path(__file__).resolve()):prior.digest(Path(__file__).resolve()),
                str(ROOT/'tools/rpi5/tests/pcie_id_handoff_host.c'):prior.digest(ROOT/'tools/rpi5/tests/pcie_id_handoff_host.c')}
            for path in [host]+sources:
                r=subprocess.run(flags+['-M',str(path)],cwd=ROOT,text=True,capture_output=True,timeout=30)
                if r.returncode:raise ValueError('Decode handoff dependencies failed: '+r.stderr)
                for token in shlex.split(r.stdout.replace('\\\n',' ').partition(':')[2]):
                    p=Path(token).resolve()
                    if p!=host:result[str(p)]=prior.digest(p)
            return result
        pins=capture();program,fixture,kernel=work/'host',work/'fixture.dtb',work/'kernel'
        tree=prior._synthetic_tree();tree['children'].append(prior._node('chosen',{'rng-seed':bytes(range(64))}))
        fixture.write_bytes(prior._encode_fdt(tree));kernel.write_bytes(prior.image())
        compiled=subprocess.run(flags+list(map(str,[host]+sources))+['-o',str(program)],cwd=ROOT,text=True,capture_output=True,timeout=60)
        if compiled.returncode or compiled.stderr:raise ValueError('Native decode handoff compilation failed: '+compiled.stderr)
        result=subprocess.run([program,fixture,kernel,'accept'],text=True,capture_output=True,timeout=30)
        if result.returncode or result.stderr or result.stdout!=EXPECTED:raise ValueError('Native decode handoff failed: '+repr(result))
        if pins!=capture():raise ValueError('Decode handoff inputs drifted')
        fixture_sha,kernel_sha=prior.digest(fixture),prior.digest(kernel)
    return dict(native_pass=True,asan_ubsan=True,no_init=True,serialized_chosen=True,
        actual_kernel_record_and_map_decoders=True,missing_descriptor_rejected=True,
        exact_rp1_pages=6,excluded_adjacent_pages=True,inputs_sha256=pins,
        fixture_sha256=fixture_sha,synthetic_kernel_sha256=kernel_sha,stdout=EXPECTED,physical_execution=False)
