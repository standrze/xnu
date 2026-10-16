# Apple-tree construction on hardware

Candidate `bl33-probe-17jfo5uh`, SHA-256
`c9fb0d775f9c2e741bc37aae58176c140c4e77be30ec1ad1cac49f8941a52449`,
was byte-verified on the authorized SD with unchanged post-CMA recovery config.
117 host tests and the post-CMA native/Python placement check passed first.
Capture: `build/rpi5/serial-capture-x5yedkmr`.

The actual probe reports `APPLE_TREE_DIAGNOSTIC BYTES=0x570` (1392 bytes),
then reaches `STOP BEFORE XNU LOADER`. This exercises the board-tree builder,
graph measurer and serializer with runtime CPU topology, boot affinity,
counter frequency and the validated UART profile. Measured and encoded sizes
agree. Both graph and bytes remain within the probe's static live allocation.

No seed is present. The 8 GiB DRAM envelope is a diagnostic input, not a claim
that all included addresses have Normal-memory attributes or are managed RAM.
The serialized output is not supplied to XNU or relocated into handoff memory.
Runtime XNU consumer behavior, complete ownership, seed provenance and kernel
materialization/transfer remain unverified. Do not count this as Gate 1 closure.
