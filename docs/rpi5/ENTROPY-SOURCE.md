# Pi 5 runtime entropy investigation

No entropy provider is implemented or qualified for the loader. No seed bytes
were acquired, logged or packaged during this investigation.

## Candidate and provenance

The pinned firmware DTB identifies enabled
`/soc@107c000000/rng@7d208000`, compatible `brcm,bcm2711-rng200`, with
translated physical extent `[0x107d208000, 0x107d208028)`. This is an address and
binding declaration, not proof of accessible, initialized or healthy hardware.

The existing pinned TF-A checkout is commit
332b62e0443b004287d2cfc032a70bba6fb86f35. Its Pi 5 platform defines the same RNG
base, but `drivers/rpi3/rng/rpi3_rng.c` uses legacy offsets: status at +4, data
at +8, and unbounded FIFO polling. Pi 5 platform.mk sets stack protection to
zero; that legacy source is added only when stack protection is enabled. Its
presence does not supply a callable runtime entropy service to BL33. Do not
enable or import it as a shortcut to RNG200 support.

The [Linux RNG200 source](https://kernel.googlesource.com/pub/scm/linux/kernel/git/axboe/linux/+/fe5881ed7293813e492ad165292ae652b676ff6c/drivers/char/hw_random/iproc-rng200.c)
uses a different register map: reset controls at +4/+8, interrupt status at
+0x18, FIFO data at +0x20 and count at +0x24. It identifies failure status bits
and includes restart handling. It is GPL-2.0-only; no code was copied into this
project.

The pinned TF-A tree also has BSD-3-Clause `drivers/brcm/rng.c`, using FIFO
data/count +0x20/+0x24 and bounded polling. It targets another Broadcom platform
and is not evidence of a reviewed Pi 5 RNG200 implementation. Its reset path
and lack of corresponding failure-status handling need review before reuse.

## Required implementation work

1. Validate the runtime compatible/reg/ranges, accessibility and ownership.
   Confirm whether firmware retains any concurrent RNG use and whether BL33
   should own MMIO or use a deliberately implemented EL3 service.
2. Establish correct RNG200 initialization, startup completion, failure handling,
   FIFO limits and bounded timeout semantics from applicable source/documentation.
   Do not silently return partial entropy after a fault or timeout.
3. Qualify the source and define conditioning/health policy. A nonzero FIFO or
   a passing statistical smoke test alone does not prove cryptographic entropy.
4. Acquire fresh bytes per boot, retain no fixed fallback, zero intermediate
   buffers and pass at least 256 bytes in writable `/chosen/random-seed` storage.
   Diagnostics must report only status/counts/provenance, never seed contents.
5. Verify failure paths on host models and actual-board acquisition across boots.
   Keep the handoff disabled until provider and loader contracts are satisfied.

This identifies a credible hardware candidate and rules out one tempting wrong
driver; it does not close Gate 0 provider requirements or Gate 1 boot entropy.
