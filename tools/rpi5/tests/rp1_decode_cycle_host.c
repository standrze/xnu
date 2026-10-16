/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual config/probe/assignment/decode cores; mapping/device/owner are doubles. */
#include "prior_assign_host.c"
#include "rp1_decode_cycle.h"
static struct rpi5_rp1_decode_cycle *decode;
static unsigned decode_calls,decode_fail,mapping_calls,mapping_fail,mapping_live;
static unsigned mapping_events[4],mapping_count;
static struct rpi5_rp1_decode_io decode_io;
static int decode_current(void *context,const struct rpi5_rp1_decode_cycle *s,
    const struct rpi5_rp1_assignment *a)
{
    decode_calls++;
    return decode_calls==decode_fail || s!=decode || a!=assignment ||
        context!=source.context || !owner_live || !owner_thread || !owner_phase ? -1:0;
}
static int decode_authorize(void *context,const struct rpi5_pcie_config_request *r)
{ return authorize(context,r) || !rpi5_rp1_decode_write_allowed(decode,r)?-1:0; }
static int decode_write(void *context,uint32_t offset,uint32_t width,uint32_t value)
{
    if(offset!=0x9000) {
        assert(offset==0x8004 && width==2 && !(value&5));
        const struct rpi5_pcie_config_request request={1,0,0,4,2,1,value};
        if(!rpi5_rp1_decode_write_allowed(decode,&request))return -1;
    }
    return write_value(context,offset,width,value);
}
static int map_common(void *context,unsigned index,struct rpi5_range range,unsigned removing)
{
    struct model *m=context;
    assert(m->bytes[1][4]==2 && !(m->bytes[1][4]&5));
    if(!rpi5_rp1_decode_mapping_allowed(decode,index,range,removing))return -1;
    if(++mapping_calls==mapping_fail)return -1;
    assert(mapping_count<4);mapping_events[mapping_count++]=index+(removing?2:0);
    if(removing){assert(mapping_live&(1u<<index));mapping_live&=~(1u<<index);}
    else {assert(!(mapping_live&(1u<<index)));mapping_live|=1u<<index;}
    if(++mapping_calls==mapping_fail)return -1;
    return 0;
}
static int decode_map(void *context,unsigned index,struct rpi5_range range)
{return map_common(context,index,range,0);}
static int decode_unmap(void *context,unsigned index,struct rpi5_range range)
{return map_common(context,index,range,1);}
static void prepare_decode(struct fixture *f,struct rpi5_rp1_bars_probe *probe,
    struct rpi5_rp1_bars_size *sizes,struct rpi5_pcie_fdt *binding,
    struct rpi5_rp1_assignment *a,struct rpi5_rp1_decode_cycle *s)
{
    prepare(f,probe,sizes,binding,a,0);
    struct rpi5_rp1_assignment_observation assigned;
    assert(!rpi5_rp1_bars_assign(a,&f->config,binding,probe,sizes,&source,&assigned));
    memset(s,0,sizeof *s);decode=s;
    decode_io=(struct rpi5_rp1_decode_io){&f->m,decode_current,decode_map,decode_unmap};
    f->config.io.authorize_write=decode_authorize;f->config.io.write=decode_write;
    f->m.calls=f->m.reads=f->m.writes=0;memset(assign_releases,0,sizeof assign_releases);
    current_calls=current_fail=decode_calls=decode_fail=mapping_calls=mapping_fail=mapping_live=mapping_count=0;
}
static void unchanged_except_mem(const struct fixture *f,const unsigned char before[2][4096])
{
    assert(!memcmp(f->m.bytes[0],before[0],4096));
    for(unsigned i=0;i<4096;i++)if(i!=4)assert(f->m.bytes[1][i]==before[1][i]);
    assert(f->m.bytes[1][4]==before[1][4] || f->m.bytes[1][4]==(before[1][4]|2));
    assert(!f->m.locked);
}
int main(void)
{
    struct fixture f;struct rpi5_rp1_bars_probe probe;struct rpi5_rp1_bars_size sizes;
    struct rpi5_pcie_fdt binding;struct rpi5_rp1_assignment a;struct rpi5_rp1_decode_cycle s;
    struct rpi5_rp1_decode_observation out;
    unsigned char initial[2][4096],nonfailing[2048];
    prepare_decode(&f,&probe,&sizes,&binding,&a,&s);memcpy(initial,f.m.bytes,sizeof initial);
    assert(!rpi5_rp1_decode_run(&s,&a,&decode_io,&out));
    assert(s.state==RPI5_RP1_DECODE_COMPLETE && out.command_before==0x400 && out.command_enabled==0x402 && out.command_after==0x400);
    assert(out.transactions==34 && out.writes_started==2 && out.mapped==3 && out.unmapped==3 && !mapping_live);
    assert(mapping_count==4 && mapping_events[0]==0 && mapping_events[1]==1 && mapping_events[2]==3 && mapping_events[3]==2);
    assert(!memcmp(initial,f.m.bytes,sizeof initial));
    unsigned callbacks=f.m.calls,reads=f.m.reads,sources=current_calls,checks=decode_calls;
    memcpy(nonfailing,assign_releases,sizeof nonfailing);
    f.config.io.authorize_write=assign_authorize;f.config.io.write=assign_write;
    struct rpi5_rp1_assignment_observation restored;
    assert(!rpi5_rp1_bars_restore(&a,&restored));
    for(unsigned i=0;i<6;i++)assert(restored.bar[i]==probe.originals[i]);finish(&f);
    unsigned faults=0;
    for(unsigned kind=0;kind<5;kind++) {
        unsigned count=kind==0?callbacks:kind==1?reads:kind==2?sources:kind==3?checks:8;
        for(unsigned fault=1;fault<=count;fault++) {
            if(kind==0 && nonfailing[fault])continue;
            prepare_decode(&f,&probe,&sizes,&binding,&a,&s);memcpy(initial,f.m.bytes,sizeof initial);
            if(kind==0)f.m.fail_at=fault;if(kind==1)assign_corrupt_read=fault;
            if(kind==2)current_fail=fault;if(kind==3)decode_fail=fault;if(kind==4)mapping_fail=fault;
            memset(&out,0xa5,sizeof out);struct rpi5_rp1_decode_observation before=out;
            assert(rpi5_rp1_decode_run(&s,&a,&decode_io,&out));
            assert(s.state==RPI5_RP1_DECODE_QUARANTINED && !s.pending_write && !s.pending_map);
            assert(!memcmp(&out,&before,sizeof out));unchanged_except_mem(&f,initial);
            unsigned stopped=f.m.calls,maps=mapping_calls,current_count=decode_calls;
            assert(rpi5_rp1_decode_run(&s,&a,&decode_io,&out)==-2);
            assert(stopped==f.m.calls && maps==mapping_calls && current_count==decode_calls);
            assert(s.transactions<=34 && s.writes_started<=2 && mapping_count<=4);finish(&f);faults++;
        }
    }
    for(unsigned bad=0;bad<9;bad++) {
        prepare_decode(&f,&probe,&sizes,&binding,&a,&s);
        struct rpi5_rp1_assignment copied=a;
        if(bad==0)owner_live=0;if(bad==1)owner_thread=0;if(bad==2)owner_phase=0;
        if(bad==3)a.state=RPI5_RP1_ASSIGN_RESTORED;
        if(bad==4)a.command|=4;
        if(bad==5)binding.gem_bar_offset+=0x4000;
        if(bad==6)f.windows.plan.outbound[0].pci_base=0x4000;
        if(bad==7)decode_io.context=&s;
        memset(&out,0xa5,sizeof out);struct rpi5_rp1_decode_observation before=out;
        assert(rpi5_rp1_decode_run(&s,bad==8?&copied:&a,&decode_io,&out));
        assert(!f.m.calls && !mapping_calls && !memcmp(&out,&before,sizeof out));finish(&f);
    }
    for(unsigned dirty=0;dirty<19;dirty++) {
        prepare_decode(&f,&probe,&sizes,&binding,&a,&s);
        switch(dirty){
        case 0:s.assignment=&a;break;case 1:s.io.context=&f;break;
        case 2:s.io.current=decode_current;break;case 3:s.io.map=decode_map;break;
        case 4:s.io.unmap=decode_unmap;break;
        case 5:s.original_command=1;break;case 6:s.transactions=1;break;
        case 7:s.writes_started=1;break;case 8:s.pending_write=1;break;
        case 9:s.pending_map=1;break;case 10:s.selected=1;break;
        case 11:s.mapped=1;break;case 12:s.unmapped=1;break;
        case 13:s.geometry.bar1_cpu.start=1;break;case 14:s.geometry.bar1_cpu.end=1;break;
        case 15:s.geometry.gem_pages.start=1;break;case 16:s.geometry.gem_pages.end=1;break;
        case 17:s.geometry.clock_pages.start=1;break;case 18:s.geometry.clock_pages.end=1;break;
        }
        memset(&out,0xa5,sizeof out);struct rpi5_rp1_decode_observation before=out;
        assert(rpi5_rp1_decode_run(&s,&a,&decode_io,&out)==-2);
        assert(s.state==RPI5_RP1_DECODE_QUARANTINED && !s.pending_write && !s.pending_map);
        assert(!f.m.calls && !mapping_calls && !decode_calls && !memcmp(&out,&before,sizeof out));finish(&f);
    }
    prepare_decode(&f,&probe,&sizes,&binding,&a,&s);assert(!rpi5_rp1_decode_run(&s,&a,&decode_io,&out));
    for(unsigned disabling=0;disabling<2;disabling++) {
        s.state=disabling?RPI5_RP1_DECODE_DISABLING:RPI5_RP1_DECODE_ENABLING;s.pending_write=1;
        struct rpi5_pcie_config_request request={1,0,0,4,2,1,disabling?0x400:0x402};
        assert(rpi5_rp1_decode_write_allowed(&s,&request));
        for(unsigned field=0;field<7;field++){struct rpi5_pcie_config_request wrong=request;((uint32_t*)&wrong)[field]^=1;assert(!rpi5_rp1_decode_write_allowed(&s,&wrong));}
        request.width=4;assert(!rpi5_rp1_decode_write_allowed(&s,&request));
        request.width=2;request.value|=4;assert(!rpi5_rp1_decode_write_allowed(&s,&request));
        s.pending_write=0;assert(!rpi5_rp1_decode_write_allowed(&s,&request));
    }
    finish(&f);
    printf("RP1_DECODE_PASS TRANSACTIONS=34 HALFWORD_COMMAND_WRITES=2 MAPS=2 UNMAPS=2 FAULTS=%u NO_NIC_ACCESS=1 NO_HARDWARE=1\n",faults);
}
