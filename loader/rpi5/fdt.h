/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_FDT_H
#define RPI5_FDT_H
#include <stddef.h>
#include <stdint.h>
#include "ranges.h"
struct rpi5_fdt_layout {
    uint32_t total, structure, structure_size, strings, strings_size;
    uint32_t reservations, reservations_size, boot_cpu;
};
/* Entire buffer must already be readable. This validates framing, not tokens,
 * reservation ownership, CPU topology or the physical address of the buffer.
 * Output remains unchanged on failure. 0=valid framing; -1=invalid. */
int rpi5_fdt_layout(const void *buffer, size_t available, struct rpi5_fdt_layout *out);
/* Validate framing plus token nesting/bounds/order; no duplicate-name or binding
 * semantics yet. Readability of the entire input remains the caller's duty. */
int rpi5_fdt_structure(const void *buffer, size_t available);
/* Count matching compatible declarations anywhere, including disabled nodes.
 * Diagnostic only: duplicates count separately, no ownership/absence proof.
 * Reads compatible values only; output unchanged on malformed input. */
int rpi5_fdt_compatible_count(const void *buffer, size_t available,
    const char *wanted, uint32_t *out);
/* Global phandle uniqueness, bounded to 1024 declarations. phandle and
 * linux,phandle may coexist only with the same value on the same node. */
int rpi5_fdt_phandles(const void *buffer, size_t available);
struct rpi5_fdt_property { uint32_t offset, length, node_offset; };
/* /chosen linux,initrd-start/end: matching 4/8-byte big-endian addresses,
 * exclusive end, nonempty 40-bit range. 0 present, 1 absent, -1 malformed.
 * Output unchanged unless present. Does not establish RAM coverage/ownership. */
int rpi5_fdt_initrd(const void *buffer, size_t available, struct rpi5_range *out);
/* Exact absolute path, no aliases/phandles. Reject duplicate matching path
 * components/properties; -2 absent, -1 malformed. Output offsets reference the
 * caller's stable readable FDT, not copied data. No binding interpretation. */
int rpi5_fdt_property(const void *buffer, size_t available, const char *path,
    const char *property, struct rpi5_fdt_property *out);
/* Exact-path simple-bus reg translation, explicit 1/2-cell widths, enabled
 * ancestors, <=8 reg extents and <=32 ranges tuples per bus. No PCI/aliases.
 * Output atomic; no MMIO reads. Final addresses limited to 40 bits. */
int rpi5_fdt_reg(const void *buffer, size_t available, const char *path,
    struct rpi5_ranges *out);
/* Confirm supported Pi UART10/GICv2 bindings and translated register profile.
 * Does not prove clock, interrupt wiring or MMIO readability. */
int rpi5_fdt_probe_mmio(const void *buffer, size_t available);
/* Terminal development only: require UART10's exact inherited GIC-400
 * SPI 121/level-high binding (INTID 153). Binding, not delivery proof. */
int rpi5_fdt_uart_irq(const void *buffer, size_t available);
/* Supported unnamed four/five-interrupt armv8 timer profile, inherited/explicit
 * GIC parent. Verifies virtual timer PPI 11 (INTID 27), not delivery. */
int rpi5_fdt_probe_timer(const void *buffer, size_t available);
struct rpi5_uart_clocks { uint32_t uart_hz, apb_hz; };
/* Supported UART10 -> /clocks/clk-uart,clk-vpu fixed-clock graph. Reads declared
 * rates, not measured hardware clocks; output atomic. No programmable clocks. */
int rpi5_fdt_uart_clocks(const void *buffer, size_t available, struct rpi5_uart_clocks *out);
/* Validate the supported RNG200 candidate's enabled path and translated span.
 * No RNG access, entropy acquisition or source-quality claim. Output atomic. */
int rpi5_fdt_rng200(const void *buffer, size_t available, struct rpi5_range *out);
int rpi5_fdt_watchdog(const void *buffer, size_t available, struct rpi5_range *out);
struct rpi5_fdt_sdhci {
    struct rpi5_range host, cfg;
    uint32_t source_hz, irq, bus_width, vmmc, vqmmc;
};
/* Pi 5 removable SD slot only, not the non-removable Wi-Fi SDIO controller.
 * Validate translated host/cfg ranges, declared fixed clock, GIC binding and
 * supply references. Atomic output, no MMIO, pin changes or voltage assumption.
 * Caller must establish actual supply/pin state before controller reset/commands.
 */
int rpi5_fdt_sdhci(const void *buffer, size_t available, struct rpi5_fdt_sdhci *out);
struct rpi5_fdt_sd_power {
    struct rpi5_range gpio, pins, aon_pins;
    uint32_t variant, settling_us; /* 0=C0, 1=D0; not a measured rail voltage. */
};
/* Exact board wiring for SD_IOVDD_SEL=GPIO3, SD_PWR_ON=GPIO4 and active-low
 * card detect=GPIO5. Validate both pin-controller variants together, regulator
 * voltages/polarity/state table and referenced default pin groups. No MMIO.
 * Reject other GPIO owners/hogs at integration time before claiming ownership.
 */
int rpi5_fdt_sd_power(const void *, size_t, struct rpi5_fdt_sd_power *);
struct rpi5_fdt_cpus { uint64_t affinity[4]; uint32_t count, enabled_mask; };
/* Narrow Pi 5 CPU binding. Includes disabled entries, marked in enabled_mask.
 * Rejects duplicate affinities/names/consumed properties. Output atomic. */
int rpi5_fdt_cpus(const void *buffer, size_t available, struct rpi5_fdt_cpus *out);
/* Require one enabled /psci node with a PSCI 0.2/1.0 binding and SMC method. */
int rpi5_fdt_psci_smc(const void *buffer, size_t available);
struct rpi5_fdt_memory { uint64_t start[8], end[8]; uint32_t count; };
/* Advertised RAM only, sorted and non-overlapping within 40-bit PA.
 * Not allocator input: reservations and live-image exclusions are not applied. */
int rpi5_fdt_memory(const void *buffer, size_t available, struct rpi5_fdt_memory *out);
/* Header plus static /reserved-memory exclusions. -2 means unsupported dynamic
 * or IOMMU policy; -1 malformed/capacity. Output unchanged on either failure.
 * Reusable pools are excluded. Caller must still add live allocations. */
int rpi5_fdt_reservations(const void *buffer, size_t available, struct rpi5_ranges *out);
struct rpi5_dynamic_reservation {
    uint64_t size, alignment;
    struct rpi5_range window[8];
    uint32_t window_count, node_offset, no_map;
};
struct rpi5_reservation_plan {
    struct rpi5_ranges fixed;
    struct rpi5_dynamic_reservation request[8];
    uint32_t count;
};
/* Decode only. Dynamic requests are not resolved/allocated by this function. */
int rpi5_fdt_reservation_plan(const void *buffer, size_t available, struct rpi5_reservation_plan *out);
struct rpi5_resolved_reservations {
    struct rpi5_range allocation[8];
    struct rpi5_ranges available;
    uint32_t count;
    /* RAM minus fixed and proposed dynamic reservations, retaining live buffers.
     * NOT allocation input or ownership proof. Firmware exclusions must be in
     * plan.fixed, not merely live, before using this for a mapping window. */
    struct rpi5_ranges reservation_free;
};
/* Pure deterministic plan; caller supplies every live extent. No memory writes,
 * firmware changes or allocator commitment. Atomic failure, no partial plan. */
int rpi5_resolve_reservations(const struct rpi5_fdt_memory *ram,
    const struct rpi5_reservation_plan *plan, const struct rpi5_range *live,
    size_t live_count, struct rpi5_resolved_reservations *out);
#endif
