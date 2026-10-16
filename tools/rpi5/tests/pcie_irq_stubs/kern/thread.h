/* SPDX-License-Identifier: BSD-2-Clause */
/* Host test double only. The actual pexpert build uses XNU's real header. */
#ifndef PCIE_IRQ_MODEL_THREAD_H
#define PCIE_IRQ_MODEL_THREAD_H
typedef void *thread_t;
thread_t current_thread(void);
void thread_reference(thread_t);
#endif
