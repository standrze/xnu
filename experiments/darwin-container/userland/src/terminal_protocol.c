/* SPDX-License-Identifier: BSD-2-Clause
 * Project-owned ASCII envelope, not an Apple userland implementation.
 */
#include "terminal_protocol.h"

static const char digits[]="0123456789abcdef";

static int number(const char *s, size_t n, uint32_t *value)
{
    *value=0;
    for (size_t i=0; i<n; i++) {
        unsigned v=(unsigned char)s[i];
        if (v>='0' && v<='9') v-='0';
        else if (v>='a' && v<='f') v=v-'a'+10;
        else return -1;
        *value=(*value<<4)|v;
    }
    return 0;
}

static uint32_t crc32(const char *s, size_t n)
{
    uint32_t crc=UINT32_MAX;
    for (size_t i=0; i<n; i++) {
        crc^=(unsigned char)s[i];
        for (unsigned j=0; j<8; j++) crc=(crc>>1)^((crc&1)?UINT32_C(0xedb88320):0);
    }
    return ~crc;
}

const char *dgt_decode(struct dgt_frame *f, const char *line, size_t n)
{
    size_t start[8]={0}, length[8], field=0;
    if (!n || n>=DGT_LINE_MAX) return "length";
    for (size_t i=0; i<n; i++) {
        if ((unsigned char)line[i]<32 || (unsigned char)line[i]>126) return "ascii";
        if (line[i]=='|') {
            if (field==7) return "fields";
            length[field]=i-start[field]; start[++field]=i+1;
        }
    }
    if (field!=7) return "fields";
    length[7]=n-start[7];
    if (length[0]!=4 || line[0]!='D' || line[1]!='G' || line[2]!='T' || line[3]!='1') return "version";
    if (length[1]!=1 || (line[start[1]]!='H' && line[start[1]]!='G')) return "direction";
    f->direction=line[start[1]];
    if (length[2]!=32) return "session";
    for (size_t i=0; i<32; i++) {
        uint32_t ignored;
        if (number(line+start[2]+i, 1, &ignored)) return "session";
        f->session[i]=line[start[2]+i];
    }
    f->session[32]=0;
    if (length[3]!=8 || number(line+start[3], 8, &f->sequence) || !f->sequence) return "sequence";
    if (!length[4] || length[4]>=sizeof f->type) return "type";
    for (size_t i=0; i<length[4]; i++) {
        char c=line[start[4]+i];
        if (c<'A' || c>'Z') return "type";
        f->type[i]=c;
    }
    f->type[length[4]]=0;
    uint32_t size, crc;
    if (length[5]!=4 || number(line+start[5], 4, &size) || size>DGT_PAYLOAD_MAX || length[6]!=2*size)
        return "payload";
    f->length=size;
    for (size_t i=0; i<size; i++) {
        uint32_t byte;
        if (number(line+start[6]+2*i, 2, &byte)) return "payload";
        f->payload[i]=(unsigned char)byte;
    }
    if (length[7]!=8 || number(line+start[7], 8, &crc) || crc!=crc32(line, start[7]-1)) return "crc";
    return 0;
}

static void hex(char *line, size_t *n, uint32_t v, unsigned width)
{
    for (unsigned i=width; i; i--) line[(*n)++]=digits[(v>>((i-1)*4))&15];
}

size_t dgt_encode(char line[DGT_LINE_MAX], const struct dgt_frame *f)
{
    if (f->length>DGT_PAYLOAD_MAX || !f->sequence) return 0;
    size_t n=0;
    const char *prefix="DGT1|";
    while (*prefix) line[n++]=*prefix++;
    line[n++]=f->direction; line[n++]='|';
    for (unsigned i=0; i<32; i++) line[n++]=f->session[i];
    line[n++]='|'; hex(line, &n, f->sequence, 8); line[n++]='|';
    size_t type_size=0;
    while (type_size<sizeof f->type && f->type[type_size]) line[n++]=f->type[type_size++];
    if (!type_size || type_size==sizeof f->type) return 0;
    line[n++]='|'; hex(line, &n, (uint32_t)f->length, 4); line[n++]='|';
    for (size_t i=0; i<f->length; i++) hex(line, &n, f->payload[i], 2);
    uint32_t crc=crc32(line, n);
    line[n++]='|'; hex(line, &n, crc, 8); line[n++]='\n';
    return n;
}
