/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_SD_HANDOFF_H
#define RPI5_SD_HANDOFF_H
#include <stdint.h>

enum rpi5_sd_bank { RPI5_SD_HOST, RPI5_SD_CFG, RPI5_SD_GPIO,
    RPI5_SD_PINS, RPI5_SD_AON_PINS };
struct rpi5_sd_platform_io {
    void *context;
    uint32_t (*read32)(void *, enum rpi5_sd_bank, uint32_t);
    void (*write32)(void *, enum rpi5_sd_bank, uint32_t, uint32_t);
    uint64_t (*microseconds)(void *);
    void (*delay_us)(void *, uint32_t);
};
enum rpi5_sd_handoff_stage { RPI5_SD_PREFLIGHT, RPI5_SD_QUEUE_HALTED,
    RPI5_SD_CLOCK_OFF, RPI5_SD_POWER_OFF, RPI5_SD_IO_3300,
    RPI5_SD_PINS_SET, RPI5_SD_POWER_ON, RPI5_SD_DIGITAL_READY };
struct rpi5_sd_handoff_result {
    enum rpi5_sd_handoff_stage stage;
    uint32_t gpio_data, gpio_direction, cfg_pins, capabilities;
    /* First masked-write readback mismatch; cleanup must not overwrite it.
     * readback_mask==0 means no such mismatch was recorded. */
    uint32_t failed_bank, failed_offset, readback_mask, expected, observed;
};
enum rpi5_sd_handoff_error { RPI5_SD_HANDOFF_OK=0,
    RPI5_SD_HANDOFF_INVALID=-1, RPI5_SD_HANDOFF_UNSUPPORTED=-2,
    RPI5_SD_HANDOFF_BUSY=-3, RPI5_SD_HANDOFF_READBACK=-4,
    RPI5_SD_HANDOFF_TIMEOUT=-5, RPI5_SD_HANDOFF_NO_CARD=-6 };
/* Independently implemented digital power/pin sequence. No SD commands, DMA,
 * sector writes or filesystem operations. Caller must own the removable slot
 * exclusively, validate exact rpi5_fdt_sd_power wiring, map the five spans as
 * ordered 32-bit Device MMIO, and serialize GPIO DATA RMW against other writers
 * (including firmware). No ownership of the AON interrupt controller is granted.
 * variant: 0=C0, 1=D0. Source declaration must be 200 MHz; CAPS must agree.
 * Rail discharge, actual voltage and source-clock rate still require board
 * evidence; success proves only the commanded digital sequence/readback.
 * A valid attempt always supplies diagnostics, including on failure. Invalid
 * arguments leave output unchanged and perform no MMIO. After a power-stage
 * error, best-effort power-off is attempted; failed hardware writes cannot be
 * undone or claimed safe. Do not automatically retry or start the PIO engine.
 */
int rpi5_sd_handoff(const struct rpi5_sd_platform_io *, uint32_t variant,
    uint32_t source_hz, struct rpi5_sd_handoff_result *);
#endif
