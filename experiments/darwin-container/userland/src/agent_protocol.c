/* SPDX-License-Identifier: BSD-2-Clause */
#include "agent_protocol.h"

static int equal(const char *a, const char *b)
{
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}

static const char digits[] = "0123456789abcdef";

static int nibble(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}

static int hex_number(const char *s, size_t size, uint32_t *value)
{
    *value = 0;
    for (size_t i = 0; i < size; i++) {
        int n = nibble(s[i]);
        if (n < 0) return -1;
        *value = (*value << 4) | (unsigned)n;
    }
    return 0;
}

uint32_t dga_crc32(const char *data, size_t size)
{
    uint32_t crc = UINT32_C(0xffffffff);
    for (size_t i = 0; i < size; i++) {
        crc ^= (unsigned char)data[i];
        for (unsigned bit = 0; bit < 8; bit++)
            crc = (crc >> 1) ^ ((crc & 1) ? UINT32_C(0xedb88320) : 0);
    }
    return crc ^ UINT32_C(0xffffffff);
}

const char *dga_decode(struct dga_frame *frame, const char *line, size_t size)
{
    size_t start[9] = {0}, length[9], field = 0;
    if (!size || size >= DGA_LINE_MAX) return "frame_length";
    for (size_t i = 0; i < size; i++) {
        unsigned char c = (unsigned char)line[i];
        if (c < 32 || c > 126) return "frame_ascii";
        if (c == '|') {
            if (field == 8) return "frame_fields";
            length[field] = i - start[field];
            start[++field] = i + 1;
        }
    }
    if (field != 8) return "frame_fields";
    length[8] = size - start[8];
    if (length[0] != 4 || line[0] != 'D' || line[1] != 'G' || line[2] != 'A' || line[3] != '1')
        return "frame_version";
    if (length[1] != 1 || (line[start[1]] != 'H' && line[start[1]] != 'G')) return "frame_direction";
    frame->direction = line[start[1]];
    if (length[2] != 32) return "frame_session";
    for (size_t i = 0; i < 32; i++) {
        if (nibble(line[start[2] + i]) < 0) return "frame_session";
        frame->session[i] = line[start[2] + i];
    }
    frame->session[32] = 0;
    if (length[3] != 8 || hex_number(line + start[3], 8, &frame->command) ||
        length[4] != 8 || hex_number(line + start[4], 8, &frame->sequence)) return "frame_number";
    if (!frame->sequence) return "frame_sequence";
    if (!length[5] || length[5] >= sizeof(frame->type)) return "frame_type";
    for (size_t i = 0; i < length[5]; i++) {
        char c = line[start[5] + i];
        if ((c < 'A' || c > 'Z') && c != '_') return "frame_type";
        frame->type[i] = c;
    }
    frame->type[length[5]] = 0;
    const char *types[] = {"HELLO", "EXEC", "STARTED", "OUT", "ERR", "OUT_EOF", "ERR_EOF", "CANCEL",
                           "CANCELLED", "EXIT", "SHUTDOWN", "ERROR"};
    int known = 0;
    for (size_t i = 0; i < sizeof(types) / sizeof(types[0]); i++) if (equal(frame->type, types[i])) known = 1;
    if (!known) return "frame_type";
    uint32_t payload_length, crc;
    if (length[6] != 4 || hex_number(line + start[6], 4, &payload_length) ||
        payload_length > DGA_PAYLOAD_MAX || length[7] != 2 * payload_length) return "frame_payload";
    frame->length = payload_length;
    for (size_t i = 0; i < frame->length; i++) {
        uint32_t byte;
        if (hex_number(line + start[7] + i * 2, 2, &byte)) return "frame_payload";
        frame->payload[i] = (unsigned char)byte;
    }
    if (length[8] != 8 || hex_number(line + start[8], 8, &crc) ||
        dga_crc32(line, start[8] - 1) != crc) return "frame_crc";
    return 0;
}

static void append_hex(char *line, size_t *used, uint32_t value, unsigned width)
{
    for (unsigned i = width; i; i--) line[(*used)++] = digits[(value >> ((i - 1) * 4)) & 15];
}

size_t dga_encode(char line[DGA_LINE_MAX], const struct dga_frame *frame)
{
    if (frame->length > DGA_PAYLOAD_MAX) return 0;
    size_t n = 0;
    const char *prefix = "DGA1|";
    while (*prefix) line[n++] = *prefix++;
    line[n++] = frame->direction; line[n++] = '|';
    for (size_t i = 0; i < 32; i++) line[n++] = frame->session[i];
    line[n++] = '|'; append_hex(line, &n, frame->command, 8);
    line[n++] = '|'; append_hex(line, &n, frame->sequence, 8); line[n++] = '|';
    size_t type_size = 0;
    while (type_size < sizeof(frame->type) && frame->type[type_size]) line[n++] = frame->type[type_size++];
    if (!type_size || type_size == sizeof(frame->type)) return 0;
    line[n++] = '|'; append_hex(line, &n, (uint32_t)frame->length, 4); line[n++] = '|';
    for (size_t i = 0; i < frame->length; i++) append_hex(line, &n, frame->payload[i], 2);
    uint32_t crc = dga_crc32(line, n);
    line[n++] = '|'; append_hex(line, &n, crc, 8); line[n++] = '\n';
    return n;
}
