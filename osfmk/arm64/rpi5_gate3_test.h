/* SPDX-License-Identifier: APSL-2.0 */
#ifndef _OSFMK_ARM64_RPI5_GATE3_TEST_H_
#define _OSFMK_ARM64_RPI5_GATE3_TEST_H_

#include <stdint.h>

/* Trial status: 0 idle, 1 running, 2 passed, 3 failed. */
void rpi5_gate3_start_concurrency_test(void);
uint32_t rpi5_gate3_concurrency_status(void);
void rpi5_gate3_start_tlb_test(void);
uint32_t rpi5_gate3_tlb_status(void);
uint32_t rpi5_gate3_xnupost_status(void);
void rpi5_gate3_start_user_tlb_test(void);
uint32_t rpi5_gate3_user_tlb_status(void);
void rpi5_gate3_start_qualification(void);

#endif /* _OSFMK_ARM64_RPI5_GATE3_TEST_H_ */
