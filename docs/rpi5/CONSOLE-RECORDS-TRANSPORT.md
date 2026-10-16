# Console-record trial transport

This is a software-only, source-pinned transport for the sealed
`display-console-records-691ku6u6` image. It has not prepared a directory,
published media, opened the serial device, rebooted the Pi, or executed the
target.

## Exact intake and publication

- restoration: `build/rpi5/gem-cpu-batch-restored-20261014`
- restoration seal: `cda1ffe9a482dcb8db9729025956c40fe81ae57ebf0276bfc1cdca90310b5af1`
- restoration plan: `87822332e49a0e76bfaff2d1b6dff8320942dd3f3e90a8bcb9297d1247e56690`
- Linux boot ID: `1fd308fa-08e5-4aa1-9799-86939ac251aa`
- retained catalog entries: 466
- candidate manifest: `f32e6b5a155d1869b51511db4993d3298765914bba2cf59784108922d38b6cb1`
- candidate image: `735f901b07895e1cbf6460c0657d46268e77871683d1f90d882efccf2d19316b`
- retained checker report: `468b260622e64ce600858fe31f25da7f00bf05814c87453be1b531533495e575`

The operation is a two-target publication, in order: `config.txt`, then
`probe.bin`. The exact normal firmware remains protected as
`413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46`.
The reverse operation restores the original config and known-good zsh loader.
Both operations preserve the entire backup catalog and refuse implicit retry,
rollback, or a power-loss atomicity claim.

An in-memory preparation audit produced checkpoint digest
`a4e9fa72a44d57b6fb8fdc0e5c8d6484a185503ea87813c4834e5acbc4f27999`,
with 31,219 closure entries, 1,634 transport-source entries, and 24,500
recorder package entries. This digest was not saved as an operational prepared
directory.

## Receiver and evidence contract

Input stays disabled until the exact candidate entry, display mirror, readonly
root, restart readiness, concise PID1 readiness, watchdog readiness, zsh-ready
marker, and prompt are present in one healthy full capture. PID1 readiness is
limited to three exact newline-framed records. Corrupt, partial, fourth, or
post-stop records fail. A garbled watchdog line is not reconstructed.

The receiver executes the original four real zsh checks and one `/sbin/reboot`
command. Success requires the ordered EXEC, pthread, PRE_SMC and fresh-firmware
markers, no returned-SMC or panic tail, and a separately collected readonly
NVMe Linux return with a new boot ID. Nominal countdown timing is retained as
engineering evidence only; physical PSCI causality remains unproven.

## Frozen source pins

- media engine: `46ace553f7457da8b7f4c5a7d7cde7cf68d1aa9f715eb0de89fb4f2f1f538cc5`
- strict protocol: `c8e6088f42ac97142ba9e6388d1c064eae012657983449d76873d2b93e1ee7df`
- receiver: `1168f4b87c1650f2e2ee1b9a79b79f53eee1ec1e5ffaa27e2a184b3310a1d7e5`
- return evidence: `d77e152b79e05cf00e21dfdb0962e6e34153ba5930539edcbf8dbd212ce50292`
- one-shot launcher: `81aa50fa213af3e0ab412c683fcc02536cbdbb3a2e84de93b06baf1a0bb44687`
- controller: `7e38bd9122697ad58f2c11a5b315ee71bdfb6e80bfb782e725027b7f31b63200`
- tests: `0da2e9214cb4c7dfc302d1d05a1f629d2751c9f020a3004b002e7b96a455a47e`

## Qualification

```sh
python3 -m unittest tools.rpi5.tests.test_console_records_transport_v1 -v
```

Five groups passed in 229.075 seconds: exact current-466 intake and in-memory
preparation; sealed two-target remote-program construction; strict readiness
and restart grammar; the actual five-command receiver plus independent return;
eight fail-closed receiver cases; and exact pair restoration/replay derivation.
The test doubles perform no hardware or remote operation.
