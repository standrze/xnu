# Apple OpenSSH resolver ownership gate

Date: 2026-10-14  
Scope: software-only ownership and composition audit  
Result: **not admitted; no provider linked**

The sealed full-client package is
`apple-ssh-localtime-r-5apxxhjz`, whose manifest SHA-256 is
`0093975e99016eca90282e2e9dd68264855d40a0bf3c9230d570cc671f3c11c1`.
It still has exactly 35 unresolved imports. The smallest coherent next
subsystem is the three-symbol resolver tranche:

- `___res_9_state`
- `_res_9_init`
- `_res_9_query`

These are not independent libc leaves. The real Apple implementation spans
`res_state.c`, `res_data.c`, `res_init.c`, `res_mkquery.c`, `res_query.c`,
`res_send.c`, and `dns.c`. The call graph requires all of the following:

1. per-thread resolver state and reload semantics;
2. DNS wire-query construction;
3. SystemConfiguration/configd DNS configuration over its Mach/MIG service;
4. the notify client and service for configuration, cancellation, and file
   monitoring;
5. mDNSResponder's DNSService query and reply transport;
6. target UDP/TCP sockets, kqueue, interrupt, and cancellation semantics;
7. deterministic target tests for file configuration, configd configuration,
   unicast UDP/TCP, mDNS, reload, cancellation, and concurrent state.

Only the DNS wire parser is already qualified. The other service and transport
owners are not. Consequently, the gate does not build or link a provider and
the full client remains at 35 unresolved imports.

## Source evidence

The checker pins these exact public Apple source checkouts:

| Project | Commit |
| --- | --- |
| apple-OpenSSH | `f386b2e948280f6ecac875329c0b56020821d558` |
| apple-libresolv | `e48cd914edc1cb14f8289b8e2dfdaac360481cd2` |
| apple-Libinfo | `39b70c515baee5b609e7e91693edbd934b6845a1` |
| apple-libnotify | `715d461778f6b93c821d99390a0078bd6f6d8c04` |
| apple-configd | `5ab18e75fd838206cf76cab596a41a3050404867` |

Fifteen exact consumer, source, and build files are SHA-256 pinned in the retained report.
The checker also requires semantic ownership evidence in each source: resolver
state and wrapper calls, configd DNS configuration, notify registration and
file monitoring, DNSService processing, socket/kqueue transport, and the
configd Mach/MIG client/server path.

## Libinfo is a separate subsystem

`_si_destination_compare` cannot honestly close the resolver tranche. Apple's
OpenSSH calls the full `si_destination_compare` from `ssh.c` before
daemonization to initialize Libinfo logging. The full owner in
`lookup.subproj/si_compare.c` uses `os_log`, `pthread_atfork`,
`PF_SYSTEM/SYSPROTO_CONTROL`, `CTLIOCGINFO`, network statistics,
`getifaddrs`, and Mach absolute time.

The same source contains `si_destination_compare_no_dependencies`, but that
routine deliberately skips full source-selection/statistics behavior. Aliasing
it to the requested ABI would change semantics, so the gate explicitly rejects
that substitution.

## Explicitly forbidden shortcuts

The checker rejects any report that enables:

- a size-only/static resolver-state facade;
- a no-op `res_init`;
- DNSService, notify, or configd stubs;
- an alias to `si_destination_compare_no_dependencies`;
- PAM, Kerberos/GSS, or other OpenSSH feature disabling.

The planned Apple filesystem layout remains `/usr/bin/ssh`, `/usr/sbin/sshd`,
`/usr/libexec`, and `/private/etc/ssh`. No accepted runtime, target, hardware,
network, key, or image was touched.

## Reproduce

```sh
python3 -m unittest -v tools.rpi5.tests.test_apple_ssh_resolver_gate
tools/rpi5/check_apple_ssh_resolver_gate.py \
  --output build/rpi5/apple-ssh-resolver-gate-20261014/report.json
```

The test suite passes five tests. The checker exits `2` by design because this
is a failing admission gate. Its retained report SHA-256 is
`a08929d2db4b2d3a16ec9e71ff918d40eceabc8f24961437ec376be6008843c0`.

The next honest sequence is recorded in the report: qualify the real notify
runtime/service, configd shared-DNS Mach/MIG path, mDNSResponder DNSService
transport, and target socket/kqueue behavior; then build the complete seven-
unit tranche and require exactly three closed imports, no newly reachable
imports, no duplicates, and the full deterministic resolver test matrix.
