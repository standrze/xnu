#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Connect the actual controller to RP1 header reads in a distinct kernel."""
import argparse
import json
from pathlib import Path
import re
import shutil
try:
    from . import build_pcie_fw_client_kernel as previous
except ImportError:
    import build_pcie_fw_client_kernel as previous

audit, ROOT, full = previous.audit, previous.ROOT, previous.full
BASE = ROOT / 'build/rpi5/pcie-fw-client-kernel-20261013-final'
BASE_SHA = '4a2c9170a0413415410cf7719310ad1bd65e207f2d62d951e2b35502304d990e'
BODY = ROOT / 'iokit/Kernel/BCM2712RP1ConfigTransport.inc'
POLICY = ROOT / 'iokit/Kernel/BCM2712RP1ConfigPolicy.h'
CORE = ROOT / 'loader/rpi5/rp1_config_snapshot.c'


def inputs():
    if audit.sha(BASE/'manifest.json') != BASE_SHA:
        raise ValueError('Accepted firmware client manifest changed')
    prior = json.loads((BASE/'manifest.json').read_text())
    pins = {**prior['inputs_sha256'], **prior['generated_sha256'], str(BASE/'manifest.json'): BASE_SHA}
    for source in (BODY, POLICY, CORE, CORE.with_suffix('.h'), Path(__file__).resolve(),
                   ROOT/'tools/rpi5/tests/test_rp1_config.py', ROOT/'tools/rpi5/tests/rp1_config_host.c',
                   ROOT/'tools/rpi5/tests/rp1_transport_host.cpp'):
        pins[str(source)] = audit.sha(source)
    for name, digest in pins.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('RP1 inherited input changed: '+name)
    objects = [Path(p) for p in (BASE/'kernel.pcie-fw-client.filelist').read_text().splitlines() if p]
    if len(objects) != len(set(objects)) or objects.count(BASE/'BCM2712PCIePHYTransport.cpp.o') != 1:
        raise ValueError('Ambiguous inherited transport')
    return pins, prior, objects


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Accepted overlay boundary changed: '+old)
    return text.replace(old,new)


def overlay_sources(output):
    overlay = output/'overlay'; overlay.mkdir()
    for name in ('BCM2712PCIePHYTransport.cpp', 'BCM2712PCIePHYTransport.h', 'BCM2712PCIeFWTransport.inc'):
        shutil.copyfile(BASE/'overlay'/name,overlay/name)
    header = overlay/'BCM2712PCIePHYTransport.h'
    text = replace_once(header.read_text(), '#include "BCM2712PCIeControllerPolicy.h"',
        '#include "BCM2712RP1ConfigPolicy.h"')
    text = replace_once(text,'extern "C" {','extern "C" {\n#include "../../loader/rpi5/rp1_config_snapshot.h"')
    text = replace_once(text,'class BCM2712PCIePHYTransport : public IOService {',
        'struct bcm2712_rp1_observation {\n    struct bcm2712_controller_observation controller;\n'
        '    struct rpi5_rp1_config_snapshot endpoint;\n};\n\nclass BCM2712PCIePHYTransport : public IOService {')
    text = replace_once(text,'    unsigned phase = BCM2712_PHY_EMPTY;',
        '    struct rpi5_pcie_config rp1Config = {};\n'
        '    bool rp1Locked = false, rp1Attempted = false;\n'
        '    static int rp1Acquire(void *);\n    static void rp1Release(void *);\n'
        '    static int rp1Lifecycle(void *);\n'
        '    static int rp1DenyWrite(void *, const struct rpi5_pcie_config_request *);\n'
        '    static int rp1Read(void *, uint32_t, uint32_t, uint32_t *);\n'
        '    static int rp1Write(void *, uint32_t, uint32_t, uint32_t);\n'
        '    unsigned phase = BCM2712_PHY_EMPTY;')
    text = replace_once(text,'    bool runController(const struct bcm2712_controller_admission *,',
        '    /* One actual controller sequence followed by fixed RP1 header reads.\n'
        '     * No lifecycle bypass, BAR writes, DMA or mapped RP1 registers. */\n'
        '    bool runControllerAndObserveRP1(const struct bcm2712_controller_admission *,\n'
        '        struct bcm2712_rp1_observation *);\n'
        '    bool runController(const struct bcm2712_controller_admission *,')
    header.write_text(text)
    body = overlay/'BCM2712PCIeFWTransport.inc'
    body.write_text(replace_once(body.read_text(),'currentPhase==BCM2712_PHY_CLOCK_FINISHING)',
        'currentPhase==BCM2712_PHY_CLOCK_FINISHING || currentPhase==BCM2712_PHY_RP1_INSPECTING)'))
    cpp = overlay/'BCM2712PCIePHYTransport.cpp'
    cpp.write_text(cpp.read_text()+'\n#include "BCM2712RP1ConfigTransport.inc"\n')
    return cpp


def build(output):
    pins, prior, original = inputs(); output = output.resolve()
    if not (output.parent == ROOT/'build/rpi5' or output.is_relative_to(Path('/private/tmp')) or
            output.is_relative_to(Path('/private/var/folders'))):
        raise ValueError('RP1 kernel requires a separate build directory')
    output.mkdir(parents=True,exist_ok=False)
    commands=[]; compiles=[]
    def execute(args,name,cwd=ROOT,strict=True):
        row = audit.execute(args,cwd,output/(name+'.log')); commands.append(row)
        if row['returncode'] or (strict and row['warning_count']):
            raise ValueError('RP1 build failed or warned: '+row['log'])
        return row
    cpp = overlay_sources(output)
    oldcpp = BASE/'overlay/BCM2712PCIePHYTransport.cpp'
    templates = ((cpp, prior['compiles'][2]['command'], oldcpp, audit.OBJ/'iokit/DEVELOPMENT'),
                 (CORE, prior['compiles'][1]['command'], previous.CORE, audit.OBJ/'pexpert/DEVELOPMENT'))
    new=[]
    for source, template, old, cwd in templates:
        if template.count(str(old)) != 1: raise ValueError('Ambiguous compiler input')
        obj = output/(source.name+'.o')
        args = [str(source) if arg == str(old) else arg for arg in template[:-2]]+['-o',str(obj)]
        args[1:1]=['-DRPI5_RP1_CONFIG_DIAGNOSTIC=1']
        dep = output/(source.name+'.d')
        execute([a for a in args[:-2] if a!='-c']+['-M','-MG','-MF',str(dep)],source.name+'-deps',cwd)
        for path in audit.dependency_paths(dep,cwd):
            if not path.is_file(): raise ValueError('Missing RP1 header: '+str(path))
            digest=audit.sha(path)
            if str(path) in pins and pins[str(path)]!=digest: raise ValueError('RP1 header drift: '+str(path))
            pins[str(path)]=digest
        row=execute(args,source.name+'-compile',cwd); row['object_sha256']=audit.sha(obj)
        compiles.append(row);new.append(obj)
        if source==cpp:
            execute([a for a in args[:-2] if a!='-c']+['-S','-o',str(output/'transport.s')],'assembly',cwd)
    _,_,extras,flags,archive,_=full.inputs()
    old=BASE/'BCM2712PCIePHYTransport.cpp.o'
    objects=[new[0] if p==old else p for p in original]+new[1:]
    filelist=output/'kernel.rp1-config.filelist';filelist.write_text(''.join(str(p)+'\n' for p in objects))
    kernel,unstripped,linkmap=output/'kernel.rp1-config',output/'kernel.unstripped',output/'kernel.map'
    flags=[('-Wl,-map,'+str(linkmap)) if a.startswith('-Wl,-map,') else a for a in flags]
    row=execute(flags+['-filelist',filelist,*extras,'-o',unstripped,archive],'link',strict=False)
    warnings=[line for line in Path(row['log']).read_text().splitlines() if 'warning:' in line]
    if warnings!=prior['baseline_linker_warnings']:raise ValueError('New RP1 kernel linker warnings')
    execute(['xcrun','strip','-S',unstripped,'-o',kernel],'strip')
    listing=audit.read_command(['xcrun','nm','-nm',kernel]);(output/'kernel.symbols').write_text(listing+'\n')
    if audit.read_command(['xcrun','nm','-ju',kernel]):raise ValueError('Undefined RP1 kernel symbols')
    textmap=linkmap.read_text(errors='surrogateescape')
    if str(old) in textmap or any(str(p) not in textmap for p in objects):raise ValueError('Incorrect RP1 constituents')
    linked=full.linked_audit(kernel.read_bytes(),listing,textmap)
    names=full.symbols(listing)
    required=['_rpi5_rp1_config_snapshot','_rpi5_pcie_config_init','_rpi5_pcie_config_transfer']
    required += [name for name in names if name.startswith('__ZN23BCM2712PCIePHYTransport') and '.' not in name and
                 any(part in name for part in ('runControllerAndObserveRP1','rp1Acquire','rp1Release',
                     'rp1Lifecycle','rp1DenyWrite','rp1Read','rp1Write'))]
    if len(required)!=10:raise ValueError('RP1 implementations missing')
    for name in required:
        if len(names.get(name,[]))!=1:raise ValueError('RP1 executable symbol ambiguous: '+name)
        address=names[name][0]
        if not any(s['initprot']&4 and s['vmaddr']<=address<s['vmaddr']+s['filesize'] for s in linked['macho']['segments']):
            raise ValueError('RP1 symbol is not executable: '+name)
    assembly=(output/'transport.s').read_text()
    emitted={}
    for method,instruction in (('rp1Read','ldr'),('rp1Write','str')):
        name=next(n for n in required if method in n)
        match=re.search(re.escape(name)+r':[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.S)
        if not match:raise ValueError('Missing emitted RP1 method: '+method)
        body=match[1]
        ordered=re.search(r'\tdmb\tosh\n(.*?)\tdsb\tsy',body,re.S)
        if not ordered or not re.search(r'\t'+instruction+r'\tw\d+, \[x\d+(?:, [^\]]+)?\]',ordered[1]):
            raise ValueError('RP1 method has no ordered 32-bit hardware access: '+method)
        if len(re.findall(r'\t(?:ldr|str)\tw\d+,',ordered[1]))!=1:
            raise ValueError('Unexpected read-modify-write between RP1 barriers')
        emitted[method]=dict(ordered_access=instruction+'32',rmw=False)
    for name,digest in pins.items():
        if audit.sha(Path(name))!=digest:raise ValueError('RP1 input changed during build: '+name)
    report=dict(profile='rp1-read-only-config-kernel-v1',inputs_sha256=pins,
        generated_sha256={str(p):audit.sha(p) for p in output.rglob('*') if p.is_file()},
        kernel=str(kernel),kernel_sha256=audit.sha(kernel),kernel_bytes=kernel.stat().st_size,
        link=linked,required_implementations=required,emitted_transport_accesses=emitted,compiles=compiles,commands=commands,
        baseline_linker_warnings=warnings,complete_kernel_link_proven=True,
        actual_controller_then_rp1_config=True,endpoint_header_reads=32,selector_writes=32,
        endpoint_config_writes=0,new_mapped_pages=0,bar_size_or_assignment_inferred=False,
        full_lifecycle_provider_added=False,boot_caller_added=False,
        installed=False,pi_executed=False,ethernet_proven=False)
    (output/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    result=build(parser.parse_args().output_dir)
    print(json.dumps({name:result[name] for name in ('kernel','kernel_bytes','kernel_sha256','pi_executed')}))
