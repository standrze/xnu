# Hardware diagnostic milestone — not full Gate 1 completion

Repeat evidence: `serial-capture-1awe85cm` with seed-metadata candidate
`bl33-probe-uqzluws5` again reached `STOP BEFORE XNU LOADER`, with all three
secondary timer IRQ records and primary IRQ verification. Subsequent boot-order
override 0xf6 and SSH root `/dev/nvme0n1p2` confirm recovery. Firmware seed
metadata is recorded separately in RNG200-PROVIDER.md; no values were exposed.

Probe `bl33-probe-1baj5v2y`, SHA-256
`df94f4b1c37afaa3ac37041d3f45a3792b6b98807c3d78d563130b59811a7d33`,
was installed and byte-verified on the authorized SD. Recovery config remained
`be19da65345d93a2548582ce950bd13d32f1b10ad4c26566fdeb830705e9fb2e`.
115 host tests and native embedded-image validation passed before deployment.
Continuous capture: `build/rpi5/serial-capture-8deeotgh`.

Observed in the same hardware pass:

- Entry at 0x6000000, EL2-to-EL1 normalization and readable UART nominal check.
- Container integrity, Mach-O segments/symbols and 93292 local relocations
  validated. Payload remains embedded, explicitly `NOT_LOADED`.
- Runtime reservations parsed and a dynamic reservation proposed, not committed.
  Probe/FDT live ranges pass the implemented reservation checks. Complete
  firmware/live ownership is still explicitly unproved.
- PSCI 1.1; initial self ON and all three secondary affinities OFF.
- Affinities 0x100, 0x200 and 0x300 entered EL1 with SCTLR=0x30d00800,
  DAIF=0x3c0 and CNTFRQ=54 MHz. Each reports one INTID 27 timer IRQ,
  timer status=5 and a distinct GIC target (2,4,8).
- Primary masked timer condition and one primary INTID 27 IRQ verified,
  with configuration/cleanup success.
- Terminal marker `STOP BEFORE XNU LOADER` reached.
- Subsequent reset, boot-order override 0xf6 and Linux login recorded.

The strict-alignment fix now reaches and passes reservation parsing on hardware.
Hash-only watchdog servicing permits validation to finish while retaining
automatic recovery. This is not proof of arbitrary workload recovery or timing.

Gate 1 audit against PLAN.md: physical kernel materialization/transfer, complete
owned memory map, runtime Apple-tree integration and at least 256 bytes of fresh
source-qualified boot seed remain incomplete. No XNU instruction execution is
claimed. Keep the full gate open; do not substitute this hardware milestone for
its remaining loader requirements.
