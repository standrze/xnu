# Apple OpenSSH notify service admission gate

Date: 2026-10-14  
Scope: software-only Apple Libnotify client/service prerequisite audit  
Result: **default-off; no provider created**

This audit continues from the resolver ownership report with SHA-256
`a08929d2db4b2d3a16ec9e71ff918d40eceabc8f24961437ec376be6008843c0`.
The current 35-import OpenSSH baseline exposes two notify imports:

- `_notify_check`
- `_notify_register_check`

They are not an honest two-function leaf. Linking Apple's resolver path makes
the complete notify dependency family visible:

- `_notify_cancel`
- `_notify_check`
- `_notify_get_state`
- `_notify_monitor_file`
- `_notify_register_check`
- `_notify_register_plain`

The four additional calls are recorded as newly reachable requirements, not
hidden behind a partial archive.

## Genuine Apple ownership

The checker pins Apple Libnotify commit
`715d461778f6b93c821d99390a0078bd6f6d8c04` and 18 unchanged source, build,
server, and test files. Source assertions establish this real path:

1. `notify_register_check` initializes the client and looks up
   `com.apple.system.notification_center` through privileged bootstrap.
2. The protocol-v3 MIG call asks notifyd to allocate/refcount a shared-memory
   slot and return the mapping size, slot, and notification-name ID.
3. The client maps notifyd's shared-memory object and `notify_check` compares
   the daemon-owned generation value under its check lock.
4. Non-memory checks still call notifyd over MIG.
5. The client watches notifyd and regenerates registrations after server
   restart; fork behavior deliberately disables unsafe inherited state.
6. notifyd owns shared-memory creation, Mach/dispatch demultiplexing, protocol
   replies, registration lifecycle, XPC entitlement handling, and vnode
   pathwatch sandbox checks.

The previously qualified Libnotify map/set collections are prerequisites, not
a substitute for this client/service protocol.

## Build boundary

The gate performs two unchanged-source, ARM64, freestanding syntax probes with
the public SDK. Both stop at their first real private build inputs:

| Unit | First missing private header |
| --- | --- |
| `notify_client.c` | `bootstrap_priv.h` |
| `libnotify.c` | `os/lock_private.h` |

Supplying declarations by hand would not solve the service boundary. A real
build also needs the generated MIG client/server, Blocks, dispatch, XPC, Mach,
bootstrap, collections, and complete private-header ownership.

## Negative controls

The admission checker rejects all of these shortcuts:

- making `notify_check` always report unchanged;
- using an in-process-only registry;
- forcing notification names into the `self.` path;
- forcing the browser loopback entitlement;
- fake bootstrap ports or MIG replies;
- a fixed shared-memory slot;
- disabling restart regeneration, path monitoring, or OpenSSH features.

The planned Apple filesystem layout remains `/usr/bin/ssh`, `/usr/sbin/sshd`,
`/usr/libexec`, and `/private/etc/ssh`. PAM and Kerberos/GSS remain enabled.
No target, hardware, image, key, network, service, or accepted runtime was
touched.

## Reproduce

```sh
python3 -m unittest -v tools.rpi5.tests.test_apple_ssh_notify_gate
tools/rpi5/check_apple_ssh_notify_gate.py \
  --output build/rpi5/apple-ssh-notify-gate-20261014/report.json
```

Six focused tests pass, including source/commit/hash checks, public-SDK compile
boundaries, exact API expansion, report mutation controls, and CLI retention.
The checker exits `2` by design because admission is default-off. The retained
report SHA-256 is
`630d6c3a26e4b8e03c73c198aff97325963a9735d6306d86df857f15ea9354e2`.

Admission requires the exact private/generated build inputs, original client
composition, a real protocol-v3 notifyd with daemon-owned shared memory, and
behavioral tests for first/unchanged/changed checks, cancellation, slot reuse,
restart regeneration, fork behavior, concurrency, and path monitoring. Only
then can the six-API family be linked while requiring no new unresolved or
duplicate symbols.
