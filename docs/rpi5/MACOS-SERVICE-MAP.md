# macOS capability and service map

Version 0.1 — researched 2026-10-12 UTC. Companion to the
[desktop OS PRD](DESKTOP-OS-PRD.md) and [source availability inventory](MACOS-SOURCE-INVENTORY.md).

## Purpose and research boundary

We should understand **what responsibilities Apple's operating system fulfills**
before choosing which components our system needs. This is architecture research
using public documentation, published source and documented product behavior;
it does not require reverse engineering proprietary binaries or private protocols.

The objective is functional coverage: capabilities, consumers, interfaces,
dependencies, permissions and failure behavior. It is not reproducing every
Apple executable or making our implementations binary-compatible with macOS.
The same capability can be provided by different components on Linux and XNU.

This first pass contains **54 grouped entries**, covering core OS and desktop
responsibilities. It is **not an exhaustive manifest of every service in every
macOS release**. Private helpers, optional features and installed applications
change the process inventory. Unknown implementation details stay unknown;
an executable's name is not evidence of its full behavior.

## 1. What counts as a service?

| Kind | Meaning | Example |
| --- | --- | --- |
| Kernel subsystem / driver | Privileged resource management and hardware support | XNU, IOKit drivers |
| System daemon | Background process with system-wide responsibility | launchd, configd, mDNSResponder |
| User agent / session service | Work scoped to a logged-in user/session | A registered LaunchAgent |
| Application helper | Separate process performing bounded work for an app | An app-bundled XPC service |
| Library / framework / public API | Code and interfaces applications call; may contact a service | AppKit, Foundation, Keychain Services |
| Desktop application / feature | User-facing behavior, possibly using many services | Finder, Dock, Spotlight |
| Online service | Remote infrastructure plus client integration | iCloud, APNs, App Store |

One framework can use multiple processes, and one process can provide multiple
capabilities. Public API documentation is not a specification of the complete
private backend. Public documentation also does not imply open-source code.
Apple's [XPC][xpc] and [Service Management][service-management] documents explain
the different lifecycle scopes; they should not be collapsed into one generic
list of always-running daemons.

## 2. Core runtime and lifecycle

The last column is **our proposed responsibility**, not a claim about Apple's
implementation or an automatic expansion of the PRD's release scope.

| ID | Apple component / kind | Documented role | Capability to specify for our OS |
| --- | --- | --- | --- |
| S01 | XNU: kernel | Mach/BSD/IOKit foundation for execution, memory and system interfaces. [Source][xnu] | Process and memory isolation, scheduling, IPC, timers, files, sockets and resource limits |
| S02 | IOKit / DriverKit: driver infrastructure | Device services; DriverKit exposes user-space driver development for supported families. [DriverKit][driverkit] | Device discovery, matching, lifetime, interrupts, DMA, power policy and safe user/device access; DriverKit is not automatically supplied by our port |
| S03 | dyld and system libraries: loader/runtime | Dynamic linking and the libraries applications rely on. [dyld source][dyld] | Versioned executable/library ABI, loading, symbol resolution, runtime errors and reproducible SDK closure |
| S04 | Foundation/Core Foundation and Dispatch: libraries | Common data/application facilities; Dispatch schedules concurrent work. [Foundation][foundation], [Dispatch][dispatch] | Strings, collections, serialization, locale/time facilities, event loops and concurrency primitives |
| S05 | launchd: supervisor daemon | Manages service lifetime and demand-started XPC services. [XPC][xpc] | System/user supervisors, readiness, activation, bounded restart backoff and shutdown ordering |
| S06 | Service Management: public framework | Registers and controls login items and bundled agents/daemons with permission state. [API][service-management] | Installable background tasks, visible enable/disable state and clean removal with the owning app |
| S07 | XPC / NSXPCConnection: IPC APIs | Structured communication across process boundaries, supporting isolation of work. [API][xpc] | Versioned messages, caller identity, authorization, limits, timeouts, cancellation and reconnection |
| S08 | UserDefaults / preferences: storage API | Persistent nonsensitive application and system settings. [API][preferences] | Scoped settings with defaults, change notifications, migration and crash-safe persistence; secrets belong elsewhere |

## 3. Graphical session, toolkit and desktop integration

| ID | Apple component / kind | Documented role | Capability to specify for our OS |
| --- | --- | --- | --- |
| S09 | WindowServer / Quartz window and display services: server/API boundary | Public interfaces expose display configuration and window information; private server internals are not fully specified. [Display services][display], [Core Graphics][graphics] | Display ownership, surface composition, window/focus/input policy and crash recovery; not an assumption that Apple's server source is available |
| S10 | Finder, Dock, desktop/workspace features: apps and UX | File navigation, app launching/switching and window/workspace organization. [Finder][finder], [Desktop & Dock][dock] | File manager, dock/launcher, task switching, workspaces and consistent session actions |
| S11 | AppKit / SwiftUI: UI frameworks | Application windows, views, controls and lifecycle; SwiftUI offers declarative UI. [AppKit][appkit], [SwiftUI][swiftui] | Supported application toolkit, events, layout, documents, controls and accessibility; not just window decorations |
| S12 | Core Graphics / ColorSync: drawing/color APIs | 2D graphics, PDF and image operations; color-profile handling and transforms. [Core Graphics][graphics], [ColorSync][colorsync] | Raster/vector drawing, image/PDF support and explicit color-space/display-profile behavior |
| S13 | Core Animation / QuartzCore: visual framework | Layer-oriented composition and animation. [API][animation] | Retained visual state, animation clocks, damage tracking and reduced-motion behavior |
| S14 | Metal: graphics/compute API | GPU resources, commands and shader execution. [API][metal] | A supported rendering/compute backend and synchronization contract; reproducing Metal is not required |
| S15 | IOSurface: shared-image framework | Shares image-buffer objects between processes. [API][iosurface] | Protected shared buffers, formats, ownership, lifetime and synchronization between apps, compositor and media |
| S16 | AppKit input / InputMethodKit: event and text-input APIs | Application event handling and input-method sessions/composition. [AppKit][appkit], [InputMethodKit][inputmethod] | Keymaps, modifiers, pointer/gesture events, shortcuts, IME composition and focus-aware routing |
| S17 | Core Text / toolkit text system: typography APIs | Fonts, glyphs, shaping and text layout. [API][coretext] | Unicode, bidirectional text, font fallback, caret/selection behavior and text editing |
| S18 | Accessibility APIs / VoiceOver: semantics and assistive tools | Applications expose semantic elements/actions to assistive technology. [API][accessibility] | Accessibility tree/events, screen reader, keyboard navigation, accessible authentication and settings |
| S19 | Launch Services / NSWorkspace: application-routing APIs | App activation and document/URL handling. [Launch Services][launchservices], [NSWorkspace][workspace] | App registry, content types, default handlers and open/activate requests; **not the same responsibility as launchd** |
| S20 | NSPasteboard / drag-and-drop: data-exchange API | Typed shared data transfer between applications. [API][pasteboard] | Clipboard ownership, format negotiation, bounded transfers, drag offers and privacy rules |
| S21 | User Notifications / Notification Center / APNs: API, UX and online service | Local notification presentation and remote notification delivery are distinct layers. [API][notifications] | Local alerts, actions, attribution, quiet modes and permissions; remote push is optional infrastructure |
| S22 | Spotlight / Core Spotlight: search and indexing | App content indexing/query interfaces alongside system search. [API][spotlight] | Permission-aware index, content extractors, incremental updates, reconciliation and search UI |
| S23 | Quick Look: preview/thumbnail capability | Previews documents without launching a full editing app. [API][quicklook] | Isolated format-specific preview workers, thumbnails, timeouts and failure containment |

## 4. Files, volumes and data lifecycle

| ID | Apple component / kind | Documented role | Capability to specify for our OS |
| --- | --- | --- | --- |
| S24 | File APIs / APFS: APIs and filesystem | File operations, coordinated access and filesystem-specific behavior. [File-system APIs][filesystem] | Durable files, atomic operations, metadata, permissions and consistent paths; APFS itself is not required |
| S25 | Disk Arbitration: volume-management API/service | Observes and mediates device appearance, mounts, unmounts and ejects. [API][diskarbitration] | Volume discovery, mount policy, busy-device handling and safe eject |
| S26 | FSEvents: filesystem-change API | Reports changes to directory trees for interested clients. [API][fsevents] | Change feeds for files/search/backup, overflow detection and reconciliation after missed events |
| S27 | File Provider: storage-extension framework | Integrates remote documents and local copies into file access. [API][fileprovider] | Provider isolation, offline cache, placeholders, hydration, progress and conflict handling; optional for local-only desktop |
| S28 | Time Machine: backup/restore capability | Maintains recoverable file history, including local snapshots on supported filesystems. [User guide][timemachine] | Versioned backup, retention, restore verification and separate failure-domain storage; snapshots alone are not independent backups |

## 5. Identity, trust, privacy and system integrity

These responsibilities must stay distinct. A login dialog does not implement
sandboxing, and package signatures do not implement privacy consent.

| ID | Apple component / kind | Documented role | Capability to specify for our OS |
| --- | --- | --- | --- |
| S29 | Open Directory: identity/directory framework | Queries directory information and supports authentication. [API][directory] | Local accounts/groups/IDs and optional external directory providers |
| S30 | Local Authentication: authentication API | Evaluates policies using supported credentials/biometrics without giving apps biometric data. [API][localauth] | Trusted credential prompts and scoped authentication results; Pi password flow first, no Touch ID/Secure Enclave assumption |
| S31 | Authorization Services: rights API | Decides whether restricted operations are authorized. [API][authorization] | Narrow privileged operations, policy checks, consent and auditing; ordinary desktop stays unprivileged |
| S32 | Keychain Services: protected-secret API | Stores and controls access to small secrets, keys and identities. [API][keychain] | Credential vault, per-app access, lock/unlock, recovery and secure deletion policy |
| S33 | Certificate, Key and Trust Services: cryptographic identity APIs | Manages certificates/keys and evaluates trust. [API][trust] | Trust store, chain/hostname/policy validation, key lifecycle and explicit trust changes |
| S34 | App Sandbox: confinement capability | Restricts application resource access. [API/documentation][sandbox] | App containers, enforced resource capabilities and brokered file access |
| S35 | Privacy consent controls: policy capability | Requires approval for protected data and sensitive access. [Platform Security][privacy] | Per-app permission grants/revocation and enforcement at actual resource boundaries; do not depend on private TCC database formats |
| S36 | Gatekeeper / execution assessment: software-trust policy | Checks downloaded software using identity/integrity and approval policy. [Platform Security][gatekeeper] | Package provenance, integrity and clear execution policy; Apple notarization is not provided by XNU |
| S37 | FileVault: at-rest protection | Protects stored user data through volume-encryption/key-management mechanisms. [Platform Security][filevault] | Encryption, unlock and recovery model; separate from runtime permissions and verified boot |
| S38 | Secure boot / signed system volume / recovery: integrity chain | Startup trust and cryptographic system-content verification depend on Apple's platform architecture. [Platform Security][platform-security], [SSV][ssv] | Independently designed boot trust, verifiable system images and recovery; the Pi does not inherit Apple's hardware guarantees |

Authentication asks **who**; authorization asks **may they do this**; secret
storage protects credentials; trust validates an identity/signature; sandboxing
bounds resource access; privacy records the user's sensitive-access choices.
Our service boundaries and tests must cover all six, even if we use fewer
processes than Apple.

## 6. Connectivity

| ID | Apple component / kind | Documented role | Capability to specify for our OS |
| --- | --- | --- | --- |
| S39 | SystemConfiguration / configd: API and daemon | Maintains/exposes configuration and changing network state. [API][systemconfiguration], [published scutil manual][configd] | One authoritative interface/address/DNS/proxy configuration service; link state is not proof of Internet access |
| S40 | Bonjour / mDNSResponder: discovery/DNS service | Name resolution and standards-based mDNS/DNS-SD discovery. [Bonjour][bonjour], [source][mdns] | Resolver, local discovery, interface scoping and privacy controls; a credible published-source reuse candidate |
| S41 | Network / URLSession: application networking APIs | Transport connections/listeners and higher-level request/download facilities. [Network][network], [URLSession][urlsession] | Asynchronous TCP/UDP/TLS/HTTP APIs, cancellation, path changes and certificate checks; these sit above device drivers |
| S42 | Network Extension: extension framework | Controlled network-provider functions such as VPN/filter/proxy services. [API][networkextension] | Optional VPN/filter/DNS-provider contracts, policy, lifecycle and fail-open/fail-closed decisions |
| S43 | CoreWLAN / Core Bluetooth: radio integration APIs | Wi-Fi configuration and Bluetooth-device communication. [CoreWLAN][wlan], [Core Bluetooth][bluetooth] | Drivers plus wireless pairing/configuration, credentials, permission handling and disconnect recovery; not supplied by Ethernet support |

## 7. Media, operations and ecosystem

| ID | Apple component / kind | Documented role | Capability to specify for our OS |
| --- | --- | --- | --- |
| S44 | Core Audio / HAL/audio server: audio APIs and service architecture | Audio devices, streams and hardware abstraction. [API][audio] | Mixing, routing, volume, timing, device changes and microphone permissions |
| S45 | AVFoundation / Core Media / Core Video / VideoToolbox: media frameworks | Capture/playback/editing, timed samples, pixel buffers and codecs. [AVFoundation][av], [Core Media][media], [Core Video][video], [VideoToolbox][videotoolbox] | Maintained codecs, A/V synchronization and permissioned capture; hardware acceleration must be independently qualified |
| S46 | ScreenCaptureKit: display-capture framework | Streams selected display/window/application content. [Documentation][capture] | Screenshot/share/record broker, explicit selection, authorization, revocation and protected-content policy |
| S47 | AppKit printing: API plus print-system integration | Print dialogs and application print operations. [API][printing] | Print-to-PDF, queues, discovery, transport, cancellation and job errors; a dialog alone is not a spooler |
| S48 | WebKit / Safari: engine/framework versus browser app | Web content execution/embedding versus end-user browser behavior. [WebKit project][webkit] | A maintained engine, isolated web content and browser UI; WebKit source is not all of Safari |
| S49 | Power/thermal coordination: platform capability/APIs | Reports power/thermal state and supports activity management. [ProcessInfo][processinfo] | Display idle, safe shutdown, thermal response and bounded background work; suspend only after hardware qualification |
| S50 | Software Update: lifecycle/security capability | Delivers authenticated system/security updates. [Platform Security][updates] | Signed metadata, download/install, interruption recovery, rollback policy and user-controlled restart |
| S51 | Unified Logging / OSLog / crash reports: diagnostics | Structured event capture and crash analysis. [Logging][logging], [crash reports][crashes] | Bounded/redacted logs, build IDs, symbols, crash capture, restart correlation and opt-in export |
| S52 | App Intents / Shortcuts: action and automation framework | Makes application actions/entities available to system experiences. [API][intents] | Typed action registry and permissioned workflows; not a requirement to recreate Siri |
| S53 | CloudKit / iCloud / Apple Account: API and online ecosystem | Account-backed remote data services and synchronization. [CloudKit][cloudkit], [Platform Security][platform-security] | Optional independent sync/accounts/conflict handling; published client interfaces do not provide Apple's servers |
| S54 | StoreKit / App Store: commerce API and distribution ecosystem | Purchases, transactions and store integration. [API][storekit] | App install/update/uninstall, provenance and permissions first; commerce and Apple-store integration are separate |

## 8. From catalog to implementation contracts

For every capability selected for a release, write a record with:

1. **Purpose and consumers:** what problem it solves; which apps/services use it.
2. **Public evidence:** source URL/tag, applicable OS versions and confidence;
   distinguish documented API, published implementation and inferred behavior.
3. **Our interface:** operations, schemas, events, errors, version negotiation,
   cancellation and limits. Do not assume Apple's private wire protocol.
4. **Lifecycle:** system/user/app scope, activation, readiness, dependencies,
   persistence, restart backoff and shutdown.
5. **Trust and data:** caller identity, permissions, privileged operations,
   owned data, secrets, retention and user controls.
6. **Failure semantics:** crash/timeout/offline/full-disk behavior, reconciliation
   and recovery without silently losing accepted work.
7. **Implementation/source choice:** reuse, port, independently implement, defer
   or exclude; record license and maintenance review separately.
8. **Acceptance evidence:** positive/negative tests, resource budgets, host versus
   board evidence, owner and release gate.

Example: our document-opening capability, inspired by S19, accepts a document
handle or URI and optional application ID. It finds permitted handlers, resolves
defaults, checks access, activates the chosen app and reports failure. Test
missing app, denied access, malformed URI and crashed target. It does **not**
require matching Launch Services' internal database or private IPC.

### How it maps to the two PRD paths

| Responsibility | Linux/Wayland route | XNU route |
| --- | --- | --- |
| Lifecycle and IPC | Integrate existing distro supervision, session and IPC services | Close a maintained runtime/supervisor/IPC implementation; audit published Apple candidates by version |
| Display/input/graphics | Existing Pi drivers, compositor and toolkit; integrate policies | Display/input drivers and buffer/IPC backend first; select/port window system and toolkit afterward |
| App/document integration | Integrate desktop registries, portals and common toolkit behavior | Define equivalent contracts; port suitable clients/services or implement bounded replacements |
| Credentials/permissions | Integrate distro security facilities; prove actual policy | Implement or port enforcement and services; development-mode XNU is not a finished security product |
| Search/previews/media | Select maintained components and isolate format handlers | Carry the same product contracts, but close runtime/codec/device dependencies separately |
| Cloud/commerce | Optional; not a prerequisite for local desktop | Same; Apple-hosted ecosystem is not a kernel feature |

These are implementation directions, not a claim of one-to-one equivalents.
The [PRD](DESKTOP-OS-PRD.md) remains authoritative for priority and acceptance.
Cataloguing Time Machine, for example, does not silently add a complete backup
suite to the current shell/storage milestone.

## 9. Coverage limits and next catalog pass

This is a desktop-oriented baseline. Separate records remain to be developed
for enterprise/device management, remote administration, detailed malware
remediation, virtualization, developer tooling, time synchronization, printing
backends, locale/input variants, Contacts/Calendar/Location, gaming, ML/AI and
cross-device continuity. Listing an area here is not claiming it was audited.

For an exact service inventory, first pin a macOS release/build and hardware
family. Then reconcile public service declarations, shipped manuals, framework
documentation and published-source release manifests. Record executable labels
only where supported by that evidence. A list of currently running processes
misses on-demand and disabled services and cannot establish completeness.

No binaries were disassembled; no private database was queried; no Pi hardware,
boot configuration or macOS service settings were changed for this document.

## Source references

References describe Apple's roles. The independent-OS requirements are our
design proposals, not quotations or claims of identical implementation.

[xnu]: https://github.com/apple-oss-distributions/xnu
[driverkit]: https://developer.apple.com/documentation/driverkit
[dyld]: https://github.com/apple-oss-distributions/dyld
[foundation]: https://developer.apple.com/documentation/foundation
[dispatch]: https://developer.apple.com/documentation/dispatch
[xpc]: https://developer.apple.com/documentation/xpc
[service-management]: https://developer.apple.com/documentation/servicemanagement
[preferences]: https://developer.apple.com/documentation/foundation/userdefaults
[display]: https://developer.apple.com/documentation/coregraphics/quartz-display-services
[graphics]: https://developer.apple.com/documentation/coregraphics
[finder]: https://support.apple.com/guide/mac-help/organize-your-files-in-the-finder-mchle9f0a1b2/mac
[dock]: https://support.apple.com/guide/mac-help/mchlp1119/mac
[appkit]: https://developer.apple.com/documentation/appkit
[swiftui]: https://developer.apple.com/documentation/swiftui
[colorsync]: https://developer.apple.com/documentation/colorsync
[animation]: https://developer.apple.com/documentation/quartzcore
[metal]: https://developer.apple.com/documentation/metal
[iosurface]: https://developer.apple.com/documentation/iosurface
[inputmethod]: https://developer.apple.com/documentation/inputmethodkit
[coretext]: https://developer.apple.com/documentation/coretext
[accessibility]: https://developer.apple.com/documentation/accessibility
[launchservices]: https://developer.apple.com/documentation/coreservices/launch_services
[workspace]: https://developer.apple.com/documentation/appkit/nsworkspace
[pasteboard]: https://developer.apple.com/documentation/appkit/nspasteboard
[notifications]: https://developer.apple.com/documentation/usernotifications
[spotlight]: https://developer.apple.com/documentation/corespotlight
[quicklook]: https://developer.apple.com/documentation/quicklook
[filesystem]: https://developer.apple.com/documentation/foundation/file-system
[diskarbitration]: https://developer.apple.com/documentation/diskarbitration
[fsevents]: https://developer.apple.com/documentation/coreservices/file_system_events
[fileprovider]: https://developer.apple.com/documentation/fileprovider
[timemachine]: https://support.apple.com/guide/mac-help/back-up-files-mh35860/mac
[directory]: https://developer.apple.com/documentation/opendirectory
[localauth]: https://developer.apple.com/documentation/localauthentication
[authorization]: https://developer.apple.com/documentation/security/authorization-services
[keychain]: https://developer.apple.com/documentation/security/keychain-services
[trust]: https://developer.apple.com/documentation/security/certificate-key-and-trust-services
[sandbox]: https://developer.apple.com/documentation/security/protecting-user-data-with-app-sandbox
[privacy]: https://support.apple.com/guide/security/controlling-app-access-to-files-in-macos-secddd1d86a6/web
[gatekeeper]: https://support.apple.com/guide/security/gatekeeper-and-runtime-protection-sec5599b66df/web
[filevault]: https://support.apple.com/guide/security/volume-encryption-with-filevault-sec4c6dc1b6e/web
[platform-security]: https://support.apple.com/guide/security/welcome/web
[ssv]: https://support.apple.com/guide/security/signed-system-volume-security-secd698747c9/web
[systemconfiguration]: https://developer.apple.com/documentation/systemconfiguration
[configd]: https://github.com/apple-oss-distributions/configd/blob/main/scutil.tproj/scutil.8
[bonjour]: https://developer.apple.com/bonjour/
[mdns]: https://github.com/apple-oss-distributions/mDNSResponder
[network]: https://developer.apple.com/documentation/network
[urlsession]: https://developer.apple.com/documentation/foundation/urlsession
[networkextension]: https://developer.apple.com/documentation/networkextension
[wlan]: https://developer.apple.com/documentation/corewlan
[bluetooth]: https://developer.apple.com/documentation/corebluetooth
[audio]: https://developer.apple.com/documentation/coreaudio
[av]: https://developer.apple.com/av-foundation/
[media]: https://developer.apple.com/documentation/coremedia
[video]: https://developer.apple.com/documentation/corevideo
[videotoolbox]: https://developer.apple.com/documentation/videotoolbox
[capture]: https://developer.apple.com/documentation/screencapturekit/capturing-screen-content-in-macos
[printing]: https://developer.apple.com/documentation/appkit/printing
[webkit]: https://webkit.org/project/
[processinfo]: https://developer.apple.com/documentation/foundation/processinfo
[updates]: https://support.apple.com/guide/security/secure-software-updates-secf683e0b36/web
[logging]: https://developer.apple.com/documentation/os/logging
[crashes]: https://developer.apple.com/documentation/xcode/diagnosing-issues-using-crash-reports-and-device-logs
[intents]: https://developer.apple.com/documentation/appintents
[cloudkit]: https://developer.apple.com/documentation/cloudkit
[storekit]: https://developer.apple.com/documentation/storekit
