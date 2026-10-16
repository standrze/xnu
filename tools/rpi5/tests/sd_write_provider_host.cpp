/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual provider/descriptor/transfer/queue/policy code, explicit host API and
 * transport doubles. No real IOKit threads, device mappings, MMIO or SD access. */
#include "../../../iokit/Kernel/BCM2712SDWriteStorage.cpp"
#include <chrono>
#include <future>
#include <vector>
#include <cstdarg>
#include <string>

static std::string startupLog;
int hostKprintf(const char *format,...)
{
    char buffer[512]; va_list args; va_start(args,format);
    int count=std::vsnprintf(buffer,sizeof buffer,format,args); va_end(args);
    assert(count>=0 && unsigned(count)<sizeof buffer); startupLog+=buffer; return count;
}
static struct { bool active=false; unsigned fault=0,reads=0; } startup;
static void put32(uint8_t *p,uint32_t value,bool big)
{
    for (unsigned i=0;i<4;i++) p[i]=uint8_t(value>>(8*(big?3-i:i)));
}
static void startupSector(uint64_t block,void *data)
{
    auto *p=static_cast<uint8_t *>(data); std::memset(p,0,512);
    if (!block) {
        put32(p+440,0x5ae1f07e,false); p[510]=0x55; p[511]=0xaa;
        p[446]=0x80; p[450]=0x0c; put32(p+454,2048,false); put32(p+458,1048576,false);
        p[466]=0xaf; put32(p+470,RPI5_SD_WRITE_START,false); put32(p+474,RPI5_SD_WRITE_BLOCKS,false);
    } else {
        p[0]=0x48; p[1]=0x2b; p[3]=4;
        put32(p+4,startup.fault==9?0x2000:0x80000100,true);
        put32(p+40,4096,true); put32(p+44,32768,true); put32(p+48,32000,true); put32(p+52,100,true);
    }
}

static std::atomic<unsigned> allocated{0},freed{0};
static thread_local bool failAllocation=false;
void *IOMallocData(size_t bytes)
{
    assert(!heldLocks);
    if (failAllocation) return nullptr;
    void *p=std::calloc(1,bytes); assert(p); allocated++; return p;
}
void IOFreeData(void *p,size_t) { assert(p && !heldLocks); freed++; std::free(p); }
struct Memory : IOMemoryDescriptor {
    std::vector<uint8_t> bytes;
    IODirection dir;
    std::atomic<unsigned> retains{0},releases{0},prepares{0},completes{0};
    int prepareError=0,completeError=0;
    bool shortRead=false,shortWrite=false;
    Memory(unsigned count,IODirection d):bytes(count*512,0x5a),dir(d) {}
    IODirection getDirection() const override { return dir; }
    uint64_t getLength() const override { return bytes.size(); }
    void retain() override { retains++; }
    void release() override { assert(retains>releases); releases++; }
    IOReturn prepare(IODirection d) override { assert(!heldLocks && d==dir); prepares++; return prepareError; }
    IOReturn complete(IODirection d) override { assert(!heldLocks && d==dir); completes++; return completeError; }
    size_t readBytes(uint64_t offset,void *out,size_t size) override
    { assert(!heldLocks && offset+size<=bytes.size()); std::memcpy(out,bytes.data()+offset,size); return shortRead?size-1:size; }
    size_t writeBytes(uint64_t offset,const void *in,size_t size) override
    { assert(!heldLocks && offset+size<=bytes.size()); std::memcpy(bytes.data()+offset,in,size); return shortWrite?size-1:size; }
};
struct Transport {
    std::mutex mutex;
    std::condition_variable cv;
    bool blockFirst=false,entered=false,released=false;
    unsigned sectors=0,errorSector=0;
    int readError=0,syncError=0;
    std::vector<char> operations;
    void waitEntered()
    {
        std::unique_lock<std::mutex> lock(mutex);
        assert(cv.wait_for(lock,std::chrono::seconds(3),[&]{return entered;}));
    }
    void unblock() { std::lock_guard<std::mutex> lock(mutex); released=true; cv.notify_all(); }
};
static Transport *transport;
extern "C" int rpi5_sd_write_sector(rpi5_sd_card *,rpi5_sd_write_policy *policy,uint64_t epoch,
    uint64_t block,const void *data,size_t bytes)
{
    assert(!heldLocks && rpi5_sd_write_request_valid(policy,epoch,block,1,bytes));
    for (unsigned i=0;i<bytes;i++) assert(static_cast<const uint8_t *>(data)[i]==0x5a);
    std::unique_lock<std::mutex> lock(transport->mutex);
    transport->operations.push_back('w');
    unsigned sector=++transport->sectors;
    if (sector==1 && transport->blockFirst) {
        transport->entered=true; transport->cv.notify_all();
        assert(transport->cv.wait_for(lock,std::chrono::seconds(3),[]{return transport->released;}));
    }
    return sector==transport->errorSector ? RPI5_SD_TIMEOUT : RPI5_SD_OK;
}
extern "C" int rpi5_sd_read_sector(rpi5_sd_card *,uint64_t block,void *data,size_t bytes)
{
    assert(!heldLocks && bytes==512);
    if (startup.active) {
        startup.reads++;
        if (startup.fault==5+startup.reads) return RPI5_SD_TIMEOUT;
        startupSector(block,data); return RPI5_SD_OK;
    }
    std::lock_guard<std::mutex> lock(transport->mutex); transport->operations.push_back('r');
    std::memset(data,static_cast<int>(block&255),bytes); return transport->readError;
}
extern "C" int rpi5_sd_write_wait_ready(rpi5_sd_card *,rpi5_sd_write_policy *policy,uint64_t epoch)
{
    assert(!heldLocks && rpi5_sd_write_request_valid(policy,epoch,RPI5_SD_WRITE_START,1,512));
    std::lock_guard<std::mutex> lock(transport->mutex); transport->operations.push_back('s'); return transport->syncError;
}
/* Explicit initializer transport doubles. The real initialize() control flow,
 * admission policy and cleanup run below; this is not hardware observation. */
extern "C" int rpi5_sd_handoff(const rpi5_sd_platform_io *,uint32_t,uint32_t,rpi5_sd_handoff_result *)
{ assert(startup.active); return startup.fault==1?RPI5_SD_TIMEOUT:RPI5_SD_OK; }
extern "C" int rpi5_sd_start_identified(rpi5_sd_card *card,const rpi5_sd_io *io,uint32_t,rpi5_sd_identity *identity)
{
    assert(startup.active);
    if (startup.fault==2) { card->last_command=9; return RPI5_SD_CONTROLLER; }
    static const uint8_t cid[16]={0x1b,0x53,0x4d,0x47,0x44,0x32,0x53,0x35,0x30,0x65,0x4f,0x68,0xd1,0xa1,0x61,0};
    static const uint8_t csd[16]={0x40,0x0e,0,0x32,0xdb,0x79,0,3,0xba,0xff,0x7f,0x80,0x0a,0x40,0,0};
    std::memcpy(identity->cid,cid,16); std::memcpy(identity->csd,csd,16);
    card->io=*io; card->ready=1; card->sectors=250347520;
    if (startup.fault==10) identity->cid[0]^=1;
    if (startup.fault==11) identity->csd[0]^=1;
    if (startup.fault==12) card->sectors++;
    return RPI5_SD_OK;
}
extern "C" int rpi5_sd_cache_probe_traced(rpi5_sd_card *card,rpi5_sd_cache_observation *cache,void *,size_t,
    rpi5_sd_cache_diagnostic *trace)
{
    assert(startup.active); card->last_command=48;
    assert(trace); std::memset(trace,0,sizeof *trace);
    if (startup.fault==4) {
        trace->stage=RPI5_SD_CACHE_STAGE_GENERAL_DECODE;
        trace->specification=6; trace->scr[0]=2; trace->payload_bytes=17;
        for (unsigned i=0;i<trace->payload_bytes;i++) trace->payload[i]=uint8_t(i);
        return RPI5_SD_UNSUPPORTED;
    }
    cache->state=startup.fault==5?RPI5_SD_CACHE_ENABLED:startup.fault==13?RPI5_SD_CACHE_UNKNOWN:RPI5_SD_CACHE_DISABLED;
    cache->specification=6; return RPI5_SD_OK;
}

struct Record {
    std::mutex mutex; std::condition_variable cv;
    unsigned callbacks=0; IOReturn status=999; UInt64 actual=999;
    BCM2712SDWriteStorage *reenter=nullptr;
    bool stopInside=false;
    static void callback(void *target,void *,IOReturn status,UInt64 actual)
    {
        auto &r=*static_cast<Record *>(target); assert(!heldLocks);
        if (r.reenter) {
            assert(r.reenter->doSynchronize(0,0,0)==kIOReturnNotPermitted);
            if (r.stopInside) { IOService upstream; r.reenter->stop(&upstream); }
        }
        std::lock_guard<std::mutex> lock(r.mutex);
        assert(!r.callbacks); r.callbacks++; r.status=status; r.actual=actual; r.cv.notify_all();
    }
    void wait(IOReturn expected,UInt64 bytes)
    {
        std::unique_lock<std::mutex> lock(mutex);
        assert(cv.wait_for(lock,std::chrono::seconds(3),[&]{return callbacks==1;}));
        assert(status==expected && actual==bytes);
    }
};
struct SDWriteProviderHostTest {
    static void initializationModels()
    {
        static const char *stages[]={"", "HANDOFF", "IDENTIFY", "ALLOCATE", "CACHE_PROBE", "CACHE_REFUSED",
            "MBR_READ", "PRIMARY_READ", "ALTERNATE_READ", "AUTHORIZE", "AUTHORIZE", "AUTHORIZE", "AUTHORIZE", "CACHE_REFUSED"};
        for (unsigned fault=0;fault<14;fault++) {
            startup.active=true; startup.fault=fault; startup.reads=0; startupLog.clear();
            BCM2712SDWriteStorage device;
            failAllocation=fault==3;
            bool result=device.initialize();
            failAllocation=false; startup.active=false;
            assert(result==!fault);
            assert(startup.reads==(fault<6 && fault?0:fault>=6 && fault<=8?fault-5:fault==13?0:3));
            assert(!device.mediaOnline && !device.writeAdmitted && !device.workerRunning);
            if (fault) {
                std::string marker=std::string("RPI5XNU:SD:WRITE_INIT_FAIL STAGE=")+stages[fault]+" RC=";
                assert(startupLog.find(marker)!=std::string::npos);
                assert(startupLog.find("WRITE_ADMITTED")==std::string::npos);
                assert(device.policy.state!=RPI5_SD_WRITE_ENABLED);
                if (fault==4) {
                    assert(startupLog.find("CACHE_PROBE_FAIL STAGE=7 RC=-5 SPEC=6 FUNCTION=0 ADDRESS=0x0 SCR=0200000000000000 BYTES=17")!=std::string::npos);
                    assert(startupLog.find("CACHE_PROBE_BYTES OFFSET=0 HEX=000102030405060708090a0b0c0d0e0f\n")!=std::string::npos);
                    assert(startupLog.find("CACHE_PROBE_BYTES OFFSET=16 HEX=10\n")!=std::string::npos);
                    assert(startupLog.find("CACHE_PROBE_BYTES OFFSET=32")==std::string::npos);
                } else assert(startupLog.find("CACHE_PROBE_FAIL")==std::string::npos);
            } else {
                assert(device.policy.state==RPI5_SD_WRITE_ENABLED && device.publishedEpoch);
                assert(startupLog.find("WRITE_INIT_FAIL")==std::string::npos);
            }
        }
        startupLog.clear();
    }
    BCM2712SDWriteStorage device;
    IOService upstream;
    UInt32 banks[5][64]={};
    std::thread worker;
    SDWriteProviderHostTest()
    {
        device.queueLock=IOLockAlloc(); device.card.ready=1; device.card.sectors=250347520;
        device.card.rca=0x12340000;
        device.policy={7,RPI5_SD_WRITE_START,RPI5_SD_WRITE_BLOCKS,
            RPI5_SD_WRITE_MAX_REQUEST_BLOCKS,RPI5_SD_WRITE_ENABLED};
        device.sectorCount=device.card.sectors; device.publishedEpoch=7;
        device.cache.state=RPI5_SD_CACHE_DISABLED;
        device.requests.accepting=1; device.mediaOnline=device.writeAdmitted=device.workerRunning=true;
        for (unsigned i=0;i<5;i++) { device.binding.size[i]=sizeof banks[i]; device.registers[i]=reinterpret_cast<uintptr_t>(banks[i]); }
        banks[RPI5_SD_HOST][0x24/4]=0x10000;
        device.retain(); worker=std::thread([&]{device.worker();});
    }
    ~SDWriteProviderHostTest()
    {
        device.stop(&upstream); worker.join();
        assert(!device.requests.head && !device.requests.active && !device.workerRunning);
        assert(device.references==1); device.free();
    }
    IOReturn submit(Memory &memory,uint64_t block,Record &record)
    {
        IOStorageCompletion completion={&record,Record::callback,nullptr};
        return device.doAsyncReadWrite(&memory,block,memory.bytes.size()/512,nullptr,&completion);
    }
    void waitQueue(unsigned count,bool closing=false)
    {
        auto end=std::chrono::steady_clock::now()+std::chrono::seconds(3);
        for (;;) {
            IOLockLock(device.queueLock);
            bool ready=closing ? !device.requests.accepting : device.requests.queued==count;
            IOLockUnlock(device.queueLock);
            if (ready) return;
            assert(std::chrono::steady_clock::now()<end);
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }
    bool quarantined() { return !device.card.ready && device.policy.state==RPI5_SD_WRITE_QUARANTINED; }
    void modelCacheEnabledBeforeEnqueue()
    {
        IOLockLock(device.queueLock);
        assert(!device.requests.head && !device.requests.active);
        device.cache.state=RPI5_SD_CACHE_ENABLED;
        IOLockUnlock(device.queueLock);
    }
};
static void pairing(const Memory &memory)
{
    assert(memory.retains==memory.releases && memory.prepares==1 && memory.completes==1);
}
static void ordering_and_snapshot()
{
    Transport t; t.blockFirst=true; transport=&t;
    SDWriteProviderHostTest h; Memory write(2,kIODirectionOut),read(1,kIODirectionIn),after(1,kIODirectionOut);
    Record w,r,a;
    assert(h.submit(write,RPI5_SD_WRITE_START,w)==0); t.waitEntered();
    std::memset(write.bytes.data(),0xcc,write.bytes.size()); /* Snapshot already owned. */
    assert(h.submit(read,0,r)==0);
    auto sync=std::async(std::launch::async,[&]{return h.device.doSynchronize(0,0,0);});
    h.waitQueue(2); assert(h.submit(after,RPI5_SD_WRITE_START+2,a)==0); t.unblock();
    w.wait(0,1024); r.wait(0,512); a.wait(0,512); assert(sync.get()==0);
    assert(t.operations==std::vector<char>({'w','w','r','s','w'}));
    pairing(write); pairing(read); pairing(after);
    assert(write.retains==2 && read.retains==2 && after.retains==2);
}
static void failed_write_drains_without_more_transport()
{
    Transport t; t.blockFirst=true; t.errorSector=2; transport=&t;
    SDWriteProviderHostTest h; Memory write(2,kIODirectionOut),read(1,kIODirectionIn); Record w,r;
    assert(h.submit(write,RPI5_SD_WRITE_START,w)==0); t.waitEntered();
    assert(h.submit(read,0,r)==0);
    auto sync=std::async(std::launch::async,[&]{return h.device.doSynchronize(0,0,0);});
    h.waitQueue(2); t.unblock();
    w.wait(kIOReturnTimeout,512); r.wait(kIOReturnOffline,0); assert(sync.get()==kIOReturnOffline);
    assert(h.quarantined() && t.operations==std::vector<char>({'w','w'})); pairing(write);
    assert(read.prepares==0 && read.retains==read.releases);
    bool value=false; assert(h.device.reportWriteProtection(&value)==kIOReturnNoMedia && value);
    assert(h.device.getWriteCacheState(&value)==kIOReturnNoMedia);
}
static void stop_cancels_active_and_queued_requests()
{
    Transport t; t.blockFirst=true; transport=&t;
    SDWriteProviderHostTest h; Memory write(2,kIODirectionOut),read(1,kIODirectionIn); Record w,r;
    assert(h.submit(write,RPI5_SD_WRITE_START,w)==0); t.waitEntered();
    assert(h.submit(read,0,r)==0);
    auto sync=std::async(std::launch::async,[&]{return h.device.doSynchronize(0,0,0);});
    h.waitQueue(2);
    auto stop=std::async(std::launch::async,[&]{h.device.stop(&h.upstream);});
    h.waitQueue(0,true); t.unblock();
    w.wait(kIOReturnOffline,512); r.wait(kIOReturnOffline,0);
    assert(sync.get()==kIOReturnOffline); stop.get();
    assert(h.quarantined() && t.operations==std::vector<char>({'w'})); pairing(write);
}
static void completion_reentrancy_and_rejection()
{
    Transport t; t.blockFirst=true; transport=&t;
    SDWriteProviderHostTest h; Memory write(1,kIODirectionOut),read(1,kIODirectionIn); Record w,r;
    w.reenter=&h.device; w.stopInside=true;
    assert(h.submit(write,0,w)==kIOReturnNotPermitted && !w.callbacks);
    assert(write.retains==write.releases && !write.prepares);
    interruptContext=true;
    assert(h.submit(write,RPI5_SD_WRITE_START,w)==kIOReturnNotPermitted);
    assert(h.device.doSynchronize(0,0,0)==kIOReturnNotPermitted); interruptContext=false;
    assert(h.device.doSynchronize(UINT64_MAX,0,0)==kIOReturnBadArgument);
    assert(h.device.doSynchronize(0,UINT64_MAX,0)==kIOReturnBadArgument);
    assert(h.device.doSynchronize(0,0,1)==kIOReturnUnsupported);
    failAllocation=true; assert(h.submit(write,RPI5_SD_WRITE_START,w)==kIOReturnNoMemory); failAllocation=false;
    assert(h.submit(write,RPI5_SD_WRITE_START,w)==0); t.waitEntered();
    assert(h.submit(read,0,r)==0); t.unblock();
    w.wait(0,512); r.wait(kIOReturnOffline,0); pairing(write);
}
static void removal_is_not_hot_reinsertion()
{
    Transport t; transport=&t;
    SDWriteProviderHostTest h; Memory write(1,kIODirectionOut); Record w,again;
    h.banks[RPI5_SD_HOST][0x24/4]=0;
    assert(h.submit(write,RPI5_SD_WRITE_START,w)==0); w.wait(kIOReturnOffline,0);
    assert(h.quarantined() && t.operations.empty() && !write.prepares);
    h.banks[RPI5_SD_HOST][0x24/4]=0x10000;
    assert(h.submit(write,RPI5_SD_WRITE_START,again)==kIOReturnNoMedia && !again.callbacks);
}
static void descriptor_failure_pairing_and_no_unapproved_io()
{
    for (unsigned mode=0;mode<5;mode++) {
        Transport t; transport=&t; SDWriteProviderHostTest h;
        Memory memory(1,mode==3 || mode==4?kIODirectionIn:kIODirectionOut); Record record;
        if (mode==0) memory.prepareError=-777;
        if (mode==1) memory.shortRead=true;
        if (mode==2) memory.completeError=-778;
        if (mode==3) memory.shortWrite=true;
        if (mode==4) t.readError=RPI5_SD_TIMEOUT;
        assert(h.submit(memory,RPI5_SD_WRITE_START,record)==0);
        record.wait(mode==0?-777:mode==2?-778:mode==4?kIOReturnTimeout:kIOReturnUnderrun,
                    mode==2?512:0);
        assert(memory.retains==memory.releases && memory.prepares==1);
        assert(memory.completes==(mode==0?0:1));
        if (mode<2) assert(t.operations.empty() && !h.quarantined());
        else assert(t.operations==std::vector<char>({mode==2?'w':'r'}));
        if (mode==2 || mode==4) assert(h.quarantined());
    }
}
static void failed_sync_and_unknown_cache_refuse_later_io()
{
    for (unsigned mode=0;mode<3;mode++) {
        Transport t; transport=&t; SDWriteProviderHostTest h;
        if (mode==0) t.syncError=RPI5_SD_TIMEOUT;
        if (mode==1) assert(h.device.setWriteCacheState(true)==kIOReturnUnsupported);
        if (mode==1) {
            assert(h.device.doSynchronize(0,0,0)==0);
            assert(t.operations==std::vector<char>({'s'}));
            continue;
        }
        if (mode==2) {
            /* Worker has no requests yet; direct MODEL injection before enqueue. */
            h.modelCacheEnabledBeforeEnqueue();
        }
        assert(h.device.doSynchronize(0,0,0)==(mode==0?kIOReturnTimeout:kIOReturnUnsupported));
        assert(h.quarantined());
        assert(t.operations==(mode==0?std::vector<char>({'s'}):std::vector<char>{}));
        Memory memory(1,kIODirectionOut); Record record;
        assert(h.submit(memory,RPI5_SD_WRITE_START,record)==kIOReturnNoMedia);
        assert(!record.callbacks && !memory.prepares && memory.retains==memory.releases);
    }
}
int main()
{
    SDWriteProviderHostTest::initializationModels();
    ordering_and_snapshot(); failed_write_drains_without_more_transport();
    stop_cancels_active_and_queued_requests(); completion_reentrancy_and_rejection();
    removal_is_not_hot_reinsertion();
    descriptor_failure_pairing_and_no_unapproved_io(); failed_sync_and_unknown_cache_refuse_later_io();
    assert(allocated==freed && !heldLocks);
    std::puts("SD_WRITE_PROVIDER_HOST_PASS");
}
