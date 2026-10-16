#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Independent actual-target stack measurements for the CPU-owned batch path.

Not a board admission or a whole-kernel stack proof. Recompile exact reused
owners with stack/dependency outputs only, then compare all executable sections
byte-for-byte. Never modifies the inherited objects or the candidate package.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from tools.rpi5 import build_display_xnu_console as display
from tools.rpi5.audit_reservation_kernel_stack import frames

ROOT=display.ROOT
BASE=ROOT/'build/rpi5/display-xnu-console-5cd94fg_'
DATABASE=display.OBJ/'compile_commands.json'
REUSED=(
 ('decode','pcie-gem-identify-kernel-20261013-v2','rp1_decode_cycle.c'),
 ('forward','pcie-root-forward-kernel-20261013-v1','pcie_root_forward.c'),
 ('fw','pcie-fw-client-kernel-20261013-final','pcie_fw_client.c'),
 ('lease','pcie-watchdog-owner-20261012-final-v2','pcie_watchdog_lease.c'),
 ('irq','pcie-irq-kernel-20261012-final','pcie_irq_mask.c'),
 ('fiq','pcie-owner-trace-kernel-20261013-v1','pe_fiq.c'),
 ('released','pcie-gem-capabilities-kernel-20261013-v1','pcie_released_windows.c'),
 ('windows','apple-pci-resources-20261012-final','BCM2712PCIWindowCore.cpp'),
 ('pmap','display-xnu-console-5cd94fg_','pmap.c'),
)
STANDARD=('startup.c','pe_init.c','machine_routines_common.c','rtclock.c',
          'IOService.cpp','IOBufferMemoryDescriptor.cpp','IOMemoryDescriptor.cpp',
          'IOLocks.cpp','locks.c','lock_mtx.c','clock.c','IOLib.cpp',
          'kalloc.c','zalloc.c','sched_prim.c','waitq.c','thread.c','turnstile.c',
          'machine_routines.c')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def code_sections(path):
    """Compare every instruction section; retain segment identity and order."""
    raw=Path(path).read_bytes()
    if len(raw)<32 or struct.unpack_from('<I',raw)[0]!=0xfeedfacf:
        raise ValueError('Expected real Mach-O64 object')
    offset=32;found=[]
    for _ in range(struct.unpack_from('<I',raw,16)[0]):
        cmd,size=struct.unpack_from('<II',raw,offset)
        if size<8 or offset+size>len(raw):raise ValueError('Invalid command')
        if cmd==0x19:
            for i in range(struct.unpack_from('<I',raw,offset+64)[0]):
                at=offset+72+80*i
                if at+80>offset+size:raise ValueError('Invalid section')
                flags=struct.unpack_from('<I',raw,at+64)[0]
                if flags&0x80000400:
                    segment=raw[at+16:at+32].split(b'\0')[0]
                    section=raw[at:at+16].split(b'\0')[0]
                    count,where=struct.unpack_from('<QI',raw,at+40)
                    if where+count>len(raw):raise ValueError('Invalid instruction extent')
                    found.append((segment,section,raw[where:where+count]))
        offset+=size
    if not found:raise ValueError('No instruction sections')
    return found

def command_rows(manifest,source):
    rows={}
    for key in ('commands','results','compiles','prepared_compiles'):
        for row in manifest.get(key,[]):
            cmd=row.get('command',[])
            if '-c' in cmd and any(str(a).endswith('/'+source) for a in cmd):
                rows[tuple(cmd)]=row
    if len(rows)!=1:raise ValueError('Ambiguous reused compile: '+source)
    return next(iter(rows.values()))

def recipes():
    result={};pins={str(DATABASE):sha(DATABASE)}
    for name,base,source in REUSED:
        path=ROOT/'build/rpi5'/base/'manifest.json';pins[str(path)]=sha(path)
        row=command_rows(json.loads(path.read_bytes()),source)
        cmd=row['command'];original=Path(cmd[cmd.index('-o')+1])
        cwd=Path(row.get('cwd',display.OBJ/'pexpert/DEVELOPMENT'))
        if name=='pmap':cwd=display.OBJ/'osfmk/DEVELOPMENT'
        if name=='windows':cwd=display.OBJ/'iokit/DEVELOPMENT'
        result[name]=(cmd,cwd,original)
    db=json.loads(DATABASE.read_bytes())
    for source in STANDARD:
        rows=[r for r in db if r['file'].endswith('/'+source)]
        if len(rows)!=1:raise ValueError('Ambiguous standard owner: '+source)
        row=rows[0];cwd=Path(row['directory'])
        result[source.split('.')[0]]=(row['arguments'],cwd,cwd/row['output'])
    # Exact retained compile, not an approximate source substitution.
    manifest=ROOT/'build/rpi5/pcie-gem-capabilities-kernel-20261013-v1/manifest.json'
    pins[str(manifest)]=sha(manifest)
    row=command_rows(json.loads(manifest.read_bytes()),'IOStartIOKit.cpp')
    cmd=row['command'];result['IOStartIOKit']=(cmd,display.OBJ/'iokit/DEVELOPMENT',Path(cmd[cmd.index('-o')+1]))
    return result,pins

def measure(output):
    output=Path(output).resolve()
    if output.parent!=ROOT/'build/rpi5' or output.exists():raise ValueError('Distinct new receipt path required')
    output.mkdir();recipe,pins=recipes();pins[str(Path(__file__).resolve())]=sha(__file__)
    def one(item):
        name,(command,cwd,original)=item
        obj=output/(name+'.o');dep=output/(name+'.d');cmd=list(command)
        cmd[cmd.index('-o')+1]=str(obj)
        if '-MF' in cmd:cmd[cmd.index('-MF')+1]=str(dep)
        else:cmd+=['-MD','-MF',str(dep)]
        cmd+=['-fstack-usage']
        result=subprocess.run(cmd,cwd=cwd,capture_output=True,timeout=60)
        log=output/(name+'.log');log.write_bytes(result.stdout+result.stderr)
        if result.returncode:raise ValueError('Compile failed: '+str(log))
        if code_sections(obj)!=code_sections(original):raise ValueError('Actual code changed: '+name)
        local={str(original):sha(original)}
        for p in display.dependencies(dep,cwd):local[str(p)]=sha(p)
        return name,dict(command=cmd,cwd=str(cwd),original=str(original),
                         original_sha256=sha(original),code_unchanged=True,
                         frames=frames(output/(name+'.su'))),local
    rows={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for name,row,local in pool.map(one,recipe.items()):rows[name]=row;pins.update(local)
    for path,digest in pins.items():
        if sha(path)!=digest:raise ValueError('Measurement input drift: '+path)
    report=dict(profile='pi5-gem-batch-unchanged-owner-stack-measurements-v1',
                hardware=False,whole_kernel_stack_proven=False,owners=rows,inputs_sha256=pins,
                generated_sha256={str(p):sha(p) for p in output.iterdir() if p.is_file()})
    (output/'measurements.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    return report

def owned_bounds(package,measurements,early_audit):
    """Finite successful OWNED paths; do not invent an OS-helper allowance.

    General allocator, contended arbitration/scheduling, panic and IRQ work
    are unchanged kernel facilities, not recursively proved by this audit.
    Their complete maximum is deliberately not added as a fictional constant.
    """
    package=Path(package).resolve();measurements=Path(measurements).resolve()
    m=json.loads((package/'manifest.json').read_bytes())
    if m['profile']!='bcm2712-gem-real-cpu-owned-batch-trial-v1':raise ValueError('Wrong real-caller profile')
    measured=json.loads(measurements.read_bytes());early=json.loads(Path(early_audit).read_bytes())
    if measured['profile']!='pi5-gem-batch-unchanged-owner-stack-measurements-v1':raise ValueError('Wrong measurement profile')
    for key in ('inputs_sha256','generated_sha256'):
        for path,pin in measured[key].items():
            if sha(path)!=pin:raise ValueError('Measured owner/receipt drift')
    tables={name:row['frames'] for name,row in measured['owners'].items()}
    for name in ('transport','provider','arm_init','kernel-rpi5_gem_ring_batch','kernel-rpi5_gem_dma_route',
                 'kernel-rpi5_reservation_kernel','kernel-reservation_record','kernel-ranges','kernel-reservations'):
        path=package/(name+'.su')
        if m['generated_sha256'].get(str(path))!=sha(path):raise ValueError('Candidate stack closure differs')
        tables[name]=frames(path)
    filelist=(package/'kernel.filelist').read_text().splitlines()
    for name in ('decode','forward','fw','lease','irq','fiq','released','IOStartIOKit','startup','pe_init','IOService',
                 'IOBufferMemoryDescriptor','IOMemoryDescriptor','machine_routines','machine_routines_common','rtclock','clock','pmap'):
        if filelist.count(measured['owners'][name]['original'])!=1:raise ValueError('Measured reused object not actual linked owner: '+name)
    aggregate=ROOT/'build/rpi5/apple-pci-resources-20261012-final/apple-bcm2712-pci-resources.o'
    producer=json.loads((aggregate.parent/'manifest.json').read_bytes())
    if filelist.count(str(aggregate))!=1 or sha(aggregate)!=producer['link']['object_sha256'] or producer['link']['command'].count(measured['owners']['windows']['original'])!=1:
        raise ValueError('Exact original window core not actual aggregate member')
    def frame(table,name):
        row=tables[table][name]
        if row['kind']!='static':raise ValueError('Unbounded owned successful frame: '+name)
        return row['bytes']
    def match(table,fragment):
        names=[n for n in tables[table] if fragment in n and '.cold.' not in n and not n.startswith('_ZZ')]
        if len(names)!=1:raise ValueError('Ambiguous exact method: '+fragment)
        return frame(table,names[0])
    t=lambda fragment:match('transport',fragment)
    p=lambda fragment:match('provider',fragment)
    bootstrap=frame('startup','kernel_bootstrap_thread')+frame('pe_init','PE_lockdown_iokit')+frame('IOStartIOKit','StartIOKitMatching')
    preparation=bootstrap+frame('transport','rpi5_pcie_id_trial_start')+t('20prepareCPUOwnedRingsEv')+p('7prepareEv')
    parent=bootstrap+frame('transport','rpi5_pcie_id_trial_start')+t('18runBoundedRP1Trial')+t('26runControllerAndObserveRP1')
    stage=parent+frame('decode','rpi5_rp1_decode_run')+t('11gemIdentifyEP')+frame('forward','rpi5_root_forward_run')+t('20gemIdentifyUnderRoot')+t('26stagePreparedCPUOwnedRings')+p('13stageCPUOwned')
    core=stage+frame('kernel-rpi5_gem_ring_batch','rpi5_gem_ring_batch')+frame('kernel-rpi5_gem_ring_batch','operation')+frame('kernel-rpi5_gem_ring_batch','guard')+p('11ringCurrent')
    # Overcount every successful project FW/IRQ/PM subframe rather than only
    # one of the sequential callbacks. No recursion: real firmware checks
    # call IRQ checks; released-window callbacks do not call transport guard.
    fw=0
    for name in ('pe_rpi5_pcie_fw_check','rpi5_pcie_fw_owner','rpi5_pcie_fw_rpc','pe_rpi5_pcie_irq_check',
                 'rpi5_pcie_irq_owner','rpi5_pcie_irq_read','pe_rpi5_watchdog_check_pcie','pe_rpi5_pcie_owner_trace'):
        fw+=frame('fiq',name)
    fw+=frame('fw','rpi5_pcie_fw_client_check')+frame('lease','rpi5_pcie_watchdog_check')
    fw+=sum(frame('irq',name) for name in ('run','read32','snapshot','owner'))
    fresh=core+t('14dmaRingCurrent')+t('5guardEv')
    released=sum(frame('released',name) for name in ('rpi5_pcie_released_windows_check','snapshot','read32'))
    window=fresh+t('14trialAdmission')+released+t('9trialRead')+t('10trialOwner')
    # Known genuine wired/kUnmapped getPhysicalSegment branch performs only
    # the existing page-list walk; mapped/system-mapper/prepare branches are
    # not requested by this provider. Include both complete compiled frames.
    mapping=core+p('7mappingEv')+frame('IOMemoryDescriptor','_ZN25IOGeneralMemoryDescriptor18getPhysicalSegmentEyPyj')+frame('IOMemoryDescriptor','_ZNK25IOGeneralMemoryDescriptor19dmaCommandOperationEjPvj')
    # Private-FDT semantic validation occurs before allocator/owner acquisition,
    # not nested under the3.3KiB execution core or later window qualification.
    rec='kernel-reservation_record'
    fdt=early['frames']['fdt']
    fdt_names=('rpi5_fdt_memory','rpi5_fdt_reservation_plan','rpi5_fdt_initrd','rpi5_fdt_property','rpi5_fdt_structure','rpi5_fdt_layout','be64','value_equal')
    fdt_bound=sum(fdt[name]['bytes'] for name in fdt_names)
    source=frame(rec,'rpi5_reservation_record_source')+fdt_bound
    resolver=frame('kernel-reservations','rpi5_resolve_reservations')+sum(frame('kernel-ranges',name) for name in ('rpi5_ranges_subtract','rpi5_ranges_find','rpi5_ranges_validate_live'))
    validate=frame(rec,'rpi5_reservation_record_validate_fdt')+max(source,resolver,frame(rec,'rpi5_reservation_record_fixed'),frame(rec,'rpi5_reservation_record_valid'))
    # Count both original16B copy/zero leaves (cannot nest) from exact prior
    # assembly inspection, even though the compiler often inlines these.
    copies=early['actual_assembly_memory_frames_overcounted_bytes']
    route=p('5routeEP')+max(frame('kernel-rpi5_reservation_kernel','rpi5_reservation_kernel_buffer')+frame(rec,'rpi5_reservation_record_valid'),
        frame('kernel-rpi5_gem_dma_route','rpi5_gem_dma_route')+frame('windows','rpi5_pcie_windows_plan'))
    qualification=parent+t('5guardEv')+t('14trialAdmission')+p('7qualifyEP')+p('8disabledEP')+route
    paths=dict(before_owner_private_fdt_validation=preparation+validate+copies,
        batch_fresh_project_firmware_guard=fresh+fw+copies,
        batch_released_window_to_standard_isOpen=window+copies,
        batch_wired_unmapped_physical_segment=mapping+copies,
        before_execution_route_qualification=qualification+copies)
    return dict(profile='pi5-gem-batch-successful-owned-stack-components-v1',
        package_manifest_sha256=sha(package/'manifest.json'),measurement_sha256=sha(measurements),
        early_audit_sha256=sha(early_audit),successful_owned_paths_bytes=paths,
        maximum_owned_path_bytes=max(paths.values()),kernel_stack_bytes=16384,
        minimum_remaining_before_unclosed_standard_helpers=16384-max(paths.values()),
        core_frame_bytes=frame('kernel-rpi5_gem_ring_batch','rpi5_gem_ring_batch'),
        whole_kernel_stack_proven=False,panic_irq_scheduler_stack_proven=False,
        standard_kernel_assumptions=[
            'Existing standard-kernel calls retain their original ABI/stack behavior; no arbitrary allocator/scheduler/cold graph bound is claimed.',
            'isOpen arbitration may allocate if its global freequeue is empty, or enter generic contended lock/wakeup paths; their whole maximum is not measured here.',
            'Genuine retained wired IOBuffer uses kIOMemoryMapperNone; successful physical-segment walk does not invoke system-mapper preparation.',
            'Sequential preparation, route qualification and batch execution frames do not coexist; no fresh owner check is removed.',
            '16KiB DEVELOPMENT kernel thread stack, no KASAN/DEBUG or multiplier expansion; asynchronous IRQ uses its separate original kernel mechanism.'],
        hardware=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--package',type=Path);p.add_argument('--measurements',type=Path);p.add_argument('--early-audit',type=Path)
    args=p.parse_args()
    if args.package:
        if not args.measurements or not args.early_audit or args.output.exists():raise ValueError('Distinct report and both actual receipts required')
        r=owned_bounds(args.package,args.measurements,args.early_audit)
        args.output.write_text(json.dumps(r,sort_keys=True,indent=2)+'\n')
        print(json.dumps(dict(receipt_sha256=sha(args.output),paths=r['successful_owned_paths_bytes'],remaining=r['minimum_remaining_before_unclosed_standard_helpers'])))
    else:
        r=measure(args.output)
        print(json.dumps(dict(receipt_sha256=sha(args.output/'measurements.json'),owners=len(r['owners']))))
