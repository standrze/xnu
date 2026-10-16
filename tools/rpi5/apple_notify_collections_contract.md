# Genuine notification-registry collection prerequisite

`build/rpi5/apple-notify-collections-20uzs24a` compiles unchanged whole current
Apple `collections_map.c` and `collections_set.c`, including their unchanged
template implementations and public headers, from Libc commit
`71bbe350ab79eef58113991d817ccc6165061a64`. All seven map/set representations and
57 exported operations have live original object owners in a zero-import static
A76 executable. The actual stack-Block data owner is the previously qualified
original Apple Blocks runtime. No accepted archive was modified.
The forced executable inherits the experimental SSH branch's existing
`glue-allocator.o` and `glue-adapters.o` for allocation/assertion; those are not
silently relabeled as modern Apple libmalloc. They are recorded as actual map
owners. Moving this dependency into the newer complete startup/allocator
composition remains separate work before target execution.

The native ASan/UBSan test executes the actual collections using 1,024 elements
in each of four maps and three pointer sets, including 1,024 intentionally
colliding original 64-bit pointer-set hashes. It checks grow/delete/shrink,
iteration early stop, clear callback semantics, clear/reuse, string-entry
identity, and original fatal allocation failure on initial/growth allocation.
Only allocation failure injection is substituted in the native collection
objects. The target objects have no such substitution. Four child processes
must genuinely terminate with SIGABRT; a bad final oracle exits 37. The source's
assert-on-allocation-failure policy is preserved, not advertised as recovery.
These collections require external serialization; the test does not claim they
are independently thread-safe.

This is a real dependency of current Libnotify's registration tables, not a
notification API implementation. Appending its archive to the original full
SSH composition leaves the experimental stdtime branch at **42** unresolved
imports, no new imports or duplicate owners. The better-qualified composition
still has **41**. `notify_client.c` and `libnotify.c` remain unbuilt pending
genuine private bootstrap/XPC/dispatch interfaces and their actual service
implementation. No notification failure stub, loopback switch, feature removal,
SSH execution, target execution, or notification-service availability is claimed.

The original SDK/private headers issue nullability warnings with the current
compiler; those warnings are retained in build logs. Dependency scans before
compilation match the actual emitted `.d` files. Static linkage and host tests
do not prove target allocator, process/fork, or Mach notification behavior.

Validation: `python3 -m unittest tools.rpi5.tests.test_apple_notify_collections -v`.
