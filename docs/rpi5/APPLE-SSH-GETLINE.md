# Apple OpenSSH public getline provider

## Result

The distinct offline package `build/rpi5/apple-ssh-getline-r2hrtn32` closes
`_getline` in the unchanged Apple OpenSSH 10.0p2 full-client link. The failed
link now has exactly 36 unresolved imports instead of 37, with no duplicate or
newly reachable symbol.

- Manifest SHA-256: `f2f2f6caba8802ccf10fd3a08f4c56208892bd847f2370dadcbd2616bee431dd`
- Original source SHA-256: `0ae4779d71f456e4ff891c90cfb378704291b7ec3ffd4da9b289578e496b54f1`
- Provider-selection header SHA-256: `cf61bd399411c46d0fdc9766f684b486afd0a9a1dacaa5c894d78456b873aea1`
- Provider archive SHA-256: `9d730285b9d2750b8eb13b3a33d13e66f7e0af4a2d0de4ee2612c504923945ff`
- Forced A76 contract SHA-256: `2aa2b84d6d423c4773a3c8a626a27a461930dd302bf3c848fab0e44400e0b761`
- Native oracle SHA-256: `c8441e460b439c6f7146424135e24017e66c18875473ed6dc4d645e907b5b658`
- Apple OpenSSH commit: `f386b2e948280f6ecac875329c0b56020821d558`

The provider is Apple's unchanged public
`openssh/openbsd-compat/bsd-getline.c`. Its original conditional body expects
`getdelim` to be undeclared when the fallback is selected, while modern Darwin
headers declare public `getdelim`. The provider-only build header therefore
renames the translation unit's static helper to `rpi5_openssh_getdelim` after
the public headers have been consumed. It changes neither source bytes nor the
exported `getline` ABI. The provider accesses FILE solely through `fgetc` and
`feof`; no FILE field or private stdio implementation is mixed in.

The A76 object exports only `_getline`. The forced contract has zero undefined
symbols and maps the live definition to `libapple-openssh-getline.a`. Four
tests pass in 1.433 seconds. The native ASan/UBSan oracle covers newline and
empty lines, a 9,000-byte EOF-terminated line that grows the buffer, final EOF,
and a rejecting negative invocation.

```sh
RPI5_GETLINE_PACKAGE=build/rpi5/apple-ssh-getline-r2hrtn32 \
RPI5_GETLINE_MANIFEST_SHA256=f2f2f6caba8802ccf10fd3a08f4c56208892bd847f2370dadcbd2616bee431dd \
python3 -m unittest tools.rpi5.tests.test_apple_ssh_getline -v
```

## Exact remaining imports

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
_localtime_r
_notify_check
_notify_register_check
_openlog
_os_log_create
_os_log_type_enabled
_pclose
_perror
_popen
_res_9_init
_res_9_query
_si_destination_compare
_sscanf
_syslog$DARWIN_EXTSN
_vsyslog
```

The remaining groups include service-backed and FILE-internal boundaries.
`bootstrap_parent` remains a private libxpc/service dependency and has not been
replaced. PAM/Kerberos and OpenSSH feature configuration remain enabled.
No runtime image, target, network connection, key, SD card, or hardware was
used or changed. Planned install paths remain `/usr/bin/ssh`, `/usr/sbin/sshd`,
`/usr/libexec`, and `/private/etc/ssh`.
