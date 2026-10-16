/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef DARWIN_GUEST_AGENT_PROTOCOL_H
#define DARWIN_GUEST_AGENT_PROTOCOL_H
#include <stddef.h>
#include <stdint.h>

#define DGA_PAYLOAD_MAX 256
#define DGA_LINE_MAX 1024
#define DGA_ARGS_MAX 16
#define DGA_COMMAND_MAX 16
#define DGA_OUTPUT_MAX (1024U * 1024U)

struct dga_frame {
    char direction;
    char session[33];
    uint32_t command, sequence;
    char type[16];
    unsigned char payload[DGA_PAYLOAD_MAX];
    size_t length;
};

uint32_t dga_crc32(const char *data, size_t size);
/* Decode an own-line record without LF or the one optional trailing CR. */
const char *dga_decode(struct dga_frame *frame, const char *line, size_t size);
size_t dga_encode(char line[DGA_LINE_MAX], const struct dga_frame *frame);
int agent_main(void);
int agent_fixture_main(const char *name, int argc, char **argv);
#endif
