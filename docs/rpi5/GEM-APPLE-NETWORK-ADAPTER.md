# BCM2712 GEM to Apple networking boundary

2026-10-14. This is an offline, default-off interface contract for the step
after bounded GEM packet DMA and interrupt handling pass on the Raspberry Pi 5.
It is not an Ethernet driver, registered interface, packet result, or SSH
result. No target image includes the adapter.

## What already exists

The current Pi kernel contains Apple's BSD networking core and DLIL, including
`ifnet_attach`, `ifnet_input`, `ifnet_output`, mbuf allocation/freeing, IPv4,
TCP/UDP, route sockets, and the tested loopback path. The RAM root contains the
original Apple `network_cmds-396.6` utilities at `/sbin/ifconfig` and
`/sbin/route`. A physical test enumerated `lo0`; it did not create an Ethernet
interface.

The current linked kernel does **not** contain `IONetworkController`,
`IONetworkInterface`, `IOEthernetController`, or `IOEthernetInterface` class
symbols. `IOKitBSDInit.cpp` has a class-name string used to match a future
`IONetworkInterface`, but a string is not the family implementation. Therefore
the controller wrapper cannot honestly publish `en0` yet.

## Apple source pin

The contract was checked against Apple's official current open-source catalog,
which identifies `IONetworkingFamily-186`, and against the public class files,
all twelve implementation units and tagged archive listed with their hashes in
[`ionetworkingfamily_186_sources.json`](../../tools/rpi5/ionetworkingfamily_186_sources.json).
The installed Kernel.framework headers are compiled in the native test as an
independent API spelling check. Relevant original implementations are:

- [`IONetworkController`](https://github.com/apple-oss-distributions/IONetworkingFamily/blob/IONetworkingFamily-186/IONetworkController.cpp)
- [`IONetworkInterface`](https://github.com/apple-oss-distributions/IONetworkingFamily/blob/IONetworkingFamily-186/IONetworkInterface.cpp)
- [`IOEthernetController`](https://github.com/apple-oss-distributions/IONetworkingFamily/blob/IONetworkingFamily-186/IOEthernetController.cpp)
- [`IOEthernetInterface`](https://github.com/apple-oss-distributions/IONetworkingFamily/blob/IONetworkingFamily-186/IOEthernetInterface.cpp)

This workspace is based on `xnu-12377.121.6` (`ac9718fb1af6...`). The catalog
entry that publishes IONetworkingFamily-186 lists `xnu-12377.1.9`, not this
later XNU patch tag. Header spelling and constants match the installed SDK, but
that is not binary/source compatibility proof. Compiling the whole family
against this exact workspace and closing every dependency remains mandatory.

### Exact source-build frontier — 2026-10-14

The original default-off builder
[`build_ionetworkingfamily_186_link_slice.py`](../../tools/rpi5/build_ionetworkingfamily_186_link_slice.py)
uses the actual `DEVELOPMENT_ARM64_BCM2712` compile database and generated XNU
headers. Its v2 result preserved the exact three-unit header frontier described
below. The v3 builder resolves that frontier without editing Apple's source: an
output-only forced preinclude loads the modern template-bearing XNU headers
under C++ linkage before the historical `extern "C"` blocks, and it exports the
exact target-SDK `TargetConditionals.h`. It compiles all twelve original units
as ARM64 Mach-O objects, combines them in an uninstalled static archive, and
links a distinct default-off kernel. It does not edit `iokit/conf/files`, the
board service catalogue, an accepted image, or any Apple source file.

The current report is
`build/rpi5/ionetworkingfamily-186-link-slice-20261014-v3-r5/report.json`,
SHA-256
`f370952ca51f5e4e77ffd2a2d4fd0acbd55901e8227694be32d5e3b63575169f`.
The twelve-object archive has SHA-256
`3004b8185acb562684b9d5f29051e35df2fdd2397e0e5cbc74a2ab0ab5a9a065`.
The distinct linked kernel has SHA-256
`c63ee521517abd91a51ab656e7ef27dc4b7eed015ec26a138194a43dd9493e4b`,
contains the required network class symbols, and has zero undefined symbols.

The preserved v2 result stopped at nine units because three original files hit
the later XNU patch headers:

- `IONetworkInterface.cpp`: C++ templates reached through an Apple `extern
  "C"` include block, plus an unavailable `TargetConditionals.h`;
- `IONetworkStack.cpp`: the same C++-linkage header boundary;
- `IOMbufMemoryCursor.cpp`: the same C++-linkage header boundary.

The v3 compatibility preinclude closes those header-build failures while
leaving the twelve Apple implementation files byte-identical. Eight old/new
tests pin the source hashes, compatibility header, compile commands, complete
archive and default-off kernel link. Production file-list and service-catalogue
wiring remain deliberately absent, so the Apple-family acceptance bit in the
GEM adapter remains false despite the successful link.

The Kernel.framework marks this kext API deprecated in favor of
NetworkingDriverKit on shipping macOS. That does not make DriverKit a substitute
inside this standalone XNU image: the target already has the BSD/DLIL kernel
side, and the open IONetworkingFamily is the matching Apple controller bridge.

## Minimum controller contract

The later C++ wrapper should subclass `IOEthernetController`; generic interface
and BSD plumbing should remain Apple's code. Its minimum responsibilities are:

1. `start(provider)` calls `super::start()`, verifies a complete same-boot GEM
   acceptance, creates its work loop, interrupt/event sources, output queue, and
   controller resources, then calls `attachInterface(..., false)`. It publishes
   a valid-but-down link before `registerService()` exposes the interface.
2. `getHardwareAddress()` returns the six-byte unicast address obtained from the
   board/firmware source selected by the hardware driver. The generic family
   publishes it as `kIOMACAddress` and uses it as the BSD interface unique ID.
3. The standard Ethernet values remain 1500-byte MTU and 1518-byte maximum frame
   including FCS. RX buffers delivered to the family carry at most 1514 bytes
   when the GEM strips the four-byte FCS; runt receives below 60 bytes are
   rejected. Short outbound frames require the separately proven GEM padding
   behavior before packet-path acceptance.
4. `getPacketFilters()` initially reports only the filters genuinely implemented
   by the driver. The Apple base implementation advertises multicast and
   promiscuous support, so the wrapper must not inherit that broader claim until
   the GEM receive filter paths are implemented and tested. Unicast and
   broadcast are the minimum.
5. `enable(interface)` enables the accepted GEM queues/IRQ path, configures and
   starts an `IOOutputQueue`, and only then permits link-up publication.
   `disable(interface)` stops and flushes the Apple output queue first, quiesces
   IRQ/DMA, retires every accepted TX mbuf, clears queued RX mbufs, and publishes
   link down.
6. `outputPacket(mbuf, ...)` never blocks. `kIOReturnOutputSuccess` transfers
   ownership to the GEM TX ring until completion; the ring must retain the
   exact descriptor-to-mbuf association and reject duplicate completion.
   `kIOReturnOutputStall` leaves
   ownership with Apple's output queue for retry; a dropped return consumes and
   frees the mbuf. TX completion frees exactly once and services the stalled
   output queue.
7. RX uses controller-allocated mbufs. `inputPacket(...,
   kInputOptionQueuePacket)` consumes each valid frame; the serialized receive
   drain calls `flushInputQueue()` after a batch. Invalid or shutdown-time
   packets are returned with `freePacket()`. A link-down transition clears any
   queued receives, and flushing is unavailable while link is down. No packet
   is delivered after the interface starts stopping.
8. Link changes use `setLinkStatus(kIONetworkLinkValid |
   kIONetworkLinkActive, medium, speed)` after the PHY reports a stable link, and
   valid-without-active for link down. `IOEthernetInterface` supplies the `en`
   prefix, so BSD assigns `en0`, `en1`, and so on.
9. `stop(provider)` synchronously detaches the interface, releases it and every
   event source/queue/medium resource, then calls `super::stop(provider)`.

[`rpi5_gem_network_adapter.h`](../../iokit/Kernel/rpi5_gem_network_adapter.h)
and its C implementation encode the admission and packet-ownership state
machine without importing Linux runtime code. It requires all eight acceptance
bits—RAM route, descriptor ring, TX DMA, RX DMA, IRQ, TX completion, RX
ownership, and Apple-family composition—plus a nonzero same-boot cookie. Until
all are present, no interface callback can run. The file is not referenced by
production source, and a test enforces that absence.

## Required sequence before activation

1. Complete the low-level one-packet path with real RAM route, descriptors, GEM
   queue programming, bus mastering, TX completion, RX ownership, and interrupt
   acknowledgement/reset evidence. This contract does not replace those gates.
2. Import/build the pinned Apple IONetworkingFamily sources into a distinct
   kernel successor and close their actual XNU/IOKit dependencies. Confirm the
   linked class symbols and no unresolved imports. This is a separate software
   composition gate.
3. Implement the thin C++ `IOEthernetController` wrapper over the accepted GEM
   transport and the default-off state machine. Compile it for Cortex-A76 and
   run ownership, failure-unwind, output-stall, RX batching, and teardown tests.
4. Only then add the service to the board catalogue. First hardware acceptance
   is `en0` registered but link down; then PHY link; then one bounded local
   Ethernet frame in each direction; then ARP/IPv4 and socket tests. DHCP, DNS,
   `sshd`, and remote login remain later milestones.

## Software-only evidence

`python3 -m unittest tools.rpi5.tests.test_gem_network_adapter -v` currently
passes four tests:

- native ASan/UBSan admission, registration rollback, output ownership,
  receive batching, link, disable, and synchronous teardown faults;
- freestanding Cortex-A76 compilation with no undefined symbols;
- compile-only ABI checks against Apple's installed Kernel.framework headers;
- exact source-pin metadata plus proof that no production source includes the
  adapter.

This evidence proves the boundary logic only. It does not prove the Apple family
can yet link into this kernel, that GEM moves a packet, that `en0` exists, or
that SSH is available.
