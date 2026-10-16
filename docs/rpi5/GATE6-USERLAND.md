# Gate 6: Pi userland portability, independent of SD durability

## Safe isolated-leaf frontier reached — 2026-10-14

The sealed 33-import client has no remaining provider that meets the genuine
Apple-source, no-new-import, no-semantic-downgrade leaf contract. The sole
plausible candidate is the `_popen`/`_pclose` pair. A real ARM64 link probe of
unchanged Libc-167 `popen.c` closes both but adds `_vfork`; that source also
lacks current locking and allocation/fdopen failure semantics. Current Apple
Libc-1752.120.2 fixes those behaviors but requires modern FILE orientation,
pthread/atfork, posix_spawn/environment ownership, and private libc hooks.
Removing those requirements or mixing its FILE ABI with the accepted Libc-167
runtime would weaken semantics.

A source/archive/hash-pinned default-off checker now partitions all 33 imports,
reproduces the old-source link delta, and rejects old-popen substitution,
vfork aliasing or fork rewriting, removal of current orientation/locking,
service/loader facades, and feature disabling. Five focused tests pass. No
provider was created; the exact import count remains 33. Resolver/notify and
all other service boundaries remain unchanged, and no target, hardware,
network, key, runtime or image was touched.
[Frontier evidence](APPLE-SSH-LEAF-FRONTIER.md).

## Original Apple Libc sscanf parser qualified — 2026-10-14

Distinct `apple-ssh-sscanf-m4_xgkm2`, manifest
`114efe7a753f69e22548da8dca5c3e4f8e20faaec26a5b0232b23d263d742eed`,
adds unchanged Apple Libc-167 `sscanf.c` and the complete unchanged
`vfscanf.c`; it is not a reduced format parser. Source SHA-256 values are
`a5d2994744baadc2cd8f2bcacd35beb4980f67ba9c4ce3410821075f01dcd015`
and `9a08021593cdee0c1caec79460ccc3272a17f3f6928be448faaba516f2680a81`.
Both are byte-verified against the pinned Apple archive.

`_sscanf` closes without newly reachable imports or duplicates, reducing the
unchanged full-client link from 34 to 33 imports. Provider and predecessor use
identical public and system stdio ABI headers. The zero-undefined A76 contract
retains provider-owned `_sscanf` and `___svfscanf`; all nine external parser
dependencies retain their qualified Apple runtime/locale owners. Five focused
tests pass, including native ASan/UBSan coverage of SSH-version and X11 format
families. The native EOF refill is an explicit test-only boundary and is absent
from the target archive. No feature, runtime, service, target, hardware,
network, key or image changed. Resolver and notify gates remain unchanged.
[Provider evidence](APPLE-SSH-SSCANF.md).

## Original Apple Libc perror provider qualified — 2026-10-14

Distinct `apple-ssh-perror-fedl96a9`, manifest
`be08baf42a4708591d75e642b80daeb8936af8210ee6155f9951124a9dd55007`,
adds unchanged Apple Libc-167 `perror.c` plus Apple's original generated
`writev` syscall form using `cerror_nocancel`. The source SHA-256 is
`865d899138df678496ef4479b96479c059c9271140ea85d01aba844f254280d5`;
the builder also verifies it byte-for-byte against the archive pinned by the
Apple source lock.

`_perror` closes without newly reachable imports or duplicates, reducing the
unchanged full-client link from 35 to 34 imports. The implementation writes an
`iovec` directly to `STDERR_FILENO`; it does not access `FILE`, `stderr`, stream
locks, or flush internals. Both `_perror` and `_writev` have provider-archive
owners in a zero-undefined forced A76 contract. Five focused tests pass,
including native ASan/UBSan prefix, empty/null label, errno and write-failure
oracles. The target did not run. Resolver and notify service boundaries remain
unchanged, and no runtime, target, hardware, key, network or image was touched.
[Provider evidence](APPLE-SSH-PERROR.md).

## Genuine Apple notify path is default-off — 2026-10-14

The two visible notify imports are not standalone leaves. Apple's resolver
requires a six-API Libnotify family whose real semantics cross privileged
bootstrap, protocol-v3 Mach/MIG, notifyd-owned shared-memory slots, restart
regeneration, dispatch/XPC, and audited vnode path monitoring. Unchanged public-
SDK probes stop at `bootstrap_priv.h` and `os/lock_private.h` before that
service closure can be built.

A source/commit/hash-pinned default-off checker now records the complete API
expansion and rejects always-unchanged checks, local registries, forced self or
loopback paths, fake ports/MIG replies, fixed slots, and disabled regeneration,
pathwatch, or OpenSSH features. Six focused tests pass. No provider was created,
the unresolved count remains 35, and no target, hardware, network, key, service,
runtime, or image was touched. [Notify evidence](APPLE-SSH-NOTIFY-GATE.md).

## Resolver ownership audit stops at real service boundary — 2026-10-14

The sealed 35-import Apple OpenSSH client cannot honestly close
`___res_9_state`, `_res_9_init`, and `_res_9_query` as isolated libc leaves.
The genuine seven-unit resolver tranche crosses per-thread state, configd's
Mach/MIG DNS service, libnotify, mDNSResponder DNSService, and UDP/TCP+kqueue
transport. `_si_destination_compare` is a distinct Libinfo network-selection
subsystem; its reduced no-dependencies helper is not an ABI-equivalent owner.

A source/commit/hash-pinned admission checker now partitions all 35 remaining
imports, rejects resolver/configd/notify/DNSService facades and feature
disabling, and records the exact admission sequence. Five tests pass. The
retained report intentionally fails admission; no provider was linked, no
import count changed, and no target, hardware, key, network, runtime, or image
was touched. [Ownership evidence](APPLE-SSH-RESOLVER-GATE.md).

## Public Apple OpenSSH localtime_r fallback qualified — 2026-10-14

Distinct `apple-ssh-localtime-r-5apxxhjz`, manifest
`0093975e99016eca90282e2e9dd68264855d40a0bf3c9230d570cc671f3c11c1`,
selects the unchanged `localtime_r` compatibility body in Apple's public
`openbsd-compat/bsd-misc.c`. Its source SHA-256 is
`f97e66fd06996b37465ee51bf172b7cd2c656e7a727ea5b25b72e0a0a7502047`.
The provider calls the already-owned public `localtime` ABI and copies its
result; it does not import Apple's notify/timezone service implementation.

`_localtime_r` closes with no newly reachable imports or duplicates, reducing
the unchanged full-client link from 36 to 35 imports. Two definitions already
present from the original `bsd-misc.c` object receive private names in this
provider copy and are dead-stripped from the forced contract. The A76 contract
has zero undefined symbols. Four focused tests pass in 1.398 seconds,
including a native ASan/UBSan UTC epoch/result-pointer oracle. This preserves
the fallback's original behavior and makes no stronger concurrency or thread-
safety claim. No target, service or hardware ran.
[Provider evidence](APPLE-SSH-LOCALTIME-R.md).

## Public Apple OpenSSH getline provider qualified — 2026-10-14

Distinct `apple-ssh-getline-r2hrtn32`, manifest
`f2f2f6caba8802ccf10fd3a08f4c56208892bd847f2370dadcbd2616bee431dd`,
adds the unchanged public `openbsd-compat/bsd-getline.c` distributed in the
same Apple OpenSSH checkout. Its source SHA-256 is
`0ae4779d71f456e4ff891c90cfb378704291b7ec3ffd4da9b289578e496b54f1`.
Only this provider unit selects the fallback body. A private compile-time name
for its static `getdelim` helper avoids colliding with modern Darwin's public
prototype; the original source and exported `getline` ABI remain unchanged.

`_getline` closes with no newly reachable imports or duplicates, reducing the
unchanged 176-unit full-client link from 37 to 36 imports. The provider uses
only public FILE APIs (`fgetc` and `feof`) and never accesses FILE internals.
Its forced A76 contract has zero undefined symbols. Four focused tests pass in
1.433 seconds, including native ASan/UBSan newline, empty-line, 9,000-byte
reallocation, EOF and negative-oracle paths. No target or hardware ran.
[Provider evidence](APPLE-SSH-GETLINE.md).

## Public Apple OpenSSH asprintf provider qualified — 2026-10-14

Distinct `apple-ssh-asprintf-ewo2v725`, manifest
`20bf991bbe83b4f02308aa21217ddf1172b1ea79bc0114ad06784565236e8f28`,
adds the unchanged public `openbsd-compat/bsd-asprintf.c` distributed in
Apple OpenSSH at commit `f386b2e948280f6ecac875329c0b56020821d558`.
Its source SHA-256 is
`3078aeecdfc3fb27e756a671bde143fd200eb919018fadadf6380f6f33201482`.
Only this provider unit selects the fallback bodies; the unchanged 176-unit
client and its original feature configuration remain untouched.

`_asprintf` and `_vasprintf` close with no newly reachable imports or
duplicates, reducing the failed full-client link from 39 to 37 imports. The
forced A76 contract has zero undefined symbols and both live definitions come
from `libapple-openssh-asprintf.a`. Four focused tests pass in 1.323 seconds,
including the native ASan/UBSan initial-allocation, realloc and direct
`va_list` paths. Neither target executable ran.

This is not a full SSH client or daemon. GSS/Kerberos, logging/notify, dyld,
resolver transport, remaining stdio, timezone, Libinfo destination comparison,
and the private `bootstrap_parent` service boundary remain. Planned install
locations remain `/usr/bin/ssh`, `/usr/sbin/sshd`, `/usr/libexec`, and
`/private/etc/ssh`; no runtime or filesystem image was changed.
[Provider evidence](APPLE-SSH-ASPRINTF.md).

## Apple DNS wire parser qualified; full client remains incomplete — 2026-10-14

Distinct `apple-ssh-dns-wire-8gn7d87_`, manifest
`94cbbbb09610948dd30142aebcb5b1df07fe302c1c9bc3169c1cffb004926b19`,
reduces the unchanged176-unit full-client link from40 to39 unresolved imports,
closing only `res_9_dn_expand`, with no newly reachable imports or duplicates.
Four whole Apple libresolv units are retained, with six explicit size and
truncation corrections. Original sanitizer and boundary failures are preserved.

Main source review and six focused groups pass2.102s, including6691 native
ASan/UBSan cases and32 forced target APIs with genuine archive/errno owners
and no unresolved imports. This is a wire-parser dependency, not DNS transport,
a resolver service, a complete SSH client/server, or target execution.
The current SDK's `bootstrap_parent` belongs to libxpc; a historical liblaunch
RPC client is not silently substituted for that missing runtime/service.
[Parser evidence](APPLE-SSH-DNS-WIRE.md).

## Original Apple daemon provider qualified — 2026-10-14

Distinct `apple-ssh-daemon-q7mo0l8m`, manifest
`30e2b0e27ad7475af67269f9275ec05863fada044d36bfc668655bfeaba6521d`,
adds the unchanged current Apple Libc `daemon.c` and original generated
`setsid` syscall147 wrapper. Bootstrap behavior remains enabled. `_daemon`
closes, but the genuine `_bootstrap_parent` dependency becomes reachable:
the unchanged176-unit full SSH client still has40 unresolved imports.

Four focused groups pass independently and in the main rerun (4.635s),
including176 native process/signal/Mach/filesystem cases, actual archive
ownership and unchanged client configuration. Native system boundaries are
explicit doubles. No full SSH link, daemon execution on the Pi, network
session, accepted-runtime replacement or disabled feature is claimed.

## Current directory family closes another import — 2026-10-13 EDT

Distinct `apple-ssh-directory-5vnm2xih`, manifest
`a31b1f23788746c51ba590d5a560eb61155618fb49ffcdf95af0142d1b359cd9`,
changes the unchanged full client41→40 unresolved imports, closing only
readdir_r with no new imports or duplicates. Five whole current Apple units
and a minimally derived opendir body replace exactly five old DIR owners in
a new private archive. Original syscall344/cerror_nocancel is retained.
The original consumer and provider22-field A76 ABI witnesses match.

Main source/ownership review and six groups pass4.691s, including16 forced
static APIs with zero undefined imports, exact archive replacement, native
ASan/UBSan errors, cookies/rewind/union filtering and four threads consuming
192 entries. Original null-member UBSan failure and two original buffer leaks
remain separately reproduced. Corrections are only offsetof for the constant
expression and two ownership frees. Native filesystem/allocator boundaries
are explicit doubles; no target execution or full SSH success is claimed.
[Full contract](../../tools/rpi5/apple_ssh_directory_contract.md).

## Original RW-lock, environment and collection prerequisites — 2026-10-13 EDT

The main-agent source/ownership review and combined 13-test rerun pass
(7.792s). These are distinct offline candidates, not installed runtime updates:

- `apple-ssh-rwlock-transport-a35pfswk`, manifest
  `7529c89500f244594b9f14f8fde7340d448950a1b4107acb3bf225ce4641a0d7`,
  supplies original generated psynch syscall306/307/308 wrappers and original
  Mach thread_switch. Eleven forced APIs link without undefined symbols;
  336 native Mach-wrapper cases use an explicit trap callback. The experimental
  original stdtime branch changes47→43 imports, not the qualified41-import
  baseline. Actual target RW-lock/trap execution is unproven.
- `apple-ssh-environment-id9imlth`, manifest
  `ba01dc58574d6349761bd648314c8341898ffd2ef46b1ef54952ecf71fa667f5`,
  composes the complete current Apple environment family with shared lock and
  owned-pointer state. Two original getenv_copy_np leaks are reproduced; a
  separately derived body adds cleanup while preserving error semantics.
  Four native threads run128 iterations each under ASan/UBSan with explicit
  environment-pointer/lock/allocator doubles. Fourteen forced target APIs
  link without undefined symbols. Only three old environment objects are
  removed from a new private archive; all retained object bytes match.
  This branch changes43→42 imports. Target fork-child registration remains
  unqualified and no accepted archive is replaced.
- `apple-notify-collections-20uzs24a`, manifest
  `cb494ba7e766967f309e7365198c9036b7ea8b3b7ad441c58e8a3fc016296793`,
  uses unchanged whole Apple map/set units and original Blocks. All57 APIs
  have original live owners in the static target. Native tests cover seven
  representations,1024 elements each, collisions, deletion, callbacks and
  four genuine fatal allocation-failure children. Existing glue allocator/
  assertion owners are explicitly retained, not relabelled Apple libmalloc.
  This is a notify registry prerequisite only; the full-client branch stays42.

Genuine notify bootstrap/XPC/service dependencies remain. No notify stub,
feature removal, full SSH link, daemon, network session or target execution
is established. The better-qualified full-client composition remains41 imports.

## Derived system and original spawn providers close another import — 2026-10-13

`apple-ssh-spawn-contract-o1r3nnno`, manifest
`08e28e13a755e593ce315df0b0454b53339455675aedd81b05006ef6f85b09eb`,
closes `_system`: unchanged full-client configuration falls42→41 unresolved
imports, no new imports or duplicates. Original current libsyscall spawn bodies
and syscall244 compose with a minimally derived Apple system body. Its sole
source change assigns `errno=err` when spawn returns ENOMEM/EAGAIN. The original
stale-errno reproduction remains separate and fails the same required-error
contract; no unchanged-upstream system claim is made.

Five groups pass independently and in the main rerun (2.184s): complete source/
consumed-header/output closure, exact original/derived error negative, native
ASan/UBSan attributes/actions/filter/signal-restoration tests plus4×32 serialized
system calls, actual full-client link delta, and16 forced A76 API owners with
zero undefined imports and strict image inspection. Process/kernel/signal/I/O
boundaries are explicit native doubles. No target process or SSH execution,
accepted-runtime replacement, provider stub or feature removal occurred.
Modern popen/pclose remain excluded: their fwide orientation dependency is
incompatible with the accepted Libc-167 FILE representation. The full SSH client
still does not link or run.

## Original Apple TTY/temp providers close four imports — 2026-10-13

`apple-ssh-tty-temp-contract-bicg15ou`, manifest
`9f55971e5feb4d9b25a48419a279f19ff9c2aa5d18003eb79dd1d3abb92552df`,
adds unchanged current Apple mktemp, readpassphrase and devname units plus
original generated fstatat64, mkdirat, write_nocancel and statfs64 wrappers.
The unchanged 176-unit full client link falls from 46 to 42 unresolved imports:
`_mkdtemp`, `_readpassphrase`, `_devname_r` and `_statfs` close, with no new
imports or duplicates. It remains a failed full-client link, not working SSH.

Four focused groups pass independently and in the main rerun: exact source,
header and output closure with omission/mutation controls; full-client command
delta; forced seven-symbol A76 static contract with zero undefined imports and
actual archive-owner checks; and native ASan/UBSan tests (7 temp-path, 15 TTY,
5 device-name cases). Native filesystem, terminal, signal and random boundaries
are explicit test doubles; no host terminal or secrets are accessed. Target
contract SHA `a69d8c1268a1d0a23bcbeb5ec4c096372977a47b0d8777ddbbd97e9b5cf9b921`.
Neither the providers nor SSH have executed on the Pi or replaced its working
runtime. The preserved modern stdio audit still fails at private libtrace/
firehose declarations; mixing modern FILE ownership with the older runtime
is not qualified and has not been done.

## Derived Apple clock reads close another SSH dependency — 2026-10-13

`apple-clock-checked-acrq3vpm`, manifest
`a2db7650517f1a30ba7374f9737ed18965c92fd4ec2126596e85febe193b7a52`,
reduces the unchanged full SSH client link from 47 to 46 unresolved imports,
zero duplicates and no newly reachable imports. The private Mach declaration
comes from the original XNU header, not an invented prototype. Genuine
mach_boottime/mach_approximate bodies and the original generated
thread_selfusage syscall compose with the inherited absolute/continuous
providers. No host test callback enters the target archive.

The clock TU is explicitly derived: errors return before converting/publishing
time values; boot-time fallback failures propagate rather than reporting
wall-clock time as uptime; valid zero ticks succeed; scale conversion uses
overflow-checked exact quotient/remainder arithmetic without a new division
runtime; optional resolution output is normalized; setter nanoseconds are
range-checked. Native original failure reproductions remain separate from
the corrected executable. ASan/UBSan tests include first/second/persistent
fallback failures, unchanged failure outputs/errno, all supported clock paths,
zero ticks and 36,936 rational-scale cases, including both overflow positions.
The earlier public-header compile failure and 128-bit-division link failure
are preserved, not relabelled as qualified providers.

Read-only forced target contract `apple-clock-read-contract-mrnnxc8f`, manifest
`e5ef9437d8eb3aa615a17c8f7b972c3dc7e7f44d64ea0f82c0aaab0c348ee64e`,
links with zero undefined symbols, passes strict static image inspection,
and verifies 13 actual provider owners in its link map. The timebase trap and
gettimeofday forwarding remain pre-existing project ABI providers, not newly
claimed original Apple implementations. Target binary SHA
`c041aa07f8a9d4df6dd566a92f6af794c39673e6928f0d346d29f69909d98e32`.
This contract is not the full SSH executable and was never executed.

The separately forced four-API contract preserves a real `_settimeofday`
dependency (`apple-clock-static-contract-9g46utl5`, manifest
`a2c7ee6b6510e86b8447fd7c4fc41a155ac0939dc8032f89aa10f56e16364209`).
Clock setting is not qualified, and no clock-setting syscall ran. The new
read-only provider has not executed on the Pi or replaced the working root.
Full SSH link/runtime and actual Ethernet remain unfinished.

## Real file-backed Libinfo and additional Apple runtime providers — 2026-10-13

The preceding composition has 47 unresolved imports, zero duplicates.
`apple-ssh-case-signal-z9p6dj86` (manifest
`6536a620946ddf6cd2f497dfcec784d7e759b07a95c0ab1f9cfe04f40fe31599`)
adds original case-search/comparison and signal-data units plus a minimally
derived strsignal: unsigned INT_MIN magnitude and capacity guards before
suffix subtraction/appending. The original heap overflow and signed overflow
remain separately reproduced and recorded; no unchanged-strsignal claim.
Only the legacy strcasecmp runtime member is replaced, every other retained
object byte preserved. A complete forced ARM64 contract proves genuine new
comparison ownership with no undefined imports; that contract is not the full
SSH client. Four focused groups pass: 174,880 case-search cases, real locale/TLS
threads, 648 signal capacity cases, both original failure reproductions,
complete closure/ownership, and full-client configuration-preserving 49 → 47
link delta. Non-C locale files and Pi execution remain unqualified.

The preceding composition has 49 unresolved imports, zero duplicates.
`apple-ssh-strncpy-chk-uhooi_u9` (manifest
`cb674efb3ebad4d28e68f519557f199bd748d57c599ead438b616dcdcc29acf9`)
adds unchanged Apple strncpy_chk/stpncpy, 50 → 49 with no new imports. Five
focused tests pass, including 332,304 valid bounds/truncation/alignment cases,
129 unterminated-source cases and genuine overflow traps before writes.
Actual A76 calls are nonrecursive. Original overlap checks occur after writes;
the native callback observes writes before the original trap, not an earlier
ASan overlap rejection or a prewrite overlap guarantee. Consumers and original
SSH features remain unchanged. No Pi execution or completed SSH link.

The preceding 50-import composition is preserved. Distinct
`apple-ssh-libc-prereqs-crebas6n` (manifest
`e50d8616f35c33e88beebab3d6e75ccfe008598669534c1ec4c06f7f9de809dd`)
adds unchanged original strnstr and the original generated initgroups wrapper,
54 → 52. The privileged group syscall has not been executed on host or Pi.
`apple-ssh-interface-helpers-o1gdvmp_` (manifest
`2165e237397a2d7ce8e364f6469a8044be29ce62575d3b985a1f68b372fe6f0f`)
adds three complete original Libinfo interface/Ethernet TUs, closing three and
newly exposing ___strncpy_chk, 52 → 50. Eight combined focused tests pass.
Native tests use original getifaddrs against local host route sysctl and bounded
MAC parser fixtures, not external services or Pi networking. Original ether_line
retains its unbounded hostname scan; arbitrary oversized inputs are not qualified.
No SSH executable is linked or running on the Pi.

The preceding composition has 54 unresolved imports. Complete original
Apple stpcpy (`apple-stpcpy-i77u3elg`, manifest
`2af08054a8d368beb4fe0dceb53e89c0c9b0dcd376be0bb132ab7875bcba9381`)
closes 56 → 55 with no new imports; 65,536 native alignment/length/canary cases
pass ASan/UBSan. The unchanged provider TU uses Apple's original provider-only
fortify build policy and actual A76 strlen/memcpy relocations, not recursive
checked calls. Three focused regressions pass.

`apple-dispatch-once-gr21uo30`, manifest
`d7f02eb05b151d5dd1ca609c8dd2bd0106d02ea756c7a72eaeb680819611cbd3`,
closes 55 → 54 without new imports. It compiles the complete original once.c
bytes against an explicitly selected private-header boundary, plus unchanged
original gate/ulock-wait/wake function fragments. Public pthread Mach-thread
identity is an explicit ABI binding; ARM quiescent-counter behavior is retained
with the real XNU commpage definition, acquire/release atomics and fatal traps.
This does not qualify complete libdispatch, queues or Objective-C callouts.
Eight real native threads share 128 predicates/512 published words; context and
recursive-call real child-trap cases pass ASan/UBSan with an explicit native-only
generation-counter double and real system pthread/ulock calls. The executable
map confirms original once/wait object ownership. Three focused tests pass;
neither new provider has executed on the Pi or completed the SSH link.

Distinct `pi-libinfo-files-wj7_spx1` compiles ten real Libinfo units under an
explicit Pi static file/cache/search profile. Public account/group/service,
numeric and passive file-host lookups pass native ASan/UBSan with four real
threads, disposable fixture files and unavailable modules failing ENOTSUP.
Original target paths retain `/var/root`, `/Users/sandrzej`, `/bin/zsh`, and
the original root/nonroot account-file policies. No host account files, dynamic
service loading or external DNS is admitted by the checked fixture. An explicit
two-pass payload-alignment correction fixes reproduced original typed-pointer
misalignment; 320 packing cases pass. This is not Pi account-lookup execution.
The actual full-client link closes six APIs but exposes 23 genuine dependencies,
changing the preceding 50-import numeric profile to 67, zero duplicates.

`apple-runtime-api-fragments-bg8jq8u2` selects exact original current Apple
reallocf/crash function bodies with complete leading licenses and an explicit
public-header boundary, not whole original libmalloc/libtrace TUs. Eight
allocation/errno cases, callback/default behavior and a real original caller
trap pass natively. It independently closes two imports in the 54-import
composition, yielding 52 without new imports. Three focused tests pass.

`apple-blocks-runtime-ga1_x5sg` compiles both complete original pure-C Apple
Blocks runtime/data units from verified official libdispatch-1542.100.32 bytes.
Native global/heap/byref-escape/nested/NULL cases and four threads performing
4,096 retain/release pairs pass ASan/UBSan. The executable map proves original
object ownership instead of using the system Blocks runtime. Three focused
tests pass. The separate full dispatch_once compilation inventory fails on
private-header/availability dependencies and is explicitly not a provider;
the unrelated ExclaveKit no-op is never selected.

Final `apple-fortify-runtime-punnvr0c` uses the exact original Apple Libc
provider-only `_FORTIFY_SOURCE=0` build policy; consumers keep their original
configuration. Nine real checked-function units (one explicit strcpy validation
ordering correction) pass 12 valid / 14 fatal native cases and actual A76 leaf
relocation/trap checks. Four focused tests pass. The first SDK-default prototype
is preserved and rejected: target disassembly exposes recursive self-branches,
despite its passing native namespace fixture. Do not select that prototype.

The final real file-backed profile plus genuine selected APIs, Blocks and
checked providers now produces 56 unresolved imports, zero duplicates. This
67 → 56 composition closes 12 and newly reaches genuine stpcpy. Counts from
different profiles are not direct progress percentages. Dispatch_once, logging,
notify/network integration, configured GSS/dynamic loading and other services
remain genuine gaps. No complete SSH executable, daemon, target execution,
live keys or SSH session is established by this source/link evidence.

## Original full OpenSSH client: source build and provider closure — 2026-10-13

The combined original full-client link now has 54 unresolved imports, down from
108, with zero duplicates. The 176 original source units, original main and
feature configuration stay intact. Distinct startup and copied-runtime inputs
select the current Apple locale owners, removing exactly eight legacy locale
object members while preserving every retained object byte. Current Apple
process/file, string/ctype/locale, original socket wrappers, current upstream
zlib and the kernel-backed random APIs compose in one real full-client link.
This is still a failed link with explicit remaining service/provider gaps.

The official zlib 1.3.2 release archive is SHA
`bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16`.
All 15 original units compile for A76 and native ASan/UBSan. The original
upstream example passes compression, gzip, dictionary and synchronization
cases; a caller built with the same SDK header as SSH passes eight streams,
bad-checksum rejection and truncation against the new archive. No system libz
supplies those tests. Apple's published zlib commit `06673bf7…` contains
version 1.2.12 and is retained as source-selection evidence; this provider is
explicitly the current [upstream release](https://zlib.net/).

The word API is a small project adapter over the already tested getentropy
buffer adapter. The unchanged original LibreSSL rejection sampler implements
arc4random_uniform. Ten boundary/rejection sequences and 256 residue groups
pass with a synthetic byte source under ASan/UBSan. Compiled A76 code delegates
only to the existing buffer API and the word adapter. These new word/uniform
APIs have not run on the Pi and do not qualify entropy or live keys.

Frozen combined evidence: `apple-ssh-runtime-groups-12k4lp6u`, manifest
`b1bc88e185700a8cfd0c55f6ccc3fa81fb5072f7e242b458026ca081924eb552`.
Three composition regressions pass independently, checking exact link deltas,
all input bytes, archive membership and remaining imports. Current Apple
locale's native harness label MBTOWC=6 is a metadata typo; the actual tests
exercise five mbtowc cases. The separate locale audit note preserves this
correction without editing the frozen harness or receipt.

All 176 translation units selected by the original client/libssh/compat
Makefile compile with the original feature configuration. The complete static
link initially reports 108 unresolved imports. Current Apple getopt/strtonum
and secure-memory providers close seven imports and expose strtoll, leaving
102. Original Apple syscall generation and arm64 public aliases close twelve
socket imports, leaving 90. Cancellable accept/connect/recvmsg/sendmsg retain
the real cerror → pthread cancellation path; the other generated calls use
their original cerror_nocancel path.

The native option/numeric cases pass ASan/UBSan. Three full-client closure
tests and three generated-instruction/alias/error-path tests pass independently.
A separate forced syscall-contract executable links without imports; its
scope is static instruction verification. The full SSH client still does not
link or execute. Account/resolver, locale, process/file, random, compression,
configured GSS/Kerberos and dynamic-loader providers remain in the real link
diagnostics. No live keys or SSH sessions have been attempted.

Frozen evidence: `apple-ssh-full-client-3xbnfnp5`,
`apple-ssh-client-leaves-8svd9i48`,
`apple-ssh-socket-syscalls-n4wc59z7`, and
`apple-ssh-socket-contract-swo77b1n`.

## Root45: actual entropy APIs and complete twelve-command batch pass — 2026-10-13

`root45-entropy-mob0oyvx/probe.bin` SHA
`90f24fea6ca7dd83345b3aedefdaf12c50334ba6d41272b17386517f7d555d75`
is 21,024,704 bytes; manifest
`8a3b8ab64840457e8647ce43482dd5ecb5762b3756136f1f091618570b9440c1`.
The actual mounted read-only root has 45 nodes / 33 files / 2,916,352 bytes.
All twelve command bodies and statuses pass, followed by the separate actual
zsh exit status zero. Existing binaries remain byte-identical; only the root
identity executable and two new diagnostics differ from accepted root43.

Both previously `NOT_RUN` probe byte sequences now have separate real-board
evidence. The original getentropy syscall passes the three admitted lengths,
oversize EINVAL and invalid-destination EFAULT checks. Original LibreSSL
RAND_bytes passes five lengths through the explicit project kernel adapter.
The genuine Apple pthread startup/prerequisite executes for each. Build-time
manifests remain immutable; no live keys, seeds, random output or its hash is
emitted. API success does not qualify the entropy source or establish SSH.

Observed startup_done is 1. Repetition test reset/failure/max counts are
2155/0/2; adaptive-proportion counts are 5/0/3. Filter total/accepted/rejected
counts are 2958/2160/798. These ten reads are separate observations; no atomic
cross-counter equality or independent entropy assessment is inferred.

Capture `root45-entropy-serial-20261013`: 53,324 bytes / 821 TX, SHA
`588dca26f0b1b0c5c141b7251c47ac5160aaa4e27cc887cf6046a64673da9abb`;
nonce `Bb05b2678914b862e`, command end offset 50776. Whole-capture fault
rejection and normal NVMe selection pass. Independent SSD Linux boot
`b4facb5d-241b-411f-82a3-5990b2a455ac` is verified. The original working
loader is restored and normal firmware remains unchanged; full replay passes.
Restore `root45-entropy-restored-20261013`: seal
`d9b79d1f693994bde6a07fbba05747aefd10ad2a57c227a97e7c1562f51e7403`,
plan `a47bf310153c40ad9b1ceb0c2ecc839c02876c7a6fc4ac3190389f0f65853efe`,
result `bf508a933256ac255566e4e3c00ab1374852bc40db0ab20d5713a9202248c3dd`.
Catalog 212 → 216 → 220; installation/restoration 23.711 / 23.781 seconds.
The new result schema correctly spells Poly1305, preserving the older root43
typo in its historical receipt rather than editing frozen evidence.

## Stateless kernel-entropy adapter: offline closure only — 2026-10-13

`kernel-entropy-rand-hfrb7y67/NOT_RUN_kernel_randprobe` is 116,432 bytes,
SHA `fed221215a29d62909e169f44bc66abac15603967db3f252737f419f30dca14a`;
manifest `f46bd17a8171c4272985875cfbb6a49d7305a49e26d2ee716facbe6aaac924f8`.
Original LibreSSL `RAND_bytes` calls the explicitly project-owned
`arc4random_buf` adapter, then original Darwin getentropy syscall 500.
The adapter chunks at 256 bytes, has no generator/cache/lock/heap/fork state,
and terminates the process on any failed syscall rather than returning partial
data as success. Linked code retains real exit syscall 1/status 127 and a trap
fallback. No private Apple RNG implementation or old RC4 fallback is substituted.

Four focused tests pass independently (0.992 seconds): exact target/header
closure, zero undefined symbols, genuine pthread constructor, actual syscall
and fail-stop instructions, original LibreSSL delegation, 11 boundary cases,
eight fatal cases, four threads and fork under ASan/UBSan with explicitly
synthetic syscall doubles. The failed full modern Apple arc4random compilation
remains recorded, including its private logging/header dependencies; it is not
presented as successful reuse.

This target and the separate entropy API/health-counter diagnostic are not yet
installed or executed on the Pi. The planned distinct 45-node batch adds both
without changing existing accepted utility bytes. No random output, seed,
live key, entropy qualification or working SSH service is claimed.

## Root43: actual packet crypto and complete ten-command trial pass — 2026-10-13

The exact `root43-packet-vqgxaczi` image SHA
`d5d3c29905ed191aa848867416bfc0444ce93f43b30ad6843dc0236d9a8c8340`
passes mounted identity for all 43 nodes / 31 files, all ten command bodies
and zero statuses, and a separate zero actual process-exit query. Its
`/usr/local/libexec/xnu/sshpacketprobe` is the byte-verified executable SHA
`7934dcd0b9882e1ad9a22834bc3f76af805283c8cdb264d26e885c0275879d1b`.
The genuine Apple startup/pthread prerequisite and both real constructors now
execute on the Pi, followed by 48 valid packet cases and 5,036 rejections.
Earlier `NOT_RUN` filenames/manifests remain immutable build-time records;
this separate board receipt supplies runtime evidence for their exact bytes.

Capture `root43-packet-serial-20261013`: 51,397 bytes / 726 TX, SHA
`d96dd7b995555f71150a079e31a6d19afd1c91e375ffd024a749ea2f1bb48fa9`;
nonce `Bd8a75b07ec32339e`, command end offset 48854. The full capture passes
fault checks through normal NVMe selection. Independent SSD Linux return boot
`3e8c66ce-fdcb-4170-a3a7-4a8d3f07ddc8` and original firmware/zsh restoration
are verified; full read-only chain replay passes. Restore
`root43-packet-restored-20261013`: seal
`a0034ab75334160b53c88c4abbe19222f8c25dd6143a3156d2872e2cc7419141`,
plan `97cf12e383ebf91aa5c53bbab5e35fb721ece0566c33a1a7849af2ee7c3c1136`,
result `6f3546b3a56b3adfa4c28c01e82a831b18530691b17fb8dacb3531f89d1156a2`.
Catalog 194 → 198 → 202; installation/restoration 23.693 / 23.725 seconds.

This is fixed public-data packet-cipher evidence, not SSH transport, key
exchange, a daemon, entropy qualification or network hardware acceptance.
One sealed report key is misspelled `actual_chacha_poly1315_public_kats`
because of a numeric metadata substitution; the actual source/oracle executes
Poly1305 unchanged. Preserve that historical key/receipt; future schemas must
use token-specific changes rather than blanket numeric replacement.

A separate future entropy API/counter diagnostic is built and host-checked,
not installed or run. See [source provenance and limits](../../tools/rpi5/entropy_runtime_provenance.md).
It exposes no random bytes, seeds or keys; even a successful API/counter test
does not qualify the underlying firmware seed or accumulator assumptions.

## Corrected root42: genuine pthreads and complete batch pass — 2026-10-13

`root42-ready-4h4evl7f/probe.bin` SHA
`6a8bcf69863ecba29f4375ed9df89806ff7de5a37f9c51d2fd1465fbdca5f793`
physically passes the complete 42-node / 30-file mounted identity, all nine
commands, and the separate actual process-exit query (zero). The unchanged
genuine pthread executable proves its exact constructor, four-thread
create/join, 2,048 mutex/allocator-operation, four TSD-destructor, once and
thread-local errno workload on Pi. Existing zsh, SSH buffer and primitive
KATs, actual Apple pwd, recovery utility aliases and metadata tests also pass.

Capture `root42-ready-serial-20261013`: 50,724 bytes / 678 TX, SHA
`7a2ef85150596963423e32d32d3362f076b53887360664b57255e8bf57f5e46e`.
Whole-capture fault checks pass through NVMe selection; independent Linux
return boot is `df0601fc-f5a8-48d6-84e4-cb0a302d7f23`. Original firmware/zsh
restoration and full chain replay pass in `root42-ready-restored-20261013`:
seal `96dbed87912bb1f8a3ce1bcaf023ff9add582bf7906f2cf6a6af812384a38d02`,
plan `62bd35deddbc0d11f8df72b3ad32165bf2e9703fa42e1c91b44943d15f4e7597`,
result `dd78d02a49977721e48c7cc3d640ed38a8897b7ab71f31f7960f55657db353c3`.
Archive catalog 176 → 180 → 184, no deletion. Publication/restoration take
23.189 / 23.615 seconds; no manual restart or added soak.

This supersedes the earlier zero-input admission failure without altering its
receipt. It does not accept full LibSystem/dyld, general allocation, entropy,
the separately built packet cipher, SSH transport or a daemon. The next
distinct 43-node / 31-file root adds the packet executable as a tenth command.

## First root42 trial: zero-input admission failure — 2026-10-13

The exact `root42-pthread-ulws4mq6` image boots to the recovery shell, but
SMP startup corrupts its required early `RAMROOT:MOUNT` record. The later
`WATCHDOG_READY SECONDS=180` record remains valid. Admission correctly sends
zero bytes; the complete identity exchange and all nine commands are unrun.
Do not interpret this as a pthread implementation failure or success.

Capture `root42-pthread-serial-20261013`: 39,436 bytes, SHA
`cdd6cd59d5f43ba969ce52fddaa44bc8e6615966e05302ae5aee93372d51af66`;
state SHA `f26427f71779c93ba80fec33274909240589896a86d94a3ade045fc57106351f`.
The recorder stops on the next boot's partial `Boot mode: NV` line with
`Unsafe/repeated boot; zero TX`, so continuous completed NVMe selection is
not claimed. Independent SSH verifies normal SSD Linux boot
`fb11a075-583a-481f-bbc8-6552336d50c8`.

Known-good restoration `root42-pthread-restored-20261013` retains original
firmware `413a050e…` and working loader `f2aee33a…`. Canonical restore seal
`d05f4d476210d53832357c5b69e6fe4d96b15461db375e2509d313d1ee89e778`,
plan `37532ef04ec861f5d2d963435766914bc80fbf3e8287686dd8aaee08441fb67b`,
result `42604e7060290c14f6464c44141eeaa86d099be2edb1def895bc344605c1f7dc`.
Archive metadata advances 158 → 162 → 166 without deletion. Install/restore
publication took 23.225 / 23.508 seconds with unchanged firmware.

Next publish actual installed root count/extent/read-only state with a
release/acquire snapshot, and emit a few bounded confirmations only after
successful existing watchdog reloads. Retain the original early log, unchanged
180-second deadline, fresh tagged boot, complete FDT/materialization/commit
checks and all 30 mounted-file hashes. A new protocol must reject contradictory
confirmations and faults through recovery. No arbitrary console serialization
or target runtime success is implied by this planned telemetry correction.

## Modern utility root and genuine crypto provider — 2026-10-13

The subsequent `apple-ssh-packet-pthread-iabcb1gr` composition now links the
genuine Apple startup/pthread implementation with original packet code and
static LibreSSL. Manifest SHA
`b1ca5bec6b327284fd8df985753ac5a10bcd324295ab981c946cc7ebb4d3cef3`;
target SHA `7934dcd0b9882e1ad9a22834bc3f76af805283c8cdb264d26e885c0275879d1b`.
The strict static inspector passes with no unresolved or duplicate symbols.
Debug-only stripping removes an `N_GSYM` metadata entry while all six loaded
code/data sections stay identical; the original strict inspector is unchanged.
The actual constructor table contains the pthread workload constructor followed
by LibreSSL's CPU-feature initializer. Four independently repeated tests pass
(0.459 s), including exact closure/linkage and a composed host workload with
four threads, 2,048 mutex/allocator operations, 48 valid packet cases and 5,036
rejections. Host pthread execution does **not** validate Pi startup or CPU
feature queries. At that build checkpoint the target was `NOT_RUN_sshpacketprobe`;
the subsequent root43 board acceptance above supersedes that unrun status. No live keys,
entropy qualification, SSH transport or server acceptance is claimed.

The separate `root96-command-batch-uc8f3v5l` root has **41 nodes / 29 files**,
SHA `4bd824425b0509b7a163649e07ded06ae7eeae6397a90d0e7b2eb75e50955708`.
It adds the actual current Apple `shell_cmds-329` `/bin/pwd` and the original
OpenSSH primitive executable. Canonical `/usr/bin/{uname,wc,hexdump}` and
`/usr/local/libexec/xnu/statprobe` currently contain byte-identical copies of
the existing recovery utilities, **not newly ported Apple implementations**.
Old paths remain compatible. The private init/recovery-shell overlays search
`/usr/bin:/bin:/usr/sbin:/sbin`; `/etc/paths` records those paths. `/usr/sbin`
does not yet exist in the image. No accepted VM sources were modified.

`check_root96_command_package.py` independently reconstructs all 11 build/
audit commands, 1,985 input pins, 37 generated files, the exact root and identity
catalogue, aliases, and static Mach-O entry linkage. Six focused mutation tests
pass. Historical recovery objects reproduce the accepted binary apart from
LC_UUID, but their original source snapshots/toolchain identity are incomplete;
do not call the entire root fully source-reproducible. Native host PATH tests
are not Pi utility acceptance. Future target commands must explicitly execute
`/bin/pwd -P`, `/usr/bin/uname`, `/usr/bin/wc /etc/motd`, and
`/usr/bin/hexdump /etc/motd`, without unsupported host-only flags. This root
has now been packaged into the distinct tagged four-CPU image
`root96-batch-amkl_cna/probe.bin`, 20,483,840 bytes, SHA
`85736b0ded6b6a93657f792281a77464ec0cf739bd357d646715eeff8fd78354`.
Manifest SHA `a1f0db805fc9eef8d520c562281c98c24c8a87ec894bc6b0921c79c04bacd737`.
Three focused tests pass with the actual native loader, retained FDT, serialized
root/Device ranges, real kernel/root/loader extents and three live-overlap
rejections. Its 13,999 input pins, 37 header pins and 21 generated files are
checked. The root lies at `[0x8234000,0x8478000)`; the loader ends at `0xa4bc170`,
below the retained firmware FDT at `0xb000000`.

The distinct readiness-v2 kernel reports only after a successful reload at
least five seconds after terminal enable; its 180-second terminal deadline and
15-second hardware timeout are unchanged. The new serial protocol requires
the exact unique loader tag, fresh root/FDT/topology/copy/commit markers and a
later shell prompt. It separately checks all 29 mounted-file hashes, executes
eight read-only tests in one nonce-framed zsh process, then queries that process's
actual exit status from the recovery shell. Nine focused protocol tests pass,
including the actual recovery C parser under ASan/UBSan, native zsh framing,
reset-during-TX and absolute per-byte deadlines. All three exchanges total 631
UART bytes at the existing pacing. The first physical trial now passes complete
mounted identity and executes all eight commands with zero per-command statuses
and batch `END:0`. It is nevertheless incomplete: the pwd oracle incorrectly
expects a bare `/`, while its actual accepted startup emits four
`DARWIN:ZSH:{ENTRY,TSD,ENTROPY,MAIN}` lines first. The recorder stops after 585
TX bytes, before the third actual process-exit/recovery query. Preserve the
failed state and raw bytes in `root41-serial-20261013`; do not relabel this full
trial as passed. A distinct strict oracle must recognize the exact real prefix.

Original Apple secure-erasure and constant-time comparison providers close
`memset_s` and `timingsafe_bcmp` in the actual packet-cipher target link.
`apple-ssh-packet-leaves-we7s8n0w` preserves genuine source implementations;
four focused tests pass, including 131,842 comparison and six erasure cases.

The separately signed-source-verified **LibreSSL 4.3.3** build
`libressl-runtime-j_dt94vs` provides all six previously missing EVP functions.
Its Cortex-A76 archive SHA is
`3a90ec330c2c5f9c55edabdabe098c39b1ca08686078cb45dc15a54968f151d0`.
The original Apple packet cipher was recompiled with matching LibreSSL headers,
not OpenSSL 3 ABI assumptions. Seven original upstream native tests and four
focused integration tests pass; 48 valid and 5,036 rejection cases execute
against static native LibreSSL, with no dynamic libcrypto fallback.
`apple-ssh-libressl-packet-9ws4lrfd` records the exact build/link outcomes.

The subsequent `apple-sysctl-runtime-nfhrya57` artifact closes `sysctlbyname`
with unchanged current Apple source and the genuine syscall 202 trap. Four
focused tests include 16,000 real host queries on eight threads, size/error
handling and twelve injected syscall failures. Actual Pi CPU-feature queries
remain unverified. The link now exposes four pthread services: `pthread_equal`,
`pthread_self`, `pthread_mutex_lock`, and `pthread_mutex_unlock`. Those services
need genuine main-thread/TSD initialization and contention support, not the
existing single-thread bootstrap maps. LibreSSL constructors also need a real
startup invocation path. See `tools/rpi5/ssh_platform_runtime_audit.md`.

The next private Apple pthread/libplatform slice compiles **14 of 15 selected
original Cortex-A76 units**, including real mutex/TSD/condition/rwlock and
platform lock/once/atomic/semaphore code. This is not all of libSystem.
`apple-pthread-platform-linkable-ydcl_6yv` manifest SHA
`c31e25c5c81d14423d3204f6e9f215f2a15f6da35b63d4dd7b378d8bce45138c`
preserves the partial archive and the main pthread unit's genuine private-header
and JIT-service compilation gaps. Linking this archive exposes eight lower-level
services: five psynch/ulock operations, the real pointer-munging token,
`abort_with_reason`, and `pthread_equal`. The target still does not link.
Four focused tests verify source/header closure, exact archive contents,
remaining imports, and namespaced original platform primitives under native
ASan/UBSan: eight host threads, 160,000 protected and 160,000 atomic increments,
one contended initializer, eight semaphore waits, and three failure cases.
These use genuine **macOS** pthread/TSD/Mach services, not a working Pi pthread
runtime. See `tools/rpi5/apple_pthread_platform_build_audit.md` for exact source,
validation artifacts and the required main-thread/startup contract.

The distinct `apple-pthread-bcm2712-qualified-x9kp1ral` successor now compiles
all 15 selected original units. It explicitly declares absent Cortex-A76 MTE
and Apple-only per-thread JIT capabilities; the original public unsupported
behavior is retained, impossible private transitions trap, and general VM W^X
is unchanged. This is a truthful Pi target configuration, not fabricated
Apple hardware. Five original wait/wake syscall emitters and the genuine
abort provider also build. Native tests cover 96,000 real syscall errors,
timeouts/wake and original abort argument/fallback behavior; psynch is not
called with invented registration state.

The genuine current and actually linked kernel registration ABI agrees across
ten fields/56 bytes; real `pthread_s` is 6,368 bytes with TSD at offset 224.
The narrow packet program technically links but is explicitly `NOT_RUN`:
forcing the real `__pthread_init` live still exposes fourteen real startup
providers, and private memcpy/memset duplicate symbols need deliberate static
integration. No runnable initialized pthread or SSH runtime is claimed.
Six focused regression tests cover the exact provenance, target ABI and native
behavior. See `tools/rpi5/apple_pthread_bcm2712_startup_contract.md`.

The subsequent `apple-pthread-memory-4idfg5qr` slice closes six of those
fourteen providers with original syscall emitters and original libplatform
memory/string implementations. Its manifest SHA is
`d229d0b2854d70b36515fc421912866067079d329e4e4bc4cb77463e0bbaa8f1`.
Only three private wrapper definition identifiers are renamed in a separate
pthread source copy; the new link has no duplicate-symbol ambiguity. Four
focused tests independently pass in 0.391 seconds, including 131,584 memory
boundary/overlap/pattern cases, 2,048 guarded strlen cases and an actual host
exit trap returning child status 37. Registration and workqueue traps are
compiled but deliberately not called with invented initialization state.
Eight genuine startup imports remain: libkernel's chroot-state owner,
host/port/thread Mach services and the two original thread entrypoints.
There is still no initialized target pthread runtime or new Pi executable.

Those eight providers are subsequently compiled from original Apple code and
matching MIG definitions in `apple-pthread-mach-linkable-9lq6yta2` (manifest
`96e38dda4d72ea8cdfe7d5a9e318dab08ed4a0a02b99eb7d11709d55ab3096af`).
The next `apple-pthread-messaging-headers-mubxo_kh` slice compiles 17 original/
generated units, including real message/reply-port and thread-entry providers;
manifest `77d1fa636ab6307ff46d0b014c0211f2695b2f3090d2fe8e2b65734fb4cd8265`.
Four focused tests independently pass in 1.325 seconds, including 24 real
macOS-kernel comparisons through the original generated host-info caller.
Both genuine libkernel and pthread initialization remain live in link checks,
with no duplicate symbols. The link now exposes ten deeper syscall, libproc,
VM/time and original logging dependencies. They are not replaced by no-ops.
The original libkernel object owns its chroot-state variable. Initialization,
kernel apple-vector/feature qualification, constructors and Pi execution remain
unproved; the partial link is not a runnable runtime.

Those ten deeper imports are now provided by eight original syscall, libproc,
VM, clock and string units in `apple-pthread-log-clock-m3ct69va`. A separate
`apple-pthread-mach-state-8rohn6p5` runtime copy removes exactly five legacy
global definitions so original Apple Mach/libkernel objects own the task port,
syscall logger and page-size/mask/shift. All other archive members are unchanged;
the accepted runtime is untouched. Both genuine initialization routines remain
linked, with **zero unresolved or duplicate symbols**. Manifest SHA:
`6f23ca213bd8760dfd79bb12bcc3c7155e7ee54e6ebef2413ff42a43aff880dc`.
Four focused tests independently pass in 1.823 seconds: full frozen closure,
exact one-member replacement, real trap/clock implementation, and native host
services (66,306 strlcpy cases, 5,120 errors, 2,048 clock bounds, socket/proc_info).
The output is deliberately `NOT_RUN_init-live`: legacy argv/TSD startup and
unwired constructor ordering still make it unsuitable for execution.

The matching Pi kernel contract is checked separately in
`apple-pthread-kernel-contract-7esv7fos`: six selected function bodies and
relocations reproduce the actual linked objects. Its real version-0 pthread
registration table points to the expected provider, and feature mask
`0x400001df` contains the current user's required bits. Static source/object
evidence covers the four-value `main_stack`, `read_random`-backed `ptr_munge`
and pinned `th_port` apple-vector paths. This is not runtime registration or
entropy-quality proof. The original non-dyld `_pthread_set_self(NULL)` is not
a valid bootstrap; original `mach_init` calls it, so the genuine
`VARIANT_DYLD` main-thread/TSD bootstrap must be integrated before ordinary
pthread initialization and constructors. Do not replace it with fake identities.

The distinct `apple-pthread-dyld-bootstrap-sskvb3j8` artifact now provides that
original DYLD bootstrap with privately namespaced definitions; only the Mach
archive's `mach_init.o` changes, and normal public pthread implementations stay
separate. It links without missing or duplicate symbols but still does not
wire or execute the new entry sequence. Manifest SHA
`75bae2177d2e9d6f93edffdfc1531699538188a5e5a51cde9d231daae88289f9`.
The extended `apple-pthread-kernel-tsd-contract-fifml3xs` audit also reproduces
the actual platform syscall, cthread-self setter and machine TSD setter,
bringing the linked-function comparison to nine; manifest SHA
`52e1a54657775a7b3712a2781501f65b9c8a7f5df8730528037e14fca0cbaef7`.
Four independent offline regression tests pass in 72.020 seconds, including
complete compile-directory-relative header membership, mutation rejection,
actual namespaced bootstrap branch/symbol ownership and final kernel dispatch.
No `NOT_RUN` target is executed. Real create/join, entry callbacks and constructor
ordering are the next runtime integration work, followed by one combined Pi test.

No SSH authentication or cryptographic check is bypassed.
**There is not yet a target packet-cipher executable, SSH daemon,
entropy qualification, or network service acceptance.** The current physical
eight-command result uses the 41-node root above; the following sections retain
the earlier 33-node attempts and their original limitations.

## Combined root trial and corrected loader — 2026-10-13

One physical attempt with the expanded 33-node/22-file root stopped at early
kernel checkpoint K, before the VM, mounted root or any userland command.
`root96-serial-20261013` records 26,606 bytes and **zero serial TX**. The linked
kernel requires a retained firmware-FDT descriptor which its ordinary loader
did not provide. The watchdog returned the Pi to NVMe Linux; independent SSH
and explicit restoration are recorded separately. Neither the SSH buffer test
nor the expanded root has passed on the Pi.

Distinct `tools/rpi5/build_root96_fdt_package.py` fixes only the loader
composition. It first reproduces the pinned retained-FDT loader's original
binary exactly, then replaces only its payload object with the unchanged
180-second kernel and unchanged expanded root. Original Device/FDT/seed
code objects, normal firmware, terminal command, and stack accounting remain
unchanged. The known-good image and failed candidate are preserved.

Corrected package: `build/rpi5/root96-fdt-euspad_2/probe.bin`, **20,139,520 bytes**,
SHA `021a49fa8f8868ccfa9de9c769bf579f5ab3ae4974f44191773bcd2d651467be`;
manifest SHA `be88d876575b84b74dc38107ecf5db5e5fd02d836f0cce4c05dbfe3423c74e13`.
Four focused tests pass (7.367s): reject the exact failed kernel/loader pair,
verify the corrected actual linked handoff and exact payload, and exercise
the actual native descriptor serialization, retained span, tree encoder and
seed transaction with synthetic fixtures under ASan/UBSan. Missing generated
or consumed-header hash maps are also rejected. The descriptor must
occur in the executable loader portion, not merely as a kernel string.
The corrected physical retry now mounts the exact 33-node read-only root and
reaches the recovery shell. However, multicore output corrupts the mandatory
watchdog marker to `SECONDkS=180`; the strict recorder sends zero bytes and
rejects the subsequent recovery boot. `root96-fdt-serial-retry-20261013`
preserves this failure, independent new Linux return and known-good restoration
are recorded separately in STATUS.md. No SSH-buffer or zsh smoke runtime pass
is inferred. A distinct telemetry-only PE kernel now emits one-shot readiness
after the first actual terminal reload; two native/closure tests pass without
extending the deadline. It is not yet a boot package or physical result.

## Original Apple SSH packet cipher, host semantics — 2026-10-13

`build_apple_ssh_packet_probe.py` preserves the original OpenSSH feature config
and compiles its actual `cipher-chachapoly-libcrypto.c`, not a feature-disabled
fallback. The host executable uses real local OpenSSL/libSystem providers and
original Poly1305/freezero/explicit_bzero code. ASan/UBSan tests pass **48**
length/sequence, in-place and encrypted-length cases, plus **5,036** per-byte
header/ciphertext/tag tampering and wrong-sequence rejections. Every failed MAC
must leave the destination untouched. Keys are fixed public test data; no live
network, random/session keys or entropy qualification.
Three focused tests pass (0.359s), including an intentionally disabled
tampering mutation which must make the rejection-test harness fail.

Artifact `build/rpi5/apple-ssh-packet-v9xoz8gd`, manifest SHA
`725eede29cd6412f4fefb8b8f3f742999f20e8bc3b30ff3c1b5316dbae8544f4`.
The Cortex-A76 cipher archive compiles, but the actual static target link is
**incomplete**: six EVP/ChaCha entry points, `memset_s` and `timingsafe_bcmp`
are absent from that link. `memset_s` has a separately built real Apple provider;
the original config expects system timingsafe_bcmp, so its fallback source
does not emit that function. Supply real providers instead of disabling
security declarations. This is host cipher behavior and a precise target
dependency result, **not** a Pi executable, complete SSH transport, AEAD
security qualification or SSH server.

## Original OpenSSH primitive executable — 2026-10-13

Separate `tools/rpi5/build_apple_ssh_crypto_probe.py` compiles the unchanged
`chacha.c` and `poly1305.c` from the same pristine Apple OpenSSH 10.0p2 checkout
`f386b2e948280f6ecac875329c0b56020821d558`. No OpenSSL feature/configuration
changes, substitute crypto implementation, runtime keys or entropy assertions.
ChaCha's intentional fixed-width 16-byte constants require one narrowly scoped
current-Clang warning suppression; the upstream source stays unchanged.

`build/rpi5/apple-ssh-crypto-_qsv492k/sshcryptoprobe` is a real static Cortex-A76
Mach-O executable, **17,704 bytes**, SHA
`1f4a41e8720e37b560fd103b0679f53a4fbee64f481765fcb59d45dddb6ca3c1`.
Manifest SHA `4a2e8e7303fe1d0f28c5a634ca04d8e132fb50350734b8a113f7180d7d2176ee`;
1,687 inherited/source pins plus 248 consumed dependency paths checked before/
after compilation. It links the preserved real startup/syscall/runtime
archives with zero undefined symbols and no dyld imports. The original
primitive archive is also preserved alongside it.

Native ASan/UBSan runs pass the ChaCha all-zero block and Poly1305 known-answer
vectors from [RFC 8439](https://www.rfc-editor.org/rfc/rfc8439), 12 length/
in-place/guard-byte cases and empty-message Poly1305. Three focused tests pass
(0.603s), including separately corrupted expected answers that must fail.
OpenSSH's original ChaCha here uses a **64-bit nonce**; the zero-state vector
overlaps the RFC layout, but does not prove its 96-bit-nonce/IETF AEAD
construction. This is primitive build/host evidence, **not** general crypto
security qualification, entropy, SSH transport/authentication or Pi execution.
The diagnostic is deliberately not added to the pending 33-node RAM-root trial.

## Static SSH buffer executable and current Apple source review — 2026-10-13

The actual Cortex-A76 executable now links successfully with real Darwin
startup/syscalls, the corrected OpenSSH 10.0p2 buffer objects and original
Apple runtime providers. `build/rpi5/apple-ssh-probe-v2-1tmwow6z/sshbufferprobe`
is 106,664 bytes, SHA256
`8b311da88fa7bf19bd7b7d0ad098186f196022afdc7aa2ef6b759d1d4cdbf17e`.
Its manifest SHA256 is
`623944b390cb778643ad9c8e8939e285a2ebb11eabee5a1d23896a103878d038`.
The distinct v2 builder captures all newly consumed compilation dependencies
before/after compilation: 303 dependency paths, 1,615 unique input paths and
71 generated output entries match. The original v1 artifact is retained.

Five focused tests pass (0.451s), recorded in
`build/rpi5/ssh-static-audit-9rmjl_l7/validation.json`. Actual target bytes
verify LC_UNIXTHREAD entry, stack/TSD/Mach startup, entropy setup, argv dispatch,
normal exit, real syscall numbers/error handling and secure-erasure calls.
No unresolved symbols or dynamic imports remain; the unused single-thread
pthread key adapters are dead-stripped. A separately compiled native probe
runs with the actual preserved OpenSSH objects and ASan/UBSan. Apple's modern
`memset_s` implementation passes boundary, error and erasure tests. These native
tests do not execute the target static program or qualify SSH transport/auth.

The current public Apple repositories were also fetched into separate Pi-only
directories. Libc main is `71bbe350ab79eef58113991d817ccc6165061a64`
(`Libc-1752.100.10`); syslog main is
`69d8586e9a599c304e1b702a9c2830e2f78126d5` (`syslog-406`). Current
`libsystem_asl.tproj/src/syslog.c` requires real ASL, os_log and pthread mutex
services and includes libdispatch/private logging headers. Modern raise and
strsignal require real pthread signalling/TLS/once support. Those dependencies
must be implemented before adopting the routines for production services.

This bootstrap executable therefore retains the explicitly selected historical
Apple logging/signal providers alongside modern memset_s and the original
OpenSSH vis fallback. Narrow SDK cast/bracing corrections affect generated
copies only and are recorded as diffs. The fopen extension-symbol alias is
limited to historical BSD fopen behavior; modern extension modes and threaded
logging are unqualified. These are bootstrap limitations, not an OS-wide
decision to replace modern Apple code with older libraries. Prefer current
Apple implementations as their actual runtime dependencies become available.

Next package the diagnostic at `/usr/local/libexec/xnu/sshbufferprobe` in the
expanded Pi RAM root, retaining `/bin/zsh` and the recovery init, then execute
it on the board. Full SSH still requires crypto, authentication, accounts,
privilege separation, PTY/session behavior and Ethernet wire traffic.

## SSH reset correction — separate overlay, 2026-10-13

The previously reproduced low-maximum reset failure is corrected **only in a
new, explicitly modified source overlay**. The pristine Apple checkout, original
archive and failing original reproducer remain unchanged and hash-verified.
This is a local correctness correction, not an upstream submission or security
severity/exploitability claim. It does not complete the SSH runtime or Ethernet.

`tools/rpi5/patches/sshbuf-reset-max.patch` preserves notices and labels the Pi
port change. `sshbuf_reset` now chooses reset allocation
`min(retained max_size, initial allocation)` rather than unconditionally
growing a small-limit buffer back to 256 bytes. Normal-limit behavior is
unchanged. Failed reallocation leaves the old valid allocation intact and still
zeroes it; read-only/parent early-return behavior and actual fatal sanity checks
are retained, not bypassed. The build mechanically verifies **all bytes outside
the reset function are unchanged**, then compares the actual production global
definition and external-dependency sets with the original archive: both match.
No new production stub, failure wrapper, crypto/config change or native-host
service import is added to the ARM64 archive.

`tools/rpi5/build_apple_ssh_buffer_reset.py` builds distinct real Cortex-A76
objects from the one corrected unit plus 11 original support units. Accepted
artifact `build/rpi5/apple-ssh-reset-7j7hbjqx/`:

- `libapple-openssh-buffers-reset.a`: **105,472 bytes**, SHA256
  `51596ace4b0cc892114f12127ef032c8d2c58fc86a623583d4ec02a455db0866`.
- Manifest SHA256
  `9cb33eed73cb696a2f3904d86c86dfd3568417a2e8008602fc9f065851461cd9`;
  patch SHA256
  `1c84b3afe485ba954fc0c32cec79f6b1ad232554ca943f47e7012dd26f17e49f`.
- **1,587 unique pins** (1,466 inputs, 312 headers and 121 generated entries,
  with overlaps), including the complete original accepted artifact, match.
- **Three focused tests pass in 2.559 seconds**. Native ASan/UBSan exercises
  capacities **1 through 512, 1024 and 4096** (514 cases), three rounds each,
  bound rejection, zero length/retained maximum, full allocated-byte zeroization,
  reuse after reset and unchanged read-only/parent-child behavior. Original
  ordinary buffer tests also pass with the corrected objects.
- An **additional host-only allocator interposition** rejects exactly one reset
  reallocation while all other calls use the actual original recallocarray.
  It verifies retained pointer/allocation/maximum, complete zeroization, continued
  put/get and a later successful shrink. Production target/native-normal objects
  have no renamed allocator or injected callback.

The same unchanged original `--low-max-reset` harness, linked against corrected
objects, now reaches its intentional **return-7 sentinel** after len/free instead
of the original **SIGSEGV / return -11**. Return 7 is not itself a generic test
success: the new 514-capacity harness independently returns zero. Original
failure evidence is preserved, not retrospectively relabeled. All results are
native host/compile evidence; no Pi execution, static target service closure,
full SSH binary or crypto implementation is claimed. No broad suite was rerun.

Next derive the **reachable** target buffer/runtime link, including actual
startup/syscall adapters rather than interpreting the earlier conservative
three-archive name inventory as missing APIs. Reuse real original providers for
secure erasure, signals/raise, error/logging and allocation, preserving failure
semantics. Then genuine public crypto/entropy and complete process/auth/privsep/
account/session/PTY integration. Original config declarations and Apple path
conventions remain requirements, not proof of implemented services. Existing
VM/Pi roots, kernels, images and firmware tooling (all 16 prior source pins)
remain unchanged; no board, SD, serial, network setting or reboot action. The
full Ethernet/zsh/TTY/SSH/Apple CLI objective and separate Gate 4 hold remain.

## SSH dependency implementation — original Apple source, 2026-10-13

Fetched the public Apple OpenSSH repository into a **new Pi-only checkout**,
`build/rpi5/apple-openssh-candidate-20261013`, pinned pristine at
`f386b2e948280f6ecac875329c0b56020821d558`. Its version header is
**OpenSSH_10.0p2**. This is the inspected Apple snapshot, not a claim that it is
the latest upstream OpenSSH or that its macOS integration exists on the Pi.
The completed VM workstream, sources and frozen artifacts remain untouched.

`tools/rpi5/build_apple_ssh_buffers.py` now builds **12 unchanged original
source units** for ARM64/Cortex-A76: SSH buffers/basic get-put/error messages,
original explicit-zero/freezero/recalloc helpers, full misc/signal/log/xmalloc/
pattern-matching/fatal/cleanup code. Original `config.h`, copyright notices and
licenses are preserved. No replacement signal/log/allocation stub or modified
vendor function is introduced. The original configure.ac unused-parameter
warning exception is retained with Wall/Wextra/Werror; other build warnings
are not suppressed. Static dependency objects disable fortify/stack protection
as explicit diagnostic inputs, **not a production-server hardening decision**.

The original config retains WITH_OPENSSL, PAM and Darwin sandbox declarations.
These are **not proof of Pi capabilities**. Public local OpenSSL **3.6.5 headers**
are compile inputs only; no OpenSSL/LibreSSL crypto runtime is linked and no
crypto policy is weakened to obtain success. Apple's additional Xcode
integration macros are not enabled in this portable dependency profile.

Accepted archive `build/rpi5/apple-ssh-buffers-_2f0fe7x/`:

- `libapple-openssh-buffers.a`: **105,456 bytes**, SHA256
  `de8d50030e23cb1d612caa6b65ada88b2ddcb431c3d70ac446a9b5cc38917f35`.
- Manifest SHA256
  `6c0cf849532749ea53ca6c7363ff6c779aef6fb31671a630228d5c4426157cca`.
- **1,461 unique pins** (1,105 source entries, 312 header entries and 94 outputs,
  with overlaps) reverify, including the entire tracked upstream snapshot and
  three unchanged read-only static runtime archives. Every target object is a
  real thin ARM64 Mach-O object. No root/kernel/image was changed or packaged.
- **Three focused tests pass in 2.148 seconds**. The actual original code links
  with native host libSystem/ASan/UBSan and passes byte-order integer roundtrip,
  string roundtrip/truncation/embedded-NUL refusal, read-only child lifetime,
  maximum-space/over-consume bounds and error-string checks. Native host
  service linkage is **not** static Pi runtime closure or Pi execution.

**A distinct original-code failure is preserved, not waived:**
`sshbuf_new → set_max_size(16) → reset → len` terminates with **SIGSEGV** in the
real sanity/signal/raise path. Source inspection shows reset growing the
allocation back to the initial 256 while retaining maximum 16, violating its
own invariant. The normal buffer tests use a fresh buffer after the independent
small-capacity bound check; the failing reset case remains a separate executable
reproducer with saved return code/stdout/stderr. No vendor patch, remote-
exploitability claim or security severity is asserted. The dependency is not
declared fully validated merely because the three focused tests pass.

Measured **conservative** selected-object symbol inventory: 100 external names,
35 present and 65 absent in the three preserved runtime archives. These counts
include unused functions from full misc/log/match units. They exclude separate
syscall/startup adapter objects, so **65 is not a count of missing Pi APIs**.
An archive symbol name is only a possible provider, not transitive linkage,
correct ABI/service behavior or current-kernel proof. The next target link must
derive the actually reachable dependency set. Current candidates include real
secure erasure (`memset_s`), signal/raise/error reporting and logging dependencies;
do not replace them with always-success functions or native host libraries.

The actual Apple build inputs also identify larger closure requirements:
`xcconfigs/openssh.xcconfig` names LibreSSL/libcrypto, PAM, BSM audit, resolver,
zlib and Foundation/Kerberos/OpenDirectory/optional Apple integrations. The
shipped launchd plist uses `/usr/libexec/sshd-keygen-wrapper` and socket
activation. Modern source splits server/listener, session and authentication
executables; original paths place `ssh` under `/usr/bin`, `sshd` under
`/usr/sbin`, helpers under `/usr/libexec` and configuration under `/etc/ssh`
(Darwin's `/private/etc` convention must be honored when aliases exist).
This is a source-backed inventory, not an installation or promise that private
Apple services can be supplied by the static runtime. Any eventual portable
profile must be explicit and retain genuine crypto, entropy, privilege
separation, credential/account checks, host-key/config handling and session/PTY
semantics. Original INSTALL/README.privsep and licenses remain authoritative.

**Next:** close the actual reachable target buffer dependencies; assess the
preserved reset/max invariant failure in a separate overlay; build/pin a real
public crypto implementation and validate target entropy, then full process/
privsep/authentication/account/PTY/service integration. Working SSH still
requires the independent Ethernet path and real wire traffic; existing loopback
socket evidence is not that result. RAM-root utilities and zsh/TTY work remain
active independently of the separate Gate 4 durability hold. No Pi, SD, serial,
firmware, network configuration, VM image or reboot action occurred in this
offline dependency step. See the archive's `validation.json` for exact limits.

21:53 UTC: a distinct runtime-identity/socket trial physically passes and its
raw transcript independently replays: mounted-root/file hashes/devfs overlay,
original zsh script, Unix stream sockets and IPv4 loopback UDP/TCP payload/
peer/half-close tests, then live recovery. No interface configuration, manual
cold cycle or soak. This is not full socket/TTY, Ethernet, SSH or Gate 4 exit.
[Physical socket milestone](GATE6-SOCKET-IDENTITY.md#physical-result--2153-utc).

20:20 UTC: original Apple ifconfig/route physically execute at `/sbin` paths
in a separately guarded same-boot diagnosis; zsh script/recovery remain working.
Strict fresh-mount trial remains failed, Ethernet/SSH unproven.
[Physical evidence and exact scope](GATE6-APPLE-NETWORK-PHYSICAL.md).

## Original Apple utility reuse — 2026-10-12

The user's reuse-first instruction is now explicit in the plan. A distinct
unstaged 27-node Pi RAM root adds unchanged Apple-source ifconfig/route while
preserving every accepted zsh/recovery/statprobe byte/mode. Exact build/source/
archive pins, pristine checkouts and original constructors verify; no VM init,
kernel/EFI/data disk or shutdown import. It is not a Pi execution or networking
claim. [Artifact, source pins and next ABI/runtime trial](GATE6-APPLE-TOOLS.md).
Prefer original file_cmds/shell_cmds selections next, not replacement commands.

## Corrective physical checkpoint — 2026-10-12 19:03 UTC

The original zsh script now **passes** on the Pi with exit zero, alongside raw
stat/lstat/fstat success and interactive version/builtin/external-exec/recovery
acceptance. The distinct corrective trial passed strict mounted-root admission
and independent raw replay after one protected software SD boot. Frozen zsh and
RAM-root content are unchanged. See [physical correction](GATE6-METADATA-PHYSICAL.md)
for current image/backup/capture hashes. This supersedes unresolved/current-OS
notes below, which remain chronological history; no old failure is reclassified.
Broader TTY/signals/job control/runtime, SSH/distribution and networking remain
open. Gate 4 durability is still held; no new cold boot/soak is required here.

## Prepared file-ABI diagnosis — 2026-10-12

The next zsh investigation is implemented as a separate read-only raw
stat/lstat/fstat/open/F_DUPFD utility with fixed controls and no fabricated
success. A distinct additive 25-node root and boot package preserve every
accepted recovery/zsh file and reuse the proven kernel. The package passes
29 host preflight checks; it is **not staged or Pi-executed**. See
[raw diagnostic artifacts and next trial](GATE6-STAT-DIAGNOSTIC.md).
The original script failure remains unresolved and Gate 4 stays held.

## Physical checkpoint — 2026-10-12 16:40 UTC

Interactive zsh 5.9 now has actual Pi evidence: computed version/array/arithmetic,
external exec, returned prompts, and exit to a live recovery shell. The original
script-file trial failed and remains unresolved; a same-boot diagnosis observed
the script as existing/readable but not regular. This is not complete Gate 6.
See [physical trial and recovery evidence](GATE6-PHYSICAL-ZSH.md) for exact
package/install/capture hashes and the next stat/open/F_DUPFD diagnosis. The
distinct zsh package is now staged; earlier unstaged descriptions below are
historical. No Gate 4 durability or Ethernet acceptance was added.

## Continuation — 2026-10-12 15:39 UTC

`audit_zsh_pi_binary.py` now inventories the actual pinned executable's complete
file-backed instruction section and raw SVC encodings, checks disassembly
coverage/continuity, and resolves only an immediately preceding MOVZ/MOVN X16.
The preserved zsh contains 143,591 instruction words and 69 trap sites:
66 BSD, 2 Mach and 1 platform TSD trap. Each has a locally resolved immediate;
all BSD/Mach numbers have one non-stub declaration in the **current source**.
The inventory records two TPIDRRO_EL0 reads (errno) and two FPCR reads (strtod).
No word decoded as unknown with the selected Cortex-A76 disassembler option.

This is not architectural feature validation, control-flow proof, preprocessor
evaluation, or binding of source tables to the installed kernel. It does not
prove the syscall argument/result contracts or Pi execution. The current source
has platform syscall subcode 2 -> cthread/TSD setup, Mach traps 28/89, and 16-KiB
own-task VM conventions consistent with the preserved adapters. The Pi's actual
startup/entropy/TSD, signal return, VM, FP/SIMD context and serial TTY behavior
still require review/board acceptance. Inventory:
`build/rpi5/zsh-pi-binary-audit-20261012-v2.json`, SHA256
`678eb2d2c2c8ca1f4efe71eb3dd24f23b83026f7e72bab18a0275c45e2487f3f`.
The earlier non-v2 report remains historical, not overwritten.

`prepare_zsh_trial_root.py` prepared a **distinct, unstaged** Pi root in
`build/rpi5/zsh-pi-trial-root-20261012`. It preserves every one of the proven
Pi root's 14 files and modes, including init, `/bin/sh` and all utilities.
Only `/bin/zsh`, the capsule's read-only dumb terminfo, and a new read-only
`/etc/zsh-smoke.zsh` are added. No VM init/poweroff, VM EFI image or firmware
variables are imported. Init still starts the proven recovery shell, not zsh.
The smoke script computes version/arithmetic/array output and runs the preserved
external `/bin/echo`; its presence is not evidence it executed or returned an
interactive prompt.

Prepared root: 1,392,640 bytes, 24 nodes, SHA256
`ddbdffe24f4441985cadf5aa1556d2b409e0c8a39d6d86dd5352d49814712e08`.
Manifest SHA256
`f5afe7b7278136cc955ae4767061463740d6a96d7a168fdfa7d37d48ecc80654`.
The frozen capsule and original Pi root retain their previous hashes. Five
inventory tests and three preparation tests pass, including malformed section/
mapping/coverage, raw-SVC disagreement, unresolved/cross-symbol setup,
conditional source variants, file preservation, collision/pin/recovery failures.

No boot image was built/staged and no kernel, serial, SD, Pi or VM operation
occurred. Next close ISA/ABI review and the Pi-specific trial guard, package a
separate recovery-backed image and run the bounded actual serial acceptance.

## Previous structural checkpoint

2026-10-12. The user authorized networking and other independent gates while
Gate 4's cache-state/durable-write test is held. A read-only RAM-backed zsh
milestone need not wait for writable storage or Ethernet. A persistent Darwin
distribution and SSH remain larger milestones, not prerequisites to a serial
shell.

## Reusable inputs and limits

The separate VM workstream already documents real Apple-distributed zsh 5.9
execution in [its VM milestone](../../experiments/darwin-container/userland/ZSH-TRIAL.md).
Its frozen `zsh-working-2026-10-12` capsule remains unchanged. The selected
runtime is a static subset with labeled project startup/syscall/VM adapters,
not full libSystem or an Apple-supported OS combination. Do not count a VM
result as Pi evidence or copy the VM EFI disk/loader onto the Pi.

The locally inspected manifests identify these reusable source selections:

| Component | Existing pinned selection | Pi work still required |
| --- | --- | --- |
| zsh | `zsh-118`, commit `666e91a595af505ef61d5f9b87df7a014a4937c6` | A76 ISA, startup/syscall/console audit and actual Pi execution |
| Libc | `Libc-167`, `Libc-391`, `Libc-1752.120.2` subsets | Selected wrappers, allocator, locale and signal/VM assumptions |
| libplatform | `libplatform-375.120.2` subset | Target instruction/ABI review |
| Libm | `Libm-93`, `Libm-2026` selected portable sources | Preserve exact selected source/build adaptations |
| Terminal support | Preserved source-built archive/terminfo and manifest | Pi serial behavior and terminal-capability tests |
| Init/utilities | Explicitly project-authored static bootstrap, not Apple launchd | Keep Pi readiness/recovery/watchdog protocol and correct shutdown behavior |
| dyld/full libSystem/OpenSSH | Not closed by the static zsh milestone | Separate source/version/license/dependency, service and networking work |

The presence of downloaded libmalloc/libpthread sources is not evidence they
are linked into this static runtime; the kernel pthread provider is not a
userland library. Original notices and licenses remain authoritative. No
source-license audit or new dependency download was performed here.

## Completed structural preflight

`tools/rpi5/check_zsh_ramroot.py` reuses the **Pi** RAM-root and static Mach-O
validators, pins both complete input hashes, and verifies executable `/bin/zsh`
is byte-identical to the supplied static binary. It writes only an optional
new local JSON report, never an image or existing report. It has no serial,
SSH, media or reboot path. Synthetic fixtures are not source-authenticity proof.

The preserved capsule passed on 2026-10-12:

- RAM root: 1,163,264 bytes, 18 nodes, `RPI5RFS1`; SHA256
  `9c15abc1254963a9681eadf7fa0924cb0a1cd0425565210ac3b32e07f47c95ec`.
- zsh: 764,288 bytes, thin static arm64 Mach-O, four segments, no unresolved
  imports/dynamic-loader commands; SHA256
  `78d947f6a08e26ceebbf275a7e15479aabbc61645ac407c546b1a82e74b437e5`.
- Report: `build/rpi5/zsh-ramroot-preflight-20261012.json`.

Run `python3 -m unittest tools.rpi5.tests.test_zsh_ramroot
tools.rpi5.tests.test_ramroot tools.rpi5.tests.test_prepare_pid1 -v` on one line:
17 tests pass, including malformed roots, wrong pins, missing/nonexecutable or
mismatched shells, static executable checks and the sanitized native RAM-root
metadata parser. **No Pi zsh boot was performed.** Structural compatibility
does not establish ISA, syscall, console or startup compatibility.

## Revised finite sequence

1. Audit preserved zsh/runtime ISA and actual syscall/startup/signal/VM
   dependencies against the BCM2712 kernel; retain concrete mismatches rather
   than importing VM-only platform assumptions.
2. Prepare a distinct opt-in Pi RAM root with existing Pi readiness markers
   and recovery interpreter preserved. A zsh prompt does not emit the current
   bootstrap interpreter's command/nonce protocol; adapt the trial guard before
   sending input. Do not reuse a storage-write recorder for this trial.
3. Build/package with fresh provenance and recovery backups, then one bounded
   Pi serial trial: computed version, arithmetic/array builtin, external exec,
   and returned prompt. No durability, network or repeated soak claim.
4. Continue network service/userland closure and writable root/history after
   their separate hardware dependencies are proven. Static zsh success alone
   does not complete the original Gate 6 distribution exit.

No excluded VM workstream file was edited or VM relaunched for this preflight.
# Genuine Apple startup and four-thread diagnostic links — 2026-10-13

Distinct `apple-pthread-static-complete-gm82fjkz/NOT_RUN_pthreadprobe`, SHA
`bc882d7d3ca236d9f649292b9a64aebb6669a1b9f3ee0806c61d21c7f418ba15`,
manifest `4a22b183000378e842d59c643ed1f8a80a520e1e77d62370880a7c095adfc35a`,
now links without undefined or duplicate symbols. Its static entry calls
original libkernel initialization, genuine DYLD main-TSD bootstrap through
Mach initialization, ordinary Apple pthread initialization, allocator setup,
late initialization and the actual Mach-O constructor list before the workload.
It uses the real public cancellable `pthread_join` and original syscall-333
emitter; old fake TSD/startup and duplicate allocator ownership are removed only
from two private archive members. Accepted runtime and older artifacts stay
unchanged.

Five focused tests independently passed in 0.618 s: complete source/generated/
header membership and mutation negatives; exact private member changes; actual
LC_UNIXTHREAD/constructor pointer and call ordering; real symbol ownership and
cancellation emitter; native adapter/workload. Distinct native bounds artifact
`apple-pthread-static-native-bounds-65neccqr`, manifest
`4a3f15122ded6e16c649d286780ce807029fd81d6d7ce00c86edceb13332024d`,
retains 16 argument/vector cases and host thread/allocator checks.
Native execution uses host pthread/zone providers, **not** target Apple pthread.
Independent source review found no blocker for the bounded four-thread probe;
default-zone allocation and selected static constructors do not establish full
libSystem, multi-zone compatibility or a working SSH service.

The real probe is now packaged at `/usr/local/libexec/xnu/pthreadprobe` in
`root96-pthread-batch-go4g0fe7`, a separate 42-node/30-file root. Its image SHA
is `9ddbbd5701ca890e97f3f5aefd4c3c0c47434fb50a34bbce51d11e77141b94fd`;
manifest `69d562664e6477570edca65e973daed65f48b50393a446a1287d7d651ba641a0`.
It adds only this executable and regenerates the identity catalogue; other
baseline file contents remain unchanged.

Distinct tagged loader `root42-pthread-ulws4mq6/probe.bin` is 20,614,912 bytes,
SHA `cb7f1e139228be125f81adc854d11fa3607347f7046d8cb6c129801770c00d08`,
manifest `c45503701eaed84be939e72ddb2afb0e45af86f3d5260f1212a40eca90fcb8be`.
It retains the ready-delay kernel `c00bc525…`, four-CPU startup, normal firmware,
180-second terminal deadline and real retained-FDT/device handoff. Exact marker:
`ROOT42_PTHREAD_TRIAL TAG=ba6a809372b04d5a80ec96b2a12a375b CPUS=4 ROOT_NODES=42 WATCHDOG_READY_V2`.
Three full/native/negative package tests pass in 55.835 s, including actual
kernel/root/loader extents, serialized FDT/map decoder, three live-overlap
rejections, full input/header/generated closure and wrong-root/tag/deadline
rejections. Old builder/checker sources are hash-pinned, untouched; the new
private adaptation changes root selection and unique tag/count/package names.

Next run the prior eight commands and new probe in the same bounded zsh batch
with the strict corrected output oracle and actual process-exit query. Pi
startup/create/join/TSD/destructors, kernel entropy qualification, network
packets and SSH remain unproven. This package has not been staged or booted.

