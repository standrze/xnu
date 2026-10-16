#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Actual A76/Apple object+stack evidence for new real CPU-owned ring caller.

No kernel/image publication, hardware, media or DMA activation. A complete
kernel/loader composition and checker remain separate prerequisites.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from tools.rpi5 import gem_dma_batch_transport_profile as profile
from tools.rpi5 import build_display_xnu_console as base
ROOT=profile.ROOT
CAP=profile.FROZEN.parent
TEMPLATE=ROOT/'build/rpi5/pcie-phy-reset-kernel-20261014-v2'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def sources():
    return [Path(__file__),Path(profile.__file__),Path(profile.memory.__file__),Path(profile.memory.prior.__file__),
        *[ROOT/p for p in profile.memory.BASE_PINS],
        *[ROOT/'iokit/Kernel'/n for n in ('BCM2712GEMDMABatchAccess.inc','BCM2712GEMDMABatchTransport.inc',
            'rpi5_gem_ring_batch.h','rpi5_gem_ring_batch.c')],
        *[ROOT/'tools/rpi5/tests'/n for n in ('test_gem_ring_batch.py','test_gem_dma_batch.py','test_gem_dma_batch_transport.py')]]
def recipes(output):
    cap=json.loads((CAP/'manifest.json').read_text());template=json.loads((TEMPLATE/'manifest.json').read_text())
    cpp=next(r['command'] for r in cap['compiles'] if '/BCM2712PCIePHYTransport.cpp' in ' '.join(r['command']))
    cppflags=base.compiler_flags(cpp,CAP/'overlay/BCM2712PCIePHYTransport.cpp')
    crow=next(r['command'] for r in template['compiles'] if '/rp1_gem_mdio.c' in ' '.join(r['command']))
    csource=next(a for a in crow if a.endswith('/overlay/rp1_gem_mdio.c'))
    cflags=base.compiler_flags(crow,csource)
    includes=['-I'+str(output/'overlay'),'-I'+str(ROOT),'-I'+str(ROOT/'osfmk'),
              '-I'+str(ROOT/'iokit/Kernel'),'-I'+str(ROOT/'loader/rpi5')]
    cppflags[1:1]=includes;cflags[1:1]=includes
    # Genuine kernel operator new is nullable; retain null-before-constructor
    # control flow instead of importing hosted C++ nonnull assumptions.
    cppflags+=['-fstack-usage','-fcheck-new'];cflags+=['-fstack-usage']
    rows=[('transport',output/'overlay/BCM2712PCIePHYTransport.cpp',cppflags,base.OBJ/'iokit/DEVELOPMENT'),
          ('provider',output/'overlay/BCM2712GEMDMABatch.cpp',cppflags,base.OBJ/'iokit/DEVELOPMENT')]
    paths=[ROOT/'iokit/Kernel/rpi5_gem_ring_batch.c',ROOT/'iokit/Kernel/rpi5_gem_dma_route.c',
        ROOT/'osfmk/arm64/rpi5_reservation_kernel.c',ROOT/'loader/rpi5/reservation_record.c',
        ROOT/'loader/rpi5/reservations.c',ROOT/'loader/rpi5/ranges.c',
        ROOT/'loader/rpi5/pcie_windows.c',ROOT/'loader/rpi5/pcie_released_windows.c',
        output/'overlay/rp1_gem_identify.c',output/'overlay/rp1_gem_capabilities.c']
    return rows+[(p.stem,p,cflags,base.OBJ/'pexpert/DEVELOPMENT') for p in paths]
def build(output):
    output=Path(output).resolve()
    if output.parent!=ROOT/'build/rpi5':raise ValueError('Distinct workspace build child only')
    output.mkdir(exist_ok=False);profile.emit(output/'overlay')
    inputs={str(p.resolve()):sha(p) for p in sources()}
    inputs.update({str(CAP/'manifest.json'):sha(CAP/'manifest.json'),str(TEMPLATE/'manifest.json'):sha(TEMPLATE/'manifest.json')})
    commands=[];headers={}
    def run(command,label,cwd):
        command=list(map(str,command));p=subprocess.run(command,cwd=cwd,capture_output=True,timeout=90)
        log=output/(label+'.log');log.write_bytes(p.stdout+p.stderr)
        commands.append(dict(command=command,cwd=str(cwd),returncode=p.returncode,log=str(log),log_sha256=sha(log)))
        if p.returncode or b'warning:' in p.stderr:raise ValueError('Object qualification failed: '+str(log))
    for label,source,flags,cwd in recipes(output):
        dep=output/(label+'.d');obj=output/(label+'.o')
        run([*flags,'-c','-MD','-MF',dep,source,'-o',obj],label,cwd)
        headers.update({p:sha(p) for p in base.dependencies(dep,cwd)})
        run(['xcrun','llvm-objdump','-d',obj],label+'-disassembly',ROOT)
        run(['xcrun','nm',obj],label+'-symbols',ROOT)
    for p,h in inputs.items():
        if sha(p)!=h:raise ValueError('Source changed during object build')
    report=dict(profile='gem-real-cpu-owned-batch-a76-objects-v1',inputs_sha256=inputs,
        actual_headers_sha256=headers,commands=commands,hardware=False,linked_kernel=False,
        active_dma_route=False,queue_publication=False,owner_check_limit=65536,
        modeled_pm_checks=64940,modeled_firmware_sequence=16233)
    report['generated_sha256']={str(p):sha(p) for p in output.rglob('*') if p.is_file()}
    (output/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output');args=parser.parse_args();build(args.output)
