/* SPDX-License-Identifier: BSD-2-Clause
 * VZ-only Group 1 IRQ dispatch, included inside sleh_irq.
 * A level timer request can remain pending in the GIC after CNTV is rearmed.
 * Acknowledge/complete that stale request without inventing a clock event.
 * Do not print here: console diagnostics can interrupt a userland wire frame.
 */
uint32_t iar = pe_vz_irq_acknowledge();
if (iar == 27U) {
	if (ml_get_timer_pending()) {
		cdp->cpu_decrementer = -1;
		ml_interrupt_masked_debug_start(rtclock_intr, DBG_INTR_TYPE_TIMER);
		rtclock_intr(TRUE);
		ml_interrupt_masked_debug_end();
	}
	pe_vz_irq_complete(iar);
} else if (iar == 1U) {
	pe_vz_irq_complete(iar);
	cpu_signal_handler();
} else if (iar < 1020U || iar > 1023U) {
	panic("VZGENERIC: unexpected IRQ %u", iar);
}
