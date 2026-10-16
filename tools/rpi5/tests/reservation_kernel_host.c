/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <corecrypto/ccdigest.h>
static unsigned digest_calls;
static void counted_digest_init(const struct ccdigest_info *di,ccdigest_ctx_t ctx)
{digest_calls++;ccdigest_init(di,ctx);}
#define ccdigest_init counted_digest_init
#define SECURITY_READ_ONLY_LATE(t) t
#include "osfmk/arm64/rpi5_reservation_boot.inc"
#undef ccdigest_init
int main(int argc,char **argv)
{
    assert(argc==7);FILE *f=fopen(argv[1],"rb");assert(f);assert(!fseek(f,0,SEEK_END));
    long size=ftell(f);assert(size>40);rewind(f);unsigned char *data=malloc((size_t)size);assert(data);
    assert(fread(data,1,(size_t)size,f)==(size_t)size);fclose(f);
    struct rpi5_fdt_memory ram;struct rpi5_reservation_plan plan;struct rpi5_resolved_reservations resolved;
    assert(!rpi5_reservation_record_source(data,(size_t)size,&ram,&plan));
    struct rpi5_range live[]={{0x9000000,0xa300000},{0xb000000,0xb000000+(uint64_t)size}};
    assert(!rpi5_resolve_reservations(&ram,&plan,live,2,&resolved));
    struct rpi5_reservation_record r={0};struct rpi5_ranges fixed;
    assert(!rpi5_reservation_record_fixed(&plan,&fixed));
    r.fixed_count=fixed.count;for(unsigned i=0;i<fixed.count;i++)r.fixed[i]=fixed.extent[i];
    r.dynamic_count=plan.count;assert(r.dynamic_count==1);
    for(unsigned i=0;i<plan.count;i++)r.dynamic[i]=(struct rpi5_reservation_claim){plan.request[i].node_offset,
        plan.request[i].no_map,resolved.allocation[i].start,resolved.allocation[i].end,plan.request[i].alignment};
    r.managed_start=0x6000000;r.managed_end=0x10000000;r.loader_start=live[0].start;r.loader_end=live[0].end;
    r.kernel_start=0x7004000;r.kernel_end=0x8300000;r.args_pa=0x8300000;r.args_bytes=1152;
    r.tree_pa=0x8304000;r.tree_bytes=12000;r.top=0xb100000;r.fdt_pa=live[1].start;r.fdt_bytes=size;r.owner_counter=50;
    for(unsigned i=0;i<32;i++){unsigned byte;assert(sscanf(argv[2]+i*2,"%2x",&byte)==1);r.fdt_sha256[i]=(unsigned char)byte;}
    unsigned char wire[RPI5_RESERVATION_RECORD_BYTES];assert(!rpi5_reservation_record_encode(&r,wire,sizeof wire));
    struct rpi5_reservation_boot_context ctx={r.managed_start,r.managed_end,r.loader_start,r.loader_end,
        r.fdt_pa,r.fdt_bytes,r.args_pa,r.args_bytes,r.tree_pa,r.tree_bytes,r.top,r.kernel_start,r.kernel_end,60};
    assert(!rpi5_boot_reservation_record());
    for(unsigned i=3;i<7;i++){
        FILE *badfile=fopen(argv[i],"rb");assert(badfile);assert(!fseek(badfile,0,SEEK_END));
        long badsize=ftell(badfile);assert(badsize>40);rewind(badfile);
        unsigned char *bad=malloc((size_t)badsize);assert(bad);
        assert(fread(bad,1,(size_t)badsize,badfile)==(size_t)badsize);fclose(badfile);
        assert(rpi5_boot_reservation_bind(wire,sizeof wire,bad,(size_t)badsize,&ctx));
        assert(digest_calls==0);assert(!rpi5_boot_reservation_record());free(bad);
    }
    assert(!rpi5_boot_reservation_bind(wire,sizeof wire,data,(size_t)size,&ctx));
    assert(digest_calls==1);
    rpi5_boot_reservations_ready=1;
    assert(rpi5_boot_reservation_record()==&rpi5_boot_reservations);
    assert(!memcmp(&r,&rpi5_boot_reservations,sizeof r));
    assert(rpi5_boot_reservation_bind(wire,sizeof wire,data,(size_t)size,&ctx));
    /* Actual observed geometry: unresolved CMA may cover the entire managed
     * span, yet resolved exclusion is only0x80000..0x4080000. */
    assert(r.dynamic[0].start==0x80000 && r.dynamic[0].end==0x4080000);
    assert(!rpi5_reservation_kernel_buffer(&r,0xe000000,0x48000));
    assert(!rpi5_reservation_kernel_buffer(&r,0x6100000,0x48000));
    assert(rpi5_reservation_kernel_buffer(&r,0x3f00000,0x48000));
    assert(rpi5_reservation_kernel_buffer(&r,0x8000000,0x48000));
    assert(rpi5_reservation_kernel_buffer(&r,0xffc0000,0x48000));
    struct rpi5_reservation_record out,before;memset(&before,0xa5,sizeof before);out=before;unsigned failures=0;
    /* Every context field is actual independently derived state. */
    for(unsigned i=0;i<sizeof ctx/sizeof(uint64_t);i++){
        struct rpi5_reservation_boot_context bad=ctx;((uint64_t *)&bad)[i]^=1;
        if(i==13)bad.counter=49;
        assert(rpi5_reservation_kernel_validate(wire,sizeof wire,data,(size_t)size,&bad,r.fdt_sha256,&out));
        assert(!memcmp(&out,&before,sizeof out));failures++;
    }
    for(unsigned i=0;i<32;i++){
        unsigned char digest[32];memcpy(digest,r.fdt_sha256,32);digest[i]^=1;
        assert(rpi5_reservation_kernel_validate(wire,sizeof wire,data,(size_t)size,&ctx,digest,&out));
        assert(!memcmp(&out,&before,sizeof out));failures++;
    }
    for(unsigned i=0;i<sizeof wire;i++){
        unsigned char bad[sizeof wire];memcpy(bad,wire,sizeof bad);bad[i]^=0x80;
        assert(rpi5_reservation_kernel_validate(bad,sizeof bad,data,(size_t)size,&ctx,r.fdt_sha256,&out));
        assert(!memcmp(&out,&before,sizeof out));failures++;
    }
    /* Native-only reset of the static publication flag to exercise actual
     * digest mismatch; no production setter exists. */
    rpi5_boot_reservations_ready=0;
    data[size-1]^=1;assert(rpi5_boot_reservation_bind(wire,sizeof wire,data,(size_t)size,&ctx));
    assert(!memcmp(&r,&rpi5_boot_reservations,sizeof r));
    printf("ACTUAL_FDT_KERNEL_APPLE_SHA_BIND_PASS faults=%u managed_CMA_window_resolved_without_relaxation NO_HARDWARE\n",failures);
    free(data);return 0;
}
