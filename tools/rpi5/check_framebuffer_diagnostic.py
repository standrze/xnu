#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Local source/actual-dependency/static-image checks, not physical admission."""
import argparse
import json
from pathlib import Path
import re
from . import build_framebuffer_diagnostic as b
def inspect(package,expected_manifest_sha256=None):
    package=Path(package).resolve();mp=package/'manifest.json'
    if package.parent!=b.ROOT/'build/rpi5' or not package.name.startswith('framebuffer-diagnostic-'):raise ValueError('Distinct observation package required')
    if expected_manifest_sha256 and b.sha(mp)!=expected_manifest_sha256:raise ValueError('Expected manifest differs')
    m=json.loads(mp.read_text());tag=m.get('tag','')
    if not re.fullmatch('[a-f0-9]{32}',tag):raise ValueError('Invalid package tag')
    t=b.tools();expected_commands=b.commands(package,tag,t)
    pins=m.get('inputs_sha256',{});generated=m.get('generated_sha256',{});headers={};scans={}
    expected_inputs={str(Path(p).resolve()) for p in (*b.SOURCES,*b.FILES,*b.imported(),*t.values())}
    # The checker may itself be newly imported after build. It is already a
    # required explicit source member; no input source is refreshed here.
    expected_outputs={str(package/'probe.elf'),str(package/'probe.bin')}
    for source in b.SOURCES:
        name=source.stem
        expected_outputs|={str(package/(name+s)) for s in ('.o','.scan.d','.actual.d')}
        if source.suffix=='.c':expected_outputs.add(str(package/(name+'.su')))
        scan=b.deps(package/(name+'.scan.d'));actual=b.deps(package/(name+'.actual.d'))
        if scan!=actual:raise ValueError('Actual header document differs')
        scans[name]=scan;expected_inputs.update(scan)
        for p in scan:headers[p]=pins.get(p)
    expected_outputs|={str(package/(label+'.log')) for label,_ in expected_commands}
    if set(pins)!=expected_inputs or set(generated)!=expected_outputs or any(not isinstance(v,str) or b.sha(p)!=v for p,v in {**pins,**generated}.items()):
        raise ValueError('Exact closure or source/output bytes differ')
    if m.get('headers_sha256')!=headers or m.get('source_scan')!=scans:raise ValueError('Actual header closure omitted or changed')
    commands=[dict(label=label,command=command,cwd=str(b.ROOT),returncode=0) for label,command in expected_commands]
    if m.get('commands')!=commands or m.get('tool_paths')!=t:raise ValueError('Exact command/tool identity differs')
    raw=(package/'probe.bin').read_bytes();loads=b.elf_inspector.inspect((package/'probe.elf').read_bytes(),raw,b.BASE)
    frames,budget=b.stack(package);dis=(package/'disassembly.log').read_text()
    symbols={row.split()[0]:row.split()[1:] for row in (package/'symbols.log').read_text().splitlines() if len(row.split())>=3}
    live_end=int(symbols['__probe_end'][1],16)
    source=(b.ROOT/'loader/rpi5/probe_framebuffer_diagnostic_main.c').read_text()
    checks=dict(exact_profile=m.get('profile')==b.PROFILE,entry_and_loads=m.get('entry')==loads['entry'] and m.get('loads')==loads['loads'],
        exact_image=m.get('image')==str(package/'probe.bin') and m.get('image_bytes')==len(raw) and m.get('image_sha256')==b.sha(package/'probe.bin'),
        actual_dependency_closure=True,source_outputs_tools_commands_pinned=True,stack_bound=m.get('stack_frames')==frames and m.get('stack_budget')==budget,
        no_false_hardware_claim=all(m.get(k) is False for k in b.FALSE_FIELDS),
        exact_output_budget=m.get('output_limit_bytes')==32768 and '#define OUTPUT_LIMIT 32768u' in source,
        one_active_watchdog_countdown=m.get('watchdog')==dict(already_active_required=True,countdown_write_once_seconds=15,software_output_seconds=8,reset_route_writes=False,reload_after_arm=False)
            and source.count('*(volatile uint32_t *)(PM+0x24)=UINT32_C(0x5a0f0000)')==1,
        no_cpu_on_call=not re.search(r'\bbl\s+[^\n]*<rpi5_psci_cpu_on>',dis),
        exact_tagged_runtime_markers=all(v in raw for v in [f'RPI5XNU:FBOBS:ENTRY TAG={tag} EL2 PRECHECK NO_XNU NO_CPU_ON ZERO_SERIAL_INPUT'.encode(),
            f'RPI5XNU:FBOBS:RESULT TAG={tag} RC='.encode(),f'RPI5XNU:FBOBS:STOP TAG={tag} NO_RELOAD DESTINATION_UNPROVEN'.encode(),
            b'OWNERSHIP_PROVEN=0 CACHE_CONTRACT_PROVEN=0',b'FRAMEBUFFER_ACCESSES=0 MAILBOX_REQUESTS=0 DRAW=0 MIRROR=0']),
        no_payload_symbols=not any(name in (package/'symbols.log').read_text() for name in ('embedded_kernel','embedded_init','rpi5_console_mirror_publish','rpi5_boot_video_encode')),
        early_uart_before_fdt=source.index('rpi5_uart_snapshot(UART,&uart)')<source.index('RPI5XNU:FBOBS:ENTRY TAG=')<source.index('check(1);if(size>1048576'),
        exact_precheck_stages=all(s in source for s in ('check(1);if(size>1048576','check(12);if((mpidr','check(13);if(rpi5_psci_query',
            'check(13+i);if(rpi5_psci_query','check(17);if(rpi5_uart_set_exact','check(18);if(!admitted','check(19);if(arm())')),
        terminal_rejection_report=all(s in raw for s in (b'RPI5XNU:FBOBS:CHECK STAGE=',b'RPI5XNU:FBOBS:REJECT STAGE=',
            b' NO_RELOAD OBSERVATION_INCOMPLETE',b' FIRMWARE_PRESERVED_CLOCK_UNVERIFIED')))
    if not all(checks.values()):raise ValueError('Observation package rejected: '+repr([k for k,v in checks.items() if not v]))
    return dict(profile=b.PROFILE,package=str(package),image=str(package/'probe.bin'),image_bytes=len(raw),image_sha256=b.sha(package/'probe.bin'),
        manifest_sha256=b.sha(mp),tag=tag,checks=checks,stack_budget=budget,watchdog=m['watchdog'],output_limit_bytes=32768,
        loader_live=dict(start=b.BASE,end=live_end),
        early_diagnostic_stages=19,early_uart_firmware_preserved=True,precheck_rejection_is_observation=False,
        physical_execution=False,installation_admitted=False,ownership_proven=False,scanout_cache_contract_proven=False)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path);p.add_argument('--manifest-sha256');a=p.parse_args()
    print(json.dumps(inspect(a.package,a.manifest_sha256),indent=2,sort_keys=True))
