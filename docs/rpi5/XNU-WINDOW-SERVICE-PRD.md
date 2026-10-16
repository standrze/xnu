# Pi 5 XNU window service PRD

Status: design proposal, 2026-10-13. This document specifies an original
window service for the Raspberry Pi 5 XNU port. It authorizes no board image,
hardware trial, or desktop implementation. The broader product requirements and
release levels remain in [DESKTOP-OS-PRD.md](DESKTOP-OS-PRD.md); the current
hardware and userland evidence lives in [STATUS.md](STATUS.md).

## Product goal

Run independent graphical applications as controllable windows on the Pi's own
HDMI display. A local keyboard and pointer must select a window, deliver input
to it, move and resize it, and recover when an application exits or crashes. The
first useful application is a graphical terminal backed by the existing XNU
userspace, with the serial console retained for diagnostics and recovery.

This service is a counterpart to the *role* of macOS WindowServer, not an
implementation of its private protocol. Apple's public APIs establish
observable capabilities; they do not publish WindowServer's process internals,
compositor algorithm, driver interface, or private wire format. The API mapping
below separates those documented behaviors from our proposed design.

An early window-service demonstration is narrower than the desktop PRD's D1
release. D1 additionally requires the local graphical terminal, editor and
file viewer, independent processes, and the stated crash behavior. D2 adds the
full desktop, accessibility, security, and performance requirements in that
PRD. Existing macOS `.app` binaries, Apple's private frameworks and service
binaries, Metal compatibility, and pixel-for-pixel macOS behavior are outside
this product contract.

## Starting evidence and entry conditions

- Genuine XNU userspace and Apple-distributed zsh have run on the physical Pi
  over serial. Keep that working image and the independent recovery path.
- The latest [status](STATUS.md) reports software-validated HDMI mailbox helpers,
  but no actual mailbox transaction, qualified framebuffer mapping, HDMI text,
  or graphical scanout on XNU. The [same-boot FDT observation](HDMI-FDT-OBSERVATION-20261013.md)
  found a firmware framebuffer service without an address or geometry. Linux's
  active display buffer is not an XNU display ownership contract.
- The checked [boot-video and UART mirror work](BOOT-VIDEO-MIRROR-OFFLINE.md)
  remains an offline candidate. It does not establish physical scanout.
- The [desktop PRD's XNU path](DESKTOP-OS-PRD.md#8-path-b--extend-the-existing-xnu-project)
  requires qualified display ownership, enough managed memory, process IPC,
  shared buffers, and local HID input. RP1 USB/HID is separate from GEM Ethernet.

The window-service schedule begins only after a safe display path is selected.
Headless protocol/model work can proceed earlier, but a host test, emulator, or
Linux screenshot cannot satisfy a physical Pi display milestone.

## What the documented Apple APIs tell us

| Public API or guidance | Documented, observable capability | Proposed Pi/XNU contract; **inference**, not Apple's implementation |
| --- | --- | --- |
| [Quartz Window Services](https://developer.apple.com/documentation/coregraphics/quartz-window-services) and [AppKit `NSWindow`](https://developer.apple.com/documentation/appkit/nswindow) | Applications can enumerate windows in the current user session; windows have identities, bounds, ordering and visibility, and AppKit has key/main-window behavior. | Give each client-owned window a stable session-local ID. Define map/unmap, bounds, stacking, focus and lifecycle events in a versioned protocol. |
| [Quartz Display Services](https://developer.apple.com/documentation/coregraphics/quartz-display-services) | Public APIs report displays and modes and request configuration changes. | Start with one qualified fixed-mode output. Give the service an output identity and geometry; add transactional mode changes only after a Pi display driver supports them. |
| [IOSurface](https://developer.apple.com/documentation/iosurface) and [its property keys](https://developer.apple.com/documentation/iosurface/iosurfacepropertykey) | Image buffers can be shared across process boundaries with explicit shape and format metadata. | Use bounded shared-memory pixel buffers owned by clients and imported by the service. Define format, stride, lifetime, release and synchronization ourselves; do not require Apple's IOSurface implementation. |
| [Core Animation](https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/CoreAnimation_guide/CoreAnimationBasics/CoreAnimationBasics.html) and [`CATransaction`](https://developer.apple.com/documentation/quartzcore/catransaction) | Applications maintain layer hierarchies; transactions group layer-property changes for rendering. | Commit a coherent window/surface state at a presentation boundary. A layer tree or animation engine is optional later; the first clients may submit one pixel surface per window. |
| [Quartz Event Services](https://developer.apple.com/documentation/coregraphics/quartz-event-services) and [`NSEvent`](https://developer.apple.com/documentation/appkit/nsevent) | Event taps can observe or filter input before foreground delivery; AppKit handles events within an application. | A trusted seat path routes ordered input to the focused client. Global observation and synthetic input require separate authorization and are absent from the first protocol. |
| [Accessibility API](https://developer.apple.com/documentation/applicationservices/axuielement) | Assistive clients can inspect semantic UI elements and invoke actions. | Window metadata is insufficient for accessibility. Require first-party clients/toolkits to expose roles, names, focus and actions through a mediated semantic tree before D2. |
| [ScreenCaptureKit](https://developer.apple.com/documentation/screencapturekit/capturing-screen-content-in-macos) | Users can choose windows or displays for permission-gated capture. | Define a brokered capture capability. Do not let ordinary clients read scanout or other clients' buffers; capture implementation can follow the first local windows. |
| [ColorSync](https://developer.apple.com/documentation/colorsync) and [`CGDisplayCopyColorSpace`](https://developer.apple.com/documentation/coregraphics/cgdisplaycopycolorspace%28_%3A%29) | Display color spaces and profiles are exposed to applications. | Specify SDR/sRGB input and an explicit scanout conversion for the first output. Profile management and wide color follow measured display support. |
| [AppKit views and controls](https://developer.apple.com/documentation/appkit/views-and-controls) and [SwiftUI controls](https://developer.apple.com/documentation/swiftui/controls-and-indicators) | Application frameworks provide buttons, text fields, menus and other controls inside a window, including their event and accessibility behavior. | Select or build a Pi client-side toolkit separately from the window service. A movable window with drawn buttons is not evidence that those controls work. |
| [WidgetKit](https://developer.apple.com/documentation/widgetkit/) and [widget timelines](https://developer.apple.com/documentation/widgetkit/keeping-a-widget-up-to-date) | Mac users place app widgets on the desktop or in Notification Center. WidgetKit renders timeline-driven views outside the app; the extension is not continuously active onscreen. | Add an original desktop-widget host above the compositor, with a user-controlled gallery, bounded updates and isolated content providers. This is separate from app controls and window management. |

These links are behavioral references, not a promise of binary or source
compatibility with Apple APIs. Details such as damage rectangles, frame pacing,
buffer quotas and service boundaries below are our design choices.

## Controls and desktop widgets

"Widget" can mean two different layers. **In-window controls** are buttons,
fields, lists, menus and sliders drawn and operated by an application toolkit.
Apple documents those in [AppKit `NSControl`](https://developer.apple.com/documentation/appkit/nscontrol)
and SwiftUI. Window decorations are a related shell responsibility: Apple's
[`NSWindow` standard buttons](https://developer.apple.com/documentation/appkit/nswindow/standardwindowbutton%28_%3A%29)
provide an observable reference for close/minimize/zoom behavior. **Desktop
widgets** are small, user-placed views of app data; Apple's WidgetKit uses
separate extension code, timelines and [App Intent actions](https://developer.apple.com/documentation/widgetkit/adding-interactivity-to-widgets-and-live-activities).
None of these documented APIs reveals a private WindowServer widget protocol.

The Pi design keeps the responsibilities distinct:

| Layer | Proposed owner | First acceptance |
| --- | --- | --- |
| Window chrome | Trusted desktop shell over the window service | Close, minimize/restore and zoom controls invoke actual window operations; pointer and keyboard paths agree. |
| App controls | Selected client-side toolkit or a bounded first-party toolkit | A button performs an action; a text field edits Unicode text; focus order, disabled state and accessible role/name/action are verified inside a real client window. |
| Desktop widgets | Separate shell host and registered provider processes | User adds, moves and removes a local clock tile; placement survives restart, updates are bounded, stale data is visible, and one failed provider does not stall windows. |

The app-control toolkit is needed for useful D1 applications. Its choice follows
the target runtime, font/text and accessibility feasibility work; this PRD does
not promise that AppKit or SwiftUI themselves run on the Pi. Desktop widgets are
a later P1 product feature, after local windows and persistent user settings.
An initial provider can publish a static or scheduled snapshot from local data.
Interactive actions require a brokered, allowlisted command path; the host
must not execute arbitrary provider code in its own process. Private content is
hidden when the session is locked. Supporting Apple's existing WidgetKit
extensions or paired-iPhone widgets is not part of this original format.

## Proposed service boundary

```text
independent apps -- versioned requests + shared pixel buffers --> window service
local HID input --> trusted seat path --> window service --> focused app
window service --> checked display mapping --> Pi HDMI scanout
serial console --------------------------------> diagnostics and recovery
```

The qualified display backend must establish physical address validation,
reservations, cache attributes and scanout lifetime. A retained firmware buffer
may leave scanout under firmware control; a later native driver would take over
mode-setting and scanout. Before the window service draws, define the handoff
from any kernel text renderer so two writers never race on the same buffer.
Only the trusted service and an explicit boot/recovery console may obtain the
checked display mapping. Ordinary applications draw into their own bounded
buffers and never receive a physical scanout address. The service owns window
placement, clipping, composition, cursor, focus and presentation. A session
shell may own decorations, launcher and shortcuts through an explicitly trusted
interface; those policies do not belong in the kernel.

The IPC choice is a **decision gate**, not a hidden assumption. The existing
[desktop PRD](DESKTOP-OS-PRD.md#window-system-decision-after-x2) prefers a
minimal Wayland shared-memory server/client experiment after X2. It requires a
working local transport, descriptor transfer, mapping and event loop on this
Darwin target. If that experiment cannot close its dependencies, a small native
versioned protocol may serve D1, with its interoperability debt recorded. One
production window protocol should be selected before client/toolkit expansion.

### Minimum client contract (proposed)

These are logical operations, not Apple API names or a frozen wire format. A
Wayland spike may satisfy them with pinned standard interfaces; a native D1
protocol would need explicit encodings and versioning.

| Operation | Required data and response | Rule to verify |
| --- | --- | --- |
| Connect | Protocol version, client identity and returned capabilities/quotas | Reject unsupported versions; identity comes from the trusted transport, not a client-supplied PID string. |
| Create window | Role, initial bounds and returned opaque session-local window ID | Validate bounds and role; one client cannot mutate another client's window. |
| Import buffer | Shared-memory handle, byte length, width, height, stride, pixel format and returned buffer ID | Check arithmetic, backing length, mapping rights and quota before import; never accept a raw physical address. |
| Configure / acknowledge | Service-proposed size and state with a serial; client acknowledgment | A resize cannot make a stale old-size buffer appear at new-size bounds without defined clipping. |
| Attach / commit | Window ID, buffer ID, bounded damage rectangles and client sequence number | Publish a complete state change or reject it; no partial application after malformed input. |
| Complete / release | Service reports request acceptance or copy completion and later releases the buffer | A client cannot overwrite or reuse an in-flight buffer before release; hardware presentation is reported only when a real signal supports it. |
| Focus / input | Service sends focus epoch, monotonic timestamp, device/event kind and event payload | Only the focused eligible client receives ordinary keys; focus loss clears repeat and modifiers. |
| Destroy / disconnect | Client closes a window or drops its connection | Revoke window IDs, imported handles, queued events and focus ownership without affecting other clients. |

Messages need bounded lengths, checked counts and explicit errors. Buffer and
window IDs are scoped to a session and owner; stale IDs cannot become authority
for a different client after reuse. Quota values are set from target memory
measurements rather than invented in this PRD.

## Window-service requirements

The priorities here are for this service. They inherit the broader desktop
PRD's GFX-01–10 and security requirements; they do not relax D1 or D2.

| ID / phase | Requirement | Acceptance evidence |
| --- | --- | --- |
| WS-01 / prerequisite | One checked Pi display output with a known live mode, full allocation extent, format, stride, cache policy and lifetime. | Same-boot physical observation, bounded write/readback where valid, visible pattern and recovery; reject an ambiguous descriptor before mapping. |
| WS-02 / first pixels | A trusted service maps scanout after a defined handoff; a first-party client submits a bounded CPU-rendered surface. | On the physical Pi, a client-drawn pattern appears while UART markers, command status and recovery behavior remain intact, with no lost or duplicate serial bytes or mapping over kernel/firmware allocations. |
| WS-03 / protocol | Negotiate protocol version and client identity; reject unknown operations, truncated messages, overflowed dimensions and excess resources. | Two separate processes connect; malformed-client tests leave the service and the other client responsive. |
| WS-04 / buffers | Define pixel format, dimensions, stride, alpha, color space, ownership, release and maximum in-flight buffers. | XRGB/ARGB and clipping fixtures; stale/reused/unreleased buffers are rejected; client death releases its objects. Start SDR/sRGB only. |
| WS-05 / composition | Commit surface and window state coherently, clip and stack windows, track changed regions, and report acceptance, copy completion or dropped work. | Two overlapping clients move/resize without stale pixels; a slow or crashed client does not block the other. Report hardware presentation only after a real signal is proven; do not promise tear-free output without a proven timing source. |
| WS-06 / local input | Route key, pointer, button and scroll events to the selected client, with explicit focus enter/leave and modifier reset. | Physical keyboard and pointer change focus, type into only the focused client, and recover after unplug or client exit. Keep serial diagnostics independent. |
| WS-07 / window lifecycle | Support create, show/hide, move, resize, close and orderly client disconnect; assign stable session-local IDs. | Two independent applications retain correct identity and stacking across a close, crash and relaunch; no stranded focus or permanently hidden window. |
| WS-08 / access policy | Keep input injection, global event monitoring, window capture, scanout mapping and trusted shell commands outside ordinary client rights. | A hostile test client is denied each privileged action and cannot obtain another client's buffer through metadata or stale handles. |
| WS-09 / recovery | Bound memory and request queues; preserve diagnostic visibility and a recoverable session when a client or compositor fails. | Kill a client and then the service in separate trials; the serial path and known-good boot/recovery image remain usable. Do not infer durable file safety until storage is qualified. |
| WS-10 / D1 client | Provide a graphical terminal using a real PTY and the maintained shell; support keyboard-only window control and visible focus. | Type and interrupt a command, resize the terminal, close/reopen it, and keep the serial recovery channel available. This plus an editor and file viewer contributes to the existing D1 gate. |
| WS-11 / D2 integration | Expose semantic accessibility, mediated capture/clipboard, lock-aware focus, output settings and measured performance. | Pass the desktop PRD's relevant UX/GFX/SEC/NFR tests with actual Pi evidence; a window-service demo alone is not D2. |

At 1920×1080, one tightly packed 32-bit image is 8,294,400 bytes (about
7.9 MiB). Multiple scanout/client buffers, the root image, kernel and runtime
compete for managed RAM. Set per-client and global quotas after measuring the
Pi's validated managed-memory range; the board's 8-GB capacity is not itself
proof that XNU can allocate all of it.

## Milestones and stop conditions

| Milestone | Relation to existing plan | Exit condition |
| --- | --- | --- |
| W0: contract model | May run alongside X0/X1 | Versioned request/state model and negative fixtures pass on the host; label this design/host evidence only. |
| W1: display admission | X0/X1, D0 | HDMI output and the exact buffer ownership/format/cache contract are proven in a physical XNU boot. Stop if the firmware path cannot supply a safe buffer; scope a display driver instead. |
| W2: one-client transport spike | After W1 and the required X2 IPC/shared-buffer slice; XM as needed | One independent XNU client submits a CPU-rendered surface through a provisional local transport, visible on HDMI with serial diagnostics. This does not select the production window protocol. |
| W3: two local windows | X2/X3 and the protocol decision | Two processes, overlapping surfaces, physical keyboard/pointer focus, move/resize, malformed-client and crash recovery pass on the Pi. This is a window-service alpha, not D1 by itself. |
| W4: desktop D1 contribution | X3 plus terminal/runtime and toolkit work | Graphical terminal, editor and file viewer use working in-window controls and satisfy the existing D1 contract with documented fixed-mode/software limits. |
| W5: D2 integration | X4/X5/X6 as applicable | Accessibility, capture permissions, persistent settings, maintained apps, performance and recovery meet the broader D2 contract. GPU acceleration is a separately qualified backend, not a W3 prerequisite. |
| W6: desktop widgets / P1 | After W4 and persistent settings; may proceed alongside W5 | A first-party clock tile can be added, positioned, removed and restored after reboot; its provider cannot read other apps' buffers, its refresh is bounded, and provider failure leaves the session responsive. |

Each milestone records source revision, dependency versions, image hashes,
display and input hardware, exact procedure, raw serial output and visible
result. Track **specified**, **implemented**, **host-tested** and
**Pi-validated** separately. A VM, Linux driver, render fixture, or photograph
without matching boot evidence does not advance the Pi-validated state.

## Decisions to resolve with evidence

1. **Display handoff:** does the bounded firmware query yield a safe retained
   buffer and supported format, or is a native display driver required? Do not
   use an address from a different Linux boot epoch.
2. **Managed memory:** what RAM ranges, reservations, mapping attributes and
   cache behavior can the XNU build actually use for display and client buffers?
3. **Input:** which RP1/USB/HID path delivers physical keyboard and pointer
   events without depending on GEM Ethernet completion?
4. **Client protocol:** after X2, does the minimal Wayland shared-memory spike
   close its Darwin transport/runtime dependencies, or is a bounded native D1
   protocol the better measured choice?
5. **Frame timing:** what completion or refresh signal exists in the accepted
   display path? Until measured, expose honest presentation status rather than
   claiming vsync or 60 Hz behavior.
6. **Runtime and policy:** which process supervisor, IPC identity and memory
   accounting facilities are available on the target? Keep privileged capture
   and input operations closed until they have an enforcement mechanism.

This PRD provides requirements and decision gates. The next physical graphics
task remains the validated framebuffer handoff and visible text console in
[PLAN.md](PLAN.md), while Ethernet, storage and userland work continue under
their existing gates.
