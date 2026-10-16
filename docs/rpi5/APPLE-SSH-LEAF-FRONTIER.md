# Apple OpenSSH safe-leaf frontier

Date: 2026-10-14  
Scope: sealed 33-import full-client composition  
Result: **no provider admitted; unresolved count remains 33**

The baseline is `build/rpi5/apple-ssh-sscanf-m4_xgkm2`, manifest SHA-256
`114efe7a753f69e22548da8dca5c3e4f8e20faaec26a5b0232b23d263d742eed`.
After qualifying the complete Apple `sscanf` parser, every remaining import is
owned by one of these coherent groups:

- GSS/Kerberos;
- resolver and Libinfo destination selection;
- notify, os_log and syslog;
- the dynamic loader;
- private bootstrap service ownership;
- the `popen`/`pclose` process-backed stdio pair.

The first five are already documented runtime or service tranches. The last
pair was the sole plausible leaf candidate and was tested directly.

## Why old Apple popen is not admitted

The unchanged public Apple Libc-167 `gen.subproj/popen.c` is pinned at commit
`630404129b7029c30def14e0a5150c4b93d7458c`. Its source SHA-256 is
`339b545121d72e27caf86c55a1ab5bde3b8f7496f97f43e865451aed256bb954`;
it is byte-identical to the member in archive
`abb1bc021fbe61622148fad98b5ef955e5f7bf56c804895a14cac6b4132d183b`.

The gate compiles that unchanged source for the ARM64 target and appends it to
the exact failed full-client link. It closes `_popen` and `_pclose`, creates no
duplicate definition, but introduces `_vfork`. The link therefore moves from
33 to 32 unresolved imports rather than meeting the no-new-import rule.

Adding or renaming a private raw-vfork body is not an acceptable shortcut. It
would still substitute a 1999 process implementation whose source:

- maintains a process-global pid list with no lock;
- leaks pipe or socket descriptors if its post-pipe allocation fails;
- states that `fdopen` cannot fail and does not handle that failure;
- depends on vfork ownership absent from the accepted runtime.

Using it would weaken the current Apple process and failure semantics expected
by current OpenSSH. Replacing `vfork` with `fork` by macro or source rewrite is
also rejected rather than relabeled as unchanged Apple behavior.

## Why current Apple popen is not a leaf

Current Apple Libc-1752.120.2 `gen/FreeBSD/popen.c` is pinned at commit
`4e34d0559e3a1b081afeb8604d9e204a1f31321d`. Its source SHA-256 is
`adfae390de4dfce979d597f4237f0c83b2e92c362d6a5df596136b990031ae71`,
verified against archive
`b7b6c6d185ef59187c392824ef464a0ebdb6b962d1574abbb93d3aa15e20d826`.

That implementation fixes the old failure and concurrency semantics, but it
is a subsystem rather than a leaf. It requires:

- current `FILE` orientation through `fwide`;
- pthread mutex and atfork behavior;
- posix_spawn actions and environment ownership;
- private libc hook headers and callbacks.

The accepted runtime intentionally uses the Libc-167 byte-stream `FILE`
composition. Removing `fwide`, locks, spawn ownership, or private hooks would
change current semantics. Mixing the modern and old FILE families is likewise
not qualified.

## Gate and negative controls

`tools/rpi5/check_apple_ssh_leaf_frontier.py` pins the exact baseline, all 33
imports, both Apple source archives and source files, and the real old-source
compile/link delta. It rejects:

- old-popen semantic downgrade;
- private-to-public vfork aliasing;
- rewriting vfork to fork;
- removal of current FILE orientation or locking;
- service or dynamic-loader facades;
- disabling PAM or Kerberos/GSS.

Five tests pass, including omission/mutation controls and a CLI round trip.
The checker exits 2 by design because no safe leaf is admitted. The retained
report is `build/rpi5/apple-ssh-leaf-frontier-20261014/report.json`, SHA-256
`f718b0bc03aee95586a70e67d27682176661ba8f9a06065d2c895e41466ea7ea`.

No provider package was created and the exact delta is 33 to 33. OpenSSH's
features, accepted runtime and planned Apple paths (`/usr/bin/ssh`,
`/usr/sbin/sshd`, `/usr/libexec`, `/private/etc/ssh`) remain unchanged. No
target, hardware, serial port, SD card, network, key or image was touched.

Reproduce with:

```sh
python3 -m unittest -v tools.rpi5.tests.test_apple_ssh_leaf_frontier
tools/rpi5/check_apple_ssh_leaf_frontier.py \
  --output build/rpi5/apple-ssh-leaf-frontier-20261014/report.json
```
