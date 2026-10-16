/* SPDX-License-Identifier: BSD-2-Clause
 * Project-owned VM-only Ethernet glue for the real XNU BSD network stack.
 * One permanent device, bounded software queue, polled split rings. No offload,
 * physical bus, hot removal, proprietary networking archive or host HTTP proxy.
 */
#include <IOKit/IOService.h>
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOLocks.h>
#include <libkern/c++/OSData.h>
#include <kern/thread.h>
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wzero-as-null-pointer-constant"
extern "C" {
#include <sys/errno.h>
#include <sys/socket.h>
#include <sys/sockio.h>
#include <sys/sysctl.h>
#include <sys/kpi_mbuf.h>
#include <net/if.h>
#include <net/if_types.h>
#include <net/ethernet.h>
#include <net/if_ether.h>
#include <net/bpf.h>
#include <net/kpi_interface.h>
#include "virtio_net.h"
vm_offset_t ml_io_map(vm_offset_t, vm_size_t);
unsigned rpi5_physical_memory_type(uint64_t, uint64_t);
}
#pragma clang diagnostic pop
bool vz_network_start(IOService *);
static int64_t vz_net_rejected;
SYSCTL_QUAD(_debug, OID_AUTO, vznet_rx_rejected, CTLFLAG_RD | CTLFLAG_LOCKED, &vz_net_rejected,
    "VM-only rejected RX metadata: len16 flags8 gso8 checksum-start16 checksum-offset16");

class VZVirtioNetwork : public IOService {
    OSDeclareDefaultStructors(VZVirtioNetwork);
    struct Packet { size_t size; unsigned char bytes[VZ_NET_FRAME_MAX]; };
    vz_net_device device = {};
    vz_net_queue rings = {};
    IOBufferMemoryDescriptor *dma = nullptr;
    IOLock *lock = nullptr;
    ifnet_t interface = nullptr;
    Packet *outgoing = nullptr;
    unsigned head = 0, count = 0;
    bool failed = false;
    static uintptr_t map(uint64_t pa, size_t n) {
        if (!n || pa >= (1ULL << 36) || n > (1ULL << 36) - pa ||
            rpi5_physical_memory_type(pa & ~UINT64_C(0x3fff), (pa + n + 0x3fff) & ~UINT64_C(0x3fff)) != 2) return 0;
        return ml_io_map(pa, n);
    }
    static void workerEntry(void *p, wait_result_t) { static_cast<VZVirtioNetwork *>(p)->worker(); }
    static errno_t output(ifnet_t, mbuf_t);
    static errno_t ioctl(ifnet_t, unsigned long, void *);
    [[noreturn]] static void detached(ifnet_t) { panic("VZNET: permanent interface detached"); }
    bool attachInterface();
    void worker();
public:
    bool start(IOService *) APPLE_KEXT_OVERRIDE;
    bool terminate(IOOptionBits = 0) APPLE_KEXT_OVERRIDE { return false; }
    bool requestTerminate(IOService *, IOOptionBits) APPLE_KEXT_OVERRIDE { return false; }
};
OSDefineMetaClassAndStructors(VZVirtioNetwork, IOService)

bool VZVirtioNetwork::start(IOService *provider)
{
    OSData *data = OSDynamicCast(OSData, provider->getProperty("vz-net"));
    if (!data || data->getLength() != sizeof(device) || !IOService::start(provider)) return false;
    memcpy(&device, data->getBytesNoCopy(), sizeof(device));
    lock = IOLockAlloc();
    outgoing = static_cast<Packet *>(IOMallocZeroData(sizeof(Packet) * 32));
    if (!lock || !outgoing) return false;
    thread_t thread = THREAD_NULL;
    retain(); /* Permanent worker owns this object and DMA until VM termination. */
    if (kernel_thread_start(workerEntry, this, &thread) != KERN_SUCCESS) return false;
    thread_deallocate(thread);
    return true;
}

bool VZVirtioNetwork::attachInterface()
{
    dma = IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,
        kIODirectionInOut | kIOMemoryPhysicallyContiguous, VZ_NET_DMA_BYTES, 0x4000);
    if (!dma || dma->prepare() != kIOReturnSuccess) { kprintf("VZXNU:NET:DMA_FAILED\n"); return false; }
    IOByteCount contiguous = 0;
    IOPhysicalAddress pa = dma->getPhysicalSegment(0, &contiguous);
    if (contiguous < VZ_NET_DMA_BYTES || vz_net_start(&device, &rings, map, dma->getBytesNoCopy(), pa)) {
        kprintf("VZXNU:NET:TRANSPORT_FAILED STAGE=%u CONTIG=%llu PA=%llx FEATURES=%08x:%08x\n",
            rings.stage, contiguous, pa, rings.features_high, rings.features_low);
        return false;
    }
    struct ifnet_init_eparams params = {};
    params.ver = IFNET_INIT_CURRENT_VERSION;
    params.len = sizeof(params);
    params.flags = IFNET_INIT_LEGACY | IFNET_INIT_NX_NOAUTO;
    params.name = "en";
    params.unit = 0;
    params.family = IFNET_FAMILY_ETHERNET;
    params.type = IFT_ETHER;
    params.output = output;
    params.demux = ether_demux;
    params.add_proto = ether_add_proto;
    params.del_proto = ether_del_proto;
    params.check_multi = ether_check_multi;
    params.framer_extended = ether_frameout_extended;
    params.softc = this;
    params.ioctl = ioctl;
    params.detach = detached;
    static const unsigned char broadcast[ETHER_ADDR_LEN] = {255, 255, 255, 255, 255, 255};
    params.broadcast_addr = broadcast;
    params.broadcast_len = ETHER_ADDR_LEN;
    int error = ifnet_allocate_extended(&params, &interface);
    if (error) { kprintf("VZXNU:NET:ALLOC_FAILED %d\n", error); return false; }
    if (ifnet_set_addrlen(interface, ETHER_ADDR_LEN) || ifnet_set_hdrlen(interface, ETHER_HDR_LEN) ||
        ifnet_set_mtu(interface, 1500) ||
        ifnet_set_flags(interface, IFF_BROADCAST | IFF_SIMPLEX | IFF_MULTICAST, 0xffff)) return false;
    error = ifnet_attach(interface, nullptr);
    if (error) { kprintf("VZXNU:NET:ATTACH_FAILED %d\n", error); return false; }
    if (ifnet_set_lladdr(interface, rings.mac, ETHER_ADDR_LEN)) return false;
    bpfattach(interface, DLT_EN10MB, ETHER_HDR_LEN);
    kprintf("VZXNU:NET:READY en0 MAC=%02x:%02x:%02x:%02x:%02x:%02x MTU=1500\n",
        rings.mac[0], rings.mac[1], rings.mac[2], rings.mac[3], rings.mac[4], rings.mac[5]);
    registerService();
    return true;
}

errno_t VZVirtioNetwork::ioctl(ifnet_t ifp, unsigned long cmd, void *data)
{
    switch (cmd) {
    case SIOCSIFFLAGS:
        return ifnet_set_flags(ifp, (ifnet_flags(ifp) & IFF_UP) ? IFF_RUNNING : 0, IFF_RUNNING);
    case SIOCSIFADDR:
        return ifnet_set_flags(ifp, IFF_UP | IFF_RUNNING, IFF_UP | IFF_RUNNING);
    case SIOCSIFMTU: {
        struct ifreq *request = static_cast<struct ifreq *>(data);
        if (!request || request->ifr_mtu < 68 || request->ifr_mtu > 1500) return EINVAL;
        return ifnet_set_mtu(ifp, static_cast<uint32_t>(request->ifr_mtu));
    }
    case SIOCADDMULTI:
    case SIOCDELMULTI:
        return 0; /* Device's default receive filter; no multicast offload. */
    default:
        return EOPNOTSUPP;
    }
}

errno_t VZVirtioNetwork::output(ifnet_t ifp, mbuf_t packet)
{
    VZVirtioNetwork *self = static_cast<VZVirtioNetwork *>(ifnet_softc(ifp));
    size_t size = mbuf_pkthdr_len(packet);
    errno_t result = 0;
    bpf_tap_out(ifp, DLT_EN10MB, packet, nullptr, 0);
    IOLockLock(self->lock);
    if (self->failed) result = ENETDOWN;
    else if (size < ETHER_HDR_LEN || size > VZ_NET_FRAME_MAX) result = EMSGSIZE;
    else if (self->count == 32) result = ENOBUFS;
    else {
        Packet *target = &self->outgoing[(self->head + self->count) % 32];
        result = mbuf_copydata(packet, 0, size, target->bytes);
        if (!result) { target->size = size; self->count++; }
    }
    IOLockUnlock(self->lock);
    mbuf_freem(packet); /* The legacy output callback owns the packet on all paths. */
    return result;
}

void VZVirtioNetwork::worker()
{
    /* Platform services can start before BSD's dlil/socket/protocol init. The
     * IOBSD resource is published after those initializations by bsd_autoconf. */
    if (!waitForService(resourceMatching("IOBSD")) || !attachInterface()) {
        kprintf("VZXNU:NET:START_FAILED\n");
        IOLockLock(lock); failed = true; IOLockUnlock(lock);
        return;
    }
    unsigned char incoming[VZ_NET_FRAME_MAX];
    for (;;) {
        Packet current;
        IOLockLock(lock);
        bool pending = count != 0;
        if (pending) current = outgoing[head];
        IOLockUnlock(lock);
        if (pending) {
            int result = vz_net_send(&rings, current.bytes, current.size);
            if (result < 0) break;
            if (!result) {
                IOLockLock(lock); head = (head + 1) % 32; count--; IOLockUnlock(lock);
                ifnet_stat_increment_out(interface, 1, static_cast<uint32_t>(current.size), 0);
            }
        }
        for (unsigned batch = 0; batch < 32; batch++) {
            size_t size = 0;
            int result = vz_net_receive(&rings, incoming, &size);
            if (result < 0) goto fault;
            if (!result) break;
            if (result == 2) {
                vz_net_rejected = static_cast<int64_t>(rings.last_rejected);
                ifnet_stat_increment_in(interface, 0, 0, 1);
                continue;
            }
            mbuf_t packet = nullptr;
            if (mbuf_getpacket(MBUF_DONTWAIT, &packet) || !packet) continue;
            if (mbuf_copyback(packet, 0, size, incoming, MBUF_DONTWAIT)) { mbuf_freem(packet); continue; }
            mbuf_pkthdr_setlen(packet, size);
            mbuf_pkthdr_setrcvif(packet, interface);
            mbuf_pkthdr_setheader(packet, mbuf_data(packet));
            bpf_tap_in(interface, DLT_EN10MB, packet, nullptr, 0);
            mbuf_adj(packet, ETHER_HDR_LEN);
            struct ifnet_stat_increment_param stats = {};
            stats.packets_in = 1;
            stats.bytes_in = static_cast<uint32_t>(size);
            ifnet_input(interface, packet, &stats);
        }
        IOSleep(1);
    }
fault:
    IOLockLock(lock); failed = true; IOLockUnlock(lock);
    ifnet_set_flags(interface, 0, IFF_RUNNING);
    kprintf("VZXNU:NET:DEVICE_FAILED\n");
    /* No DMA/object free: a failed virtual device remains pinned until VM exit. */
}

bool vz_network_start(IOService *provider)
{
    VZVirtioNetwork *service = new VZVirtioNetwork;
    bool ok = service && service->init() && service->attach(provider) && service->start(provider);
    if (service) service->release();
    return ok;
}
