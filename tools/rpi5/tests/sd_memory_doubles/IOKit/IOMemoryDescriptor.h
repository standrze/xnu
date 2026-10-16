/* SPDX-License-Identifier: BSD-2-Clause */
/* Test-only bounded API double. Not an Apple implementation or runtime proof. */
#ifndef SD_MEMORY_DESCRIPTOR_DOUBLE_H
#define SD_MEMORY_DESCRIPTOR_DOUBLE_H
#include <stddef.h>
#include <stdint.h>
using IOReturn=int;
enum IODirection { kIODirectionNone=0, kIODirectionIn=1, kIODirectionOut=2, kIODirectionInOut=3 };
enum { kIOReturnSuccess=0, kIOReturnBadArgument=-101, kIOReturnTimeout=-102,
       kIOReturnNoMedia=-103, kIOReturnOffline=-104, kIOReturnUnderrun=-105,
       kIOReturnIOError=-106, kIOReturnNotPermitted=-107, kIOReturnNoMemory=-108 };
class IOMemoryDescriptor {
public:
    virtual ~IOMemoryDescriptor()=default;
    virtual IODirection getDirection() const=0;
    virtual uint64_t getLength() const=0;
    virtual void retain()=0;
    virtual void release()=0;
    virtual IOReturn prepare(IODirection)=0;
    virtual IOReturn complete(IODirection)=0;
    virtual size_t readBytes(uint64_t,void *,size_t)=0;
    virtual size_t writeBytes(uint64_t,const void *,size_t)=0;
};
#endif
