# SPDX-License-Identifier: BSD-2-Clause
"""Distinct exact offline loader/kernel display overlays; no file or hardware I/O."""
from pathlib import Path
from . import console_mirror_overlay as mirror
ROOT=Path(__file__).resolve().parents[2]
ARM=ROOT/'build/rpi5/firmware-fdt-handoff-20261012-final/arm_init.c'
LOADER=ROOT/'build/rpi5/firmware-fdt-handoff-20261012-final/probe_main.c'
SEED=ROOT/'build/rpi5/firmware-fdt-handoff-20261012-final/firmware_seed_tree.c'
ALLOCATOR=ROOT/'loader/rpi5/display_allocate_zero_adapter.c'
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Exact display overlay boundary changed: '+old[:100])
    return text.replace(old,new)
def allocator(text):
    text=once(text,'int rpi5_display_allocate_run(', 'int rpi5_display_xnu_allocate_run(')
    text=once(text,'#include "display_allocate_adapter.h"', '#include "display_xnu_allocate.h"')
    return once(text,'no EL3 FDT-window alias, no later cache enable.',
        'no EL3 FDT-window alias. This distinct XNU profile may enable caches\n     * only after all four matched responses close the session; request pages\n     * and image remain retained below topOfKernelData and are never reused.')
def seed(text):
    text=once(text,'tree->chosen.property_count<2 || tree->chosen.property_count>4 ||',
        'tree->chosen.property_count!=5 ||')
    return once(text,'struct rpi5_adt_property properties[5];','struct rpi5_adt_property properties[6];')
def loader(text):
    text=once(text,'#include "tree_handoff.h"','#include "tree_handoff.h"\n#include "display_xnu_allocate.h"\n#include "display_xnu_handoff.h"')
    anchor='static int board_tree_diagnostic('
    block='''/* Single owner, before any CPU_ON. No framebuffer access in BL33. */
_Alignas(4096) static uint8_t display_pages[4][4096];
static struct rpi5_display_allocate_result display_result;
static struct rpi5_display_allocate_report display_report;
static struct rpi5_display_retained display_retained;
static int display_ready;
static int display_allocate(uintptr_t pa,size_t bytes,const struct rpi5_fdt_cpus *cpus)
{
    uint64_t mpidr;
    __asm__ volatile("mrs %0,mpidr_el1":"=r"(mpidr));
    if (cpus->count!=4 || cpus->enabled_mask!=15 ||
        (mpidr & UINT64_C(0xff00ffffff))!=cpus->affinity[0] ||
        rpi5_psci_query(0x8400000a,0xc4000004)!=0) return 0;
    for (unsigned i=1;i<4;i++) if (rpi5_psci_query(0xc4000004,cpus->affinity[i])!=1) return 0;
    struct rpi5_range image={(uintptr_t)__probe_start,(uintptr_t)__probe_end};
    struct rpi5_range managed={0x6000000,0x10000000};
    if (!text("RPI5XNU:DISPLAYXNU:ENTRY TAG=" RPI5_DISPLAY_XNU_TAG " SAME_BOOT OWNED_FRAMEBUFFER_CONSOLE_V1\\r\\n")) return 0;
    if (!text("RPI5XNU:DISPLAYXNU:ALLOCATE_BEGIN SAME_BOOT FOUR_TX_MAX ONE_ALLOCATE NO_FB_ACCESS\\r\\n")) return 0;
    int rc=rpi5_display_xnu_allocate_run((const void *)pa,bytes,image,display_pages,
        cpus->affinity[0],&display_result,&display_report);
    if (!text("RPI5XNU:DISPLAYXNU:ALLOCATE RC=") || !hex((uint64_t)(int64_t)rc) ||
        !text(" COMPLETED=") || !hex(display_report.session.completed) ||
        !text(" QUARANTINED=") || !hex(display_report.session.quarantined_buffers) || !text("\\r\\n")) return 0;
    if (rc || rpi5_display_allocation_retained(&display_result,&display_report,(const void *)pa,
        bytes,pa,image,&managed,1,&display_retained)) return 0;
    display_ready=1;
    return text("RPI5XNU:DISPLAYXNU:OWNED START=") && hex(display_retained.retained_pages.start) &&
        text(" END=") && hex(display_retained.retained_pages.end) &&
        text(" MANAGED_UNCHANGED NO_LOADER_DRAW RETAIN_UNTIL_RESET\\r\\n");
}

'''
    text=once(text,anchor,block+anchor)
    anchor='    if (rpi5_board_tree_memory_map(&tree,&types)) return 0;'
    text=once(text,anchor,'''    static struct rpi5_memory_types display_types;
    if (!display_ready || rpi5_display_xnu_types(&display_retained,&types,&display_types)) return 0;
    types=display_types;
'''+anchor)
    anchor='    /* Geometry first; resolved planner below proves reservation exclusion.'
    text=once(text,anchor,'''    static struct rpi5_display_xnu_tree display_tree;
    if (rpi5_display_xnu_tree_reserve(&tree,&display_tree)) return 0;
'''+anchor)
    anchor='    int reported=text("RPI5XNU:BL33:LOAD_PLAN HEADER=")'
    text=once(text,anchor,'''    static struct rpi5_handoff_plan display_handoff;
    struct rpi5_display_xnu_record display_record;
    size_t display_tree_bytes;
    if (rpi5_seed_tree_measure(&tree.root,sizeof encoded,&display_tree_bytes) || display_tree_bytes>UINT32_MAX) return 0;
    input.tree_length=(uint32_t)display_tree_bytes;
    if (rpi5_display_xnu_handoff(&display_retained,&display_report,fdt_pa,fdt_length,
        (struct rpi5_range){(uintptr_t)__probe_start,(uintptr_t)__probe_end},&input,
        &handoff,&display_handoff,&display_record) ||
        rpi5_display_xnu_tree_commit(&tree,&display_record,&display_tree)) return 0;
    handoff=display_handoff;
    if (!text("RPI5XNU:DISPLAYXNU:HANDOFF VIDEO_PHYSICAL NORMAL_NC_NX REQUIRED UART_FIRST\\r\\n")) return 0;
'''+anchor)
    anchor='    if (payload_ok && cpus_ok && reservations_ok && frequency && frequency<=UINT32_MAX)\n        tree_ok=board_tree_diagnostic('
    return once(text,anchor,'''    if (payload_ok && cpus_ok && psci_ok && reservations_ok && frequency && frequency<=UINT32_MAX &&
        display_allocate(pa,total,cpus))
        tree_ok=board_tree_diagnostic(''')
def arm(text):
    anchor='#include "arm64/rpi5_firmware_fdt.inc"'
    text=once(text,anchor,anchor+'\n#include "arm64/rpi5_display_xnu.inc"')
    anchor='\tpmap_first_pnum = (ppnum_t)atop(gDramBase);'
    block='''    const void *display_record;
    struct rpi5_display_xnu_record display_value;
    if (SecureDTGetProperty(chosen, "rpi5-framebuffer", &display_record, &dt_entry_size) != kSuccess ||
        rpi5_display_xnu_record_decode(display_record, dt_entry_size, &display_value) ||
        display_value.managed_start != args->physBase || display_value.managed_end - display_value.managed_start != args->memSize ||
        display_value.top != args->topOfKernelData || display_value.fdt != rpi5_fdt_source_span.physical ||
        display_value.fdt_bytes != rpi5_fdt_source_span.bytes ||
        rpi5_display_xnu_video_valid(&display_value, args->Video.v_baseAddr, args->Video.v_width,
            args->Video.v_height, args->Video.v_rowBytes, args->Video.v_depth, 0, 0, 0, 1) ||
        args->Video.v_display != 0 || rpi5_physical_memory_type(display_value.reserve_start, display_value.reserve_end) != 1) {
        panic("BCM2712: invalid same-boot retained framebuffer contract");
    }
    rpi5_display_contract = display_value;
    rpi5_display_contract_ready = 1;
'''
    text=once(text,anchor,block+anchor)
    anchor='    rpi5_fdt_source_kva = phystokv(rpi5_fdt_source_span.physical);'
    return once(text,anchor,'''    if (end_kern < args->virtBase || end_kern - args->virtBase > args->memSize ||
        rpi5_display_contract.loader_start < args->physBase + (end_kern - args->virtBase) ||
        rpi5_display_contract.loader_end > args->topOfKernelData) {
        panic("BCM2712: display owner overlaps reclaimable kernel memory");
    }
'''+anchor)
def pmap(text):
    anchor='vm_map_address_t\npmap_map_bd_with_options('
    text=once(text,anchor,'#include "arm64/rpi5_display_xnu_api.h"\n_Static_assert(MAIR_WRITECOMB == 0x44 && CACHE_ATTRINDX_WRITECOMB == 1, "A76 Normal-NC MAIR differs");\n\n'+anchor)
    anchor='\tconst bool first_page_is_dram = is_dram_addr(start);'
    text=once(text,anchor,'''    if (rpi5_display_xnu_map_admit(start, end,
            (options & PMAP_MAP_BD_MASK) == PMAP_MAP_BD_WCOMB,
            (prot & VM_PROT_EXECUTE) == 0, 1) < 0) {
        panic("BCM2712: unsafe early framebuffer mapping");
    }
'''+anchor)
    anchor='\tpt_entry_t pte;\n#if defined(ARM64_BOARD_CONFIG_BCM2712)\n\tif (!rpi5_physical_memory_type(pa, pa + PAGE_SIZE)) {'
    text=once(text,anchor,'''\tpt_entry_t pte;
    if (rpi5_display_xnu_map_admit(pa, pa + PAGE_SIZE,
            (wimg & VM_WIMG_MASK) == VM_WIMG_WCOMB, 1, 0) < 0) {
        panic("BCM2712: unsafe late framebuffer cache alias");
    }
#if defined(ARM64_BOARD_CONFIG_BCM2712)
\tif (!rpi5_physical_memory_type(pa, pa + PAGE_SIZE)) {''')
    anchor='\tbool set_NX = false, set_XO = false, set_TPRO = false;'
    text=once(text,anchor,'''    int display_owned = rpi5_display_xnu_map_admit(pa, pa + PAGE_SIZE,
        1, (prot & VM_PROT_EXECUTE) == 0, 0);
    if (display_owned < 0 || (display_owned == 1 &&
        (pmap != kernel_pmap || !(prot & VM_PROT_WRITE)))) {
        panic("BCM2712: framebuffer mapping is not kernel writable NX");
    }
'''+anchor)
    # This package only changes the selected mapping type path; all unrelated
    # physical ranges still pass through the complete original pmap guards.
    verify='''
int
rpi5_display_xnu_mapping_verify(uint64_t virtual, uint64_t physical, uint64_t length)
{
    if (!virtual || (virtual & PAGE_MASK) || !length || (length & PAGE_MASK) ||
        length > 0x1000000 || virtual > UINT64_MAX - length || physical > UINT64_MAX - length ||
        rpi5_display_xnu_map_admit(physical, physical + length, 1, 1, 1) != 1) return -1;
    uint64_t mair;
    __asm__ volatile("mrs %0, mair_el1" : "=r"(mair));
    if (((mair >> (8 * CACHE_ATTRINDX_WRITECOMB)) & 255) != 0x44) return -1;
    for (uint64_t offset = 0; offset < length; offset += PAGE_SIZE) {
        pt_entry_t *ptep = pmap_pte(kernel_pmap, virtual + offset);
        if (ptep == PT_ENTRY_NULL) return -1;
        pt_entry_t entry = *((volatile pt_entry_t *)ptep);
        if ((entry & ARM_PTE_TYPE_VALID) != ARM_PTE_TYPE_VALID || pte_to_pa(entry) != physical + offset ||
            (entry & ARM_PTE_ATTRINDXMASK) != ARM_PTE_ATTRINDX(CACHE_ATTRINDX_WRITECOMB) ||
            (entry & ARM_PTE_APMASK) != ARM_PTE_AP(AP_RWNA) ||
            (entry & (ARM_PTE_NX | ARM_PTE_PNX)) != (ARM_PTE_NX | ARM_PTE_PNX)) return -1;
    }
    return 0;
}
'''
    return text+verify
def serial(text):
    text=mirror.overlay(text)
    old='    __atomic_store_n(&rpi5_console_mirror_state, 2, __ATOMIC_RELEASE);'
    new='''    unsigned expected = 1;
    (void)__atomic_compare_exchange_n(&rpi5_console_mirror_state, &expected, 2,
        false, __ATOMIC_RELEASE, __ATOMIC_RELAXED);'''
    text=once(text,old,new)
    anchor='static void\nrpi5_console_mirror_putc(char c, bool poll)'
    return once(text,anchor,'''#include "arm64/rpi5_display_xnu_api.h"
int
rpi5_display_xnu_mirror_started(void)
{
    return __atomic_load_n(&rpi5_console_mirror_state, __ATOMIC_ACQUIRE) != 0;
}
'''+anchor)
def video(text):
    anchor='void\ninitialize_screen(PE_Video * boot_vinfo, unsigned int op)'
    text=once(text,anchor,'#include "arm64/rpi5_display_xnu_api.h"\n#include "'+str(ROOT/'loader/rpi5/console_mirror.h')+'"\n\n'+anchor)
    anchor='\tif (boot_vinfo) {\n\t\tstruct vc_info new_vinfo = vinfo;'
    text=once(text,anchor,'''    if (boot_vinfo) {
        /* A revoke is not a reader-quiescence barrier. Never unmap or replace
         * the admitted mapping after publication, including after revocation. */
        if (rpi5_display_xnu_mirror_started()) {
            rpi5_console_mirror_revoke();
            panic("BCM2712: published framebuffer remap prohibited");
        }
        if (rpi5_display_xnu_video_admit(boot_vinfo->v_baseAddr, boot_vinfo->v_width, boot_vinfo->v_height,
                boot_vinfo->v_rowBytes, boot_vinfo->v_depth, boot_vinfo->v_offset, boot_vinfo->v_length,
                boot_vinfo->v_rotate, boot_vinfo->v_scale)) {
            rpi5_console_mirror_revoke();
            panic("BCM2712: changed live framebuffer descriptor");
        }
        rpi5_console_mirror_revoke(); /* Before any geometry/mapping change. */
\t\tstruct vc_info new_vinfo = vinfo;''')
    anchor='#if HAS_UCNORMAL_MEM || APPLEVIRTUALPLATFORM\n'
    if text.count(anchor)!=1:raise ValueError('Exact Apple video cache branch changed')
    text=text.replace(anchor,'#if defined(ARM64_BOARD_CONFIG_BCM2712)\n                unsigned int flags = VM_WIMG_WCOMB;\n#elif HAS_UCNORMAL_MEM || APPLEVIRTUALPLATFORM\n',1)
    anchor='\t\t\t\tnewVideoVirt = ml_io_map_unmappable((vm_map_offset_t)new_vinfo.v_physaddr, newMapSize, flags);   /* Allocate address space for framebuffer */'
    text=once(text,anchor,anchor+'''
                if (!newVideoVirt || rpi5_display_xnu_geometry(new_vinfo.v_physaddr, new_vinfo.v_width,
                        new_vinfo.v_height, new_vinfo.v_rowbytes, new_vinfo.v_depth, newMapSize) ||
                    rpi5_display_xnu_mapping_verify(newVideoVirt, new_vinfo.v_physaddr, newMapSize)) {
                    panic("BCM2712: actual framebuffer PTE/MAIR validation failed");
                }''')
    anchor='\tgraphics_now = gc_graphics_boot && !gc_desire_text;'
    text=once(text,anchor,'''    if (op == kPEReleaseScreen || op == kPEDisableScreen) rpi5_console_mirror_revoke();
'''+anchor)
    end='\n}\n\nvoid vcattach(void);'
    ready='''
    /* initialize_screen has completed: do not publish during early mappings.
     * vcattach owns the first post-VM acquire. Later revocation is permanent. */
    if (vm_initialized && gc_initialized && gc_enabled && gc_acquired && !gc_graphics_boot &&
        vinfo.v_baseaddr && vinfo.v_physaddr && vinfo.v_depth == 32 && !vinfo.v_rotate &&
        rpi5_display_xnu_geometry(vinfo.v_physaddr, vinfo.v_width, vinfo.v_height,
            vinfo.v_rowbytes, vinfo.v_depth, lastVideoMapSize) == 0 &&
        rpi5_display_xnu_mapping_verify(lastVideoVirt, vinfo.v_physaddr, lastVideoMapSize) == 0) {
        if (rpi5_console_mirror_publish()) {
            kprintf("RPI5XNU:DISPLAYXNU:MIRROR_READY NORMAL_NC NX UART_FIRST INPUT_UART ONLY_MAPPING_RETAINED_UNTIL_RESET\\n");
        }
    }
'''
    return once(text,end,ready+end)
