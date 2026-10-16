# GEM physical-aperture alias gate

The accepted zero-transmit board capture stopped at:

`DMA_MAP REASON=36 PAGE=0 ATTR=6 VA=2 PA=185532416 PAR_R=0xff0000000b0f0b00 PAR_W=0xff0000000b0f0b00`

The retained `IOBufferMemoryDescriptor` VA and WCOMB page attribute had already
passed. The static physical-aperture alias resolved the same physical page, but
its `0xff` translation attribute was Normal write-back rather than the required
Normal-NC `0x44`. This is expected from the current non-monitor ARM physmap:
it permits block mappings, while `__ARM_PTE_PHYSMAP__` is enabled only for an
Apple monitor build. Consequently XNU updates PV-tracked aliases but cannot
rewrite one physical-aperture page without changing a much larger block.

`RPI5_GEM_PAGE_GRANULAR_PHYSMAP=1` is a default-off BCM2712 DEVELOPMENT option.
It is deliberately a coupled change:

1. `arm_vm_physmap_init` constructs both physical-aperture regions that can be
   returned to the VM with page mappings instead of block mappings.
2. `proc_reg.h` enables XNU's existing physical-aperture PTE branch in
   `pmap_update_cache_attributes_locked`.

The latter updates the physmap PTE and PV-tracked aliases under XNU's existing
PV lock, PTE-write, TLB-flush, and cache-synchronization machinery. The GEM
provider still rejects unless the retained VA and `ml_static_ptovirt` alias
both translate read/write as Normal-NC to the exact same PA. There is no alias
bypass, manual PTE write, device-memory fallback, or cache-flush-only fiction.

This is software qualification, not board success. A successor zero-TX trial
must still produce `REASON=41` and `PAR_R/PAR_W` attributes `0x44` for both
pages before the ring provider can advance. Page-granular mapping also consumes
more page-table memory. Nothing here enables BME, queues, DMA, IRQ, packets,
network interfaces, or SSH.
