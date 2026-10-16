# Apple OpenSSH public asprintf provider

## Result

The distinct offline package `build/rpi5/apple-ssh-asprintf-ewo2v725` closes
the `_asprintf` and `_vasprintf` imports in the unchanged Apple OpenSSH
10.0p2 full-client link. It introduces no duplicate or newly reachable symbol.
The failed link now reports exactly 37 unresolved imports instead of 39.

- Manifest SHA-256: `20bf991bbe83b4f02308aa21217ddf1172b1ea79bc0114ad06784565236e8f28`
- Original source SHA-256: `3078aeecdfc3fb27e756a671bde143fd200eb919018fadadf6380f6f33201482`
- Provider archive SHA-256: `6d10963d6064531b997f70c6ba96139a90163cd57f3e98ec8d651e551c044671`
- Forced A76 contract SHA-256: `422fad919f782615e4b75e28326122422204379e9b33dc8c7d968b9503e98ce3`
- Native oracle SHA-256: `12d0638f4d81759392cdccc5efe7b76e6705f9376d4d19c3a9af335804341f68`
- Apple OpenSSH commit: `f386b2e948280f6ecac875329c0b56020821d558`

The provider is the unchanged public
`openssh/openbsd-compat/bsd-asprintf.c` retained in Apple's OpenSSH source.
The existing provider-only build annotation undefines `HAVE_ASPRINTF` and
`HAVE_VASPRINTF` for that translation unit so its shipped fallback bodies are
compiled. It does not change the global OpenSSH configuration, consumer
objects, PAM/Kerberos selection, or any frozen predecessor.

## Evidence

The A76 provider object exports exactly `_asprintf` and `_vasprintf`. A forced
static contract links both through the new archive with zero undefined
symbols. Its map records the archive member as the live owner of each API.
The native ASan/UBSan oracle exercises the direct and `va_list` APIs, a short
format, an empty result, and a 4,098-byte format that takes the realloc path.
Four retained-package tests pass in 1.323 seconds.

Reproduce the retained verification with:

```sh
RPI5_ASPRINTF_PACKAGE=build/rpi5/apple-ssh-asprintf-ewo2v725 \
RPI5_ASPRINTF_MANIFEST_SHA256=20bf991bbe83b4f02308aa21217ddf1172b1ea79bc0114ad06784565236e8f28 \
python3 -m unittest tools.rpi5.tests.test_apple_ssh_asprintf -v
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
_getline
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

These include genuine external service and subsystem boundaries. In
particular, the current SDK's `bootstrap_parent` is a private libxpc/service
dependency; the historical liblaunch RPC is not substituted. No SSH target,
network connection, key, hardware, SD card, or accepted runtime was used or
changed. Future paths remain `/usr/bin/ssh`, `/usr/sbin/sshd`, `/usr/libexec`,
and `/private/etc/ssh`.
