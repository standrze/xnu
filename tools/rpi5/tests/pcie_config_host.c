/* SPDX-License-Identifier: BSD-2-Clause */
/* Synthetic controller/ownership model, never physical admission. */
#include "pcie_config.h"
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>

enum kind { ACQUIRE, RELEASE, CHECK, AUTHORIZE, READ, WRITE, ORDER };
struct event { enum kind kind; uint32_t offset, width, value; };
struct model {
    pthread_mutex_t mutex;
    struct rpi5_pcie_config *session;
    unsigned locked, calls, fail_at, wrong_at, bad_status_at, bad_value_at;
    unsigned deny, dma_admitted, recurse, reads, writes;
    uint32_t status, selector;
    unsigned char bytes[2][4096];
    struct event events[32];
};
struct fixture {
    struct model m;
    struct rpi5_pcie_config config;
    struct rpi5_pcie_config_io io;
    struct rpi5_pcie_link link;
    struct rpi5_pcie_windows windows;
    struct rpi5_pcie_rc rc;
    struct rpi5_pcie_ubus ubus;
    struct rpi5_pcie_serdes serdes;
    struct rpi5_pcie_reset reset;
    struct rpi5_pcie_rescal rescal;
};

static int event(struct model *m, enum kind kind, uint32_t offset, uint32_t width, uint32_t value)
{
    assert(m->locked);
    m->events[m->calls++ % 32] = (struct event){kind, offset, width, value};
    if (kind != ACQUIRE && kind != RELEASE) {
        assert(m->session->state == RPI5_PCIE_CONFIG_BUSY);
        if (m->recurse) {
            struct rpi5_pcie_config_request r = {1,0,0,0,4,0,0};
            uint32_t out = 0xfeedbeef;
            assert(rpi5_pcie_config_transfer(m->session,&r,&out) == RPI5_PCIE_CONFIG_LOCK);
            assert(out == 0xfeedbeef && m->session->state == RPI5_PCIE_CONFIG_BUSY);
        }
    }
    return m->calls == m->fail_at;
}
static int acquire(void *context)
{
    struct model *m = context;
    if (pthread_mutex_lock(&m->mutex)) return -1; /* ERRORCHECK refuses recursive acquisition. */
    assert(!m->locked);
    m->locked = 1;
    if (!event(m,ACQUIRE,0,0,0)) return 0;
    m->locked = 0;
    assert(!pthread_mutex_unlock(&m->mutex));
    return -1;
}
static void release(void *context)
{
    struct model *m = context;
    (void)event(m,RELEASE,0,0,0);
    m->locked = 0;
    assert(!pthread_mutex_unlock(&m->mutex));
}
static int check(void *context) { return event(context,CHECK,0,0,0) ? -1 : 0; }
static int order(void *context) { return event(context,ORDER,0,0,0) ? -1 : 0; }
static int authorize(void *context, const struct rpi5_pcie_config_request *r)
{
    struct model *m = context;
    if (event(m,AUTHORIZE,r->offset,r->width,r->value) || m->deny) return -1;
    if (r->offset <= 4 && r->offset + r->width > 4 && !m->dma_admitted &&
        ((r->value >> (8 * (4-r->offset))) & 4)) return -1;
    return 0;
}
static unsigned char *address(struct model *m, uint32_t offset, uint32_t width)
{
    unsigned bus = offset >= 0x8000;
    uint32_t where = offset - (bus ? 0x8000 : 0);
    assert(width == 1 || width == 2 || width == 4);
    assert(where + width <= 4096 && !(where & (width - 1)));
    if (bus) assert(m->selector == 0x100000);
    return &m->bytes[bus][where];
}
static int read_value(void *context, uint32_t offset, uint32_t width, uint32_t *out)
{
    struct model *m = context;
    if (event(m,READ,offset,width,0)) return -1;
    if (offset == 0x4068) {
        assert(width == 4);
        *out = m->calls == m->bad_status_at ? 0x80 : m->status;
    } else if (offset == 0x9000) {
        assert(width == 4);
        *out = m->selector ^ (m->calls == m->wrong_at ? 0x1000 : 0);
    } else {
        unsigned char *p = address(m,offset,width);
        *out = 0;
        for (unsigned i=0; i<width; i++) *out |= (uint32_t)p[i] << (i*8);
        if (m->calls == m->bad_value_at) *out |= UINT32_C(0x80000000);
        m->reads++;
    }
    return 0;
}
static int write_value(void *context, uint32_t offset, uint32_t width, uint32_t value)
{
    struct model *m = context;
    int failed = event(m,WRITE,offset,width,value);
    if (offset == 0x9000) {
        assert(width == 4 && value == 0x100000);
        m->selector = value;
    } else {
        unsigned char *p = address(m,offset,width);
        uint32_t where = offset - (offset >= 0x8000 ? 0x8000 : 0);
        for (unsigned i=0; i<width; i++) {
            unsigned char byte = (unsigned char)(value >> (i*8));
            if (where+i == 6 || where+i == 7) p[i] &= (unsigned char)~byte; /* W1C status. */
            else p[i] = byte;
        }
        m->writes++;
    }
    return failed ? -1 : 0; /* Failed posted write may already have taken effect. */
}
static int read32(void *c, uint32_t o, uint32_t *v) { return read_value(c,o,4,v); }
static int write32(void *c, uint32_t o, uint32_t v) { return write_value(c,o,4,v); }
static int read16(void *c, uint32_t o, uint16_t *v)
{
    uint32_t value;
    int rc=read_value(c,o,2,&value);
    if (!rc) *v=(uint16_t)value;
    return rc;
}
static int write16(void *c, uint32_t o, uint16_t v) { return write_value(c,o,2,v); }
static void setup(struct fixture *f)
{
    memset(f,0,sizeof *f);
    pthread_mutexattr_t attr;
    assert(!pthread_mutexattr_init(&attr));
    assert(!pthread_mutexattr_settype(&attr,PTHREAD_MUTEX_ERRORCHECK));
    assert(!pthread_mutex_init(&f->m.mutex,&attr));
    assert(!pthread_mutexattr_destroy(&attr));
    f->m.session = &f->config;
    f->m.status = 0xb0;
    memset(f->m.bytes,0x5a,sizeof f->m.bytes);
    f->windows.state = RPI5_PCIE_WINDOWS_COMPLETE;
    f->windows.io.context = &f->m;
    f->windows.io.physical_base = UINT64_C(0x1000120000);
    f->windows.io.mapped_bytes = 0x9310;
    f->windows.io.read32 = read32;
    f->windows.io.write32 = write32;
    f->windows.io.order = order;
    f->rc.state = RPI5_PCIE_RC_COMPLETE;
    f->rc.windows = &f->windows;
    f->rc.bridge_reset = &f->reset;
    f->rc.calibration = &f->rescal;
    f->rc.io.read16 = read16;
    f->rc.io.write16 = write16;
    f->ubus.state = RPI5_PCIE_UBUS_COMPLETE;
    f->ubus.serdes = &f->serdes;
    f->serdes.state = RPI5_PCIE_SERDES_COMPLETE;
    f->serdes.bridge_reset = &f->reset;
    f->serdes.calibration = &f->rescal;
    f->serdes.mdio.state = RPI5_PCIE_MDIO_READY;
    f->serdes.mdio.io.context = &f->m;
    f->serdes.mdio.io.physical_base = UINT64_C(0x1000120000);
    f->serdes.mdio.io.mapped_bytes = 0x9310;
    f->serdes.mdio.io.read32 = read32;
    f->serdes.mdio.io.write32 = write32;
    f->serdes.mdio.io.order = order;
    f->reset.state = RPI5_PCIE_RESET_COMPLETE;
    f->rescal.state = RPI5_PCIE_RESCAL_COMPLETE;
    f->link.state = RPI5_PCIE_LINK_COMPLETE;
    f->link.windows = &f->windows;
    f->link.io.rc = &f->rc;
    f->link.io.read16 = read16;
    f->link.io.write16 = write16;
    f->link.ubus = &f->ubus;
    f->io = (struct rpi5_pcie_config_io){&f->m,acquire,release,check,authorize,read_value,write_value,order};
    assert(!rpi5_pcie_config_init(&f->config,&f->link,&f->io));
    assert(f->m.calls == 0);
}
static void finish(struct fixture *f) { assert(!f->m.locked); assert(!pthread_mutex_destroy(&f->m.mutex)); }
static uint32_t mask(unsigned width) { return width == 4 ? UINT32_MAX : (UINT32_C(1) << (width*8))-1; }

static void transactions(void)
{
    struct fixture f;
    setup(&f);
    f.m.recurse = 1;
    for (unsigned bus=0; bus<2; bus++) for (unsigned width=1; width<=4; width*=2)
    for (unsigned offset=0; offset<4096; offset+=width) {
        struct rpi5_pcie_config_request r = {bus,0,0,offset,width,0,0};
        uint32_t out=0;
        unsigned before=f.m.calls;
        assert(!rpi5_pcie_config_transfer(&f.config,&r,&out));
        assert(out == (0x5a5a5a5a & mask(width)));
        assert(f.m.calls-before == (bus ? 14u : 9u));
    }
    assert(f.m.reads == 14336 && !f.m.writes);
    assert(rpi5_pcie_config_ready(&f.config));
    /* True command-byte/halfword writes must not clear adjacent W1C status. */
    for (unsigned bus=0; bus<2; bus++) for (unsigned width=1; width<=4; width*=2) {
        struct rpi5_pcie_config_request r = {bus,0,0,4,width,1,0x12345678 & mask(width)};
        unsigned before=f.m.calls, reads=f.m.reads;
        f.m.bytes[bus][6]=0xff; f.m.bytes[bus][7]=0xff;
        assert(!rpi5_pcie_config_transfer(&f.config,&r,NULL));
        assert(f.m.calls-before == (bus ? 15u : 10u));
        assert(f.m.reads == reads); /* No config read/RMW or W1C "verification". */
        assert(f.m.bytes[bus][4] == 0x78);
        assert(f.m.bytes[bus][6] == (width==4 ? 0xcb : 0xff));
        assert(f.m.bytes[bus][7] == (width==4 ? 0xed : 0xff));
    }
    /* An all-ones config value is valid, unlike all-ones bridge status. */
    memset(f.m.bytes[1],0xff,sizeof f.m.bytes[1]);
    struct rpi5_pcie_config_request r={1,0,0,0xffc,4,0,0};
    uint32_t out=0;
    assert(!rpi5_pcie_config_transfer(&f.config,&r,&out) && out==UINT32_MAX);
    finish(&f);
}
static unsigned failures(void)
{
    unsigned positions=0;
    for (unsigned bus=0; bus<2; bus++) for (unsigned width=1; width<=4; width*=2)
    for (unsigned write=0; write<2; write++) {
        struct fixture f;
        setup(&f);
        struct rpi5_pcie_config_request r={bus,0,0,0xfc,width,write,0x78};
        uint32_t out=0;
        assert(!rpi5_pcie_config_transfer(&f.config,&r,&out));
        unsigned calls=f.m.calls;
        finish(&f);
        for (unsigned at=1; at<calls; at++) { /* release cannot fail by contract. */
            setup(&f); f.m.fail_at=at; out=0xfeedbeef;
            assert(rpi5_pcie_config_transfer(&f.config,&r,&out) != 0);
            assert(out==0xfeedbeef && !f.m.locked);
            assert(f.config.state == (at==1 ? RPI5_PCIE_CONFIG_READY : RPI5_PCIE_CONFIG_QUARANTINED));
            assert(f.m.calls == (at==1 ? 1 : at+1)); /* Only release follows failure. */
            if (write && at==(bus ? 10u : 6u)) {
                assert(f.m.writes==1 && f.m.bytes[bus][0xfc]==0x78); /* No rollback fiction. */
            }
            if (at>1) {
                unsigned reads=f.m.reads, writes=f.m.writes, before=f.m.calls;
                assert(rpi5_pcie_config_transfer(&f.config,&r,&out)==RPI5_PCIE_CONFIG_STATE);
                assert(f.m.calls==before+2 && f.m.reads==reads && f.m.writes==writes);
            }
            finish(&f); positions++;
        }
    }
    return positions;
}
static void rejection(void)
{
    struct fixture f;
    struct rpi5_pcie_config_request r={1,0,0,0,4,0,0}, bad;
    uint32_t out=0xfeedbeef;
    setup(&f);
    for (unsigned i=0; i<11; i++) {
        bad=r;
        switch(i) {
            case 0: bad.bus=256; break; case 1: bad.device=32; break;
            case 2: bad.function=8; break; case 3: bad.width=0; break;
            case 4: bad.width=3; break; case 5: bad.offset=4096; break;
            case 6: bad.offset=4095; break; case 7: bad.offset=1; break;
            case 8: bad.write=2; break;
            case 9: bad.width=1; bad.write=1; bad.value=256; break;
            case 10: bad.width=2; bad.write=1; bad.value=65536; break;
        }
        assert(rpi5_pcie_config_transfer(&f.config,&bad,&out)==RPI5_PCIE_CONFIG_ARGUMENT);
        assert(!f.m.calls && out==0xfeedbeef);
    }
    for (unsigned bus=0; bus<256; bus++) for (unsigned dev=0; dev<32; dev++)
    for (unsigned fn=0; fn<8; fn++) {
        if (bus<2 && !dev && !fn) continue;
        bad=r; bad.bus=bus; bad.device=dev; bad.function=fn;
        assert(rpi5_pcie_config_transfer(&f.config,&bad,&out)==RPI5_PCIE_CONFIG_ABSENT);
        bad.write=1;
        assert(rpi5_pcie_config_transfer(&f.config,&bad,NULL)==RPI5_PCIE_CONFIG_ABSENT);
        assert(!f.m.calls);
    }
    assert(rpi5_pcie_config_transfer(NULL,&r,&out)==RPI5_PCIE_CONFIG_ARGUMENT);
    assert(rpi5_pcie_config_transfer(&f.config,NULL,&out)==RPI5_PCIE_CONFIG_ARGUMENT);
    assert(rpi5_pcie_config_transfer(&f.config,&r,NULL)==RPI5_PCIE_CONFIG_ARGUMENT);
    finish(&f);
    /* Every endpoint status/selector check must reject corrupted routing. */
    for (unsigned at=1; at<=14; at++) {
        setup(&f); f.m.bad_status_at=at;
        int rc=rpi5_pcie_config_transfer(&f.config,&r,&out);
        assert(rc == ((at==4 || at==8 || at==11) ? RPI5_PCIE_CONFIG_LINK : 0));
        finish(&f);
        setup(&f); f.m.wrong_at=at;
        rc=rpi5_pcie_config_transfer(&f.config,&r,&out);
        assert(rc == ((at==7 || at==12) ? RPI5_PCIE_CONFIG_SELECTOR : 0));
        finish(&f);
    }
    setup(&f); f.m.status=0x80; bad=r; bad.bus=0;
    assert(!rpi5_pcie_config_transfer(&f.config,&bad,&out)); /* Root remains accessible with link down. */
    assert(rpi5_pcie_config_transfer(&f.config,&r,&out)==RPI5_PCIE_CONFIG_LINK);
    finish(&f);
    for (unsigned status=0; status<256; status++) {
        setup(&f); f.m.status=status;
        int rc=rpi5_pcie_config_transfer(&f.config,&r,&out);
        assert(rc == (((status&0xf0)==0xb0) ? 0 : RPI5_PCIE_CONFIG_LINK));
        finish(&f);
    }
    setup(&f); f.m.status=UINT32_MAX;
    assert(rpi5_pcie_config_transfer(&f.config,&r,&out)==RPI5_PCIE_CONFIG_LINK); finish(&f);
    setup(&f); r.width=1; f.m.bad_value_at=9;
    assert(rpi5_pcie_config_transfer(&f.config,&r,&out)==RPI5_PCIE_CONFIG_VALUE); finish(&f);
    setup(&f); r=(struct rpi5_pcie_config_request){1,0,0,4,2,1,4};
    assert(rpi5_pcie_config_transfer(&f.config,&r,NULL)==RPI5_PCIE_CONFIG_DENIED);
    assert(!f.m.writes && f.m.calls==4); finish(&f);
    setup(&f); f.m.dma_admitted=1;
    assert(!rpi5_pcie_config_transfer(&f.config,&r,NULL)); finish(&f);
    setup(&f); f.rc.state=RPI5_PCIE_RC_QUARANTINED;
    assert(rpi5_pcie_config_transfer(&f.config,&r,NULL)==RPI5_PCIE_CONFIG_DEPENDENCY);
    assert(f.m.calls==2); finish(&f);
}
static void *worker(void *context)
{
    struct fixture *f=context;
    struct rpi5_pcie_config_request r={1,0,0,0xfc,4,0,0};
    for (unsigned i=0; i<2000; i++) {
        uint32_t out=0;
        assert(!rpi5_pcie_config_transfer(&f->config,&r,&out));
        assert(out==0x5a5a5a5a);
    }
    return NULL;
}
static void initialization(void)
{
    for (unsigned i=0; i<15; i++) {
        struct fixture f; setup(&f);
        struct rpi5_pcie_config fresh={0}, before={0};
        switch(i) {
            case 0: f.link.state=RPI5_PCIE_LINK_READY; break;
            case 1: f.windows.io.context=NULL; break;
            case 2: f.windows.io.physical_base++; break;
            case 3: f.windows.io.mapped_bytes--; break;
            case 4: f.rc.windows=NULL; break;
            case 5: f.ubus.state=RPI5_PCIE_UBUS_QUARANTINED; break;
            case 6: f.serdes.state=RPI5_PCIE_SERDES_QUARANTINED; break;
            case 7: f.serdes.mdio.state=RPI5_PCIE_MDIO_QUARANTINED; break;
            case 8: f.reset.state=RPI5_PCIE_RESET_READY; break;
            case 9: f.rescal.state=RPI5_PCIE_RESCAL_READY; break;
            case 10: f.rc.bridge_reset=NULL; break;
            case 11: f.serdes.mdio.io.context=NULL; break;
            case 12: f.windows.io.order=NULL; break;
            case 13: f.link.io.read16=NULL; break;
            case 14: f.rc.io.write16=NULL; break;
        }
        assert(rpi5_pcie_config_init(&fresh,&f.link,&f.io)==RPI5_PCIE_CONFIG_DEPENDENCY);
        assert(!memcmp(&fresh,&before,sizeof fresh) && !f.m.calls);
        struct rpi5_pcie_config_request r={1,0,0,0,4,0,0};
        uint32_t out=0xfeedbeef;
        assert(!rpi5_pcie_config_ready(&f.config));
        assert(rpi5_pcie_config_transfer(&f.config,&r,&out)==RPI5_PCIE_CONFIG_DEPENDENCY);
        assert(f.config.state==RPI5_PCIE_CONFIG_QUARANTINED && out==0xfeedbeef);
        assert(f.m.calls==4); /* Ready query plus failed transaction: lock/release only. */
        finish(&f);
    }
    struct fixture f; setup(&f);
    assert(rpi5_pcie_config_init(&f.config,&f.link,&f.io)==RPI5_PCIE_CONFIG_STATE);
    struct rpi5_pcie_config fresh={0};
    f.io.authorize_write=NULL;
    assert(rpi5_pcie_config_init(&fresh,&f.link,&f.io)==RPI5_PCIE_CONFIG_ARGUMENT);
    assert(rpi5_pcie_config_init(NULL,&f.link,&f.io)==RPI5_PCIE_CONFIG_ARGUMENT);
    assert(!f.m.calls); finish(&f);
}
static void concurrency(void)
{
    struct fixture f; setup(&f);
    pthread_t threads[2];
    assert(!pthread_create(&threads[0],NULL,worker,&f));
    assert(!pthread_create(&threads[1],NULL,worker,&f));
    assert(!pthread_join(threads[0],NULL)); assert(!pthread_join(threads[1],NULL));
    assert(f.m.reads==4000 && f.m.calls==56000 && !f.m.locked);
    finish(&f);
}
int main(void)
{
    initialization(); transactions(); unsigned positions=failures(); rejection(); concurrency();
    printf("PCIE_CONFIG_HOST_PASS READS=14336 THREAD_READS=4000 FAILURE_POSITIONS=%u NO_MMIO=1\n",positions);
    return 0;
}
