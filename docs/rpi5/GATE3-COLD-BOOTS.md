# Gate 3 true cold-boot qualification

Status: no passing boot credited. The separate four-core concurrency,
kernel/user TLB and 34-case XNUPOST trials passed on the earlier kernel. The
first combined-image boot failed strict pre-soak and cache-visibility checks,
so it is not credited. A revised image is host-built but unbooted. The
completed preliminary eight-hour soak is not a cold boot.
Use the **same final combined qualification image** for all 20 cold boots and
the later final soak. Each cold boot must reach the ordered XNUPOST,
concurrency, kernel-TLB, user-TLB, cross-core invalidation, soak-arm and
`QUALIFICATION:PRE_SOAK_PASS` markers before it is credited. The operator may
then deliberately remove 5 V for the next attempt without waiting eight
hours; a timed `SOAK:PASS` is required only on the final uninterrupted run.

Use one immutable image and one verified power-disconnection method for all
20 attempts. A Linux `reboot`, watchdog reset, reset button, or EEPROM
boot-order fallback is **not** a power-off cold boot. Disconnect the Pi 5's
5 V input (or use a power switch that demonstrably removes it), observe the
board powered off, wait at least 10 seconds, and restore power. Do not
disconnect the 4090 serial receiver; it must capture each complete boot.

For every attempt, append a ledger entry **before** starting the next one:

- Consecutive attempt number, immutable boot-image SHA-256, kernel SHA-256,
  Pi identity, EEPROM version and boot arguments.
- UTC timestamps of power removal and restoration, the exact power-control
  method, and independent evidence that 5 V was absent (operator observation
  or a power-meter/switch log). The timing and power evidence require human
  review; serial alone cannot prove removal of power.
- Unfiltered serial capture path, acquisition start/end times, byte count and
  SHA-256. Mark any capture gap, disconnection, or overwritten bytes as a
  failed attempt.
- Exact four-core online marker, one or more live PID 1 ticks, the complete
  ordered pre-soak qualification chain, and absence of a panic or failure
  marker. Record the result as PASS or FAIL and explain any ambiguity rather
  than silently excluding the attempt.

After each capture finishes, run the strict named combined checker with
`--pre-soak-only`, `--require-case-file tools/rpi5/gate3_selected_cases.txt`,
and the exact `xnu.vm_tests` MTE-only skip exception documented in
[GATE3-VERIFICATION.md](GATE3-VERIFICATION.md). Preserve its JSON report with
the raw capture. A PASS here verifies only the serial pre-soak chain; the
ledger still requires independently reviewed 5 V-off evidence.

Any failed or unverified attempt resets the consecutive-pass count to zero.
Keep the failed capture and ledger entry; do not renumber later attempts to
hide a break. Only after 20 consecutive verified passes on the same image
may the cold-boot requirement be marked complete. The audit must pair the
ledger with every raw capture and the independent power-off evidence.

Store the ledger as JSON with `candidate_image_sha256`, `kernel_sha256`,
`sd_image_sha256_before`, `sd_image_sha256_after`, and an `attempts` array.
Hash the actual SD `probe.bin` before the first power cycle and again after
the streak; both values must equal the candidate image hash. Keep the SD
unmodified between those readings and record any intervening Linux writes or
restaging as a broken streak. These endpoint hashes improve chain of custody,
but cannot prove every intermediate boot used that file without operator or
hardware review. Each attempt needs `number`, the same two hashes,
`power_method`, `power_off_evidence`, `power_removed_utc`,
`power_restored_utc`, `capture_dir` (relative to the ledger),
`serial_sha256`, and `result`. Each capture directory contains the
`serial.bin` and either `manifest.json` from `capture_serial.py` or
`state.json` from the independently running `long_serial_capture.py`.
After the sequence, run:

```sh
python3 tools/rpi5/check_gate3_cold_boots.py path/to/ledger.json \
  > gate3-cold-boots-check.json
```

The checker requires matching pre/post SD image hashes, a finished and
hash-matching capture spanning each power cycle, at least 10 seconds off,
and 20 consecutive PASS entries on the same hashes. It independently runs
the strict named pre-soak checker on every capture, requiring all 34 selected
cases, the one exact VM MTE skip, workload detail/timing and the ordered
qualification chain. Each attempt must also show a Raspberry Pi `BOOTSYS`
banner, four-core online marker and PID 1 tick on that first boot, with no
failure marker. This ordering rejects
runtime lines recycled from before the apparent boot. The four-core/PID 1
chain must occur after the **first** BOOTSYS banner in each capture and before
any later banner; a later warm boot cannot rescue a failed initial cold boot.
A subsequent Linux watchdog-recovery banner is allowed. It also rejects
byte-identical serial captures across different attempt directories, which
would otherwise allow one recording to be copied and credited repeatedly.
Its output explicitly keeps
physical-power evidence as a **human-review requirement**; an operator's
ledger assertion cannot prove that 5 V was truly absent, nor can software
prove that no attempted boot was omitted from the ledger.

The SD card is the disposable `XNU_PROBE` boot medium; normal Linux root is
NVMe `/dev/nvme0n1p2`. Before the first cycle, verify the SD label, image
hash and known-good backup. After the last cycle, allow watchdog recovery
to Linux, confirm the NVMe root over SSH, and restore/hash-check the SD
fallback. Do not begin this sequence while the eight-hour soak is running.
