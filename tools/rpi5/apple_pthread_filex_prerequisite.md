# Apple pthread prerequisite for current FILEX/popen

This is a default-off software gate. It does not admit a provider, alter an
image, or convert host pthread behavior into Raspberry Pi evidence.

The current Apple pthread archive owns the required mutex, TSD, atfork, once,
and cancellation entry points. The kernel source owns the fork, bsdthread,
psynch, and ulock syscall numbers. Source and symbol ownership are necessary,
but are not target behavioral qualification.

The accepted physical root42 evidence establishes only its exact four-thread
workload: create/join, 2,048 mutex-protected increments, four distinct errno/TSD
instances, four TSD destructors, and one `pthread_once`. It explicitly does not
cover all of libSystem. A later root42 attempt failed before transmitting any
commands and contributes no positive evidence.

The host oracle checks recursive mutex depth, six-thread contention and errno
isolation, atfork ordering across a real fork, and deferred cancellation with a
cleanup handler. It runs the host runtime under ASan/UBSan and is only a
behavioral specification.

The FILEX/popen tranche remains disabled until all of these target behaviors
are demonstrated with the genuine current Apple implementation:

1. Recursive mutex ownership and nesting on the target.
2. Current Libc `fork.c` composed with the real libSystem atfork callbacks,
   including child pthread reinitialization.
3. A genuine `VARIANT_CANCELABLE` build and target cancellation-point cleanup.
4. Coherent `__sFILEX` allocation, orientation, and recursive stream locking.

Run the focused gate tests with:

```sh
python3 -m unittest tools.rpi5.tests.test_apple_pthread_filex_prerequisite -v
```

Build an immutable evidence package with:

```sh
python3 tools/rpi5/build_apple_pthread_filex_prerequisite.py
```

The resulting manifest must report `gate_open: false` and
`filex_popen_admission_allowed: false` until new physical evidence closes every
listed target blocker.
