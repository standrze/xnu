# Bounded GEM capability reader

This separate offline successor adds16 reads to the accepted GEM identification
path: MID and design registers DCFG1/2/5/6/8/10/12, in two identical passes.
They execute after the existing15 pre-clock reads and two MID reads, before the
existing15 post-clock reads. Only the enclosing successful clock/owner/restore
sequence publishes the combined result. A later clock failure leaves the whole
trial output unchanged even though the capability substep completed.

The pure decoder exposes bus-width code (unknown codes explicitly yield0bits),
queue mask/count,64-bit descriptor feature, interrupt clear policy, packet buffer,
TSU, screening and prefetch fields. It retains all raw bits; it does not infer
reserved bit meanings. Queue0 always exists; the low DCFG6 mask is ORed with1,
as in the original driver. The DAW64 bit is not a usable DMA address width or
permission. No device-status, interrupt-status or statistics registers are read.

Exact primary Linux sources are preserved and SHA/length checked by
`tools/rpi5/rp1_gem_capabilities_sources.json`. Relevant original functions are
`macb_dbw`, `macb_configure_caps`, and `macb_probe_queues`. RP1 uses `rp1-gem` /
`cdns,macb`, with SYS as both hclk/pclk. Reading these design words follows the
existing clock-admitted, Device-mapped read path; no Linux register writes,
reset, interrupt enable, PHY operation or DMA setup are copied.

Implementation is `loader/rpi5/rp1_gem_capabilities.{h,c}` and the distinct
`tools/rpi5/rp1_gem_capabilities_profile.py` overlay. The helper and every C/C++
consumer must compile against the same emitted headers: the successor adds one
callback to the private GEM I/O struct. Compiling against older headers would
not be ABI-compatible. Existing frozen code and packages are unchanged.

Validation uses real C under ASan/UBSan, A76 freestanding compilation, and the
full original controller/provider/owner runtime with explicit MMIO, VM and time
doubles. New reads retain actual pre/post firmware/PM/IRQ guards and exact
owner/thread/phase/assignment/maps. All failures quarantine without cleanup or
retry. This is software evidence, not physical capabilities or packet transport.

Next: produce a separately tagged bounded kernel/package, capture actual design
words, then use those plus same-boot PHY description to design checked MDIO and
descriptor/DMA ownership. No reset/MDIO/DMA should be enabled by this reader.
