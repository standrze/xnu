# Apple Libc `perror` provider

## Result

The retained package is
`build/rpi5/apple-ssh-perror-fedl96a9`. Its `manifest.json` SHA-256 is
`be08baf42a4708591d75e642b80daeb8936af8210ee6155f9951124a9dd55007`.
It composes the unchanged Apple Libc-167 `perror.c` with Apple's ordinary
generated `writev` syscall form:

```asm
__SYSCALL2(_writev, writev, 3, cerror_nocancel)
```

The failed full-client link moves from 35 to 34 unresolved imports. It closes
only `_perror`, introduces no newly reachable import and reports no duplicate
definition. The package does not link or qualify the complete SSH client.

## Source identity

The checked-in source lock identifies the public Apple
`apple-oss-distributions/Libc` tag `Libc-167` at commit
`630404129b7029c30def14e0a5150c4b93d7458c`. The retained archive and selected
source are independently pinned:

| Input | SHA-256 |
|---|---|
| `Libc-167.tar.gz` | `abb1bc021fbe61622148fad98b5ef955e5f7bf56c804895a14cac6b4132d183b` |
| `stdio.subproj/perror.c` | `865d899138df678496ef4479b96479c059c9271140ea85d01aba844f254280d5` |

The builder verifies that the selected file is byte-for-byte identical to the
member extracted from that pinned archive. The source is compiled unchanged.
Its implementation constructs two or four `iovec` entries and writes them to
`STDERR_FILENO`; it does not dereference `FILE`, use `stderr`, lock a stream or
flush stdio state. Its imports are the accepted runtime's `__error`,
`strerror`, and `strlen`, plus the genuine `writev` wrapper's existing
`cerror_nocancel` owner.

## Static contract

The target objects export exactly `_perror` and `_writev`. The forced ARM64
contract has zero undefined symbols, and the link map attributes both live
symbols to `libapple-libc167-perror.a`. Artifact hashes are:

| Artifact | SHA-256 |
|---|---|
| `libapple-libc167-perror.a` | `88a8e7a9179ba1ca941eb4234c4f1dbf712b4c6c1e0150724a1238af2289457a` |
| `target-perror.o` | `6eaa72ae7ddd892d6d67328a442d2ce56b0cf4cc7617613e3ae5cb407d708c48` |
| `target-writev.o` | `f80b35765ae58c37b1fed2523229121872dc75d5a0cda817f7ec21fc11493b14` |
| `NOT_RUN_perror_contract` | `4456cf7670bc026d438235a45b037caad883cbdcb08a265d5c5268c4bf1c2d7d` |

The exact remaining imports are:

```text
_GSS_C_NT_HOSTBASED_SERVICE
___res_9_state
__os_log_debug_impl
__os_log_default
__os_log_error_impl
_bootstrap_parent
_closelog
_dlclose
_dlerror
_dlopen
_dlsym
_gss_delete_sec_context
_gss_display_status
_gss_get_mic
_gss_import_name
_gss_indicate_mechs
_gss_init_sec_context
_gss_release_buffer
_gss_release_cred
_gss_release_name
_gss_release_oid_set
_notify_check
_notify_register_check
_openlog
_os_log_create
_os_log_type_enabled
_pclose
_popen
_res_9_init
_res_9_query
_si_destination_compare
_sscanf
_syslog$DARWIN_EXTSN
_vsyslog
```

Resolver, Libinfo destination selection and notify remain service-owned
boundaries. `popen`/`pclose` and `sscanf` remain in the separately documented
stdio/process tranche; this provider does not change those decisions.

## Native tests and limits

Five focused tests pass. The ASan/UBSan native oracle verifies the prefixed,
empty and null-label `iovec` shapes, errno forwarding to `strerror`, newline
termination, and the original void API's behavior when `writev` fails. The
negative control exits 37. The target object was linked and inspected but was
not executed.

No hardware, serial port, SD card, target filesystem, network, key or service
was touched. OpenSSH's features and accepted runtime are unchanged. Planned
Apple filesystem locations remain `/usr/bin/ssh`, `/usr/sbin/sshd`,
`/usr/libexec`, and `/private/etc/ssh`.

Reproduce the retained-package checks with:

```sh
RPI5_PERROR_PACKAGE=build/rpi5/apple-ssh-perror-fedl96a9 \
RPI5_PERROR_MANIFEST_SHA256=be08baf42a4708591d75e642b80daeb8936af8210ee6155f9951124a9dd55007 \
python3 -m unittest -v tools.rpi5.tests.test_apple_ssh_perror
```
