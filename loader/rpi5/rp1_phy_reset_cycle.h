/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PHY_RESET_CYCLE_H
#define RPI5_PHY_RESET_CYCLE_H
#include "rp1_phy_gpio_observe.h"
#include "rp1_gem_mdio.h"
#define RPI5_PHY_RESET_WINDOW_US 40000u
enum rpi5_phy_reset_state { RPI5_PHY_RESET_UNUSED,RPI5_PHY_RESET_ACTIVE,
    RPI5_PHY_RESET_COMPLETE,RPI5_PHY_RESET_QUARANTINED };
struct rpi5_phy_reset_session;
struct rpi5_phy_reset_io {
    void *context;
    /* Fresh exclusive GPIO32 ownership, exact original-FDT binding and three
     * live Device maps, sole current pre-IOKit CPU/thread, live completed GEM
     * clocks/design and unchanged root/BAR/IRQ/PM/firmware owners. It must
     * also verify the root LINK_CONTROL currently has ASPM/clock-PM disabled.
     * A receipt or a historical snapshot grants NONE of this authority. */
    int (*current)(void *,const struct rpi5_phy_reset_session *);
    int (*now)(void *,uint64_t *);
    /* Actual read/write adapters retain fresh owner guards pre/post and sample
     * monotonic time before MMIO and after the final guard. Reject expired
     * writes BEFORE side effect. Post-access error may mean write occurred. */
    int (*read)(void *,unsigned,uint32_t,uint64_t,uint64_t,uint32_t *,uint64_t *);
    int (*write)(void *,unsigned,uint32_t,uint32_t,uint64_t,uint64_t,uint64_t *);
    /* Bounded <=1ms guarded chunks, <=5 delay chunks, actual completion in
     * [target,target+1000), without extending the outer deadline. */
    int (*wait)(void *,uint64_t,uint64_t,uint64_t,uint64_t *);
    /* Genuine fresh timed C22 five-read sequence; no PHY writes/reset, same
     * 32 polls/20ms and caller's enclosing40ms bound. Copies output only on
     * full management register restoration. GPIO32 stays high throughout. */
    int (*manage)(void *,uint64_t,uint64_t,struct rpi5_gem_mdio_observation *,uint64_t *);
};
struct rpi5_phy_reset_observation {
    uint32_t ctrl_before,ctrl_after,pad_before,pad_after,out_before,out_after,oe_before,oe_after;
    uint32_t initial_pcie_inte,reads,writes,low_input,high_input;
    uint64_t asserted_us,deasserted_us,completed_us;
    struct rpi5_gem_mdio_observation phy;
};
struct rpi5_phy_reset_session {
    enum rpi5_phy_reset_state state;
    const struct rpi5_phy_reset_session *self;
    struct rpi5_phy_reset_io io;
    uint32_t busy,pending,step,bank,offset,value,reads,writes;
    uint64_t started_us,last_us,deadline_us;
    struct rpi5_phy_reset_observation observed;
    int error;
};
/* No mapping is performed by this core. Caller supplies exact currently held
 * GPIO32 pages and must revoke them after success, then complete inherited
 * post-clock/root/BAR restoration. On failure no cleanup/retry/compensation
 * occurs, and output is unchanged. This intentionally pulses external reset
 * and restores the ORIGINAL GPIO settings, which may reassert reset. */
int rpi5_phy_reset_run(struct rpi5_phy_reset_session *,const struct rpi5_phy_gpio_binding *,
    const struct rpi5_phy_reset_io *,struct rpi5_phy_reset_observation *);
int rpi5_phy_reset_read_allowed(const struct rpi5_phy_reset_session *,unsigned,uint32_t);
int rpi5_phy_reset_write_allowed(const struct rpi5_phy_reset_session *,unsigned,uint32_t,uint32_t);
#endif
