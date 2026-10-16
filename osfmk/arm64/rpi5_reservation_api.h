/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RESERVATION_API_H
#define RPI5_RESERVATION_API_H
#ifdef __cplusplus
extern "C" {
#endif
struct rpi5_reservation_record;
/* Exact same-boot kernel-owned immutable record, absent before complete
 * boot validation/VM handoff. No copying in historical/legacy records, no
 * setter, allocation authority, DMA permission or external registry export. */
const struct rpi5_reservation_record *rpi5_boot_reservation_record(void);
#ifdef __cplusplus
}
#endif
#endif
