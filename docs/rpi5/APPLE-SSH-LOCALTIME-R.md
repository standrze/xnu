# Apple OpenSSH public localtime_r fallback

## Result

The distinct offline package `build/rpi5/apple-ssh-localtime-r-5apxxhjz`
closes `_localtime_r` in the unchanged Apple OpenSSH 10.0p2 full-client link.
The failed link now has exactly 35 unresolved imports instead of 36, with no
duplicate or newly reachable symbol.

- Manifest SHA-256: `0093975e99016eca90282e2e9dd68264855d40a0bf3c9230d570cc671f3c11c1`
- Original source SHA-256: `f97e66fd06996b37465ee51bf172b7cd2c656e7a727ea5b25b72e0a0a7502047`
- Provider-selection header SHA-256: `8fc9e4d855ee3164712f08f047a6c3091c826d129716d374bb33d3cad323ddc5`
- Provider archive SHA-256: `e516fe36410eea1d44481705885c108fa13c3a9ba4bddebfb3ad52ba0e8d3969`
- Forced A76 contract SHA-256: `9b7f8dcd4190189eff5fb2ce69fc080df2634c496f0c4ead4be21af8db4d85e9`
- Native oracle SHA-256: `9e447917d829df8e556541988f3d48a8055aa093e2e38645d0d3d15b1a32a200`
- Apple OpenSSH commit: `f386b2e948280f6ecac875329c0b56020821d558`

The provider compiles Apple's unchanged public
`openssh/openbsd-compat/bsd-misc.c` with only `HAVE_LOCALTIME_R` undefined for
this translation unit. The full client configuration remains unchanged. The
two bodies already owned by the client's original `bsd-misc.c` object,
`ssh_get_progname` and `pledge`, receive provider-private names. The linker
dead-strips those renamed atoms; neither appears in the forced contract.

The selected fallback calls the existing public `localtime` ABI, copies the
returned `struct tm`, and returns the caller's result pointer. It does not use
Apple's current Libc timezone/notify service implementation, add locks, access
FILE internals, or create a service facade. Because the original fallback
inherits `localtime`'s static-storage behavior, this evidence makes no stronger
thread-safety or concurrency claim than the shipped body itself.

The forced A76 contract has zero undefined symbols and maps `_localtime_r` to
the new archive. Four tests pass in 1.398 seconds. The native ASan/UBSan oracle
checks a UTC epoch conversion, returned pointer, complete fields and unchanged
input, plus a rejecting negative invocation.

```sh
RPI5_LOCALTIME_R_PACKAGE=build/rpi5/apple-ssh-localtime-r-5apxxhjz \
RPI5_LOCALTIME_R_MANIFEST_SHA256=0093975e99016eca90282e2e9dd68264855d40a0bf3c9230d570cc671f3c11c1 \
python3 -m unittest tools.rpi5.tests.test_apple_ssh_localtime_r -v
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

The low-risk compatibility leaves are now exhausted. Remaining stdio names
cross FILE-layout or process boundaries, while resolver, Libinfo, logging,
notify, dyld, GSS/Kerberos and bootstrap names require real subsystem or
service ownership. `bootstrap_parent` remains private libxpc territory; it has
not been substituted. PAM/Kerberos and all OpenSSH features remain enabled.
No target, runtime image, network, key, SD card, or hardware was used or
changed. Planned paths remain `/usr/bin/ssh`, `/usr/sbin/sshd`, `/usr/libexec`,
and `/private/etc/ssh`.
