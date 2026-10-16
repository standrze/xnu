/* SPDX-License-Identifier: BSD-2-Clause */
#include "firmware_seed.h"
#include "fdt.h"
int rpi5_firmware_seed_version(const void *fdt,size_t length)
{
    static const uint8_t version[]="6219bf00832ac18711372008da5ed99cf1c62ecf";
    static const uint8_t timestamp[]={0x6a,0x31,0xe5,0x1d};
    if (!fdt || !length || length>UINTPTR_MAX-(uintptr_t)fdt) return -1;
    struct rpi5_fdt_layout layout;
    struct rpi5_fdt_property v,t;
    if (rpi5_fdt_layout(fdt,length,&layout) || layout.total!=length ||
        rpi5_fdt_property(fdt,length,"/chosen/bootloader","version",&v) ||
        rpi5_fdt_property(fdt,length,"/chosen/bootloader","build-timestamp",&t) ||
        v.length!=sizeof version || t.length!=sizeof timestamp ||
        v.offset>length || v.length>length-v.offset ||
        t.offset>length || t.length>length-t.offset) return -1;
    const uint8_t *bytes=fdt;
    for(size_t i=0;i<sizeof version;i++) if(bytes[v.offset+i]!=version[i]) return -1;
    for(size_t i=0;i<sizeof timestamp;i++) if(bytes[t.offset+i]!=timestamp[i]) return -1;
    return 0;
}
int rpi5_firmware_seed_select(const void *fdt,size_t length,
    struct rpi5_fdt_property *out)
{
    uintptr_t base=(uintptr_t)fdt, result=(uintptr_t)out;
    if (!fdt || !out || !length || length>UINTPTR_MAX-base ||
        sizeof(*out)>UINTPTR_MAX-result ||
        (base<result+sizeof(*out) && result<base+length)) return -1;
    struct rpi5_fdt_layout layout;
    struct rpi5_fdt_property seed;
    if (rpi5_fdt_layout(fdt,length,&layout) || layout.total!=length ||
        rpi5_fdt_property(fdt,length,"/chosen","rng-seed",&seed) ||
        seed.length!=64 || seed.offset>length || 64>length-seed.offset) return -1;
    *out=seed;
    return 0;
}
