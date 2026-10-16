/* SPDX-License-Identifier: BSD-2-Clause */
/* Experimental built-in, serialized, read-only removable SD transport.
 * No Linux implementation code is used. Register references and limitations:
 * docs/rpi5/GATE4-STORAGE.md. DMA, writes, hot reinsertion and power management
 * are deliberately not advertised. Runtime opt-in is separate from build opt-in.
 */
#if defined(ARM64_BOARD_CONFIG_BCM2712) && DEVELOPMENT && RPI5_STORAGE_PROVIDER
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
extern "C" {
#include "rpi5_sd_contract.h"
#include "rpi5_sdhci_core.h"
/* Actual XNU built-in private ABI; not exported to IOKit translation units.
 * The real definition/signature is in osfmk/kern/thread.{h,c}. */
void thread_terminate_self(void);
}

class BCM2712SDStorage : public IOBlockStorageDevice {
    OSDeclareDefaultStructors(BCM2712SDStorage);
    struct Request {
        rpi5_sd_request_link link; /* First member: intrusive queue identity. */
        IOMemoryDescriptor *buffer;
        IOStorageCompletion completion;
        UInt64 block, count;
    };
    rpi5_sd_binding binding = {};
    rpi5_sd_card card = {};
    rpi5_sd_request_queue requests = {};
    IOMemoryMap *pages[4] = {};
    vm_offset_t registers[5] = {};
    unsigned pageCount = 0;
    IOLock *queueLock = nullptr;
    thread_t workerThread = THREAD_NULL;
    bool workerRunning = false, providerOpened = false;
    bool mediaOnline = false, reportedPresent = false;
    UInt64 sectorCount = 0;
    bool readBinding(IOService *);
    bool mapRegisters();
    static UInt32 readRegister(void *, rpi5_sd_bank, UInt32);
    static void writeRegister(void *, rpi5_sd_bank, UInt32, UInt32);
    static UInt32 hostRead(void *, UInt32);
    static void hostWrite(void *, UInt32, UInt32);
    static UInt64 microseconds(void *);
    static void delay(void *, UInt32 us) { IODelay(us); }
    static void workerEntry(void *, wait_result_t);
    void worker();
    bool present();
    void perform(Request *, IOReturn *, UInt64 *);
protected:
    void free() APPLE_KEXT_OVERRIDE;
public:
    bool start(IOService *) APPLE_KEXT_OVERRIDE;
    void stop(IOService *) APPLE_KEXT_OVERRIDE;
    IOReturn doAsyncReadWrite(IOMemoryDescriptor *, UInt64, UInt64,
        IOStorageAttributes *, IOStorageCompletion *) APPLE_KEXT_OVERRIDE;
    IOReturn doEjectMedia() APPLE_KEXT_OVERRIDE { return kIOReturnUnsupported; }
    IOReturn doFormatMedia(UInt64) APPLE_KEXT_OVERRIDE { return kIOReturnNotWritable; }
    UInt32 doGetFormatCapacities(UInt64 *, UInt32) const APPLE_KEXT_OVERRIDE { return 0; }
    char *getVendorString() APPLE_KEXT_OVERRIDE { static char s[]="Raspberry Pi"; return s; }
    char *getProductString() APPLE_KEXT_OVERRIDE { static char s[]="BCM2712 SD PIO read-only"; return s; }
    char *getRevisionString() APPLE_KEXT_OVERRIDE { static char s[]="Gate4-RO1"; return s; }
    char *getAdditionalDeviceInfoString() APPLE_KEXT_OVERRIDE { static char s[]="No DMA or writes"; return s; }
    IOReturn reportBlockSize(UInt64 *) APPLE_KEXT_OVERRIDE;
    IOReturn reportEjectability(bool *) APPLE_KEXT_OVERRIDE;
    IOReturn reportMaxValidBlock(UInt64 *) APPLE_KEXT_OVERRIDE;
    IOReturn reportMediaState(bool *, bool * = nullptr) APPLE_KEXT_OVERRIDE;
    IOReturn reportRemovability(bool *) APPLE_KEXT_OVERRIDE;
    IOReturn reportWriteProtection(bool *) APPLE_KEXT_OVERRIDE;
    IOReturn reportPollRequirements(bool *, bool *) APPLE_KEXT_OVERRIDE;
    IOReturn getWriteCacheState(bool *) APPLE_KEXT_OVERRIDE;
    IOReturn setWriteCacheState(bool) APPLE_KEXT_OVERRIDE { return kIOReturnUnsupported; }
    IOReturn doSynchronizeCache() APPLE_KEXT_OVERRIDE { return kIOReturnUnsupported; }
    IOReturn doSynchronize(UInt64, UInt64, IOStorageSynchronizeOptions) APPLE_KEXT_OVERRIDE { return kIOReturnUnsupported; }
    IOReturn doUnmap(IOBlockStorageDeviceExtent *, UInt32, IOStorageUnmapOptions) APPLE_KEXT_OVERRIDE { return kIOReturnNotWritable; }
};
OSDefineMetaClassAndStructors(BCM2712SDStorage, IOBlockStorageDevice)

bool BCM2712SDStorage::readBinding(IOService *provider)
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
bool BCM2712SDStorage::mapRegisters()
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
            memory->release(); /* A successful IOMemoryMap retains its descriptor. */
            if (!pages[i]) return false;
            physical[i]=page; pageCount++;
        }
        registers[bank]=pages[i]->getVirtualAddress()+(binding.base[bank]&0x3fff);
    }
    return true;
}
UInt32 BCM2712SDStorage::readRegister(void *context, rpi5_sd_bank bank, UInt32 offset)
{
    auto *self=static_cast<BCM2712SDStorage *>(context);
    if (static_cast<unsigned>(bank)>RPI5_SD_AON_PINS || (offset&3) || offset>self->binding.size[bank]-4)
        panic("BCM2712 SD invalid MMIO read");
    UInt32 value=*reinterpret_cast<volatile UInt32 *>(self->registers[bank]+offset);
    __asm__ volatile("dmb osh" ::: "memory");
    return value;
}
void BCM2712SDStorage::writeRegister(void *context, rpi5_sd_bank bank, UInt32 offset, UInt32 value)
{
    auto *self=static_cast<BCM2712SDStorage *>(context);
    if (static_cast<unsigned>(bank)>RPI5_SD_AON_PINS || (offset&3) || offset>self->binding.size[bank]-4)
        panic("BCM2712 SD invalid MMIO write");
    __asm__ volatile("dmb osh" ::: "memory");
    *reinterpret_cast<volatile UInt32 *>(self->registers[bank]+offset)=value;
    __asm__ volatile("dsb oshst" ::: "memory");
}
UInt32 BCM2712SDStorage::hostRead(void *context, UInt32 offset) { return readRegister(context,RPI5_SD_HOST,offset); }
void BCM2712SDStorage::hostWrite(void *context, UInt32 offset, UInt32 value) { writeRegister(context,RPI5_SD_HOST,offset,value); }
UInt64 BCM2712SDStorage::microseconds(void *)
{
    uint64_t time, ns;
    clock_get_uptime(&time); absolutetime_to_nanoseconds(time,&ns);
    return ns/1000;
}
bool BCM2712SDStorage::present()
{
    return !(readRegister(this,RPI5_SD_GPIO,4)&32) &&
        (readRegister(this,RPI5_SD_HOST,0x24)&0x10000);
}
bool BCM2712SDStorage::start(IOService *provider)
{
    int enabled=0;
    if (!PE_parse_boot_argn("bcm2712_sd_readonly",&enabled,sizeof enabled) || enabled!=1 ||
        ml_at_interrupt_context() || !readBinding(provider) || !IOBlockStorageDevice::start(provider)) return false;
    queueLock=IOLockAlloc();
    if (!queueLock || !provider->open(this)) goto fail;
    providerOpened=true;
    if (!mapRegisters()) goto fail;
    {
        rpi5_sd_platform_io io={this,readRegister,writeRegister,microseconds,delay};
        rpi5_sd_handoff_result state={};
        int rc=rpi5_sd_handoff(&io,binding.variant,binding.source_hz,&state);
        kprintf("RPI5XNU:SD:HANDOFF RC=%d STAGE=%u CAPS=0x%x GPIO=0x%x\n",
            rc,unsigned(state.stage),state.capabilities,state.gpio_data);
        if (state.readback_mask)
            kprintf("RPI5XNU:SD:READBACK BANK=%u REG=0x%x MASK=0x%x WANT=0x%x GOT=0x%x\n",
                state.failed_bank,state.failed_offset,state.readback_mask,state.expected,state.observed);
        if (rc) goto fail;
        rpi5_sd_io host={this,hostRead,hostWrite,microseconds,delay};
        rc=rpi5_sd_start(&card,&host,binding.source_hz);
        if (rc) {
            kprintf("RPI5XNU:SD:INIT_FAIL RC=%d CMD=%u STATUS=0x%x\n",rc,card.last_command,card.last_interrupt);
            goto fail;
        }
    }
    sectorCount=card.sectors;
    if (!setProperty(kIOMaximumBlockCountReadKey,UInt64(RPI5_SD_MAX_READ_BLOCKS),64) ||
        !setProperty(kIOMaximumByteCountReadKey,UInt64(RPI5_SD_MAX_READ_BLOCKS)*512,64)) goto fail;
    mediaOnline=true; requests.accepting=1;
    workerRunning=true;
    retain(); /* The worker owns maps/lock until it has drained cancellations. */
    {
        thread_t thread=THREAD_NULL;
        if (kernel_thread_start(workerEntry,this,&thread)!=KERN_SUCCESS) {
            workerRunning=false; requests.accepting=0; mediaOnline=false; release(); goto fail;
        }
        thread_deallocate(thread);
    }
    kprintf("RPI5XNU:SD:READ_ONLY_READY SECTORS=%llu BLOCK=512 DMA=0 WRITES=0\n",sectorCount);
    registerService();
    return true;
fail:
    if (providerOpened) { provider->close(this); providerOpened=false; }
    IOBlockStorageDevice::stop(provider);
    return false;
}
void BCM2712SDStorage::stop(IOService *provider)
{
    if (queueLock) {
        IOLockLock(queueLock);
        requests.accepting=0; mediaOnline=false;
        IOLockWakeup(queueLock,&requests,false);
        /* A completion may synchronously stop this service on the worker.
         * Its retained object will drain/free resources after returning. */
        while (workerRunning && workerThread!=current_thread())
            IOLockSleep(queueLock,&workerRunning,THREAD_UNINT);
        IOLockUnlock(queueLock);
    }
    if (providerOpened) { provider->close(this); providerOpened=false; }
    IOBlockStorageDevice::stop(provider);
}
void BCM2712SDStorage::free()
{
    assert(!workerRunning && !requests.head && !requests.active);
    for (unsigned i=0;i<pageCount;i++) pages[i]->release();
    if (queueLock) IOLockFree(queueLock);
    IOBlockStorageDevice::free();
}
IOReturn BCM2712SDStorage::doAsyncReadWrite(IOMemoryDescriptor *buffer, UInt64 block, UInt64 count,
    IOStorageAttributes *attributes, IOStorageCompletion *completion)
{
    if (ml_at_interrupt_context()) return kIOReturnNotPermitted;
    if (!buffer || !completion || !completion->action || !queueLock) return kIOReturnBadArgument;
    if (buffer->getDirection()!=kIODirectionIn) return kIOReturnNotWritable;
    if (!rpi5_sd_read_request_valid(sectorCount,block,count,buffer->getLength())) return kIOReturnBadArgument;
    if (attributes && (attributes->options&~(kIOStorageOptionForceUnitAccess|kIOStorageOptionIsStatic)))
        return kIOReturnUnsupported;
    Request *request=IOMallocType(Request);
    if (!request) return kIOReturnNoMemory;
    request->buffer=buffer; request->completion=*completion; request->block=block; request->count=count;
    buffer->retain();
    IOLockLock(queueLock);
    IOReturn result=kIOReturnSuccess;
    if (!requests.accepting) result=kIOReturnOffline;
    else if (!mediaOnline) result=kIOReturnNoMedia;
    else if (rpi5_sd_queue_push(&requests,&request->link)) result=kIOReturnNoResources;
    else IOLockWakeup(queueLock,&requests,true);
    IOLockUnlock(queueLock);
    if (result!=kIOReturnSuccess) { buffer->release(); IOFreeType(request,Request); }
    return result; /* Rejected requests receive no callback: Apple's caller owns that path. */
}
void BCM2712SDStorage::perform(Request *request, IOReturn *status, UInt64 *actual)
{
    *actual=0;
    *status=request->buffer->prepare(kIODirectionIn);
    if (*status!=kIOReturnSuccess) return;
    UInt8 sector[512];
    for (UInt64 i=0;i<request->count;i++) {
        IOLockLock(queueLock);
        bool usable=requests.accepting && mediaOnline;
        IOLockUnlock(queueLock);
        if (!usable) { *status=kIOReturnOffline; break; }
        if (!present()) { card.ready=0; *status=kIOReturnNoMedia; break; }
        int rc=rpi5_sd_read_sector(&card,request->block+i,sector,sizeof sector);
        if (rc) {
            *status=rc==RPI5_SD_TIMEOUT ? kIOReturnTimeout : kIOReturnIOError;
            kprintf("RPI5XNU:SD:READ_FAIL LBA=%llu RC=%d CMD=%u STATUS=0x%x\n",
                request->block+i,rc,card.last_command,card.last_interrupt);
            break;
        }
        IOByteCount written=request->buffer->writeBytes(*actual,sector,sizeof sector);
        *actual+=written;
        if (written!=sizeof sector) { *status=kIOReturnUnderrun; break; }
    }
    IOReturn completed=request->buffer->complete(kIODirectionIn);
    if (*status==kIOReturnSuccess && completed!=kIOReturnSuccess) *status=completed;
}
void BCM2712SDStorage::workerEntry(void *context, wait_result_t)
{
    static_cast<BCM2712SDStorage *>(context)->worker();
    thread_terminate_self();
}
void BCM2712SDStorage::worker()
{
    IOLockLock(queueLock);
    workerThread=current_thread();
    for (;;) {
        while (!requests.head && requests.accepting) IOLockSleep(queueLock,&requests,THREAD_UNINT);
        if (!requests.head && !requests.accepting) break;
        auto *request=reinterpret_cast<Request *>(rpi5_sd_queue_pop(&requests));
        assert(request);
        bool cancel=!requests.accepting || !mediaOnline;
        IOLockUnlock(queueLock);
        IOReturn status=kIOReturnOffline;
        UInt64 actual=0;
        if (!cancel) perform(request,&status,&actual);
        IOLockLock(queueLock);
        if (!card.ready) mediaOnline=false;
        assert(!rpi5_sd_queue_complete(&requests));
        IOLockUnlock(queueLock);
        IOStorageCompletion completion=request->completion;
        request->buffer->release();
        IOFreeType(request,Request);
        IOStorage::complete(&completion,status,actual); /* No mutex or work-loop gate held. */
        IOLockLock(queueLock);
    }
    workerThread=THREAD_NULL; workerRunning=false;
    IOLockWakeup(queueLock,&workerRunning,false);
    IOLockUnlock(queueLock);
    release(); /* No member access after this point. */
}
IOReturn BCM2712SDStorage::reportMediaState(bool *value, bool *changed)
{
    if (!value || !queueLock) return kIOReturnBadArgument;
    IOLockLock(queueLock);
    if (mediaOnline && !present()) mediaOnline=false;
    *value=mediaOnline;
    if (changed) *changed=reportedPresent!=mediaOnline;
    reportedPresent=mediaOnline;
    IOLockUnlock(queueLock);
    return kIOReturnSuccess;
}
IOReturn BCM2712SDStorage::reportMaxValidBlock(UInt64 *value)
{
    if (!value || !queueLock) return kIOReturnBadArgument;
    IOLockLock(queueLock);
    bool online=mediaOnline;
    if (online) *value=sectorCount-1;
    IOLockUnlock(queueLock);
    return online ? kIOReturnSuccess : kIOReturnNoMedia;
}
IOReturn BCM2712SDStorage::reportBlockSize(UInt64 *v) { if (!v) return kIOReturnBadArgument; *v=512; return kIOReturnSuccess; }
IOReturn BCM2712SDStorage::reportEjectability(bool *v) { if (!v) return kIOReturnBadArgument; *v=false; return kIOReturnSuccess; }
IOReturn BCM2712SDStorage::reportRemovability(bool *v) { if (!v) return kIOReturnBadArgument; *v=true; return kIOReturnSuccess; }
IOReturn BCM2712SDStorage::reportWriteProtection(bool *v) { if (!v) return kIOReturnBadArgument; *v=true; return kIOReturnSuccess; }
IOReturn BCM2712SDStorage::getWriteCacheState(bool *v) { if (!v) return kIOReturnBadArgument; *v=false; return kIOReturnSuccess; }
IOReturn BCM2712SDStorage::reportPollRequirements(bool *required, bool *expensive)
{
    if (!required || !expensive) return kIOReturnBadArgument;
    *required=true; *expensive=false; return kIOReturnSuccess;
}
#endif
