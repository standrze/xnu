# Timed payload diagnostic

Candidate `bl33-probe-two7sghd`, probe SHA-256
`f519035e0265ac91a0f45bf52703d9917edf205a5034028197dd66ae1227e890`,
passed 114 host tests and the native embedded-kernel audit. SD copy hash matched;
recovery configuration remained unchanged.

Continuous capture: `build/rpi5/serial-capture-f9vy9aos`.
The receiver was ready before the agent requested reboot over SSH.
The probe reports UART nominal success, PSCI-binding success and CPU-topology
success. Last payload marker is `CONTAINER_HASH_BEGIN`, CNTVCT=0x481f2da.
No subsequent stage or exception marker appears before firmware restarts.

The same capture records BOOTSYS restart with AON_RESET=3, PM_RSTS=0x20,
BOOT_ORDER override 0xf6 and BOOTMODE=0x06, followed by Linux boot.
SSH independently confirms `/dev/nvme0n1p2` as root. No second reboot command
or manual recovery was requested. This closes the prior capture gap and
demonstrates reset-to-NVMe recovery for this diagnostic configuration.

The remaining immediate question is whether container hashing is slow or stuck
under MMU/cache-off execution. Do not remove integrity verification or count
this reset as a successful payload check. Add bounded progress inside hashing,
and put inexpensive independent checks before that expensive stage where their
own prerequisites permit it. CPU_ON, reservation completion and XNU execution
remain unproved.

Follow-up candidate `bl33-probe-wy8fzchm` adds count-only hash progress at
entry and after each 256 KiB update, with architectural counter timestamps in
the probe observer. Integrity checking still covers every byte and compares
the final digest. Default observer is a no-op for other users; no input bytes
or digest are exposed to it. All 114 host tests passed; additional SHA reference
vectors immediately below/at/above chunk boundaries also passed. The candidate
build succeeded but has not yet been deployed or board-verified.

Completed continuous capture has 38603 bytes, SHA-256
`dcd8faabaef0f74c28a0d88ebac48f3a9c36903fd0b7d43561c1035bdb7947a2`.

## Hash-progress board run

Probe `bl33-probe-wy8fzchm` was deployed with matching local/SD SHA-256
`f40b68e0f553a769332b3aaaa7aa6bc84f7a69c92fd5105238db95fa4856f4a4`.
Capture `serial-capture-qsn980sz` shows completion of the 64-byte table hash,
then monotonic 256 KiB progress through 0xd00000 bytes of the 0xf74e78-byte
kernel. First kernel counter is 0x497265f and last is 0x2f9b49ae, with declared
CNTFRQ 54 MHz. The watchdog then resets the board; the same capture shows the
0xf6 boot-order override. SSH confirms NVMe Linux recovery again.

This rejects the immediate-stall hypothesis: hashing is progressing, but the
15-second recovery interval is shorter than this MMU/cache-off workload. Full
kernel digest comparison is still unproved. Investigate supported timeout
extension or bounded progress-based watchdog servicing, retaining a total
deadline. Do not bypass the hash or disable recovery indefinitely.
