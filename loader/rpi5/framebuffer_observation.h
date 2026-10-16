/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_FRAMEBUFFER_OBSERVATION_H
#define RPI5_FRAMEBUFFER_OBSERVATION_H
#include "framebuffer_descriptor.h"
#define RPI5_FB_OBSERVE_NODES 4
#define RPI5_FB_OBSERVE_PATH 128
struct rpi5_fb_observed_node {
    char path[RPI5_FB_OBSERVE_PATH];
    uint32_t kind; /* 1 simple-framebuffer, 2 brcm,bcm2708-fb */
    uint32_t present, malformed; /* width,height,stride,format,reg,status,firmware */
    uint32_t width,height,stride,format,status,firmware;
    uint32_t reg_words,reg[4]; /* Raw big-endian cells, NOT guessed addresses. */
    int32_t descriptor_rc,plan_rc;
    uint32_t apple_compatible,overlaps_live,overlaps_fixed;
    struct rpi5_fb_plan plan;
};
struct rpi5_fb_observation {
    uint32_t total_bytes,simplefb_declarations,mailbox_fb_declarations,count;
    uint32_t root_ac,root_sc,chosen_ac,chosen_sc; /* 0 absent, UINT32_MAX malformed */
    int32_t memory_rc,reservations_rc;
    struct rpi5_fdt_memory memory;
    struct rpi5_reservation_plan reservations;
    struct rpi5_fb_observed_node node[RPI5_FB_OBSERVE_NODES];
};
/* Same-boot READABLE/STABLE FDT bytes only. No dereference of reg/firmware/
 * framebuffer values, no MMIO, mailbox request, mapping, drawing or allocation.
 * Bounded whole-tree path walk (depth32, path127, four relevant nodes, 1MiB).
 * A valid observation may report a missing/unsupported descriptor/reservation;
 * that is discovery data, never framebuffer ownership or cache approval.
 * Property payloads other than the seven listed facts are never copied out.
 * Output unchanged on malformed whole-tree/bounds/capacity failure.
 */
int rpi5_fb_observe(const void *,size_t,const struct rpi5_range *,size_t,
    struct rpi5_fb_observation *);
/* Identical parser using caller-owned scratch, avoiding a multi-kilobyte
 * temporary on the EL1 stack. Scratch is not output and may change on failure;
 * it must not alias the input blob, live table or atomic output. */
int rpi5_fb_observe_with_scratch(const void *,size_t,const struct rpi5_range *,size_t,
    struct rpi5_fb_observation *,struct rpi5_fb_observation *);
/* Bounded record formatter; caller's sinks must have finite failure deadlines.
 * Numeric facts only plus validated node paths, never arbitrary FDT payloads. */
int rpi5_fb_observation_log(const struct rpi5_fb_observation *,
    int (*)(const char *),int (*)(uint64_t));
#endif
