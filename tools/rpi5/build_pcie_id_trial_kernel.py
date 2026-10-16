#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct single-CPU first-controller/RP1-ID kernel with DMA decode closed."""
import argparse
import json
from pathlib import Path
import re
import shutil
try:
    from . import build_rp1_config_kernel as base
    from . import pcie_fw_reuse_recovery_evidence as recovery
except ImportError:
    import build_rp1_config_kernel as base
    import pcie_fw_reuse_recovery_evidence as recovery

ROOT,audit=base.ROOT,base.audit
BODY=ROOT/'iokit/Kernel/BCM2712PCIeIDTrial.inc'
RELEASED=ROOT/'loader/rpi5/pcie_released_windows.c'

def overlay(output):
    cpp=base_overlay(output);directory=cpp.parent
    header=directory/'BCM2712PCIePHYTransport.h'
    text=base.replace_once(header.read_text(),'extern "C" {','extern "C" {\n#include "../../loader/rpi5/pcie_released_windows.h"')
    text=base.replace_once(text,'    unsigned phase = BCM2712_PHY_EMPTY;',
        '    bool trialMode=false, trialPreclaim=false;\n'
        '    struct rpi5_pcie_released_windows trialWindows={};\n'
        '    static int trialOwner(void *);\n    static int trialOrder(void *);\n'
        '    static int trialRead(void *,uint32_t,uint32_t *);\n'
        '    static int trialAdmission(IOService *,unsigned);\n'
        '    bool trialDisableMSI();\n    unsigned phase = BCM2712_PHY_EMPTY;')
    text=base.replace_once(text,'    bool runControllerAndObserveRP1(',
        '    unsigned trialPhase() const { return getPhase(); }\n'
        '    bool runBoundedRP1Trial(struct bcm2712_rp1_observation *);\n    bool runControllerAndObserveRP1(')
    header.write_text(text)
    for name in ('BCM2712PCIeController.inc','BCM2712PCIeControllerRun.inc'):
        shutil.copyfile(ROOT/'iokit/Kernel'/name,directory/name)
    run=directory/'BCM2712PCIeControllerRun.inc'
    text=run.read_text()
    text=base.replace_once(text,
        'if (!guard() || rpi5_pcie_windows_init(&windows, &binding, &windowIO, RPI5_PCIE_WINDOW_ACK_FOUR_BYTES) ||\n        rpi5_pcie_rc_init',
        'if (!trialMode || !guard() || rpi5_pcie_windows_init(&windows, &binding, &windowIO, RPI5_PCIE_WINDOW_ACK_FOUR_BYTES)) { fail(); return false; }\n'
        '    /* Diagnostic policy: no endpoint-originated RAM/MIP window. */\n'
        '    for (unsigned i=0;i<3;i++) windows.plan.inbound[i].bar_lo &= ~UINT32_C(31);\n'
        '    if (!trialDisableMSI() || rpi5_pcie_rc_init')
    run.write_text(text)
    cpp.write_text(cpp.read_text()+'\n#include "BCM2712PCIeIDTrial.inc"\n')
    return cpp

base_overlay=base.overlay_sources

def build(output):
    output=output.resolve()
    if output.parent!=ROOT/'build/rpi5':raise ValueError('Fresh separate ID trial build required')
    evidence=recovery.inspect(ROOT/'build/rpi5/fwabi-reuse-pair-installed-20261013',
        ROOT/'build/rpi5/fwabi-reuse-capture-20261013',ROOT/'build/rpi5/fwabi-reuse-pair-restored-20261013')
    oldcore,oldinputs,oldoverlay=base.CORE,base.inputs,base.overlay_sources
    prepared=output.parent/(output.name+'-inputs');prepared.mkdir(exist_ok=False)
    base.CORE=ROOT/'loader/rpi5/rp1_config_snapshot_checked.c'
    pins,prior,objects=oldinputs()
    pins.update(evidence['files_sha256']);pins.update(evidence['verifier_source_sha256'])
    for source in (BODY,RELEASED,RELEASED.with_suffix('.h'),Path(__file__).resolve(),
                   ROOT/'tools/rpi5/tests/test_pcie_released_windows.py',
                   ROOT/'tools/rpi5/tests/pcie_released_windows_host.c',
                   ROOT/'tools/rpi5/tests/test_pcie_id_provider.py',
                   ROOT/'tools/rpi5/tests/pcie_id_provider_host.cpp'):
        pins[str(source)]=audit.sha(source)
    boot=prepared/'IOStartIOKit.cpp'
    original=ROOT/'iokit/Kernel/IOStartIOKit.cpp'
    text=base.replace_once(original.read_text(),'void\nStartIOKitMatching(void)\n{',
        'void rpi5_pcie_id_trial_start(void) __attribute__((noreturn));\n\nvoid\nStartIOKitMatching(void)\n{\n'
        '\trpi5_pcie_id_trial_start(); /* Before all driver matching; terminal diagnostic. */')
    text=base.replace_once(text,'void StartIOKitMatching(void);',
        'void StartIOKitMatching(void) __attribute__((noreturn));')
    boot.write_text(text)
    oldboot=next(p for p in objects if p.name=='IOStartIOKit.cpo')
    rows=[];new=[]
    def execute(args,name,cwd):
        row=audit.execute(args,cwd,prepared/(name+'.log'));rows.append(row)
        if row['returncode'] or row['warning_count']:raise ValueError('ID trial input compile failed: '+row['log'])
        return row
    template=json.loads(oldboot.with_suffix('.cpo.json').read_text().strip().removesuffix(','))
    bootargs=list(template['arguments']);index=bootargs.index('-o');del bootargs[index:index+2]
    bootargs=[str(boot) if a==str(original) else a for a in bootargs]
    bootargs[1:1]=['-iquote',str(ROOT/'iokit/Kernel')]
    for source,args,cwd in ((boot,bootargs,Path(template['directory'])),
                           (RELEASED,[str(RELEASED) if a==str(base.previous.CORE) else a
                                      for a in prior['compiles'][1]['command'][:-2]],audit.OBJ/'pexpert/DEVELOPMENT')):
        obj=prepared/(source.name+'.o');args=[*args,'-o',str(obj)]
        dep=prepared/(source.name+'.d')
        execute([a for a in args[:-2] if a!='-c']+['-M','-MG','-MF',str(dep)],source.name+'-deps',cwd)
        for path in audit.dependency_paths(dep,cwd):
            digest=audit.sha(path)
            if str(path) in pins and pins[str(path)]!=digest:raise ValueError('ID trial input drift: '+str(path))
            pins[str(path)]=digest
        execute(args,source.name+'-compile',cwd);new.append(obj)
        if source==boot:
            execute([a for a in args[:-2] if a!='-c']+['-S','-o',str(prepared/'boot.s')],
                    source.name+'-assembly',cwd)
    for path in prepared.rglob('*'):
        if path.is_file():pins[str(path)]=audit.sha(path)
    objects=[new[0] if p==oldboot else p for p in objects]+[new[1]]
    def inputs():return pins,prior,objects
    base.inputs=inputs;base.overlay_sources=overlay
    # The original RP1 builder uses the captured compile invocation; add the
    # opt-in only in our in-memory copy, never alter the accepted manifest.
    prior=json.loads(json.dumps(prior))
    prior['compiles'][2]['command'][1:1]=['-DRPI5_PCIE_ID_TRIAL=1']
    try:
        report=base.build(output)
    finally:
        base.CORE,base.inputs,base.overlay_sources=oldcore,oldinputs,oldoverlay
    listing=(output/'kernel.symbols').read_text()
    names=base.full.symbols(listing)
    methods=('trialOwner','trialRead','trialOrder','trialAdmission','trialDisableMSI','runBoundedRP1Trial')
    required=['_rpi5_pcie_id_trial_start','_rpi5_pcie_released_windows_init','_rpi5_pcie_released_windows_check']
    required += [name for name in names if name.startswith('__ZN23BCM2712PCIePHYTransport') and '.' not in name
                 and any(method in name for method in methods)]
    if len(required)!=9:raise ValueError('ID provider/entry executable implementations missing')
    for name in required:
        if len(names.get(name,[]))!=1:raise ValueError('ID implementation ambiguous: '+name)
        address=names[name][0]
        if not any(s['initprot']&4 and s['vmaddr']<=address<s['vmaddr']+s['filesize']
                   for s in report['link']['macho']['segments']):
            raise ValueError('ID implementation not executable: '+name)
    def function(assembly,name):
        match=re.search(re.escape(name)+r':[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.S)
        if not match:raise ValueError('ID emitted function missing: '+name)
        return match[1]
    bootbody=function((prepared/'boot.s').read_text(),'_StartIOKitMatching')
    calls=re.findall(r'\tbl\t([^\n;]+)',bootbody)
    if [name.strip() for name in calls]!=['_rpi5_pcie_id_trial_start'] or re.search(r'\tret\b',bootbody):
        raise ValueError('Boot matching must invoke only terminal ID entry')
    emitted=(output/'transport.s').read_text()
    ownerbody=function(emitted,next(name for name in required if 'trialOwner' in name))
    admissionbody=function(emitted,next(name for name in required if 'trialAdmission' in name))
    msibody=function(emitted,next(name for name in required if 'trialDisableMSI' in name))
    entrybody=function(emitted,'_rpi5_pcie_id_trial_start')
    if '\tbl\t_ml_get_cpu_count' not in ownerbody or \
        '\tbl\t_rpi5_pcie_released_windows_check' not in admissionbody:
        raise ValueError('Actual CPU/released-provider implementation not called')
    if not re.search(r'\tdmb\tosh\n.*?\tstr\tw\d+, \[x\d+(?:, [^\]]+)?\].*?\tdsb\tsy',msibody,re.S):
        raise ValueError('Actual MSI disable has no ordered 32-bit hardware store')
    if '\twfi' not in entrybody or '\tbl\t_ml_set_interrupts_enabled' not in entrybody or re.search(r'\tret\b',entrybody):
        raise ValueError('ID entry must mask interrupts and terminally park')
    linkmap=(output/'kernel.map').read_text(errors='surrogateescape')
    if str(oldboot) in linkmap or str(new[0]) not in linkmap or str(new[1]) not in linkmap:
        raise ValueError('Actual boot/released constituent replacement not proven')
    report.update(profile='pcie-first-id-inbound-disabled-v1',boot_caller_added=True,
        bounded_discovery_lifecycle_provider_added=True,full_production_lifecycle_provider_added=False,
        all_ten_inbound_bar_decoders_disabled=True,builtin_msi_bar_disabled=True,
        caller_before_iokit_matching=True,one_cpu_required=True,always_terminal_park=True,
        firmware_recovery_evidence=evidence,prepared_compiles=rows,
        id_required_implementations=required,emitted_single_terminal_boot_call=True,
        emitted_runtime_cpu_and_released_checks=True,emitted_ordered_msi_disable=True,
        required_bootargs=['cpus=1'],forbidden_secondary_start=True,
        trial_scope='First controller/link/RP1 identification; no endpoint BAR writes, IRQ delivery, DMA or Ethernet')
    (output/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    result=build(parser.parse_args().output_dir)
    print(json.dumps({key:result[key] for key in ('kernel','kernel_bytes','kernel_sha256','profile')}))
