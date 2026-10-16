# Gate 0 closure worklist — 2026-09-04

## Closure — 2026-09-25

Gate 0's inspected DEVELOPMENT kernel and reviewed provider/loader contract
are complete for the exact reproducible `31c860a0` image. Two fresh canonical
builds were byte-identical; the prepared dependencies and their hashes were
reconciled to the lock, no KDK archive or dummy startup provider is linked,
the native Mach-O/relocation/layout comparison passes, and crypto/PRNG startup
is observed on the Pi. The artifact-specific ISA review is recorded in
`ISA-REVIEW.md`; Gate 1's hardware record is in `GATE1-AUDIT.md`. This closure
does not make RELEASE supported or prove every future driver/kernel path.

## Current checkpoint — 2026-09-12

Fresh kernel-output build and corrected incremental build now pass. Their
export metadata is byte-identical after fixing its missing rule dependency;
171 tests pass. Crypto/PRNG startup is hardware-observed in an earlier explicitly
identified image. Full deterministic-build and data-aware instruction audits,
plus the locked-toolchain mismatch, remain unresolved. See the current
[Gate audit](GATE1-AUDIT.md) for artifact identities and evidence limits.
Historical link failures and unimplemented-provider statements below are
superseded only to the extent stated in that current audit.

At this historical checkpoint Gate 0 had not passed; the closure above
supersedes that status. This is a source-backed worklist, not a boot
certificate.

## First linked kernel checkpoint

`run-3wcan521` is the first successful incremental `make all` (exit 0), including
all symbol sets and the original export validators. The last eight trust-cache
API exclusions match the pre-existing BCM2712 source/header provider guards;
they do not return successful dummy results or make hashes trusted. All 41 host
tests pass and nm reports no undefined kernel symbols. Clean-build ordering and
runtime-provider/loader requirements remain open. Earlier failure inventories
below are historical, not the current build result.

`run-41ij5p7s` integrates the reviewed policies into make. Two generated Private
export files depend on the policy script, upstream export files and generated
osfmk configuration/ECC header. An explicit path resolver supplies the same files
to linker exports, aliases, symbol sets and check_all_exports. Public sustainable
KPI lists do not include Private and are unchanged. The kernel links and the
validator now reports 75 remaining errors; it is not suppressed. The incremental
build works, but clean-build prerequisite ordering still needs verification.
The 39 host tests pass; the current suite is not a full make dependency test.

The reviewed policies now have one `apply_reviewed_policy` entry point consuming
generated configuration and the ECC header. Applied in memory to the current
Private lists, it excludes 32 common and 8 arm64 entries. Unreviewed APIs remain
unchanged; 75 entries still lack providers against the current linked symbol
inventory. This is a measured policy preview, not a changed kernel build. The
39-test suite passes, including combined-policy checks that trust-cache and
IOMMU APIs are not silently removed. Make integration remains outstanding.

Export-policy configuration input now has a strict reader for doconf's generated
CONFIG_DEFINES plus config_ecc_logging.h. It requires Pi DEVELOPMENT markers,
rejects duplicate assignments/definitions and non-boolean feature values, and
does not execute make or shell input. Inspection of the current generated files
confirms FS_COMPRESSION, SKYWALK, CONFIG_MACH_BRIDGE_RECV_TIME,
CONFIG_SYSDIAGNOSE and CONFIG_ECC_LOGGING are all off. ECC comes from its separate
OPTIONS header; the other options come from the complete generated definition
assignment. This closes the hand-entered feature-input gap for the reviewed
policies. Build integration and the remaining policy groups remain open.

The first explicit export-policy transformation is implemented in
`tools/rpi5/export_policy.py`: for BCM2712 DEVELOPMENT with FS_COMPRESSION off,
it excludes exactly 27 reviewed Private compression exports (the former 24
zero aliases plus three setters). It preserves other lines verbatim and rejects
missing or duplicate policy entries. Other boards and enabled compression retain
their input unchanged. Tests exercise the actual upstream Private.exports file.
This transformation is not yet connected to make: remaining feature families
must be reviewed and all export-generation/validation paths must consume the
same policy output before packaging can pass. No build success is claimed.

The policy now also names exactly four disabled Skywalk exports:
`kern_packet_set_ulpn_flag`, `nxioctl_kernel`, `pktap_input_packet`, and
`pktap_output_packet`. The first two providers are selected by `optional skywalk`
in bsd/conf/files; the packet-tap functions are inside pktap.c's SKYWALK guard.
The transformation leaves every other networking export unchanged, preserves
Skywalk-enabled and other-board inputs, and composes with the compression policy.
Missing policy entries still fail rather than silently adapting to upstream.
The 36-test host suite passes. Build integration remains pending; this does not
resolve the remaining private monitor/IOMMU, trust-cache or diagnostic exports.

Diagnostic policy now covers five ECC APIs, three remote bridge-time APIs and
the sysdiagnose notification API, scoped to their respective Private export
files. Source selection for all three providers is explicit in osfmk/conf/files
and files.arm64. The generated config_ecc_logging.h confirms ECC is off. Policy
application requires explicit boolean feature values: missing values and numeric
surrogates are rejected rather than interpreted as disabled. Enabled providers
and other boards retain their exports. All 37 host tests pass. Build integration
must obtain the remaining feature values from generated configuration before
applying this policy; the policy is still not wired into packaging.

Follow-up `run-gwr8qbwc`: BCM2712's !FS_COMPRESSION branch no longer defines
address-zero API aliases. Other boards retain upstream behavior. The kernel
relinks with no undefined symbols; `nm -g` now finds no global absolute-zero
definitions. This closes the unsafe-alias issue in the kernel, not the export
policy: the full build correctly rejects the still-advertised compression APIs.
A native object-level test verifies absence on Pi and all 24 original aliases
on the non-Pi branch. All 34 host tests pass. No compressed-filesystem support
has been added or claimed.

Provider-audit correction: a matching global name does not establish a usable
implementation. The linked kernel has **24 absolute-zero definitions**, all
from `bsd/kern/decmpfs.c`'s upstream `!FS_COMPRESSION` UNUSED_SYMBOL branch.
These are not callable functions. This invalidates any interpretation of the
name-only export matches as runtime provider closure. `audit_exports.py --kernel`
now invokes `nm -g` and reports these definitions separately (null means this
check was not requested). Do not copy this upstream pattern to close missing
Pi APIs. The Pi export policy must also exclude unavailable compression APIs,
or enable and validate their actual implementation if compression enters scope.

Additional source classifications: ECC logging is selected by
CONFIG_ECC_LOGGING; remote bridge time by CONFIG_MACH_BRIDGE_RECV_TIME;
sysdiagnose notifications by CONFIG_SYSDIAGNOSE. Their absence reflects current
feature selection. `pmap_cs_configuration` and protected-I/O-filter queries have
implementations in x86_64/SPTM pmap, not the selected legacy ARM pmap. The packet
ULPN and Nexus ioctl exports have Skywalk providers. These findings distinguish
intentional feature omissions from a need to add dummy kernel implementations.

Read-only export triage is now available in `tools/rpi5/audit_exports.py`.
Against this checkpoint's 21,066 global symbols, the seven component lists
(common, arm64 and existing arm64.MacOSX variants) contain 115 unmatched entries:
18 Private common, 73 Private arm64, 19 Private arm64.MacOSX and 5 Unsupported
arm64.MacOSX. The other checked lists have matching providers. Counts describe
entries, not unique APIs; they do not establish ABI compatibility. The tool
records input hashes and source lines, understands aliases and wildcard patterns,
and never changes exports. Apple's build-time validator remains authoritative.
Next review those four lists against source feature guards and platform scope;
do not derive the shipping KPI surface solely from symbol availability.

`run-kpb_djd0` applies the first policy change: `EXPORT_SOURCE_PLATFORM` is
BCM2712 for the Pi board and otherwise preserves PLATFORM. Thus MacOSX SDK use
does not opt this downstream kernel into the macOS-specific Private/Unsupported
lists. The common and architecture lists still undergo the original checks.
`KUNCUserNotifications.c` gates the absent notification APIs on
CONFIG_USER_NOTIFICATION; these are not required by the planned raw PID 1.
The build still fails on the remaining Private lists, as expected. A real make
fragment regression checks both board selections; the 32-test host suite passes.
No export is removed based on an automatic linked-symbol intersection.

`run-js8t2wr1` links, strips and generates a dSYM with no undefined symbols;
its source manifest is unchanged during the build. `make all` then fails in
symbol-set/export validation. The stock export lists advertise unavailable
IOUnifiedAddressTranslator, trust-cache, SPTM/IOMMU, Skywalk and other APIs.
Do not silently intersect exports with linked symbols or turn off validation:
define a reviewed Pi KPI surface before publishing a kernel-development package.

The remaining three link dependencies were optional diagnostics. BCM2712
profile extraction now returns ENOTSUP without modifying outputs; zone scanning
returns KERN_NOT_SUPPORTED without invoking callbacks. Other targets preserve
the original code. No fake LLVM serializer or zone scanner was supplied.
MPTCP advice-dependent Wi-Fi exceptions are conditional; without the advisory
provider ordinary TCP loss accounting remains. Native tests cover both MPTCP
modes and diagnostic error/side-effect behavior. The full host suite is 29 tests.
Firehose was rebuilt in `firehose-yhykn_e9` before the successful link.

The first stripped artifact is 16,225,264 bytes, ARM64/ALL MH_EXECUTE, with
LC_UNIXTHREAD PC `0xfffffe00074c8488`. Its __TEXT begins at
`0xfffffe0007004000`; __DATA contains zero-fill not represented by file bytes.
LC_DYSYMTAB has zero undefined symbols and 93,292 local relocations; split segment
information is present. The loader must not assume a flat file image or absence
of relocation metadata. Full ISA, bounds, relocation and provider audits remain.
This artifact is not ready to boot, and the toolchain is still noncanonical.

## Evidence and next sequence

1. The first final-link attempt, `build/rpi5/run-5p99p5xy/build.log`,
   reported 303 undefined symbols. Many were public ARM sources not selected by
   the original minimal configuration, not missing proprietary implementations.
   Do not treat that count as the current final dependency inventory.
2. `NOS_ARM_PMAP` and explicit Pi source entries now select legacy pmap,
   bootstrap, context switching, cache assembly and PCB code. Apple AMCC sources
   referenced by `NOS_ARM_ASM` are absent from this snapshot and are not selected
   on Pi. No PPL/SPTM monitor was enabled. A real config-generator regression
   test verifies the required objects appear exactly once.
3. Monitor-free pmap now compiles. Unsupported trust-cache declarations and
   unused signing-monitor helpers are excluded; the physical-write helper's
   existing read-only mapping implementation is declared before use. Commpage
   invalidation without range TLBI uses full local EL1 invalidation and the
   existing completion barrier before TTBR switching. Native regression tests
   cover both range and non-range control paths; hardware correctness is unproven.
   Apple CPU tunables are not applied on Pi.
4. Rebuild firehose for the final generated configuration, relink and replace
   the preliminary undefined-symbol list. Classify each symbol as a source
   selection omission, disabled-feature call, compiler helper or actual provider.
   The next link (`build/rpi5/run-luci0a8r`) reduced the list to 46 symbols.
   It exposed SHA1/AES/SipHash/crypto registration, profiling,
   `__chkstk_darwin`, KPERF and networking references. Their reachability is not
   yet fully audited. Generic cache cleaning and the absent Apple monitor entry
   have since been adapted; required crypto wrapper sources are now selected.
   The stable checkpoint `build/rpi5/run-2sw6g6v_` reports 33 unresolved symbols,
   with source unchanged during the build. Thread stack/block-hint accessors now
   compile independently of DTrace. Next resolve disabled socket/FIFO/filter,
   KPERF, FSE and coredump references plus compiler/profiling runtime helpers.
   Crypto wrappers linking does not supply the still-missing registered provider.
5. Close the runtime registration contracts below, then inspect the complete
   Mach-O and instruction set. Only then evaluate Gate 0's exit criteria.

## Local socket dependency experiment

The next source-selection pass enabled real local sockets (required by FIFO),
KPERF, filesystem events and coredump support. SipHash is now selected for
non-network POSIX semaphore consumers. These sources compile after correcting
optional-feature guards and pointer-width conversions. The config generator
tests confirm that the intended objects are actually selected, not just named
in a MASTER feature group.

The link in `build/rpi5/run-b2iqspqs` exposes a larger dependency surface:
the socket implementation has unconditional dependencies on IP PCB state,
traffic-class handling, NECP helpers, network statistics and protocol domains.
Therefore SOCKETS without NETWORKING is **not yet a supported independent
configuration in this snapshot**. Its successful compilation is not a linked
local-socket implementation. The previous 33-symbol count no longer describes
the expanded configuration. Resolve this dependency boundary explicitly before
claiming further link closure; do not fill missing protocol functions with
successful stubs. Compiler stack probing, profiling serialization and the zone
leak scanner also remain unresolved.

Gate 1 still has no hardware evidence. Pi RAM SKU and debug-UART availability
have been requested; host build work can continue independently.

Protocol-domain registration now respects NETWORKING: local, system-control and
virtual-socket domains remain, while absent IP/routing/raw-network domains are
not registered. A compiled harness checks both domain sequences. This removes
six unresolved symbols but does not complete the socket dependency separation.

## Compiler stack probe

The missing Darwin stack probe is implemented in `osfmk/arm64/rpi5_stack_probe.s`
and selected only for BCM2712 DEVELOPMENT. The installed compiler's machine IR
identifies `csr_aarch64_stackprobe_darwin`, a byte count in x9, and scratch x16/x17.
The implementation preserves x9, SP, the other registers and NZCV, probes every
4 KiB downward and the endpoint, and performs no stores. Thus it cannot step
over a 16 KiB guard page. A host ARM64 harness executes the actual assembly with
protected mmap pages, tests crossing a guard into readable memory beyond it,
and checks preservation and absence of memory writes. These are host ABI tests,
not proof of kernel exception handling on the Pi.

LLVM 21.1.8's public `compiler-rt/lib/builtins/aarch64/chkstk.S` is explicitly
Windows-specific (x15 in 16-byte units), so it was inspected but not imported.
The downstream implementation is original BSD-2-Clause code, not a renamed
Windows helper. The compiler ABI fixture is retained for future toolchain checks.

The link checkpoint `build/rpi5/run-i1i0ru4x` reports 84 unresolved symbols and no
`__chkstk_darwin` failure. Profiling serialization, zone scanning and the remaining
socket/network dependencies are still open, as is runtime crypto registration.

## Runtime requirements not proven by the linker

### Latest source-selection checkpoint

The local-only socket experiment is superseded by `NETWORK_BASE` selecting
INET, NECP and traffic management. Pi NIC drivers remain deferred. This avoids
inventing a broad local-socket-only fork of the common networking implementation.
`run-gu84b3ka` exposed ESP/BPF declaration dependencies; those are repaired.
`run-xqpr5meg` exposed an unconditional Skywalk adapter lookup; the ordinary
interface hardware-assist fallback is implemented and tested in both modes.
`run-b74ux8s2` now stops on Skywalk-only fields and packet types in DLIL and a
conditional function prototype. Review these boundaries before expanding the
configuration again. These builds have not reached a fresh final link.

The subsequent DLIL, routing, statistics and interface-API boundary changes
advance compilation to NECP clients and drop tracing (`run-fct2ea0m`). The
mbuf receive strategy is preserved, native-nexus detection is false without
Skywalk, absent Nexus queues use the existing error fallback, and receive
steering returns ENOTSUP. Skywalk-only statistics providers and sysctls are not
registered when their implementation is absent. NECP and trie logs no longer
truncate pointer values; they use XNU's permuted full-width address helper.
Pi NECP's Apple browser-role entitlement branch is unavailable, consistent with
the earlier exec policy; the independent privileged-delegation check is retained.

There are now twenty-three host tests. New fragment tests exercise receive
strategy selection, nexus detection and browser-role denial with the original
privilege fallback. None establish hardware gate completion. Remaining compile
errors are Skywalk-only NECP client state/route-resolution/timer references and
drop-tap packet APIs, not a new final-link result.

Subsequent checkpoint `run-tmx38p64`: the drop-tap packet declarations and
implementations are Skywalk-only; mbuf tracing is retained. NECP offload route
helpers/timer, connection-statistics providers and offload cleanup now follow
their existing Skywalk callers. Shared MAC-address population remains available.
Queue setup/dequeue retains ordinary scheduling while excluding unavailable
dynamic Skywalk diagnostics and adapter callbacks. A native fragment test checks
default dequeue and the Skywalk adapter callback's error/result handoff.
Remaining errors are scheduler packet-type guards, CoDel integer-to-float
precision diagnostics, and two unused NECP helpers. No final link was reached.

Checkpoint `run-aly5tzss` advances past those errors. Skywalk-only ECN/L4S and
timestamp packet cases are conditional; the mbuf cases remain. CoDel explicitly
casts interval/count inputs to float, preserving upstream single-precision
evaluation. A regression harness compares it to the original implicit arithmetic
over representative values, including counts around 2^24 and UINT32_MAX. This
does not validate the scheduler algorithm or prove all overflow cases safe.
NECP unused statistics and route-monitor callback/registration functions now
follow their Skywalk-only callers. The remaining build errors are in
`pktsched_fq_codel.c`: missing DLIL declaration and unavailable dynamic Skywalk
diagnostic/channel APIs. No complete image or hardware-gate evidence exists.

Checkpoint `run-y09movaa`: scheduler declarations, dynamic Skywalk diagnostics
and channel notification boundaries are repaired. IPv4 shared argument/wire
types are explicitly included, dummynet copy helpers are conditional, and the
NECP skip-IPsec target remains available without IPsec. Raw sockets retain their
connected destination when content filtering is disabled; socket diagnostics do
not inspect nonexistent filter state. Compilation reaches TCP cache/input/output,
which still call multipath helpers and access MPTCP-only fields without guards.
The accessor itself is now MPTCP-only. Reviewing its callers and shared retransmit
macros is the next source task. All 23 existing host tests pass; these do not
exercise TCP transport or prove a kernel link, boot, or Gate 1 completion.

Checkpoint `run-9caclcwh`: `TCP_RESET_REXMT_STATE` now clears ordinary retry
shift/start fields in both configurations and calls the multipath reset only
with MPTCP. A native fragment test verifies both modes and unchanged unrelated
state. Window-update and keepalive multipath callbacks are also conditional.
The full build still fails on other multipath state references in TCP
cache/input/output and an unused option-parser variable. All 24 host tests pass;
neither the full transport nor the complete kernel has been validated.

| Contract | Source evidence | Required implementation/evidence |
|---|---|---|
| Fresh boot entropy | `osfmk/prng/prng_random.c`: `bootseed_init_bootloader`, `bootseed_init`; ARM requests four 64-byte seeds | Loader supplies 256 fresh bytes through the platform seed interface; short reads fail; no fixed development seed |
| PRNG registration | `register_and_init_prng` copies callbacks, initializes entropy, initializes boot CPU generator, sets ready, reseeds, then clears seed storage | Real compatible provider and startup hook; validate callback completeness, ordering and known-answer/reseed tests |
| Random consumers | `read_random` calls refresh/generate without a null-provider fallback | Prove registration precedes every reachable consumer; early DRBG support alone is insufficient |
| Secondary generators | `osfmk/arm64/machine_routines.c` calls `random_cpu_init`; that function panics if no provider is installed | Establish boot CPU registration before secondary initialization; per-CPU state and concurrency tests |
| Registered crypto | `libkern/crypto/register_crypto.c` stores `g_crypto_funcs`; SHA2 wrappers dereference digest descriptors/callbacks | Source-build required algorithms and a correctly populated registration table; no partial table presented as complete |
| AMFI / Image4 | `libkern/amfi/amfi.c`, `libkern/img4/interface.c` initialize provider pointers to NULL | Inventory every reachable dereference and define a scoped DEVELOPMENT policy; no Apple binary-provider ABI assumption |
| Trust caches / browser roles | Pi target omits trust API, returns untrusted and leaves browser role mask zero | Unsupported, not verified Apple trust. Shared-cache code retains its existing root-check fallback when enforcement applies |
| Mockfs paging | `bsd/miscfs/mockfs/mockfs_fsnode.c`, `bsd/dev/memdev.c` | Allocation repaired, but fast mapping still has page-unit/address-space issues; validate ordinary paging fallback before PID 1 |

No in-tree caller of `register_and_init_prng` or `register_crypto_functions` was
found by the source audit; the functions' definitions/declarations are present.
This is evidence of a missing integration step, not evidence that a provider can
be safely omitted. Exact startup ranks and all dynamic consumers remain open.

## Validation limits

Checkpoint `run-gg1_nx7w`: six unresolved symbols remain. `pf_pbuf.c` is now
selected by NETWORKING for CLAT/NAT464 as well as PF. `pf_find_mtag`,
`pf_find_fragment_tag` and `pf_copy_fragment_tag` moved unchanged from pf.c;
their declarations moved to pf_pbuf.h, which pfvar.h already includes. A direct
comparison against HEAD confirmed all three bodies unchanged. This preserves
tag lookup/copy behavior rather than dropping PF metadata. Header cleanup occurred
during rebuilding; repeat an unchanged-source build before accepting artifacts.
The config test requires pf_pbuf.o exactly once. Packet lifetime, fragment tag
registration and NAT464 runtime behavior still need validation. Remaining:
profiling serializers (2), MPTCP globals (2), symptoms query (1), zone scan (1).

Checkpoint `run-ohkh8hid`: 14 unresolved symbols remain. Socket-flow statistics
open/close and provider callbacks now require SKYWALK as well as the extension
definition. The registration's extra retain and close's corresponding release
share that condition. Provider implementation and UDP-subflow registration are
Skywalk-only in ntstat.c. Ordinary flow tracking is retained. All 27 host tests
pass, but do not exercise socket-flow lifetime or concurrency. Remaining groups:
profiling (2), multipath (2), packet buffer (8), symptoms (1), zone scanning (1).

Checkpoint `run-ppiv3ohq`: 16 unresolved symbols remain; ESP header sizing and
IPsec keepalive collection are no longer referenced without IPsec. TCP retains
the current MTU, NECP uses direct tunnel MTU, and keepalive collection continues
to non-IPsec providers. A native no-IPsec MTU test covers null/non-null routes
and several values; 27 host tests pass. It does not validate tunnel behavior or
keepalive hardware. Remaining groups: profiling (2), multipath (2), statistics
(2), packet buffer (8), Wi-Fi symptoms (1), zone scanning (1).

Checkpoint `run-q5px3ttl`: 18 unresolved symbols remain; bridge and content-filter
symbols are no longer requested. Early bridge input/helper follows IF_BRIDGE.
NECP qualification and its single-use lookup follow CONTENT_FILTER, matching the
sole caller in content_filter.c. Listener setup uses false for filter presence
when the provider is absent, retaining ordinary filter and SYN-cookie branches.
The 26 host tests pass; full bridge/filter/listener runtime behavior is unproven.
Remaining groups: profiling (2), IPsec (2), multipath (2), statistics (2), shared
packet buffer (8), Wi-Fi symptoms (1), and zone scanning (1).

Checkpoint `run-gkpznj4_`: 22 unresolved symbols remain. The two network logging
globals are resolved by the existing `multi_layer_pkt_log.c`, now selected by
NETWORKING, matching TCP consumers without IPsec. The configuration test requires
one logging object; all 26 host tests pass. Packet-buffer source audit found
`pf_find_fragment_tag` and `pf_copy_fragment_tag` dependencies in `pf_pbuf.c`;
review that metadata contract before enabling the shared implementation. No
bootable image, final-config firehose rebuild or runtime-provider closure yet.

### Fresh link inventory: run-t1nnmd_m

This expanded networking configuration reaches the real kernel link with 24
unresolved symbols. The manifest records source_unchanged_during_build=true.
Names below omit Mach-O's leading underscore decoration.

| Group | Unresolved symbols |
|---|---|
| Profiling serialization | `__llvm_profile_get_size_for_buffer_internal`, `__llvm_profile_write_buffer_internal` |
| Bridge | `bridge_early_input`, `bridge_enable_early_input` |
| Content filtering | `cfil_check_filter_control_unit`, `cfil_filter_present` |
| IPsec | `esp_hdrsiz`, `key_fill_offload_frames_for_savs` |
| Multipath | `mptcp_log_handle`, `mptcp_preferred_version` |
| Network logging | `net_mpklog_enabled`, `net_mpklog_type` |
| Statistics | `nstat_provider_stats_close`, `nstat_provider_stats_open` |
| Shared packet buffer | `pbuf_contig_segment`, `pbuf_copy_back`, `pbuf_destroy`, `pbuf_get_packet_buffer_address`, `pbuf_inet6_cksum`, `pbuf_inet_cksum`, `pbuf_init_mbuf`, `pbuf_resize_segment` |
| Remaining helpers | `symptoms_is_wifi_lossy`, `zone_leaks_scan` |

The packet-buffer implementation is selected only by PF in `bsd/conf/files`
(`bsd/net/pf_pbuf.c`), while CLAT/NAT464 consumers are now selected without PF.
Audit its dependencies before changing source selection. The other network
groups need caller/feature/provider review; do not insert successful stubs.
Rebuild firehose for the finalized configuration before accepting any link.
The 26 host tests pass, but neither linking nor runtime-provider closure nor
Gate 1 hardware probes are complete.

Checkpoint `run-7wtr8udq`: IPv6 forwarding/output/raw/UDP compile after matching
PF/IPsec labels and locals to their consumers, preserving NECP's skip target,
and moving shared scope tracking outside content filtering. UDP6's NECP local
is no longer conditional on IPsec. The build now fails in shared socket options
on a Skywalk statistics override and an MPTCP client-UUID accessor. No final
link or hardware evidence is available from this checkpoint.

Checkpoint `run-5xw31p20`: TCP Prague compiles with explicit casts preserving
the existing float evaluation. UDP content-filter locals and NECP policy-local
declaration match their feature use. IPv6 fragment context recovery casts through
uintptr_t, consistent with its save helper. UDP and fragmentation compile; IPv6
forwarding stops on an unused label. The 26 host tests still pass, but do not
validate Prague arithmetic over all inputs, UDP policy or fragment processing.

Checkpoint `run-7_50pglj`: TCP lock/unlock/getlock retain real inpcb mutex
operations without MPTCP; parent socket locking and its retry transition are
conditional. The SYN-cookie parameter remains in the ABI and is marked possibly
unused. Current compilation failures are socket-buffer-space, timer garbage
collection and keepalive-option multipath references. The 25 host tests pass
but do not validate these socket lock paths. Full linking and Gate 1 remain open.

Checkpoint `run-6n7621_x`: TCP cache/output compile. Three receive-window
branches retain ordinary TCP calculations when MPTCP is absent; their original
multi-path alternatives remain conditional. Cache version-update and MPTCP
heuristic-decision functions are conditional, matching their only source callers
in MPTCP. Compilation now stops in TCP subroutines/timers on multipath state
and an unused SYN-cookie parameter. The 25 host tests pass but do not establish
TCP receive-window/timer correctness, final linking, or Gate 1 completion.

Latest checkpoint `run-63hdzi60` compiles TCP input; TCP cache/output still fail
on multipath references. Ordinary receive wakeups remain. The new non-MPTCP
no-data fragment test checks one packet free and unchanged unrelated flags.

Checkpoint `run-zrs_cyn7` compiles TCP buffer-space, garbage collection and
keepalive-option paths. Multipath parent cleanup/callbacks are conditional;
ordinary disposal and keepalive calls remain. A test exercises read-probe reset
conditions in both MPTCP modes. The build now stops on five implicit float
conversion diagnostics in TCP Prague. The 26 tests do not establish socket
locking, garbage-collection concurrency or full transport correctness.

Twenty-six host tests cover native compiled address/trust/TLB/stack-probe contracts and
real config generation. They do not execute the kernel. Firehose is verified as
plain arm64; no complete kernel image exists to inspect yet. Build evidence uses
the explicitly noncanonical installed Xcode 26.6 toolchain. No Pi boot, timer,
interrupt, DMA or SMP behavior has been validated.
