# Raspberry Pi 5 XNU port: revised implementation plan

## RAM-resident zsh plus local USB keyboard — active parallel track, 2026-10-16

The kernel, read-only RAM root, Apple zsh 5.9 and command payload already run
from RAM after firmware/loader handoff. The SD card is still the cold-boot
transport; removing that dependency is a separate future boot-media task.

Local USB keyboard work is specified in [USB-KEYBOARD.md](USB-KEYBOARD.md).
Fresh NVMe Linux inventory confirms both RP1 DWC3/xHCI 1.1 controllers and a
real Corsair K65 boot-keyboard interface on controller 0. USB-1 now passes on
the physical Pi with 16 stable read-only capability reads. USB-2 also passes:
controller 0 halted, accepted HCRST, cleared HCRST/CNR and ended halted after
exactly two USBCMD writes, with no port, status, doorbell, runtime, DMA, IRQ or
BME write. Both zero-transmit trials returned automatically to NVMe and the
normal SD triple is restored. USB-3 now also passes on the Pi with the v11
candidate and zero-transmit v6 capture: one Port Status Change event was
consumed, the No-Op completed, the controller halted, BME was restored, the
outer decode teardown reached `END OK=1`, and Linux returned automatically.
USB-4 now also passes on the physical Pi. The zero-transmit v4 trial reset
controller 0 port 2, consumed one successful port-status event, enabled slot 1,
addressed the device, completed all four EP0 descriptor transfers and selected
exactly the Corsair K65 `1b1c:1baf` boot interface `03/01/01`/endpoint `0x81`.
The controller halted, BME was restored, Linux returned automatically and the
normal SD triple was restored. USB-5's first-report subgate now also passes:
the v7 image completed three HID setup transfers, configured DCI 3 and received
one real 8-byte periodic idle report. The zero report correctly emitted no
terminal bytes; this is transport evidence, not a keypress. Linux returned and
the exact normal SD triple was restored without reboot. USB-6's v9 and v11
physical startup attempts both failed before the USB worker when an inherited
early IOKit dispatch raced platform-expert matching. The normal image was
restored and separately reverified through the HDMI/UART zsh prompt. USB-6 now
has a software-complete, fail-closed v13 candidate: the proven early
`IOStartIOKit.cpo` is restored unchanged, `IOKitBSDInit` performs the late
dispatch, and one retained owner thread performs the full
PCIe/xHCI bring-up, 255-report cyclic polling and `cons_cinput` delivery under
an observation-only watchdog lease. Its manifest SHA is
`8c5e9111a40399bdeb277663cda71206bd5ad5fa5ccb8c91b2917a988c0a8e3a`;
the independent checker passes actual Mach-O call-order, symbol, hash,
IRQ-off and no-staging checks. It has not been staged or run on the Pi. The
current boundary is one guarded physical boot and keyboard-only HDMI/zsh
command test. Do not claim working XNU USB input until repeated physical
press/release reports and that command test pass.

## Full retained GEM provider passed on the Pi — 2026-10-14

The complete CPU-owned `0x48000` Apple mapping provider is now a passed board
prerequisite.  The exact immutable package is
`build/rpi5/gem-full-provider-trial-20261014-v13`, manifest SHA
`c91ed69c129103004ad92f2aa74424c8730203ea42040d697123ced46e88d402`,
kernel SHA `ec98111e3c23bca4c85c3cfc7114da33407fbe38efe1cd7c1928fb35d8083081`
and image SHA `1080346d6acad62784ce27d54b0130b0a56f94133bde49fcf8d42e9fde023a4f`.
The receive-only serial stream is 54,530 bytes, SHA
`ba231c633737c56853939895fd60a13f9b270fddb72a8565b8a8532a9f04c169`.
Its strict parser validates all 18 ordered Normal-NC page proofs and all 128
ordered CPU-owned 2-KiB packet-span proofs.  The retained owner completes at
observation step 9 with no error.  Both live snapshots have NCR and all four
queue registers at zero and IMR exactly `0x3fffffff`; on Cadence GEM, a set IMR
bit means the interrupt is disabled.  Endpoint COMMAND ends at `0000`, the
trial emits `END OK=1`, transmits zero serial bytes and returns automatically to
NVMe Linux boot `b78ce2fc-b053-4277-a2e9-34cada155cda`.

The exact normal SD triple was restored afterward: probe
`f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536`,
config `aaccab184135aca272db4123fcba34e20874ae0959a90aed1ef6fd4d5e18ed28`
and firmware `413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46`.
This closes item 1 below; do not repeat the provider board gate.

The next gate is the separate queue-0 save/write/readback/reverse-restore trial
described in item 2.  Its corrected default-off core is software-qualified at
`build/rpi5/gem-queue-admission-candidate-20261014-v5`, manifest SHA
`13384217e12e5bacd27300c34a4158fa52c380a3f824fd72b7d9f2fb815a7c6b`.
The core now requires the exact RP1 all-masked IMR value `0x3fffffff`, not zero.
Before any board run, compose it with the passing v13 provider and prove that
every failure after the first queue write parks for autonomous reset.  Keep
BME clear, NCR zero, all interrupts masked, every descriptor CPU-owned, and
restore the four queue registers before accepting the gate.

The v5 candidate pins the passing v13 manifest, capture state and 146-record
parser report, so `physical_prerequisites_satisfied=true`; it is still not
kernel-composed, staged or hardware-executed.

## Current execution sequence — visible shell, real DMA mappings, packets, 2026-10-14

Visible XNU/zsh is now verified by the user's monitor photograph and the same
fresh nonce as the full passing serial capture. No unchanged display replay or
soak remains. Input is still UART. The PHY reset/C22 trial also passes on the
actual Pi: ID600d84a2 and exact GPIO/maps/BAR/root restoration, followed by
independent SSD return and original firmware/image restoration, catalog414.
After the clean console/reboot trial, provider retry and mapping diagnostic, the
mapping prerequisite reached catalog 524 on Linux boot
`2d237d96-a323-4df7-a8b4-ad9b4eb5f477`. XNU zsh 5.9,
all four command exchanges, one real reboot invocation, the ordered pthread/
restart path, `PRE_SMC`, independent NVMe return and exact pair restoration
pass. Normal firmware remained protected. This closes the serial-controlled
terminal/reboot milestone; local keyboard, Ethernet and SSH remain unfinished.
The accepted mapping diagnostic identifies one exact failing predicate. The
static physmap alias for page0 resolves the right PA, but read/write PAR has
attribute `0xff` instead of the retained buffer VA's required Normal-NC `0x44`:
`DMA_MAP REASON=36 PAGE=0 ATTR=6 VA=2 PA=185532416`
`PAR_R=18374686479857158912 PAR_W=18374686479857158912`. Route, live RP1
callbacks, CPU ring stores/readbacks, BME, queues, IRQs and packets remain zero.
The first page-granular-physmap successor then failed closed before alias
translation: runtime table accounting observed five 16-KiB bootstrap pages but
the provisional estimate allowed four (`REASON=26`). It also exposed an exact
image-marker/parser mismatch and showed that the composed image had not linked
the enabled `loose_ends.o` alongside enabled `pmap.o` and `arm_vm_init.o`.
Original config, normal firmware and known-good zsh image are restored.
The corrected v10 retry emits four exact `0x44` read/write alias rows,
reason41, bounded table accounting and Discarded-before-route with zero
activation. Its historical recorder retains a failed classification because
of an inapplicable inherited RP1-ID/link success rule, but the new immutable
mapping-only post-capture checker passes the exact raw stream, complete source
and receipt closure, automatic return and catalog512→518→524 restoration.
The mapping gate is therefore formally accepted without another reboot and
without claiming RP1 identity/link or Ethernet success. Restoration
`gem-physmap-mapping-v5-restored` is sealed by
`91a00c05d5bee963e87e316a4748eeee4e38be706a8f6c6432238f3047180c00`
with plan
`0192c6a07d6947c41443aa24b18f1432a867c9f8c9676773a29e7b6a097e5058`.
Ethernet/IRQ/DMA packet delivery is not yet achieved. The distinct
physmap-enabled CPU-owned-ring successor has now also completed one bounded
board run: two 16-KiB pages, 640/640 CPU descriptor stores/readbacks, zero
packet spans, zero UART TX, clean watchdog return and exact catalog 524→530→536
restoration. The immutable board and composite reports are respectively SHA
`050d50a2efd723ddd3bf37ad3b0f7753b4242396ee41d6271b5a5729e5d5b96f`
and `7b6443bcd84190b6d1fee5408b4d808ba435a2c28455a95e62be1fb6b63f6be0`.
This closes the CPU-only ring gate without enabling BME, queues, DMA, IRQs,
packets, Ethernet or SSH. The exact normal SD baseline is now restored at
catalog 536, and the Pi is on fresh NVMe Linux boot
`d2fd08b0-1ff7-46ab-b237-e2e64f20446a` with both SD partitions unmounted.

Next implementation order:

1. Preserve the mapping and CPU-ring raw streams, historical failed parser
   classifications, supplemental typed reports, return receipts and the exact
   restored triple. Do not repeat either board gate. The next software and
   physical prerequisite is the full `0x48000` provider with all 128 packet spans
   retained in preferred RAM and every span proven through the same
   page-granular Normal-NC CPU mapping path. Keep BME, queue registers, GEM
   receive/transmit, DMA, IRQs and packet submission disabled during that proof.
   The default-off provider is now target-linked at
   `build/rpi5/gem-full-provider-candidate-20261014-v1`, manifest SHA
   `a78512231a31a43d2810664610bc47a35c9b54bee086b66b0a224dcf66a3f4ef`;
   its seven tests and reproduced offline report pass. Its missing evidence is
   specifically one bounded same-boot board run proving all 18 pages and 128
   spans, not another software layout exercise.
   Do not stage the rejected first transport draft. The current fail-closed
   assessment, SHA
   `de3c41b295ffe49a33397f565751c2b16962460585147823167daa7c29aec8a1`,
   requires 18 ordered page records, 128 ordered span records, fresh
   BME/NCR/IMR/queue observations, zero UART TX, automatic NVMe return and exact
   catalog/restoration closure before a replacement can be publishable.
2. After full-span mapping passes, run a separate queue-0 publication diagnostic:
   save, write and read back only RBQP/RBQPH/TBQP/TBQPH, verify the exact 64-bit
   ring addresses and all 640 descriptor words, then restore the four registers
   in reverse. Require endpoint BME=0 throughout, GEM RE/TE=0 and IRQs masked.
   Follow with separate PHY autoneg/link, BME-only set/read/clear, polling
   TX/RX DMA, one interrupt-delivery, IONetworkingFamily `en0`, IP and SSH
   gates. A polling packet result is intermediate evidence, not a substitute
   for the required interrupt/DMA/driver outcome.
   The default-off software core for this later step is qualified at
   `build/rpi5/gem-queue-admission-candidate-20261014-v3`, manifest SHA
   `795f6850a1136a1b73036710ffc023a42e2f5370d47f58ae4e81a2202e66e9b0`.
   It remains blocked from kernel composition and hardware execution until the
   full-span mapping prerequisite has its own accepted board evidence. See
   [the Gate 5 wired review](GATE5-WIRED-NEXT-MILESTONE-20261014.md).
3. Preserve the now-passing user-controlled restart path. The actual catalog466
   trial boots root33/HDMI, publishes clean PID1/watchdog records, executes all
   four zsh checks, invokes genuine Apple reboot syscall55 once, reaches the
   fixed PSCI `PRE_SMC` path, and returns to fresh NVMe Linux. Exact pair
   restoration/replay reaches catalog476. Keep every earlier failed capture
   and the original kernel fault checks; do not tune delays, relax admission or
   repeat this gate. Retain the watchdog fallback: nominal timing and ordered
   markers do not prove unconditional PSCI causality or physical poweroff.
4. Continue real Apple SSH/runtime providers without feature-disabled facades.
   Current daemon/setsid exposes bootstrap_parent; the qualified Apple DNS
   wire parser closes res_9_dn_expand, and the genuine Apple-distributed
   `bsd-asprintf.c` provider closes `_asprintf`/`_vasprintf`. Genuine Apple
   `bsd-getline.c` and the selected public-ABI `localtime_r` fallback close two
   more leaf imports, and unchanged Apple Libc-167 `perror.c` plus its genuine
   `writev` syscall wrapper closes `_perror`, all without adding dependencies.
   Unchanged Apple Libc-167 `sscanf.c` plus the complete `vfscanf.c` closes
   `_sscanf` while retaining the existing nine Apple runtime/locale owners.
   The exact full-client remainder is33 imports.  The tested leaf frontier
   admits no further safe isolated provider: historical `popen` adds `_vfork`
   and weakens semantics, while current Apple `popen` belongs to a modern FILE/
   pthread/spawn/private-libc tranche. The default-off pthread/FILEX gate
   credits existing target contention and errno/TLS evidence. A distinct
   target-linked recursive-mutex candidate and bounded serial package now pass
   software checks and are ready for a future bound Pi execution. A coherent
   current-Apple FILEX candidate also links with zero undefined symbols and
   excludes legacy FILE owners. Neither is target runtime evidence. Admission
   remains closed pending both exact target runs plus real fork/atfork and a
   genuine cancelable-variant run; host sanitizer success is not target
   evidence. Current
   private-XPC/bootstrap service ownership is not replaced by a historical
   liblaunch shim. Network services and persistent storage remain separate
   unfinished requirements, not consequences of the visible shell.
   In parallel, the v3 default-off `IONetworkingFamily-186` slice now compiles
   all twelve unchanged Apple implementation units and links a distinct arm64
   kernel with zero undefined symbols. Report SHA is
   `f370952ca51f5e4e77ffd2a2d4fd0acbd55901e8227694be32d5e3b63575169f`.
   The remaining boundary is production composition, catalogue ownership and a
   thin controller attachment over accepted GEM transport—not more family
   source stubbing. Do not register `en0` until the low-level packet/IRQ gates
   pass and the wrapper's ownership/teardown path is separately qualified.

## Earlier execution snapshots — 2026-10-13

The full-height XNU candidate now physically boots and all four real zsh5.9
command exchanges pass. Its complete240s SD→NVMe capture remains failed:
~49s loader startup plus180s service/15s watchdog extends beyond the recorder.
Linux boots ~10s after capture expiry. Independent recovery/original pair
restoration pass, catalog384. Preserve that failed full capture and separate
partial command proof. Implement a distinct300s host-capture successor
(60s loader+180s service+15s countdown+45s return allowance), unchanged target
and TX deadlines. Obtain full-height visual confirmation; do not repeat a
compact diagnostic or soak. Ethernet reset transport is software-qualified,
not yet executed on the board.

Latest physical step: the compact768-store HDMI diagnostic passes within the
original500ms limit, including the single user-requested replay. User photos
and explicit confirmation establish that its tiny pattern reached the monitor;
the downsampled lettering is not the intended console. Original config/zsh
are restored, catalog374, independent SSD Linux boot388349d4-3664-4ac1-9488-7d59cc4f6566.
Next stage the distinct frozen `display-xnu-console-5cd94fg_` only after its
own guarded transport qualification and exact current-baseline admission.
It uses Apple's full-height renderer, UART input and the unchanged bounded180s
terminal/15s watchdog return. No further compact replay or soak is planned.
Ethernet reset/MDIO and Apple userland prerequisites continue software-only in
parallel; their software tests do not establish physical PHY or SSH readiness.

User-facing priority: show the existing working zsh on HDMI. Run a framebuffer
handoff/ownership and Apple text-console workstream alongside Ethernet and SSH;
do not make display output wait for a network driver. The loader currently
supplies no framebuffer. The actual standalone GET-only query now succeeds:
one display, raw1920×1080/depth16/pitch3840 and zero address words. Full capture,
independent SSD Linux return, original working-loader restoration and replay
pass, catalog294. [Actual query evidence](HDMI-GET-OBSERVATION-20261013.md).
The distinct zero-prefix allocation-only successor now passes all four
exchanges and fresh candidate admission on the Pi. Full capture, independent
SSD Linux return, original config/zsh restoration and replay pass, catalog324.
Next implement a bounded visible pixel/text proof using Apple's font, then
same-boot retained backing and explicit consistent noncached XNU video mapping.
Do not widen FDT RAM, the managed span or a global Apple feature macro. Serial
completion alone is not visible output. Preserve the preceding failed candidate.
The first visible candidate now times out at500ms after9rows/2880stores.
Allocation succeeds, but the draw remains failed and visual output unconfirmed.
Independent recovery/restoration and replay pass, catalog344. Preserve this
image/capture; implement a separately bounded compact proof alongside the real
XNU mapping/renderer integration without making that proof an extra prerequisite
for the existing serial zsh's HDMI mirror.
The first allocation trial completed all four exchanges at depth32, but
rejects raw returned address0x3f400000 under its frozen C-prefix-only predicate.
It performs no framebuffer access. Independent Linux recovery and restoration
of both original config and loader pass, catalog314. Preserve this failure;
the Pi 5 reference implementations do not require incoming C-prefix bits.
Fresh address/extent/format and reservation/cache/lifetime authority must still
be established separately in every consumer boot. First
establish a Pi 5 display buffer, validate its
format/stride/extent, exclude it from allocation, and pass checked video data
to XNU's existing text renderer. Initial input may continue over serial;
local USB keyboard support is a separate RP1 USB/HID dependency. The current
SSD Linux now detects HDMI-A-1 connected/enabled with 256 EDID bytes and
3840×2160 modes (2026-10-13 16:46:12 EDT). Linux's framebuffer is not a
standalone firmware/XNU allocation or mapping contract.

Development-toolchain priority: make this a system where the user can compile
and run Swift, C and C++ programs. Build the target SDK and prove Mac-hosted
cross compilation first; native compilation on the Pi follows writable storage,
qualified memory and the necessary userland/runtime support. Keep this work
active alongside display and networking without treating compiler availability
as a prerequisite for showing the existing zsh prompt. The [DEV-01–04
acceptance contract](DESKTOP-OS-PRD.md)
requires separate physical-Pi execution and native-build evidence.

The boot-video ABI encoder and default-off UART/Apple-renderer mirror now pass
software tests and a complete target kernel link. The separate same-boot
FDT-only observation has now completed before any display allocation/mapping.
The initial zero-byte attempt remains failed. After UART recovery, the distinct
early-stage observer completed all 19 prechecks and an actual RC=0 inventory:
no simple-framebuffer node, only the firmware framebuffer service with no
address/geometry. Complete capture, automatic NVMe return, independent Linux
and exact working-image restoration pass; catalog 266. Next implement a
bounded GET-only firmware query, not allocation or guessed mapping. GET
framing, fresh original-FDT mailbox resolution and the pure bounded transaction
core pass 15 software groups with independent transaction review. Real linked
buffer reservation/address/cache and ordered Device access remain required
before the first standalone query; none of these pure helpers authorizes
framebuffer drawing.
[Physical findings and receipts](HDMI-FDT-OBSERVATION-20261013.md).

Latest physical Ethernet trial: the bounded PHY management candidate reads
five0xffff responses and correctly rejects PHY identity. Temporary MAC
management settings restore, but maps/BAR/root restoration is not established
by that failed transaction. Its inherited parser also rejects propagated RC=-6;
preserve the invalid full capture. Independent SSD return and original config/
firmware/zsh restoration pass, catalog334. Next observe the actual RP1 GPIO32
reset state through three exact additional Device pages, then implement explicit
source-backed reset ownership before another bounded MDIO trial. No packets,
DMA or IRQ delivery are established. This is not another stability soak.

Preceding physical Ethernet trial: the distinct capability candidate passes all
47 records, with repeated design words reporting one queue, a 128-bit internal
bus and the 64-bit descriptor feature. Full capture, independent SSD Linux
return, original firmware/zsh restoration and byte-only replay pass, catalog
304. Actual PM63188 remains below65536; no DMA, IRQ delivery, PHY access or
packets. Next implement bounded PHY management with exact temporary MAC
management-clock restoration. Capability bits do not qualify DMA addressability.
[Actual evidence](GATE5-PCIE-IRQ-TRANSPORT.md).

Preceding physical Ethernet trial: the distinct selected-source candidate passes
all 42 rows. Both actual GEM MID reads return `00070109`, and all 15 clock
words repeat identically before and after. Root COMMAND/window, endpoint
COMMAND, all six BARs and both mappings restore successfully. Exact SYS
CTRL2/0x802 plus SEL4 and unchanged PLL/rate/ETH/TSU checks retain all guards
and budgets; actual PM62940 remains below65536. This is register-profile
admission, not measured physical frequency or universal gate-state proof.
Complete 34,072-byte zero-TX capture, independent SSD Linux return and original
firmware/zsh restoration pass, catalog 286. Preserve both earlier failures.
Next implement source-backed bounded MAC/PHY capability/management and then
actual IRQ delivery, DMA rings and Ethernet traffic. Neither packets nor XNU
SSH work yet.

Latest Ethernet checkpoint: the complete same-boot BAR sizing/assignment,
MEM-only decoding, exact GEM/clock Device mappings, reverse unmapping,
COMMAND restoration and all-six original BAR restoration pass on the Pi.
All 25 records and full capture health pass; independent SSD Linux recovery
and original firmware/zsh restoration pass. That cycle's catalog is 240. The cycle
uses 34 config transfers / two halfword writes / two maps / two unmaps, with
61,092 PM checks under the unchanged 65,536 limit.

Every successor must repeat fresh inherited clock validation and GEM identity
under its live owner before PHY management, IRQ delivery, DMA rings or traffic;
the passed diagnostic receipt is not fresh authority for another boot.
Combine independently validated operations in each bounded physical trial.

In parallel, finish the actual OpenSSH executable: all 176 original client
source units compile. Current Apple process/file/locale, original generated
socket wrappers, current upstream zlib and kernel-backed random APIs reduce
unresolved link imports from 108 to 40 in the latest verified combined link. Real
file-backed Libinfo, selected original Apple APIs, Blocks and checked C runtime
providers now compose into a distinct link with 47 imports: additional genuine
dependencies are exposed, rather than hidden. Continue real dispatch_once,
stpcpy runtime qualification and remaining runtime/service providers; both
original-source providers now build/link with native tests but lack Pi execution.
Original strnstr and generated initgroups close 54 → 52; whole original Apple
interface/Ethernet helpers close three and expose genuine ___strncpy_chk,
giving 52 → 50, zero duplicates. Continue the checked provider and remaining
service dependencies without changing the original SSH feature configuration.
Original strncpy_chk/stpncpy then close 50 → 49 with no new dependencies;
five native/target-contract tests pass. Original post-copy overlap checking is
retained and is not a prewrite overlap-safety guarantee.
Original case-search/comparison and minimally corrected signal providers close
49 → 47, no new dependencies. Preserve the reproduced original signal failures;
the accepted archive is derived, not unchanged upstream strsignal. Four focused
groups pass, including complete target ownership; no target execution is claimed.
The derived Apple clock read provider then closes 47 → 46 with no new imports.
Original failure paths are reproduced and corrected explicitly; native tests
include 36,936 rational-scale cases, and the forced read-only target contract
has zero undefined symbols with actual map-owner checks. Clock setting still
lacks `_settimeofday`; preserve that separate forced-link failure. Next qualify
the read APIs on the Pi and continue real file/stdio/service dependencies, not
host test doubles or reduced SSH features.
Original current Apple TTY/temp providers and four original generated syscall
wrappers then close 46 → 42, with no new imports or duplicates. Four main-rerun
groups pass native and forced static contracts; no new target execution is
claimed. Preserve the modern stdio compile/ABI failures while implementing the
remaining real runtime dependencies.
The current system/spawn group closes42→41. It retains original spawn/trap
bodies and explicitly derives a one-line errno propagation fix in system,
preserving the original failed error contract. Five main-rerun groups pass;
16 forced APIs link with zero undefined imports. No target execution or
modern/legacy FILE mixing is claimed.
The original full-client feature configuration and failed links are retained
as concrete dependency evidence. A linked/running client and daemon still
require acceptance; the existing diagnostics do not establish either.

Latest userland checkpoint: the 45-node / 33-file root physically passes all twelve
commands, mounted identity, separate actual zero zsh exit, complete fault scan,
independent SSD Linux return and original-loader restoration. Catalog is 220.
Original getentropy and LibreSSL RAND APIs now execute successfully; startup
health completion and zero failure counters are observed, not entropy-quality
or live-key qualification. No manual restart or additional soak.

Ethernet checkpoint: all-six RP1 BAR sizing/restoration passes on the Pi with
49 transactions and 12 writes. The corrected nested-check composition uses
44,748 PM checks within the unchanged 65,536 limit. Full fault-checked capture,
independent SSD Linux return, original firmware/zsh restoration and replay
pass; catalog 212. Address assignment, Device mapping, interrupt delivery,
DMA and Ethernet traffic are not yet accepted.

Userland previously passed all ten commands in the 43-node / 31-file root,
including real OpenSSH/LibreSSL packet crypto (48 valid / 5,036 rejected cases)
and a separate actual zero zsh exit; root45 retains these successes and adds both
entropy diagnostics in one boot. Original LibreSSL RAND uses an explicit
project-owned stateless getentropy adapter, not private Apple corecrypto or
an RC4 fallback. Host/API success does not qualify live keys or establish SSH.

The BAR assignment candidate has now passed as recorded above. Full OpenSSH
client/daemon link dependencies continue in parallel;
packet/RAND diagnostics do not close that executable or service. Do not repeat
an accepted soak or boot merely to replay
offline evidence; preserve failure records and combine substantive changes.

The Pi LAN is reachable again. One guarded firmware/BL33 trial completed the
actual 19-marker ABI sequence (five SMCs, RC 0), automatically returned to normal
NVMe Linux, and both original firmware and working zsh image were restored.
Full receipt/capture/return/restoration replay passes; no manual power cycle or
repeat soak. [Physical evidence and limits](GATE5-PCIE-IRQ-TRANSPORT.md).

Parallel work now follows this sequence:

Current checkpoint: the corrected 42-node image now passes all nine commands
on the Pi, including genuine Apple pthread startup and four-thread lifecycle,
complete mounted identity and the separate actual zero process exit. Continuous
capture through NVMe return, independent Linux return and original firmware/zsh
restoration all pass; catalog 184. Next batch adds the real packet executable
as command ten. Ethernet proceeds independently with passive owner telemetry:
bounded logging now survives, but the contained BAR trial stopped at guard 4
before its first write. Preserve that failure and identify the exact owner
state before changing any access policy or limits. No additional soak.

The subsequent passive owner trace now identifies that state on the Pi:
65,536 PM checks exhausted, IRQ post-core PM failure, no next SMC, deadlines
still valid, zero BAR writes. Full fault-checked capture, independent Linux
return and original pair restoration pass (catalog 194). Develop a distinct
full-path-tested redundant-check correction while the ten-command packet
image proceeds; do not raise limits or remove MMIO pre/post admission.
Here admission means the existing transport pre/post guards and provider
owner-check sites, with firmware checks bracketing the complete lifecycle
callback; it does not imply a firmware call per individual provider read.

1. Finish the combined loader/kernel retained-FDT and readiness handoff, then test the
   distinct 96-entry-capacity XNU RAM-root candidate on the Pi. The first
   physical attempt stopped before VM initialization because the loader omitted
   a descriptor required by the linked kernel; zero serial input was sent,
   watchdog recovery worked, and known-good zsh was restored. Preserve that
   failed image/evidence and add a negative compatibility regression. It
   contains the preserved shell/tools, a regenerated 22-file identity catalogue,
   a real statically linked Apple OpenSSH buffer diagnostic, and corrected RP1
   configuration-read code. Building those components is not board acceptance.
   The corrected loader now boots the exact root to the recovery shell, but
   SMP output corrupted its mandatory watchdog marker; no commands were sent.
   Move distinct readiness telemetry after a real bounded reload, retain
   strict admission, and batch the independently checked utility/crypto root
   into the next useful trial where its timing budget permits.
   That distinct 41-node trial now mounts correctly and emits all eight valid
   command outputs/zero per-command statuses. Its oracle falsely rejects the
   known four-line pwd startup prefix, so the separate final process-exit
   query never runs. The original failure stays preserved; a distinct strict
   v2 oracle validates the existing actual bytes without inventing that missing
   query. SSD Linux return and baseline restoration are independently verified,
   with 118 inherited artifacts. Do not repeat the same physical batch solely
   to diagnose this known oracle issue; combine v2 with the next substantive
   userland addition.
   The ensuing 42-node pthread trial reaches the shell but its early mount
   marker is corrupted by concurrent CPU startup. Admission sends zero bytes;
   all nine commands remain unrun. Independent SSD Linux return and exact
   baseline restoration are verified, with 166 retained artifacts. Add bounded
   late confirmation of actual installed read-only root state after successful
   watchdog reloads; do not merely extend the delay or waive root identity.
   Batch the same nine useful commands into the corrected distinct image.
   Use the distinct checked installer and marker-guarded serial trial; reclaim
   only an exact redundant FAT backup after archiving and hash verification.
2. The concrete PCIe lifecycle provider and boot caller now execute on the Pi.
   The first bounded ID attempt reached UBUS configuration after initial PHY
   setup, then failed safely before identifying RP1; original firmware/zsh were
   restored. Exact passive telemetry now identifies a successful `0x416c` read
   returning `0x60`: our predicate wrongly requires reserved-zero workaround
   bits before reaching the documented outstanding-request fallback. Correct
   UBUS and its QoS/clock consumers in a distinct image, preserve strict
   unrelated-bit/access/recovery checks, then continue bounded controller/link/RP1
   discovery. The trace returned automatically to verified SSD Linux; the
   original firmware/zsh pair was restored. The corrected AXI kernel/loader now
   pass actual full-link and package tests. The zero-input physical trial now
   completes UBUS/QoS/root-complex setup and reaches link training after PERST
   release, then fails before RP1 identification. Normal SSD Linux return is
   independently verified; the original pair is restored and full replay passes.
   Batch a source-correct elapsed settling helper with passive link-step/return/
   elapsed telemetry, retaining the original timing ceilings. The actual
   elapsed image now physically passes link training: 100,623-us reset settling,
   one link-up poll in 540 us. Clock finishing also completes; `LAST=14` is
   RP1 configuration inspection, not phase-13 clock finishing. The generic
   `0x4068=0x0003e0b0` field is stale because config callbacks do not update it.
   The distinct passive config trace now completes all 32 transfers but reads
   stable all-ones endpoint data. The actual linked RC core omits bus-number
   initialization; Linux reference confirms primary 0 / secondary 1 /
   subordinate 1. The narrow separate route correction now physically reads
   initial root bus zero, sets `00010100`, confirms all readbacks, then obtains
   RP1 ID `00011de4` at Gen 2 ×4 with endpoint COMMAND disabled. However its
   53-argument logging record panics after END; the earlier config trace has
   the same missed post-END encoding panic. Keep successful ID evidence distinct
   from whole-trial acceptance. Fix logging with bounded framed calls and reject
   faults throughout recovery, without weakening assertions. Assess batching
   the next guarded BAR sizing/restore step, without resource assignment,
   COMMAND/MEM/BME, IRQ, DMA or packets, only after separate admission review.
   The original pair is restored in `root-route-restored-20261013`, with fresh
   SSD Linux boot `ee1f125a-112c-4da6-9f06-635451451e94` and 158 retained archive
   catalog entries. Original receipt/capture/return/restoration replay passes
   its narrower ID/return scope; separate health supplements explicitly flag
   both panics. Original admission and raw capture remain immutable.
   The reviewed byte-sealed path most recently measures 22.461-second publication and 22.890-second
   restoration while retaining fresh device/root/current-image/active rollback
   checks. Preserve frozen v2 evidence; make the next controller descriptor-
   driven and derive ancestry counts from validated receipts rather than adding
   per-trial publisher copies or rerunning old compiler/history audits.
   The firmware ABI result
   does not establish whole-domain ownership, safe endpoint DMA, or Ethernet.
   Continue with BAR/interrupt/DMA/GEM integration and actual wire traffic.
3. In parallel, add current Apple utilities and close genuine SSH crypto,
   entropy, process/authentication/session/PTY dependencies. The buffer probe
   is a dependency test, not an SSH client/server or crypto acceptance test.
   Real LibreSSL now closes EVP; current Apple erasure/comparison/sysctl leaves
   close their target imports. Next integrate genuine Apple pthread/main-thread
   initialization, required libplatform services and crypto constructors rather
   than substituting no-op locks or bootstrap fake identities. Six genuine
   original providers now close the next link gap; eight main-thread startup
   imports were exposed, and the static private-symbol collision is explicitly
   fixed in a distinct artifact. Genuine Mach/thread/message providers now close
   that layer. Ten deeper logging/syscall/libproc/VM/time imports now close with
   original providers, and a private five-global ownership correction yields
   zero unresolved/duplicate symbols. Four new focused tests independently pass.
   Actual linked-kernel apple-vector/registration-feature contracts are audited.
   Genuine `VARIANT_DYLD` main-thread/TSD bootstrap now precedes the
   ordinary pthread initialization and constructor sequence: non-dyld
   `_pthread_set_self(NULL)` cannot bootstrap the original `mach_init` path.
   The distinct original-provider startup/create/join diagnostic links cleanly
   with no undefined/duplicate symbols; five focused tests independently pass
   (0.618 s) and startup review finds no blocker for this bounded probe. Add
   it to the next separate root with the prior eight-command batch and corrected
   v2 oracle, checking genuine target thread creation/TSD/mutex/destructors and
   actual batch-process exit. The old fake-entry/TSD diagnostic stays unexecuted.
   Current checks are offline results, not an initialized target runtime or SSH.

Known-good artifacts remain preserved. Gate 4 durable storage is separately
held; the full zsh/TTY, Ethernet, services, Apple-layout and recovery objective
remains active. No unrelated VM image or source is changed.

## Latest correction — separate OpenSSH buffer-reset overlay, 2026-10-13

Corrected the reproduced retained-max/reset invariant in one copied source
function; pristine Apple source and original failing artifact remain unchanged.
Actual production symbol/extern sets match the original. New Cortex-A76 archive
`build/rpi5/apple-ssh-reset-7j7hbjqx`, 105,472 bytes/SHA 51596ace…, 1,587 verified
pins. Three focused tests pass (2.559s): 514 capacities/three rounds, zeroization,
read-only/parent behavior, actual original ordinary buffer tests and an explicit
extra host-only allocation failure. Original repro now reaches its intentional
return-7 sentinel; the dedicated new regression returns zero. Native host/
compile evidence only, not static Pi runtime/SSH/crypto or board acceptance.
[Detailed correction and validation limits](GATE6-USERLAND.md).

Next close the actual reachable target runtime dependencies with original
providers and correct startup/syscall adapters, not three-archive symbol names
alone. Follow with genuine public crypto/entropy and full process/auth/privsep/
account/session/PTY integration while preserving Apple path conventions and
failure semantics. Independent Ethernet still needs its prepared guarded
physical ABI/recovery step once authorized Pi-LAN reachability and fresh SSD/
card/sole-owner verification are available. No board/SD/serial/firmware/network/
reboot or VM image action, no broad suite rerun; all previous accepted baseline
and 16 tooling pins remain unchanged. Full goal and Gate 4 hold stay active.

## Latest offline implementation — original OpenSSH dependencies, 2026-10-13

New pristine Apple OpenSSH checkout f386b2e9… (10.0p2), separate from VM work.
Twelve unchanged buffer/error/compat/signal/log/allocator/pattern/fatal units
compile for Cortex-A76; archive `build/rpi5/apple-ssh-buffers-_2f0fe7x`, SHA
de8d5003…, 105,456 bytes and 1,461 matching unique pins. Original config stays
unchanged, no crypto/PAM/sandbox implementation inferred from declarations;
public OpenSSL headers only, no crypto runtime or full Xcode integrations.
Three focused tests pass (2.148s) under native host libSystem/ASan/UBSan, not Pi
runtime closure. A separate original low-max/reset SIGSEGV reproducer remains
unfixed and explicitly recorded. No vendor source patch or replacement stub.
[Exact artifact, failure and dependency limits](GATE6-USERLAND.md).

Next derive/close actually reachable target dependencies (including real
secure erasure/signals/logging), assess the retained reset/max failure in a
distinct overlay, then genuine public crypto/entropy and full process/privsep/
auth/account/PTY/service integration. Conservative object/archive symbol counts
are not a list of missing Pi APIs; separate syscall/startup objects and actual
link reachability must be included. Follow Apple's command/config/helper path
conventions and preserve source licenses. Working SSH still requires Ethernet
wire traffic and further real userland services; no security-feature bypass
to declare success. Board trial still waits for authorized Pi-LAN reachability
and fresh SSD/card/sole-owner verification. Existing VM sources/artifacts,
Pi root/kernel/images and Gate 4 hold remain untouched. No board action or
broad suite rerun; all original full-goal scope remains active.

## Latest verification — recovery replay and read-only return collector, 2026-10-13

Added full receipt-bound ABI/capture/normal-Linux/dual-restoration replay and
one-attempt read-only SSH Linux-return capture. Complete typed zero-TX trace,
armed metadata, byte/time coverage, fresh SD and bounded actual f6/NVMe boot,
new exact SSD/card identity and both restored original hashes remain separate
requirements. No implicit retry/reboot/restore or controller permission.
**Nine targeted tests pass (23.591s)** using synthetic serial/receipt/SSH
fixtures; direct CLI checks pass, prior 16 tooling pins unchanged. No broad
suite rerun or physical acceptance claim.
[Exact tooling, artifact and limits](GATE5-PCIE-IRQ-TRANSPORT.md).

Fresh SSH still times out. The Mac routes 192.168.4.23 through its **default
gateway 10.0.0.1/en0**, not a direct/specific Pi-LAN route; known mDNS lookup and
ARP entry are absent. Current Pi OS/boot is unverified; no SD/firmware/serial/
reboot/power action. Next restore authorized network reachability (no silent
Mac network switch), reverify SSD Linux/exact card/sole ownership, then one
guarded installation, armed continuous capture, ABI/recovery boot, independent
normal Linux return and explicit dual restoration. This reachability finding
does not call for another Pi power cycle. Offline Ethernet/SSH/userland work
remains available; full objective and separate Gate 4 hold remain active.

## Latest tooling — dual firmware/image install, restore and recorder, 2026-10-13

Actual dual-file publisher/explicit restore and installation-bound receive-only
recorder are implemented. Complete SSD raw/file backups, both FAT temporaries
verified before either rename, firmware-first publication with durable SSD
journal, exact latest FAT/60-artifact ancestry and typed receipts. No atomic
pair/FAT power-loss claim, implicit retry/rollback, config or HFS change. New
coordinators share a nonblocking OS board lease; recorder also rejects existing
port handles and uses exclusive serial access. No serial commands/reboot or
reopen on disconnect. **17 focused tests pass (43.927s)** with explicit hardware
doubles; no broad suite rerun and no physical publication/recovery claim.
[Detailed behavior, plan-only artifact and limits](GATE5-PCIE-IRQ-TRANSPORT.md).

Both fresh SSH attempts to 192.168.4.23 timed out; current Pi OS/boot is
unverified. Probe exists and has no reader/other trial coordinator observed;
no SD/serial/firmware/power/reboot action. Local plan-only
`build/rpi5/fwabi-pair-plan-20261013` uses the **last verified**, not fresh boot
ID; 16 source/archive pins match, no remote run. Do not execute it as a stale
authority. Next freshly verify normal SSD Linux, exact card/raw baseline and
sole ownership; use a fresh dual installation run, validate its receipt, arm
continuous receive-only capture **before** one bounded ABI/recovery boot.
Require independent new normal NVMe Linux return, then explicit restoration
of both old firmware and zsh. Inspect unknown outcomes in the same run/journal/
mount/live handle instead of retrying. Controller writes remain held pending
independent domain/source/endpoint/DMA admission. Full Ethernet/zsh/TTY/SSH/
Apple CLI/layout scope and the separate Gate 4 durability hold stay unchanged.

## Latest preparation — real standalone firmware ABI caller, 2026-10-13

Built/audited a separate primary-only BL33 with original-FDT preflight, actual
PM/IRQ/NS firmware-client cores and real SMC instructions. Package
`build/rpi5/pcie-fwabi-y_995zop` (55,552 bytes, SHA 3cd15bad…) is paired with the
unchanged distinct EL3 verifier, not installed or board-tested. One watchdog
reload, three selective GIC-disable writes, QUERY/CLAIM/three timed CHECKs and
terminal no-servicing park; no controller/calibration/endpoint/DMA write or new
XNU execution. 9,088 pins, 17 package/11 exact leaf checks, 101 selected tests
(40.210s), actual modeled trace/strict 19-line serial replay, unchanged prior
11,505 kernel pins. [Details and explicit evidence scope](GATE5-PCIE-IRQ-TRANSPORT.md).

Next implement/test guarded **dual firmware/loader** install+restore using the
latest restored FAT and **60 inherited artifacts**, then arm an installation-
bound continuous receive-only capture before one ABI/autonomous SSD-return
trial. Passing a modeled/parser trace is not board acceptance. Do not silently
replace firmware with an old single-file publisher. After physical ABI/recovery
proof, close remaining real power/shared-domain/source/endpoint/DMA provider and
XNU controller caller, then RP1/BAR/IRQ/DMA/GEM/wire traffic. Full zsh/TTY, socket/
SSH, Apple utilities/layout and the independent Gate 4 hold remain unchanged.
Fresh SSH is SSD Linux boot 3977a538… with SD unmounted; no live mutation here.

## Latest integration — XNU firmware client in controller path, 2026-10-13

Real retained PE owner, strict NS protocol client and exact SMCCC64 assembly
now compile/link into a distinct complete kernel. Actual startup is one PM
claim → NS IRQ claim → EL3 QUERY/CLAIM → reset/calibration; actual guards
recheck IRQ/firmware before/after the independent provider. Missing/error SMC
fails before reset; failed claim leaves local interrupts masked for terminal
park, not normal continuation. Remaining domain/source/endpoint/DMA admission
is not relaxed. [Exact artifacts, real-body tests and limits](GATE5-PCIE-IRQ-TRANSPORT.md).
All 94 focused tests pass (34.200 seconds), 11,505 pins and actual native
loader host-buffer checks agree. No firmware/kernel installed or board trial.
Next firmware-ABI caller/package and dual firmware/loader preservation/staging
against current restored FAT/60-artifact chain, then one exact ABI/recovery
trial before controller writes. Follow with full provider/boot caller and
controller/RP1/BAR/IRQ/DMA/GEM packets. Full objective and Gate 4 hold remain.

## Latest implementation — firmware-side controller verifier, 2026-10-13

An actual EL3 fast-SiP service now checks selected SPI group/mask/active state
from the secure view, retained controller-1 reset/RESCAL accessibility and an
already armed/decreasing watchdog. One trusted-NS owner, nonblocking one-attempt
lock, immutable check/deadline bounds and quarantine; no hardware writes or
release/retry. A distinct full TF-A image links/audits with 9,024 matching pins;
91 focused regressions pass. [ABI, exact artifact and limits](GATE5-PCIE-IRQ-TRANSPORT.md).
No firmware installed, no new board execution, source/endpoint/DMA or whole
power ownership granted. Original firmware/images/kernel sources stay intact.
Fresh SSH remains SSD Linux boot `3977a538-fae5-434d-a94f-50c9422fea84`, SD
unmounted. Next actual XNU SMC consumer/retained owner/startup/terminal-failure
park, then guarded dual firmware/loader ABI/recovery trial against the restored
60-artifact baseline before controller writes/RP1/IRQ/DMA/GEM packets. Full
userland/network/recovery objective and separate Gate 4 durability hold remain.

## Latest physical result — read-only PCIe access passed, 2026-10-12

The exact standalone access image physically completes all 30 ordered word/
halfword register reads in 578,620 us, RC 0 / 184 callbacks, with no PCIe writes,
config/endpoint/DMA access. Continuous zero-TX capture shows the autonomous
reset, actual next-boot override and NVMe selection; independent SSH confirms
new SSD Linux boot `3977a538-fae5-434d-a94f-50c9422fea84`. Both read snapshots
agree, but status matches the project's RC-down predicate, not link-up.
Guarded restoration verifies 56 prior artifacts plus complete fresh snapshots
and restores the tested zsh image. [Exact physical evidence](GATE5-ACCESS.md).
Current FAT is `fd2d20729dca2025df35310eb1165a64692d0bed3e604bb8f77355ff28ec8033`;
next installer must use this restored receipt and **60 inherited artifacts**.
Next close concrete power/shared-domain/firmware/source/endpoint/DMA/IRQ
ownership, wire the actual controller boot caller, then bounded controller/
RP1/BAR/IRQ/GEM packet trials. Read accessibility is not write/driver admission.
Full zsh/TTY, Ethernet, SSH, Apple utilities/layout/recovery and Gate 4 scope
remain active; no repeated soak, manual cycle or firmware/config/HFS change.

## Latest physical result — autonomous recovery / zsh restored, 2026-10-12

The tagged watchdog-only image physically passed on the Pi: actual one-time
15-second countdown/decrement, non-servicing stop, continuous reset/bootloader
capture, actual `0xf6` override/NVMe selection and a different verified SSD
Linux boot. Zero serial TX, one software SD boot, no manual cycle or extra soak.
Guarded restoration reverified 48 inherited artifacts plus fresh full snapshots
and restored the tested zsh image. [Full physical evidence and cleanup diagnosis](GATE5-WATCHDOG-PHYSICAL.md).
Current Linux boot is `2407dd80-a11d-47f0-9ae0-57f5c47345ef`, SD unmounted;
current FAT hash is `0999f771c93c0747efaf262b8ce5232762628497a9db4e2bc2f2c648917c76eb`.
Next use that restored receipt and **52 inherited artifacts** for the distinct
read-only PCIe access trial, then concrete shared-domain/endpoint/IRQ/DMA/
controller/RP1/GEM/packet progression. No PCIe admission is inferred from the
watchdog result. Full userland/network/recovery objective and Gate 4 hold remain.

## Latest implementation — watchdog-only image, 2026-10-12

A distinct 38,592-byte primary-only BL33 candidate now links the unchanged real
PM lease with fixed-address route/countdown access and exactly one 15-second
reload. No XNU/PCIe/GIC/reset/calibration/RP1/DMA access or reset-route write.
The inherited secondary/IRQ entry dependencies are removed in a new entry;
the actual protocol's wait now rejects regression at its initial boundary.
All 61 focused tests, 16 emitted-image checks, accepted kernel pin sets and
35 unchanged zsh/socket checks pass. [Artifact and limits](GATE5-WATCHDOG-ONLY.md).
Fresh SSH confirms the same SSD Linux boot/root and both SD partitions
unmounted; no serial/media/power/reboot/config action occurred. Physical PM
reset/SSD return is still unproven. Next implement guarded current-baseline
installation/rollback with all 44 inherited artifacts and uninterrupted tagged
capture, then one software recovery trial before PCIe access/controller/RP1/
IRQ/DMA/GEM packets. No repeated soak. Full userland/network/recovery objective
and separate Gate 4 hold remain active.

## Latest live prerequisite — exact SD boot/recovery reference, 2026-10-12

Fresh SSD Linux boot `8512e93e-ec70-4715-bb02-d118afe393ed` is stable. The new
read-only collector verifies the current physically tested socket/zsh image,
all protected file hashes and complete MBR/FAT bytes before/after a RO FAT
mount, with exact mount ownership and final unmounted-state/root/boot checks.
SD config already contains `set_reboot_order=0xf6`; EEPROM stays SD-first
`0xf461`. Current Linux firmware boot mode is 6, partition 1, tryboot 0.
The configured watchdog request is **60**, distinct from the diagnostic's
planned single 15-second reload; no config rewrite is required by that fact.
[Exact live evidence, source snapshots and next single-trial sequence](GATE5-PCIE-RECOVERY-REFERENCE.md).
All **48 selected reference/installer/socket tests pass** in 10.452 seconds;
accepted 2,435/2,411 kernel pins and 35 unchanged zsh/socket checks revalidate.
Next implement a distinct watchdog-only trial, preserve the current image/
44-artifact chain with fresh snapshots, arm uninterrupted capture, then one
software boot to qualify actual PM reset and SSD return. This configuration
reference does not prove the latch, live countdown, physical reset-return,
inherited/shared domains or PCIe/IRQ/endpoint/DMA admission. Follow that with
bounded access/controller/RP1/BAR/IRQ/DMA/GEM and packet validation; retain full
zsh/TTY/SSH/Apple utilities/layout/recovery scope and the separate Gate 4 hold.
No SD writes, HFS mount, serial, Pi reboot/power or firmware/config changes.

## Latest integration — real controller IRQ handoff, 2026-10-12

The real initial-controller path now claims the existing watchdog exactly
once, then the actual selective IRQ lease before reset/calibration access.
XNU's own interrupt API masks the handoff and restores prior state only after
successful claim; failed claim is terminal with local interrupts left disabled.
Actual guards freshly check the same lease before/after the independent
provider, including post-callback thread/singleton/provider/phase ownership.
PRECLAIM prerequisites are explicitly distinguished from the later IRQ claim.
[Artifact, sequencing, test doubles and remaining admission](GATE5-PCIE-IRQ-TRANSPORT.md).
A distinct complete kernel compiles warning-free, has zero undefined symbols
and no new linker warnings, retains all actual controller/IRQ entries and
initializers, and passes native loader host-buffer checks and all 2,435 pins.
All **286 selected regressions pass** in 172.591 seconds, including localhost
socket checks; the unchanged physically tested zsh/socket package retains all
35 checks. No boot caller, concrete shared-domain/source/endpoint/DMA provider,
combined package, install, board activation or Ethernet proof is added.
Next close actual shared-domain/power/clock/firmware/endpoint/DMA and bounded
fault/reset/SSD-return admission, then guarded controller/RP1/BAR trials and
IRQ routing/DMA/GEM packets. Keep full zsh/TTY, sockets/SSH, Apple utilities/
Darwin layout and recovery scope active, with Gate 4 durability held separately.
No accepted image/source/root or Pi/serial/SD/power/firmware/reboot/soak action;
no manual hardware step is needed for this source integration.

## Latest implementation — selective non-secure SPI lease, 2026-10-12

Actual PE claim/check code now compiles/links in a distinct complete kernel,
using the existing GIC mapping and PM lease. Precise PCIe2 W1C masks exclude
NVMe, local IRQ/FIQ must be masked during claim, and the current thread is
retained/bound until reset. Fresh enable/active samples, preserved pending
events, permanent quarantine and atomic output pass native core/actual-PE
models. Complete linkage has no undefined symbols/new warnings; 2,411 pins,
all original controller definitions/initializers and native loader host-buffer
validation pass. [Evidence and limits](GATE5-PCIE-IRQ-MASK.md).
All **282 selected regressions pass** in 150.979 seconds; the unchanged tested
zsh/socket package retains all 35 checks.
Next distinct transport integration must claim IRQ ownership after its existing
single watchdog claim but before reset/calibration MMIO, then recheck on the
same owner. This cannot be called from the earlier PRECLAIM callback; preserve
that sequencing distinction rather than inventing completed IRQ ownership.
Secure firmware, inherited/shared domains, source/endpoint/DMA safety and
bounded access/reset/SSD-return still need real admission before activation.
No boot caller/package/install/Pi/serial/SD/power/firmware/reboot/soak change;
full zsh/TTY, Ethernet, SSH, Apple utilities/layout and recovery scope stays
active, with Gate 4 durability independently held.

## Latest evidence — live lifecycle bindings, 2026-10-12

Fresh SSH verifies SSD Linux, boot `8512e93e-ec70-4715-bb02-d118afe393ed`.
The new fixed read-only collector passes two stable metadata snapshots and
root/boot checks, derives exact PCIe2 GIC-bank selection excluding NVMe, and
records live GEM clock rates. All 26 selected tests, prior accepted pin sets
and 35 unchanged zsh/socket checks pass. Host-controller runtime-power status
is explicitly unsupported, not proof of active inherited domains; absent
clock properties are not physical access permission.
[Live evidence and concrete provider requirements](GATE5-PCIE-LIFECYCLE-REFERENCE.md).
Next implement actual shared-domain and selective SPI ownership, close bounded
access/reset/SSD-return admission, then combine/package/guardedly trial the real
controller before RP1/BAR/IRQ/DMA/GEM and wire tests. No old image/source/root
change, Pi reboot, serial, mount, SD block access/write, firmware edit or soak.
Full serial zsh/TTY, Ethernet, sockets/SSH, original Apple utilities/Darwin
layout and recovery stay active; Gate 4 durability remains a separate hold.

## Latest integration — actual controller composition, 2026-10-12

One real owner entry now wires the actual initial chain, RC/windows, bounded
link training and post-link clock on the same sessions/maps and one watchdog
claim. Actual halfword instructions/barriers, independently guarded one-ms
delay chunks, twelve fresh modeled unused-window rechecks and all clock modes
pass five focused tests, including 12,806 owner-guard/12,810 provider failures.
A distinct complete kernel compiles three warning-free new units and links
without undefined symbols/new linker warnings. Native loader host-buffer
validation and all 2,380 pins pass.
[Evidence and required concrete provider](GATE5-PCIE-CONTROLLER.md).
All **268 selected regressions pass** in 137.465 seconds with local-loopback
access; prior pins and 35 unchanged tested zsh/socket checks also revalidate.
The independent callback is a required contract, NOT a concrete power/clock/
shared-domain/IRQ/DMA/recovery implementation or a physical proof. Next supply
that real provider and access/recovery evidence, then combine loader/kernel/
root and preflight before a bounded board trial. Continue actual RP1 config/
BAR discovery, interrupt routing, DMA/coherency, GEM clocks/PHY and packets.
Do not manufacture COMPLETE dependencies or turn an ownership flag into
physical admission. Full serial zsh/TTY, Ethernet, SSH/sockets, original Apple
utilities/Darwin layout and recovery stay active; Gate 4 remains separate.
No accepted image/source/root, Pi, serial, SD, power, firmware, reboot or soak
change or fresh OS/root observation; no manual restart for this source work.

## Latest integration — clock policy and pre-link advertisement, 2026-10-12

Actual `runPHYUBUSQoSAndClock` now calls the real prior chain and honors
original-FDT `aspm-no-l0s` before link training. The compiled clock core also
handles absent/default/safe/no-l1ss post-link modes without enabling root ASPM/
clock-PM, inventing a BCM2712 RGR1 timer or fabricating a completed link. Five
focused model/real-build tests pass with 1,124 callback failures, 1,124 dependency
losses and 280 all-ones reads. A distinct complete kernel links warning-free
new units with no undefined symbols/new linker warnings; native loader host-
buffer validation, all 2,343 pins and 35 unchanged zsh/socket checks pass.
[Evidence and actual integration boundary](GATE5-PCIE-CLOCK.md).
All **263 selected regressions pass** in 116.236 seconds with local-loopback access.
Next close concrete inherited-domain/shared ownership, IRQ/endpoint/DMA
quiescence and autonomous recovery, then wire actual RC/windows/link and the
post-link clock core on those sessions; continue config/BAR discovery, IRQ,
DMA and GEM. The existing owner guard is NOT a check_lifecycle provider.
Keep full real serial zsh/TTY, Ethernet, SSH/sockets, original Apple utilities/
Darwin layout and recovery scope active; Gate 4 remains separately held.
No accepted image/source/root or Pi/serial/SD/power/firmware/reboot/soak state
changed; no current-root or Ethernet claim. No manual restart for source work.

## Latest integration — original-FDT options and QoS, 2026-10-12

Actual preparation now validates original firmware options before provider/map
ownership. The pinned stock DTB's VDM map is consumed by the real FIFO/VDM
continuation after the actual PHY/UBUS/unused-window chain, on the same mapping,
sessions and watchdog claim. Six focused parser/model/build tests pass, including
425 callback failures and 425 dependency losses. The separate complete kernel,
native loader host-buffer check, all 2,312 pins and the unchanged tested
zsh/socket package's 35 checks pass. [Evidence](GATE5-PCIE-PROFILE-QOS.md).
All **258 selected regressions pass** in 108.009 seconds with local-loopback access.
No physical activation, provider/boot caller or permission inference from FDT
absence. Next concrete inherited power/clock/shared ownership, IRQ/endpoint/DMA
quiescence and recovery; consume retained CLKREQ/ASPM policy while wiring
RC/windows/link with current unused-window rechecks, then config/BAR/IRQ/DMA/GEM.
No new manual restart is required for this source work. Keep full real serial
zsh/TTY, Ethernet, SSH/sockets, original Apple utilities/Darwin layout and
recovery scope; Gate 4 remains separate. Accepted images/source/root and Pi/
serial/media/power/firmware/reboot/soak state are untouched; no current-root claim.

## Latest integration — unused-window prerequisite, 2026-10-12

The actual PHY/UBUS owner now wires a read-only check of unused inbound slots
4–10/outbound 2–3 through its existing Device mapping, real sessions and single
watchdog claim. Two stable snapshots, owner/watchdog guards, strict RC/PERST/
link/IDDQ predicates and exact 23-read/no-write phase policy pass six focused
model/real-build tests. A distinct complete kernel and native actual-loader
host-buffer validation pass; all 2,272 pins and 35 tested zsh/socket checks
revalidate. [Artifact and limitations](GATE5-PCIE-UNUSED-WINDOWS.md).
All **252 selected regressions pass** in 97.751 seconds with local-loopback
access; the initial sandbox-only UDP-bind failures resolve on the full rerun.
No physical observation, boot caller, provider registration or admission is
claimed. Next concrete inherited lifecycle/power/clock/shared ownership and
IRQ/endpoint/DMA quiescence/recovery, plus full original-FDT option validation;
then wire RC/windows/link with current unused-window rechecks, config/BAR,
interrupts, DMA and GEM. The new inspector alone cannot supply the complete
`check_quiescent` contract. Keep real serial zsh/TTY, Ethernet, SSH/sockets,
Apple utilities/Darwin layout and recovery intact. Gate 4 remains separately
held; no accepted images/source/root changes or Pi/serial/media/reboot/soak
operation or current-root claim.

## Latest integration — complete PCI/FDT kernel link, 2026-10-12

A distinct complete kernel now combines original Apple PCI code, the real
PHY/UBUS/watchdog owner and retained-FDT path with the preserved source-built
kernel providers. The original replay matches every non-UUID byte; the final
link replaces exactly the superseded early-kernel/PM objects and has no undefined
symbols or new linker warnings. Seven added initializers are in the genuine
read-only runtime table with actual local fixups. Five focused tests and the
native real-loader copy/rebase comparison pass.
[Exact artifact, replay and limits](GATE5-PCIE-KERNEL-LINK.md).
All **246 selected regressions pass** in 85.373 seconds; complete-kernel and
preceding component pins plus the preserved zsh/socket package revalidate.
Not installed, booted or combined with the new loader. Next concrete provider/
boot-caller and genuine power/clock/shared ownership, RP1 quiescence/autonomous
recovery admission; unused-window/RC/windows/link/config/BAR; then IRQ/DMA/GEM.
Keep full serial zsh/TTY, Ethernet, SSH, Apple utilities and recovery scope.
Accepted images/sources/root and Gate 4 hold remain unchanged; no Pi, serial,
media, power, firmware, reboot or soak action or current-root claim.

## Latest integration — retained firmware FDT to real preparation, 2026-10-12

A distinct loader/kernel-component build now supplies a descriptor-only raw-FDT
handoff and actual post-VM Normal-RAM view, requires post-kernel retention,
copies/sanitizes through Apple OSData and calls the real strict PCIe preparation
path via `prepareBoot`. Four focused tests pass with actual early-kernel/IOKit
compilation, original-family partial linkage and native real resolver/handoff/
seed/Apple serialization/resource decoding. Opt-out whole-image equivalence
passes; the new loader bound leaves 4,032 bytes without relaxing its reserve.
[Evidence and remaining integration](GATE5-FIRMWARE-FDT-HANDOFF.md).
All **241 selected regressions pass** in 82.286 seconds; final component pins
and all 35 checks on the unchanged tested zsh/socket package revalidate.
No activation or boot caller. Next complete-kernel replacement/linkage,
intentional provider registration and genuine power/clock/shared-resource/
RP1-DMA-quiescence/recovery admission, then unused-window/RC/windows/link/
config/BAR/IRQ/DMA/GEM. No accepted source/image/kernel/root modification, Pi/
serial/SD/power/firmware/reboot/soak action or Gate 4 waiver. Preserve all real
zsh/TTY, Ethernet, SSH, original utilities and recovery requirements.

## Latest implementation — actual PHY-to-UBUS connection, 2026-10-12

A separately compiled copy of the real IOKit PHY owner now runs the actual
UBUS/AXI core on its existing SerDes/reset/calibration session, through guarded
phase-restricted volatile access. No new mappings or watchdog claim. Four tests
pass, including 502 modeled guard failures, both AXI paths, exact old/new access
permissions and real warning-free compilation/partial Apple PCI linkage. All
732 input and 17 generated hash entries revalidate (747 unique files).
All **211 selected regressions pass** in
76.392 seconds. [Evidence](GATE5-PCIE-UBUS-TRANSPORT.md).
This is implemented kernel continuation, not physical admission, final kernel
integration or Ethernet. Next genuine power/clock/shared-resource ownership,
RP1/DMA quiescence and autonomous recovery admission; raw-FDT/provider/
constructor/final-kernel integration; unused-window/RC/windows/link/config/BAR/
IRQ/DMA/GEM. Accepted zsh/socket/source/image/root bytes remain intact. No Pi,
SD/serial/power/firmware/reboot/soak action or Gate 4 waiver. Keep all original
zsh/networking/SSH/userland/recovery requirements in scope.

## Latest loader connection — exact PCIe Device declarations, 2026-10-12

A distinct uninstalled loader candidate now inserts exactly five Device pages
for the three real PHY transport resources, after strict raw-FDT decoding.
Original records/kernel/root are preserved; original-object and patch-disabled
replays reproduce the entire tested boot image. Four focused tests pass,
including actual Apple-tree encoding/kernel-map decoding and failure boundaries.
The new call-chain bound leaves 4,128 bytes without relaxing the stack margin.
All 207 selected regressions pass in 79.855 seconds; candidate/PHY input and
generated pins revalidate without changing the accepted zsh/socket image.
[Artifact and precise limits](GATE5-PCIE-DEVICE-HANDOFF.md).
This closes the software declaration gap, not physical mapping or hardware
permission. Next genuine retained power/clock/shared-resource and RP1/DMA
quiescence/recovery admission; intentional provider/FDT/constructor/final kernel
integration; then actual UBUS/RC/unused-window/windows/link/config/BAR/IRQ/DMA
and GEM Ethernet. No registration/activation of the PHY object, staging,
serial/media/power/firmware/reboot/soak operation or Gate 4 waiver occurred.
Keep the real zsh/socket/SSH/userland workstreams and full objective intact.

## Latest implementation — real PCIe PHY kernel transport, 2026-10-12

The initial reset/calibration/SerDes cores now have real IOKit Device mapping,
ordered volatile access, timing and the actual diagnostic watchdog callbacks
in a separate, uninstalled kernel object. Four focused tests pass (206 modeled
guard failures), eight units compile warning-free, and original PCI/PM objects
partially link. All **193 selected regressions pass** in 59.604 seconds.
[Exact scope, artifact and remaining admission](GATE5-PCIE-PHY-TRANSPORT.md).
The current handoff does not declare these Device pages and is intentionally
rejected. Next: distinct exact-page loader integration; actual inherited
power/clock/shared lifecycle and RP1/DMA quiescence; independently admitted
reset timing/SSD return; then UBUS/RC/unused-window/link wiring and concrete
original-family config-write/BAR/IRQ/DMA ownership. Do not convert FDT numbers,
provider-open or local COMPLETE state into hardware permission. No final kernel,
attachment, RP1 link, NIC or Ethernet claim; no SD/serial/power/firmware/reboot/
soak change. Fresh SSH returned No route to host, not proof of boot state.
Preserve real zsh/socket evidence, SSH work and Gate 4's separate hold.

## Latest prerequisite — PCIe diagnostic watchdog owner, 2026-10-12

A separate opt-in real pexpert owner now linearizes watchdog servicing versus
one diagnostic claimant, preventing other CPUs/callouts from feeding after
the claim. It uses the existing validated PM mapping, one 15-second reload,
12-second access deadline and >2-second hardware margin; no renewal/cancel/
release or reset-route/boot-order write. Actual kernel compile/partial link and
all 189 selected regressions pass. [Evidence](GATE5-PCIE-WATCHDOG-OWNER.md).
Not yet a full kernel, physical reset/return receipt or concrete PCIe owner.
Next connect actual Device/power/clock/shared-resource/lifecycle ownership and
phase-specific config/resource policy to this lease, qualify opt-in family/
constructor registration, then admit a single protected physical RP1 trial.
No accepted image/source, SD/serial/power/firmware change, reboot or soak.
Current OS/root is unverified after SSH timeout; no hardware state is inferred.
Zsh/socket evidence, SSH workstream and Gate 4's separate hold remain intact.

## Latest software checkpoint — original PCI resource integration, 2026-10-12

An abstract original-family resource bridge now registers allocator windows in
PCI bus space, translates original address properties to CPU descriptors, and
requires live owner BAR/mapping admission and local quarantine. A separate
BCM-only configurator adaptation handles allocated base zero and original
Bar64 tags without changing accepted/pristine sources. Actual A76/header/family
relocatable linkage and all 161 selected regressions pass; 16,384 native
original-type address cases execute. [Evidence](GATE5-APPLE-PCI-RESOURCES.md).
This is not a concrete provider, final kernel/registration, MMIO, physical BAR
readback, IRQ/DMA/NIC or Ethernet milestone. Next implement the actual Device
owner with power/clock/shared lifecycle/recovery and phase-specific config
write/resource policy, then opt-in registration and admitted RP1 bring-up.
The physically proven zsh/socket package stays untouched; no new reboot/soak
or Gate 4 waiver. Original SSH dependency work remains independent.

## Latest checkpoint — mounted-root/socket trial, 2026-10-12 21:53 UTC

The distinct v2 identity/socket package has now passed protected installation,
one software boot and independently replayed physical runtime root identity,
original zsh and Unix/UDP/TCP loopback payload tests. All 157 selected regressions
pass. Serial is released and the Pi is left in XNU recovery. Next advance
concrete PCIe/RP1 provider integration and original SSH build/runtime
dependencies without an immediate manual restart. Do not waive the historical
strict failed mount-line trial. The devfs overlay is checked separately from
the covered RAM-root `/dev` record. No new soak, manual cold cycles, Ethernet
claim or Gate 4 exit. [Evidence](GATE6-SOCKET-IDENTITY.md).

Updated 2026-09-04 after Astra's architecture review. This supersedes the
original ordering of SMP before the first RAM-backed userspace process.

## Objective and scope

PCI configuration continuation 2026-10-12: the new serialized root/RP1
config core now connects to all six original IOPCIBridge virtual accessors
through a compiler-enforced abstract subclass. Strict A76/family linkage and
140 selected regressions pass, with original type/offset helper execution,
W1C subword/failure/concurrency coverage. [Evidence](GATE5-APPLE-PCI-CONFIG.md).
No concrete provider or hardware caller; next implement Device/power/clock/
lifecycle/recovery ownership and original-family resource translation/final
registration, then admitted RP1/IRQ/GEM/PHY/DMA/IONetworkingFamily/wire trials.
Fresh verified SSD Linux and exact unmounted card identity are available.
Independently prepare the socket install/identity-framing trial with fresh
FAT/probe/snapshots and all 40 historical artifacts; recorder before reboot.
No current-image changes, new manual restart/soak or Gate 4 waiver.

Apple PCI family header integration 2026-10-12: the eleven source entries
of the pinned original kext target compile with actual Pi XNU headers and
actual IIG-generated interfaces. A separate copy needs a BCM-only DART
exclusion and two return-type fixes; the pristine baseline failure is retained.
Relocatable family linkage passes, not final kernel/ABI/runtime acceptance;
`___dso_handle` remains outside the reference-kernel symbol inventory.
[Evidence and next integration sequence](GATE5-APPLE-PCI-BUILD.md).
All 135 selected regressions pass. Next implement the BCM root-bridge backend
against the real original interfaces and qualify final-link/constructor/family
registration, independently of hardware provider/recovery admission. Only
then stage admitted access/bring-up, observe/assign RP1 resources and continue
interrupts/GEM/PHY/DMA/IONetworkingFamily/wire tests. No accepted image changes,
manual reboot/soak request or weakening of Gate 4.

Apple PCI allocator continuation 2026-10-12: original pinned `IOPCIRange.cpp`
and declarations cross-build unchanged for A76 with a small RP1 BAR-candidate
adapter. Original-code sanitized fragmentation/translation tests and all 130
selected regressions pass. [Source and evidence](GATE5-APPLE-RANGES.md).
No hardware caller or whole-family compatibility claim. Continue actual
provider/recovery/access admission and IOPCIFamily enumeration/configuration;
only real BAR programming/readbacks may authorize resource reconciliation.
RP1 interrupts, GEM/PHY/DMA, IONetworkingFamily and wire tests remain required.
Known-good zsh/socket artifacts and the separately held Gate 4 stay unchanged.

Socket data-path continuation 2026-10-12: the separate read-only local helper
and A76 package implement Unix-socket/UDP/TCP payload, partial-I/O and half-close
diagnostics. Native Mac data paths and 448 failure positions pass; all 127 selected
regressions and 34 package checks pass. Accepted kernel/recovery/zsh/Apple tools
are preserved. **Not staged or Pi-executed.** [Evidence and next steps](GATE6-SOCKET-DIAGNOSTIC.md).
Next close post-mount identity framing and baseline-aware protected installation
when SSD Linux is verified, then one bounded socket trial. Continue actual
PCIe/RP1/NIC integration independently; loopback is not Ethernet/SSH, and Gate 4
durability stays held. No new manual restart/soak request.

Apple networking userland physical continuation 2026-10-12: upstream-placed
ifconfig lists loopback/exit zero; route opens its routing socket and reaches
usage/expected exit 64. zsh script/recovery pass. The separate same-boot
diagnosis does not waive strict mount-marker failure, establish Ethernet or
packet traffic, or close Gates 5/6. [Evidence](GATE6-APPLE-NETWORK-PHYSICAL.md).
Next continue PCIe/RP1/NIC and bounded socket data-path work; fix post-mount
identity framing without repeated lucky-boot requests.

Filesystem convention requirement 2026-10-12: follow Darwin/macOS placement and
each pinned Apple component's install settings. New ifconfig/route additions
use `/sbin`; preserve accepted images and historical receipts. Track bootstrap
exceptions explicitly; `/private` aliases, writable state and ownership need
real filesystem support, not cosmetic directories. See
[filesystem contract and migration sequence](FILESYSTEM-CONVENTIONS.md).

Apple reuse-first continuation 2026-10-12: follow the user's explicit request
to reuse applicable Apple open source before writing replacement utilities or
generic PCI/network infrastructure. Physically accepted zsh already uses Apple
source. A distinct unstaged Pi RAM root now adds unchanged original Apple
ifconfig/route with exact source/build/archive/constructor evidence; no VM init,
kernel, disk or shutdown imports. [Reuse policy and next utility work](GATE6-APPLE-TOOLS.md).
Next close actual Pi command ABI/socket/ioctl contracts and a bounded read-only
trial; select file_cmds/shell_cmds next rather than rewriting those commands.
Choose compatible IOPCIFamily/IONetworkingFamily for generic infrastructure,
retaining labeled BCM2712/RP1-specific backend work. No Pi/runtime/ABI/network
acceptance is inferred from source availability, VM execution or preparation.

Gate 5 RC continuation 2026-10-12: implemented root misc/class/endian/16-bit
ASPM/clock-PM setup, calling the actual window core and bound as a prerequisite
of link startup. Sanitized RC/window/UBUS/link composition plus all 146 new
callback-failure positions and freestanding A76 combined linkage pass.
[RC checkpoint](GATE5-RC.md). Not hardware-wired; actual provider/ownership,
unused-window safety and bounded reset/one-shot recovery destination remain
before physical integration. Existing zsh and access packages stay unchanged.
Full zsh/TTY, Ethernet, sockets/SSH, original-source utilities and recovery
remain active alongside the independently held Gate 4 durability test.

Gate 5 actual-access continuation 2026-10-12: a distinct standalone early ARM
image now implements actual ordered 16/32-bit reads of the exact bridge/reset/
RESCAL allowlist, two-pass logging, primary/FDT/PM prerequisites and fatal-only
watchdog handling. Candidate `pcie-access-vo0exx93` passes 15 local package checks
and the 92-test regression group. [Actual code, candidate and limits](GATE5-ACCESS.md).
It is not installed/Pi-executed and explicitly not hardware-admitted. Recorded
`BOOT_ORDER=0xf461` is SD-first; a watchdog reset must not be treated as automatic
SSD rollback. Next close the bounded reset/one-shot destination and protected
installer/recorder boundary, then physically observe accessibility before any
PCIe mutation. Actual power/clock/shared ownership, unused windows and RC setup
remain needed before composing the reset/calibration/window/SerDes/UBUS/link
components. Existing zsh image/source/root are preserved and all 37 checks pass;
fresh SSH returned No route to host, so no SSD return is assumed. Full userland,
Ethernet, sockets/SSH, utilities, recovery and separately held durability remain
the objective; no serial/media/firmware operation or new restart/soak occurred.

Gate 5 link continuation 2026-10-12: the fixed Gen2/x4 diagnostic link-start
component is implemented and locally checked, including actual 16-bit control
transactions, RC/profile admission, ordered PERST release, measured settling,
bounded polling, degraded-link observations and final-state verification.
All 21 arrival paths and 1,701 callback-failure positions are modeled; A76
compilation and the 90-test regression group pass. It is not in actual builds
and is not a trained-link/RP1/NIC claim. [Link checkpoint](GATE5-LINK.md).
Next close actual Device/power/clock/shared ownership and fault/watchdog recovery,
unused-window safety and RC misc/class/endian setup, then compose the existing
components in a distinct preserved-baseline hardware trial. The accepted zsh
image remains unchanged; all 37 package checks pass. Fresh SSH timed out, so no
SSD return or new hardware trial is assumed. Full zsh/TTY/runtime, Ethernet,
socket/SSH, utilities, recovery and separately held durable storage remain in
scope. No new cold boot/soak or user action was requested.

Gate 6 physical continuation 2026-10-12 19:03 UTC: the prepared metadata
correction is installed and passes a strict fresh-boot physical trial plus
independent raw replay. The original script now succeeds with exit zero;
stat/lstat/fstat, interactive zsh builtins/external exec and live recovery pass.
All 32 historical NVMe backups and fresh protected snapshots were verified;
one armed software SD reboot, no cold cycle/soak, HFS mount or firmware edit.
[New physical baseline and evidence](GATE6-METADATA-PHYSICAL.md). Current image
`35260343...`, full FAT `18b6fdf8...`; prior failures stay historical failures.
No full Gate 6/network/durability exit. Continue broader TTY/runtime compatibility,
PCIe provider/link/RP1 IRQ/DMA/Ethernet, socket/SSH closure and RAM-root tools.
Last proven OS is XNU recovery; old staging profiles must not be rerun against
the new baseline. The held storage gate remains independent of development.

Gate 5 continuation 2026-10-12: PCIe2 window planning/programming now implements
the two outbound and three inbound declarations, explicit known four-byte
padding policy, ordered writes, targeted/final readbacks and no-retry quarantine.
All 87 selected host regressions pass; actual FDT-decoder composition and A76
target compilation are included. This is not hardware integration or Ethernet
acceptance. Close actual accessible Device/power/clock/shared ownership,
fault/watchdog handling and unused-window safety before composing RC/misc,
windows, SerDes/UBUS and bounded PERST/link setup in reference order.
[Window checkpoint](GATE5-WINDOWS.md). Fresh SSH times out; no board/media action.
Corrective zsh package remains unchanged with all 37 checks passing; its real
metadata/script trial still requires verified SSD Linux and exact baseline
staging. Gate 4 remains independently held, not a global development hold.

Gate 5/6 continuation 2026-10-12: independent corrective-zsh byte replay now
verifies package/receipt binding and all original-script/interactive/recovery
evidence, with mutation tests rather than recorder-status trust. UBUS/AXI
post-SerDes defaults are implemented/tested for both hardware timing-bit
profiles, including all callback failures and target compilation. Neither is
new physical acceptance. Next verify SSD Linux before any metadata staging;
continue actual Device/power/clock ownership, RC/windows and bounded PERST/link
integration for networking. [UBUS](GATE5-UBUS.md),
[metadata](GATE6-METADATA-CORRECTION.md). No board/media operation; Gate 4 remains
held and does not globally block these workstreams.

Gate 6 staging/recorder continuation 2026-10-12: a distinct current-baseline
installer now preserves the 32-artifact chain and fresh protection snapshots;
a combined bounded recorder demands exact fresh copy/mount admission, actual
raw metadata success, original script success and interactive zsh/live recovery.
Neither is Pi-executed. Finish independent transcript auditing, then stage only
after fresh SSD Linux/card verification. SSH still times out; board/media remain
untouched. Gate 4 is not waived and networking work remains independent.
[Current correction checkpoint](GATE6-METADATA-CORRECTION.md).

Gate 6 corrective preparation 2026-10-12: distinct package `bl33-probe-wdmzdtem`
passes 37 host checks with the unchanged diagnostic root/frozen zsh and preserved
corrective kernel. Actual linked VFS getter and storage-off SD entry guard are
verified, with seven new focused rejection tests. Not installed or Pi-tested;
no original failure is waived. Next prepare a current-baseline installer and
distinct finite recorder, then physically test metadata and original script
acceptance once SSD Linux is verified. No new kernel/VM build or board action.
[Correction checkpoint](GATE6-METADATA-CORRECTION.md). Independent networking and
RAM-root work continue; replacement-card durability remains separate.

Gate 6 continuation 2026-10-12 18:02 UTC: the raw-file diagnostic was installed
with 28 historical backups verified, and one software SD boot reached recovery.
The strict root-marker trial stopped safely with zero TX after SMP logging tore
the mount line; it remains failed. A separately guarded same-boot diagnosis
completed: actual stat/lstat/fstat return ENOTSUP with untouched buffers, while
plain/NOCTTY open, F_DUPFD and exact shared-offset reads work. Actual old-kernel
inspection finds the missing VFS getter; a preserved corrective kernel already
has it. Next review/package that kernel with storage disabled, then test raw
metadata and original zsh acceptance. No fabricated types or frozen-zsh change.
[Physical diagnosis and current baseline](GATE6-STAT-PHYSICAL.md). Serial is
released; no power-cycle/soak request. Gate 4 remains held; PCIe/RP1/Ethernet,
socket/SSH dependencies, RAM-root tools and recovery work remain active.

Gate 5 SerDes continuation 2026-10-12: bounded MDIO and fixed 54-MHz setup are
implemented and compose with calibration/reset session prerequisites. All 27
focused host tests pass; no hardware integration or trained-link claim.
[SerDes checkpoint](GATE5-SERDES.md). Next provide actual power/clock/shared
ownership and Device-access/fault handling, then compose RC/UBUS/window/PERST
and bounded link training. The stat-diagnostic image remains unchanged/unstaged
and passes all 29 checks, now explicitly excluding these hardware components.
No Pi/serial/media, kernel or VM operation was performed.

Gate 5 shared-calibration continuation 2026-10-12: the one-shot RESCAL component
is implemented and host-tested, including every callback failure on all bounded
poll paths, real-time deadline checks and non-rearmable quarantine. It is not
wired into BL33/XNU or physically executed. Next close its actual shared
power/clock/Device-access provider, then SerDes/refclock and link training.
[Calibration and bridge lifecycle](GATE5-BRIDGE-LIFECYCLE.md). A fresh SSH retry
also timed out after the existing watchdog interval; no SSD return is assumed,
no media/serial/power operation was made and no current image was replaced.

Gate 6 file-diagnostic preparation 2026-10-12: the raw stat/open/F_DUPFD utility,
preserved-root build and distinct boot package are implemented and preflighted.
They are not installed or Pi-executed. Fresh SSH timed out; serial/media/power
remain untouched. Next verify SSD Linux, preserve the current zsh image through
a new baseline-aware installer, and run one bounded raw-file diagnosis. Do not
reuse old staging hashes, claim the script bug fixed or repeat a soak.
[Diagnostic artifacts and next step](GATE6-STAT-DIAGNOSTIC.md).

Gate 6 physical continuation 2026-10-12 16:40 UTC: the distinct zsh package
`bl33-probe-_qoqmu9u` is installed with all 24 historical backups verified and
fresh snapshots/current-topology recovery images preserved. One guarded software
SD boot reached zsh. The original script-file trial failed; separate same-boot
diagnostics proved actual interactive zsh 5.9, array/arithmetic, external exec,
returned prompts and exit to the live recovery shell. Do not convert that subset
into full Gate 6 exit or waive the script failure. Next capture raw stat/fstat
and open/F_DUPFD results to distinguish metadata/ABI/descriptor causes, while
independent PCIe power/clock/RESCAL/SerDes work continues. Full details and current
media baseline: [physical zsh checkpoint](GATE6-PHYSICAL-ZSH.md). Serial is released;
no repeated boot/soak or user action is required. Gate 4 durability stays held.

Independent Gate 5/6 continuation 2026-10-12 15:39 UTC: initial PCIe2 reset
control is implemented with bounded callback/failure/quarantine tests but is
not yet wired to hardware. Follow [bridge lifecycle](GATE5-BRIDGE-LIFECYCLE.md)
through power/clock/shared RESCAL, mapping, SerDes and trained-link closure;
reset release alone is not bridge/NIC acceptance. In parallel the preserved
zsh binary now has a complete static trap/decode inventory and a new Pi trial
RAM root preserving the proven init/recovery shell. See [userland](GATE6-USERLAND.md).
Neither is staged or Pi-executed. All 73 selected host tests pass; no board,
serial, SD or kernel/VM build operation occurred. Gate 4 remains blocked while
the user finds a spare SD; these independent results do not satisfy durability.

Gate 4 evidence audit 2026-10-12 15:14 UTC: [the exit audit](GATE4-EXIT-AUDIT.md)
maps every original write/persistence requirement to actual evidence. Read-only
SD/HFS operation passed; cache admission, admitted writes and post-reboot
durability remain incomplete. Primary-source review establishes no applicable
cache-off guarantee or matching Samsung workaround for this card. Do not repeat
W3/control or weaken admission. A new identified disposable card or authoritative
new cache-state evidence is required for the next Gate 4 hardware step. The
existing spare-card question remains unanswered; do not repeat it automatically.
This does not block the separately authorized Gate 5/6 work below.

Gate 5 continuation 2026-10-12 15:05 UTC: the distinct recovery-backed topology
image has now passed one physical software SD boot. The loader decoded the
**full firmware FDT**, emitted the exact expected bridge/MIP/GEM/outbound
declarations and `PASS PCIE_MMIO=0 CONFIG_ACCESS=0 DMA=0 NIC_READY=0`, then
transferred into the proven shell kernel/root. XNU reached shell-ready/prompt.
The 90-second RX-only capture finished with zero TX; no soak or cold-boot repeat.
Package `bl33-probe-28ubwa1k`, install `pcie-topology-installed-20261012`, evidence
`mac-pcie-topology-trial-20261012/validation.json`. W3 and all recovery artifacts
are preserved; MBR/HFS/config/firmware are unchanged. Pi is now in XNU, not SSH
Linux; recorder has released the Mac serial port. The existing kernel's one-hour
development watchdog still applies, without a guaranteed automatic SSD return.

Next finite step: close bridge register accessibility, clock/reset ownership
and safe mapping/lifecycle requirements before wiring the separate link/config
observer. Firmware explicitly reset PCI1/PCI2 before this handoff; do not assume
Linux's earlier trained link or programmed windows survive. Only after verified
bridge bring-up/config/BAR/window observations proceed to IRQ/DMA and Ethernet.
No further board action is needed merely to repeat today's declaration result.
Gate 4 cache admission/durability remains held; Gate 6 portability is independent.

Gate 5 continuation 2026-10-12 14:35 UTC: a fresh, boot-bound 12-node filtered
Linux topology now passes the native C decoder and agrees with the observed
RP1 BAR1 assignment in the resource planner. Default-off loader integration
`--gate5-pcie-topology` is implemented and freshly ARM-built with source/stack
evidence. It reports FDT declarations only and excludes storage trials; it
does not call the MMIO observer, access PCIe, embed a kernel or complete any
network acceptance. Its host diagnostic artifact is unstaged and placement
unverified. Next: a distinct recovery-backed boot-stage topology package, then
safe bridge mapping/lifecycle/bring-up and config observation. Keep the SD
cache/durability hold and existing VM workstream isolation unchanged.

Execution sequencing update 2026-10-12 13:40 UTC: the user explicitly requested
continued networking and other independent gates. Gate 4's **write durability**
exit is blocked on this card's cache-state evidence; this is not a global
development hold. Preserve its passed shell/SD/HFS read-only evidence and all
recovery images. Do not repeat unchanged cache trials, soaks or cold boots.

Proceed on two independent tracks: Gate 5 PCIe/RP1 discovery, bridge/IRQ/DMA and
Ethernet implementation; and Gate 6 RAM-backed static-userland portability and
dependency closure. Neither requires claiming durable SD writes. Gate 6's full
persistent distribution still requires real writable storage; SSH also needs
actual networking and its own userland/service closure. The next shared-board
trial must be separately packaged and bounded, with recovery preserved; host
progress alone is not board acceptance. See [network groundwork](GATE5-NETWORK.md)
and [Pi zsh portability](GATE6-USERLAND.md).

Gate 4 execution update 2026-10-12 13:12 UTC: automatic SSD Linux return is now
verified with new boot `36ac234c-2a31-4b30-bb5d-de87fa5bd8e2`; the original
RX capture is preserved and deliberately stopped. The single guarded Linux
CMD48 control completed, returning R1 `0x900` and the same full 512 zero bytes
as W3, while all 20 backups and full protected MBR/FAT/HFS bytes passed both
checks. This is actual independent-transport comparison, not cache admission
or durability. Linux's zero feature metadata can result from skipped extension
parsing and is not independent absence proof. Next: independent protocol/card
evidence for the malformed zero General Information response, without guessed
decoder relaxation, another unchanged W3 trial or manual reboot. The Pi stays
in SSD Linux, SD unmounted. Actual admitted writes and the entire original
reboot/fsck/RO-full-read/protection exit chain remain required and incomplete.

Gate 4 execution update 2026-10-12 12:13 UTC: W3 has now been safely staged and
physically booted once. It failed closed with zero input/batch/mount at General
Information decoding: valid SD6 SCR, completed 512-byte all-zero extension data.
Preserve the exact trace and all images/backups. Existing live RX-only/SSH handles
14191/23351 observe automatic SSD return; no manual reboot or repeated W3 trial.
Next finite action is fresh SSD/card/HFS verification, then the prepared read-only
Linux CMD48 control. Resolve actual card versus XNU transport behavior before
changing admission/decoding. All original write/persistence/protection exit
requirements remain intact and incomplete.

Gate 4 execution checkpoint 2026-10-12 06:00 UTC: actual RO SD/HFS prerequisites
remain passed. W2's write startup failed closed at cache observation with zero
serial input/no batch/no HFS mount. Preserve its original evidence and installed
FAT baseline. Continue offline exact-stage/buffer diagnostics while existing
RX-only/SSH handles 78529/58883 observe its automatic SSD fallback; no manual
restart or new soak. A successor needs a distinct fresh build/package check,
new verified SSD boot/card/full clean HFS evidence, preserved W1/W2/RO/full
backups, and an armed marker guard before one software SD reboot. Actual writes
and the complete reboot/no-repair-fsck/RO-full-read/protected-media chain remain
mandatory; host/model/synthetic Mac evidence does not complete this gate.

Build a public-source downstream XNU port for Raspberry Pi 5 Model B.
The first convincing operating-system milestone is one Cortex-A76 running XNU,
timer-driven scheduling and a minimal RAM-backed PID 1 over the debug UART.
Four-core support follows. The longer-term objective is a headless Darwin
system with SD storage, Ethernet, a shell and eventually SSH. An interactive
serial terminal does not require Ethernet: target it after Gate 3 and before
the storage/network drivers, with a deliberately small static command
interpreter in the RAM-backed image. That is a separate milestone from a
general BSD shell and SSH distribution.

Execution priority updated 2026-10-11 for the user's shell-first objective:
reuse the physically proven polling console, then verify userspace
`fork` → `execve` → `wait4` on the existing RAM-backed executable. If that
passes, implement the smallest read-only, multi-file RAM root needed to host
a static shell and utilities, then verify command execution and repeatable
cold boot on the actual 8-GB Pi. SDHCI, network, UART IRQ conversion, dyld and
full libSystem closure are not prerequisites for this bounded static-shell
path. Defer them unless a measured boot-path failure requires one. The
numbered gates below remain the broader port/qualification roadmap, not a
requirement to complete every driver before a serial shell.

Use one focused regression check and one relevant board attempt per meaningful
boot-path change; do not repeat full suites, unchanged builds or soaks without
a new hypothesis. Preserve each artifact's source revision/hashes, build
command, boot configuration and raw serial evidence. See
[the process dependency trial](PROCESS-TRIAL.md). It passed on the physical
Pi on 2026-10-11; this does not itself complete the usable-shell milestone.
Proceed to the bounded read-only multi-file RAM root, preserving the proven
single-executable RAM image path and the process-trial artifact.
The RAM-root extension passed on the physical Pi on 2026-10-11; see
[the RAM-root evidence](RAMROOT-TRIAL.md). Proceed to a static shell and
utilities, using paced automated serial input and preserving this image.
The [static shell](SHELL-TRIAL.md) passed all twelve checks on the physical
Pi after one guarded SD software boot at 19:38 UTC on 2026-10-11. External
programs, pipelines, scripts and error recovery work. The remaining shell
milestone requirement was two separately captured power-off/on cold starts
of this unchanged image. Both passed all twelve shell checks at 20:00:21 and
20:15:24 UTC, with firmware confirming power-on resets. The repeatable
interactive serial-shell objective is achieved. No further image rebuild,
SD rewrite, restart or soak is needed for this milestone. The numbered
driver/qualification roadmap remains separate future work; do not resume
its tests automatically as a prerequisite to using this shell.
The terminal's bounded watchdog window is not a guarantee of automatic NVMe
fallback: an earlier SD-inserted reset loop was captured, and the new trial
must preserve a deliberate physical recovery path.

Execution priority updated 2026-10-12: speedrun the real Apple-distributed zsh
from official Apple repositories, building only the runtime dependencies it
actually needs. Static linking is preferred where viable, rather than gating on
complete dyld/LibSystem, storage, networking or a desktop. Preserve the working
bootstrap and recovery image. Use one focused build/boot smoke check; no new
soak, repeated cold-boot campaign or broad suite unless a concrete blocking
failure calls for it. See the [PRD fast lane](DESKTOP-OS-PRD.md#fast-lane-to-zsh-2026-10-12-user-direction).

VM-only result 2026-10-12: real source-built Apple zsh 5.9 now boots into an
interactive XNU VZ prompt; version, arrays/arithmetic, an external executable,
prompt return and clean shutdown passed. Working image/provenance/launch are
preserved in [the zsh milestone](../../experiments/darwin-container/userland/ZSH-TRIAL.md).
This does not establish zsh on the physical Pi or reopen any Pi soak gate.

Native macOS builds are the initial supported workflow. The owned board's RAM
SKU is the initial hardware test configuration and must be recorded in lab
results. The lab needs a 3.3 V debug UART adapter, spare SD card, adequate Pi 5
power supply and cooling. All destructive media preparation must identify the
specific removable device before writing it.

Graphics, camera, audio, Wi-Fi, APFS and proprietary macOS components are outside
this plan. USB and GPIO drivers follow the initial storage/network milestones.
No release date is committed before build and hardware-probe feasibility passes.

## Gate 0 — build and runtime dependency closure (in progress)

1. Import Apple's history at `xnu-12377.121.6`, commit
   `ac9718fb1af618d5ce8678d0dc6e8a58f252216f`. Keep upstream notices intact.
2. Lock matching AvailabilityVersions and libdispatch sources; record toolchain
   versions and hashes. Use a project-owned SDK copy; never modify Xcode's SDK.
3. Add an independent BCM2712 board and MASTER configuration. Use plain arm64,
   Cortex-A76, 16 KiB pages, 40-bit PA and explicit feature selections. Audit
   Apple register, PAC, BTI, range-TLBI and coherent-I/O assumptions.
4. Remove the Pi target's KDK archive dependency. Keep unresolved symbols fatal;
   inventory required compiler builtins and build their real implementations
   from licensed sources. Build libfirehose from the matching release.
5. Inventory initialization providers as well as link inputs: entropy, PRNG,
   crypto, AMFI/Image4, platform expert and CPU services. Record source provenance,
   initialization order and any development-only adaptation explicitly.
6. Produce and inspect a complete DEVELOPMENT kernel: instruction compatibility,
   generated config, no arm64e or KDK inputs, load commands, segment layout,
   entry point, fixups, symbols and build provenance. No dummy provider stubs.

Exit: complete inspected kernel artifact and a reviewed provider/loader contract.
A successful configuration probe or host-tool build alone does not pass Gate 0.
RELEASE remains unsupported while development-only boot policies are required.

Current execution order within Gate 0: close startup providers after successful
incremental and fresh-kernel-output builds -> complete
instruction/relocation and loader-contract inspection -> reproducible build
verification. Firehose has been rebuilt for the selected configuration.
BCM2712 DEVELOPMENT explicitly does not support profile extraction or zone
reachability scanning; these APIs return unsupported errors, not success stubs.
See [closure worklist](GATE0-CLOSURE.md).
The [provider startup contract](PROVIDER-STARTUP.md) requires crypto registration
before PRNG registration: entropy initialization already consumes SHA-512 through
the registered crypto table. A standalone DRBG is insufficient.

Source-selection revision: the DEVELOPMENT kernel includes the public IP/NECP/
traffic-management core because socket/FIFO implementation in this snapshot
depends on it. This does not add a Pi NIC driver or move Ethernet hardware
validation ahead of Gate 5. A sockets-only build was investigated and found to
require extensive protocol separation; it is not the baseline being pursued.

## Gate 1 — standalone firmware/loader hardware probes

Use Pi firmware -> TF-A BL31/PSCI -> small BL33 loader -> XNU.
Pin firmware and TF-A source commits before producing the first boot medium.
The loader may prefix a composite `kernel_2712.img`; the container format must
have a versioned manifest, checked lengths, offsets and hashes.

- Consume the runtime FDT, including reserved memory and address translations.
  Construct an Apple flattened device tree with the semantics XNU expects.
- Print CPU identity/features, exception level, firmware identity, RAM ranges,
  UART configuration and FDT diagnostics before transferring control.
- Normalize TF-A's EL2 entry into EL1: timer access/offsets, traps, MMU/cache
  state, vectors, stacks and instruction visibility. Do this for secondaries too.
- Implement exception diagnostics, GICv2 Group 1 IRQs, virtual timer INTID 27
  and PSCI secondary probes. Discover GIC CPU target bits; Aff0 is not a usable
  target index on this board.
- Load a defined thin Mach-O kernel contract. Start with zero virtual KASLR;
  check physical/virtual L2-block compatibility (32 MiB for 16 KiB granules),
  segment bounds, zero-fill, entry/fixups and bootstrap page-table capacity.
- Initially expose a bounded contiguous reservation-free RAM extent. Cover
  loader-owned boot data, Apple DT and init image with `topOfKernelData`.
- Supply at least 256 bytes of fresh boot seed and identify its actual entropy
  source. Never package a fixed seed as a runtime solution.
  Approved source adaptation: a fresh 64-byte firmware HWRNG seed may feed
  domain-separated HKDF-SHA256 to produce that 256-byte interface buffer.
  Derived size is not an entropy claim. Require runtime source/version and
  ownership validation, one-time consumption/erasure, published-vector tests
  and explicit firmware-trust assumptions before deployment.
- Preserve/verify UART10 baud and clock setup or program them explicitly.

Exit: raw serial evidence of all probes on the actual board, including consistent
EL1 state and timer IRQ delivery on every CPU. QEMU virt only tests shared
contracts; it does not validate BCM2712, the Pi affinity layout or RP1.

## Gate 2 — single-core XNU and RAM-backed PID 1

Integrate early UART, platform services, exceptions, VM and timer IRQ handling.
Keep timer accounting and preemption correct when adapting the existing FIQ
timer path to GICv2 IRQ delivery. Initialize real PRNG/crypto services before use.

Use DEVFS and MOCKFS with `rd=md0 launchdsuffix=release`. Supply a raw static thin
ARM64 Mach-O through `/chosen/memory-map/RAMDisk` (two little-endian uint64 values:
physical address and byte length). Align/pad to 16 KiB and reserve its memory.
Require LC_UNIXTHREAD, no dyld/imports/undefined symbols and no code signature.
Resolve the mockfs fast path's page-unit, address-width and address-space defects
end to end; first investigate disabling that optimization in favor of ordinary
paging. A page-shift-only patch is insufficient.

Scope any AMFI/Image4 adaptation to BCM2712 DEVELOPMENT with explicit policy and
tests; do not label bypasses production security. PID 1 opens `/dev/console`,
verifies its PID, emits `XNU-RPI5 USERSPACE PID1 OK`, then remains alive. Verify
timed syscalls and scheduler activity, not just one printed line or a busy loop.

Exit: reproducible one-core boot, working console/syscalls/timers and surviving
PID 1; archive kernel, dSYM, link map, source revision and raw serial logs.

## Gate 3 — SMP correctness, then stability

Implement IOKit CPU registration/lifecycle, PSCI reset trampoline and physical
CPU-data handoff, SGI/IPI delivery and TLB shootdowns. Preserve Aff1 in CPU lookup
without treating affinity IDs as shared-cache topology. Audit HAS_CLUSTER with
NO_CPU_OVRD and all Apple-specific cluster paths. Test synchronization and cache
visibility across four cores before enabling power-management features.

Exit: four-core concurrency and cross-core invalidation tests, applicable XNUPOST
tests, then 20 consecutive cold boots and an eight-hour timer/IPI/SMP soak.
Use serial `RPI5XNU:<stage>:PASS|FAIL` markers and preserve unfiltered logs.

Development sequencing exception (operator decision, 2026-09-27): after three
same-image power-off boots pass the combined pre-soak checks, begin the
serial-terminal milestone without demanding 17 more manual power cycles now.
This is permission to advance development, **not** Gate 3 exit or release
qualification. Keep the remaining cold-boot streak and final unchanged-image
eight-hour soak on the verification backlog; revisit them if instability
appears and before claiming the formal Gate 3 exit.

## Serial-terminal milestone — after Gate 3, before network

Add RX and interrupt-driven input to the existing debug UART path, connect it
to a usable console/TTY interface, and start a small static RAM-backed command
interpreter with a prompt and bounded built-in diagnostics. Verify input,
editing, output, repeated commands and recovery over the debug probe on the
actual Pi. This gives a usable interactive XNU terminal without waiting for
PCIe, RP1, Ethernet, IP or SSH. It is not yet a general BSD shell: file-backed
executables, process launching, a real filesystem and broader userland remain
separate work. This milestone must not dilute Gate 3's SMP exit tests.

Development status (2026-09-28): the PL011 driver already has a receive path,
and XNU's `serial=3` enables its existing serial keyboard poller and
`/dev/console` TTY input. A separate static `tools/rpi5/pid1_terminal.S` image
now builds with `tools/rpi5/build_pid1.py --source` and provides a bounded
prompt plus `help`, `status`, `ticks`, and `echo` commands. A guarded Pi/Mac
Debug Probe trial verified both UART directions and the console TTY. The
qualification image still uses `serial=1`, and the terminal image still polls
for input rather than using a UART interrupt. Preserve the qualification image
while developing the shell path. UART interrupts remain a later opt-in
improvement, not a blocker for userspace command execution.

The initial opt-in image was `build/rpi5/bl33-probe-ddkxb8_8/probe.bin`
(SHA-256 `e01a90bb18b1210661ac26398b55a144956faeb8570b971cbdfbf0ae0f23b48f`).
Its manifest records `serial_terminal=true`, the unchanged Gate 3 kernel hash,
and a separate terminal RAMDisk; the embedded boot command uses `serial=3`.
It was staged on the disposable `XNU_PROBE` SD partition, distinct from the
preserved Gate 3 baseline.
`tools/rpi5/serial_terminal_trial.py` now offers a bounded acceptance capture:
it sends no bytes until it sees this PID 1 image's unique banner and prompt
plus XNU's `Serial keyboard started` marker (in either startup order),
then checks help, status, echo, TTY erase editing, unknown-command handling,
repeated-command recovery, and two `ticks` responses. The `ticks` command
prints `CNTVCT_EL0` and `CNTFRQ_EL0` in fixed-width hex; the trial requires
the counter to increase at a stable nonzero frequency. This is monotonic
diagnostic time, not a wall clock or RTC test. It passed simulated-serial tests
and the guarded Pi/Mac Debug Probe trial.
The counter read is statically supported by this kernel's boot path:
`arm_init` calls `wfe_timeout_init()` on the boot CPU and on secondary/idle
CPU initialization; that sets `CNTKCTL_EL1.PL0VCTEN` when
`user_timebase_type()` is not `NONE` (the BCM2712 path returns `SPEC`). This
permits EL0 reads of `CNTVCT_EL0` and `CNTFRQ_EL0`; the Pi trial confirmed
that the command does not fault and the values advance.
The editing probe sends DEL (`0x7f`): this tree's `CERASE` default is octal
`0177`, and the arm console's `kmopen` installs it through `termioschars`.
`TTYDEF_LFLAG` includes canonical input and echo, so the prompt can read
edited lines from `/dev/console` once the serial keyboard poller is live.

UART RX interrupt contract, still pending: the pinned firmware DTB's
`serial@7d001000` node declares `interrupts = <0 121 4>` (GIC SPI 121,
absolute INTID 153, level-high). This is static binding evidence, not a
runtime IRQ test. The generated Apple device tree currently carries only the
UART's compatible, register window, and phandle; this tree also has no
`AppleSerialShim` implementation to register the PL011 interrupt with the GIC.
The opt-in terminal loader now also validates the exact UART/GIC interrupt
tuple and inherited parent against the runtime firmware DTB; it prints
`UART_IRQ_BINDING SPI=121 INTID=153 NOT_ENABLED` only on a match. Host mutation
tests reject changes to each tuple byte, parent phandle, and cell count. This
still does not prove IRQ delivery or authorize enabling it: the BCM2712 XNU
handler currently accepts only timer IRQ 27 and IPI 1 and panics on IRQ 153.
First verify physical RX and the TTY through `serial=3` polling on a separate
development boot. Then implement and test the GIC/PL011 registration, mask,
acknowledge, bounded drain, and wakeup path against the runtime interrupt
binding before removing the poller. Do not conflate polling success with the
interrupt-driven exit condition.

Physical connection check: Raspberry Pi's documentation identifies Pi 5's
dedicated `UART` header as UART10, and the Debug Probe's `U` port as the UART
bridge. Its keyed three-pin JST-SH-to-JST-SH lead connects both UART directions
and ground when used on those two ports. For separate header leads, probe TX
(orange) goes to Pi RX, probe RX (yellow) to Pi TX, and GND (black) to GND.
The existing receive-only capture proves only Pi TX to probe RX. Confirm the
other direction by typing through the guarded trial, not by assuming it from
the cable's presence. Sources: Raspberry Pi's
[Debug Probe guide](https://www.raspberrypi.com/documentation/microcontrollers/debug-probe.html)
and [Pi 5 UART documentation](https://www.raspberrypi.com/documentation/computers/configuration.html).

The operator ended the non-qualifying soak tail early and moved the Debug
Probe's USB cable to the MacBook, leaving its `U` cable on the Pi. The partial
capture is preserved under `build/rpi5/gate3-partial-tail-20260927/`.
After a controlled SD-removal boot, Linux root was verified as
`/dev/nvme0n1p2` and the reinserted disposable card as `XNU_PROBE` on
`/dev/mmcblk0p1`. Its Gate 3 image hash matched
`454906aa802f013549ef936a9d15bcc42b10638ed73d6759a276797737b1d06c`.
That image is preserved both on NVMe and on SD as
`probe.gate3-20260927.bin`; the original `probe.before-register.bin` backup
also remains. The separate terminal artifact passed all twelve host package
checks and is now the SD `probe.bin` at SHA-256
`e01a90bb18b1210661ac26398b55a144956faeb8570b971cbdfbf0ae0f23b48f`.

The first marker-guarded Mac trial captured XNU, all four CPUs online and
`Serial keyboard started`, but concurrent UART output tore the one-time
terminal banner/prompt. It correctly transmitted zero bytes. A revised guard
uses the terminal-only loader marker and a bounded echo probe after the
keyboard marker; its host tests pass. The second trial captured zero bytes
because the macOS serial port stalled during setup, then received nothing.
Its result does not establish a terminal failure. After the operator
reconnected the Debug Probe USB cable to the Mac, a receive-only Pi Linux
test captured the exact marker `RPI5_MAC_UART_TEST_20260928`. A third guarded
boot passed all ten terminal checks in
`build/rpi5/mac-terminal-trial-replug-20260928/`: loader and keyboard markers,
wake echo, help, status, increasing `ticks` at 54 MHz, echo, DEL editing,
unknown-command handling, and repeated-command recovery. Its 31,894-byte
raw serial capture has SHA-256
`f26cdd7709d1e47a7ec84a18cd8919a9deb21cde147962b5a2e72708d69835c9`;
97 bytes were transmitted only after the terminal-specific markers. This
proves an interactive XNU serial terminal on the actual Pi. It does not prove
a durable unattended session: the current development watchdog stops reloads
after about 120 seconds, and the Pi subsequently returned to NVMe Linux.
Extend that window only for a separately identified terminal development
image while preserving a bounded watchdog fallback. Then separately implement
UART IRQ-driven RX; polling success is not the interrupt-driven exit.
Do not connect the probe's `D` connector or send input to the old Gate 3 image.
Formal Gate 3 qualification remains open.

Terminal longevity follow-up (2026-09-28): a first one-hour watchdog image
accidentally omitted the port's required crypto and pthread provider build
flags and panicked during early XNU initialization. The corrected
provider-enabled image reached the prompt and passed the same ten interactive
checks, but returned to NVMe Linux soon afterward. This suggests the CPU 0
timer-IRQ path alone is not a reliable watchdog service while PID 1 blocks for
input; it does not by itself prove which watchdog fired. A new terminal-only
kernel uses a one-second delayed thread call to reload the PM watchdog while
the bounded one-hour window is active, leaving Gate 3 soak and the default
120-second policy separate. Its host tests, provider-enabled kernel build and
12-case package preflight pass. The staged SD `probe.bin` is
`build/rpi5/bl33-probe-tr2bpvqv/probe.bin` (SHA-256
`a4fb01fcee8724cd68b5a162b77c80e72880a2afba0db9366fda9d7371d8ca53`);
the Gate 3 baseline remains preserved. The first board boot with this image
has not produced trustworthy serial evidence: two Mac receive-only windows
captured zero bytes even though the Debug Probe USB device remained enumerated.
No input was sent. Pi Linux is not reachable, which is consistent with XNU
running but not proof of it. Restore/verify the Mac probe receive path before
claiming a successful callout or late interactive check; do not repeat a
Gate 3 qualification soak merely to test the terminal.

Debug Probe recovery (2026-10-11): the Mac previously reported probe firmware
1.01 (`bcdDevice=0x0101`). After the operator placed the separate probe in
BOOTSEL mode and unlocked the Mac, its `RPI-RP2` update volume was identified
as an RP2040 bootloader. The official Raspberry Pi `debugprobe.uf2` v2.3.1
(SHA-256 `aae9585f456c28c00865eb3df4d4bfc184f8e7ae60ebed3cc32a32512521a1b8`)
was installed; the same probe serial `E66480454F719939` re-enumerated with
`bcdDevice=0x0231` and `/dev/cu.usbmodem102`. No Pi disk was written or Pi power
changed by this update. A fresh receive-only window opened without the previous
setup stall and captured a readable `TERMINAL:WATCHDOG_KICK RELOADS=1` marker
in `build/rpi5/mac-probe-v231-live-20261011/`; the subsequent 180-second
receive-only window in `build/rpi5/mac-probe-v231-watchdog-20261011/` captured
`RELOADS=12`, `24`, and `36`, with no reboot markers and zero transmitted bytes.
Its 129-byte raw capture has SHA-256
`0454245fae45c4daea0ae09800e05e6f421e4a530a4c35ac6d0ddb8e33655e09`.
This establishes readable board output and watchdog
activity, not a complete boot transcript, a fresh interactive-terminal pass,
or proof that old firmware was the sole cause of the earlier serial failure.
The terminal package still passes all twelve identity checks against the
preserved Gate 3 baseline. These are host checks, not fresh board acceptance.
Before sending acceptance commands, start the marker-guarded trial before a
controlled boot so it observes the terminal loader and keyboard-start markers
in that same serial session. Do not replace those guards with watchdog markers.
The late interactive check now waits at least 180 seconds after the initial
command checks pass, not after opening the recorder: operator reboot delays
must not count toward terminal longevity. Two additional host tests verify
that anchor and that failed initial acceptance cannot initiate late input.
The first guarded trial (`build/rpi5/mac-terminal-v231-20261011/`) reached its
600-second deadline before the operator's restart; it recorded watchdog
reloads through 192, but no startup markers and zero transmitted bytes. A
receive window opened after the restart saw fresh reloads 1, 12, and 24, but
also missed the one-time startup markers. It was stopped without transmitting.
These are missed-startup captures, not successful command trials or evidence
that PID 1 failed. The runner now separates a receive-only operator boot wait
(`--boot-wait-seconds`, bounded to 30–3600) from the initial-command timeout
and the post-acceptance longevity delay. Two more tests cover that separation
and its forwarding; the full 295-test host suite passes. The replacement
trial uses `--boot-wait-seconds 3600 --seconds 180 --late-check-seconds 180`
under `caffeinate -i` in `build/rpi5/mac-terminal-v231-longwait-20261011/`.
It must observe both boot markers before transmitting; waiting for an operator
restart does not count as soak time or terminal acceptance.

Fresh hardware acceptance (2026-10-11): the replacement guarded trial observed
the operator's controlled SD boot, the terminal-only loader IRQ-binding marker,
`Serial keyboard started`, and CPUs 1, 2, and 3 online alongside the boot CPU.
Interleaved SMP logs tore the first prompt, so the terminal-only wake echo
recovered it. All eleven checks passed: the ten initial marker/command checks
plus a late echo at least 180 seconds after initial acceptance in the same
serial session. `ticks` advanced at a stable 54 MHz; DEL editing, unknown-command
recovery, and repeated status commands passed. Watchdog reload markers 1, 12,
24, and 36 preceded the successful late echo, with no intervening reboot marker.
The raw 31,912-byte capture in
`build/rpi5/mac-terminal-v231-longwait-20261011/serial.bin` has SHA-256
`f83420c5aa17df11770b814e7062fa90c305c5a7b9941f251a799dd44cdcfc74`;
its `state.json` records `status=passed`, all eleven checks, and 127 transmitted
bytes. The runner finished and released the port. This is fresh board proof of
the polling serial terminal and responsiveness beyond the old reset window;
it does not prove the entire one-hour policy, UART IRQ delivery, or Gate 3
qualification. The terminal remains a minimal PID 1 interpreter (`help`,
`status`, `ticks`, `echo`), not a general BSD shell. The development watchdog
still deliberately bounds this image to about one hour before fallback.
Formal Gate 3 qualification remains open.

## Gate 4 — SD and a real root filesystem

Active as of 2026-10-11 at the user's request. See
[Gate 4 implementation and evidence](GATE4-STORAGE.md) for the pinned
components, SD binding/PIO transport, fresh opt-in storage/HFS kernel link,
and remaining hardware/integration exit checks. The proven shell image is
preserved. Physical adapter trials have reached XNU and the RAM shell but
not yet SD reads: the initial configuration-parser fault is fixed, and the
register-diagnostic boot identified an incorrect whole-power-byte readback
requirement: bus power cleared while 3.3-V voltage selection stayed latched.
The power-enable-only correction preserves voltage selection and external
rail guards, and passes native fault tests. Its fresh kernel links successfully;
the separate SD-only package `bl33-probe-unsh3788` passes 22 preflight checks
and was staged after fresh SSD-root, card, backup and before/after sector checks.
The marker-guarded recorder was armed before a one-shot SD software reboot at
23:51:19 UTC. It exited at 2026-10-12 00:00:43 UTC with zero received/transmitted
bytes and no reads. Actual boot and physical reads remain unconfirmed; this is
an inconclusive observation, not a diagnosed SD-driver failure. The probe was
USB-present; a UART-lead check and physical restart were requested but not yet
confirmed. No second trial is started automatically after timeout. Resume on
confirmed hardware/connectivity state with a recorder armed before the boot.
The user has since confirmed a restart and reported an SD boot; the separate
one-hour `mac-sd-read-powerbit-restart-20261012` recorder is live but has received
no UART bytes at the latest checkpoint. No additional restart is requested.
At the subsequent 2026-10-12 checkpoint, the user returned the Pi to verified
NVMe Linux. The empty recorder was stopped deliberately for a bounded Linux
UART diagnostic: Pi TX counters increase but Mac receives nothing, even with
DTR asserted/rearmed. Image/backups/card hashes remain unchanged; FAT is
unmounted and the serial port released. Keep Linux up and inspect the UART
link before another XNU boot. The stricter independent raw SD evidence guard
passes the expanded 137-test host regression; no physical read is claimed.
The user subsequently confirmed the U-to-UART cable and returned Linux. A fresh
marker reached the Mac at 2026-10-12 00:57:52 UTC, clearing that observation
blocker. Fresh card/reference/image/backup verification and all 22 package
checks passed; `mac-sd-read-link-restored-20261012` was armed before the
00:59:12 UTC one-shot SD reboot. Firmware/BL31/SD-only loader output is observed;
the resumed guarded storage trial continued without rewriting the SD. It passed
at 01:04:33 UTC: sixteen actual sector records match Linux, bounds rejection and
the live shell passed. A host receive-boundary bug interrupted recording after
three complete reads; the failed capture is preserved and a separately logged
continuation collected only the remaining thirteen. Both capture segments and
their unobserved closed-port gap are explicit in metadata, not a continuous
capture or second-boot claim. The HFS guard independently verifies all sixteen
raw records. Only a local HFS staging plan was generated; fresh SSD Linux is
required before any fixture/partition or HFS boot-image installation. The
expanded focused host regression now passes 141 tests. Gate 4 remains active:
HFS repeatability and separate write durability are not yet achieved.

Later checkpoint, 2026-10-12 02:14 UTC: verified NVMe Linux returned
automatically; the guarded stagers preserved full FAT/MBR and image backups,
created/readback-verified the disposable HFS partition, and installed the
distinct read-only HFS image. XNU registered HFS and published `/dev/disk0s2`.
The first mount command stopped at the covered RAM root's statfs64 ENOTSUP:
mockfs lacks VFS_GETATTR. This is not an HFS mount/read/exec pass. The narrowly
scoped archive statistics fix passed host tests. Its fresh kernel/package build
has now succeeded (`run-obi6gw3d`, package `bl33-probe-a5wng87t`), and all 29
corrective package checks pass, including the actual linked mockfs VFS getter
slot. A distinct correction installer preserves the failed image and all old
backups. It subsequently executed after fresh exact-root Linux/full HFS reads.
At 03:12:40 UTC, `mac-hfs-stats-corrected-trial-20261012` passed two complete
read-only HFS mount/full-file-hash/script-and-binary-exec/non-forced-unmount
cycles in one fresh boot. All ten file reconstructions and mount ordering were
independently rechecked against raw serial evidence. The final shell is live;
writes/DMA remain disabled. Preserve the passed `9defaf57...` package. Next is
separate write-provider/cache-sync/writable-mount integration and a batched
changed-image trial followed by reboot/remount/fsck/full-byte persistence checks.
This satisfies read-only repeatability, not cold boots or full Gate 4 exit.
See [STATUS.md](STATUS.md) for actual artifacts and current two-partition media
state. Do not repeat the earlier one-partition initial staging sequence.
Earlier preparation, before these physical results: HFS service matching, converter-ready ordering and
permanent built-in initialization/lifetime also compile and link in a separate
fresh kernel, requiring `bcm2712_hfs=1`. A separate read-only HFS package with
bounded mount/status/unmount tooling passes 28 host identity checks; it has
not been staged/booted and no test partition has been created on the SD. A
separate clean 128-MiB HFS+ fixture passes native read-only Mac fsck and file
hash readback, but provides no Pi storage acceptance. It does not
replace the isolated SD-only trial. The guarded HFS recorder is implemented
for two mount/read/unmount cycles and complete-file hashes in one boot, but
cannot arm before actual SD-read success and fresh Linux partition evidence.
Those preparation checks alone did not claim a filesystem or durability pass.

Implement BCM2712 SDHCI and integrate a pinned IOStorageFamily plus HFS+.
Start with PIO/read-only on disposable media; add writes and DMA only after
buffer ownership, cache maintenance, address limits and error recovery tests.
Exit: repeatable mount/read validation, then separately verified write durability.

2026-10-12 04:17 UTC write-path checkpoint: the distinct opt-in worker/cache/
writable-userland/loader profile is implemented and host-tested. Fresh source-
stable kernel `run-93r3j3i2` and package `bl33-probe-ybis0sa6` pass all 29
linked-byte/provenance checks; no image has been installed or booted. The Pi
has automatically returned to exact SSD Linux with a new boot ID, and two
complete HFS hashes still match the clean fixture. See STATUS.md and
GATE4-WRITE-POLICY.md for exact artifacts and limitations. Next is a separately
guarded installer/serial write batch, then independent intervening-reboot,
filesystem-consistency, read-only remount and full-file persistence proof.
Neither successful host checks nor same-boot fsync/readback completes Gate 4.

04:40 UTC: the guarded installer and serial write recorder are implemented and
host-tested. Actual installation preserved the accepted RO image and complete
MBR/FAT/HFS backups, verified unchanged HFS/MBR and recorded a full post-install
FAT baseline. The exclusive recorder was armed before the one-shot SD reboot.
The separate five-file write/fsync/full-serial-read/non-forced-unmount batch is
now awaiting fresh cache-off hardware admission; independent post-reboot fsck,
read-only remount/full-file persistence and protected-media checks remain next.
No manual restart or repeated soak is required. Current evidence is in STATUS.md.

05:00 UTC: that write trial ended without admission, with zero serial TX/no
batch. The cause remains unknown. Its raw evidence is preserved; a distinct
diagnostic image now passes a fresh source-stable kernel build and all 29
package checks. Wait for the current automatic SSD return, freshly verify root,
new boot/card/HFS and full protected FAT, then install that diagnostic successor
with distinct backups. Do not rerun the first write trial or redo RO/soak gates.
The [write-trial recovery sequence](GATE4-WRITE-TRIAL.md) retains the full Gate 4
exit requirements; none is waived by this startup failure or the host tests.
At 05:25 UTC the complete-raw write transcript auditor, new-boot guarded
read-only partition capturer and no-repair fsck/read-only remount/full-ten-file
Mac auditor are implemented and host-tested. A real synthetic local HFS image
passes the Mac execution path without changing its bytes; no Pi-written image
has been captured or audited. Existing RX-only/SSD waiters remain live while
the prepared W2 diagnostic package stays unstaged. This preparation does not
replace actual admission/write/unmount/reboot/persistence/protected-boot proof.

## Gate 5 — PCIe/RP1 and Ethernet

Development is active independently of the Gate 4 durability hold. Host-tested
FDT/resource planning and GEM descriptor ownership are now joined by a bounded
PCIe observation core; it is not yet connected to actual MMIO or a kernel NIC.
The missing Linux topology dependencies are now captured and reconciled, and
an opt-in topology-only hook is compiled into a fresh host diagnostic. Actual
standalone boot-stage declarations remain unobserved. Next: establish safe
bridge mapping/bring-up, integrate the observer into a distinct diagnostic
image, then verify programmed outbound
windows and RP1 resources before interrupt/DMA/MAC integration. Do not infer
standalone XNU state from Linux's assigned resources.

Implement Broadcom PCIe, MIP/MSI routing, RP1 enumeration, clocks, resets,
interrupts and DMA mapping before the Cadence GEM Ethernet driver. Integrate a
compatible IOPCIFamily/IONetworkingFamily. Validate packet checksums, sustained
bidirectional traffic and DMA/cache correctness. Register-level documentation
and independently written code are the implementation basis.

## Gate 6 — headless Darwin distribution

The existing VM's preserved source-built zsh and RAM root pass Pi-format/static
Mach-O structural preflight. This is not Pi zsh execution. Continue startup,
syscall/VM/signal, Cortex-A76 ISA and console portability work without waiting
for writable SD. Keep the recovery interpreter and VM workstream unchanged;
only a separate opt-in image may become a Pi zsh trial. Full distribution
completion below remains a separate, larger acceptance target.

Treat dyld, libSystem/libc, a maintained init, a general BSD shell/utilities
and OpenSSH as a separate dependency-closure project on a real filesystem.
The earlier RAM-backed serial interpreter is intentionally smaller; the
single-file mockfs proof cannot host this full userland. Inventory public
component versions and missing services before selecting distribution contents.

## Verification and release policy

Host tests exercise parser bounds, range overlap, Apple DT encoding, malformed
Mach-O inputs, configuration selection and provenance checks. Add sanitizers and
fuzzing when native parsers exist. Keep deterministic build manifests separate
from runtime entropy. Rebase only onto explicit Apple tags, reviewing changed
boot contracts, KPIs, ISA assumptions and dependency pins together.

Initially publish source-ready changes; preserve per-file licenses and modification
notices. Newly written loader/tooling may use BSD-2-Clause; kernel-derived code
retains applicable upstream terms. SDKs/KDKs are local build inputs and are not
redistributed. Firmware and additional providers need their own license inventory.

See [DEPENDENCIES.md](DEPENDENCIES.md) and [STATUS.md](STATUS.md) for current evidence.
