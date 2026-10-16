# Experimental shared GPU compute from Darwin

Actual XNU guest → host Metal → guest result, without passthrough. No physical
Pi access, host network listener, arbitrary shaders or host pointers are used.
This is a project typed compute interface, not Apple's Metal ABI or a desktop.

## Actual proof

Two fresh host-generated seeds selected guest vector operands. Source-built
`gpuctl` called the typed C library inside Darwin, through a real AF_UNIX
datagram socket to its init-supervised terminal relay. The relay wrapped the request in its existing
session-checked DGT1 console channel. The host's real Metal compute pipeline ran
the operation on Apple M5 Max, returned the result, and the guest verified each
element. Host observations independently recorded the same operands/results.
An unsupported operation returned status 1 rather than CPU success.

Networking, Apple ZLE editing/history, real PTY/job control, Ctrl-C/Ctrl-Z,
resize/SIGWINCH and binary input/output all passed in the same boot. Normal zsh
exit saved history, unmounted HFS+ and powered off. Four focused host boundary
checks passed; there was no soak.
[Initial GPU evidence](../results/2026-10-12-shared-gpu/verification.json).
[Later combined Apple DNS parser/GPU evidence](../results/2026-10-12-apple-network-gpu/verification.json).

## Build and launch

Add `--shared-gpu` to `userland/build.py --mode zsh --storage --pty
--framed-terminal`, with the same pinned Apple zsh/terminfo inputs. `--network`
and `--apple-dns` are independent optional userland flags; GPU transport does
not rely on IP networking. Package a new EFI image with the maintained loader
and the appropriate kernel profile, preserving the prior checkpoint.

On the signed development CLI use `darwin run --interactive --framed-terminal
--shared-gpu --boot-disk ... --data-disk ... --variable-store ... --output-dir
NEW_DIRECTORY`. Only use an explicitly copied disposable data image and copied
variables template for trials. Add `--network-nat` for the network profile.
`terminal_trial.py --shared-gpu [--network --apple-dns]` exercises the actual
guest and validates independent host Metal observations, not just text markers.

The private working image is `build/apple-network-gpu-working-2026-10-12/`.
It contains the signed CLI, EFI, kernel, RAM root, actual Apple zsh, writable
data image and variables, all hashed. EFI/variables contain entropy: do not
publish this directory or call repeated seed use production-safe. `0.1.0` and
the earlier qualified terminal/network images remain unchanged.

Guest examples:

```sh
/bin/gpuctl selftest 12345
/bin/gpuctl unsupported
```

`src/gpu_client.h` exposes `gpu_client_add(a, b, count, result)` to source-built
guest callers. Vectors are copied, never mapped host pointers. Success is zero;
positive values are host status codes, negative values local transport errors.
On failure the result array is unchanged. This is currently a source client,
not a packaged dylib or a promise of binary Metal compatibility.

## Wire contract and bounds

DGT1 `GPU`/`GPURES` use the enclosing VM's fresh session nonce and strict
direction sequence. The host accepts requests only after HELLO, with one in
flight; a second request or premature EXIT fails the session. CRC is corruption
detection, not authentication. VM channel ownership is the isolation boundary.

All fields below are big endian, including float32 IEEE754 bit patterns:

| Bytes | Request (`GPU`) | Response (`GPURES`) |
| --- | --- | --- |
| 0–3 | `DGC1` | `DGR1` |
| 4–7 | Relay-owned monotonically increasing request ID | Exact request ID |
| 8–9 | Operation: 1 = vector add | Status |
| 10–11 | Element count | Returned element count, zero on error |
| 12 onward | A[count], then B[count] | Result[count] |

Maximum 16 finite float32 elements per request and 1024 submissions per VM,
including rejected requests. Status: 0 success, 1 unsupported operation,
2 invalid request, 3 unavailable/disabled, 4 session quota, 5 execution failure.
Host report storage is independently limited to the first 64 observations.
No CPU fallback, guest-selected shader, buffer handle or memory address exists.

Each VM owns a separate host bridge/Metal queue. Inputs and outputs belong to
one command. A two-second completion deadline disables later submissions on
execution failure; a timed-out command retains its Metal-owned resources until
completion. GPU scheduling itself remains the host driver's responsibility.
This is resource-bounded experimental sharing, not proven hostile-guest isolation.

The guest relay owns `/data/.darwin-gpu.sock`, mode 0600, a bounded receive
queue and one pending datagram. Clients bind private named sockets, use bounded
send/receive timeouts and unlink only their own paths. The relay replaces local
IDs with its own wire IDs and strips them from local replies. It rejects stale
or unsolicited host replies and removes its endpoint on normal teardown.
An unclean VM stop can leave socket paths on its copied disk; startup fails
explicitly instead of deleting an unknown existing path. Crash recovery and
arbitrary applications/graphics remain future work, not hidden fallback behavior.
