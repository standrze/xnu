/* SPDX-License-Identifier: BSD-2-Clause */
#include "display_mailbox_transaction.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

struct model {
    struct rpi5_display_mailbox_session session;
    struct rpi5_display_mailbox_fdt binding;
    struct rpi5_display_mailbox_buffer buffers[3];
    struct rpi5_display_mailbox_ops ops;
    struct rpi5_display_mailbox_result result;
    _Alignas(16) unsigned char bytes[3][128];
    uint64_t time;
    unsigned count, callback, owners, fail_callback, fail_owner;
    unsigned tx, pop, peek, admitted, publish, acquire, prepared[3], acquired[3];
    unsigned head_valid, head, initially_busy, tx_busy, rx_wait, forever_tx, forever_rx;
    unsigned wrong_head, wrong_pop, bad_reply, extra_reply, backwards, stuck, leap, revoke;
    unsigned mutate_binding, mutate_buffer, mutate_ops, reenter, inside, last_guard, tx_slots;
    unsigned mutate_session, tx_status_reads, initial_tx_busy;
    unsigned owner_mutate, owner_reenter;
};
static void put(unsigned char *p,uint32_t value)
{for(unsigned i=0;i<4;i++)p[i]=(unsigned char)(value>>(8*i));}
static uint32_t get(const unsigned char *p)
{return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static int event(struct model *m)
{
    assert(m->last_guard);m->last_guard=0;
    m->callback++;
    if(m->revoke==m->callback)m->fail_owner=m->owners+1;
    if(m->mutate_binding==m->callback)m->binding.fdt_bytes++;
    if(m->mutate_buffer==m->callback)m->buffers[0].mailbox_address+=16;
    if(m->mutate_ops==m->callback)m->ops.context=NULL;
    if(m->mutate_session==m->callback)m->session.deadline_us=UINT64_MAX;
    if(m->reenter==m->callback){
        assert(rpi5_display_mailbox_query(&m->session,&m->binding,m->buffers,&m->ops,
            42,1000000,&m->result)!=0);
    }
    return m->callback==m->fail_callback ? -1 : 0;
}
static int current(void *p,const struct rpi5_display_mailbox_session *s,
    const struct rpi5_display_mailbox_fdt *f,const struct rpi5_display_mailbox_buffer *b,uint64_t owner)
{
    struct model *m=p;m->owners++;
    assert(s==&m->session && f==&m->binding && b==m->buffers && owner==42);
    assert(!m->inside);m->last_guard=1;
    if(m->owner_mutate==m->owners)m->session.deadline_us=UINT64_MAX;
    if(m->owner_reenter==m->owners)
        assert(rpi5_display_mailbox_query(&m->session,&m->binding,m->buffers,&m->ops,
            42,1000000,&m->result)!=0);
    return m->owners==m->fail_owner ? -1 : 0;
}
static int admit(void *p,unsigned slot,const struct rpi5_display_mailbox_buffer *b,
    const struct rpi5_display_mailbox_fdt *f)
{
    struct model *m=p;int rc=event(m);if(rc)return rc;
    assert(b==&m->buffers[slot] && f==&m->binding && slot<3);
    assert(!(m->admitted&(1u<<slot)));m->admitted|=1u<<slot;return 0;
}
static int now(void *p,uint64_t *value)
{
    struct model *m=p;int rc=event(m);if(rc)return rc;
    if(m->backwards && m->callback>=m->backwards){*value=0;return 0;}
    if(!m->stuck)m->time++;
    if(m->leap && m->callback>=m->leap)m->time+=1000000;
    *value=m->time;return 0;
}
static int rd(void *p,uint32_t offset,uint32_t *value)
{
    struct model *m=p;int rc=event(m);if(rc)return rc;
    if(offset==RPI5_DISPLAY_MBOX_RX_STATUS){
        if(m->initially_busy && !m->tx){*value=0;return 0;}
        if(m->forever_rx && m->tx){*value=RPI5_DISPLAY_MBOX_EMPTY;return 0;}
        if(m->rx_wait && m->head_valid){m->rx_wait--;*value=RPI5_DISPLAY_MBOX_EMPTY;return 0;}
        *value=m->head_valid ? 0 : RPI5_DISPLAY_MBOX_EMPTY;return 0;
    }
    if(offset==RPI5_DISPLAY_MBOX_TX_STATUS){
        if(!m->tx_status_reads++){*value=m->initial_tx_busy ? 0 : RPI5_DISPLAY_MBOX_EMPTY;return 0;}
        if(m->forever_tx || m->tx_busy){if(m->tx_busy)m->tx_busy--;*value=RPI5_DISPLAY_MBOX_FULL;}
        else *value=RPI5_DISPLAY_MBOX_EMPTY;
        return 0;
    }
    if(offset==RPI5_DISPLAY_MBOX_PEEK){assert(m->head_valid);m->peek++;*value=m->head;return 0;}
    assert(offset==RPI5_DISPLAY_MBOX_RX && m->head_valid && m->peek>m->pop);
    assert(m->head==m->session.expected_word);m->pop++;
    *value=m->wrong_pop ? m->head^16 : m->head;
    m->head_valid=m->extra_reply!=0;return 0;
}
static int wr(void *p,uint32_t offset,uint32_t value)
{
    struct model *m=p;int rc=event(m);if(rc)return rc;
    unsigned slot=m->session.slot;
    assert(offset==RPI5_DISPLAY_MBOX_TX && slot<3 && !(m->tx_slots&(1u<<slot)));
    assert(value==0x200008u+slot*4096 && m->prepared[slot]);
    assert(!m->head_valid);m->tx_slots|=1u<<slot;m->tx++;
    m->head_valid=1;m->head=m->wrong_head ? value^m->wrong_head : value;return 0;
}
static int caching(void *p,unsigned slot,const struct rpi5_display_mailbox_buffer *b,
    size_t bytes,enum rpi5_display_mailbox_cache direction)
{
    struct model *m=p;int rc=event(m);if(rc)return rc;
    assert(b==&m->buffers[slot] && bytes==(slot ? 88u : 28u));
    unsigned char *wire=b->cpu;
    if(direction==RPI5_DISPLAY_MBOX_PUBLISH){
        assert(!m->prepared[slot] && !get(wire+4) && !get(wire+16));
        assert(get(wire+8)==(slot ? 0x40014u : 0x40013u));
        assert(get(wire+20)==(slot ? slot-1 : 0));
        m->prepared[slot]=1;m->publish++;return 0;
    }
    assert(direction==RPI5_DISPLAY_MBOX_ACQUIRE && m->pop==slot+1 && !m->acquired[slot]);
    m->acquired[slot]=1;m->acquire++;
    put(wire+4,0x80000000);put(wire+16,0x80000000u|(slot ? 64u : 4u));
    if(!slot)put(wire+20,m->count);
    else for(unsigned i=1;i<16;i++)put(wire+20+4*i,0xffff0000u|slot<<8|i);
    if(m->bad_reply)put(wire+m->bad_reply,0xffffffffu);
    return 0;
}
static void setup(struct model *m)
{
    memset(m,0,sizeof *m);m->count=2;m->time=100;
    m->binding.mmio=(struct rpi5_range){0x107c013880,0x107c0138c0};
    m->binding.fdt_bytes=0x13a32;m->binding.dma_profile=RPI5_MAILBOX_DMA_PI5_NO_RANGES_DIRECT;
    for(unsigned i=0;i<3;i++)m->buffers[i]=(struct rpi5_display_mailbox_buffer){m->bytes[i],128,0x200000+i*4096};
    m->ops=(struct rpi5_display_mailbox_ops){m,current,admit,now,rd,wr,caching};
    memset(&m->result,0xa5,sizeof m->result);
}
static int run(struct model *m)
{return rpi5_display_mailbox_query(&m->session,&m->binding,m->buffers,&m->ops,42,1000000,&m->result);}
static void failed(struct model *m)
{
    unsigned char sentinel[sizeof m->result];memset(sentinel,0xa5,sizeof sentinel);
    assert(run(m)<0);assert(m->session.state==RPI5_DISPLAY_MBOX_QUARANTINED);
    assert(!m->session.busy && m->session.quarantined_buffers==7 && m->session.error<0);
    assert(!memcmp(&m->result,sentinel,sizeof sentinel));
    unsigned tx=m->tx,pop=m->pop,callback=m->callback,owner=m->owners;
    assert(run(m)<0);assert(m->tx==tx && m->pop==pop && m->callback==callback && m->owners==owner);
}
static void success(void)
{
    struct model m;
    for(unsigned count=0;count<=2;count++){
        setup(&m);m.count=count;m.tx_busy=2;m.rx_wait=3;
        int rc=run(&m);if(rc)fprintf(stderr,"rc=%d stage=%u callback=%u owner=%u tx=%u\n",rc,m.session.stage,m.callback,m.owners,m.tx);
        assert(!rc);
        assert(m.result.count==count && m.result.count_reply.words[0]==count);
        assert(m.session.state==RPI5_DISPLAY_MBOX_COMPLETE && !m.session.busy);
        assert(m.tx==count+1 && m.pop==count+1 && m.peek==count+1);
        assert(m.publish==count+1 && m.acquire==count+1 && m.admitted==(1u<<(count+1))-1);
        assert(m.session.completed==m.admitted && m.session.tx_attempted==m.admitted);
        for(unsigned i=0;i<count;i++){
            assert(m.result.settings[i].words[0]==i && m.result.settings[i].word_count==16);
            assert(m.result.settings[i].words[15]==(0xffff0000u|(i+1)<<8|15));
        }
        for(unsigned i=0;i<3;i++)for(unsigned j=i ? 88 : 28;j<128;j++)assert(!m.bytes[i][j]);
        unsigned calls=m.callback;assert(run(&m)<0 && calls==m.callback);
    }
    puts("DISPLAY_MBOX_SUCCESS PASS COUNT=0,1,2 DISTINCT_BUFFERS=3 RAW_ONLY=1");
}
static void faults(void)
{
    struct model m;setup(&m);assert(!run(&m));unsigned callbacks=m.callback,owners=m.owners;
    for(unsigned i=1;i<=callbacks;i++){
        setup(&m);m.fail_callback=i;failed(&m);
        setup(&m);m.revoke=i;failed(&m);
        setup(&m);m.reenter=i;failed(&m);
        setup(&m);m.mutate_binding=i;failed(&m);
        setup(&m);m.mutate_buffer=i;failed(&m);
        setup(&m);m.mutate_ops=i;failed(&m);
        setup(&m);m.mutate_session=i;failed(&m);
    }
    for(unsigned i=1;i<=owners;i++){
        setup(&m);m.fail_owner=i;failed(&m);
        setup(&m);m.owner_mutate=i;failed(&m);
        setup(&m);m.owner_reenter=i;failed(&m);
    }
    printf("DISPLAY_MBOX_FAULTS PASS CALLBACKS=%u OWNERS=%u NO_RETRY=1 OUTPUT_ATOMIC=1\n",callbacks,owners);
}
static void bounds(void)
{
    struct model m;
    setup(&m);m.initially_busy=1;failed(&m);assert(!m.tx && !m.pop && !m.peek);
    setup(&m);m.initial_tx_busy=1;failed(&m);assert(!m.tx && !m.pop && !m.peek);
    for(unsigned bit=0;bit<32;bit++){
        setup(&m);m.wrong_head=1u<<bit;failed(&m);assert(m.tx==1 && !m.pop && m.head_valid);
    }
    setup(&m);m.wrong_pop=1;failed(&m);assert(m.tx==1 && m.pop==1);
    setup(&m);m.extra_reply=1;failed(&m);assert(m.tx==1 && m.pop==1 && m.head_valid);
    setup(&m);m.forever_tx=1;m.stuck=1;failed(&m);assert(!m.tx && m.session.polls==512);
    setup(&m);m.forever_rx=1;m.stuck=1;failed(&m);assert(m.tx==1 && !m.pop && m.session.polls==512);
    setup(&m);m.backwards=2;failed(&m);assert(!m.tx);
    setup(&m);m.leap=2;failed(&m);assert(!m.tx);
    setup(&m);assert(!run(&m));unsigned calls=m.callback;
    for(unsigned i=2;i<=calls;i++){
        setup(&m);m.backwards=i;failed(&m);
        setup(&m);m.leap=i;failed(&m);
    }
    setup(&m);assert(rpi5_display_mailbox_query(&m.session,&m.binding,m.buffers,&m.ops,42,1,&m.result)<0);
    assert(m.session.error==-3 && !m.tx && m.session.quarantined_buffers==7);
    setup(&m);m.time=UINT64_MAX-1;failed(&m);assert(!m.tx);
    setup(&m);m.count=3;failed(&m);assert(m.tx==1);
    for(unsigned offset=0;offset<=24;offset+=4){setup(&m);m.bad_reply=offset ? offset : 12;failed(&m);}
    puts("DISPLAY_MBOX_BOUNDS PASS MISMATCH_PEEK_POP=0 POLL_CAP=512 CLOCK_FAIL_CLOSED=1");
}
static void admission(void)
{
    struct model m;unsigned char unchanged[sizeof m.result];memset(unchanged,0xa5,sizeof unchanged);
    for(unsigned test=0;test<11;test++){
        setup(&m);
        switch(test){
        case 0:m.buffers[0].cpu=(char *)m.buffers[0].cpu+1;break;
        case 1:m.buffers[0].capacity=87;break;
        case 2:m.buffers[0].capacity=4097;break;
        case 3:m.buffers[0].mailbox_address=UINT64_C(0x100000000);break;
        case 4:m.buffers[0].mailbox_address=0xfffffff0;break;
        case 5:m.buffers[0].mailbox_address=0;break;
        case 6:m.buffers[0].mailbox_address|=8;break;
        case 7:m.buffers[1]=m.buffers[0];break;
        case 8:m.buffers[1].mailbox_address=m.buffers[0].mailbox_address;break;
        case 9:m.buffers[0].cpu=&m.result;break;
        default:m.ops.cache=NULL;break;
        }
        assert(run(&m)<0 && !m.callback && !m.owners && !m.tx);
        assert(m.session.state==RPI5_DISPLAY_MBOX_UNUSED && !memcmp(&m.result,unchanged,sizeof unchanged));
    }
    setup(&m);assert(rpi5_display_mailbox_query(&m.session,&m.binding,m.buffers,&m.ops,42,0,&m.result)<0);
    assert(rpi5_display_mailbox_query(&m.session,&m.binding,m.buffers,&m.ops,42,1000001,&m.result)<0);
    assert(rpi5_display_mailbox_query(&m.session,&m.binding,m.buffers,&m.ops,0,100,&m.result)<0);
    assert(!m.callback && !m.tx);
    puts("DISPLAY_MBOX_ADMISSION PASS NO_ADDRESS_GUESS NO_BUFFER_REUSE NO_HARDWARE");
}
int main(int argc,char **argv)
{
    assert(argc==2);
    if(!strcmp(argv[1],"success"))success();
    else if(!strcmp(argv[1],"faults"))faults();
    else if(!strcmp(argv[1],"bounds"))bounds();
    else if(!strcmp(argv[1],"admission"))admission();
    else abort();
}
