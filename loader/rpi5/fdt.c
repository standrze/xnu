/* SPDX-License-Identifier: BSD-2-Clause */
#include "fdt.h"
static uint32_t be32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}
static uint64_t be64(const uint8_t *p) { return ((uint64_t)be32(p) << 32) | be32(p + 4); }
int rpi5_fdt_initrd(const void *buffer, size_t available, struct rpi5_range *out)
{
    if (!out) return -1;
    struct rpi5_fdt_property start, end;
    int a=rpi5_fdt_property(buffer,available,"/chosen","linux,initrd-start",&start);
    int b=rpi5_fdt_property(buffer,available,"/chosen","linux,initrd-end",&end);
    if (a==-2 && b==-2) return 1;
    if (a || b || start.length!=end.length ||
        (start.length!=4 && start.length!=8)) return -1;
    const uint8_t *p=buffer;
    struct rpi5_range result={
        start.length==4 ? be32(p+start.offset) : be64(p+start.offset),
        end.length==4 ? be32(p+end.offset) : be64(p+end.offset)
    };
    if (result.start>=result.end || result.end>(1ull<<40)) return -1;
    *out=result;
    return 0;
}
static int overlap(uint32_t a, uint32_t n, uint32_t b, uint32_t m)
{
    return n && m && a < b + m && b < a + n;
}
int rpi5_fdt_layout(const void *buffer, size_t available, struct rpi5_fdt_layout *out)
{
    if (!buffer || !out || available < 40) return -1;
    const uint8_t *p = buffer;
    uint32_t total = be32(p + 4), version = be32(p + 20), compat = be32(p + 24);
    if (be32(p) != 0xd00dfeed || total < 40 || total > available ||
        total > 16u * 1024 * 1024 || version < 17 || compat > 17 || compat > version) return -1;
    struct rpi5_fdt_layout result = {
        total, be32(p + 8), be32(p + 36), be32(p + 12), be32(p + 32),
        be32(p + 16), 0, be32(p + 28)
    };
    if (result.structure < 40 || result.structure > total || (result.structure & 3) ||
        result.structure_size > total - result.structure || result.structure_size < 4 ||
        result.strings < 40 || result.strings > total || result.strings_size > total - result.strings ||
        result.reservations < 40 || result.reservations > total || (result.reservations & 7) ||
        overlap(result.structure, result.structure_size, result.strings, result.strings_size)) return -1;
    uint32_t pos = result.reservations;
    for (;;) {
        if (total - pos < 16 || overlap(pos, 16, result.structure, result.structure_size) ||
            overlap(pos, 16, result.strings, result.strings_size)) return -1;
        uint64_t address = be64(p + pos), size = be64(p + pos + 8);
        pos += 16;
        if (!address && !size) break;
        /* Reject an unrepresentable exclusive end; physical policy comes later. */
        if (!size || address > UINT64_MAX - size) return -1;
    }
    result.reservations_size = pos - result.reservations;
    *out = result;
    return 0;
}

int rpi5_fdt_structure(const void *buffer, size_t available)
{
    struct rpi5_fdt_layout layout;
    if (rpi5_fdt_layout(buffer, available, &layout)) return -1;
    const uint8_t *p = buffer;
    uint32_t pos = layout.structure, end = pos + layout.structure_size;
    unsigned depth = 0, root_seen = 0;
    uint8_t has_child[64];
    while (end - pos >= 4) {
        uint32_t token = be32(p + pos);
        pos += 4;
        if (token == 1) {
            if (depth == 64 || (!depth && root_seen)) return -1;
            uint32_t start = pos;
            while (pos < end && p[pos]) {
                if (p[pos] < 0x21 || p[pos] > 0x7e || p[pos] == '/') return -1;
                ++pos;
            }
            if (pos == end || (!depth && pos != start) || (depth && pos == start)) return -1;
            ++pos;
            while (pos & 3) { if (pos == end || p[pos++]) return -1; }
            if (depth) has_child[depth - 1] = 1;
            else root_seen = 1;
            has_child[depth++] = 0;
        } else if (token == 2) {
            if (!depth) return -1;
            --depth;
        } else if (token == 3) {
            if (!depth || has_child[depth - 1] || end - pos < 8) return -1;
            uint32_t length = be32(p + pos), name = be32(p + pos + 4);
            pos += 8;
            if (length > end - pos || name >= layout.strings_size) return -1;
            uint32_t cursor = layout.strings + name;
            uint32_t stop = layout.strings + layout.strings_size;
            if (!p[cursor]) return -1;
            while (cursor < stop && p[cursor]) {
                if (p[cursor] < 0x21 || p[cursor] > 0x7e) return -1;
                ++cursor;
            }
            if (cursor == stop) return -1;
            pos += length;
            /* Pi firmware can leave nonzero property alignment padding.
             * It is not value data; retain bounds/alignment, ignore contents. */
            while (pos & 3) { if (pos == end) return -1; ++pos; }
        } else if (token == 4) {
            continue;
        } else if (token == 9) {
            return root_seen && !depth && pos == end ? 0 : -1;
        } else return -1;
    }
    return -1;
}

static int equal(const uint8_t *a, const char *b)
{
    while (*a && *a == (uint8_t)*b) { ++a; ++b; }
    return *a == (uint8_t)*b;
}
static int value_equal(const uint8_t *a, uint32_t length, const char *b)
{
    uint32_t n = 0;
    while (b[n]) ++n;
    return length == n + 1 && equal(a, b);
}

int rpi5_fdt_compatible_count(const void *buffer, size_t available,
    const char *wanted, uint32_t *out)
{
    struct rpi5_fdt_layout layout;
    if (!wanted || !*wanted || !out || rpi5_fdt_structure(buffer,available) ||
        rpi5_fdt_layout(buffer,available,&layout)) return -1;
    const uint8_t *p=buffer;
    uint32_t pos=layout.structure, end=pos+layout.structure_size, count=0;
    while (pos<end) {
        uint32_t token=be32(p+pos); pos+=4;
        if (token==1) {
            while (p[pos]) pos++;
            pos=(pos+4)&~3u;
        } else if (token==3) {
            uint32_t length=be32(p+pos), name=be32(p+pos+4); pos+=8;
            if (equal(p+layout.strings+name,"compatible")) {
                uint32_t cursor=0;
                int matched=0;
                if (!length) return -1;
                while (cursor<length) {
                    uint32_t start=cursor;
                    while (cursor<length && p[pos+cursor]) cursor++;
                    if (cursor==length || cursor==start) return -1;
                    matched |= value_equal(p+pos+start,cursor-start+1,wanted);
                    cursor++;
                }
                count+=(uint32_t)matched;
            }
            pos=(pos+length+3)&~3u;
        }
    }
    *out=count;
    return 0;
}

int rpi5_fdt_phandles(const void *buffer, size_t available)
{
    struct rpi5_fdt_layout layout;
    if (rpi5_fdt_structure(buffer,available) || rpi5_fdt_layout(buffer,available,&layout)) return -1;
    const uint8_t *p=buffer;
    uint32_t handles[1024], count=0, value[64]={0}, seen[64]={0};
    uint32_t pos=layout.structure, depth=0;
    for (;;) {
        uint32_t token=be32(p+pos); pos+=4;
        if (token==1) {
            value[depth]=0; seen[depth]=0; depth++;
            while (p[pos]) pos++;
            pos=(pos+4)&~3u;
        } else if (token==2) depth--;
        else if (token==3) {
            uint32_t length=be32(p+pos), name=layout.strings+be32(p+pos+4);
            pos+=8;
            uint32_t bit=equal(p+name,"phandle")?1:equal(p+name,"linux,phandle")?2:0;
            if (bit) {
                if (length!=4 || (seen[depth-1]&bit)) return -1;
                uint32_t handle=be32(p+pos);
                if (!handle || handle==UINT32_MAX) return -1;
                if (seen[depth-1]) {
                    if (value[depth-1]!=handle) return -1;
                } else {
                    if (count==1024) return -1;
                    for (uint32_t i=0;i<count;i++) if (handles[i]==handle) return -1;
                    handles[count++]=handle;
                    value[depth-1]=handle;
                }
                seen[depth-1]|=bit;
            }
            pos=(pos+length+3)&~3u;
        } else if (token==9) return 0;
    }
}

int rpi5_fdt_property(const void *buffer, size_t available, const char *path,
    const char *property, struct rpi5_fdt_property *out)
{
    if (!path || path[0]!='/' || !property || !out) return -1;
    uint32_t begin[63], lengths[63], components=0, cursor=1;
    while (path[cursor]) {
        if (components==63 || cursor>=1024) return -1;
        begin[components]=cursor;
        while (path[cursor] && path[cursor]!='/') {
            if (cursor>=1024 || (uint8_t)path[cursor]<0x21 || (uint8_t)path[cursor]>0x7e) return -1;
            cursor++;
        }
        lengths[components]=cursor-begin[components];
        if (!lengths[components++]) return -1;
        if (path[cursor]=='/' && !path[++cursor]) return -1;
    }
    size_t key=0;
    while (property[key]) {
        if (key>=255 || (uint8_t)property[key]<0x21 || (uint8_t)property[key]>0x7e) return -1;
        key++;
    }
    if (!key) return -1;
    struct rpi5_fdt_layout layout;
    if (rpi5_fdt_structure(buffer,available) || rpi5_fdt_layout(buffer,available,&layout)) return -1;
    const uint8_t *p=buffer;
    uint8_t matched[64]={0}, seen[64]={0};
    uint32_t pos=layout.structure, depth=0, target_node=0;
    int found=0;
    struct rpi5_fdt_property result={0};
    for (;;) {
        uint32_t node_pos=pos, token=be32(p+pos); pos+=4;
        if (token==1) {
            uint32_t name=pos;
            while (p[pos]) pos++;
            uint32_t length=pos-name;
            matched[depth]=depth==0;
            if (depth && depth<=components && matched[depth-1] && length==lengths[depth-1]) {
                matched[depth]=1;
                for (uint32_t i=0;i<length;i++)
                    if (p[name+i]!=(uint8_t)path[begin[depth-1]+i]) matched[depth]=0;
            }
            if (matched[depth]) {
                if (seen[depth]++) return -1;
                if (depth==components) target_node=node_pos;
            }
            depth++;
            pos=(pos+4)&~3u;
        } else if (token==2) depth--;
        else if (token==3) {
            uint32_t length=be32(p+pos), name=layout.strings+be32(p+pos+4);
            pos+=8;
            if (depth==components+1 && matched[depth-1] && equal(p+name,property)) {
                if (found++) return -1;
                result=(struct rpi5_fdt_property){pos,length,target_node};
            }
            pos=(pos+length+3)&~3u;
        } else if (token==9) break;
    }
    if (!found) return -2;
    *out=result;
    return 0;
}

int rpi5_fdt_psci_smc(const void *buffer, size_t available)
{
    struct rpi5_fdt_layout layout;
    if (rpi5_fdt_structure(buffer, available) || rpi5_fdt_layout(buffer, available, &layout)) return -1;
    const uint8_t *p = buffer;
    uint32_t pos = layout.structure, depth = 0, selected = 0, nodes = 0, seen = 0;
    for (;;) {
        uint32_t token = be32(p + pos); pos += 4;
        if (token == 1) {
            uint32_t name = pos;
            while (p[pos]) ++pos;
            pos = (pos + 4) & ~3u;
            if (++depth == 2 && equal(p + name, "psci")) {
                if (nodes++) return -1;
                selected = 1;
            }
        } else if (token == 2) {
            if (depth == 2) selected = 0;
            --depth;
        } else if (token == 3) {
            uint32_t length = be32(p + pos), name = layout.strings + be32(p + pos + 4);
            pos += 8; const uint8_t *value = p + pos;
            pos = (pos + length + 3) & ~3u;
            if (!selected || depth != 2) continue;
            uint32_t bit = equal(p + name, "method") ? 1 : equal(p + name, "compatible") ? 2 : equal(p + name, "status") ? 4 : 0;
            if (seen & bit) return -1;
            seen |= bit;
            if (bit == 1 && !value_equal(value, length, "smc")) return -1;
            if (bit == 4 && !value_equal(value, length, "okay") && !value_equal(value, length, "ok")) return -1;
            if (bit == 2) {
                uint32_t cursor = 0, matched = 0;
                while (cursor < length) {
                    uint32_t start = cursor;
                    while (cursor < length && value[cursor]) ++cursor;
                    if (cursor == length || cursor == start) return -1;
                    ++cursor;
                    matched |= value_equal(value + start, cursor - start, "arm,psci-1.0") ||
                        value_equal(value + start, cursor - start, "arm,psci-0.2");
                }
                if (!matched) return -1;
            }
        } else if (token == 9) return nodes == 1 && (seen & 3) == 3 ? 0 : -1;
    }
}

int rpi5_fdt_cpus(const void *buffer, size_t available, struct rpi5_fdt_cpus *out)
{
    struct rpi5_fdt_layout layout;
    if (!out || rpi5_fdt_structure(buffer, available) || rpi5_fdt_layout(buffer, available, &layout)) return -1;
    const uint8_t *p = buffer;
    struct rpi5_fdt_cpus result = {{0}, 0, 0};
    uint32_t names[4], pos = layout.structure, depth = 0, in_cpus = 0, found = 0;
    uint32_t cells = 0, container_seen = 0, cpu_seen = 0, cpu_active = 0, enabled = 1;
    uint64_t affinity = 0;
    for (;;) {
        uint32_t token = be32(p + pos); pos += 4;
        if (token == 1) {
            uint32_t name = pos;
            while (p[pos]) ++pos;
            pos = (pos + 4) & ~3u;
            ++depth;
            if (depth == 2 && equal(p + name, "cpus")) {
                if (found++) return -1;
                in_cpus = 1;
            } else if (in_cpus && depth == 3) {
                cpu_active = p[name] == 'c' && p[name+1] == 'p' && p[name+2] == 'u' && p[name+3] == '@';
                if (cpu_active) {
                    if (container_seen != 3 || result.count == 4) return -1;
                    for (uint32_t i = 0; i < result.count; ++i)
                        if (equal(p + name, (const char *)p + names[i])) return -1;
                    names[result.count] = name;
                    cpu_seen = 0; enabled = 1; affinity = 0;
                }
            }
        } else if (token == 2) {
            if (in_cpus && depth == 3 && cpu_active) {
                if ((cpu_seen & 15) != 15 || (affinity & ~0xff00ffffffull)) return -1;
                for (uint32_t i = 0; i < result.count; ++i) if (result.affinity[i] == affinity) return -1;
                result.affinity[result.count] = affinity;
                result.enabled_mask |= enabled << result.count;
                ++result.count; cpu_active = 0;
            }
            if (depth == 2) in_cpus = 0;
            --depth;
        } else if (token == 3) {
            uint32_t length = be32(p + pos), name = layout.strings + be32(p + pos + 4);
            pos += 8; const uint8_t *value = p + pos;
            pos = (pos + length + 3) & ~3u;
            if (in_cpus && depth == 2) {
                uint32_t bit = equal(p + name, "#address-cells") ? 1 : equal(p + name, "#size-cells") ? 2 : 0;
                if (bit) {
                    if ((container_seen & bit) || length != 4) return -1;
                    container_seen |= bit;
                    if (bit == 1) { cells = be32(value); if (cells != 1 && cells != 2) return -1; }
                    else if (be32(value)) return -1;
                } else if (equal(p + name, "status")) return -1; /* unsupported container status */
            } else if (in_cpus && depth == 3 && !cpu_active && equal(p + name, "device_type") && value_equal(value, length, "cpu")) {
                return -1; /* CPU binding with an unsupported node-name form. */
            } else if (in_cpus && depth == 3 && cpu_active) {
                uint32_t bit = equal(p + name, "device_type") ? 1 : equal(p + name, "compatible") ? 2 :
                    equal(p + name, "reg") ? 4 : equal(p + name, "enable-method") ? 8 : equal(p + name, "status") ? 16 : 0;
                if (bit && (cpu_seen & bit)) return -1;
                cpu_seen |= bit;
                if (bit == 1 && !value_equal(value, length, "cpu")) return -1;
                if (bit == 2 && !value_equal(value, length, "arm,cortex-a76")) return -1;
                if (bit == 8 && !value_equal(value, length, "psci")) return -1;
                if (bit == 4) { if (length != cells * 4) return -1; affinity = cells == 1 ? be32(value) : be64(value); }
                if (bit == 16) {
                    if (value_equal(value, length, "disabled")) enabled = 0;
                    else if (!value_equal(value, length, "okay") && !value_equal(value, length, "ok")) return -1;
                }
            }
        } else if (token == 9) {
            if (!found || container_seen != 3 || !result.count || !result.enabled_mask) return -1;
            *out = result; return 0;
        }
    }
}

static int prefix(const uint8_t *a, const char *b)
{
    while (*b) if (*a++ != (uint8_t)*b++) return 0;
    return 1;
}

static int reserve_append(struct rpi5_ranges *r, uint64_t address, uint64_t size)
{
    if (!size || address >= (1ull << 40) || size > (1ull << 40) - address || r->count == 32) return -1;
    r->extent[r->count++] = (struct rpi5_range){address, address + size};
    return 0;
}
int rpi5_fdt_reservation_plan(const void *buffer, size_t available, struct rpi5_reservation_plan *out)
{
    struct rpi5_fdt_layout l;
    if (!out || rpi5_fdt_structure(buffer, available) || rpi5_fdt_layout(buffer, available, &l)) return -1;
    const uint8_t *p = buffer;
    struct rpi5_reservation_plan result = {0};
    for (uint32_t pos = l.reservations; pos + 16 < l.reservations + l.reservations_size; pos += 16)
        if (reserve_append(&result.fixed, be64(p + pos), be64(p + pos + 8))) return -1;
    uint32_t pos=l.structure, depth=0, root_seen=0, root_ac=0, root_sc=0;
    uint32_t container=0, containers=0, container_seen=0, ac=0, sc=0;
    uint32_t seen=0, disabled=0, dynamic=0, nested=0, reg=0, reglen=0;
    uint32_t sizepos=0, sizelen=0, alignpos=0, alignlen=0, windowpos=0, windowlen=0, node=0;
    for (;;) {
        uint32_t token=be32(p+pos); pos+=4;
        if (token==1) {
            uint32_t name=pos; while (p[pos]) ++pos; pos=(pos+4)&~3u; ++depth;
            if (depth==2 && prefix(p+name,"reserved-memory@")) return -2;
            if (depth==2 && equal(p+name,"reserved-memory")) {
                if (containers++) return -1;
                container=1;
            } else if (container && depth==3) {
                if (root_seen!=3 || container_seen!=7 || ac!=root_ac || sc!=root_sc) return -1;
                seen=disabled=dynamic=nested=reg=reglen=0;
                sizepos=sizelen=alignpos=alignlen=windowpos=windowlen=0;
                node=name-4;
            } else if (container && depth>3) nested=1;
        } else if (token==2) {
            if (container && depth==3 && !disabled) {
                if (dynamic || nested) return -2;
                if ((seen&24)==24) return -1;
                if (seen&1) {
                    if (!reglen || reglen%(4*(ac+sc))) return -1;
                    for (uint32_t cursor=reg; cursor<reg+reglen; cursor+=4*(ac+sc))
                    if (reserve_append(&result.fixed, ac==1?be32(p+cursor):be64(p+cursor),
                        sc==1?be32(p+cursor+4*ac):be64(p+cursor+4*ac))) return -1;
                } else {
                    if (!(seen&4) || sizelen!=4*sc || result.count==8) return -1;
                    struct rpi5_dynamic_reservation *r=&result.request[result.count++];
                    r->size=sc==1?be32(p+sizepos):be64(p+sizepos);
                    r->alignment=1; r->node_offset=node; r->no_map=!!(seen&8);
                    if (seen&64) {
                        if (alignlen!=4*sc) return -1;
                        r->alignment=sc==1?be32(p+alignpos):be64(p+alignpos);
                    }
                    if (!r->size || r->size>(1ull<<40) || !r->alignment ||
                        r->alignment>(1ull<<40) || (r->alignment&(r->alignment-1))) return -1;
                    if (seen&128) {
                        uint32_t stride=4*(ac+sc);
                        if (!windowlen || windowlen%stride || windowlen/stride>8) return -1;
                        for(uint32_t cursor=windowpos;cursor<windowpos+windowlen;cursor+=stride) {
                            uint64_t a=ac==1?be32(p+cursor):be64(p+cursor);
                            uint64_t n=sc==1?be32(p+cursor+4*ac):be64(p+cursor+4*ac);
                            if (!n || a>=(1ull<<40) || n>(1ull<<40)-a) return -1;
                            r->window[r->window_count++]=(struct rpi5_range){a,a+n};
                        }
                    } else {
                        r->window[0]=(struct rpi5_range){0,1ull<<40}; r->window_count=1;
                    }
                }
            }
            if (depth==2) {
                if (container && (root_seen!=3 || container_seen!=7 || ac!=root_ac || sc!=root_sc)) return -1;
                container=0;
            }
            --depth;
        } else if (token==3) {
            uint32_t length=be32(p+pos), name=l.strings+be32(p+pos+4); pos+=8;
            uint32_t value=pos; pos=(pos+length+3)&~3u;
            if (depth==1 || (container && depth==2)) {
                uint32_t bit=equal(p+name,"#address-cells")?1:equal(p+name,"#size-cells")?2:0;
                uint32_t *fields=depth==1?&root_seen:&container_seen;
                if (bit) {
                    if ((*fields&bit) || length!=4) return -1;
                    uint32_t cells=be32(p+value); if (cells!=1 && cells!=2) return -1;
                    *fields|=bit;
                    if (depth==1) { if(bit==1) root_ac=cells; else root_sc=cells; }
                    else { if(bit==1) ac=cells; else sc=cells; }
                } else if (container && depth==2 && equal(p+name,"ranges")) {
                    if ((container_seen&4) || length) return -1; container_seen|=4;
                } else if (container && depth==2 && equal(p+name,"status")) return -2;
            } else if (container && depth==3) {
                uint32_t bit=equal(p+name,"reg")?1:equal(p+name,"status")?2:equal(p+name,"size")?4:
                    equal(p+name,"no-map")?8:equal(p+name,"reusable")?16:equal(p+name,"iommu-addresses")?32:
                    equal(p+name,"alignment")?64:equal(p+name,"alloc-ranges")?128:0;
                if (seen&bit) return -1; seen|=bit;
                if(bit==1) { reg=value; reglen=length; }
                if(bit==4) { sizepos=value; sizelen=length; }
                if(bit==64) { alignpos=value; alignlen=length; }
                if(bit==128) { windowpos=value; windowlen=length; }
                if(bit==32) dynamic=1;
                if((bit==8 || bit==16) && length) return -1;
                if(bit==2) {
                    if(value_equal(p+value,length,"disabled")) disabled=1;
                    else if(!value_equal(p+value,length,"okay") && !value_equal(p+value,length,"ok")) return -2;
                }
            }
        } else if(token==9) { *out=result; return 0; }
    }
}

int rpi5_fdt_reservations(const void *buffer, size_t available, struct rpi5_ranges *out)
{
    struct rpi5_reservation_plan plan;
    if (!out) return -1;
    int status=rpi5_fdt_reservation_plan(buffer,available,&plan);
    if (status) return status;
    if (plan.count) return -2;
    *out=plan.fixed; return 0;
}

int rpi5_fdt_memory(const void *buffer, size_t available, struct rpi5_fdt_memory *out)
{
    struct rpi5_fdt_layout layout;
    if (!out || rpi5_fdt_structure(buffer, available) || rpi5_fdt_layout(buffer, available, &layout)) return -1;
    const uint8_t *p = buffer;
    struct rpi5_fdt_memory result = {{0}, {0}, 0};
    uint32_t pos = layout.structure, depth = 0, selected = 0, widths = 0, ac = 0, sc = 0;
    uint32_t seen = 0, enabled = 0, reg = 0, length_reg = 0;
    for (;;) {
        uint32_t token = be32(p + pos); pos += 4;
        if (token == 1) {
            uint32_t name = pos;
            while (p[pos]) ++pos;
            pos = (pos + 4) & ~3u;
            ++depth;
            if (depth == 2) {
                selected = equal(p + name, "memory") || prefix(p + name, "memory@");
                seen = 0; enabled = 1;
            } else if (selected && depth > 2) return -1;
        } else if (token == 2) {
            if (selected && depth == 2) {
                if (widths != 3 || (seen & 3) != 3 || !length_reg || length_reg % (4 * (ac + sc))) return -1;
                if (enabled) for (uint32_t cursor = reg; cursor < reg + length_reg; cursor += 4 * (ac + sc)) {
                    uint64_t address = ac == 1 ? be32(p + cursor) : be64(p + cursor);
                    uint64_t size = sc == 1 ? be32(p + cursor + 4 * ac) : be64(p + cursor + 4 * ac);
                    if (!size || address >= (1ull << 40) || size > (1ull << 40) - address || result.count == 8) return -1;
                    uint32_t index = result.count;
                    for (uint32_t i = 0; i < result.count; ++i) {
                        if (address < result.end[i] && result.start[i] < address + size) return -1;
                        if (address < result.start[i] && index == result.count) index = i;
                    }
                    for (uint32_t i = result.count; i > index; --i) {
                        result.start[i] = result.start[i - 1]; result.end[i] = result.end[i - 1];
                    }
                    result.start[index] = address; result.end[index] = address + size; ++result.count;
                }
            }
            if (depth == 2) selected = 0;
            --depth;
        } else if (token == 3) {
            uint32_t length = be32(p + pos), name = layout.strings + be32(p + pos + 4);
            pos += 8; uint32_t value = pos;
            pos = (pos + length + 3) & ~3u;
            if (depth == 1) {
                uint32_t bit = equal(p + name, "#address-cells") ? 1 : equal(p + name, "#size-cells") ? 2 : 0;
                if (bit) {
                    if ((widths & bit) || length != 4) return -1;
                    uint32_t cells = be32(p + value);
                    if (cells != 1 && cells != 2) return -1;
                    widths |= bit; if (bit == 1) ac = cells; else sc = cells;
                }
            } else if (depth == 2 && selected) {
                uint32_t bit = equal(p + name, "device_type") ? 1 : equal(p + name, "reg") ? 2 : equal(p + name, "status") ? 4 : 0;
                if (seen & bit) return -1;
                seen |= bit;
                if (bit == 1 && !value_equal(p + value, length, "memory")) return -1;
                if (bit == 2) { reg = value; length_reg = length; }
                if (bit == 4) {
                    if (value_equal(p + value, length, "disabled")) enabled = 0;
                    else if (!value_equal(p + value, length, "okay") && !value_equal(p + value, length, "ok")) return -1;
                }
            } else if (depth == 2 && equal(p + name, "device_type") && value_equal(p + value, length, "memory")) return -1;
        } else if (token == 9) {
            if (!result.count) return -1;
            *out = result; return 0;
        }
    }
}
