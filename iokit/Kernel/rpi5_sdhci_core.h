/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_SDHCI_CORE_H
#define RPI5_SDHCI_CORE_H
#include <stddef.h>
#include <stdint.h>

/* Single-owner synchronous PIO engine. The platform adapter must provide
 * ordered, aligned 32-bit Device MMIO, a monotonic microsecond clock and delay.
 * No allocation, IRQ, DMA, write/erase command or filesystem dependency.
 */
struct rpi5_sd_io {
    void *context;
    uint32_t (*read32)(void *, uint32_t);
    void (*write32)(void *, uint32_t, uint32_t);
    uint64_t (*microseconds)(void *);
    void (*delay_us)(void *, uint32_t);
};
struct rpi5_sd_card {
    struct rpi5_sd_io io;
    uint64_t sectors;
    uint32_t rca, last_interrupt, last_command;
    int ready;
};
enum rpi5_sd_result {
    RPI5_SD_OK=0, RPI5_SD_INVALID=-1, RPI5_SD_TIMEOUT=-2,
    RPI5_SD_CONTROLLER=-3, RPI5_SD_CARD=-4, RPI5_SD_UNSUPPORTED=-5
};
/* PRECONDITION: exclusive controller/card ownership; platform has established
 * SD pin selection, a card power cycle into stable 3.3-V VDD AND 3.3-V I/O,
 * CQE disabled, and
 * validated the controller clock. FDT voltage declarations do not prove this.
 * This function resets the host/card and selects 1-bit default-speed mode.
 * First implementation accepts SD v2 SDHC/SDXC only; no SDSC/MMC/SDUC/UHS.
 * Valid attempts invalidate any prior card state, including on failure.
 */
int rpi5_sd_start(struct rpi5_sd_card *, const struct rpi5_sd_io *, uint32_t source_hz);
/* Same initialization/opcode sequence, optionally used by the future write
 * provider to retain ACTUAL CMD2/CMD9 observations. R2's CRC/end byte is zero,
 * not observed on SDHCI. Output is unchanged on any failed initialization.
 * This records identity; it does not authorize writes or establish cache state.
 */
struct rpi5_sd_identity { uint8_t cid[16], csd[16]; };
int rpi5_sd_start_identified(struct rpi5_sd_card *, const struct rpi5_sd_io *,
    uint32_t source_hz, struct rpi5_sd_identity *);
/* Exactly one 512-byte sector, atomic output on failure. Caller serializes all
 * requests. A controller/card error invalidates the card until start succeeds.
 * Invalid arguments/ranges cause no MMIO and leave the card state unchanged.
 */
int rpi5_sd_read_sector(struct rpi5_sd_card *, uint64_t lba, void *, size_t);
/* Convert SDHCI R2 register words (RESP0 first) into canonical CSD bytes and
 * decode SDHC/SDXC capacity. Pure helpers shared with hostile-input tests.
 */
void rpi5_sd_csd_bytes(const uint32_t response[4], uint8_t csd[16]);
int rpi5_sd_csd_sectors(const uint8_t csd[16], uint64_t *sectors);
#endif
