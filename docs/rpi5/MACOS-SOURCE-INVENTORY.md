# macOS/Darwin source availability and reuse inventory

Version 0.2 — checked 2026-10-12 UTC. Companion to the
[service map](MACOS-SERVICE-MAP.md) and [desktop PRD](DESKTOP-OS-PRD.md).

## Short answer

**Yes: substantial Apple source exists, including older releases.** We already
use some of it. There are also independent open-source implementations of
Cocoa/OpenStep-style frameworks and desktops. We do not have to invent every
service from scratch or reverse engineer proprietary binaries to learn its role.

What we do **not** have is a complete public macOS desktop source tree that can
simply be rebuilt for the Pi. Apple's releases are collections of components;
an old Darwin release is not the complete source to the corresponding Mac OS X
graphical product. Start with [Apple's release catalog][releases] and its
[release component manifests][distribution], not assumptions based on names.

Source availability and buildability are separate facts. A public framework
API, SDK header or sample app is not the framework implementation. An available
implementation is not necessarily current, standalone, suitably licensed for
our distribution or portable to this XNU ABI.

## 1. Source already represented in this project

| Component | Exact project pin | Current evidence |
| --- | --- | --- |
| XNU | `xnu-12377.121.6`, commit `ac9718fb1af618d5ce8678d0dc6e8a58f252216f` | Source is this checkout; modified Pi kernel has achieved the separate serial-shell milestone |
| AvailabilityVersions | `AvailabilityVersions-157.2` | Pinned build dependency; not a desktop service |
| libdispatch | `libdispatch-1542.100.32` | Pinned dependency used by the build work; this does not establish a complete running Darwin Dispatch/userspace stack |
| IOStorageFamily | `IOStorageFamily-337.100.1`, commit `7edb88fbae296fb7c8ce2f64e115e116e566d51c` | Pristine source exists locally and experimental kernel integration is documented |
| HFS | `hfs-715.120.4`, commit `124b970fd5390f1c2cd6f985478616a04f6eeb1f` | Pristine source exists locally; experimental integration is not proof of physical Pi filesystem operation |

References: [main input lock](../../tools/rpi5/inputs.lock.json),
[storage lock](../../tools/rpi5/gate4-storage.lock.json),
[storage integration evidence](GATE4-STORAGE.md), [current status](STATUS.md).
The storage lock uses the Apple `macos-265` component manifest. Local source
presence was checked; no hardware test was performed for this inventory.

## 2. Official Apple-origin source candidates

These are source inventories, **not approved imports or build guarantees**.
Except for the explicit project pins and historical examples, repository links
are discovery entry points; select and record a tested revision before use.

| Component / primary source | What the published code provides | Reuse boundary for our OS |
| --- | --- | --- |
| [XNU][xnu] | Mach/BSD kernel and IOKit foundations | Already our kernel basis; not the whole Darwin userland or graphical desktop |
| [Libc][libc], [Libsystem][libsystem] | C/POSIX runtime components and system-library aggregation | Important for Gate 6; Libsystem alone does not contain every dependency it aggregates |
| [dyld][dyld] | Mach-O dynamic loading/linking implementation | Pair with compatible kernel/runtime behavior; modern sources can depend on additional Apple build/runtime infrastructure |
| [objc4][objc] | Objective-C runtime | Useful for Objective-C frameworks; neither Foundation nor AppKit by itself |
| [libdispatch][dispatch], [Libnotify][notify] | Work dispatch/event infrastructure and process notification mechanisms | Runtime candidates; **Libnotify is not Notification Center** |
| Historical [launchd-842.92.1][launchd] | Apple service-launch/supervision/bootstrap implementation and tooling | Real older source to study or evaluate; not evidence of today's macOS launchd/XPC implementation or compatibility |
| Historical [CF-1153.18][cf] | Core Foundation strings, collections, property lists, bundles, run loops and related infrastructure | C-level framework foundation; not all Cocoa, not current AppKit, and not a substitute for auditing runtime dependencies |
| [configd][configd] | System/network configuration infrastructure | Candidate after runtime/network closure; not a complete Wi-Fi stack or settings application |
| [bootp](https://github.com/apple-oss-distributions/bootp), [network_cmds](https://github.com/apple-oss-distributions/network_cmds) | DHCP/IP configuration code and network commands | Selected historical bootp packet/BPF/IPv4 routines, original route and original ifconfig now run in the separate VM workstream. Ifconfig changed/read back/restored en0 MTU and displayed leased IPv4; compiled modules are not blanket device/private-ioctl qualification. Full daemon and renewal remain unfinished. This is not a Pi hardware driver. |
| [mDNSResponder][mdns] | DNS/mDNS/DNS-SD infrastructure behind Bonjour | Strong candidate for standards-based local discovery after networking works; qualify the chosen platform build |
| [DiskArbitration][disks] | Disk discovery and mount/eject arbitration infrastructure | Needs working devices, filesystem/runtime interfaces and policy integration |
| [PowerManagement][power] | Published power-management policy/service code | Architectural reference or port candidate; Pi hardware capabilities differ from Mac power/sleep hardware |
| [Security][security] | Published security framework, trust/keychain and service components | Does not provide the entire Apple security architecture, backend services or Secure Enclave; dependency closure may be substantial |
| [IOGraphics][graphics], [IOHIDFamily][hid] | Display/framebuffer-family and HID/input infrastructure | IOGraphics includes IOBootFramebuffer; neither repository supplies a Pi GPU driver or the full WindowServer |
| [IONetworkingFamily](https://github.com/apple-oss-distributions/IONetworkingFamily) | Ethernet/network-controller, interface and output-queue infrastructure | Prefer compatible original Apple family code; this is not an RP1 GEM or VM VirtIO-net device driver |
| [IOStorageFamily][storage], [hfs][hfs] | Storage interfaces and HFS implementation | Already evaluated in Gate 4; successful compilation remains distinct from physical reads/mounts/writes |
| [Swift Foundation][swift-foundation], [Corelibs Foundation][corelibs] | Published Foundation implementations/components for Swift and cross-platform use | Modern Swift Foundation is not every OS-shipped Foundation facility; Corelibs targets non-Darwin platforms with best-effort compatibility, not a drop-in Objective-C macOS framework |
| [WebKit][webkit] | Browser-engine code including web rendering and JavaScript infrastructure | Open engine, **not all of Safari**; a maintained target port still needs graphics, fonts, networking, sandboxing and platform integration |

The launchd and CF tags are deliberately named historical examples, not our
selected versions. Older sources are valuable for understanding services and
bootstrapping experiments, but may introduce obsolete APIs, missing fixes or
architecture assumptions. Do not mix arbitrary release tags and call the result
a coherent Darwin distribution.

## 3. Independent open-source graphical alternatives

These projects are **not leaked or old Apple graphical source**. They are
independent implementations or operating-system projects with their own goals.

| Project | What it actually offers | What it does not solve automatically |
| --- | --- | --- |
| [GNUstep Base][gnustep-base] | Foundation/OpenStep-style non-graphical Objective-C framework | Complete current Apple Foundation behavior or our kernel/runtime port |
| [GNUstep GUI][gnustep-gui] | AppKit-like application/window/control APIs | Apple's AppKit implementation, complete macOS API compatibility or hardware display support |
| [GNUstep Back][gnustep-back] | Rendering/window-system backends for GNUstep GUI | A guaranteed Wayland or bare-XNU backend for the version we select; inspect backend support before committing |
| [Window Maker][windowmaker] | A NeXT-inspired **X11** window manager | A native Wayland compositor or a complete OS; X11 support is a real architectural choice |
| [ravynOS][ravynos] | An independently developed macOS-like system/project with published source | A qualified Raspberry Pi distribution or complete macOS compatibility; current README targets x86-64 and describes arm64/arm64e as future work |
| [Darling][darling] | A Darwin/macOS compatibility environment on Linux with published runtime/framework work | A native XNU desktop or a general guarantee that macOS applications work |

GNUstep's [own architecture overview][gnustep-overview] separates Base, GUI and
Back. This is the most direct framework family to evaluate if the desired
developer experience is specifically Objective-C/OpenStep/Cocoa-like. That is
a different product decision from making a visually Mac-like Qt/GTK desktop.
Neither choice requires binary compatibility with existing macOS applications.

Current-project caution: ravynOS's default branch is `darwin` and its README
describes Darwin and FreeBSD foundations; do not rely on older descriptions
calling it only FreeBSD-based. Darling's current README describes ongoing GUI
work, including an initial Metal translation effort; do not claim either
“no GUI work exists” or “macOS GUI compatibility is complete.” Neither project
was built or tested for this inventory.

For the Linux/Wayland route, the existing compositor/toolkit/driver projects in
the [PRD](DESKTOP-OS-PRD.md) remain valid open-source building blocks. Replacing
working Linux services with historical Darwin daemons is not a requirement for
an Apple-style product and should need a specific functional justification.

## 4. Important gaps and misleading similarities

The official sources reviewed do **not** provide a complete publicly released
modern WindowServer, AppKit, SwiftUI, Metal, Finder or Dock implementation that
we can assemble into macOS. The source catalog is not proof of a universal
negative, but these components must be treated as unavailable unless a specific
released implementation and suitable terms are identified.

Keep these distinctions explicit:

- **Core Foundation is not AppKit.** Common data types are not a GUI toolkit.
- **IOGraphics is not WindowServer.** Driver-family infrastructure is below the
  graphical session/compositor and does not implement its whole behavior.
- **Swift/Foundation source is not SwiftUI source.** Language, runtime, base
  library and UI framework are separate components.
- **WebKit is not Safari.** An engine and a finished browser are separate products.
- **HFS source is not APFS source.** Use the filesystem actually implemented and
  validated, rather than treating file API documentation as filesystem code.
- **A public Apple cloud API is not its backend source.** Local replacements or
  independently operated services are distinct projects.
- **Public security code is not the Apple hardware trust chain.** Source for a
  trust function does not deliver a Secure Enclave, notarization service or
  protected boot configuration on a Pi.

## 5. Licensing and provenance gate

Do not approve a repository wholesale from a GitHub badge. Before importing a
subset, record exact tag/commit and hashes, per-file notices, dependencies,
modifications, redistribution requirements and the build/test evidence.

Examples of why this matters:

- XNU's [APPLE_LICENSE][xnu-license] is APSL 2.0, while its tree also contains
  other notices. Check the actual selected files, not just the repository root.
- Swift Foundation publishes [Apache 2.0 with the Swift Runtime Library
  Exception][foundation-license]; this does not determine the license of every
  other Foundation-related project or dependency.
- **corecrypto is not a generally redistributable open-source drop-in under its
  default published terms.** Its [current README][corecrypto] describes an
  evaluation-only license. Do not import it into the distributable OS on the
  assumption that public source equals redistribution permission. Any differently
  licensed subset needs its own exact review.

This inventory is not a distribution approval or a legal opinion. Existing
project provider/license constraints remain in force; no new code was imported.

## 6. Recommended next evaluation sequence

The user has selected **working XNU command line first, then compilation of the
real Apple-published libraries from source**. See the [PRD](DESKTOP-OS-PRD.md)
CLI-01–05 and SRC-01–05 requirements. The service catalog and graphical
alternatives are future research, not prerequisites for either phase.

1. Hand off the existing XNU serial shell with clear limits; close only the
   access, interaction and session-lifetime gaps. Preserve the proven image.
2. Inventory a coherent official Apple runtime dependency set around Libc,
   Libsystem and dyld. Pin source origins, versions and hashes; resolve the
   required syscall/thread/allocation/platform dependencies and toolchain inputs.
   Libsystem is an aggregation point, not all these implementations in one tree.
3. Cross-build the smallest useful runtime slice from those sources, preserve
   downstream patches separately, and run a program linked against it on the Pi.
   Expand to a compatible dynamic loader/library set with actual target tests.
   Official-source compilation on the Mac is acceptable initially; native Pi
   compilation requires a separate compiler/build-tools/storage milestone.
4. Add other published Apple libraries/services only for selected CLI needs.
   Standards-based services such as mDNSResponder wait for their network/runtime
   dependencies; GUI-framework comparisons wait for explicit graphical scope.
   Do not silently substitute GNUstep, Darling or custom API stubs for the
   requested Apple implementations. Report unavailable dependencies first.
5. Before selecting any historical component, document maintenance ownership,
   security-update strategy, missing interfaces and the cost of keeping it alive.
6. Import only the selected, reviewed subsets. Preserve provenance, license
   notices, build recipes and hardware evidence; source presence or a successful
   host build alone does not prove an operational Darwin runtime.

The reuse decision should read: **capability → available source/version →
dependencies → license/provenance review → port or replacement → acceptance**.
This gives us an evidence-based way to build the OS without reconstructing
Apple's private implementation.

[releases]: https://opensource.apple.com/releases/
[distribution]: https://github.com/apple-oss-distributions/distribution-macOS
[xnu]: https://github.com/apple-oss-distributions/xnu
[libc]: https://github.com/apple-oss-distributions/Libc
[libsystem]: https://github.com/apple-oss-distributions/Libsystem
[dyld]: https://github.com/apple-oss-distributions/dyld
[objc]: https://github.com/apple-oss-distributions/objc4
[dispatch]: https://github.com/apple-oss-distributions/libdispatch
[notify]: https://github.com/apple-oss-distributions/Libnotify
[launchd]: https://github.com/apple-oss-distributions/launchd/tree/launchd-842.92.1
[cf]: https://github.com/apple-oss-distributions/CF/tree/CF-1153.18
[configd]: https://github.com/apple-oss-distributions/configd
[mdns]: https://github.com/apple-oss-distributions/mDNSResponder
[disks]: https://github.com/apple-oss-distributions/DiskArbitration
[power]: https://github.com/apple-oss-distributions/PowerManagement
[security]: https://github.com/apple-oss-distributions/Security
[graphics]: https://github.com/apple-oss-distributions/IOGraphics
[hid]: https://github.com/apple-oss-distributions/IOHIDFamily
[storage]: https://github.com/apple-oss-distributions/IOStorageFamily
[hfs]: https://github.com/apple-oss-distributions/hfs
[swift-foundation]: https://github.com/swiftlang/swift-foundation
[corelibs]: https://github.com/swiftlang/swift-corelibs-foundation
[webkit]: https://github.com/WebKit/WebKit
[gnustep-base]: https://github.com/gnustep/libs-base
[gnustep-gui]: https://github.com/gnustep/libs-gui
[gnustep-back]: https://github.com/gnustep/libs-back
[gnustep-overview]: https://developer.gnustep.org/Manuals/Base/Introduction.html
[windowmaker]: https://www.windowmaker.org/
[ravynos]: https://github.com/ravynsoft/ravynos
[darling]: https://github.com/darlinghq/darling
[xnu-license]: https://github.com/apple-oss-distributions/xnu/blob/main/APPLE_LICENSE
[foundation-license]: https://github.com/swiftlang/swift-foundation/blob/main/LICENSE.md
[corecrypto]: https://github.com/apple/corecrypto#licensing-and-contributions
