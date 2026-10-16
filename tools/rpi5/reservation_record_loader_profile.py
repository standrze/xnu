# SPDX-License-Identifier: BSD-2-Clause
"""Distinct same-boot reservation handoff; pure exact-boundary overlays only.

The property exists before measurement. Its only commit is after actual seed
consumption/erasure, before final ADT encoding. No secret-derived digest exists.
This preserves original firmware FDT in place, and never changes its RAM nodes.
"""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[2]
PARENT_LOADER_SHA256='8439db4535e56f55f32205c8819c435efadeb1064f60ad0c0e04357531d1b0d4'
PARENT_SEED_SHA256='977aa5d74a0525194906a061da59027f3cebbb5eb1e61b9a791660cc13f9fc13'
def once(text,old,new):
    if text.count(old)!=1: raise ValueError('Reservation overlay boundary changed: '+old[:80])
    return text.replace(old,new)
def loader(text):
    if hashlib.sha256(text.encode()).hexdigest()!=PARENT_LOADER_SHA256:raise ValueError('Exact accepted HDMI loader differs')
    text=once(text,'#include "display_xnu_handoff.h"','#include "display_xnu_handoff.h"\n#include "reservation_record_tree.h"')
    anchor='static int board_tree_diagnostic('
    block='''/* Actual same-boot planner snapshot. No seed or pre-erasure digest. */
static struct rpi5_reservation_record_tree reservation_tree;
static struct rpi5_resolved_reservations reservation_actual;
static struct rpi5_handoff_input reservation_input;
static struct rpi5_handoff_plan reservation_handoff;
static uintptr_t reservation_fdt_pa;
static size_t reservation_fdt_bytes;
static unsigned reservation_pending;
int rpi5_reservation_record_finalize(struct rpi5_board_tree *tree)
{
    struct rpi5_fdt_property seed;
    struct rpi5_reservation_record record;
    uint64_t counter;
    if (reservation_pending!=1) return -1;
    reservation_pending=2; /* Any failure consumes this attempt. */
    if (rpi5_firmware_seed_select((const void *)reservation_fdt_pa,reservation_fdt_bytes,&seed) || seed.length!=64) return -1;
    for (unsigned i=0;i<64;i++) if (((volatile const uint8_t *)reservation_fdt_pa)[seed.offset+i]) return -1;
    __asm__ volatile("mrs %0,cntvct_el0":"=r"(counter));
    if (rpi5_reservation_record_make((const void *)reservation_fdt_pa,reservation_fdt_bytes,
        reservation_fdt_pa,(struct rpi5_range){(uintptr_t)__probe_start,(uintptr_t)__probe_end},
        &reservation_actual,&reservation_input,&reservation_handoff,counter,&record) ||
        rpi5_reservation_record_tree_commit(tree,&record,&reservation_tree)) return -1;
    reservation_pending=3;
    return 0;
}

'''
    text=once(text,anchor,block+anchor)
    anchor='    if (rpi5_display_xnu_tree_reserve(&tree,&display_tree)) return 0;'
    text=once(text,anchor,anchor+'\n    if (reservation_pending || rpi5_reservation_record_tree_reserve(&tree,&reservation_tree)) return 0;')
    old='''        &handoff,&display_handoff,&display_record) ||
        rpi5_display_xnu_tree_commit(&tree,&display_record,&display_tree)) return 0;
    handoff=display_handoff;'''
    new='''        &handoff,&display_handoff,&display_record)) return 0;
    /* Commit the unchanged original display prefix, then restore the exact
     * measured combined descriptor. Both arrays point at the same FB bytes. */
    tree.chosen.properties=display_tree.properties;
    tree.chosen.property_count=5;
    int display_commit=rpi5_display_xnu_tree_commit(&tree,&display_record,&display_tree);
    tree.chosen.properties=reservation_tree.properties;
    tree.chosen.property_count=6;
    if (display_commit) return 0;
    handoff=display_handoff;
    reservation_actual=*resolved;
    reservation_input=input;
    reservation_handoff=handoff;
    reservation_fdt_pa=fdt_pa;
    reservation_fdt_bytes=fdt_length;
    reservation_pending=1;'''
    return once(text,old,new)
def seed(text):
    if hashlib.sha256(text.encode()).hexdigest()!=PARENT_SEED_SHA256:raise ValueError('Exact accepted HDMI seed helper differs')
    text=once(text,'#include "seed_tree.h"','#include "seed_tree.h"\nextern int rpi5_reservation_record_finalize(struct rpi5_board_tree *);')
    text=once(text,'tree->chosen.property_count!=5 ||','tree->chosen.property_count!=6 ||')
    text=once(text,'struct rpi5_adt_property properties[6];','struct rpi5_adt_property properties[7];')
    return once(text,'    if (status) goto clear;','    if (status) goto clear;\n    if (rpi5_reservation_record_finalize(tree)) { status=-1; goto clear; }')
def sources():
    return [ROOT/'loader/rpi5'/p for p in ('reservation_record.h','reservation_record.c',
        'reservation_record_tree.h','reservation_record_tree.c')]+[Path(__file__).resolve()]
STACK_UNITS=frozenset(('reservation_record','reservation_record_tree','fdt','ranges','reservations',
    'firmware_seed_fdt','sha2small','dec32be','enc32be'))
def stack_budget(unit_stack_files,loader_stack_file,seed_stack_file):
    """Actual emitted A76 static frames, no compiler or historical replay.

    Overcount every frame in all selected helper units, including mutually
    exclusive FDT leaves. Finalize runs after isolated seed-stack return and
    before ADT encoding, so neither recursive ADT frames nor crypto seed-stack
    frames nest here. The top loader frame already includes any inlined caller.
    """
    if set(unit_stack_files)!=STACK_UNITS:raise ValueError('Incomplete reservation stack source set')
    def parse(path):
        rows=[]
        for line in Path(path).read_text().splitlines():
            location,size,kind=line.rsplit('\t',2);size=int(size)
            if kind!='static' or size<0:raise ValueError('Unbounded reservation stack frame')
            rows.append(dict(location=location,bytes=size,kind=kind))
        if not rows:raise ValueError('Missing reservation stack frames')
        return rows
    helper=[row for name in sorted(STACK_UNITS) for row in parse(unit_stack_files[name])]
    caller=[]
    required={'probe_el1_main','rpi5_reservation_record_finalize','rpi5_firmware_seed_tree'}
    for row in parse(loader_stack_file)+parse(seed_stack_file):
        name=row['location'].rsplit(':',1)[-1]
        if name in required or name=='firmware_seed_diagnostic':caller.append(row)
    names=[row['location'].rsplit(':',1)[-1] for row in caller]
    if not required.issubset(names) or len(names)!=len(set(names)):raise ValueError('Incomplete reservation caller frames')
    total=sum(row['bytes'] for row in helper+caller)
    if total+512>=32768:raise ValueError('Reservation finalization exceeds unchanged32KiB stack')
    return dict(conservative_bytes=total,stack_bytes=32768,required_margin=512,
        minimum_remaining_bytes=32768-total,helper_frames=helper,caller_frames=caller,
        scope='Actual A76 nonrecursive post-seed/pre-ADT finalization; every helper frame overcounted; masked IRQ and separate fault stack remain required')
