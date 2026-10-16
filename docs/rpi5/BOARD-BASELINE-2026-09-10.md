# Board access and ownership update — 2026-09-10

## Verified access

- Pi: `sandrzej@192.168.4.23`, hostname `kamidana`, Pi 5 Model B Rev 1.0.
- Capture host: `sandrzej@192.168.4.76`, hostname `leszy` (Ubuntu).
- Official Debug Probe: USB 2e8a:000c, `/dev/ttyACM0`, stable path
  `/dev/serial/by-id/usb-Raspberry_Pi_Debug_Probe__CMSIS-DAP__E66480454F719939-if01`.
- Fresh capture-host SSH session includes dialout and has read/write access.
- Pi passwordless sudo verified using `sudo -k; sudo -n id -u` (result 0).

During the user-triggered reboot, the read-only 115200 8N1 receiver observed
readable BOOTSYS/BOOTLOADER banners for EEPROM release 086b83e3, RAM initialization
reporting 64 Gbit, RP1 initialization and NVMe boot-file reads. The Pi subsequently
returned over SSH with uptime under a minute. Thus host USB, receive permission,
probe U-to-UART10 wiring and early firmware serial reception are established.
No transmit test was performed. This was stock firmware/Linux, NOT our BL33.

## Durable capture tooling

`tools/rpi5/capture_serial.py` now records raw serial bytes locally through SSH,
with a separate receiver-status log and timestamp/hash manifest. It uses the
explicit stable device path, 115200 8N1, strict SSH host checking and an exclusive
serial open; it does not transmit serial bytes or initiate reboot. Prior termios
settings are restored on normal completion/error cleanup. Exclusivity prevents
new opens but cannot evict a process that already had the device open.

A five-second passive smoke check produced
`build/rpi5/serial-capture-za7cttyc/`, with CAPTURE_READY/CAPTURE_FINISHED and
32 received bytes while Linux was running. The independently checked SHA-256 is
`49e72de8f7307f2da804d9da32b7849bf5a6484fc35fe7ae6974572829233565`.
This validates recorder access and
normal termination only; it is not a replacement for a recorded boot run.

At 20:48 UTC, a 12-second capture in
`build/rpi5/serial-capture-ujew93v6/` received a unique diagnostic marker written
over SSH by the Pi to `/dev/ttyAMA10`. The marker
`RPI5_UART_RX_CHECK_8de411ba044c43788de50db39e71f5d2` arrived intact, surrounded
by CR CR LF on both sides (57 bytes total). Raw SHA-256:
`69ad9017889d3630fcc8f1f6236e6e251fe794d83dacc403aa293c57aa139acb`.
Receiver and Pi write both exited successfully. This establishes end-to-end
Linux UART output reception at 115200; it does not establish probe-to-Pi input,
standalone loader operation or a complete boot capture. The recorder manifest's
`transmitted_bytes: 0` describes the receiver, not the Pi-side diagnostic write.
No reboot or boot configuration change was made.

The Pi serial getty is active at 115200. ModemManager is active on the capture
host and udev marks the probe `ID_MM_CANDIDATE=1`, but the queried service journal
had no entries and no competing holder was reported by unprivileged `fuser`.
These checks do not prove interference or exclude holders invisible to that
account. No service was disabled. The earlier 32 non-text bytes remain unexplained;
do not attribute them to ModemManager or claim all future captures are clean.

The bounded capture ended during firmware initialization. The raw bytes appeared
as escaped chunks in the conversation tool output, not as a complete archived
boot-log artifact. Do not claim a complete boot trace or Gate 1 serial proof.

## Privileged read-only observations at 20:42 UTC

Linux version: `6.18.34+rpt-rpi-2712`.
`/proc/iomem` now exposes real addresses rather than zeros. Selected inclusive
intervals below are converted to exclusive ends:

| Region | Start | Exclusive end |
| --- | --- | --- |
| Low reserved firmware | 0 | 0x80000 |
| First System RAM bank | 0x80000 | 0x3fc00000 |
| Linux kernel code | 0x200000 | 0x1600000 |
| Following reserved span | 0x1600000 | 0x1830000 |
| Linux kernel data | 0x1830000 | 0x1b50000 |
| Reserved span containing initramfs | 0x2e06c000 | 0x2f000000 |
| Additional low reserved span | 0x3a000000 | 0x3e000000 |
| UART10 MMIO | 0x107d001000 | 0x107d001200 |
| RNG200 MMIO | 0x107d208000 | 0x107d208028 |

Other reserved intervals exist throughout RAM, including repeated 4 MiB spans
at 0x1e000000, 0x6e000000, 0xae000000, 0xee000000 and corresponding high-bank
locations. The map alone does not identify their owners or establish whether
they persist in a different firmware/BL33 boot chain. Never copy this Linux
allocation map verbatim into a standalone loader policy.

Reading only the 40-byte `/sys/firmware/fdt` header and its terminated reservation
table reports total size 80360 and no header reservation entries. The original
tree's structure/properties were not dumped by this privileged check. Selected
live `/chosen` properties report initrd start 0x2e06c000, end 0x2efffc44.
No seed properties, initramfs contents or arbitrary physical memory were read.

An empty FDT header reservation table is NOT an empty ownership map: reserved
memory nodes, firmware contracts, live FDT/image/stacks and other boot inputs
remain independent exclusions. Linux's own allocations are another category.

The only physical disk listed is the 238.5G NVMe, with mounted boot/root
partitions. No spare SD was present. No storage writes, boot configuration
changes, or additional reboots were performed during this evidence collection.
