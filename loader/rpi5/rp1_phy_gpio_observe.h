/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PHY_GPIO_OBSERVE_H
#define RPI5_PHY_GPIO_OBSERVE_H
#include "rp1_gem_capabilities.h"
struct rpi5_phy_gpio_binding { uint32_t phandle,pin,active_low,reset_ms; uint64_t bank_offset[3]; };
/* Exact fresh Pi5 GEM -> active-low GPIO32 binding. Declaration only; no
 * pin/reset authority. GPIO extents must be the three RP1 BAR1 banks. */
int rpi5_phy_gpio_fdt(const void *,size_t,struct rpi5_phy_gpio_binding *);
int rpi5_phy_gpio_pcie_equal(const struct rpi5_pcie_fdt *,const struct rpi5_pcie_fdt *);
enum rpi5_phy_gpio_state { RPI5_PHY_GPIO_UNUSED,RPI5_PHY_GPIO_ACTIVE,
    RPI5_PHY_GPIO_COMPLETE,RPI5_PHY_GPIO_QUARANTINED };
struct rpi5_phy_gpio_session;
struct rpi5_phy_gpio_io {
    void *context;
    /* Exact current owner/thread/phase, original FDT and completed caps, held
     * root forwarding/BAR/decode/maps; never historical receipt authority. */
    int (*current)(void *,const struct rpi5_phy_gpio_session *);
    /* Actual host-only Device maps, exact 16KiB pages, no alias/reuse. Every
     * mapping/read/revoke must have fresh existing owner guards pre/post.
     * Any failure may have side effects; retain/quarantine, never retry. */
    int (*map)(void *,unsigned,struct rpi5_range);
    int (*unmap)(void *,unsigned,struct rpi5_range);
    int (*read)(void *,unsigned,uint32_t,uint32_t *);
};
struct rpi5_phy_gpio_observation { uint32_t raw[2][6],reads,mapped,unmapped; };
struct rpi5_phy_gpio_session {
    enum rpi5_phy_gpio_state state;
    const struct rpi5_phy_gpio_session *self;
    const struct rpi5_gem_cap_session *cap;
    struct rpi5_phy_gpio_io io;
    struct rpi5_range page[3];
    uint32_t busy,pending,index,pass,word,reads,mapped,unmapped;
    uint32_t raw[2][6];
    int error;
};
/* Read-only observer, not a PHY admission/reset routine. Twelve bounded
 * reads: GPIO32 STATUS/CTRL, RIO1 OUT/OE/IN, PAD32; raw snapshots may differ.
 * Three new maps, reverse revocation; enclosing clocks/owner/limits unchanged.
 * Output commits only after all revocations and final owner check; enclosing
 * caller must still complete post-clocks/root/BAR restoration. No GPIO/PHY,
 * MAN, clock, DMA, IRQ or reset writes. Failure leaves output unchanged and
 * quarantines with no forced cleanup; never reuse an admitted session. */
int rpi5_phy_gpio_run(struct rpi5_phy_gpio_session *,const struct rpi5_gem_cap_session *,
    const struct rpi5_phy_gpio_binding *,const struct rpi5_phy_gpio_io *,struct rpi5_phy_gpio_observation *);
int rpi5_phy_gpio_map_allowed(const struct rpi5_phy_gpio_session *,unsigned,struct rpi5_range,unsigned);
int rpi5_phy_gpio_read_allowed(const struct rpi5_phy_gpio_session *,unsigned,uint32_t);
#endif
