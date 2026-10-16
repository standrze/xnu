/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_FIRMWARE_SEED_H
#define RPI5_FIRMWARE_SEED_H
#include <stddef.h>
#include <stdint.h>
struct rpi5_fdt_property;
/* Match the qualified June 17 EEPROM identity and timestamp from runtime
 * FDT metadata. This is a trusted-firmware consistency check, not attestation. */
int rpi5_firmware_seed_version(const void *fdt, size_t length);
/* Select only the unique /chosen/rng-seed of exactly 64 bytes in a structurally
 * valid FDT whose total equals length. Metadata only: no seed contents read.
 * Caller guarantees readable stable FDT; writable ownership and trusted
 * firmware/version remain caller prerequisites before consuming. Atomic out. */
int rpi5_firmware_seed_select(const void *fdt, size_t length,
    struct rpi5_fdt_property *out);
/* HKDF-SHA256, absent salt, info "rpi5-xnu/boot-seed/v1" (no NUL).
 * Exactly 64 input bytes -> 256 derived bytes, NOT 256 raw entropy bytes.
 * Caller qualifies fresh secret firmware input, supplies disjoint buffers,
 * consumes the source once and erases it. No hardware/FDT access here.
 * Output unchanged on invalid input. Library stack residue is not erased
 * by this wrapper; runtime integration must address that separately. */
int rpi5_firmware_seed_derive(const uint8_t *seed, size_t seed_length,
    uint8_t *output, size_t output_length);
/* Single-primary transaction. *consumed must initially be zero and must never
 * be reset for the same boot. All three writable ranges must be disjoint.
 * Invalid metadata leaves everything unchanged. Once accepted, sets consumed
 * before derivation and wipes all 64 source bytes even on derivation failure.
 * Does not establish FDT ownership, firmware provenance or stack erasure. */
int rpi5_firmware_seed_consume(uint8_t *seed, size_t seed_length,
    uint8_t *output, size_t output_length, uint8_t *consumed);
/* AArch64 isolated-stack wrapper, single-primary and non-reentrant. Caller
 * argument ranges are checked against rpi5_seed_stack[0x4000] before switching.
 * Requires -mgeneral-regs-only code. Wipes scratch stack on normal return;
 * fatal exceptions cannot return to XNU and do not guarantee erasure. */
extern uint8_t rpi5_seed_stack[0x4000];
int rpi5_firmware_seed_consume_isolated(uint8_t *seed, size_t seed_length,
    uint8_t *output, size_t output_length, uint8_t *consumed);
#endif
