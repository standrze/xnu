/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_ROOT_FORWARD_H
#define RPI5_PCIE_ROOT_FORWARD_H
#include "rp1_decode_cycle.h"

enum rpi5_root_forward_state {
    RPI5_ROOT_FORWARD_EMPTY, RPI5_ROOT_FORWARD_CHECKING,
    RPI5_ROOT_FORWARD_WINDOW, RPI5_ROOT_FORWARD_ENABLING,
    RPI5_ROOT_FORWARD_LIVE, RPI5_ROOT_FORWARD_DISABLING,
    RPI5_ROOT_FORWARD_RESTORING, RPI5_ROOT_FORWARD_COMPLETE,
    RPI5_ROOT_FORWARD_QUARANTINED
};
struct rpi5_root_forward;
struct rpi5_root_forward_io {
    void *context;
    /* Fresh exact session/owner/thread/phase/decode/maps identity. Every real
     * read/write callback ALSO retains the existing pre/post owner guards. */
    int (*current)(void *,const struct rpi5_root_forward *,const struct rpi5_rp1_decode_cycle *);
    int (*read)(void *,uint32_t,unsigned,uint32_t *);
    int (*write)(void *,uint32_t,unsigned,uint32_t);
    int (*identify)(void *,const struct rpi5_rp1_decode_cycle *);
};
struct rpi5_root_forward_snapshot { uint32_t id,header,buses,command,window; };
struct rpi5_root_forward {
    enum rpi5_root_forward_state state;
    const struct rpi5_rp1_decode_cycle *decode;
    struct rpi5_root_forward_io io;
    uint32_t wanted_window,reads,writes,pending,offset,width,write,value;
    struct rpi5_root_forward_snapshot before,live,after;
    uint32_t outbound[10];
};
struct rpi5_root_forward_observation {
    struct rpi5_root_forward_snapshot before,live,after;
    uint32_t wanted_window,reads,writes;
};

/* Single unused session. Root config offsets are direct controller registers,
 * NOT endpoint ECAM. A 16-bit COMMAND write never rewrites STATUS/W1C bits.
 * Qualifies exact live BAR/outbound geometry; temporarily programs the minimal
 * 1MiB-granular nonprefetchable root memory window and MEM alone, invokes the
 * separately guarded read-only identify callback, disables MEM, restores the
 * original window and verifies the complete route/outbound state again.
 * No IO/BME, inbound/DMA, IRQ, endpoint, clock/reset or PHY write.
 * Failure quarantines, publishes no output, performs no forced cleanup/retry.
 * A failure can leave root/endpoint MEM and maps active until bounded reset.
 */
int rpi5_root_forward_run(struct rpi5_root_forward *,const struct rpi5_rp1_decode_cycle *,
    const struct rpi5_root_forward_io *,struct rpi5_root_forward_observation *);
int rpi5_root_forward_access_allowed(const struct rpi5_root_forward *,uint32_t,unsigned,unsigned,uint32_t);
#endif
