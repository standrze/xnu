/* SPDX-License-Identifier: BSD-2-Clause */
/* Executes the unchanged C++ adapter and C transfer/policy with explicit
 * descriptor/allocator/context/transport doubles. No real IOKit or SD access. */
#include "rpi5_sd_memory.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <vector>

static bool interruptContext,allocationFailure;
static unsigned allocations,frees,calls,failedSector;
static size_t allocationBytes;
static std::vector<unsigned char> expected;
bool ml_at_interrupt_context() { return interruptContext; }
void *IOMallocData(size_t bytes) {
    allocations++; allocationBytes=bytes;
    return allocationFailure ? nullptr : malloc(bytes);
}
void IOFreeData(void *bytes,size_t count) { assert(count==allocationBytes); frees++; free(bytes); }
struct Memory : IOMemoryDescriptor {
    std::vector<unsigned char> bytes;
    IODirection dir;
    unsigned retains=0,releases=0,prepares=0,completes=0;
    int prepareError=0,completeError=0;
    bool shortCopy=false;
    Memory(unsigned count,IODirection d):bytes(count*512,0x5a),dir(d) {}
    IODirection getDirection() const override { return dir; }
    uint64_t getLength() const override { return bytes.size(); }
    void retain() override { retains++; }
    void release() override { assert(retains==releases+1); releases++; }
    IOReturn prepare(IODirection d) override { assert(d==dir); prepares++; return prepareError; }
    IOReturn complete(IODirection d) override { assert(d==dir); completes++; return completeError; }
    size_t readBytes(uint64_t offset,void *dest,size_t count) override {
        assert(offset+count<=bytes.size()); if(shortCopy) return count-1;
        memcpy(dest,bytes.data()+offset,count); return count;
    }
    size_t writeBytes(uint64_t offset,const void *src,size_t count) override {
        assert(offset+count<=bytes.size()); if(shortCopy) return count-1;
        memcpy(bytes.data()+offset,src,count); return count;
    }
};
static Memory *mutatedMemory;
extern "C" int rpi5_sd_write_sector(rpi5_sd_card *,rpi5_sd_write_policy *,uint64_t,
                                    uint64_t block,const void *data,size_t bytes) {
    assert(bytes==512); unsigned index=static_cast<unsigned>(block-RPI5_SD_WRITE_START);
    assert(memcmp(data,expected.data()+index*512,512)==0);
    if(mutatedMemory) memset(mutatedMemory->bytes.data(),0xcc,mutatedMemory->bytes.size());
    calls++; return calls==failedSector ? RPI5_SD_TIMEOUT : 0;
}
extern "C" int rpi5_sd_read_sector(rpi5_sd_card *,uint64_t block,void *data,size_t bytes) {
    assert(bytes==512); calls++; if(calls==failedSector) return RPI5_SD_TIMEOUT;
    memset(data,static_cast<int>(block&255),bytes); return 0;
}
static int remain(void *context) { return context ? *static_cast<int *>(context) : 1; }
static void reset() {
    interruptContext=allocationFailure=false; allocations=frees=calls=failedSector=0;
    allocationBytes=0; mutatedMemory=nullptr;
}
int main() {
    for(unsigned count=1;count<=32;count++) {
        reset(); Memory memory(count,kIODirectionOut); expected=memory.bytes; mutatedMemory=&memory;
        rpi5_sd_card card={}; card.ready=1; card.sectors=250347520;
        rpi5_sd_write_policy policy={7,RPI5_SD_WRITE_START,RPI5_SD_WRITE_BLOCKS,
            RPI5_SD_WRITE_MAX_REQUEST_BLOCKS,RPI5_SD_WRITE_ENABLED};
        auto result=rpi5_sd_memory_execute(&card,&policy,7,RPI5_SD_TRANSFER_WRITE,RPI5_SD_WRITE_START,count,&memory,remain,nullptr);
        assert(result.status==0 && result.transfer.actual_bytes==count*512 && calls==count);
        assert(allocations==1 && frees==1 && allocationBytes==count*512);
        assert(memory.retains==1 && memory.releases==1 && memory.prepares==1 && memory.completes==1);
        reset(); Memory read(count,kIODirectionIn);
        result=rpi5_sd_memory_execute(&card,&policy,7,RPI5_SD_TRANSFER_READ,0,count,&read,remain,nullptr);
        assert(result.status==0 && result.transfer.actual_bytes==count*512 && allocationBytes==512);
        for(unsigned i=0;i<count*512;i++) assert(read.bytes[i]==static_cast<unsigned char>(i/512));
        assert(read.retains==read.releases && read.prepares==read.completes && allocations==frees);
    }
    for(unsigned fault=0;fault<12;fault++) {
        reset(); Memory memory(2,kIODirectionOut); expected=memory.bytes;
        rpi5_sd_card card={}; card.ready=1; card.sectors=250347520;
        rpi5_sd_write_policy policy={7,RPI5_SD_WRITE_START,RPI5_SD_WRITE_BLOCKS,
            RPI5_SD_WRITE_MAX_REQUEST_BLOCKS,RPI5_SD_WRITE_ENABLED};
        int accepting=1;
        if(fault==0) interruptContext=true;
        if(fault==1) memory.dir=kIODirectionIn;
        if(fault==2) memory.dir=kIODirectionInOut;
        if(fault==3) allocationFailure=true;
        if(fault==4) memory.prepareError=-201;
        if(fault==5) memory.completeError=-202;
        if(fault==6) memory.shortCopy=true;
        if(fault==7) accepting=0;
        if(fault==8) failedSector=2;
        if(fault==9) { failedSector=2; memory.completeError=-202; }
        if(fault==10) policy.epoch=8;
        if(fault==11) card.ready=0;
        auto result=rpi5_sd_memory_execute(&card,&policy,7,RPI5_SD_TRANSFER_WRITE,RPI5_SD_WRITE_START,2,&memory,remain,&accepting);
        assert(result.status!=0 && memory.retains==memory.releases);
        assert(memory.completes==(memory.prepares && !memory.prepareError ? 1u : 0u));
        assert(frees==(allocationFailure ? 0u : allocations));
        if(fault==4) assert(result.status==-201 && calls==0);
        if(fault==5) assert(result.status==-202 && result.transfer.actual_bytes==1024);
        if(fault==8 || fault==9) assert(result.status==kIOReturnTimeout && result.transfer.actual_bytes==512);
        if(fault==5 || fault==8 || fault==9) assert(policy.state==RPI5_SD_WRITE_QUARANTINED && !card.ready);
        if(fault!=5 && fault!=8 && fault!=9) assert(calls==0);
    }
    puts("SD_MEMORY_ADAPTER_PASS");
}
