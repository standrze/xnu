# Apple Libc `sscanf` provider

## Result

The retained package is `build/rpi5/apple-ssh-sscanf-m4_xgkm2`. Its manifest
SHA-256 is
`114efe7a753f69e22548da8dca5c3e4f8e20faaec26a5b0232b23d263d742eed`.
It adds Apple's unchanged Libc-167 `sscanf.c` and the complete unchanged
Libc-167 `vfscanf.c` parser. It is not a format-specific substitute.

The exact failed full-client link moves from 34 to 33 unresolved imports. It
closes only `_sscanf`, introduces no newly reachable import and reports no
duplicate symbol. The full client still does not link or run.

## Source and stdio ABI identity

Both files are verified byte-for-byte against the source archive pinned by the
existing Apple runtime lock: public tag `Libc-167`, commit
`630404129b7029c30def14e0a5150c4b93d7458c`, archive SHA-256
`abb1bc021fbe61622148fad98b5ef955e5f7bf56c804895a14cac6b4132d183b`.

| Original source | SHA-256 |
|---|---|
| `stdio.subproj/sscanf.c` | `a5d2994744baadc2cd8f2bcacd35beb4980f67ba9c4ce3410821075f01dcd015` |
| `stdio.subproj/vfscanf.c` | `9a08021593cdee0c1caec79460ccc3272a17f3f6928be448faaba516f2680a81` |

`sscanf` constructs the original read-only string-backed `FILE` and invokes
the complete `__svfscanf` parser. The provider and its sealed predecessor
consume identical stdio ABI headers:

| Header | SHA-256 |
|---|---|
| SDK `usr/include/stdio.h` | `d2220614f42d3cb678ae0de176ba0ab3256e15fb45b3efdb5d17b8ac1f6a4b54` |
| SDK `usr/include/sys/stdio.h` | `a8078ae1cba1a46a66d0de6fe7f13bbc969cdb7e78fc2d4b9a5c5cdaaf16126b` |

No accepted runtime object was changed or replaced.

## Dependency ownership

The forced ARM64 contract has zero undefined symbols. Its link map attributes
`_sscanf` and `___svfscanf` to `libapple-libc167-sscanf.a`. Every external
parser dependency remains owned by the pre-existing Apple runtime or locale
composition:

```text
__DefaultRuneLocale
___maskrune
___srefill
_fread
_strlen
_strtod
_strtol
_strtoul
_ungetc
```

The locale table and rune mask come from the qualified Apple locale slice.
The remaining owners are the accepted Apple runtime archive, including the
Libc-167 refill, fread, numeric conversion and ungetc objects. The provider
does not supply facades for any of them.

Artifact hashes are:

| Artifact | SHA-256 |
|---|---|
| `libapple-libc167-sscanf.a` | `f30817811de6087d37712bd9d50e2b95bd1934cb95ce9fe15ed14655ca2e804d` |
| `target-sscanf.o` | `6cd088a7754cebc1d5efd236807f674a265d42356d222b8c05c62da5aab08119` |
| `target-vfscanf.o` | `668423ae43843248587d1fdae06ce46f8faee2b718ee9c2beec35474e9cbed19` |
| `NOT_RUN_sscanf_contract` | `970c2b131ac4f43a697cc2b8d0f8b77f64db49bf5ca0bb610211014801174c69` |

## Behavioral evidence and limits

Five focused tests pass. A native ASan/UBSan executable exercises the actual
OpenSSH format families represented by the retained consumers: SSH version
major/minor and scanset, X11 unsigned display number, two-digit hex byte and
`%n`, suppressed/token strings, scansets and empty-input failure. The only
native test boundary is an EOF-returning `fixture_srefill` for an exhausted
string-backed `FILE`; it is not present in either target object or archive.
The target contract uses the real accepted `___srefill` owner.

The 33 remaining imports are the previously documented GSS/Kerberos, dyld,
logging/notify, bootstrap, resolver/Libinfo and `popen`/`pclose` groups.
Resolver and notify remain genuine service boundaries. No feature was
disabled, and no logging, resolver, service or process facade was introduced.

No target, hardware, serial port, SD card, network, key or filesystem image
was touched. Planned Apple paths remain `/usr/bin/ssh`, `/usr/sbin/sshd`,
`/usr/libexec`, and `/private/etc/ssh`.

Reproduce the retained-package checks with:

```sh
RPI5_SSCANF_PACKAGE=build/rpi5/apple-ssh-sscanf-m4_xgkm2 \
RPI5_SSCANF_MANIFEST_SHA256=114efe7a753f69e22548da8dca5c3e4f8e20faaec26a5b0232b23d263d742eed \
python3 -m unittest -v tools.rpi5.tests.test_apple_ssh_sscanf
```
