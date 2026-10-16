/* SPDX-License-Identifier: BSD-2-Clause */
ENTRY(_start)
ASSERT(DEFINED(LOADER_BASE), "Supply a reviewed LOADER_BASE; no default placement")
ASSERT((LOADER_BASE & 0xffff) == 0, "LOADER_BASE must be 64 KiB aligned")
SECTIONS {
    . = LOADER_BASE;
    __probe_start = .;
    .text : { KEEP(*(.text.entry)) *(.text*) }
    .rodata : { *(.rodata*) }
    .payload ALIGN(64) : {
        __payload_start = .;
        KEEP(*(.payload))
        __payload_end = .;
    }
    .data : { *(.data*) }
    . = ALIGN(16);
    __bss_start = .;
    .bss (NOLOAD) : { *(.bss*) *(COMMON) . = ALIGN(16); }
    __bss_end = .;
    .stack (NOLOAD) : { . += 0x4000; }
    __stack_top = .;
    .exception_stack (NOLOAD) : { . += 0x4000; }
    __exception_stack_top = .;
    __secondary_stacks = .;
    .secondary_stacks (NOLOAD) : { . += 4 * 0x4000; }
    __secondary_fault_stacks = .;
    .secondary_fault_stacks (NOLOAD) : { . += 4 * 0x4000; }
    __probe_end = .;
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
ASSERT(__probe_end < 0x10000000000, "Probe exceeds 40-bit PA")
