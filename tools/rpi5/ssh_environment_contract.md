# Current Apple environment family: distinct offline composition

The whole current Apple `getenv.c`, `setenv.c`, and `putenv.c` are used from
Libc commit `71bbe350ab79eef58113991d817ccc6165061a64`. All readers and mutators
share the original current unfair-lock and owned-pointer state. The new private
archive removes exactly the three older environment objects from a copied
archive; every other object is byte-identical. No accepted archive is changed.

Original `getenv_copy_np` leaks its already allocated buffer in two actual paths:
the variable disappears between allocation and reread, or five growth retries
are exhausted. The host fixture triggers both through actual `setenv`/`unsetenv`
calls from the allocation callback, verifies the outstanding allocation, and
cleans up fixture state. The original fails the no-leak oracle. The derived
whole `getenv.c` changes only those two cleanup paths: free before EAGAIN, and
free while preserving errno on disappearance. Original source/object and both
positive and negative oracle results are retained.

Native ASan/UBSan tests use an isolated environment pointer, allocator accounting,
and a genuine host mutex behind explicitly test-only lock callbacks. Four threads
perform 128 set/get/copy/unset iterations each. This is execution of the actual
environment algorithms, not execution of the target unfair-lock implementation.
The 14-API forced A76 static target has zero undefined symbols and exact owners
for the actual target lock, current reallocf, and static `_NSGetEnviron` providers.
No target executable is run on macOS.

The unqualified timezone branch moves 43 to 42 imports, closing only
`getenv_copy_np`, with no new imports or duplicate owners. Its genuine notification
dependencies remain. The prior qualified full-client composition still has 41
imports. This does not qualify full SSH, modern Libc startup, timezone services,
or multithreaded target fork. In particular, retaining and force-linking
`__environ_lock_fork_child` does not prove that the full Libc fork-child callback
registration runs in this static startup; that wiring must be completed before
the new environment composition is admitted to a runtime package.
