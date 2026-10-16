/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_GEM_MDIO_H
#define RPI5_RP1_GEM_MDIO_H
#include "rp1_gem_capabilities.h"
#include "pcie_fdt.h"
#define RPI5_GEM_MDIO_POLLS 32u
#define RPI5_GEM_MDIO_US 20000u
#define RPI5_GEM_MDIO_TRANSFERS 5u
enum rpi5_gem_mdio_state { RPI5_GEM_MDIO_UNUSED, RPI5_GEM_MDIO_ACTIVE,
    RPI5_GEM_MDIO_COMPLETE, RPI5_GEM_MDIO_QUARANTINED };
enum rpi5_gem_mdio_stage { RPI5_GEM_MDIO_PREFLIGHT=1, RPI5_GEM_MDIO_DIVIDER,
    RPI5_GEM_MDIO_ENABLE, RPI5_GEM_MDIO_READ_PHY, RPI5_GEM_MDIO_DISABLE,
    RPI5_GEM_MDIO_RESTORE_DIVIDER, RPI5_GEM_MDIO_FINISH };
struct rpi5_gem_mdio_session;
struct rpi5_gem_mdio_io {
    void *context;
    /* Fresh exact same-boot owner/thread/phase, immutable original-FDT
     * binding, completed capabilities and held GEM/clock Device maps. No
     * MMIO in current(); actual read/write/clock callbacks ALSO retain the
     * existing firmware/IRQ/PM pre/post guards; no cached permission. */
    int (*current)(void *,const struct rpi5_gem_mdio_session *,
        const struct rpi5_gem_cap_session *,const struct rpi5_pcie_fdt *);
    int (*read)(void *,uint32_t,uint32_t *);
    int (*write)(void *,uint32_t,uint32_t);
    int (*now_us)(void *,uint64_t *);
};
struct rpi5_gem_mdio_session {
    enum rpi5_gem_mdio_state state;
    const struct rpi5_gem_mdio_session *self;
    const struct rpi5_gem_cap_session *capabilities;
    const struct rpi5_pcie_fdt *binding;
    struct rpi5_gem_mdio_io io;
    uint32_t busy,stage,pending,offset,value,reads,writes,clocks,polls,transfer;
    uint32_t ncr_before,ncr_live,ncr_after,ncfgr_before,ncfgr_live,ncfgr_after;
    uint32_t changed_divider,phy_address,command,last_nsr,last_man,raw[5];
    uint64_t start_us,last_us,deadline_us;
    int error;
};
struct rpi5_gem_mdio_observation {
    uint32_t phy_address,phy_id,bmcr,bmsr_latched,bmsr_current,link,autoneg_complete;
    uint32_t ncr_before,ncr_live,ncr_after,ncfgr_before,ncfgr_live,ncfgr_after;
    uint32_t reads,writes,polls,clocks,transfers,changed_divider;
    uint64_t elapsed_us;
};
/* Permission for exact pending callback only. Writes are fixed C22 READ MAN
 * commands, MPE-only NCR transitions or CLK-only NCFGR transitions. No IRQ,
 * statistics, RX/TX enable, DMA, clock controller or PHY writes. */
int rpi5_gem_mdio_read_allowed(const struct rpi5_gem_mdio_session *,uint32_t);
int rpi5_gem_mdio_write_allowed(const struct rpi5_gem_mdio_session *,uint32_t,uint32_t);
int rpi5_gem_mdio_clock_allowed(const struct rpi5_gem_mdio_session *);
/* Semantic field equality for fresh-decoded binding; never depends on C
 * padding bytes and never treats a phandle alone as current authority. */
int rpi5_gem_mdio_binding_equal(const struct rpi5_pcie_fdt *,const struct rpi5_pcie_fdt *);
/* Run strictly inside the existing identity before/after clock bracket AFTER
 * fresh completed design reads. Fixed PHY address1/rgmii-id/200MHz selected
 * source profile comes from the retained original FDT + identity owner, not
 * measured clock frequency. CLK code5/DIV96 is <=IEEE2.5MHz at that profile.
 * NCR command bits, RE/TE and ALL unrecognized bits must be off; only named
 * non-command R/W bits are preserved. No unknown potentially strobed bit is
 * echoed. NCFGR retains all non-CLK bits under its ordinary config R/W ABI.
 * BMSR is intentionally read twice (latch-low semantics); no link-up demand.
 * All accesses are finite; time sampled before every MMIO and after final
 * access, no deadline extension. Every callback has fresh owner pre/post.
 * Any failure quarantines WITHOUT cleanup writes, leaves ordinary output
 * unchanged; diagnostic partial state is not restoration/ownership proof.
 * One-shot; no retry after uncertain MAN/NCR/NCFGR writes. No historical
 * receipt can admit this operation. Original global65536 limits unchanged. */
int rpi5_gem_mdio_run(struct rpi5_gem_mdio_session *,const struct rpi5_gem_cap_session *,
    const struct rpi5_pcie_fdt *,const struct rpi5_gem_mdio_io *,struct rpi5_gem_mdio_observation *);
#endif
