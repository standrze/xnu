# Pi 5 read-only Linux baseline

Collected over verified key-based SSH at 2026-09-06 01:42–01:44 UTC.
Target: `sandrzej@192.168.4.23`, hostname `kamidana`.
No reboot, package install, boot-file change or media write was performed.

## Observed identity

- Model: Raspberry Pi 5 Model B Rev 1.0; user-confirmed 8 GB SKU.
- Linux: `6.18.34+rpt-rpi-2712 aarch64`.
- OS reports Debian GNU/Linux 13 (trixie), version 13.5.
- `/proc/meminfo` MemTotal: 8255888 kB.
- `vcgencmd get_throttled`: `throttled=0x0` at capture time.
- Bootloader: `086b83e3332dfc8927c56762771d082f3077a1ae`, release,
  2026/05/26 16:01:25. This identifies the installed EEPROM, not our future
  pinned TF-A build or every firmware artifact.
- `/dev/serial0` resolves to `/dev/ttyAMA10`.
- Existing Linux command line selects `console=serial0,115200` and `console=tty1`.

## Live Linux device-tree observations

Read selected properties from `/proc/device-tree` with `od -An -tx1`.
Both reserved-memory address and size cell counts are 2. Values below are
decoded big-endian; intervals use exclusive ends.

| Property | Observed bytes | Interpretation |
| --- | --- | --- |
| linux,cma/size | `00 00 00 00 04 00 00 00` | 64 MiB dynamic request |
| linux,cma/alloc-ranges | `00 00 00 00 00 00 00 00 00 00 00 00 40 00 00 00` | Allocate within [0, 0x40000000) |
| atf@0/reg | `00 00 00 00 00 00 00 00 00 00 00 00 00 08 00 00` | [0, 0x80000) |

`memory@0/reg` advertises three address/size pairs:

- Address 0, size 0x3fc00000.
- Address 0x40000000, size 0xc0000000.
- Address 0x100000000, size 0x100000000.

These are advertised ranges, NOT a reservation-free allocation map. The tree
also contains nvram@0 and nvram@1 reservations. Follow-up inspection found:

- nvram@0: status `okay`, firmware bootloader-config/nvmem-rmem binding,
  range [0x3fd235c0, 0x3fd235f8). This is inside the hole between advertised
  memory banks, not allocatable RAM.
- nvram@1: status `disabled`, bootloader-public-key/nvmem-rmem binding,
  zero address/size. The disabled node must not become an active zero-size
  reservation. No NVRAM contents or key contents were read.

`/proc/iomem` addresses are redacted to zero for this SSH user. A read-only
`sudo -n cat /proc/iomem` attempt returned `sudo: a password is required`;
there is no unredacted Linux allocation map in this capture.

`lsblk` shows active root and `/boot/firmware` on a 238.5G NVMe device
(`nvme0n1p2` and `nvme0n1p1` respectively), not an SD card. This active disk
is not disposable boot-test media. No SD device was listed.

Other ownership inputs still need review. `/sys/firmware/fdt` exists (80360
bytes, root-readable); its contents were not captured. No seeds were read.

## Consequence for Gate 1

### Native validation of filtered Linux tree

`tools/rpi5/capture_linux_tree.py sandrzej@192.168.4.23` generated
`build/rpi5/linux-filtered-tree-p4i5dkut/filtered.dtb` and a hash manifest.
The remote collector reads only allowlisted binding properties; it excludes
chosen, seeds, identities and unrelated subtrees before transmission. This is
a reconstructed diagnostic tree with an EMPTY header reservation map, NOT an
original DTB or complete ownership capture. Never use it as firmware input.

The sanitizer-enabled `tools/rpi5/tests/linux_tree_probe.c` diagnostic passed
structure, phandles, memory, reservations, CPUs, PSCI, MMIO, UART clocks and RNG
binding checks. The timer check returned -1. Direct property inspection confirms
five timer interrupt tuples: PPI 13, 14, 11, 10, 12, all type 1 and flags 0xf08.
There is no interrupt-names or local interrupt-parent property; the root parent
is phandle 1. The existing validator requires exactly four tuples and therefore
rejects this live Linux binding. Review the fifth tuple against the authoritative
timer binding before extending support; do not remove length validation blindly.

Resolved in the validator after checking Linux's authoritative
[ARM architected timer binding](https://raw.githubusercontent.com/torvalds/linux/master/Documentation/devicetree/bindings/timer/arm,arch_timer.yaml):
the fifth entry describes the EL2 virtual timer. The Pi validator now accepts
exactly four or five tuples, checking every type, PPI and flags value against
the observed profile. It does not enable VHE or use the fifth timer. Regression
cases reject three/six tuples and mutations of each field in all five tuples.
Re-running the native diagnostic on the same filtered capture passes all ten
checks. This establishes binding compatibility only, not interrupt delivery.

Follow-up CPU/UART property inspection:

- Four Cortex-A76 CPU nodes declare PSCI enable-method and affinities 0,
  0x100, 0x200, 0x300. PSCI declares 1.0 and 0.2 compatibility, method `smc`.
  This is binding evidence, not a test of CPU_ON or current exception levels.
- The dedicated UART node is `/soc@107c000000/serial@7d001000`, status `okay`.
  Its `uartclk` and `apb_pclk` links are phandles 0x0e and 0x0f, matching
  clk-uart and clk-vpu. Declared frequencies are 44236800 and 750000000 Hz.
  These are declarations, not hardware measurements. The pinned fixture's
  9216000 Hz UART value must not be substituted for this runtime value.
- `/chosen/stdout-path` is `serial10:115200n8`; DT alias serial10 targets the
  dedicated UART. DT alias serial0 instead targets RP1's serial@30000.
  Linux's `/dev/serial0` symlink still resolves to ttyAMA10: filesystem names
  and device-tree aliases are not interchangeable. The loader's explicit
  UART10 path matches the observed dedicated debug UART.

The live Linux CMA properties have the expected two-cell size and four-cell
allocation-range widths. This is evidence against treating the older malformed
pinned CMA encoding as universal board behavior. It does not justify relaxing
strict parsing or silently dropping reservations.

This is Linux's live tree after firmware/overlay/kernel processing, not proof of
the exact FDT that our selected TF-A/BL33 boot chain will supply. Keep that
distinction until a standalone probe captures its actual input. Full ownership
review, runtime integration, fresh entropy and raw per-CPU UART evidence remain
required. The ordered Debug Probe has not yet arrived.
