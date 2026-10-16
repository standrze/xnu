/* SPDX-License-Identifier: BSD-2-Clause */
/* Distinct opt-in experimental write-trial provider; absent from default builds.
 * The proven read-only adapter and its opcode list are unchanged. No DMA,
 * cache enabling, erase/trim, retries, hot reinsertion or reset-after-error.
 * See docs/rpi5/GATE4-WRITE-POLICY.md before integrating/staging this class. */
#if defined(ARM64_BOARD_CONFIG_BCM2712) && DEVELOPMENT && RPI5_STORAGE_WRITE_PROVIDER
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wzero-as-null-pointer-constant"
#pragma clang diagnostic ignored "-Wshadow-field"
#include <IOKit/storage/IOBlockStorageDevice.h>
#pragma clang diagnostic pop
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOKitKeys.h>
#include <IOKit/IOLocks.h>
#include <libkern/c++/OSData.h>
#include <libkern/libkern.h>
#include <machine/machine_routines.h>
#include <kern/clock.h>
#include <kern/thread.h>
#include <pexpert/pexpert.h>
#include "rpi5_sd_memory.h"
extern "C" {
#include "rpi5_sd_contract.h"
#include "rpi5_sd_cache.h"
void thread_terminate_self(void);
}

class BCM2712SDWriteStorage : public IOBlockStorageDevice {
    OSDeclareDefaultStructors(BCM2712SDWriteStorage);
#if defined(RPI5_SD_WRITE_HOST_TEST)
    friend struct SDWriteProviderHostTest;
#endif
    enum Kind { Read, Write, Synchronize };
    struct Request {
        rpi5_sd_request_link link;
        IOMemoryDescriptor *buffer;
        IOStorageCompletion completion;
        UInt64 block, count, epoch;
        Kind kind;
        bool done;
        IOReturn status;
    };
    struct ContinueContext { BCM2712SDWriteStorage *self; bool removed; };
    static_assert(__builtin_offsetof(Request,link)==0,"Intrusive request identity");
    rpi5_sd_binding binding = {};
    rpi5_sd_card card = {};
    rpi5_sd_identity identity = {};
    rpi5_sd_cache_observation cache = {};
    rpi5_sd_write_policy policy = {}; /* Only initializer/worker touch this. */
    rpi5_sd_request_queue requests = {};
    IOMemoryMap *pages[4] = {};
    vm_offset_t registers[5] = {};
    unsigned pageCount = 0;
    IOLock *queueLock = nullptr;
    thread_t workerThread = THREAD_NULL;
    bool workerRunning=false, providerOpened=false, mediaOnline=false;
    bool reportedPresent=false, writeAdmitted=false;
    UInt64 sectorCount=0, publishedEpoch=0;
    bool readBinding(IOService *);
    bool mapRegisters();
    bool initialize();
    bool initializationFailed(const char *,int);
    bool present();
    static UInt32 readRegister(void *, rpi5_sd_bank, UInt32);
    static void writeRegister(void *, rpi5_sd_bank, UInt32, UInt32);
    static UInt32 hostRead(void *, UInt32);
    static void hostWrite(void *, UInt32, UInt32);
    static UInt64 microseconds(void *);
    static void delay(void *, UInt32 us) { IODelay(us); }
    static int continuing(void *);
    static void workerEntry(void *, wait_result_t);
    void worker();
    IOReturn perform(Request *, UInt64 *);
protected:
    void free() APPLE_KEXT_OVERRIDE;
public:
    bool start(IOService *) APPLE_KEXT_OVERRIDE;
    void stop(IOService *) APPLE_KEXT_OVERRIDE;
    IOReturn doAsyncReadWrite(IOMemoryDescriptor *, UInt64, UInt64,
        IOStorageAttributes *, IOStorageCompletion *) APPLE_KEXT_OVERRIDE;
    IOReturn doSynchronizeCache() APPLE_KEXT_OVERRIDE { return doSynchronize(0,0,0); }
    IOReturn doSynchronize(UInt64, UInt64, IOStorageSynchronizeOptions) APPLE_KEXT_OVERRIDE;
    IOReturn doEjectMedia() APPLE_KEXT_OVERRIDE { return kIOReturnUnsupported; }
    IOReturn doFormatMedia(UInt64) APPLE_KEXT_OVERRIDE { return kIOReturnNotWritable; }
    UInt32 doGetFormatCapacities(UInt64 *, UInt32) const APPLE_KEXT_OVERRIDE { return 0; }
    IOReturn doUnmap(IOBlockStorageDeviceExtent *, UInt32, IOStorageUnmapOptions) APPLE_KEXT_OVERRIDE { return kIOReturnUnsupported; }
    char *getVendorString() APPLE_KEXT_OVERRIDE { static char s[]="Raspberry Pi"; return s; }
    char *getProductString() APPLE_KEXT_OVERRIDE { static char s[]="BCM2712 SD bounded write trial"; return s; }
    char *getRevisionString() APPLE_KEXT_OVERRIDE { static char s[]="Gate4-W1"; return s; }
    char *getAdditionalDeviceInfoString() APPLE_KEXT_OVERRIDE { static char s[]="PIO; disposable HFS extent only; cache off"; return s; }
    IOReturn reportBlockSize(UInt64 *) APPLE_KEXT_OVERRIDE;
    IOReturn reportEjectability(bool *) APPLE_KEXT_OVERRIDE;
    IOReturn reportMaxValidBlock(UInt64 *) APPLE_KEXT_OVERRIDE;
    IOReturn reportMediaState(bool *, bool * = nullptr) APPLE_KEXT_OVERRIDE;
    IOReturn reportRemovability(bool *) APPLE_KEXT_OVERRIDE;
    IOReturn reportWriteProtection(bool *) APPLE_KEXT_OVERRIDE;
    IOReturn reportPollRequirements(bool *, bool *) APPLE_KEXT_OVERRIDE;
    IOReturn getWriteCacheState(bool *) APPLE_KEXT_OVERRIDE;
    IOReturn setWriteCacheState(bool) APPLE_KEXT_OVERRIDE { return kIOReturnUnsupported; }
};
OSDefineMetaClassAndStructors(BCM2712SDWriteStorage,IOBlockStorageDevice)

bool BCM2712SDWriteStorage::readBinding(IOService *provider)
{
    static const char *keys[]={"reg","rpi5-sd-power-reg","rpi5-sd-pad-variant",
        "clock-frequency","rpi5-sd-settling-us","rpi5-gic-intid"};
    OSData *data[6];
    OSData *compatible=OSDynamicCast(OSData,provider->getProperty("compatible"));
    static const char wanted[]="brcm,bcm2712-sdhci";
    if (!compatible || compatible->getLength()!=sizeof wanted ||
        memcmp(compatible->getBytesNoCopy(),wanted,sizeof wanted)) return false;
    for (unsigned i=0;i<6;i++) {
        data[i]=OSDynamicCast(OSData,provider->getProperty(keys[i]));
        if (!data[i]) return false;
    }
    return !rpi5_sd_binding_decode(data[0]->getBytesNoCopy(),data[0]->getLength(),
        data[1]->getBytesNoCopy(),data[1]->getLength(),data[2]->getBytesNoCopy(),data[2]->getLength(),
        data[3]->getBytesNoCopy(),data[3]->getLength(),data[4]->getBytesNoCopy(),data[4]->getLength(),
        data[5]->getBytesNoCopy(),data[5]->getLength(),&binding);
}
bool BCM2712SDWriteStorage::mapRegisters()
{
    UInt64 physical[4]={};
    for (unsigned bank=0;bank<5;bank++) {
        UInt64 page=binding.base[bank]&~UInt64(0x3fff);
        unsigned i;
        for (i=0;i<pageCount;i++) if (physical[i]==page) break;
        if (i==pageCount) {
            if (pageCount==4) return false;
            IOMemoryDescriptor *memory=IOMemoryDescriptor::withPhysicalAddress(page,0x4000,kIODirectionInOut);
            if (!memory) return false;
            pages[i]=memory->map(kIOMapAnywhere|kIOMapInhibitCache);
            memory->release();
            if (!pages[i]) return false;
            physical[i]=page; pageCount++;
        }
        registers[bank]=pages[i]->getVirtualAddress()+(binding.base[bank]&0x3fff);
    }
    return true;
}
UInt32 BCM2712SDWriteStorage::readRegister(void *context, rpi5_sd_bank bank, UInt32 offset)
{
    auto *self=static_cast<BCM2712SDWriteStorage *>(context);
    if (static_cast<unsigned>(bank)>RPI5_SD_AON_PINS || (offset&3) || offset>self->binding.size[bank]-4)
        panic("BCM2712 SD write trial invalid MMIO read");
    UInt32 value=*reinterpret_cast<volatile UInt32 *>(self->registers[bank]+offset);
    __asm__ volatile("dmb osh" ::: "memory");
    return value;
}
void BCM2712SDWriteStorage::writeRegister(void *context, rpi5_sd_bank bank, UInt32 offset, UInt32 value)
{
    auto *self=static_cast<BCM2712SDWriteStorage *>(context);
    if (static_cast<unsigned>(bank)>RPI5_SD_AON_PINS || (offset&3) || offset>self->binding.size[bank]-4)
        panic("BCM2712 SD write trial invalid MMIO write");
    __asm__ volatile("dmb osh" ::: "memory");
    *reinterpret_cast<volatile UInt32 *>(self->registers[bank]+offset)=value;
    __asm__ volatile("dsb oshst" ::: "memory");
}
UInt32 BCM2712SDWriteStorage::hostRead(void *context, UInt32 offset) { return readRegister(context,RPI5_SD_HOST,offset); }
void BCM2712SDWriteStorage::hostWrite(void *context, UInt32 offset, UInt32 value) { writeRegister(context,RPI5_SD_HOST,offset,value); }
UInt64 BCM2712SDWriteStorage::microseconds(void *)
{
    uint64_t time, ns;
    clock_get_uptime(&time); absolutetime_to_nanoseconds(time,&ns);
    return ns/1000;
}
bool BCM2712SDWriteStorage::present()
{
    return !(readRegister(this,RPI5_SD_GPIO,4)&32) && (readRegister(this,RPI5_SD_HOST,0x24)&0x10000);
}
bool BCM2712SDWriteStorage::initialize()
{
    kprintf("RPI5XNU:SD:WRITE_INIT_BEGIN\n");
    rpi5_sd_platform_io platform={this,readRegister,writeRegister,microseconds,delay};
    rpi5_sd_handoff_result handoff={};
    int rc=rpi5_sd_handoff(&platform,binding.variant,binding.source_hz,&handoff);
    if (rc) {
        kprintf("RPI5XNU:SD:WRITE_HANDOFF RC=%d STAGE=%u BANK=%u REG=0x%x MASK=0x%x WANT=0x%x GOT=0x%x\n",
            rc,unsigned(handoff.stage),handoff.failed_bank,handoff.failed_offset,
            handoff.readback_mask,handoff.expected,handoff.observed);
        return initializationFailed("HANDOFF",rc);
    }
    rpi5_sd_io host={this,hostRead,hostWrite,microseconds,delay};
    rc=rpi5_sd_start_identified(&card,&host,binding.source_hz,&identity);
    if (rc) return initializationFailed("IDENTIFY",rc);
    const rpi5_sd_write_profile *profile=rpi5_sd_write_selected_profile();
    if (!rpi5_sd_write_profile_valid(profile))
        return initializationFailed("PROFILE",RPI5_SD_INVALID);
    constexpr size_t bytes=1536+sizeof(rpi5_sd_cache_diagnostic);
    auto *scratch=static_cast<UInt8 *>(IOMallocData(bytes));
    if (!scratch) return initializationFailed("ALLOCATE",RPI5_SD_INVALID);
    const char *stage="CACHE_PROBE";
    auto *trace=reinterpret_cast<rpi5_sd_cache_diagnostic *>(scratch+1536);
    rc=rpi5_sd_cache_probe_traced(&card,&cache,scratch,1024,trace);
    if (rc) {
        /* Only copied observations: no diagnostic read/reset/retry. Hex chunks
         * avoid a large formatting buffer or hundreds of separate prints. */
        char scrHex[17]={};
        constexpr char hex[]="0123456789abcdef";
        for (unsigned i=0;i<8;i++) {
            scrHex[i*2]=hex[trace->scr[i]>>4]; scrHex[i*2+1]=hex[trace->scr[i]&15];
        }
        kprintf("RPI5XNU:SD:CACHE_PROBE_FAIL STAGE=%u RC=%d SPEC=%u FUNCTION=%u ADDRESS=0x%x SCR=%s BYTES=%u\n",
            trace->stage,rc,trace->specification,trace->function,trace->address,scrHex,trace->payload_bytes);
        if (trace->payload_bytes<=sizeof trace->payload) {
            for (unsigned offset=0;offset<trace->payload_bytes;offset+=16) {
                char chunk[33]={};
                unsigned count=trace->payload_bytes-offset;
                if (count>16) count=16;
                for (unsigned i=0;i<count;i++) {
                    UInt8 value=trace->payload[offset+i];
                    chunk[i*2]=hex[value>>4]; chunk[i*2+1]=hex[value&15];
                }
                kprintf("RPI5XNU:SD:CACHE_PROBE_BYTES OFFSET=%u HEX=%s\n",offset,chunk);
            }
        }
    }
    if (!rc) kprintf("RPI5XNU:SD:WRITE_CACHE_OBSERVED CACHE=%u SPEC=%u FUNCTION=%u ADDRESS=0x%x\n",
        cache.state,cache.specification,cache.function,cache.address);
    if (!rc && cache.state!=RPI5_SD_CACHE_ABSENT && cache.state!=RPI5_SD_CACHE_DISABLED) {
        stage="CACHE_REFUSED";
        rc=RPI5_SD_UNSUPPORTED;
    }
    if (!rc) { stage="MBR_READ"; rc=rpi5_sd_read_sector(&card,0,scratch,512); }
    if (!rc) { stage="PRIMARY_READ"; rc=rpi5_sd_read_sector(&card,profile->start+2,scratch+512,512); }
    if (!rc) { stage="ALTERNATE_READ"; rc=rpi5_sd_read_sector(&card,profile->start+profile->blocks-2,scratch+1024,512); }
    if (!rc) {
        stage="AUTHORIZE";
        rc=rpi5_sd_write_authorize_profile(&policy,profile,card.sectors,identity.cid,16,identity.csd,16,
            scratch,512,scratch+512,512,scratch+1024,512);
    }
    IOFreeData(scratch,bytes);
    if (rc) return initializationFailed(stage,rc);
    sectorCount=card.sectors; publishedEpoch=policy.epoch;
    return policy.state==RPI5_SD_WRITE_ENABLED && publishedEpoch;
}
bool BCM2712SDWriteStorage::initializationFailed(const char *stage,int rc)
{
    /* Stored observations only: diagnostic printing must never introduce a
     * new MMIO read, card command, reset, admission retry or write. */
    kprintf("RPI5XNU:SD:WRITE_INIT_FAIL STAGE=%s RC=%d CMD=%u STATUS=0x%x CACHE=%u SPEC=%u\n",
        stage,rc,card.last_command,card.last_interrupt,cache.state,cache.specification);
    return false;
}
bool BCM2712SDWriteStorage::start(IOService *provider)
{
    kprintf("RPI5XNU:SD:WRITE_START_BEGIN\n");
    int enabled=0, readonly=0;
    PE_parse_boot_argn("bcm2712_sd_readonly",&readonly,sizeof readonly);
    if (!PE_parse_boot_argn("bcm2712_sd_write_trial",&enabled,sizeof enabled) || enabled!=1 || readonly)
        return initializationFailed("BOOT_ARGUMENTS",RPI5_SD_INVALID);
    if (ml_at_interrupt_context()) return initializationFailed("INTERRUPT_CONTEXT",RPI5_SD_INVALID);
    if (!readBinding(provider)) return initializationFailed("BINDING",RPI5_SD_INVALID);
    if (!IOBlockStorageDevice::start(provider)) return initializationFailed("SUPER_START",RPI5_SD_INVALID);
    const char *stage="LOCK";
    queueLock=IOLockAlloc();
    if (!queueLock) goto fail;
    stage="PROVIDER_OPEN";
    if (!provider->open(this)) goto fail;
    providerOpened=true;
    stage="MAP_REGISTERS";
    if (!mapRegisters()) goto fail;
    stage="INITIALIZE";
    if (!initialize()) goto fail;
    stage="PROPERTIES";
    if (!setProperty(kIOMaximumBlockCountReadKey,UInt64(RPI5_SD_MAX_READ_BLOCKS),64) ||
        !setProperty(kIOMaximumByteCountReadKey,UInt64(RPI5_SD_MAX_READ_BLOCKS)*512,64) ||
        !setProperty(kIOMaximumBlockCountWriteKey,UInt64(RPI5_SD_WRITE_MAX_REQUEST_BLOCKS),64) ||
        !setProperty(kIOMaximumByteCountWriteKey,UInt64(RPI5_SD_WRITE_MAX_REQUEST_BLOCKS)*512,64)) goto fail;
    mediaOnline=true; writeAdmitted=true; requests.accepting=1;
    workerRunning=true; retain();
    stage="WORKER_START";
    {
        thread_t thread=THREAD_NULL;
        if (kernel_thread_start(workerEntry,this,&thread)!=KERN_SUCCESS) {
            workerRunning=false; requests.accepting=0; mediaOnline=false; writeAdmitted=false; release(); goto fail;
        }
        thread_deallocate(thread);
    }
    kprintf("RPI5XNU:SD:WRITE_ADMITTED SECTORS=%llu START=%llu BLOCKS=%llu EPOCH=%llu CACHE=%u SPEC=%u DMA=0\n",
        sectorCount,policy.start,policy.blocks,publishedEpoch,cache.state,cache.specification);
    registerService();
    return true;
fail:
    kprintf("RPI5XNU:SD:WRITE_START_FAIL STAGE=%s\n",stage);
    rpi5_sd_write_revoke(&policy);
    if (providerOpened) { provider->close(this); providerOpened=false; }
    IOBlockStorageDevice::stop(provider);
    return false;
}
void BCM2712SDWriteStorage::stop(IOService *provider)
{
    bool close=false;
    if (queueLock) {
        IOLockLock(queueLock);
        requests.accepting=0; mediaOnline=false; writeAdmitted=false;
        IOLockWakeup(queueLock,&requests,false);
        while (workerRunning && workerThread!=current_thread())
            IOLockSleep(queueLock,&workerRunning,THREAD_UNINT);
        close=providerOpened; providerOpened=false;
        IOLockUnlock(queueLock);
    }
    if (close) provider->close(this);
    IOBlockStorageDevice::stop(provider);
}
void BCM2712SDWriteStorage::free()
{
    assert(!workerRunning && !requests.head && !requests.active);
    rpi5_sd_write_revoke(&policy);
    for (unsigned i=0;i<pageCount;i++) pages[i]->release();
    if (queueLock) IOLockFree(queueLock);
    IOBlockStorageDevice::free();
}
IOReturn BCM2712SDWriteStorage::doAsyncReadWrite(IOMemoryDescriptor *buffer, UInt64 block, UInt64 count,
    IOStorageAttributes *attributes, IOStorageCompletion *completion)
{
    if (ml_at_interrupt_context()) return kIOReturnNotPermitted;
    if (!buffer || !completion || !completion->action || !queueLock) return kIOReturnBadArgument;
    IODirection direction=buffer->getDirection();
    if (direction!=kIODirectionIn && direction!=kIODirectionOut) return kIOReturnBadArgument;
    if (!rpi5_sd_read_request_valid(sectorCount,block,count,buffer->getLength())) return kIOReturnBadArgument;
    if (attributes && (attributes->options&~(kIOStorageOptionForceUnitAccess|kIOStorageOptionIsStatic)))
        return kIOReturnUnsupported;
    Request *request=IOMallocType(Request);
    if (!request) return kIOReturnNoMemory;
    request->buffer=buffer; request->completion=*completion; request->block=block; request->count=count;
    request->kind=direction==kIODirectionIn ? Read : Write;
    buffer->retain();
    IOLockLock(queueLock);
    IOReturn result=kIOReturnSuccess;
    request->epoch=publishedEpoch;
    /* A queue-protected publication snapshot, not concurrent access to the
     * worker-owned mutable policy. Every write rechecks the REAL policy before
     * prepare and each sector; stale queued requests cannot bypass revocation. */
    rpi5_sd_write_policy snapshot={publishedEpoch,policy.start,policy.blocks,
        policy.max_request_blocks,UInt32(writeAdmitted?RPI5_SD_WRITE_ENABLED:RPI5_SD_WRITE_DISABLED)};
    if (!requests.accepting) result=kIOReturnOffline;
    else if (!mediaOnline || !writeAdmitted) result=kIOReturnNoMedia;
    else if (request->kind==Write && !rpi5_sd_write_request_valid(&snapshot,request->epoch,block,count,buffer->getLength()))
        result=kIOReturnNotPermitted;
    else if (rpi5_sd_queue_push(&requests,&request->link)) result=kIOReturnNoResources;
    else IOLockWakeup(queueLock,&requests,true);
    IOLockUnlock(queueLock);
    if (result!=kIOReturnSuccess) { buffer->release(); IOFreeType(request,Request); }
    return result; /* Rejection has no callback; caller owns that path. */
}
int BCM2712SDWriteStorage::continuing(void *context)
{
    auto *state=static_cast<ContinueContext *>(context);
    auto *self=state->self;
    IOLockLock(self->queueLock);
    bool usable=self->requests.accepting && self->mediaOnline && self->writeAdmitted;
    IOLockUnlock(self->queueLock);
    if (usable && !self->present()) { state->removed=true; usable=false; }
    return usable;
}
IOReturn BCM2712SDWriteStorage::perform(Request *request, UInt64 *actual)
{
    *actual=0;
    ContinueContext context={this,false};
    if (!continuing(&context)) {
        if (context.removed) { card.ready=0; rpi5_sd_write_quarantine(&policy); }
        return kIOReturnOffline;
    }
    if (cache.state!=RPI5_SD_CACHE_ABSENT && cache.state!=RPI5_SD_CACHE_DISABLED) {
        card.ready=0; rpi5_sd_write_quarantine(&policy);
        return kIOReturnUnsupported;
    }
    if (request->kind==Synchronize) {
        /* This queued barrier runs after all prior requests completed. Cache
         * was actually observed off; no path in this provider can enable it.
         * CMD13 alone would NOT flush an enabled/unknown cache. */
        int rc=rpi5_sd_write_wait_ready(&card,&policy,request->epoch);
        if (rc) { card.ready=0; rpi5_sd_write_quarantine(&policy); }
        return !rc ? kIOReturnSuccess : rc==RPI5_SD_TIMEOUT ? kIOReturnTimeout : kIOReturnIOError;
    }
    rpi5_sd_memory_result result=rpi5_sd_memory_execute(&card,&policy,request->epoch,
        request->kind==Read ? RPI5_SD_TRANSFER_READ : RPI5_SD_TRANSFER_WRITE,
        request->block,request->count,request->buffer,continuing,&context);
    if (context.removed) { card.ready=0; rpi5_sd_write_quarantine(&policy); }
    *actual=result.transfer.actual_bytes;
    return result.status;
}
IOReturn BCM2712SDWriteStorage::doSynchronize(UInt64 block, UInt64 count, IOStorageSynchronizeOptions options)
{
    if (ml_at_interrupt_context()) return kIOReturnNotPermitted;
    if (!queueLock || block>=sectorCount || count>sectorCount-block) return kIOReturnBadArgument;
    if (options&~kIOStorageSynchronizeOptionBarrier) return kIOReturnUnsupported;
    Request *request=IOMallocType(Request);
    if (!request) return kIOReturnNoMemory;
    request->buffer=nullptr; request->kind=Synchronize; request->done=false;
    IOLockLock(queueLock);
    IOReturn status=kIOReturnSuccess;
    request->epoch=publishedEpoch;
    if (workerThread==current_thread()) status=kIOReturnNotPermitted; /* No completion-reentrancy deadlock. */
    else if (!requests.accepting) status=kIOReturnOffline;
    else if (!mediaOnline || !writeAdmitted) status=kIOReturnNoMedia;
    else if (rpi5_sd_queue_push(&requests,&request->link)) status=kIOReturnNoResources;
    else {
        retain(); /* Keep lock/object alive through stop/drain and wakeup. */
        IOLockWakeup(queueLock,&requests,true);
        while (!request->done) IOLockSleep(queueLock,request,THREAD_UNINT);
        status=request->status;
        IOLockUnlock(queueLock);
        IOFreeType(request,Request);
        release();
        return status;
    }
    IOLockUnlock(queueLock);
    IOFreeType(request,Request);
    return status;
}
void BCM2712SDWriteStorage::workerEntry(void *context, wait_result_t)
{
    static_cast<BCM2712SDWriteStorage *>(context)->worker();
    thread_terminate_self();
}
void BCM2712SDWriteStorage::worker()
{
    IOLockLock(queueLock);
    workerThread=current_thread();
    for (;;) {
        while (!requests.head && requests.accepting) IOLockSleep(queueLock,&requests,THREAD_UNINT);
        if (!requests.head) break;
        auto *request=reinterpret_cast<Request *>(rpi5_sd_queue_pop(&requests));
        assert(request);
        bool cancel=!requests.accepting || !mediaOnline || !writeAdmitted;
        IOLockUnlock(queueLock);
        UInt64 actual=0;
        IOReturn status=cancel ? kIOReturnOffline : perform(request,&actual);
        IOLockLock(queueLock);
        if (!card.ready || policy.state!=RPI5_SD_WRITE_ENABLED) { mediaOnline=false; writeAdmitted=false; }
        assert(!rpi5_sd_queue_complete(&requests));
        if (request->kind==Synchronize) {
            request->status=status; request->done=true;
            IOLockWakeup(queueLock,request,false);
            /* Caller owns/frees the request after wake; never touch it again. */
        } else {
            IOStorageCompletion completion=request->completion;
            IOMemoryDescriptor *buffer=request->buffer;
            IOLockUnlock(queueLock);
            buffer->release(); IOFreeType(request,Request);
            IOStorage::complete(&completion,status,actual); /* No locks, descriptor prepared/complete already paired. */
            IOLockLock(queueLock);
        }
    }
    rpi5_sd_write_revoke(&policy);
    writeAdmitted=false; mediaOnline=false;
    workerThread=THREAD_NULL; workerRunning=false;
    IOLockWakeup(queueLock,&workerRunning,false);
    IOLockUnlock(queueLock);
    release(); /* No member access afterward. */
}
IOReturn BCM2712SDWriteStorage::reportMediaState(bool *value, bool *changed)
{
    if (!value || !queueLock) return kIOReturnBadArgument;
    IOLockLock(queueLock);
    if (mediaOnline && !present()) { mediaOnline=false; writeAdmitted=false; }
    *value=mediaOnline;
    if (changed) *changed=reportedPresent!=mediaOnline;
    reportedPresent=mediaOnline;
    IOLockUnlock(queueLock);
    return kIOReturnSuccess;
}
IOReturn BCM2712SDWriteStorage::reportMaxValidBlock(UInt64 *value)
{
    if (!value || !queueLock) return kIOReturnBadArgument;
    IOLockLock(queueLock);
    bool online=mediaOnline;
    if (online) *value=sectorCount-1;
    IOLockUnlock(queueLock);
    return online ? kIOReturnSuccess : kIOReturnNoMedia;
}
IOReturn BCM2712SDWriteStorage::reportWriteProtection(bool *value)
{
    if (!value || !queueLock) return kIOReturnBadArgument;
    IOLockLock(queueLock);
    bool online=mediaOnline;
    *value=!writeAdmitted;
    IOLockUnlock(queueLock);
    return online ? kIOReturnSuccess : kIOReturnNoMedia;
}
IOReturn BCM2712SDWriteStorage::getWriteCacheState(bool *value)
{
    if (!value || !queueLock) return kIOReturnBadArgument;
    IOLockLock(queueLock);
    bool known=mediaOnline && writeAdmitted &&
        (cache.state==RPI5_SD_CACHE_ABSENT || cache.state==RPI5_SD_CACHE_DISABLED);
    if (known) *value=false;
    IOLockUnlock(queueLock);
    return known ? kIOReturnSuccess : kIOReturnNoMedia;
}
IOReturn BCM2712SDWriteStorage::reportBlockSize(UInt64 *v) { if (!v) return kIOReturnBadArgument; *v=512; return kIOReturnSuccess; }
IOReturn BCM2712SDWriteStorage::reportEjectability(bool *v) { if (!v) return kIOReturnBadArgument; *v=false; return kIOReturnSuccess; }
IOReturn BCM2712SDWriteStorage::reportRemovability(bool *v) { if (!v) return kIOReturnBadArgument; *v=true; return kIOReturnSuccess; }
IOReturn BCM2712SDWriteStorage::reportPollRequirements(bool *required, bool *expensive)
{
    if (!required || !expensive) return kIOReturnBadArgument;
    *required=true; *expensive=false; return kIOReturnSuccess;
}
#endif
