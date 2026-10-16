/* SPDX-License-Identifier: BSD-2-Clause */
/* Descriptor/worker execution model. Transport calls are deliberately stubbed;
 * the separate SDHCI tests cover register protocol. No device is opened. */
#include "rpi5_sd_transfer.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

struct fixture {
    uint8_t input[16384], output[16384], scratch[16384], device[16384];
    unsigned prepare, complete, copy_from, copy_to, checks, commands;
    unsigned fail_prepare, fail_complete, fail_copy_from, fail_copy_to, fail_command, cancel_at, revoke, revoke_at;
    enum rpi5_sd_transfer_kind direction;
    struct rpi5_sd_write_policy policy;
    struct rpi5_sd_card card;
};
static int prepare(void *context, enum rpi5_sd_transfer_kind kind)
{
    struct fixture *f=context; assert(!f->prepare++ && !f->complete); f->direction=kind;
    return f->fail_prepare?123:0;
}
static int complete(void *context, enum rpi5_sd_transfer_kind kind)
{
    struct fixture *f=context; assert(f->prepare==1 && !f->complete++ && kind==f->direction);
    return f->fail_complete?456:0;
}
static size_t copy_from(void *context, uint64_t offset, void *dst, size_t bytes)
{
    struct fixture *f=context; assert(!offset && !f->commands && f->direction==RPI5_SD_TRANSFER_WRITE);
    assert(bytes<=sizeof f->input); f->copy_from++; memcpy(dst,f->input,bytes);
    if (f->revoke) rpi5_sd_write_revoke(&f->policy);
    return bytes-(f->fail_copy_from?1:0);
}
static size_t copy_to(void *context, uint64_t offset, const void *src, size_t bytes)
{
    struct fixture *f=context; assert(offset+bytes<=sizeof f->output && f->direction==RPI5_SD_TRANSFER_READ);
    f->copy_to++; memcpy(f->output+offset,src,bytes);
    return bytes-(f->fail_copy_to==f->copy_to?1:0);
}
static int continuing(void *context)
{
    struct fixture *f=context;
    if (++f->checks==f->revoke_at) rpi5_sd_write_revoke(&f->policy);
    return f->checks!=f->cancel_at;
}
int rpi5_sd_read_sector(struct rpi5_sd_card *c, uint64_t block, void *dst, size_t bytes)
{
    struct fixture *f=c->io.context; assert(block>=1050624 && block<1050656 && bytes==512);
    assert(f->prepare==1 && !f->complete);
    if (++f->commands==f->fail_command) { c->ready=0; return RPI5_SD_CONTROLLER; }
    memcpy(dst,f->device+(block-1050624)*512,512); return 0;
}
int rpi5_sd_write_sector(struct rpi5_sd_card *c, struct rpi5_sd_write_policy *p,
    uint64_t epoch, uint64_t block, const void *src, size_t bytes)
{
    struct fixture *f=c->io.context; assert(rpi5_sd_write_request_valid(p,epoch,block,1,bytes));
    assert(f->prepare==1 && !f->complete && f->copy_from==1);
    memset(f->input,0,16384); /* Mutating caller bytes cannot change the owned snapshot. */
    if (++f->commands==f->fail_command) { c->ready=0; return RPI5_SD_CONTROLLER; }
    memcpy(f->device+(block-1050624)*512,src,512); return 0;
}
static void init(struct fixture *f)
{
    memset(f,0,sizeof *f); f->card=(struct rpi5_sd_card){.io.context=f,.ready=1,.sectors=250347520};
    f->policy=(struct rpi5_sd_write_policy){.epoch=9,.start=RPI5_SD_WRITE_START,
        .blocks=RPI5_SD_WRITE_BLOCKS,.max_request_blocks=RPI5_SD_WRITE_MAX_REQUEST_BLOCKS,
        .state=RPI5_SD_WRITE_ENABLED};
    for (unsigned i=0;i<16384;i++) f->input[i]=f->device[i]=(uint8_t)(i*13+17);
}
static struct rpi5_sd_buffer buffer(struct fixture *f, unsigned count)
{
    return (struct rpi5_sd_buffer){f,count*512,prepare,complete,copy_from,copy_to,continuing};
}
static struct rpi5_sd_transfer_result run(struct fixture *f, enum rpi5_sd_transfer_kind kind, unsigned count)
{
    struct rpi5_sd_buffer b=buffer(f,count);
    return rpi5_sd_transfer(&f->card,&f->policy,9,kind,1050624,count,&b,f->scratch,sizeof f->scratch);
}
int main(void)
{
    struct fixture f;
    for (unsigned count=1;count<=32;count++) for (unsigned op=1;op<=2;op++) {
        init(&f); struct rpi5_sd_transfer_result r=run(&f,(enum rpi5_sd_transfer_kind)op,count);
        assert(!r.status && r.actual_bytes==count*512 && r.attempted_sectors==count);
        assert(f.prepare==1 && f.complete==1 && f.commands==count);
        uint8_t *data=op==1?f.output:f.device;
        for (unsigned i=0;i<count*512;i++) assert(data[i]==(uint8_t)(i*13+17));
    }
    for (unsigned op=1;op<=2;op++) for (unsigned fault=0;fault<7;fault++) {
        init(&f);
        switch (fault) {
        case 0: f.fail_prepare=1; break;
        case 1: f.fail_complete=1; break;
        case 2: f.fail_command=2; break;
        case 3: f.cancel_at=1; break;
        case 4: f.cancel_at=3; break;
        case 5: if (op==2) f.fail_copy_from=1; else f.fail_copy_to=2; break;
        case 6: if (op==2) f.revoke=1; else f.cancel_at=2; break;
        }
        struct rpi5_sd_transfer_result r=run(&f,(enum rpi5_sd_transfer_kind)op,3);
        assert(r.status && f.commands<=3 && f.complete==(f.prepare && !f.fail_prepare?1u:0u));
        if (fault==0 || fault==3 || fault==6 || (fault==5 && op==2)) assert(!f.commands);
        if (fault==2 || fault==4 || (fault==5 && op==1)) assert(r.actual_bytes==512);
        if (op==2 && r.attempted_sectors) assert(!f.card.ready && f.policy.state==RPI5_SD_WRITE_QUARANTINED);
        if (op==1 && fault==2) assert(!f.card.ready && f.policy.state==RPI5_SD_WRITE_QUARANTINED);
        if (fault==1) assert(r.cleanup_status==456 && r.status==RPI5_SD_CLEANUP_ERROR);
        if (fault==0) assert(r.memory_status==123);
    }
    init(&f); struct rpi5_sd_buffer b=buffer(&f,2);
    assert(rpi5_sd_transfer(&f.card,&f.policy,9,RPI5_SD_TRANSFER_WRITE,2048,2,&b,f.scratch,16384).status);
    assert(rpi5_sd_transfer(&f.card,&f.policy,8,RPI5_SD_TRANSFER_WRITE,1050624,2,&b,f.scratch,16384).status);
    assert(rpi5_sd_transfer(&f.card,&f.policy,9,RPI5_SD_TRANSFER_WRITE,1050624,2,&b,f.scratch,512).status);
    assert(rpi5_sd_transfer(&f.card,&f.policy,9,RPI5_SD_TRANSFER_READ,1050624,2,&b,f.scratch,511).status);
    assert(rpi5_sd_transfer(&f.card,&f.policy,9,0,1050624,2,&b,f.scratch,16384).status);
    b.bytes--;
    assert(rpi5_sd_transfer(&f.card,&f.policy,9,RPI5_SD_TRANSFER_READ,1050624,2,&b,f.scratch,16384).status);
    assert(!f.prepare && !f.complete && !f.commands && !f.checks);
    /* A read-only caller need not have a write lease at all. */
    init(&f); b=buffer(&f,2);
    assert(!rpi5_sd_transfer(&f.card,0,0,RPI5_SD_TRANSFER_READ,1050624,2,&b,f.scratch,512).status);
    init(&f);
    b=buffer(&f,2); b.prepare=0;
    assert(rpi5_sd_transfer(&f.card,&f.policy,9,RPI5_SD_TRANSFER_READ,1050624,2,&b,f.scratch,16384).status);
    b=buffer(&f,2); b.complete=0;
    assert(rpi5_sd_transfer(&f.card,&f.policy,9,RPI5_SD_TRANSFER_WRITE,1050624,2,&b,f.scratch,16384).status);
    b=buffer(&f,2); b.copy_to=0;
    assert(rpi5_sd_transfer(&f.card,&f.policy,9,RPI5_SD_TRANSFER_READ,1050624,2,&b,f.scratch,16384).status);
    b=buffer(&f,2); b.copy_from=0;
    assert(rpi5_sd_transfer(&f.card,&f.policy,9,RPI5_SD_TRANSFER_WRITE,1050624,2,&b,f.scratch,16384).status);
    b=buffer(&f,2); b.continuing=0;
    assert(rpi5_sd_transfer(&f.card,&f.policy,9,RPI5_SD_TRANSFER_READ,1050624,2,&b,f.scratch,16384).status);
    b=buffer(&f,2);
    assert(rpi5_sd_transfer(0,&f.policy,9,RPI5_SD_TRANSFER_READ,1050624,2,&b,f.scratch,16384).status);
    assert(rpi5_sd_transfer(&f.card,&f.policy,9,RPI5_SD_TRANSFER_READ,1050624,2,0,f.scratch,16384).status);
    assert(rpi5_sd_transfer(&f.card,&f.policy,9,RPI5_SD_TRANSFER_READ,1050624,2,&b,0,16384).status);
    assert(!f.prepare && !f.complete && !f.commands && !f.checks);
    /* Even an invalid external epoch change between sectors cannot leak a
     * second write. Real ownership serialization prohibits this mutation. */
    init(&f); f.revoke_at=3;
    struct rpi5_sd_transfer_result revoked=run(&f,RPI5_SD_TRANSFER_WRITE,3);
    assert(revoked.status==RPI5_SD_INVALID && revoked.actual_bytes==512 && f.commands==1);
    assert(f.policy.state==RPI5_SD_WRITE_QUARANTINED && f.complete==1);
    init(&f); f.fail_command=2; f.fail_complete=1;
    struct rpi5_sd_transfer_result r=run(&f,RPI5_SD_TRANSFER_WRITE,3);
    assert(r.status==RPI5_SD_CONTROLLER && r.cleanup_status==456 && r.actual_bytes==512);
    puts("SD_TRANSFER_PASS"); return 0;
}
