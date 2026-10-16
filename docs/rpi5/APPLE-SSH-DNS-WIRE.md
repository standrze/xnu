# Apple DNS wire-parser prerequisite

The distinct `apple-ssh-dns-wire-8gn7d87_` software artifact closes
`res_9_dn_expand` in the unchanged full 176-translation-unit Apple OpenSSH
client composition: **40 → 39 unresolved imports**, no new dependencies and
no duplicate symbols. This does not make the client executable or DNS usable.

Manifest SHA:
`94cbbbb09610948dd30142aebcb5b1df07fe302c1c9bc3169c1cffb004926b19`.
The original source is the pinned Apple public libresolv commit
`e48cd914edc1cb14f8289b8e2dfdaac360481cd2` under
`build/rpi5/apple-libresolv-candidate-20261014`.

Four whole units are compiled with the actual A76 target flags. `ns_parse.c`
and `ns_netint.c` remain byte-identical. `res_comp.c` and `ns_name.c` retain
their complete implementations, with six explicit size/truncation guards.
They reject a nonpositive signed expansion capacity, zero unpack capacity,
missing extended-label length byte, empty skip span, missing normal-label
terminator and truncated extended label. No parser feature is disabled;
all 257 extended-label width encodings are exercised, including zero's
original 256-bit meaning.

The original failures are retained separately. A negative destination size
reproduces UBSan pointer overflow; a missing extended-label byte reproduces
an ASan heap read. Four further original boundary cases return the retained
negative oracle. The checked implementation passes 6,691 native cases and
each negative expectation still fails. The host harness uses real host libc
and the actual original/derived parser bodies, not network-service doubles.

All 32 exported parser APIs are forced into a static A76 contract with zero
undefined symbols and exact archive owners. Its errno provider is the real
previously composed Apple provider. Actual command/flags, source/header and
generated-output inventories have omission and mutation negatives. This is
static linkage, not a claim that all 32 APIs were dynamically tested.

Six focused groups passed in 2.124 seconds:

```sh
RPI5_DNS_WIRE_PACKAGE="$PWD/build/rpi5/apple-ssh-dns-wire-8gn7d87_" \
RPI5_DNS_WIRE_MANIFEST_SHA256=94cbbbb09610948dd30142aebcb5b1df07fe302c1c9bc3169c1cffb004926b19 \
python3 -m unittest tools.rpi5.tests.test_apple_ssh_dns_wire -v
```

No target execution, network operation, resolver transport/service, modern
private FILE ABI compatibility, accepted-runtime replacement or exhaustive
parser audit is claimed. `res_9_init`, `res_9_query`, `__res_9_state`, libinfo
destination selection, bootstrap, notify/logging, stdio, dyld and GSS-related
dependencies remain explicit. This artifact and its three source/test files
are preserved independently of all hardware trial images.
