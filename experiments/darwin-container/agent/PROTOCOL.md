# Darwin guest agent protocol, version 1

DC3 is a separate, opt-in managed path. Preserve DC2's shell image and serial
protocol. This initial target is one disposable, exclusive Apple-silicon VZ VM:
PID 1, one agent, and one active job. It is not OCI, a PTY, a network service,
or a hostile-root authentication boundary. Commands receive EOF on stdin.

## Why ASCII framing

The frozen XNU console's `kmoutput` strips bit 7; `kmputc` and TTY processing
insert carriage returns. Raw termios alone cannot make binary serial safe.
The serial poller can fill the 1,024-byte TTY input queue before userland runs.
Use printable ASCII/hex records, small requests, and stop-and-wait control.
Native codec tests do not prove the live console carries arbitrary bytes.

## Wire record

```text
DGA1|H|00112233445566778899aabbccddeeff|00000001|00000002|EXEC|0010|<hex>|<crc32>\n
```

Nine pipe-separated fields, with no spaces:

| Field | Canonical representation |
| --- | --- |
| Magic/version | `DGA1` |
| Direction | `H` host request or `G` guest response |
| Session | Fresh host UUID represented as 32 lowercase hex digits |
| Command ID | Eight lowercase hex digits; 0 for session control |
| Sequence | Eight lowercase hex digits, starts at 1 separately per direction |
| Type | Exact uppercase type below |
| Payload byte length | Four lowercase hex digits, 0–256 |
| Payload | Exactly twice that many lowercase hex digits, empty for length 0 |
| Checksum | Eight lowercase hex digits: standard IEEE CRC32 of all ASCII bytes before the final `|checksum` |

CRC uses reflected polynomial `0xedb88320`, initial `0xffffffff`, final XOR
`0xffffffff`. It detects corruption, not malicious forgery. Every record ends in
LF; decoders remove contiguous CR bytes only immediately before LF. Embedded CR,
noncanonical hex, extra fields, unknown types/version, incorrect length/checksum,
overflow and records exceeding 1,024 bytes fail validation. Parsers have bounded
storage and can discard oversized lines through LF. Neither a suffix of an
oversized line nor an echoed input is an authoritative response.

Boot/kernel noise is retained in raw evidence but not interpreted as agent data,
including unrelated own-line diagnostics after negotiation. Lines starting `DGA`
are protocol candidates; an unknown version is a failure, not ordinary noise.
After negotiation, malformed protocol records or sequence gaps invalidate transport
completeness. Later exit 0 cannot rescue missing output. A fresh delimiter can
recover diagnostic parsing, not success. Valid, checksum-verified `H` echoes may
be ignored by the host; they never advance guest sequence or command state.

The agent first emits the exact own-line `DARWIN:AGENT:READY:1`. The host sends no
managed requests before it. A session is adopted only once through HELLO. Foreign
sessions, repeated EXEC, old command IDs and reordered/duplicate sequences never
launch a process. Session/sequence exhaustion is a failure, not wraparound.

## Messages and ordering

| Direction/type | ID | Payload and meaning |
| --- | --- | --- |
| H HELLO | 0 | Empty; sequence 1, proposes fresh session |
| G HELLO | 0 | ASCII `exec,streams,cancel,shutdown`; sequence 1 |
| H EXEC | 1–16 | NUL-separated argv including final NUL; at most 16 arguments and 256 total bytes, nonempty absolute argv[0] |
| G STARTED | Active | Four-byte big-endian PID, after fork and registration for supervision; group setup is attempted by the parent and required in the child before exec |
| G OUT / ERR | Active | Nonempty stdout/stderr byte chunks, at most 256 bytes |
| G OUT_EOF / ERR_EOF | Active | Empty; each stream completed exactly once, after its final data |
| H CANCEL | Active or most recently completed | Empty; no subsequent EXEC after cancellation intent |
| G CANCELLED | Matching | One byte: 1 accepted active cancellation, 0 already completed |
| G EXIT | Active | Five bytes described below; after both stream EOFs and cleanup |
| H SHUTDOWN | 0 | Empty; requests normal XNU halt; active job is cancelled first |
| G SHUTDOWN | 0 | Empty acknowledgement before normal `reboot(RB_HALT)` |
| G ERROR | Matching or 0 | Bounded ASCII diagnostic code; fatal protocol/I/O/launch-supervision/cleanup error |

EXEC IDs are strictly increasing, starting at 1, with at most 16 commands in a
session and only one active command. The agent execs argv directly with cwd `/`
and a fixed minimal environment. The CLI may deliberately map a user-supplied
shell command to `/bin/sh -c`; it must not interpolate it into the transport.
The managed argv-byte limit is distinct from DC2's larger shell-line limit.

EXIT's five bytes are:

1. Termination kind: 0 normal exit, 1 signal termination.
2. Exit status 0–255, or signal number 1–31 for kind 1.
3. Cancellation accepted: boolean, independent of observed termination.
4. Cleanup verified: boolean; a successful result requires 1.
5. Output cap exceeded / bytes truncated: boolean; a successful result requires 0.

Exactly 1 MiB followed by EOF remains complete. STARTED confirms supervision of
the child PID, not successful exec or workload readiness; an exec failure still
has a terminal status (126 or 127). Cleanup does not rely on process groups.

Normal exit 143 is not signal 15. Host cancellation intent, cancellation ACK,
actual termination and guest stop are recorded separately. If EXIT races ahead
of a pending CANCEL, the guest replies CANCELLED=0 for the most recent completed
ID. The host waits for that ACK before shutdown and does not start another job.
ACK=1 and terminal cancellation must agree; ACK=0 and terminal non-cancellation
must agree. Duplicate host cancellation/shutdown intent does not queue duplicate
control or bypass a pending terminal record/ACK. Output-limit or unverified
cleanup must not start another EXEC.
Stale requests for older/wrong IDs are failures, never applied to another job.

## I/O, flow control and process ownership

The host waits for HELLO before EXEC and STARTED before ordinary further control.
A compact CANCEL may accompany the outstanding EXEC; total queued/in-flight
request bytes remain below 1,024. A new EXEC waits for the previous terminal
record and cleanup. Writes retain a cursor across short writes/EAGAIN and have
bounded queues. No retries may execute a command twice.

Child stdin is an EOF descriptor. Stdout and stderr use independent pipes and
are multiplexed with host control input; no blocking pipe read may prevent
cancellation. The combined decoded output cap is 1 MiB per command. On overflow,
terminate the job and drain/discard remaining bytes rather than deadlocking a
full pipe. Retain all bytes through the cap and set output-limit evidence.
Child descriptors must not leak the agent console/protocol channel.

One exclusive VM contains only init, the agent, and the job. The exact Darwin
`kill` syscall has a third `posix` argument: verified `kill(-1, signal, 0)` excludes
PID 1, system processes and the caller, permitting owned-VM cleanup of descendants
that escape process groups. This is agent-only guest code; never issue a host
broadcast kill. Native test doubles must constrain signals to test children.
PID 1 reaps adopted descendants while waiting for the agent.

Cancellation uses TERM, approximately one second of grace, then KILL. On leader
exit, remaining job descendants are cleaned before terminal completion too.
Reap the leader, drain both streams, and require the source-supported no-remaining-
job-process check (`kill(-1, 0, 0)` returning ESRCH) before cleanupVerified=1.
Bound cleanup/drain time; if verification fails, emit ERROR and fail the session.
The host's bounded VZ stop remains the ultimate cleanup boundary. No success is
claimed until the actual guest-stop callback is observed.

## Host outcome

Preserve raw serial, per-command stdout/stderr bytes, session/command IDs, events,
termination kind/status/signal, cancellation flags, output-limit/cleanup state,
boot input hashes, and actual VZ termination. Display only decoded application
bytes on stdout/stderr in managed mode. A session succeeds only if every requested
command naturally exits 0, streams and transport are complete, cleanup is verified,
SHUTDOWN is acknowledged and the guest stops without VZ error. Exit 1 is a valid
completed command, but not command success. Cancellation is a distinct outcome.

SIGINT, timeout or deterministic cancellation first requests managed cleanup,
then shutdown within bounded grace; failure escalates to forced VZ stop and
cannot be reported as graceful success. A shutdown ACK is not a stopped VM.
Deterministic cancellation time starts at STARTED. A partial protocol candidate
at serial EOF invalidates transport completeness; unrelated incomplete kernel
diagnostics do not. Preserve the first failure even if the VM subsequently stops.

## Acceptance

Native checks: cross-language golden frames, every fragmentation boundary,
coalescing, all 256 byte values, CRC/length/version/type failures, oversized lines,
foreign/stale/duplicate messages, exit-vs-cancel race, separate stream EOFs,
short I/O/EAGAIN/EINTR, launch errors, output cap, and bounded descendant cleanup.

Real fresh-image VZ trials: two sequential commands with exact separate binary
stdout/stderr; normal exit 1; missing executable; cancellation of a TERM-ignoring
job with escaped descendants; output flood/limit; idle/active shutdown and a
bounded failed/forced-stop path. Preserve evidence rather than treating synthetic
tests as guest proof. Fixtures and the guest are built from local source, not
copied macOS binaries. No Pi, installed container services or proprietary macOS
userland are needed.
