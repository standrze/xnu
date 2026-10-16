# Native Apple tree integration requirements

This is a consumer-derived checkpoint, not a complete tree schema or boot proof.
The generic serializer exists; the Pi runtime tree builder does not yet exist.

## Early clock identification

`pexpert/arm/pe_identify_machine.c:pe_identify_machine` first looks for `arm-io`.
Its SoC-base lookup reads `device_type` as a terminated string and the second
native uintptr in `ranges` as the physical base. Linux FDT big-endian ranges
cannot be copied unchanged. The exact Pi mapping must be deliberately translated;
do not create a fictional Apple register window to satisfy this lookup.

When this path proceeds, `/cpus` must exist. Children with `state=running` supply
native-endian clock values. Supply `timebase-frequency` as an explicit four-byte
little-endian value from the observed counter frequency. `bus-frequency` and
`clock-frequency` also affect derived clock fields. After clearing the clock
structure, the code overwrites its initial bus fallback with `bus_frequency_hz`;
omitting the property on a running node therefore leaves the final divisor zero.
The builder must obtain valid nonzero clock values, or the BCM2712 platform path
must be deliberately adapted and tested. Arbitrary constants are not a solution.

## CPU topology

`osfmk/arm64/machine_routines.c:ml_parse_cpu_topology` requires `/cpus` and a `reg`
property per included CPU, read via `ml_readprop` and narrowed to uint32. Its
cluster/CPU extraction uses the kernel's MPIDR macros and compile-time topology.
The standalone probe's success with affinities 0, 0x100, 0x200, 0x300 does not
prove that XNU interprets this topology correctly. Preserve runtime affinity
evidence and review the MT/affinity interpretation before generating an SMP tree.
Do not replace physical affinities with invented sequential IDs.

The current BCM2712 configuration already reserves four logical cluster slots
and physical cluster IDs 0..3 with HAS_CLUSTER enabled. The current macros use
Aff1 for cluster and Aff0 for CPU. Consequently the Pi affinities produce four
one-CPU logical clusters, not four cores in a single modeled cache domain. An
extracted-source regression now checks the cluster-offset loop for every
nonempty subset of these affinities: offsets plus Aff0 are distinct, compact
and within MAX_CPUS. This resolves array-index capacity for this representation,
not cache-sharing/scheduler topology correctness, reset execution or XNU SMP.
The eventual builder must mark exactly the actual boot CPU `state=running`;
`ml_is_boot_cpu` uses that property rather than checking MPIDR itself.

## Boot entropy

`pexpert/gen/pe_gen.c:PE_get_random_seed` reads `/chosen/random-seed` and erases
the consumed bytes in place. Consequently the constructed tree needs writable,
reserved storage, not a read-only view into a container. Missing/empty/all-zero
seed input is rejected by that consumer. `osfmk/prng/prng_random.c` requests
4 * SHA512_DIGEST_LENGTH = 256 bootloader bytes for ARM64.

Length/nonzero checks cannot establish entropy quality. The actual source,
freshness, acquisition failures and seed lifetime remain unresolved. Do not use
a fixed fixture, board serial number, timestamp or host-packaged seed as the
runtime entropy provider. Never log or preserve runtime seed bytes in reports.

## Integration order

1. Resolve runtime clocks, translated MMIO, CPU interpretation and entropy source.
2. Construct explicit native-endian properties in caller-owned buffers, preserving
   physical identities and omitting unsupported optional Apple facilities.
3. Encode the tree, reserve its exact bytes after the kernel, and include it plus
   boot arguments and every other live allocation in bootstrap/topOfKernelData
   validation.
4. Verify against the actual XNU consumers, then capture board execution evidence.

Other consumers and optional-to-mandatory paths still require review. This file
does not authorize a minimal tree as sufficient for XNU startup.
