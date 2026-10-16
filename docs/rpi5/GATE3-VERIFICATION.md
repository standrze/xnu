# Gate 3 hardware verification protocol

Gate 3 exit is defined in [PLAN.md](PLAN.md): four-core concurrency and
cross-core invalidation, applicable XNUPOST, 20 consecutive cold boots, and an
eight-hour timer/IPI/SMP soak. Host model tests and standalone loader probes do
not satisfy these XNU runtime requirements.

## Required observations

1. Record the exact kernel, dSYM, link map, source revision, boot image hashes,
   board identity, firmware, boot arguments and XNUPOST configuration. Keep raw
   serial bytes and acquisition metadata for every run.
2. Run a four-CPU workload that proves all four *XNU scheduler* CPUs execute
   concurrently and share state correctly. Record per-CPU execution counters and
   assert their CPU IDs are distinct. Emit `RPI5XNU:SMP_CONCURRENCY:PASS` only
   after the assertions, or `FAIL` when any assertion fails.
3. Test a mapping change initiated on one CPU and observed on every other CPU
   after cross-core TLB invalidation. Include repeated map/unmap and permission
   changes under load; stale data or permissions must fail. Emit
   `RPI5XNU:CROSS_CORE_INVALIDATION:PASS|FAIL`.
   The current board-passing `--gate3-tlb-trial` image proves 16 kernel-VA
   remaps, eight permission checks, and 64 concurrent remaps, half with
   read-only permissions checked on remote CPUs. A separate board-passing
   trial covers user ASIDs. These are standalone results; do not alias either
   trial's PASS to the combined-image
   `CROSS_CORE_INVALIDATION:PASS`.
4. Inventory the XNUPOST cases that build and apply to BCM2712 DEVELOPMENT.
   Run them on the four-core kernel, save each case/result and failures, and
   emit `RPI5XNU:XNUPOST:PASS|FAIL` for the selected suite. Document exclusions
   by test name and reason; an empty suite cannot pass.
5. After the preceding tests pass, perform 20 consecutive **power-off** cold
   boots of the same image. Record the power cycle method, serial capture and
   boot number for each. Every boot must reach the kernel's four-CPU ready point
   and a live PID 1; any failed attempt breaks the streak. Distinguish power
   cycling from watchdog reset or Linux `reboot`. Follow the separate
   [cold-boot protocol](GATE3-COLD-BOOTS.md); it is not started yet.
6. On that image, capture an uninterrupted eight-hour run with timer, IPI and
   SMP work continuing throughout. Record monotonic elapsed time, per-CPU
   counters at regular intervals, faults and the final result. The current
   `capture_serial.py` limit is 600 seconds; use the independently running
   receive-only `long_serial_capture.py` on the serial host for this run.
   Preserve its unfiltered raw output and acquisition
   metadata. A sequence of five-minute captures cannot prove continuity.

The 2026-09-26 eight-hour run passed on an earlier soak image, before the
four-core concurrency and cross-core invalidation trials. Classify it as
valuable endurance qualification, **not**
the final Gate 3 exit soak: the exit run must use the immutable image that
passed the preceding tests and 20 cold boots. A rebuild changes that image
identity. Record boot arguments for each boot; do not silently substitute a
different diagnostic configuration and call it the same tested system.

`build_probe.py` keeps standalone kernel-TLB, user-TLB, concurrency, XNUPOST and soak modes
mutually exclusive. An additional opt-in `--gate3-qualification-config` mode
provides a sequential coordinator. Its 34 selected XNUPOST cases and each
standalone trial passed separately on the earlier kernel. The first combined
image booted, but failed strict pre-soak and cache-visibility checks; a revised
combined image is host-built and unbooted. The configuration uses indices printed by the exact
kernel build; the builder rejects overlapping or reordered index ranges.
Passing the standalone kernel-TLB trial alone is still narrower than the required
`CROSS_CORE_INVALIDATION` result. The opt-in user-ASID TLB trial exercises
remote user translations; both standalone trials passed, but the revised
combined coordinator remains unproven on the board. The user-ASID trial rejects a post-warmup local
TLB flush caused by switching into its temporary pmap, because such a flush
would invalidate the remote-shootdown inference. Verify the final image's binary/hash and
embedded boot command line across its cold-boot streak and final soak. A
developer-only `1_1`
container build checks wiring, not test selection or hardware behavior.

The coordinator starts on its own kernel thread after `bsd_do_post()` and the
PID 1 launch path. It requires the acquire-read XNUPOST aggregate status to be
pass, starts concurrency and waits for its terminal status, then starts the
kernel-TLB and user-TLB trials in order, waiting for each terminal status.
Only after both pass does it emit `CROSS_CORE_INVALIDATION:PASS` and call
`rpi5_gate3_enable_soak(28800)`. Each trial has a 45-second coordinator
timeout; failure or timeout emits permanent `QUALIFICATION:FAIL` and never
arms the soak. `QUALIFICATION:PRE_SOAK_PASS` means only that the soak was armed,
not that the eight-hour run or full Gate 3 passed. Its first board capture
reached this marker but failed subsequent verification; it has not passed.
There is an additional hard timing constraint: `pe_init_fiq()` grants the
pre-soak watchdog only 120 seconds, with at most 24 five-second reloads, and
`pe_rpi5_watchdog_enable_soak()` resets its deadline only when qualification
arms the soak. Measure the selected XNUPOST and standalone trial durations on
hardware before relying on this sequence. If their combined worst case cannot
fit the recovery window, add a separately bounded qualification watchdog mode;
do not start the eight-hour soak early merely to evade the limit.
The selected-suite checker accepts `--require-timing` and reports
`duration_seconds` from the unique `RPI5XNU:XNUPOST:TIMING` line; use it with
`--require-summary` for new board captures. In these strict modes it also
requires all XNUPOST records to belong to the first `BOOTSYS` segment, so a
later fallback boot cannot fill missing case or summary evidence. The standalone concurrency,
kernel-TLB and user-TLB trial `TIMING` lines use the same tick/frequency units.
For a selected case that passes overall but emits an inapplicable subtest
`TESTSKIP`, use `--allow-skip CASE=exact message` only after inspecting and
documenting that subtest's source and platform precondition. The checker
requires the exact message and count; an unlisted or changed skip fails.
On this Pi's full 34-case run, `xnu.vm_tests` emitted one MTE-only skip with
the exact message `System not designed to support this test, skipping...`
from `vm_tests.c` when neither `HAS_MTE` nor `HAS_MTE_EMULATION_SHIMS` is
available. The case still completed and had a passing assertion. Carry this
one named exception into the final combined-run checker; do not exclude the
whole VM case or treat other skips as passing by default.
For each new standalone trial capture, run
`python3 tools/rpi5/check_gate3_trials.py SMP_CONCURRENCY serial.bin` or
`python3 tools/rpi5/check_gate3_trials.py TLB serial.bin` or
`python3 tools/rpi5/check_gate3_trials.py USER_TLB serial.bin`. This requires one
boot marker *before the trial PASS*, four online CPUs, live PID 1 in the same
first boot (possibly after a very fast trial PASS), an exact
terminal PASS, the expected
workload detail and one valid timing line, and rejects any explicit runtime
failure. It reports raw SHA-256 and duration; a passing report is still only
evidence for that trial, not for the full cross-core invalidation requirement.
Later `BOOTSYS` output from the intended watchdog return to Linux is allowed.
The checker keeps these required observations within the first XNU boot,
so later boot output cannot be combined with an earlier trial PASS.
For PID 1 liveness it accepts either the one-time `OK` line or a later `TICK`:
the earlier TLB board capture had UART interleaving that garbled `OK` while
subsequent ticks were intact.

Before staging the current four standalone packages, run
`tools/rpi5/check_gate3_package_set.py` with `--inventory`, `--concurrency`,
`--kernel-tlb`, `--user-tlb`, `--kernel` and `--init` paths. It hashes the
actual images and inputs, checks each manifest's exclusive opt-in, and requires
one shared kernel and RAMDisk identity. This guards against mixing builds; it
does not prove physical placement, boot, or runtime behavior.

Every runtime result line uses a complete line in the form
`RPI5XNU:<stage>:PASS|FAIL`. The stage must be uppercase ASCII letters, digits
or underscores and begin with a letter. A PASS is emitted only after the
associated assertions finish. FAIL is never erased by a later PASS. The
following command extracts exact markers from raw captures, includes each raw
SHA-256 and exits nonzero for any FAIL or missing required PASS:

```sh
python3 tools/rpi5/check_gate3_serial.py \
  --require SMP_CONCURRENCY --require CROSS_CORE_INVALIDATION \
  --require XNUPOST path/to/selected-run/serial.bin > gate3-markers.json
```

That command checks marker evidence only. It does not infer CPU concurrency,
power removal, XNUPOST applicability, or eight hours of continuous operation
from text. The final audit must pair its JSON with raw captures, run metadata,
workload source, test list and timing records before declaring the gate passed.

For a long-soak capture, after copying the recorder's `serial.bin` and
`state.json` into one local directory, also run:

```sh
python3 tools/rpi5/check_gate3_soak.py --seconds 28800 \
  path/to/long-capture > gate3-soak-check.json
```

This verifies the raw hash against the recorder metadata, a finished capture,
the requested and actual capture durations, an arm marker preceding the timed
pass, 64-IPI/cache markers, monotonically advancing
heartbeat ACKs without a gap exceeding 120 counts, absence of explicit
failures, and Linux serial output after a recovery BOOTSYS banner. The arm,
heartbeat, IPI/cache and timed PASS evidence must all occur within the first
BOOTSYS segment; a second warm boot cannot complete a broken soak. It tolerates one
observed non-digit UART interleave immediately before the arm duration.
It is a conservative evidence check, not a replacement for the separate
NVMe-root and SD-fallback verification or the other Gate 3 exit tests.

For the eventual *combined qualification image*, run the ordered checker
against that run's finished recorder directory. The exact 34 selected names
from the current-kernel TOC are fixed in
[`gate3_selected_cases.txt`](../../tools/rpi5/gate3_selected_cases.txt):

```sh
python3 tools/rpi5/check_gate3_qualification.py path/to/qualified-capture \
  --require-case-file tools/rpi5/gate3_selected_cases.txt \
  --allow-skip 'xnu.vm_tests=System not designed to support this test, skipping...' \
  > gate3-qualification-check.json
```

For each cold-boot capture, use the same command with `--pre-soak-only`
before removing power for the next attempt. This checks the full named suite,
trial details/timings and ordered `QUALIFICATION:PRE_SOAK_PASS` without
pretending the eight-hour result exists. It does not prove physical power-off
or image identity; those require the separate ledger and operator review.

It composes the named-suite, three standalone-workload and long-soak evidence
checks, and additionally requires their qualification markers to occur exactly
once, in order, in the first XNU boot. It does **not** credit the separate
20-power-off cold-boot streak, assert XNUPOST applicability, or prove the
capture came from the recorded image hash; those remain audit obligations.

## Next hardware transition: combined qualification image

The preliminary 28,800-second soak and all separately bounded trials passed;
their raw captures and hashes are recorded in [GATE3-AUDIT.md](GATE3-AUDIT.md).
The Pi returned to NVMe Linux (`/dev/nvme0n1p2`) after each trial, and the
`XNU_PROBE` SD fallback was restored and verified at SHA-256
`dda91fe297e3266ff96b75b29b9821d27892e9647d05dfd4d9d518c29e67849c`.
The revised combined 1–34 candidate is
`build/rpi5/bl33-probe-ci45m9zs/probe.bin` (SHA-256
`454906aa802f013549ef936a9d15bcc42b10638ed73d6759a276797737b1d06c`).
It embeds kernel SHA-256
`564aa144bc3c50f7e7a231c8c2a32e164885603182e983048a5d2ba4bc3c300f`
and the same RAMDisk as the earlier standalone trials. Its native/container
comparison passed, but it has **not been booted**. The preceding combined
image's failed raw capture is documented in [GATE3-AUDIT.md](GATE3-AUDIT.md)
and cannot count toward the 20-pass streak.

Before staging it, establish a verifiable way to remove and restore the Pi's
5 V input power for 20 consecutive cold boots. Linux `reboot`, watchdog reset,
and a merely low-power state do not count. Start a receive-only serial capture
before each boot, record image identity and power-cycle method, and check the
first boot's ordered chain through `QUALIFICATION:PRE_SOAK_PASS` before removing
power for the next attempt. Once 20 same-image boots pass, leave the unchanged
image running for its final uninterrupted eight-hour soak and preserve its
complete capture and recovery evidence. Do not count any prior standalone
boot or the preliminary soak toward this sequence.

## Source inventory of candidate XNUPOST cases

The BCM2712 DEVELOPMENT configuration inherits `config_xnupost` from its
documented `KERNEL_DEV` composition
([configuration](../../config/MASTER.arm64.bcm2712)); the token selects
`CONFIG_XNUPOST` ([master mapping](../../config/MASTER)). The test sources are
selected through `optional config_xnupost` entries in
[osfmk/conf/files](../../osfmk/conf/files) and
[bsd/conf/files](../../bsd/conf/files). This is source-level build eligibility,
not proof that a fresh BCM2712 image has linked or run any case. At runtime,
`kernPOST=0x1` enables the on-device suite; `kernPOST_config` selects test
numbers, which must be read from that exact image's printed test table of
contents rather than hard-coded here
([XNUPOST implementation](../../osfmk/tests/kernel_tests.c),
[usage](../../osfmk/tests/README.md)).

| Named case | Source and Gate 3 relevance | Qualification before inclusion |
| --- | --- | --- |
| `ipi_test` | [processor.c](../../osfmk/kern/processor.c) binds the test thread to each registered processor and invokes `arm64_ipi_test`; direct IPI candidate. | Confirm all four CPU IDs in serial and a real interrupt on each. The loop alone does not prove simultaneous traffic. |
| `arm64_lock_test` | [platform_tests.c](../../osfmk/arm64/platform_tests.c) calls the ARM lock tests; synchronization candidate. | Inspect the selected lock subtests and confirm they actually run on distinct BCM2712 CPUs. |
| `pmap_test` | Registered in [bsd_tests.c](../../bsd/tests/bsd_tests.c), implemented by the non-SPTM [ARM pmap](../../osfmk/arm/pmap/pmap.c); mapping lifecycle candidate. | Review its assumptions for the 16 KiB BCM2712 pmap and capture every subtest result. It cannot substitute for explicit cross-core stale-TLB observation. |
| `vm_tests` | [vm_tests.c](../../osfmk/vm/vm_tests.c) covers map, fault, wiring and accounting cases; VM regression candidate. | Check each subtest for unsupported pager or platform assumptions before running. |
| `test_thread_call` | [test_thread_call.c](../../osfmk/tests/test_thread_call.c) checks scheduled callbacks, deadlines and wakeups; timer/scheduler candidate. | Confirm the callback ran and the test's timeout bounds hold on the board. |
| `vfp_state_test` | [vfp_state_test.c](../../osfmk/tests/vfp_state_test.c) starts multiple threads and checks preserved FP state; context-switch stress candidate. | Registered only with `__ARM_VFP__`; verify the build guard and CPU distribution. |
| `test_os_log_parallel`, `console_serial_parallel_log_tests` | Registered in [kernel_tests.c](../../osfmk/tests/kernel_tests.c); parallel logging candidates for contention and console survival. | Confirm logger dependencies are present and that execution spans multiple CPUs. |
| `counter_tests` | [counter_test.c](../../bsd/kern/counter_test.c) checks a startup increment of a scalable counter. | Useful as a startup regression, but it does not exercise cross-core counter traffic. |
| `copyio_test`, `parse_boot_arg_test` | Registered in [bsd_tests.c](../../bsd/tests/bsd_tests.c); general boot and memory-access regressions. | Include when linked and runnable; neither establishes SMP correctness. |

Conditional exclusions are `ctrr_test` without CTRR/PV-CTRR,
`arm64_ropjop_test` without Apple PAC, MTE tests without `HAS_MTE`,
`specres_test` without `HAS_SPECRES`, and SPTM-only tests on the non-SPTM
BCM2712 pmap. These guards appear in
[kernel_tests.c](../../osfmk/tests/kernel_tests.c) and
[bsd_tests.c](../../bsd/tests/bsd_tests.c). `arm64_late_pan_test` depends on
`__ARM_PAN_AVAILABLE__`, which [BCM2712.h](../../pexpert/pexpert/arm64/BCM2712.h)
defines; qualify it against actual board support before including it. Preserve
the generated test table of contents and record any additional exclusion by
exact case name and reason. The current board audit in
[GATE3-AUDIT.md](GATE3-AUDIT.md) records passing `xnu.ipi_test` and
`xnu.pmap_test` runs. Those individual results do not constitute the selected
Gate 3 XNUPOST suite or close the exclusions audit.

For each selected suite capture, check the named cases rather than relying
on `kernel_do_post()` returning success: `xnupost_run_tests()` records
individual `TESTBEGIN`/`PASS`/`FAIL`/`TESTEND` events but returns
`KERN_SUCCESS` even after an assertion failure. Run, for example:

```sh
python3 tools/rpi5/check_gate3_xnupost.py \
  --require xnu.ipi_test --require xnu.pmap_test \
  --require-summary \
  path/to/selected-run/serial.bin > gate3-xnupost-check.json
```

The checker requires one complete, non-skipped run of each named case with
at least one passing assertion, balanced XNUPOST start/finish events, and no
assertion or runtime failure anywhere in that capture. It rejects the older
broad-selector `ipi_test` capture because three VFP assertions failed there,
even though the IPI case itself passed. The exact `pmap_test` capture passes
its single named-case check; neither result claims a complete selected suite.
New exact-selector images also opt in to an on-device
`RPI5XNU:XNUPOST:PASS|FAIL SELECTED=N PASSED=M` summary after the BSD POST
phase. It counts only non-ignored kernel and BSD cases and requires a nonempty
selection with all cases marked passed. This marker is additional evidence,
not a substitute for checking named cases and their raw assertions. Use
`--require-summary` for the new qualification image: it also requires the
reported selected/passed counts to equal the explicitly named case list.
Omit it only when auditing older captures that predate this marker.

The archived inventory capture
`build/rpi5/serial-capture-7qhww_gg/serial.bin` observed these table entries
for its then-current image: `test_thread_call` #16, `vfp_state_test` #23,
`vm_tests` #24, `arm64_lock_test` #28, `pmap_test` #30, and `ipi_test` #32.
These numbers are **not** assumed stable across images. An inventory image
from the newer concurrency-trial kernel has been host-validated at
`build/rpi5/bl33-probe-bacc6gkb/probe.bin` (SHA-256
`c06feb38da463cf4327c729ab5b033bce1c9cf3ab85445d1bf329e049a804c4a`),
but must run on board after the ongoing eight-hour soak before selecting
new test indices. A sensible sequence is timer/thread-call, lock, VFP,
then VM cases, each in a separately bounded watchdog-backed image; retain
both passing and failing raw logs. The lock test invokes the broader
`lt_test_locks()` suite; the VFP test spawns four threads but does not bind
them to distinct CPUs, so it cannot replace the dedicated concurrency trial.

The probe builder now accepts `--gate3-xnupost-config` with explicit
comma-separated inclusive ranges (for example `16_16,23_24`) and rejects
bare indices or malformed ranges. A host-only container trial verified that
the exact selector survives into the embedded boot command line. Its example
indices came from the **older** inventory and are not approved for the
current kernel until that kernel's table is captured on the Pi. The selector
still runs separately from concurrency, TLB and soak modes.
