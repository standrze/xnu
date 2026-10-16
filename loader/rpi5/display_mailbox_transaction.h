/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_DISPLAY_MAILBOX_TRANSACTION_H
#define RPI5_DISPLAY_MAILBOX_TRANSACTION_H
#include "display_mailbox_get.h"
#include "display_mailbox_fdt.h"

#define RPI5_DISPLAY_MBOX_RX 0x00u
#define RPI5_DISPLAY_MBOX_PEEK 0x10u
#define RPI5_DISPLAY_MBOX_RX_STATUS 0x18u
#define RPI5_DISPLAY_MBOX_TX 0x20u
#define RPI5_DISPLAY_MBOX_TX_STATUS 0x38u
#define RPI5_DISPLAY_MBOX_EMPTY 0x40000000u
#define RPI5_DISPLAY_MBOX_FULL 0x80000000u
#define RPI5_DISPLAY_MBOX_CHANNEL 8u
#define RPI5_DISPLAY_MBOX_MAX_POLLS 512u
#define RPI5_DISPLAY_MBOX_MAX_CALLBACKS 4096u
#define RPI5_DISPLAY_MBOX_MAX_DURATION_US 1000000u
#define RPI5_DISPLAY_MBOX_MAX_CAPACITY 4096u

enum rpi5_display_mailbox_state {
    RPI5_DISPLAY_MBOX_UNUSED, RPI5_DISPLAY_MBOX_ACTIVE,
    RPI5_DISPLAY_MBOX_COMPLETE, RPI5_DISPLAY_MBOX_QUARANTINED
};
enum rpi5_display_mailbox_cache {
    RPI5_DISPLAY_MBOX_PUBLISH = 1, RPI5_DISPLAY_MBOX_ACQUIRE = 2
};
enum rpi5_display_mailbox_stage {
    RPI5_DISPLAY_MBOX_ADMISSION = 1, RPI5_DISPLAY_MBOX_REQUEST,
    RPI5_DISPLAY_MBOX_PUBLISHING, RPI5_DISPLAY_MBOX_WAIT_TX,
    RPI5_DISPLAY_MBOX_SENDING, RPI5_DISPLAY_MBOX_WAIT_RX,
    RPI5_DISPLAY_MBOX_PEEKING, RPI5_DISPLAY_MBOX_POPPING,
    RPI5_DISPLAY_MBOX_ACQUIRING, RPI5_DISPLAY_MBOX_VALIDATING,
    RPI5_DISPLAY_MBOX_QUIET, RPI5_DISPLAY_MBOX_FINISH
};
struct rpi5_display_mailbox_buffer {
    void *cpu;
    size_t capacity;
    /* Explicit caller-admitted address: no PA/VA conversion, GPU alias OR,
     * truncation or address inference is performed by this pure core. */
    uint64_t mailbox_address;
};
struct rpi5_display_mailbox_session {
    enum rpi5_display_mailbox_state state;
    const struct rpi5_display_mailbox_session *self;
    uint64_t owner, start_us, last_us, deadline_us;
    uint32_t busy, stage, slot, polls, callbacks;
    uint32_t tx_attempted, pop_attempted, completed, quarantined_buffers;
    uint32_t expected_word, peek_word, popped_word;
    int error;
};
struct rpi5_display_mailbox_ops {
    void *context;
    /* Fresh in-memory check of the current boot, thread, lifecycle, exact
     * session/binding/buffers and EXCLUSIVE mailbox consumer/producer lease.
     * Must be bounded, non-reentrant and perform no MMIO/cache/time work.
     * Independently attest NO outstanding earlier firmware request or other
     * mailbox client: both FIFOs EMPTY does not prove firmware has finished
     * a request whose TX word it already consumed. Do not infer this from
     * EMPTY bits or from an old response/receipt. Also require buffers never
     * sent before this session, retained until
     * controller reset after quarantine. It is not a historical receipt.
     * This predicate brackets every OTHER callback, including now/admit.
     * Continuous exclusion between PEEK and RX is essential: no competing
     * consumer may remove the matched head while current() still succeeds. */
    int (*current)(void *, const struct rpi5_display_mailbox_session *,
        const struct rpi5_display_mailbox_fdt *,
        const struct rpi5_display_mailbox_buffer *, uint64_t);
    /* Separately establish actual linked buffer extent, exclusion from all
     * other live regions, mailbox DMA address/coherency and current mapping.
     * The pure FDT result alone grants none of those authorities. */
    int (*admit)(void *, unsigned, const struct rpi5_display_mailbox_buffer *,
        const struct rpi5_display_mailbox_fdt *);
    int (*now_us)(void *, uint64_t *);
    /* Future adapters must use the freshly admitted Device mapping, exact
     * 32-bit access and appropriate peripheral ordering. No actual MMIO is
     * implemented here. RX is destructive; PEEK must be non-destructive. */
    int (*read32)(void *, uint32_t, uint32_t *);
    int (*write32)(void *, uint32_t, uint32_t);
    /* PUBLISH: clean the full firmware-writable backing to PoC and complete
     * DSB before TX; ACQUIRE: order matched completion, invalidate the full
     * backing, complete DSB before CPU inspection. Caller must prove cache
     * line isolation/alias discipline and choose the actual architecture ops.
     * Coherent-memory alternatives need equally explicit ordering proof.
     * No generic buffer allocator/free or controller reset callback exists. */
    int (*cache)(void *, unsigned, const struct rpi5_display_mailbox_buffer *,
        size_t, enum rpi5_display_mailbox_cache);
};
struct rpi5_display_mailbox_result {
    uint32_t count;
    struct rpi5_display_get_reply count_reply, settings[2];
};

/* Zero-initialized one-shot session; no retry/reset/reuse API. Inputs and all
 * three caller-owned backing regions must be stable, disjoint and readable;
 * buffers also writable, >=88 and <=4096 bytes, 16-byte CPU/bus aligned.
 * Exact same-boot FDT provenance and linked-buffer/cache authority are fresh
 * caller obligations, not established by pointer/shape checks here.
 * COUNT then indices [0,count), count<=2, each in its own never-reused buffer.
 * Fresh both-FIFOs-empty admission, RX-empty before each TX, PEEK address|8 before
 * POP, and POP rechecked. Mismatched PEEK is NEVER popped or drained.
 * At most512 total TX/RX status polls and4096 non-current callbacks, plus a
 * caller-selected global monotonic deadline <=1s. Stuck time cannot loop
 * indefinitely. Callbacks themselves MUST be bounded; core cannot preempt.
 * Any failure after admission quarantines ALL backing until controller reset,
 * even if TX completion is unknown; no compensation or late-response retry.
 * Output unchanged on failure. Results are raw query data, not framebuffer
 * format, allocation, address, lifetime, scanout or mapping authority. */
int rpi5_display_mailbox_query(struct rpi5_display_mailbox_session *,
    const struct rpi5_display_mailbox_fdt *,
    const struct rpi5_display_mailbox_buffer [3],
    const struct rpi5_display_mailbox_ops *, uint64_t owner,
    uint32_t duration_us, struct rpi5_display_mailbox_result *);
#endif
