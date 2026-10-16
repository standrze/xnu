# Opt-in normal console records

This is software-only qualification of `display-console-records-691ku6u6`.
It has not been prepared, installed, or executed on the Pi. No frozen image or
global/default source was changed. The candidate retains the normal firmware,
the same Apple framebuffer renderer/mapping, the real reboot CLI, the original
180-second terminal deadline and 15-second hardware watchdog fallback.

## Cause and changes

The old ordinary `kprintf` owns `kprintf_lock`, while `/dev/console` writes
through the Apple console ring and its separate flush mutex. Both eventually
reach the same PL011; the old FIFO-space test and DR write are separate. These
locks do not serialize the two streams. Terminal service was also reachable
from CPU0 timer IRQ, so merely adding an IRQ-enabled dispatch would not cover
its readiness record.

The distinct profile changes six kernel owners:

- `pe_kprintf`: before its existing IRQ masking, eligible normal thread calls
  use the original Apple print buffer, formatter and console ring. Records up
  to 255 bytes occupy one ring reservation. Longer output is split without
  truncation; it is not claimed to be one atomic record. Both original logging
  and raw fallback paths remain.
- `serial_console`: accepts only initialized serial-console, IRQ-enabled,
  preemption-zero, noninterrupt/nonpanic/nondebugger/non-PPL thread context.
  A recursive call from the ring's current UART/video drainer is refused, so
  it cannot sleep trying to reacquire its own flush mutex.
- `pe_serial`: a single nonblocking inline CASA protects the PL011 FR test and
  DR store. Interrupt state is restored on either result. There is no sleep,
  video, console or scheduler operation while this small guard is held.
- `sleh`: retains the existing allocated one-second callout and publishes its
  armed state before `thread_call_enter_delayed` can make it runnable. That
  function's return value means “already queued,” not success or failure. Terminal IRQ
  service is excluded; early/nonterminal IRQ service remains.
- `pe_fiq`: terminal servicing requires the armed callout and normal thread
  context before any PM write or readiness publication. The brief
  enabled-but-unarmed transition and a missing owner perform no service; they
  do not extend the deadline. The original deadline-establishment expression,
  counter epoch, five-second reload check and maximum-three root reports are
  retained verbatim.
- Restart policy: only boot `RESTART:READY` uses the normal record API. The
  post-halt bounded raw `PRE_SMC`/returned-call implementation, fixed PSCI
  leaves, one-shot policy and nominal-only rate claim are unchanged.

Only `/sbin/launchd` changes in the RAM root. Its signal-mask/pending/reap/stop
policy is identical; its actual-state label becomes:

```
RPI5XNU:INIT:SHUTDOWN_READY MASKED POLLED STOP_LATCH
```

Including both newline frames and TTY CRLF expansion, the new report fits
inside the actual 80-byte `kmoutput` chunk. The previous report needed 83
bytes. This is a bound for an otherwise empty TTY queue, not a promise about
arbitrary backlog, unbounded stdout, early output or raw exception writers.

## Evidence and limits

Five core groups pass: actual generated Apple ring/print-buffer/kprintf bodies
under explicit host locks, formatter, clock and MMIO doubles; 4,000 contended
normal records; 4,000 contended FIFO stores; recursion/IRQ/context/full-FIFO
refusals; original split-check FIFO overflow model; actual watchdog service and
gate with IRQ, unarmed/missing owner, failed route and deadline cases; and all
six actual whole-owner Cortex-A76 translation units. The callout harness also
executes the first callback synchronously from the enqueue double: armed state
is already visible, service occurs once, and the callback requeues itself.

The actual linked image has zero undefined kernel, PID1 and loader symbols.
The original 205-case PID1 native signal-policy oracle still passes. Three
package groups pass, including actual same-image native loader materialization
and closure/type/owner mutation negatives. These are not target timing or
physical UART/HDMI/reset proofs.

The new A76 frames are 336 bytes for formatted records, 320 for literal
records, 32 for the UART leaf and 16 for the thread-owner check. The inherited
original `handle_bti_fail` retains its dynamic stack usage; its reported
64-byte static portion is **not** a bound on that unrelated failure path.

Panic, IRQ, early boot, debugger, post-halt and explicit unbuffered writers
retain raw escape paths. They can still interleave with normal traffic; no
universal serial atomicity or physical delivery guarantee is made. Scheduling
or console failure still leaves the finite watchdog fallback in control.

## Qualification

```
python3 -m unittest tools.rpi5.tests.test_console_records -v
RPI5_CONSOLE_RECORD_PACKAGE=/Users/stephen/Documents/ChatGPT/xnu/build/rpi5/display-console-records-691ku6u6 \
RPI5_CONSOLE_RECORD_MANIFEST_SHA256=f32e6b5a155d1869b51511db4993d3298765914bba2cf59784108922d38b6cb1 \
python3 -m unittest tools.rpi5.tests.test_display_console_records -v
```

Image: 20,187,584 bytes,
SHA-256 `735f901b07895e1cbf6460c0657d46268e77871683d1f90d882efccf2d19316b`.
Tag: `b8f942ef8e1543b0b962f5bb7797df1b`.

The manifest seals 24,401 inherited and current inputs, 835 compiler-discovered
headers, 108 generated artifacts and all 40 command/log results. Principal
current-source pins are:

- profile `c97b9a3823e76795bf9da76aa41e1d3feec2fdd06ab44dd8e3a1dadb1342d7de`
- console record body `8357f752040edfc86347c687728211c618bbce7612b45e98f2b5b7b1c23e5941`
- PL011 leaf `4de62aa7104b67bf9710d85f3e19532683f103467cdec7e957150bf5da76ebe5`
- native host `aa2d53787ca9ce774333b2f0036976afd175db86d424c464f32929be2e9593a1`
- core test `58987c14210d6d2df58f90436ebe4d7bda6865fabbcaf51c0d8edb098016c911`
- builder `6729893c90952acbd4ebf254a28197a2e1b8017d7db8e49b0bf0e40fdeee44cf`
- checker `c606b0fdc718999a433d4310b64d721bbcbdbdf54ec732de10941830d6bfac21`

The core suite passed 5/5 in 1.315 seconds. The exact no-compiler artifact
admission, mutation-negative and native loader suite passed 3/3 in 38.428
seconds. These timings are evidence labels, not target performance claims.

No controller, preparation, staged-media change or hardware operation is part
of this qualification.
