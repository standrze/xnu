# Gate 2 libpthread adaptation

`libpthread-kern.patch` applies only to the pinned `libpthread-539.100.4`
archive. `xnu-pthread-header-overlay.patch` applies to a copied
`bsd/sys/pthread_internal.h` in the isolated build stage. No tracked XNU header
or SDK file is patched. The source archive SHA-256 and every adapted source
SHA-256 are checked by `gate2-pthread.lock.json` before compilation.

The pinned `ksyn_waitq_element` was 56 bytes on arm64; XNU's opaque uthread
slot is 48 bytes. The adaptation removes the final `kwe_uth` pointer and uses
the stored `kwe_thread` with `get_bsdthread_info` at its three read sites.
This assumes a queued thread remains valid at each cancellation check. Static
assertions in the overlay verify the adapted 48-byte size and all field offsets.

Other changes match current XNU signatures: a two-argument thread-port lookup,
integer wait-queue identities, VM fault wire tag, and the VM unslide address.
The removed `VM_MAKE_TAG` macro is expanded to its former bit encoding.
Three `os_log_error` diagnostics use kernel `printf` to avoid a DSO handle in
the static link. The old `pthread_kern` callback pointer is renamed at compile
time to `rpi5_pthread_kern`, avoiding XNU's read-only pointer. The function
table remains the pinned v0 table; no callback stubs are supplied.

The fresh host kernel build confirms source compilation and static linking.
Thread lifetime and startup behavior still require Pi runtime validation.
