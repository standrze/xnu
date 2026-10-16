# DGT1 PTY transport

This experimental opt-in transport carries bytes over the current seven-bit
kernel console. It is independent of the frozen DGA1 managed execution protocol.
It requires `build.py --mode zsh --storage --pty --framed-terminal` and the host
CLI's `darwin run --interactive --framed-terminal`. Neither side silently falls
back to sending unframed keystrokes to an incompatible image.

After configuring the console raw, the relay emits the exact own-line marker
`DARWIN:PTY:READY:1`. The host sends HELLO with its fresh 32-lowercase-hex session
ID and initial size. The guest creates a real controlling PTY with that size,
forks Apple's source-built zsh, and acknowledges HELLO before relaying bytes.

Each LF-terminated ASCII record has this form:

```
DGT1|H/G|session32|sequence8|TYPE|length4|payloadhex|crc32hex8
```

Numbers are lowercase fixed-width hex. CRC32 (IEEE polynomial `0xedb88320`)
covers everything before the final `|`. The console may add trailing CRs before
LF; these are removed only from the envelope, never from decoded payloads.
Records are shorter than 640 bytes and payloads at most 256 bytes. Independent
direction sequence counters begin at 1; missing, duplicate, wrong-session,
corrupt and malformed records invalidate the session. CRC is error detection,
not authentication or an isolation boundary.

| Direction | Type | Payload |
| --- | --- | --- |
| H → G | HELLO | Initial rows and columns, two unsigned big-endian 16-bit values |
| G → H | HELLO | Exact accepted initial size |
| H → G | INPUT | 1–256 unchanged input bytes, including signals/escape sequences |
| G → H | OUTPUT | 1–256 unchanged bytes read from the PTY master |
| H → G | RESIZE | Nonzero rows and columns, same representation as HELLO |
| G → H | SIZE | Exact size after successful XNU `TIOCSWINSZ` |
| G → H | EXIT | One byte, shell exit status (128 + signal when applicable) |
| G → H | GPU | Opt-in bounded typed compute request; see SHARED-GPU.md |
| H → G | GPURES | Matching typed result/error, never PTY input |

GPU requests are accepted only after HELLO. There is at most one outstanding
request, and EXIT is rejected until its response is queued. Without host GPU
opt-in, requests return an explicit unavailable status; no fallback is used.
The original PTY-only image and frozen DGA1 protocol are not changed by this
optional extension. [Typed payload and ownership](SHARED-GPU.md).

Host `SIGWINCH` reads the real host terminal size. Applying the resize to the
guest PTY invokes XNU's normal foreground-group `SIGWINCH`; the host does not
fake zsh variables or run a substitute signal handler. Ctrl-C/Ctrl-Z are INPUT
bytes interpreted by the guest's real line discipline. External host TERM/INT
still stop the VM through the existing lifecycle policy.

The relay retains partial serial/PTY writes. It stops reading new host input
while one decoded INPUT is pending; it does not discard later frames under
backpressure. Host pre-handshake input is capped at 8 KiB and the encoded write
queue at 64 KiB. Existing session runtime and 64-MiB serial-capture limits remain.
Host output uses a separate 1-MiB bounded queue with write-readiness callbacks.
After VM stop it gets at most two seconds to drain; queue overflow or a drain
deadline fails explicitly instead of blocking the lifecycle queue. This is not
a production terminal service.

`serial.bin` preserves the wire and boot diagnostics; `terminal-output.bin`
preserves only decoded PTY bytes. `result.json.terminal` records the handshake,
acknowledged sizes, decoded byte count and shell exit. A VM start alone does not
prove any terminal behavior. `terminal_trial.py` exercises actual guest editing,
history, job control, resize and high-bit input/output on copied virtual media.
Zsh's current profile still lacks the optional compctl module and multibyte
locale support; byte-preserving transport is not a claim of Unicode support.
