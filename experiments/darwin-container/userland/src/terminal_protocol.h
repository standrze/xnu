/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef DARWIN_TERMINAL_PROTOCOL_H
#define DARWIN_TERMINAL_PROTOCOL_H
#include <stddef.h>
#include <stdint.h>

/* DGT1 is separate from the frozen DGA1 managed execution protocol. */
#define DGT_PAYLOAD_MAX 256
#define DGT_LINE_MAX 640
struct dgt_frame {
    char direction, session[33], type[8];
    uint32_t sequence;
    unsigned char payload[DGT_PAYLOAD_MAX];
    size_t length;
};
const char *dgt_decode(struct dgt_frame *frame, const char *line, size_t size);
size_t dgt_encode(char line[DGT_LINE_MAX], const struct dgt_frame *frame);
#endif
