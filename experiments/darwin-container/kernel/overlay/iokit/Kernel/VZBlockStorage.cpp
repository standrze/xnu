/* SPDX-License-Identifier: BSD-2-Clause
 * Dedicated VZ guest transport. IOStorageFamily and HFS are real pinned Apple
 * sources; this transport is original project code, not a Pi hardware driver.
 * Permanent one-device profile: no hot removal, unload, discard or formatting.
 */
#include <IOKit/storage/IOBlockStorageDevice.h>
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOLocks.h>
#include <libkern/c++/OSData.h>
#include <machine/machine_routines.h>
#include <kern/thread.h>
#include <arm/machine_routines.h>
extern "C" {
#include "virtio_block.h"
/* Exact kernel declarations, gated out of the IOKit exported header view. */
vm_offset_t ml_io_map(vm_offset_t, vm_size_t);
unsigned rpi5_physical_memory_type(uint64_t, uint64_t);
}

class VZBlockStorage : public IOBlockStorageDevice {
    OSDeclareDefaultStructors(VZBlockStorage);
    struct Request {
        Request *next;
        IOMemoryDescriptor *buffer;
        IOStorageCompletion completion;
        UInt64 block, count, actual;
        IOReturn status;
        bool synchronous, done, force;
    };
    vz_block_queue queue = {};
    IOBufferMemoryDescriptor *dma = nullptr;
    IOLock *lock = nullptr;
    Request *head = nullptr, *tail = nullptr;
    unsigned pending = 0;
    bool firstReport = true;
    static uintptr_t map(uint64_t pa, size_t length) {
        if (!length || pa>=(1ULL<<36) || length>(1ULL<<36)-pa ||
            rpi5_physical_memory_type(pa&~UINT64_C(0x3fff), (pa+length+0x3fff)&~UINT64_C(0x3fff))!=2) return 0;
        return ml_io_map(pa, length);
    }
    static void workerEntry(void *context, wait_result_t) { static_cast<VZBlockStorage *>(context)->worker(); }
    void worker();
    IOReturn submitRequest(Request *);
    IOReturn perform(Request *);
public:
    bool start(IOService *) APPLE_KEXT_OVERRIDE;
    bool terminate(IOOptionBits = 0) APPLE_KEXT_OVERRIDE { return false; }
    bool requestTerminate(IOService *, IOOptionBits) APPLE_KEXT_OVERRIDE { return false; }
    IOReturn doAsyncReadWrite(IOMemoryDescriptor *, UInt64, UInt64, IOStorageAttributes *, IOStorageCompletion *) APPLE_KEXT_OVERRIDE;
    IOReturn doSynchronizeCache() APPLE_KEXT_OVERRIDE { return doSynchronize(0, 0, 0); }
    IOReturn doSynchronize(UInt64, UInt64, IOStorageSynchronizeOptions) APPLE_KEXT_OVERRIDE;
    IOReturn doEjectMedia() APPLE_KEXT_OVERRIDE { return kIOReturnUnsupported; }
    IOReturn doFormatMedia(UInt64) APPLE_KEXT_OVERRIDE { return kIOReturnUnsupported; }
    UInt32 doGetFormatCapacities(UInt64 *, UInt32) const APPLE_KEXT_OVERRIDE { return 0; }
    IOReturn doUnmap(IOBlockStorageDeviceExtent *, UInt32, IOStorageUnmapOptions) APPLE_KEXT_OVERRIDE { return kIOReturnUnsupported; }
    char *getVendorString() APPLE_KEXT_OVERRIDE { static char s[]="Darwin project"; return s; }
    char *getProductString() APPLE_KEXT_OVERRIDE { static char s[]="VZ writable workload disk"; return s; }
    char *getRevisionString() APPLE_KEXT_OVERRIDE { static char s[]="0.1"; return s; }
    char *getAdditionalDeviceInfoString() APPLE_KEXT_OVERRIDE { static char s[]="virtio 1.2; polled; flush supported"; return s; }
    IOReturn reportBlockSize(UInt64 *v) APPLE_KEXT_OVERRIDE { if (!v) return kIOReturnBadArgument; *v=512; return kIOReturnSuccess; }
    IOReturn reportMaxValidBlock(UInt64 *v) APPLE_KEXT_OVERRIDE { if (!v) return kIOReturnBadArgument; *v=queue.capacity-1; return kIOReturnSuccess; }
    IOReturn reportEjectability(bool *v) APPLE_KEXT_OVERRIDE { if (!v) return kIOReturnBadArgument; *v=false; return kIOReturnSuccess; }
    IOReturn reportRemovability(bool *v) APPLE_KEXT_OVERRIDE { return reportEjectability(v); }
    IOReturn reportWriteProtection(bool *v) APPLE_KEXT_OVERRIDE { return reportEjectability(v); }
    IOReturn reportMediaState(bool *present, bool *changed=nullptr) APPLE_KEXT_OVERRIDE {
        if (!present) return kIOReturnBadArgument;
        *present=true;
        if (changed) { *changed=firstReport; firstReport=false; }
        return kIOReturnSuccess;
    }
    IOReturn reportPollRequirements(bool *media, bool *busy) APPLE_KEXT_OVERRIDE {
        if (!media || !busy) return kIOReturnBadArgument;
        *media=false; *busy=false; return kIOReturnSuccess;
    }
    IOReturn getWriteCacheState(bool *v) APPLE_KEXT_OVERRIDE { if (!v) return kIOReturnBadArgument; *v=true; return kIOReturnSuccess; }
    IOReturn setWriteCacheState(bool) APPLE_KEXT_OVERRIDE { return kIOReturnUnsupported; }
};
OSDefineMetaClassAndStructors(VZBlockStorage, IOBlockStorageDevice)

bool VZBlockStorage::start(IOService *provider)
{
    OSData *data=OSDynamicCast(OSData, provider->getProperty("vz-block"));
    if (!data || data->getLength()!=sizeof(vz_block_device) || !IOBlockStorageDevice::start(provider)) return false;
    vz_block_device device={}; memcpy(&device, data->getBytesNoCopy(), sizeof(device));
    lock=IOLockAlloc();
    dma=IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,
        kIODirectionInOut|kIOMemoryPhysicallyContiguous, VZ_BLOCK_DMA_BYTES, 0x4000);
    if (!lock || !dma || dma->prepare()!=kIOReturnSuccess) return false;
    IOByteCount contiguous=0;
    IOPhysicalAddress pa=dma->getPhysicalSegment(0, &contiguous);
    if (contiguous<VZ_BLOCK_DMA_BYTES || vz_block_start(&device, &queue, map, dma->getBytesNoCopy(), pa)) {
        kprintf("VZXNU:BLOCK:START_FAILED\n"); return false;
    }
    setProperty("device-type", "Generic");
    setProperty("DarwinWorkloadDisk", true);
    thread_t thread=THREAD_NULL;
    retain(); /* Permanent worker and DMA stay owned until this VM exits. */
    if (kernel_thread_start(workerEntry, this, &thread)!=KERN_SUCCESS) return false;
    thread_deallocate(thread);
    kprintf("VZXNU:BLOCK:READY SECTORS=%llu FLUSH=1\n", queue.capacity);
    registerService();
    return true;
}

IOReturn VZBlockStorage::submitRequest(Request *r)
{
    IOLockLock(lock);
    if (pending>=64) { IOLockUnlock(lock); return kIOReturnNoResources; }
    r->next=nullptr;
    if (tail) tail->next=r; else head=r;
    tail=r; pending++;
    IOLockWakeup(lock, &head, true);
    IOLockUnlock(lock);
    return kIOReturnSuccess;
}

IOReturn VZBlockStorage::doAsyncReadWrite(IOMemoryDescriptor *buffer, UInt64 block, UInt64 count,
    IOStorageAttributes *attributes, IOStorageCompletion *completion)
{
    if (ml_at_interrupt_context()) return kIOReturnNotPermitted;
    if (!buffer || !completion || !completion->action || !lock || !count || block>=queue.capacity ||
        count>queue.capacity-block || count>UINT64_MAX/512 || buffer->getLength()!=count*512 ||
        (buffer->getDirection()!=kIODirectionIn && buffer->getDirection()!=kIODirectionOut)) return kIOReturnBadArgument;
    if (attributes && (attributes->options&~(kIOStorageOptionForceUnitAccess|kIOStorageOptionIsStatic))) return kIOReturnUnsupported;
    Request *r=IOMallocType(Request);
    if (!r) return kIOReturnNoMemory;
    *r={}; r->buffer=buffer; r->completion=*completion; r->block=block; r->count=count;
    r->force=attributes && (attributes->options&kIOStorageOptionForceUnitAccess);
    buffer->retain();
    IOReturn result=submitRequest(r);
    if (result!=kIOReturnSuccess) { buffer->release(); IOFreeType(r, Request); }
    return result;
}

IOReturn VZBlockStorage::doSynchronize(UInt64 block, UInt64 count, IOStorageSynchronizeOptions options)
{
    if (ml_at_interrupt_context()) return kIOReturnNotPermitted;
    if (!lock || block>=queue.capacity || count>queue.capacity-block) return kIOReturnBadArgument;
    if (options&~kIOStorageSynchronizeOptionBarrier) return kIOReturnUnsupported;
    Request r={}; r.synchronous=true;
    IOReturn result=submitRequest(&r);
    if (result!=kIOReturnSuccess) return result;
    IOLockLock(lock);
    while (!r.done) IOLockSleep(lock, &r, THREAD_UNINT);
    result=r.status;
    IOLockUnlock(lock);
    return result;
}

IOReturn VZBlockStorage::perform(Request *r)
{
    r->actual=0;
    if (r->synchronous) return vz_block_request(&queue, 4, 0, 0) ? kIOReturnIOError : kIOReturnSuccess;
    IODirection direction=r->buffer->getDirection();
    IOReturn status=r->buffer->prepare(direction);
    if (status!=kIOReturnSuccess) return status;
    UInt64 length=r->count*512;
    void *bounce=static_cast<UInt8 *>(dma->getBytesNoCopy())+VZ_BLOCK_DATA_OFFSET;
    while (r->actual<length) {
        UInt64 remaining=length-r->actual;
        UInt32 bytes=remaining>VZ_BLOCK_MAX_BYTES ? VZ_BLOCK_MAX_BYTES : static_cast<UInt32>(remaining);
        if (direction==kIODirectionOut && r->buffer->readBytes(r->actual, bounce, bytes)!=bytes) { status=kIOReturnIOError; break; }
        if (vz_block_request(&queue, direction==kIODirectionIn ? 0 : 1, r->block+r->actual/512, bytes)) {
            status=kIOReturnIOError; break;
        }
        if (direction==kIODirectionIn && r->buffer->writeBytes(r->actual, bounce, bytes)!=bytes) { status=kIOReturnIOError; break; }
        r->actual+=bytes;
    }
    if (status==kIOReturnSuccess && r->force && direction==kIODirectionOut && vz_block_request(&queue, 4, 0, 0)) status=kIOReturnIOError;
    IOReturn complete=r->buffer->complete(direction);
    return status==kIOReturnSuccess ? complete : status;
}

void VZBlockStorage::worker()
{
    for (;;) {
        IOLockLock(lock);
        while (!head) IOLockSleep(lock, &head, THREAD_UNINT);
        Request *r=head; head=r->next; if (!head) tail=nullptr;
        IOLockUnlock(lock);
        IOReturn status=perform(r);
        bool synchronous=r->synchronous;
        IOLockLock(lock); pending--;
        if (synchronous) { r->status=status; r->done=true; IOLockWakeup(lock, r, true); }
        IOLockUnlock(lock);
        if (!synchronous) {
            IOStorageCompletion completion=r->completion;
            UInt64 actual=r->actual;
            r->buffer->release(); IOFreeType(r, Request);
            IOStorage::complete(&completion, status, actual);
        }
    }
}
