# SPDX-License-Identifier: BSD-2-Clause
"""Exact private same-boot reservation consumer; frozen display image is unchanged."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[2]
ARM=ROOT/'build/rpi5/display-xnu-console-5cd94fg_/arm_init.c'
def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Reservation consumer anchor changed: '+old)
    return text.replace(old,new)
def arm(text):
    text=once(text,'#include "arm64/rpi5_display_xnu.inc"',
        '#include "arm64/rpi5_display_xnu.inc"\n#include "arm64/rpi5_reservation_boot.inc"')
    text=once(text,'\tconst_boot_args = *args;', '''    /* start.s passed the original BootArgs as its bootstrap virtual address.
     * Capture its physical identity before replacing args with the const copy. */
    uint64_t reservation_args_va=(uintptr_t)args;
    if (reservation_args_va<args->virtBase || reservation_args_va-args->virtBase>args->memSize ||
        sizeof(*args)>args->memSize-(reservation_args_va-args->virtBase))
        panic("BCM2712: original reservation BootArgs pointer outside managed RAM");
    uint64_t reservation_args_pa=args->physBase+(reservation_args_va-args->virtBase);
\tconst_boot_args = *args;''')
    text=once(text,'\tpmap_first_pnum = (ppnum_t)atop(gDramBase);', '''    const void *reservation_wire;
    uint64_t reservation_tree_va=(uintptr_t)args->deviceTreeP;
    uint64_t reservation_kernel_va=(uintptr_t)&_mh_execute_header;
    uint64_t reservation_kernel_end=round_page(segHIGHESTKC ? segHIGHESTKC : getlastkerneladdr());
    uint64_t reservation_counter;
    __asm__ volatile("mrs %0,cntvct_el0":"=r"(reservation_counter));
    if (reservation_tree_va<args->virtBase || reservation_tree_va-args->virtBase>args->memSize ||
        args->deviceTreeLength>args->memSize-(reservation_tree_va-args->virtBase) ||
        reservation_kernel_va<args->virtBase || reservation_kernel_end<reservation_kernel_va ||
        reservation_kernel_end-args->virtBase>args->memSize ||
        rpi5_fdt_source_span.physical<args->physBase ||
        rpi5_fdt_source_span.physical-args->physBase>args->memSize ||
        rpi5_fdt_source_span.bytes>args->memSize-(rpi5_fdt_source_span.physical-args->physBase))
        panic("BCM2712: reservation context is outside the actual boot mapping");
    struct rpi5_reservation_boot_context reservation_context={
        .managed_start=args->physBase,.managed_end=args->physBase+args->memSize,
        .loader_start=rpi5_display_contract.loader_start,.loader_end=rpi5_display_contract.loader_end,
        .fdt_pa=rpi5_fdt_source_span.physical,.fdt_bytes=rpi5_fdt_source_span.bytes,
        .args_pa=reservation_args_pa,.args_bytes=sizeof(*args),
        .tree_pa=args->physBase+(reservation_tree_va-args->virtBase),.tree_bytes=args->deviceTreeLength,
        .top=args->topOfKernelData,.kernel_start=args->physBase+(reservation_kernel_va-args->virtBase),
        .kernel_end=args->physBase+(reservation_kernel_end-args->virtBase),.counter=reservation_counter};
    /* The validated retained source is already covered by the bootstrap map.
     * Validate all exclusions before arm_vm_init initializes managed memory. */
    if (SecureDTGetProperty(chosen,RPI5_RESERVATION_RECORD_PROPERTY,&reservation_wire,&dt_entry_size)!=kSuccess ||
        rpi5_boot_reservation_bind(reservation_wire,dt_entry_size,
            (const void *)(uintptr_t)(args->virtBase+(rpi5_fdt_source_span.physical-args->physBase)),
            rpi5_fdt_source_span.bytes,&reservation_context))
        panic("BCM2712: invalid same-boot resolved reservation ownership");
\tpmap_first_pnum = (ppnum_t)atop(gDramBase);''')
    return once(text,'    rpi5_fdt_source_kva = phystokv(rpi5_fdt_source_span.physical);',
        '''    rpi5_fdt_source_kva = phystokv(rpi5_fdt_source_span.physical);
    if (args->physBase+(end_kern-args->virtBase)!=rpi5_boot_reservations.kernel_end)
        panic("BCM2712: reservation kernel extent changed during VM initialization");
    rpi5_boot_reservations_ready=1;''')
