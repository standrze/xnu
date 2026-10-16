/* SPDX-License-Identifier: BSD-2-Clause */
/* Linked only by the distinct opt-in write-trial provider. No writable media
 * is advertised here; controller ownership/admission and caller completion
 * belong to that separately gated provider. */
#include "rpi5_sd_memory.h"
#include <IOKit/IOLib.h>
#include <machine/machine_routines.h>

namespace {
struct MemoryContext {
    IOMemoryDescriptor *memory;
    int (*continuing)(void *);
    void *context;
};

IODirection direction(rpi5_sd_transfer_kind kind)
{
    return kind==RPI5_SD_TRANSFER_READ ? kIODirectionIn : kIODirectionOut;
}
int prepare(void *opaque, rpi5_sd_transfer_kind kind)
{
    return static_cast<MemoryContext *>(opaque)->memory->prepare(direction(kind));
}
int complete(void *opaque, rpi5_sd_transfer_kind kind)
{
    return static_cast<MemoryContext *>(opaque)->memory->complete(direction(kind));
}
size_t copyFrom(void *opaque, uint64_t offset, void *bytes, size_t count)
{
    return static_cast<MemoryContext *>(opaque)->memory->readBytes(offset,bytes,count);
}
size_t copyTo(void *opaque, uint64_t offset, const void *bytes, size_t count)
{
    return static_cast<MemoryContext *>(opaque)->memory->writeBytes(offset,bytes,count);
}
int continuing(void *opaque)
{
    auto *context=static_cast<MemoryContext *>(opaque);
    return context->continuing(context->context);
}
IOReturn status(const rpi5_sd_transfer_result &result)
{
    switch (result.status) {
    case RPI5_SD_OK: return kIOReturnSuccess;
    case RPI5_SD_INVALID: return kIOReturnBadArgument;
    case RPI5_SD_TIMEOUT: return kIOReturnTimeout;
    case RPI5_SD_CARD: return kIOReturnNoMedia;
    case RPI5_SD_CANCELLED: return kIOReturnOffline;
    case RPI5_SD_BUFFER_ERROR: return result.memory_status ? result.memory_status : kIOReturnUnderrun;
    case RPI5_SD_CLEANUP_ERROR: return result.cleanup_status ? result.cleanup_status : kIOReturnIOError;
    default: return kIOReturnIOError;
    }
}
}

rpi5_sd_memory_result rpi5_sd_memory_execute(rpi5_sd_card *card, rpi5_sd_write_policy *policy,
    uint64_t epoch, rpi5_sd_transfer_kind kind, uint64_t block, uint64_t count,
    IOMemoryDescriptor *memory, int (*shouldContinue)(void *), void *opaque)
{
    rpi5_sd_memory_result result={};
    result.status=kIOReturnBadArgument;
    result.transfer.status=RPI5_SD_INVALID;
    if (ml_at_interrupt_context()) { result.status=kIOReturnNotPermitted; return result; }
    if (!card || !policy || !memory || !shouldContinue || !card->ready ||
        (kind!=RPI5_SD_TRANSFER_READ && kind!=RPI5_SD_TRANSFER_WRITE) ||
        memory->getDirection()!=direction(kind)) return result;
    uint64_t bytes=memory->getLength();
    if (!rpi5_sd_read_request_valid(card->sectors,block,count,bytes) ||
        (kind==RPI5_SD_TRANSFER_WRITE && !rpi5_sd_write_request_valid(policy,epoch,block,count,bytes)))
        return result;
    size_t scratchBytes=kind==RPI5_SD_TRANSFER_READ ? 512 : static_cast<size_t>(bytes);
    memory->retain();
    void *scratch=IOMallocData(scratchBytes);
    if (!scratch) { memory->release(); result.status=kIOReturnNoMemory; return result; }
    MemoryContext context={memory,shouldContinue,opaque};
    rpi5_sd_buffer buffer={&context,bytes,prepare,complete,copyFrom,copyTo,continuing};
    result.transfer=rpi5_sd_transfer(card,policy,epoch,kind,block,count,&buffer,scratch,scratchBytes);
    IOFreeData(scratch,scratchBytes);
    memory->release();
    result.status=status(result.transfer);
    return result;
}
