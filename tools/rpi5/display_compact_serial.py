# SPDX-License-Identifier: BSD-2-Clause
"""Strict allocation-plus-store evidence; serial completion is not scanout proof."""
import json
import re
from . import display_allocate_zero_serial as allocation
PROFILE='pi5-display-compact-standalone-v1'
PREFIX='RPI5XNU:DISPLAYCOMPACT:'
CONTRACT=dict(x=16,y=16,width=96,height=8,stride=7680,stores=768,store_bits=32,
    framebuffer_reads=0,draw_deadline_us=500000,global_software_deadline_required=True,
    zero_opaque_alpha_halves=True,pixel_layout='PI5 glyphs24px + RGB strips3x8px in each48px half',font_row_step=2,font='unchanged Apple osfmk/console/iso_font.c',
    same_boot_allocator_required=True,fresh_fdt_required=True,mmu_cache_off_required=True,
    no_mapping=True,no_retry=True,no_release=True,retain_full_allocation_until_reset=True,
    physical_visual_confirmation_required=True,xnu_handoff=False)
def same(a,b):return json.dumps(a,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(b,sort_keys=True,separators=(',',':'),allow_nan=False)
def inspect(data,report):
    try:return _inspect(data,report)
    except (IndexError,KeyError,TypeError) as e:raise ValueError('Incomplete visible records/report') from e
def _inspect(data,report):
    if not isinstance(data,bytes) or len(data)>4*1024*1024 or report.get('profile')!=PROFILE or not same(report.get('visible_contract'),CONTRACT):raise ValueError('Exact bounded visible report required')
    normalized=data.replace(b'\r\n',b'\n')
    raw=[row for row in normalized.split(b'\n') if PREFIX.encode() in row]
    try:rows=[row.decode('ascii') for row in raw]
    except UnicodeError as e:raise ValueError('Non-ASCII visible record') from e
    if not rows:raise ValueError('Missing visible records')
    start=normalized.find(raw[0]);end=normalized.find(raw[-1],start)+len(raw[-1])
    if normalized[start:end]!=b'\n'.join(raw):raise ValueError('Interleaved visible records')
    previous=report|{'profile':allocation.PROFILE}
    if rows[-1].startswith(PREFIX+'REJECT '):
        result=allocation.inspect(data.replace(PREFIX.encode(),allocation.PREFIX.encode()),previous)
        return result|dict(visible_store_pass=False,drawing=False,framebuffer_memory_access=False,
            physical_visibility_proven=False,visual_confirmation_required=True)
    draw_rows=[row for row in rows if row.startswith(PREFIX+'DRAW ')]
    cpu_rows=[row for row in rows if row.startswith(PREFIX+'EL1 ')]
    if len(cpu_rows)!=1 or not cpu_rows[0].endswith(' CPU_MMU_CACHE_OFF NO_XNU NO_CPU_ON BOUNDED_FRAMEBUFFER_STORES'):
        raise ValueError('Exact visible CPU/access profile required')
    if len(draw_rows)!=1 or rows[-3]!=draw_rows[0] or not rows[-4].endswith(' ALLOCATION_METADATA_NO_HANDOFF') or not rows[-2].endswith(' FIXED_PROFILE=1 MAX_TX=4 ALLOCATE_MAX=1 RELEASE=0 DRAW=1 VISUAL_CONFIRMATION_REQUIRED NO_HANDOFF_AUTHORITY'):
        raise ValueError('Exact visible phase and result ordering required')
    names=['RC','FIRST','LAST','ATTEMPTED','COMPLETED','ROWS','GUARDS','TIMES','BARRIERS','USED','START_US','LAST_US','DEADLINE_US']
    match=re.fullmatch(re.escape(PREFIX+'DRAW')+''.join(' '+name+'=('+allocation.HEX+')' for name in names)+' NO_FB_READ RETAIN_UNTIL_RESET VISUAL_CONFIRMATION_REQUIRED',draw_rows[0])
    if not match:raise ValueError('Malformed bounded drawing record')
    draw=dict(zip(names,(int(value,16) for value in match.groups())));rc=allocation.signed(draw['RC'])
    projected=normalized.replace((draw_rows[0]+'\n').encode(),b'',1).replace(PREFIX.encode(),allocation.PREFIX.encode())
    projected=projected.replace(b'CPU_MMU_CACHE_OFF NO_XNU NO_CPU_ON BOUNDED_FRAMEBUFFER_STORES',b'CPU_MMU_CACHE_OFF NO_XNU NO_CPU_ON NO_FRAMEBUFFER_ACCESS')
    projected=projected.replace(b' ALLOCATION_METADATA_NO_HANDOFF',b' NO_MAPPING_NO_DRAW')
    projected=projected.replace(b'RELEASE=0 DRAW=1 VISUAL_CONFIRMATION_REQUIRED NO_HANDOFF_AUTHORITY',b'RELEASE=0 DRAW=0 NO_HANDOFF_AUTHORITY')
    result=allocation.inspect(projected,previous)
    if (draw['USED']>1 or draw['ATTEMPTED']>768 or draw['COMPLETED']>draw['ATTEMPTED'] or draw['ROWS']>8 or
        draw['GUARDS']>17 or draw['TIMES']>785 or draw['BARRIERS']>8 or draw['ROWS']>draw['BARRIERS'] or
        draw['ROWS']*96>draw['COMPLETED'] or rc not in (0,-1,-2,-3,-4)):raise ValueError('Impossible/unbounded drawing progress')
    if not result['allocation_trial_pass']:
        if rc!=-2 or any(draw[k] for k in names if k!='RC'):raise ValueError('Failed allocation must not admit drawing')
    elif rc==0:
        base=result['candidate']['CPU']
        if (draw['USED']!=1 or draw['ATTEMPTED']!=768 or draw['COMPLETED']!=768 or draw['ROWS']!=8 or
            draw['GUARDS']!=17 or draw['TIMES']!=785 or draw['BARRIERS']!=8 or
            draw['FIRST']!=base+16*7680+16*4 or draw['LAST']!=base+23*7680+111*4 or
            not draw['START_US']<=draw['LAST_US']<draw['DEADLINE_US'] or draw['DEADLINE_US']-draw['START_US']!=500000):raise ValueError('Complete exact store phase required')
    else:
        if rc==-2:raise ValueError('Successful allocation cannot skip drawing without failure')
        base=result['candidate']['CPU']
        if draw['USED']:
            if draw['FIRST'] not in (0,base+16*7680+16*4) or draw['LAST'] not in (0,base+23*7680+111*4):raise ValueError('Partial drawing address differs')
        elif any(draw[k] for k in names if k!='RC'):raise ValueError('Unadmitted drawing has side effects')
    passed=result['allocation_trial_pass'] and rc==0
    return result|dict(diagnostic_pass=passed,visible_store_pass=passed,draw_result_rc=rc,draw=draw,
        framebuffer_writes_attempted=draw['ATTEMPTED'],framebuffer_reads=0,physical_visibility_proven=False,
        drawing=draw['ATTEMPTED']>0,framebuffer_memory_access=draw['ATTEMPTED']>0,
        access_evidence_scope='Store attempts reported by the trial; independent visibility unproven',
        allocation_component_drawing=False,allocation_component_framebuffer_memory_access=False,
        visual_confirmation_required=True,receiver_path_qualified=False)

