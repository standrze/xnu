# Pi OS PRD — command line first; desktop later

Version: 0.5. Scope revised 2026-10-13, America/New_York: command line first,
then the shortest official Apple-source runtime path to zsh and a development
toolchain.
Research and repository checkpoint: 2026-10-12 UTC.

**Current deliverable: a working, user-accessible XNU command line on the Pi.**
The graphical desktop, Wayland comparison and Apple service catalog are future
reference material, not active implementation requirements. Desktop P0/D2
criteria below do not block the CLI milestone. No GUI, browser, GPU, audio,
cloud-service or toolkit work starts under this immediate scope.

**Latest priority: get real Apple-distributed zsh running as soon as possible.**
The bootstrap shell proof already exists; do not repeat its qualification or add
new soak/large regression gates. Preserve recovery, build the smallest required
Apple-source runtime slice, and use one focused build/boot smoke check before
handoff. Full libc/framework completeness, networking, persistence and broad
hardening may follow later. Never achieve speed by copying the host shell/libraries
or calling the bootstrap implementation Apple zsh.

**Next product priority: a usable development toolchain for this XNU system.**
The user should be able to build and run their own programs, with Swift explicitly
supported alongside C and C++. Start with reproducible Mac-hosted cross builds
for the Pi, then make compilation on the Pi a separately demonstrated capability.
Work on target headers, runtime and toolchain packaging can proceed alongside
display and network work; native compilation depends on persistent writable
storage and a qualified usable memory range. It does not delay the zsh handoff.

The future desktop sections extend the [XNU port plan](PLAN.md); they do not
claim that graphics work is implemented or that the existing gates have passed.
This document does not replace the current storage/network work, authorize a
new installation, or change the Pi's recovery system.

Companion research: the [macOS capability and service map](MACOS-SERVICE-MAP.md)
explains documented Apple responsibilities and the contracts our OS would need;
the [source inventory](MACOS-SOURCE-INVENTORY.md) separates published Apple code,
historical releases, independent implementations and unavailable components.
Understanding these capabilities is in scope; reverse engineering private
binaries/protocols or reproducing every Apple process is not the research method.

## 0. Immediate milestone — use the XNU command line

Deliver a serial prompt the user can open from the Mac, enter commands, run
programs/pipelines/scripts, recover from command errors and reconnect to without
an unnecessary Pi restart. This means XNU userspace, not the Pi's Linux recovery
shell. A graphical terminal emulator, Wayland, Ethernet and SSH are not needed.

### What we already have, and what remains

| Component | Reuse now | Remaining CLI work / boundary |
| --- | --- | --- |
| XNU kernel and board port | Existing downstream source and preserved working-shell image | Preserve proven boot/process behavior; change only dependencies needed by this milestone |
| Init, shell and utilities | Existing project-owned static `tools/rpi5/user/` implementation, with board-proven fork/exec/wait, pipes and scripts | Expose a usable session and address demonstrated interaction defects; do not replace it merely to acquire a familiar shell name |
| Serial transport | Existing Pi UART console and Mac Debug Probe path | Verify current image/session and single-reader ownership before connecting; historical boot evidence is not proof of a live prompt now |
| Session lifetime | Existing watchdog/recovery infrastructure | The proven shell image has a one-hour development window; a normal-use profile must not unexpectedly expire. Preserve fault recovery rather than blindly disabling the watchdog |
| Filesystem | Existing read-only multi-file RAM root | Sufficient for the first command session. Writable/persistent files remain separate Gate 4 work, not a reason to withhold the existing shell |
| Published Apple runtime code | Pinned build components now; official Libc/Libsystem/dyld sources for the required post-bootstrap phase below | Full dynamic Darwin userspace is not required by the current static shell; do not add it as a prerequisite or silently replace the planned Apple implementations |
| Maintained general shell | Immediate next implementation: pinned Apple-distributed zsh | Build only the runtime dependencies needed to launch it; advanced completion, locale breadth and full job-control qualification are deferred rather than release gates |
| Linux recovery command line | Existing Linux system, independently maintained | Recovery/staging aid only; Linux shell access does not count as XNU CLI acceptance. Wayland has no role in either serial CLI |

The first working-shell proof is already achieved: the
[shell trial](SHELL-TRIAL.md) records successful commands and two cold starts.
Do not repeat that qualification campaign. Remaining delivery work concerns
current accessibility, ordinary interactive behavior and the development-session
limit, not proving again that XNU can execute a shell.

### CLI acceptance contract

| ID | First-delivery requirement | Evidence / current gap |
| --- | --- | --- |
| CLI-01 | User can open the serial connection, obtain the XNU prompt and disconnect/reconnect | Verify the current target/session and release any test reader before handoff; no simultaneous readers |
| CLI-02 | Basic commands, working-directory changes, file reads, pipelines and scripts work | Existing board evidence covers `help`, `ls`, `cat`, `pwd`, `cd`, `uname`, pipes and `sh`; reuse it unless relevant code changes |
| CLI-03 | A failed command or malformed input returns to a usable prompt; a foreground operation can be interrupted safely | Error recovery is demonstrated; foreground interrupt behavior still requires a focused check before claiming it |
| CLI-04 | A normal-use session is not ended by a hidden test deadline | Existing one-hour window is a known gap; implement/review a separate normal-use watchdog policy and perform one targeted boundary check if changed, not recurring soaks |
| CLI-05 | User receives connection instructions, available commands, limitations and recovery instructions | Clearly state read-only RAM root, custom shell, absent SSH/network and unsupported shell features; do not call it zsh |

Sequence: inspect fresh state and existing trial ownership → hand off the proven
shell when safe → close only the CLI interaction/lifetime gaps → let the user
use it → build and validate the official Apple-source runtime incrementally.
Continue storage as the next separately accepted capability for files that
survive reboot; runtime source/build work can proceed alongside it. A maintained
general shell is now the immediate source-runtime priority; network access follows
as needed. Desktop implementation requires a later explicit scope decision.

### Fast lane to zsh (2026-10-12 user direction)

1. Pin the official Apple zsh source and identify its minimal build configuration.
2. Source-build only the authentic Apple runtime components needed to link/run
   that configuration. Prefer static linking if viable; do not require a full
   dyld/LibSystem installation merely as an architectural preference.
3. Package the actual zsh binary alongside the known-good bootstrap/recovery path.
4. One fresh boot: identify zsh's version, execute a builtin and external command,
   observe an error/exit status, then make the prompt accessible to the user.
   Report partial/unsupported features plainly; expand checks only for a concrete
   failure that blocks this handoff. VM success is not a physical-Pi success claim.

No additional soak, repeated cold-start campaign, exhaustive shell suite,
container isolation project or desktop work blocks this sequence. Record pins,
build commands and output hashes as part of building, not as a separate project.

### Required post-bootstrap phase — build the real Apple libraries

**User requirement:** once the command-line bootstrap is usable, use Apple's
published implementations and compile them from source. The custom static
bootstrap is a means of reaching that environment, not a permanent replacement
for the available Darwin libraries. This phase precedes graphical work and does
not delay the initial shell handoff.

Reaffirmed 2026-10-11: this source-origin requirement includes the real general
shell, specifically [Apple's zsh distribution](https://github.com/apple-oss-distributions/zsh),
not only libraries. Apply it to both physical Pi and managed Darwin VM userland.
Select and pin a buildable Apple-published revision with its dependency/license
closure; compile and run it on our XNU target before calling zsh delivered.
The current custom shell and managed guest agent remain explicit bootstrap
components. Do not silently substitute Homebrew binaries, the host's `/bin/zsh`,
or a different implementation for the selected Apple-source build.

Use [Apple's release catalog](https://opensource.apple.com/releases/) and the
official repositories it directs users to, including
[Libc](https://github.com/apple-oss-distributions/Libc),
[Libsystem](https://github.com/apple-oss-distributions/Libsystem) and
[dyld](https://github.com/apple-oss-distributions/dyld). These are source-build
targets, not a claim that three repository builds produce a complete runtime.
Resolve the required syscall, threading, allocation, platform, compiler-runtime
and other dependencies for the selected versions before fixing the build order.
The [source inventory](MACOS-SOURCE-INVENTORY.md) records additional Apple-origin
candidates such as libdispatch, Libnotify, objc4 and historical Core Foundation;
add them when an actual command-line application needs them, not as an all-at-once
framework collection.

| ID | Required outcome | Acceptance evidence |
| --- | --- | --- |
| SRC-01 | Authentic, versioned upstream source | Official URL, release/tag, immutable commit and archive/tree digest for each selected component; a coherent release baseline related to our XNU pin, with every cross-release exception explained |
| SRC-02 | Source-built target runtime | Clean rebuild from pinned inputs, with recorded host toolchain, target ABI, headers, dependency graph, build commands/logs and output hashes; no copied macOS system-library binaries presented as our build |
| SRC-03 | Transparent adaptation | Preserve upstream source and a reviewable Pi/XNU patch series; record missing/private dependencies and any bootstrap stubs. A stub or compatibility reimplementation does not count as the Apple implementation |
| SRC-04 | Actual XNU use, not compilation alone | A source-built target program exercises the selected library on the physical Pi; record linked/loaded library identities and relevant functional checks. For dynamic linking, prove the target dyld loads the intended libraries without undeclared host-runtime dependencies |
| SRC-05 | Safe incremental adoption | Retain the known-good static shell and recovery image; promote each runtime increment only after its target checks pass, with source notices and applicable license obligations recorded |

Build-host policy: initially cross-compile on the Mac for the Pi's XNU/arm64
environment. That is still compilation from the actual source. Native compilation
*on the Pi* is an explicit follow-on priority requiring writable build storage,
a working compiler/linker, build tools, qualified memory and sufficient runtime
coverage; booting a shell does not establish a self-hosting development system.
Host compiler/build tools may be used under their applicable terms; this is not
a requirement to rebuild the entire host toolchain. Label runtime subsets as
partial, and track downloaded, compiled, linked and Pi-tested states separately.

Start with dependency/provenance closure, then a small source-built C runtime
slice and target test program, then expand the runtime and dynamic loader in
dependency order. Do not force the most recent versions to fit or combine old
versions without an ABI/dependency review. If a required implementation is not
published or cannot be built under usable terms, report that exact gap and obtain
a scope decision before substituting an independent implementation. This promise
covers available Apple-published source, not proprietary macOS frameworks.

This planning edit does not take over an active board recorder, stage an image,
reboot the Pi or cancel other authorized work. Follow [STATUS.md](STATUS.md) for
fresh hardware evidence. The latest recorded checkpoint has the UART link
restored and an SD-read trial in progress; older UART-failure notes are history,
not an instruction to request another cable check.

### Development toolchain priority — build for and on the Pi

The target is an ordinary developer workflow: edit source, compile, link, run,
and see diagnostics on this XNU system. Swift is a required language target;
C and C++ establish the lower-level toolchain and library baseline. Additional
languages can use the same documented target ABI and sysroot once their runtime
requirements are identified. SwiftUI and other macOS application frameworks
are separate platform work.

| ID | Required outcome | Acceptance evidence |
| --- | --- | --- |
| DEV-01 | Reproducible cross-build SDK | Versioned target triple/ABI, headers, libraries, linker settings and build commands; compile and link small C, C++ and Swift programs on the Mac, then run those exact binaries on the physical Pi |
| DEV-02 | Native C/C++ compilation | On the Pi, use a packaged compiler, assembler/linker, headers and libraries to build and run a program from source on persistent writable storage; capture diagnostics and a second build after reboot |
| DEV-03 | Native Swift compilation | On the Pi, `swiftc` builds and runs a small standalone Swift program against the target Swift runtime and standard library; then build and run a minimal local Swift package with SwiftPM |
| DEV-04 | Usable developer environment | Document installation/update and command-line usage; verify source/object/output files, temporary directories, process launching, memory use and failure recovery on the Pi without depending on Mac-hosted execution |

Sequence: define the target ABI and build a project-owned sysroot from the
source-built runtime; prove C/C++ cross builds and execution; qualify a Swift
cross compiler, target runtime/standard library and one physical-Pi program;
then bring native Clang/linker and Swift toolchain components to the Pi as
storage, memory and runtime dependencies become available. Keep cross-build and
native-build evidence separate. A host `swiftc` producing a Mach-O file is not
evidence that the Pi can execute it, and a target binary running on the Pi is
not evidence that `swiftc` runs there.

## 1. Future desktop product decision in brief

Build a cohesive, local-first desktop for the **Raspberry Pi 5 with 8 GB RAM**:
consistent windows, an application launcher and dock, a status/menu bar,
search, files, settings, a real terminal, useful applications, and dependable
updates and recovery. Aim for the integration and attention to interaction
associated with a Mac, using our own identity and redistributable components.

There are two valid starting points, at different layers:

| Path | Starting point | What the project primarily builds | Recommendation |
| --- | --- | --- | --- |
| A: Linux + Wayland | A supported Pi Linux distribution with existing drivers and applications | Desktop experience, integration, image/release engineering | First usable graphical product |
| B: this XNU port | A working experimental kernel and bounded serial userspace | Remaining platform drivers, Darwin runtime, display/input stack, then desktop | Separate research track toward an XNU-native edition |

**Wayland is not an operating system or a kernel.** It specifies communication
between applications and a compositor; the compositor handles display and
window-management policy. It can be implemented on operating systems other
than Linux. **XNU is a kernel**, incorporating Mach, BSD facilities and IOKit;
it is not the complete macOS desktop. These are complementary layers, so an
eventual XNU + Wayland system is possible in principle, but requires substantial
porting underneath the protocol. [Wayland][src-wayland], [Apple XNU][src-xnu]

When graphical work is explicitly resumed, the recommended strategy is to
validate the desktop product on Linux, retain the XNU project,
and share specifications and deliberately portable components. Do not make
the first desktop depend on completing an XNU GPU driver. Do not promise that
the Linux desktop can later be moved unchanged to XNU.

### What “like Apple” means here

- Consistent focus, window controls, shortcuts, menus, typography and settings.
- Applications that cooperate through files, clipboard, open-with actions,
  notifications and permission requests.
- Predictable boot, login, lock, update, shutdown and recovery behavior.
- Keyboard access and assistive-technology support built into the product.
- A coherent developer/application contract, not just a wallpaper and theme.

Apple's window guidance is a useful interaction reference for active/inactive
windows and multi-application workflows; it is not an implementation of those
features for this project. [Apple window guidance][src-apple-windows]

### Explicit non-goals for version 1

Running arbitrary macOS `.app` bundles; App Store, iCloud, iMessage or Apple ID
integration; reproducing proprietary WindowServer, AppKit, SwiftUI or Metal;
APFS; a claim of macOS compatibility or Apple-equivalent platform security.
Do not assume availability or redistribution rights for Apple fonts, icons,
sounds, SDKs or proprietary binaries. Inventory licenses before importing
components; use original branding and appropriately licensed assets.

## 2. Release definitions and current evidence

These names prevent a graphics demo being mistaken for a finished OS:

| Level | Definition | Not sufficient |
| --- | --- | --- |
| D0: graphics proof | Actual Pi output from a controlled framebuffer/display path, with recorded ownership and recovery | Firmware logo, HDMI cable detection or a host screenshot |
| D1: local desktop alpha | Local keyboard/mouse; independent application windows; graphical terminal, file viewer and editor; bounded crash handling | Serial input alone, one fullscreen demo or simulated windows in one app |
| D2: usable desktop MVP | All P0 requirements below, including persistent files, maintained browser, networking, accessibility, permissions and recovery | D1 with an attractive theme |
| D3: enhanced desktop | Multi-monitor/HiDPI refinements, richer search, broader devices and applications | Advertising the board's theoretical capabilities as tested features |

“P0” means mandatory for **D2**, not mandatory before the first visible window.
P1 means the next release; P2 is exploratory. Unless marked as current evidence,
all requirements and numbers in this document are **proposals**, not measured
performance or existing support.

D2 requires UX-01–14, GFX-01–10, NFR-01–08 and SEC-01–05. The graphics and
nonfunctional requirements are P0 even where their table omits a priority
column. Earlier D0/D1 exceptions do not carry into D2. Revise an unrealistic
budget explicitly after baseline measurement; do not silently waive it at release.

### Existing XNU project: evidence at this checkpoint

| Area | What can be claimed | Consequence for this PRD |
| --- | --- | --- |
| Serial userspace | Repeatable custom static RAM-backed shell, external utilities, pipelines and scripts passed board trials | Useful bootstrap, not zsh or full Darwin userspace |
| Storage | Gate 4 adapter builds and has reached XNU; successful physical SD reads, HFS mounts and durable writes remain unproven | Persistent desktop data is still a dependency |
| Network | PCIe/RP1/GEM groundwork and host tests; no accepted XNU Ethernet runtime | No XNU networking claim |
| Display | Current loader explicitly supplies no framebuffer | Display handoff must first be established |
| Memory | Current handoff sets `mem_size=0x0a000000` (160 MiB), while reporting `mem_actual=0x200000000` (8 GiB) | The board's 8 GB is not currently a validated 8-GB XNU allocator pool |
| Runtime/toolkits | Full dyld/libSystem/init/general-shell closure remains Gate 6 | No assumed GUI framework, browser or macOS app support |

Evidence: [status](STATUS.md), [shell trials](SHELL-TRIAL.md),
[storage](GATE4-STORAGE.md), [network](GATE5-NETWORK.md),
[loader handoff source](../../loader/rpi5/probe_main.c), and
[memory ownership contract](OWNERSHIP-LEDGER.md). The older
[dependency inventory](DEPENDENCIES.md) is a starting inventory, not current
completion status.

Earlier UART observation failures also occurred under Linux and were not proof
of an XNU boot failure. The newer status checkpoint records the restored link
and an active SD-read trial. Consult [STATUS.md](STATUS.md), not this planning
snapshot, before target actions. This PRD edit requires no reboot or soak.

## 3. Hardware and support contract

Initial qualification configuration:

- Raspberry Pi 5, 8 GB, stock clock, adequate power supply and active cooling.
- One HDMI display at 1920×1080, 60 Hz, SDR; ordinary wired USB keyboard/mouse.
- A dedicated installation device with at least 64 GB usable capacity.
  Linux may use SD or NVMe; XNU initially follows the existing SD plan.
  XNU NVMe support is **not** implied by Linux NVMe recovery working.
- Wired Ethernet for the D2 network baseline. No network is required for D0
  or the first local graphical terminal. Wi-Fi/Bluetooth are later support.
- One explicitly qualified audio output, initially HDMI on Linux; the XNU
  audio path must be selected and implemented separately before D2.
- MacBook-hosted serial diagnostics and the known-good recovery installation
  remain available. The 4090 is not a required desktop/runtime dependency.

The Pi advertises a VideoCore VII GPU, GLES 3.1/Vulkan 1.3 and dual 4K60 output.
Those are hardware/platform capabilities, not this project's XNU driver support
or initial desktop acceptance target. [Official Pi 5 specifications][src-pi5]

Unsupported devices and modes must be reported explicitly. No silent enabling
of suspend, HDR, camera, accelerated video decoding or dual 4K effects before
separate driver and product tests.

## 4. Shared product requirements

The same D2 product contract applies to either kernel. Earlier XNU alphas may
ship with named omissions, but may not be called D2 until those gaps close.

| ID / priority | Requirement | Acceptance evidence |
| --- | --- | --- |
| UX-01 / P0 | Local account setup, login, lock/unlock, logout, reboot and shutdown; developer auto-login is opt-in | Complete lifecycle from physical console; ordinary apps cannot receive input while locked |
| UX-02 / P0 | Dock/launcher with pinned and running apps, search-to-launch, app switching, and clear active state | Launch two instances where supported; switch by keyboard and pointer; terminate one without confusing its identity |
| UX-03 / P0 | Move, resize, minimize, maximize, fullscreen, close, and two virtual workspaces | Five independent windows; correct focus after dialogs, workspace switch and app exit; no offscreen unrecoverable windows |
| UX-04 / P0 | Top status bar with clock, network, volume and session actions; first-party app commands | State follows the active app; unsupported third-party global menus remain in the app, not empty or misleading menus |
| UX-05 / P0 | File browser with paths, list/grid, open-with, copy/move/rename, trash/restore and visible errors | Round-trip a directory fixture, including Unicode names; cancel an operation; recover from full-disk and permission errors without silent loss |
| UX-06 / P0 | Real graphical terminal with PTY, maintained shell, resize, signals and job control | Run pipeline, foreground/background job, interrupt, resize and shell exit; terminal never substitutes for the serial recovery channel |
| UX-07 / P0 | Text editor, settings and maintained ARM64 browser | Save/reopen UTF-8 file; settings persist; browser passes pinned local HTML/JS/TLS/download fixtures with an active security-update source |
| UX-08 / P0 | Clipboard and drag/drop of text/files; default-app and MIME association handling | Cross-process, cross-toolkit transfer; explicit target permission checks; no unlimited clipboard history by default |
| UX-09 / P0 | Display, keyboard, pointer, audio, network, account, accessibility and update settings | Show actual supported values; apply/revert risky display changes; persist through restart |
| UX-10 / P0 | Notifications with actions and do-not-disturb | Correct app attribution; no sensitive content on lock screen by default; actions target the originating app |
| UX-11 / P0 | App launcher search and filename search over user-selected locations | Permission-aware results, cancellation and bounded resource usage; search never exposes another account's files |
| UX-12 / P0 | Consistent first-party design system | Review common controls in light/dark, focused/unfocused, disabled/error and large-text states; test GTK and Qt guest apps without forcing identical internals |
| UX-13 / P0 | Keyboard-only operation, screen-reader semantics, visible focus, high contrast, text scaling and reduced motion | Complete login, launch, file-open/edit/save and settings tasks with keyboard and a real screen reader; test custom controls, not only toolkit widgets |
| UX-14 / P0 | Predictable application lifecycle and session recovery | Killing one ordinary app does not kill the desktop; compositor failure returns to a recoverable session and does not corrupt saved files; unsaved third-party state is not guaranteed |
| UX-15 / P1 | Two displays, 4K with 2× scaling, qualified fractional scaling and trackpad gestures | Per-output geometry and pointer mapping, connect/disconnect, scale changes and text-quality checks |
| UX-16 / P1 | Full-text search, richer preview, Wi-Fi/Bluetooth and wider audio/device support | Explicit indexed-content policy and per-device acceptance reports |

Proposed interaction defaults: a Super/Command-compatible launcher shortcut,
Alt-Tab app/window switching, conventional text shortcuts and unchanged terminal
Ctrl-C semantics. Offer a Mac-keyboard preset instead of globally remapping
Control and breaking command-line applications. Distinguish closing a window
from quitting an application where the application supports that lifecycle.

Typography, spacing, color roles, icon sizes, corner radii and animation timing
belong in versioned design tokens. Use an 8-unit layout rhythm and a 200 ms
default transition as initial design candidates, not locked platform APIs.
Accessibility settings must override decoration and animation choices.

## 5. Graphical-layer engineering specifications

These are the lower-level contracts needed to satisfy the product, independent
of whether their implementation is Linux/Wayland or XNU-native.

| ID | Contract | Minimum verification |
| --- | --- | --- |
| GFX-01 | Discover outputs and supported modes; fixed boot mode is acceptable only for D0/D1 | Log actual mode, stride, format, physical buffer extent and ownership; reject inconsistent geometry |
| GFX-02 | Privileged display service owns scanout; apps submit bounded buffers rather than physical addresses | Reject oversized/overflowing buffers and unauthorized device mappings; isolate client memory |
| GFX-03 | Define buffer format, stride, alpha, color space, lifetime, release and synchronization | Begin with SDR/sRGB and 32-bit XRGB/ARGB formats; no reuse before release; malformed-client and stale-buffer tests |
| GFX-04 | Compose independent surfaces with damage tracking, clipping, stacking, resize and presentation feedback | Overlap/transparency tests; bounded queues; slow client cannot block unrelated windows |
| GFX-05 | Seat/input service owns devices and supplies ordered events with monotonic timestamps | Key repeat, modifiers, layouts, pointer buttons, scroll, hotplug and focus-loss cleanup; no stuck keys after unplug |
| GFX-06 | Text has Unicode shaping, font fallback, selection, caret and input-method composition | Non-ASCII filenames, combining marks, bidirectional sample and one composed-input workflow; no byte-based cursor navigation |
| GFX-07 | Session policy controls focus, activation, shortcuts, lock and privileged shell protocols | Background client cannot silently capture typing or activate over a locked session; verify trusted-shell identity |
| GFX-08 | Clipboard, file access, screenshots and screen sharing have explicit policy boundaries | Deny untrusted direct capture and input injection; portal cancellation/denial works; don't mistake a prompt UI for enforcement |
| GFX-09 | Renderer is replaceable: CPU first where needed, accelerated backend only when validated | Record renderer identity and fallback; GPU loss cannot silently corrupt memory; no acceleration claim from link success |
| GFX-10 | Graphics failure retains diagnosis and recovery | Serial logs survive graphics-client failure; recovery boot and failed-session restart are demonstrated |

At 1080p a single tightly packed 32-bit buffer is approximately 7.9 MiB; three
scanout-sized buffers alone consume about 23.7 MiB, before application surfaces,
textures, kernel or runtime memory. A 4K buffer is approximately 31.6 MiB.
This is arithmetic, not a memory benchmark; expanded XNU memory support is
therefore a first-class dependency, not an incidental optimization.

For a Wayland implementation, specify and pin a tested protocol matrix:
`wl_shm`, `wl_seat`, `wl_output`, `xdg-shell`, clipboard/data-device semantics,
activation, text-input, presentation feedback and the selected shell/lock
extensions. Accelerated sharing adds a separately tested buffer/fence path.
Not every compositor implements every extension. The core protocol alone does
not provide a universal global menu, file manager, permission broker or secure
application sandbox. [Wayland architecture][src-wayland-architecture]

## 6. Performance, reliability and security targets

These are proposed **D2 release budgets**. Record a baseline before treating them
as commitments. D0/D1 software rendering is exempt from D2 frame-rate targets
and must be labeled accordingly.

| ID | Proposed target | Measurement contract |
| --- | --- | --- |
| NFR-01 | 1080p60 desktop; at least 95% of frames within one refresh interval in the interaction trace | Five-window scripted move/resize/scroll trace, 60 seconds × 3; record presentation timestamps, renderer, power and thermal state |
| NFR-02 | p95 input-to-visible-response ≤100 ms | Separate end-to-end measurement with a visible response and camera/instrumentation; compositor timing alone is insufficient |
| NFR-03 | Idle system non-reclaimable footprint ≤1.5 GiB; reference workload ≤5 GiB | Record OS-specific accounting and shared-memory treatment; workload = terminal, files, editor, settings and three fixed browser fixtures; don't simply sum process RSS |
| NFR-04 | Cold power-on to usable login ≤30 s; authenticated session ready ≤5 s; warm terminal launch ≤1 s | Record storage/model/image and timestamps; three samples during release qualification, not a new recurring cold-boot campaign |
| NFR-05 | No panic, compositor death or unbounded memory growth during one 60-minute mixed workload | Named release-candidate scenario with fixed stop condition; rerun only after a relevant change or explicit release decision, not indefinitely |
| NFR-06 | Saving and successful update acknowledgment survive restart; failed update restores a bootable system | Fault injection at defined update phases on disposable installation media; user data and previous working image preserved |
| NFR-07 | Ordinary desktop session is unprivileged; administrative changes require explicit authorization | Privilege-boundary tests, permissions inspection, no default passwordless administrative desktop account |
| NFR-08 | No forced telemetry or cloud account; exportable local diagnostics | Network/log audit; secrets redacted; user explicitly chooses diagnostic upload |

Security release requirements (SEC-01–05 are P0; SEC-06 is deferred and not a
D2 security claim):

- **SEC-01:** Sign release artifacts and metadata; reject invalid signatures, mismatched
  hashes and unauthorized version rollback. Controlled recovery to a known-good
  signed release is distinct from permitting arbitrary downgrade attacks.
- **SEC-02:** Keep system and user data separately recoverable. Build and verify a rollback
  mechanism; package-manager updates alone are not proof of transactional OS
  rollback. No automatic repartitioning of the existing recovery NVMe system.
- **SEC-03:** Treat system packages as trusted administrator-installed software. Use
  restricted application packages and permission mediation for untrusted apps.
  On Linux, selected Flatpak apps plus working portal backends are a candidate;
  audit granted permissions individually. XNU needs its own proven equivalent,
  or must explicitly limit an alpha to trusted software. [Flatpak][src-flatpak],
  [desktop portals][src-portals]
- **SEC-04:** Gate screenshot, global-input, clipboard-monitoring and remote-control
  interfaces. Trusted panel protocols must not be exposed indiscriminately to
  sandboxed clients. Test the boundary with a hostile test client.
- **SEC-05:** Record a dependency manifest/SBOM, licenses, source modifications and an
  update owner. Triage critical upstream security notices within 72 hours;
  define release or mitigation handling instead of promising unreviewed updates.
- **SEC-06 / P1 research:** Full-disk encryption and a validated hardware-rooted boot trust chain are
  separate requirements before claiming protection against physical attackers.
  A signed download is not secure boot, and this Pi design does not inherit
  Apple's signed-system-volume chain. [Apple SSV reference][src-apple-ssv]

## 7. Path A — Linux + Wayland

### Recommended initial stack

Use a pinned, supported **64-bit Raspberry Pi OS** base for Pi hardware support.
Its current documentation describes a Debian-based distribution and maintained
packages; Raspberry Pi has documented its adoption of labwc. Begin with that
existing compositor rather than making a new compositor a prerequisite.
[Raspberry Pi OS][src-pios], [labwc adoption][src-pios-labwc]

| Layer | Initial implementation choice | Project responsibility |
| --- | --- | --- |
| Kernel/devices | Distribution Pi kernel, firmware, storage/USB/network/audio drivers | Pin coherent versions; qualify our exact peripherals and image |
| Display/GPU | VC4 DRM display plus V3D DRM rendering; Mesa V3D/V3DV | Prove real acceleration and presentation behavior on the Pi |
| Input | Kernel input + libinput + keyboard layout support | Focus, shortcuts, text input, device settings and accessibility integration |
| Compositor | labwc/wlroots from supported packages | Configure, test extensions, apply narrowly justified changes only |
| Desktop shell | Project dock/launcher/status UI assembled above the compositor | Original interaction/design system; explicit privileged-shell boundary |
| First-party UI | Qt 6/Qt Quick candidate for shell/settings; validate before freezing SDK | Accessible controls, restrained effects, protocol adapters; not a promise of Qt-on-XNU support |
| Existing apps | Distro ARM64 terminal/files/editor/browser initially | Cohesive launch/defaults/shortcuts; reuse instead of rewriting all apps |
| Session/services | Distribution login/session, D-Bus, network service, PipeWire/WirePlumber, portal backends | Integrate policy, settings, diagnostics and recovery |
| Distribution | Reproducible image + packages; vetted Flatpak optional | Signed delivery, recovery and update rollback engineering |

Mesa explicitly separates Pi 5 display support through VC4 from rendering
through V3D; importing a user-space graphics library alone is not enough on a
new kernel. [Mesa V3D][src-mesa]

labwc integrates separate desktop clients using extensions such as layer-shell
for panels and foreign-toplevel management for docks; session locking is also
a distinct client/protocol integration. Audit the exact pinned capabilities.
[labwc integration][src-labwc]

Qt supports Wayland clients, but a custom dock is not automatically supplied by
Qt's ordinary window API. Prototype its layer/toplevel interfaces first.
GTK applications remain supported guests. Toolkit accessibility infrastructure
does not excuse testing custom shell controls. [Qt Wayland][src-qt],
[GTK accessibility][src-gtk-a11y]

PipeWire handles media transport while its session manager supplies routing and
policy; qualify both rather than treating audio as a volume icon.
[PipeWire session management][src-pipewire]

### Alternative Linux starting points

- **Plasma/KWin:** choose if a broad integrated desktop with less custom plumbing
  matters more than a small bespoke shell. Customize documented extension points;
  qualify Pi memory/performance before choosing it. [Plasma development][src-plasma]
- **Weston/libweston:** use as an independent graphics diagnostic or foundation
  for a deliberate custom-compositor project. Its basic desktop is not this
  PRD's complete product. [Weston][src-weston]
- **New wlroots compositor:** defer unless a measured limitation in existing
  compositors prevents a P0 requirement; it adds security, protocol, focus,
  recovery and maintenance obligations.

### Linux execution sequence

| Milestone | Work package | Exit / decision |
| --- | --- | --- |
| L0: freeze baseline | Select image/package versions, dedicated media, hardware matrix and test fixtures | Rebuildable manifest and recovery strategy; do not repurpose recovery storage |
| L1: qualify platform | Display/GPU/input/audio/network tests on untouched upstream desktop | Renderer evidence, supported device list and initial NFR measurements |
| L2: design/session spike | Nested or separate session: dock, bar, launcher, focus and shell protocol adapter | Five-window workflow and keyboard-only prototype; choose labwc or Plasma based on evidence |
| L3: local alpha | Terminal, files, editor, settings, clipboard, session/crash handling | D1 achieved; no app-compatibility inflation |
| L4: application integration | Browser, file portals, notifications, defaults, network/audio UI, accessibility | UX-01 through UX-14 functional tests pass; P0 omissions visible |
| L5: distribution hardening | Update/recovery, privileges, sandbox/capture policy, packaging, reproducibility | Security/fault tests and reproducible release manifest |
| L6: release candidate | Defined NFR scenario, visual review and user acceptance walkthrough | D2 only if every P0 is accepted; publish limitations alongside image |

Start in a disposable session/image. Installing another desktop into the sole
working recovery system is not the first implementation step.

## 8. Path B — extend the existing XNU project

### What must exist below the desktop

1. **Memory and runtime:** validate larger managed-memory ranges, page mappings,
   reservations, cache behavior and DMA addressability; close the selected
   userspace ABI, threading, timers, shared memory, IPC, filesystem and PTY paths.
2. **Display:** establish actual Pi 5 scanout and ownership; reserve any retained
   framebuffer and expose only a checked display-service mapping. A firmware
   framebuffer is a feasibility candidate, not an established interface here.
3. **Local input:** implement the selected USB host/HID path. For RP1 USB,
   PCIe/RP1 enumeration, interrupts and DMA are dependencies; Ethernet itself
   is not. USB keyboard/mouse support is not delivered by the GEM network driver.
4. **Window system:** process-separated display service, input/focus policy,
   software renderer, surface IPC and text rendering, then desktop clients.
5. **Distribution:** persistent filesystem, maintained userland, account/service
   management, networking, browser/toolkit ports, audio, updates and recovery.

Apple publishes additional projects such as IOGraphics and IOHIDFamily, but
their existence is not evidence of a Pi 5 display controller, GPU or USB host
driver. Evaluate versions, dependencies and licenses before selecting them.
[IOGraphics][src-iographics], [IOHIDFamily][src-iohid]

### XNU execution sequence and branching dependencies

This supplements the numbered port gates; it does not renumber them. Display
research can run alongside Gate 4, and first pixels can come from RAM userspace.
Neither Ethernet nor a browser is required before the first graphical terminal.

| Milestone | Work package | Exit / stop condition |
| --- | --- | --- |
| X0: feasibility inventory | Observe firmware/display handoff; map retained buffers, services and missing APIs; choose fixed-mode display candidate | Written ownership/driver plan and reproducible probe; if no safe scanout path, stop the GUI schedule and scope a display driver |
| X1: first userspace pixels | Checked framebuffer mapping, CPU drawing, serial diagnostics; preserve bootstrap/recovery contracts | D0 on physical Pi, format/stride/bounds verified; no allocator overlap; no GPU claim |
| XM: desktop memory | Expand the current 160-MiB managed window from validated runtime RAM ranges in stages | Record usable/reserved bytes; exercise high addresses, SMP allocation and DMA boundaries; reference workload fits before D2 |
| X2: local input + IPC | RP1/USB host/HID as selected; event service; local sockets or chosen IPC, shared buffers, client teardown | Local keyboard/mouse, two isolated clients; unplug/crash/malformed-message tests |
| X3: software window system | Surface management, compositor, text, window controls; PTY terminal and minimal editor/file viewer | D1 with genuine processes and local input; fixed-mode/software limitations published |
| X4: Darwin/application closure | Continue Gates 4–6; durable storage, maintained libraries/init/general shell, toolkit and browser feasibility, network/audio | Versioned SDK/runtime contract and real target applications; no substitution of a serial interpreter for general shell support |
| X5: accelerated display | Display modes/interrupts; buffer allocator; GPU submissions/scheduler/fences; Mesa/backend port or independently scoped alternative | Real accelerated clients, isolation/reset/fault tests and measured presentation; dependency is separate from X3 |
| X6: usable edition | Shared desktop/services, accessibility, permissions, update/recovery and NFR qualification | D2 criteria met on XNU; if any major subsystem is absent, remain a clearly labeled alpha |

XM, X4 and X5 are partly parallel workstreams, not a rule that all must finish
before X1–X3. X4 requires a full maintained runtime for D2; a bounded static
implementation is permissible for earlier proofs.

### Window-system decision after X2

**Preferred interoperability experiment: port a minimal Wayland server/client
path using shared-memory software buffers.** First demonstrate local socket
semantics, descriptor transfer/cleanup, polling/event-loop adaptations, memory
mapping, clocks and client isolation on our Darwin runtime. Run two independent
clients; a host build is not acceptance. Local IPC does not require Ethernet.

Next inventory and port the chosen compositor's backend requirements. Linux
DRM/KMS, libinput/evdev, udev, session services, buffer/fence interfaces and
sandbox mechanisms need replacements or deliberate compatibility layers.
Do not label this “build wlroots on XNU” and hide the missing platform work.

If that spike cannot close its dependency list, use a small native display
server and explicit versioned surface/input protocol for **D1 only**, or defer
XNU graphics. Record the compatibility debt: a private protocol does not run
existing Wayland clients without an adapter. Do not start two production
window systems simultaneously.

### Acceleration is a distinct high-risk project

A CPU-rendered desktop does not require a finished 3D driver. An accelerated
desktop does require command submission, GPU virtual memory, buffer ownership,
cache/DMA rules, synchronization, interrupt handling, hang recovery and safe
multi-process access, plus a compatible user-space renderer. Mode-setting and
rendering are separate driver problems. Mesa's documented Linux V3D/VC4 split
is a useful dependency map, not a ready-made XNU port. [Mesa V3D][src-mesa]

No Metal implementation is proposed. Initially target the rendering API the
selected open-source toolkit actually needs; GLES can be sufficient, and
Vulkan is not a prerequisite to first windows. Do not place an unbounded GPU
port on a dated release schedule before X0/X2 and a driver feasibility review.

## 9. Shared code and compatibility boundaries

| Component | Reuse expectation | Boundary that must remain explicit |
| --- | --- | --- |
| Product/design tokens, icons, interaction tests | High | Same behavior, not identical backend code |
| First-party data models, parsers and document formats | High if kept portable | No Linux/macOS framework calls in the shared core |
| Toolkit/renderer source | Conditional | Depends on runtime, threading, fonts, graphics and accessibility ports |
| Wayland protocol definitions and client tests | Potentially shared | Actual server, event loop, shared-memory and descriptor semantics must work on each OS |
| Desktop service API | Specify common operations | Linux D-Bus/portals/session plumbing needs a Darwin adapter and enforcement |
| GPU/display/input drivers | Little direct reuse assumed | Different kernel APIs, DMA/VM models, device lifetime and license constraints |
| Linux application binaries/Flatpak images | No automatic XNU reuse | Linux ELF/syscall/runtime dependencies are not supplied by XNU |
| macOS ARM64 applications | Not supported by either proposed MVP | ARM64 and Mach-O alone do not supply Apple's frameworks, services and ABI environment |

Keep toolkit-specific UI out of the kernel repository when implementation
starts: this repo owns XNU/platform work; a separate desktop workspace should
own shell/apps and the Linux image recipe. Share a small versioned specification
and test-fixture package. Creating those workspaces is a later implementation
decision, not part of this PRD change.

Swift compilation is a development-toolchain priority under DEV-01–04 above.
SwiftUI/AppKit must not be assumed available merely because the kernel is XNU;
Qt's macOS backend likewise assumes a macOS GUI environment, not bare Darwin.

## 10. First work packages, risks and approval points

The proposed next engineering packages are deliberately bounded:

| Package | Deliverable | Dependencies / review |
| --- | --- | --- |
| WP-01: product prototype | Clickable or nested-session dock/bar/window workflow, tokens and keyboard map | No board driver work; review product behavior before visual polishing |
| WP-02: Linux baseline | Pinned image manifest and graphics/input/app evidence bundle | Dedicated media or isolated session; preserve existing recovery environment |
| WP-03: XNU feasibility report | Display handoff contract, managed-memory expansion plan, USB/runtime missing-dependency list | Source work now; board probes only after observation/recovery is restored |
| WP-04: backend contract | Versioned surface/input/session operations and shared acceptance fixtures | Use L2 and X2 evidence before freezing low-level ABI |
| WP-05: release architecture | Boot/update/rollback design, app trust model, component/license manifest | Required before presenting an image as a maintainable distribution |

Main risks and decisions:

- **XNU GPU/display feasibility:** largest platform uncertainty; software graphics
  provides a smaller intermediate outcome, not evidence acceleration is easy.
- **Darwin application ecosystem:** a current browser and toolkit are major ports,
  not items delivered by kernel boot. Fail their feasibility gates explicitly.
- **Linux product integration:** global menus, portals, capture restrictions and
  screen-reader behavior vary by toolkit/compositor; test the chosen combination.
- **Scope:** a custom compositor, custom toolkit and custom kernel simultaneously
  multiply maintenance. Reuse an existing Linux compositor and select one XNU
  window-system path at a time.
- **Security and distribution:** development bypasses and root diagnostics are
  not acceptable production defaults. A usable GUI is not security qualification.
- **Staffing:** Linux work needs desktop/UI and integration/release ownership;
  XNU additionally needs kernel/driver, graphics and userland-port expertise.
  Parallel agents can research/build/test isolated units, but cannot replace
  hardware evidence or eliminate undocumented-hardware dependencies.

No calendar commitment is made here. Linux has an existing stack to integrate;
XNU still has feasibility work. Estimate L3 after L1/L2 measurements, X3 after
X0/X2, and XNU D2 only after toolkit/browser and acceleration feasibility are
resolved. Track effort and unknowns per package rather than inventing a shared
date for fundamentally different starting points.

Proposed defaults for review: Linux first for D2; XNU retained as a distinct
edition; 1080p single-display first; own brand rather than macOS compatibility;
labwc baseline with a Qt prototype; software-first XNU graphics. Changing any
of these is a product decision, not an implicit consequence of this document.

## 11. Acceptance and evidence policy

Each accepted requirement must link to the source revision, dependency pins,
image hash, hardware/display configuration, exact procedure and raw results.
Record four statuses separately: **specified**, **implemented**, **host-tested**,
and **Pi-validated**. A source review, link result, screenshot, synthetic fixture
or Linux success must not be promoted into XNU hardware acceptance.

Use automated component/negative tests first. Batch related checks into a board
boot when safe. Preserve the proven shell image and recovery system, stage new
images separately, and verify exact media identity and hashes before writes.
Do not repeat completed cold-boot campaigns or start indefinite soaks. Ask for
a physical action only when an in-scope software path cannot perform it safely.

D2 handoff consists of: reproducible image recipe and manifests; installation
and recovery instructions; developer/runtime contract; application/device
support matrix; P0 test results and accessibility review; update/security
ownership; known limitations. A live demonstration should show login → launch
terminal → open/edit/save a file → use browser → change a setting → lock/unlock
→ recover from one crashed ordinary application, with no hidden serial commands.

## Primary-source references

These sources establish the upstream architecture and candidate components.
The product requirements, targets and implementation recommendations above are
our proposed design, not upstream guarantees. Pin exact revisions during L0/X0;
web documentation and package availability can change.

[src-wayland]: https://wayland.freedesktop.org/index.html
[src-wayland-architecture]: https://wayland.freedesktop.org/architecture.html
[src-xnu]: https://github.com/apple-oss-distributions/xnu
[src-pi5]: https://www.raspberrypi.com/products/raspberry-pi-5/
[src-pios]: https://www.raspberrypi.com/documentation/computers/os.html
[src-pios-labwc]: https://www.raspberrypi.com/news/a-new-release-of-raspberry-pi-os/
[src-mesa]: https://docs.mesa3d.org/drivers/v3d.html
[src-labwc]: https://labwc.github.io/integration.html
[src-weston]: https://wayland.pages.freedesktop.org/weston/index.html
[src-plasma]: https://develop.kde.org/docs/plasma/
[src-qt]: https://doc.qt.io/qt-6/wayland-and-qt.html
[src-gtk-a11y]: https://docs.gtk.org/gtk4/section-accessibility.html
[src-pipewire]: https://docs.pipewire.org/page_session_manager.html
[src-flatpak]: https://docs.flatpak.org/en/latest/basic-concepts.html
[src-portals]: https://flatpak.github.io/xdg-desktop-portal/docs/
[src-apple-windows]: https://developer.apple.com/design/human-interface-guidelines/windows
[src-apple-ssv]: https://support.apple.com/guide/security/signed-system-volume-security-secd698747c9/web
[src-iographics]: https://github.com/apple-oss-distributions/IOGraphics
[src-iohid]: https://github.com/apple-oss-distributions/IOHIDFamily
