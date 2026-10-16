# Apple system/spawn error contract

This is a software-only qualification of current Apple source. Neither an SSH
process nor a target process is executed by the tests.

The [POSIX system() return-value contract](https://pubs.opengroup.org/onlinepubs/9799919799/functions/system.html)
requires a child-creation failure to return -1 and report its error through
errno. The original Apple system.3 also describes fork-like failures as -1.
The source-selected current libsyscall posix_spawn implementation instead
returns the error number directly and restores the caller's errno.

For original system.c's ENOMEM/EAGAIN branch, this combination returns -1 while
leaving a deliberately unrelated EDOM in errno. The original source and the
failing native contract are preserved. The derived source adds exactly one
`errno = err;` statement in that existing branch. It does not change which
errors take the branch, shell arguments, signal handling, waiting, cancellation
point, process creation mechanism, or mutex ownership.

The native oracle compiles both complete original and derived system units
with the same complete original spawn unit. Only native symbols are namespaced;
kernel/process/signal/allocation-failure boundaries are explicit test doubles.
Original host pthread mutexes exercise serialization. This proves the selected
source-level callback contract, not XNU process creation, cancellation during
wait, real signal delivery, or a working SSH client.

The target archive excludes modern popen: its fwide dependency requires FILE
orientation state incompatible with the frozen Libc-167 stdio layout. No fwide
stub, mixed FILE ownership, or accepted-runtime replacement is used.
