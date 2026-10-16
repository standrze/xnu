/* SPDX-License-Identifier: BSD-2-Clause */
/* Compile-only ABI spell check against Apple's installed Kernel.framework. */
#include <IOKit/network/IOEthernetController.h>
#include <IOKit/network/IOEthernetInterface.h>
#include <IOKit/network/IOOutputQueue.h>
#include <type_traits>

static_assert(kIOEthernetAddressSize == 6);
static_assert(kIOEthernetMaxPacketSize == 1518);
static_assert(kIOEthernetCRCSize == 4);
static_assert(kIOReturnOutputSuccess == 0x0000);
static_assert(kIOReturnOutputDropped == 0x0001);
static_assert(kIOReturnOutputStall == 0x0102);
static_assert(IOEthernetInterface::kInputOptionQueuePacket == 1);

using OutputPacket = UInt32 (IONetworkController:: *)(mbuf_t, void *);
using GetAddress = IOReturn (IOEthernetController:: *)(IOEthernetAddress *);
using InputPacket = UInt32 (IONetworkInterface:: *)(mbuf_t, UInt32,
    IOOptionBits, void *);
using FlushInput = UInt32 (IONetworkInterface:: *)(void);

static_assert(std::is_same_v<decltype(&IONetworkController::outputPacket),
    OutputPacket>);
static_assert(std::is_same_v<
    decltype(static_cast<GetAddress>(&IOEthernetController::getHardwareAddress)),
    GetAddress>);
static_assert(std::is_same_v<decltype(&IONetworkInterface::inputPacket),
    InputPacket>);
static_assert(std::is_same_v<decltype(&IONetworkInterface::flushInputQueue),
    FlushInput>);
