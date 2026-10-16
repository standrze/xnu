#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Local source/actual-dependency/static-image checks, not physical admission."""
import argparse
import json
from pathlib import Path
import re
import struct
from . import build_display_compact_package as b
def same(left,right):
    """Type-sensitive JSON identity: bool/int/float are never interchangeable."""
    return json.dumps(left,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(right,sort_keys=True,separators=(',',':'),allow_nan=False)
def inspect(package,expected_manifest_sha256=None):
    package=Path(package).resolve();mp=package/'manifest.json'
    if package.parent!=b.ROOT/'build/rpi5' or not package.name.startswith('display-compact-'):raise ValueError('Distinct observation package required')
    if expected_manifest_sha256 and b.sha(mp)!=expected_manifest_sha256:raise ValueError('Expected manifest differs')
    m=json.loads(mp.read_text());tag=m.get('tag','')
    if not re.fullmatch('[a-f0-9]{32}',tag):raise ValueError('Invalid package tag')
    t=b.tools();expected_commands=b.commands(package,tag,t)
    pins=m.get('inputs_sha256',{});generated=m.get('generated_sha256',{});headers={};scans={}
    expected_inputs={str(Path(p).resolve()) for p in (*b.SOURCES,*b.FILES,*b.authority_inputs(),*b.imported(),*t.values())}
    # The checker may itself be newly imported after build. It is already a
    # required explicit source member; no input source is refreshed here.
    expected_outputs={str(package/'probe.elf'),str(package/'probe.bin')}
    for source in b.SOURCES:
        name=source.stem
        expected_outputs|={str(package/(name+s)) for s in ('.o','.scan.d','.actual.d')}
        if source.suffix=='.c' and source!=b.ROOT/'osfmk/console/iso_font.c':expected_outputs.add(str(package/(name+'.su')))
        scan=b.deps(package/(name+'.scan.d'));actual=b.deps(package/(name+'.actual.d'))
        if scan!=actual:raise ValueError('Actual header document differs')
        scans[name]=scan;expected_inputs.update(scan)
        for p in scan:headers[p]=pins.get(p)
    expected_outputs|={str(package/(label+'.log')) for label,_ in expected_commands}
    if set(pins)!=expected_inputs or set(generated)!=expected_outputs or any(not isinstance(v,str) or b.sha(p)!=v for p,v in {**pins,**generated}.items()):
        raise ValueError('Exact closure or source/output bytes differ')
    if not same(m.get('headers_sha256'),headers) or not same(m.get('source_scan'),scans):raise ValueError('Actual header closure omitted or changed')
    commands=[dict(label=label,command=command,cwd=str(b.ROOT),returncode=0) for label,command in expected_commands]
    if not same(m.get('commands'),commands) or not same(m.get('tool_paths'),t):raise ValueError('Exact command/tool identity differs')
    raw=(package/'probe.bin').read_bytes();loads=b.elf_inspector.inspect((package/'probe.elf').read_bytes(),raw,b.BASE)
    frames,budget=b.stack(package);dis=(package/'disassembly.log').read_text()
    symbols={row.split()[0]:row.split()[1:] for row in (package/'symbols.log').read_text().splitlines() if len(row.split())>=3}
    live_end=int(symbols['__probe_end'][1],16)
    source=(b.ROOT/'loader/rpi5/probe_display_compact_main.c').read_text()
    def words(name,expected):
        row=symbols[name];offset=int(row[1],16)-b.BASE;length=int(row[2],16)
        return length==len(expected)*4 and struct.unpack_from('<'+'I'*len(expected),raw,offset)==expected
    storage=int(symbols['rpi5_display_allocate_pages'][1],16)
    storage_bytes=int(symbols['rpi5_display_allocate_pages'][2],16)
    # Reassemble only the immutable entry/architecture sources to compare real
    # instruction bytes? No: checker is read-only and never compiles. Exact
    # leaf instruction encoding plus linked transition disassembly below.
    leaves={
        'rpi5_display_compact_store':(0xb9000001,0xd65f03c0),
        'rpi5_display_compact_barrier':(0xd5033f9f,0xd65f03c0),
        'rpi5_display_query_identity':(0xd65f03c0,),
        'rpi5_display_query_registers':(0xd5384241,0xd5381002,0xa9000801,0xd53b4221,0xd53800a2,0xa9010801,0xd53be001,0xd53b0022,0xa9020801,0xd5380001,0xf9001801,0xd65f03c0),
        'rpi5_display_query_counter':(0xd5033fdf,0xd53be040,0xd65f03c0),
        'rpi5_display_query_read':(0xd5033f9f,0xb9400000,0xd5033f9f,0xd65f03c0),
        'rpi5_display_query_write':(0xd5033f9f,0xb9000001,0xd5033f9f,0xd65f03c0),
        'rpi5_display_query_clean':(0xd5033f9f,0xd2800801,0xd50b7a20,0x91010000,0xf1000421,0x54ffffa1,0xd5033f9f,0xd65f03c0),
        'rpi5_display_query_invalidate':(0xd5033f9f,0xd2800801,0xd5087620,0x91010000,0xf1000421,0x54ffffa1,0xd5033f9f,0xd65f03c0)}
    # The disassembly file is regenerated from the actual checked ELF, not
    # trusted merely because its saved hash appears in the manifest.
    actual_dis=b.subprocess.check_output([t['objdump'],'-d',str(package/'probe.elf')],text=True,timeout=30)
    if actual_dis!=dis:raise ValueError('Saved disassembly differs from actual ELF')
    entry=dis[dis.index('<probe_enter_el1>:'):dis.index('<probe_el1_entry>:')]
    transition=[r'mov\s+x9, #0x80000000',r'msr\s+HCR_EL2, x9',r'msr\s+VTTBR_EL2, xzr',
        r'mov\s+x9, #0x800(?![0-9a-f])',r'movk\s+x9, #0x30d0, lsl #16',r'msr\s+SCTLR_EL1, x9']
    positions=[]
    for pattern in transition:
        match=re.search(pattern,entry,re.I);positions.append(match.start() if match else -1)
    transition_words=(0xd2b00009,0xd51c1109,0xd5033fdf,0xd2800069,0xd51ce109,0xd51ce07f,
        0xd2867fe9,0xd51c1149,0xd51c113f,0xd51c117f,0xd51c211f,0xd2810009,0xf2a61a09,0xd5181009,
        0xd518105f,0xd518e11f,0xd51be33f,0xd51be23f,0xd0000009,0x91000129,0xd518c009,0xd51c4115,
        0xd51c4034,0xd28078a9,0xd51c4009,0xd5033f9f,0xd5033fdf,0xd69f03e0)
    transition_offset=int(symbols['probe_enter_el1'][1],16)-b.BASE
    transition_end=int(symbols['probe_el1_entry'][1],16)-b.BASE
    font_source=(b.ROOT/'osfmk/console/iso_font.c').read_text()
    font_body=font_source.split('unsigned char iso_font[256 * 16] = {',1)[1].split('};',1)[0]
    font_bytes=bytes(int(v,16) for v in re.findall(r'0x([0-9A-Fa-f]{2})\b',font_body))
    if len(font_bytes)!=4096:raise ValueError('Original Apple font shape changed')
    font_offset=int(symbols['iso_font'][1],16)-b.BASE
    adapter_source=(b.ROOT/'loader/rpi5/display_compact_adapter.c').read_text()
    patch_source=(b.ROOT/'loader/rpi5/display_compact_patch.c').read_text()
    checks=dict(exact_profile=m.get('profile')==b.PROFILE,entry_and_loads=same(m.get('entry'),loads['entry']) and same(m.get('loads'),loads['loads']),
        exact_image=m.get('image')==str(package/'probe.bin') and same(m.get('image_bytes'),len(raw)) and m.get('image_sha256')==b.sha(package/'probe.bin'),
        actual_dependency_closure=True,source_outputs_tools_commands_pinned=True,stack_bound=same(m.get('stack_frames'),frames) and same(m.get('stack_budget'),budget),
        no_false_hardware_claim=all(m.get(k) is False for k in b.FALSE_FIELDS),
        exact_allocation_contract=same(m.get('allocation_contract'),b.contract()) and m.get('mailbox_requests_authored') is True and
            m.get('allocation_contract_scope')=='frozen allocator component only; visible_contract separately authorizes store phase',
        exact_visible_contract=same(m.get('visible_contract'),b.visible_contract()) and m.get('framebuffer_stores_authored') is True,
        unchanged_apple_font=font_bytes==raw[font_offset:font_offset+4096] and int(symbols['iso_font'][2],16)==4096,
        single_same_boot_allocator_and_store_path=adapter_source.count('rpi5_display_allocate_run(')==1 and
            adapter_source.count('rpi5_display_compact_store(')==1 and source.count('rpi5_display_compact_run(')==1 and
            not any(name in adapter_source for name in ('rpi5_display_query_read(','rpi5_display_query_write(','rpi5_display_query_clean(','rpi5_psci_cpu_on(')),
        exact_bounded_store_loops='for(unsigned y=0;y<8;y++)' in patch_source and 'for(unsigned x=0;x<96;x++)' in patch_source,
        exact_output_budget=same(m.get('output_limit_bytes'),32768) and '#define OUTPUT_LIMIT 32768u' in source,
        one_active_watchdog_countdown=same(m.get('watchdog'),dict(already_active_required=True,countdown_write_once_seconds=15,software_output_seconds=8,reset_route_writes=False,reload_after_arm=False))
            and source.count('*(volatile uint32_t *)(PM+0x24)=UINT32_C(0x5a0f0000)')==1,
        no_cpu_on_call=not re.search(r'\bbl\s+[^\n]*<rpi5_psci_cpu_on>',dis),
        actual_tagged_markers=all(v in raw for v in [f'RPI5XNU:DISPLAYCOMPACT:ENTRY TAG={tag} EL2 PRECHECK NO_XNU NO_CPU_ON ZERO_SERIAL_INPUT'.encode(),
            f'RPI5XNU:DISPLAYCOMPACT:RESULT TAG={tag} RC='.encode(),f'RPI5XNU:DISPLAYCOMPACT:STOP TAG={tag} NO_RELOAD RETAIN_UNTIL_RESET'.encode(),
            b'FIXED_PROFILE=1 MAX_TX=4 ALLOCATE_MAX=1 RELEASE=0 DRAW=1 VISUAL_CONFIRMATION_REQUIRED NO_HANDOFF_AUTHORITY']),
        no_payload_symbols=not any(name in symbols for name in ('embedded_kernel','embedded_init','rpi5_console_mirror_publish','rpi5_boot_video_encode')),
        actual_stack_extent=int(symbols['__stack_top'][1],16)-int(symbols['__bss_end'][1],16)==32768,
        exact_architecture_leaves=all(words(name,expected) for name,expected in leaves.items()),
        actual_identity_el2_el1_transition=all(p>=0 for p in positions) and positions==sorted(positions) and
            raw[transition_offset:transition_end]==struct.pack('<28I',*transition_words),
        isolated_linked_pages=storage%4096==0 and storage_bytes==16384 and b.BASE<=storage<storage+storage_bytes<=live_end<=1<<32 and symbols['rpi5_display_allocate_pages'][0].lower()=='b',
        exact_precheck_stages=all(s in source for s in ('check(1);if(size>1048576','check(12);if((mpidr','check(13);if(rpi5_psci_query',
            'check(13+i);if(rpi5_psci_query','check(17);if(rpi5_uart_set_exact','check(18);if(!admitted','check(19);if(arm())')))
    if not all(checks.values()):raise ValueError('GET query package rejected: '+repr([k for k,v in checks.items() if not v]))
    return dict(profile=b.PROFILE,package=str(package),image=str(package/'probe.bin'),image_bytes=len(raw),image_sha256=b.sha(package/'probe.bin'),
        manifest_sha256=b.sha(mp),tag=tag,checks=checks,stack_budget=budget,watchdog=m['watchdog'],output_limit_bytes=32768,
        loader_live=dict(start=b.BASE,end=live_end),allocation_storage=dict(start=storage,bytes=storage_bytes),allocation_contract=b.contract(),
        allocation_contract_scope='frozen allocator component only; visible_contract separately authorizes store phase',visible_contract=b.visible_contract(),framebuffer_stores_authored=True,
        required_normal_firmware_sha256=b.FW_SHA,early_diagnostic_stages=19,
        physical_execution=False,installation_admitted=False,ownership_proven=False,scanout_cache_contract_proven=False,
        mailbox_allocate_transport_authored=True,framebuffer_access=False,allocation=False,drawing=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path);p.add_argument('--manifest-sha256');a=p.parse_args()
    print(json.dumps(inspect(a.package,a.manifest_sha256),indent=2,sort_keys=True))



