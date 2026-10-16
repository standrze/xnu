/* SPDX-License-Identifier: BSD-2-Clause */
/* Explicit host doubles, NOT Apple IOKit/kernel implementations. */
#ifndef RPI5_WRITE_PROVIDER_HOST_DOUBLES_H
#define RPI5_WRITE_PROVIDER_HOST_DOUBLES_H
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <thread>
using UInt8=uint8_t; using UInt32=uint32_t; using UInt64=uint64_t;
using vm_offset_t=uintptr_t; using IOReturn=int; using IOByteCount=uint64_t;
using IOStorageSynchronizeOptions=uint32_t; using IOStorageUnmapOptions=uint32_t;
enum IODirection { kIODirectionNone=0,kIODirectionIn=1,kIODirectionOut=2,kIODirectionInOut=3 };
enum { kIOReturnSuccess=0,kIOReturnBadArgument=-101,kIOReturnTimeout=-102,
    kIOReturnNoMedia=-103,kIOReturnOffline=-104,kIOReturnUnderrun=-105,
    kIOReturnIOError=-106,kIOReturnNotPermitted=-107,kIOReturnNoMemory=-108,
    kIOReturnUnsupported=-109,kIOReturnNotWritable=-110,kIOReturnNoResources=-111 };
inline thread_local unsigned heldLocks=0;
inline thread_local bool interruptContext=false;
struct IOLock { std::mutex mutex; std::condition_variable cv; };
inline IOLock *IOLockAlloc() { return new IOLock; }
inline void IOLockFree(IOLock *lock) { delete lock; }
inline void IOLockLock(IOLock *lock) { lock->mutex.lock(); heldLocks++; }
inline void IOLockUnlock(IOLock *lock) { assert(heldLocks); heldLocks--; lock->mutex.unlock(); }
inline void IOLockWakeup(IOLock *lock,void *,bool) { lock->cv.notify_all(); }
inline int IOLockSleep(IOLock *lock,void *,int)
{
    assert(heldLocks); heldLocks--;
    std::unique_lock<std::mutex> guard(lock->mutex,std::adopt_lock);
    lock->cv.wait(guard); guard.release(); heldLocks++;
    return 0;
}
using thread_t=void *; using wait_result_t=int;
inline constexpr thread_t THREAD_NULL=nullptr;
inline constexpr int THREAD_UNINT=0,KERN_SUCCESS=0;
inline thread_t current_thread() { static thread_local int identity; return &identity; }
inline int kernel_thread_start(void (*)(void *,wait_result_t),void *,thread_t *) { std::abort(); }
inline void thread_deallocate(thread_t) { std::abort(); }
extern "C" inline void thread_terminate_self() {}
inline bool ml_at_interrupt_context() { return interruptContext; }
inline void IODelay(UInt32) {}
inline void clock_get_uptime(uint64_t *value) { *value=0; }
inline void absolutetime_to_nanoseconds(uint64_t value,uint64_t *out) { *out=value; }
inline bool PE_parse_boot_argn(const char *,void *,int) { return false; }
#define APPLE_KEXT_OVERRIDE override
#define OSDeclareDefaultStructors(name) public: name()=default; ~name() override=default; private:
#define OSDefineMetaClassAndStructors(name,base)
#define OSDynamicCast(type,value) dynamic_cast<type *>(value)
#define panic(...) std::abort()
int hostKprintf(const char *,...);
#define kprintf hostKprintf
void *IOMallocData(size_t);
void IOFreeData(void *,size_t);
template<class T> T *hostAllocType() { return static_cast<T *>(IOMallocData(sizeof(T))); }
#define IOMallocType(type) hostAllocType<type>()
#define IOFreeType(ptr,type) IOFreeData(ptr,sizeof(type))
class OSObject { public: virtual ~OSObject()=default; };
class OSData : public OSObject {
public: unsigned getLength() const { return 0; } const void *getBytesNoCopy() const { return nullptr; }
};
class IOMemoryMap { public: uintptr_t getVirtualAddress() const { return 0; } void release() { std::abort(); } };
inline constexpr int kIOMapAnywhere=1,kIOMapInhibitCache=2;
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
    static IOMemoryDescriptor *withPhysicalAddress(uint64_t,uint64_t,IODirection) { std::abort(); }
    IOMemoryMap *map(int) { std::abort(); }
};
class IOService : public OSObject {
public:
    std::atomic<unsigned> references{1};
    virtual bool start(IOService *) { return true; }
    virtual void stop(IOService *) {}
    virtual void free() {}
    bool open(IOService *) { return true; }
    void close(IOService *) {}
    void retain() { references++; }
    void release() { assert(references.fetch_sub(1)>1); } /* Stack-owned test service. */
    OSObject *getProperty(const char *) { return nullptr; }
    bool setProperty(const char *,UInt64,unsigned) { return true; }
    void registerService() { std::abort(); }
};
struct IOStorageCompletion {
    void *target;
    void (*action)(void *,void *,IOReturn,UInt64);
    void *parameter;
};
struct IOStorageAttributes { uint32_t options; };
inline constexpr uint32_t kIOStorageOptionForceUnitAccess=1,kIOStorageOptionIsStatic=2;
inline constexpr uint32_t kIOStorageSynchronizeOptionBarrier=2;
struct IOBlockStorageDeviceExtent {};
class IOStorage : public IOService {
public:
    static void complete(IOStorageCompletion *c,IOReturn status,UInt64 actual)
    { assert(!heldLocks); c->action(c->target,c->parameter,status,actual); }
};
class IOBlockStorageDevice : public IOStorage {
public:
    virtual IOReturn doAsyncReadWrite(IOMemoryDescriptor *,UInt64,UInt64,IOStorageAttributes *,IOStorageCompletion *)=0;
    virtual IOReturn doSynchronizeCache()=0;
    virtual IOReturn doSynchronize(UInt64,UInt64,IOStorageSynchronizeOptions)=0;
    virtual IOReturn doEjectMedia()=0;
    virtual IOReturn doFormatMedia(UInt64)=0;
    virtual UInt32 doGetFormatCapacities(UInt64 *,UInt32) const=0;
    virtual IOReturn doUnmap(IOBlockStorageDeviceExtent *,UInt32,IOStorageUnmapOptions)=0;
    virtual char *getVendorString()=0;
    virtual char *getProductString()=0;
    virtual char *getRevisionString()=0;
    virtual char *getAdditionalDeviceInfoString()=0;
    virtual IOReturn reportBlockSize(UInt64 *)=0;
    virtual IOReturn reportEjectability(bool *)=0;
    virtual IOReturn reportMaxValidBlock(UInt64 *)=0;
    virtual IOReturn reportMediaState(bool *,bool *)=0;
    virtual IOReturn reportRemovability(bool *)=0;
    virtual IOReturn reportWriteProtection(bool *)=0;
    virtual IOReturn reportPollRequirements(bool *,bool *)=0;
    virtual IOReturn getWriteCacheState(bool *)=0;
    virtual IOReturn setWriteCacheState(bool)=0;
};
inline constexpr char kIOMaximumBlockCountReadKey[]="read-blocks",kIOMaximumByteCountReadKey[]="read-bytes";
inline constexpr char kIOMaximumBlockCountWriteKey[]="write-blocks",kIOMaximumByteCountWriteKey[]="write-bytes";
#endif
