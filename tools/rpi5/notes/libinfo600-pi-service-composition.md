# Current Apple Libinfo: real providers and a Pi service boundary

This is an offline source/build audit, not an installed account service or an
SSH execution claim. The accepted Pi images and SSH configuration were not
changed. Native tests do not query the host's account database or perform DNS.

## Pinned original sources and useful results

Official [Apple Libinfo-600](https://github.com/apple-oss-distributions/Libinfo/tree/39b70c515baee5b609e7e91693edbd934b6845a1),
commit `39b70c515baee5b609e7e91693edbd934b6845a1`, is preserved in
`build/rpi5/apple-libinfo-main-candidate-20261013`. This supersedes, without
altering, the old Libinfo-542.40.3 experiment. All tracked files were checked
against the fetched commit before the inventory build.

The original macOS configuration inventory is
`build/rpi5/apple-libinfo-current-kdmwyk4q/manifest.json`, SHA256
`a4f36e835877087e9bfc5fbafa73d2f0749f4bc722a9d001b9a0c9640e9f9443`.
It preserves CONFIG_MAC, DARWIN_DIRECTORY_AVAILABLE, DS_AVAILABLE and
SYNTH_ROOTFS. Seven of fifteen selected original translation units compile.
The whole unchanged OpenSSH client link drops from 54 to 51 unresolved imports:
real `getifaddrs`, `freeifaddrs`, and `h_errno` now have providers. There are no
new imports or duplicate symbols in this step. No claim is made that the
remaining eight TUs compiled.

The numeric/account parser artifact is
`build/rpi5/apple-libinfo-numeric-f893rytw/manifest.json`, SHA256
`4eabb37da4c78195671150c37342f2021582c7ad7a4194bd960d5929596d1a2c`.
The unchanged complete `si_getaddrinfo.c` compiles after supplying two exact
existing XNU `bsd/netinet/in_private.h` IPv4-class macros through a private
header, with the original notices retained. It also compiles original current
Apple Libc `inet_addr.c`, `inet_ntop.c`, `inet_pton.c`, and `inet_ntoa.c`.
The complete client gains `freeaddrinfo`, `gai_strerror`, `inet_ntoa`, and
`inet_ntop`, but reaches three real checked-libc dependencies:
`__snprintf_chk`, `__sprintf_chk`, and `__strcpy_chk`. Thus the measured remaining
count is **50**, not 47. The fortify checks were not disabled.

Five focused tests pass. They independently check actual scanned/consumed
header membership, all pinned bytes, original source identity, exact link
composition and diagnostics, and rerun the ASan/UBSan native fixtures:

- Six user and three group packed-record cases, fifteen rejections, genuine
  original `LI_ils_create` packing and `si_item_retain/release` ownership.
- Sixteen numeric-host and nine numeric-service cases, IPv4 shorthand and
  strict trailing-text policy, IPv6/mapped/loopback/passive forms, a small-buffer
  error, two error strings, and real freeing of a two-node addrinfo chain.

These tests reach the original private parser routines, not a replacement
parser. Native libc/pthread/allocator services remain an explicit host boundary.
They **do not** prove public `getpwuid/getpwnam/getaddrinfo`, OS account-file
access, DNS, network interfaces on the Pi, or the final full SSH executable.

## Completed, separate Pi file-backed composition

The later selected profile is
`build/rpi5/pi-libinfo-files-wj7_spx1/manifest.json`, SHA256
`544943437813436add20988cbbca221f4aafb37da3b6815244a0d2c664a5bc9e`.
Its `libpi-libinfo-files.a` compiles ten current original core TUs with explicit
Pi overlays, not the macOS inventory. It selects real cache/file/search modules,
rejects unavailable modules with NULL/ENOTSUP, and chooses the existing
stat/fstat/mtime validation branch instead of pretending a notify service exists.
Original account-file selection, result ownership, pthread TSD/destruction and
locking remain. An exact original private dispatch enum supplies only the
declaration required by this build; it is not a runtime provider.

The fixtures use disabled-password records and Darwin paths: root has
`/var/root` and `/bin/zsh`, and the fictional user has `/Users/sandrzej`.
They exist only in the artifact's isolated fixture directory. The native test
redirects file paths to these fixtures and exercises both original euid policies
without changing host credentials or reading host accounts. Four host threads
perform 512 account iterations, with real public user/group, service, numeric,
named-host-file and missing-file paths. It never calls the host group-setting
syscall. Five focused tests passed again in 2.021 seconds; this includes 320
typed-payload alignment cases and complete byte/header membership validation.

The original variable-data packer put pointer/gid arrays after unaligned strings.
The actual failing ASan/UBSan public-call artifact
`pi-libinfo-files-v3oq5pjg` remains intact. A private two-pass overlay adds matching
eight-byte payload padding and checked added-padding/aggregate arithmetic.
It does not claim universal constructor size safety: original per-list size
arithmetic and stable-input assumptions remain. The unrelated original format
`1` second-pass header issue is not used by these fixtures and was not changed.

An initial clean prototype, `pi-libinfo-files-8tiqz9yr`, allowed the original
libnetwork path-check to load dynamically for an ordinary named host. It is not
selected as proof of no external service activity. The final fixture supplies
the original `AI_PASSIVE` flag and binds native `dlopen` to an abort-only negative
boundary. The actual target implementation is unchanged and still reports its
real dynamic-network dependencies. Native libdispatch/Blocks, pthread, allocator,
I/O and logging remain explicit host boundaries, not target qualification.

This composition closes six existing imports (`getaddrinfo`, `getnameinfo`,
`getpwnam`, `getpwuid`, `getservbyname`, `initgroups`) but exposes 23 real internal
dependencies, so the whole unchanged client moves **50 to 67**, with no duplicate
symbols. Source declarations and successful host fixtures do not make this a
complete target service. Actual dispatch_once, notification/interface services,
logging, group-setting syscall and other file/string providers remain necessary.

## Current checked-libc provider composition

The selected successor is
`build/rpi5/apple-fortify-runtime-punnvr0c/manifest.json`, SHA256
`adcab45b4082c864520a6101d4fc5efa8e2ada095aa1a23b4dbc01aaeb3cc365`,
archive `libapple-fortify.a`. It compiles nine complete original current Apple
secure TUs; only `strcpy_chk.c` has a narrow correction moving its length/bounds
and overlap checks before its copy. A real four-byte allocation demonstrates
the preserved original copy-before-validation heap overflow under ASan.
The selected private crash header consists of exact original declarations and
macros; the real Apple crash callback and caller's hardware trap remain.
Original `PR_13085474_CHECK=0` policy retains overlap checks rather than disabling
them for old macOS application SDK versions. Existing memcpy overlap policy and
other original semantics are not silently changed.

Four focused tests pass, including 12 successful cases, 14 fatal child processes,
callback-before-original-trap proof, untouched-destination checks where promised,
the original heap-overflow negative, actual Cortex-A76 provider relocations and
exact source/generated/compiler dependency membership. This is local compiler
and native correctness evidence, not execution on the Pi.

The earlier artifact `apple-fortify-runtime-5zejwq5n` is deliberately retained
but **must not be admitted as a target provider**. SDK consumer fortification
re-fortified the provider implementation: target checked memcpy/memmove/memset
formed self-loops, even though the namespaced host fixture passed through real
host checked providers. Target inspection caught this boundary error. The
successor pins and applies the original Apple `xcodescripts/libc.xcconfig`
provider-only `_FORTIFY_SOURCE=0` setting. No OpenSSH/Libinfo consumer flags are
changed. Tests require the target's actual `_memcpy`, `_memmove`, `_memset`,
`_stpcpy`, `_vsnprintf` and `_vsprintf` calls, not namespaced host success alone.

The whole-client link appends this archive and the independently tested original
Apple selected reallocf/crash and Blocks archives. It closes twelve existing
imports and exposes `_stpcpy`, leaving **67 to 56** unresolved, with no duplicate
symbols. No recursive checked-wrapper workaround is added. Actual dispatch_once,
destination comparison, logging, notifications/interfaces, resolver, GSS and
dynamic-loader dependencies remain explicit. The original full SSH feature
configuration, main, authentication and crypto sources are unchanged. There is
no completed static ssh executable, target execution, live key or network claim.

## Original hooks and what they actually permit

`lookup.subproj/search_module.c` supports `/etc/sysinfo.conf` only when
`SYSINFO_CONF_ENABLE` is exactly `1`. Categories include `default`, `user`,
`group`, `grouplist`, `host`, `service`, `addrinfo`, and `nameinfo`.

However, the original constructor builds its default module list **before**
reading that file. The actual list is cache, optional DarwinDirectory/MUser/DS,
then **mdns, file**. The comment has a different order; the array governs.
`si_module.c` also contains an unconditional `mdns` static-module entry.
There is no corresponding original `MDNS_AVAILABLE` switch in those files.
Omitting DS_AVAILABLE and DARWIN_DIRECTORY_AVAILABLE is a supported original
feature selection, but it does not remove mDNS. A file-only sysinfo.conf is not
by itself a link/startup independence proof.

A narrowly named **project Pi platform composition** can legitimately select
Apple's real file backend, with its original lookup/failure semantics, without
claiming the macOS module inventory. The requirements below motivated the
separate completed profile above; target runtime dependencies remain open:

1. Preserve this unmodified macOS-profile audit.
2. Make an exact source-derived Pi-only module/default-list overlay that omits
   unavailable providers, rather than defining fake successful module objects.
   Retain real cache/file/search providers and document unavailable DNS.
3. Provide a deliberate `/etc/sysinfo.conf` (for example `default: cache file`
   and explicit account/host categories) plus the enabling environment in the
   real startup. The dispatcher must still reject unknown/unavailable lookups
   honestly. Test the actual original selector, not merely presence of strings.
4. Supply actual `/etc/passwd`, `/etc/master.passwd`, `/etc/group`, `/etc/hosts`
   and `/etc/services` under Darwin conventions. Do not fabricate authenticated
   users or infer a password database from a demonstration record.
5. Build and test the real dispatch-once/Blocks ownership, per-thread result
   lifetime, cache validation, and public getpwuid/getpwnam/group/numeric paths.
   Selecting files does not make these runtime contracts disappear.

The root distinction matters: the unchanged file backend opens
`/etc/master.passwd` (ten fields) when effective uid is zero, and `/etc/passwd`
(seven fields) otherwise. A missing file yields NULL; it does not invent a
root account. Groups come from `/etc/group`. The native parser fixture uses
locked, fictional records only and does not install them.

Account/group cache validation already has a genuine stat/fstat/mtime path.
Hosts/services/protocols are hardwired to notify-based validation in the
original constructor. A future Pi profile must either supply a real notify
service or deliberately select and test the existing stat-validation branch;
it must not stub notify as successful or silently accept stale cached records.

## Remaining macOS-profile gaps, not automatic Pi requirements

Actual compile diagnostics name these missing private headers:
`mach-o/dyld_priv.h`, `dispatch/private.h`, `os/feature_private.h`,
`net/netsrc.h`, `xpc/private.h`, `dns_sd_private.h`, and
`DarwinDirectory/RecordStore_priv.h`. Providing declarations is not equivalent
to providing the called services.

- DS uses XPC/bootstrap/OpenDirectory/MIG services. This is not a required Pi
  identity source if the Pi explicitly composes the file backend instead.
- Current DarwinDirectory uses a local record-store API plus feature/variant
  checks; it should not all be described as a missing daemon.
- mDNS and resolver paths require real DNS-SD/resolver/notification and network
  services. File-only/numeric operation does not constitute working DNS.
- Current file/search constructors use real dispatch_once and Blocks; public
  lookup stores real thread-specific result ownership. The existing genuine
  pthread startup is useful but does not itself supply libdispatch.
- Original Apple OpenSSH main calls `si_destination_compare` for its AF_UNIX
  logging initialization **before** option parsing, then requires a real account
  lookup. Its current comparison implementation initializes actual logging,
  mach timebase and atfork handling; normal route comparisons additionally use
  PF_SYSTEM/SYSPROTO_CONTROL with netsrc/ntstat. Do not redirect this to the
  separate no-dependencies function or replace original main with a version
  printer and call that a completed client.
- GSS/Kerberos and dynamic-loader imports remain unchanged in the full-client
  audit. Deciding a separate Pi optional-feature profile is distinct from
  falsifying provider success or weakening required authentication/crypto.

## Provenance and notices

The repository's `APPLE_LICENSE` is APSL 1.1, while most selected lookup files
carry explicit APSL 2.0 headers. Other selected files retain their own BSD/DEC,
ISC, Apple, and XNU notices. Preserve the applicable per-file terms; the root
license filename is not evidence that every file has one interchangeable
license. Some modern private-interface files contain bare Apple notices. This
audit does not grant private implementation rights or certify redistribution
clearance. No private corecrypto, RC4 fallback, live keys, or hardware actions
were introduced.
