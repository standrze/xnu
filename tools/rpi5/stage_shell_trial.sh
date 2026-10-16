#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause
# Authorized disposable SD only. Run on the Pi with a freshly validated SHA.
set -eu
new=${1:?Usage: sudo sh stage_shell_trial.sh CANDIDATE_SHA256}
test ${#new} = 64
case "$new" in *[!0-9a-f]*) exit 2 ;; esac
sd=/dev/mmcblk0p1
mp=/mnt/xnu-probe
candidate=/home/sandrzej/xnu-shell-candidate-20261011.bin
old=e1548c9e083fa7f4c78f19834075cab125683f76d3d9ac56ae3eb95705cdaa4d
hash() { sha256sum "$1" | cut -d ' ' -f 1; }
test "$(hostname)" = kamidana
test "$(findmnt -n -o SOURCE /)" = /dev/nvme0n1p2
test "$(blkid -s UUID -o value "$sd")" = 4FA7-3725
test "$(blkid -s PARTUUID -o value "$sd")" = 5ae1f07e-01
test "$(blkid -s LABEL -o value "$sd")" = XNU_PROBE
test "$(hash "$candidate")" = "$new"
mkdir -p "$mp"
if ! findmnt -n "$sd" >/dev/null; then mount -o ro "$sd" "$mp"; fi
test "$(findmnt -n -o SOURCE "$mp")" = "$sd"
test "$(hash "$mp/probe.bin")" = "$old"
test "$(hash "$mp/config.txt")" = aaccab184135aca272db4123fcba34e20874ae0959a90aed1ef6fd4d5e18ed28
test "$(hash "$mp/bl31.bin")" = 413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46
test "$(hash "$mp/bcm2712-rpi-5-b.dtb")" = e67017e5d45b97af478ebc93d651a086f2adcb6a650fe453eb9f1cf47e66473f
test "$(hash "$mp/probe.gate3-20260927.bin")" = 454906aa802f013549ef936a9d15bcc42b10638ed73d6759a276797737b1d06c
test "$(hash "$mp/probe.polling-backup-20261011.bin")" = a4fb01fcee8724cd68b5a162b77c80e72880a2afba0db9366fda9d7371d8ca53
test "$(hash "$mp/probe.process-passed-20261011.bin")" = 043eeb43dc55aeb520be7cd5c4541ad39b222b120a6ddf166f809ea834a20341
printf 'SHELL_STAGE_START_UTC '; date -u +%FT%TZ
blkid "$sd"
rpi-eeprom-config
cat "$mp/config.txt"
# Preserve a second independent copy on NVMe before making SD writable.
nvme_backup=/home/sandrzej/xnu-ramroot-passed-backup-20261011.bin
if test ! -e "$nvme_backup"; then cp -p "$mp/probe.bin" "$nvme_backup"; fi
test "$(hash "$nvme_backup")" = "$old"
trap 'sync; mount -o remount,ro /mnt/xnu-probe' EXIT
mount -o remount,rw "$mp"
backup=$mp/probe.ramroot-passed-20261011.bin
if test ! -e "$backup"; then cp -p "$mp/probe.bin" "$backup"; fi
test "$(hash "$backup")" = "$old"
test ! -e "$mp/probe.shell-20261011.tmp"
cp "$candidate" "$mp/probe.shell-20261011.tmp"
test "$(hash "$mp/probe.shell-20261011.tmp")" = "$new"
mv "$mp/probe.shell-20261011.tmp" "$mp/probe.bin"
sync
mount -o remount,ro "$mp"
test "$(hash "$mp/probe.bin")" = "$new"
sha256sum "$mp/probe.bin" "$backup" "$nvme_backup" "$mp/config.txt"
findmnt -n -o SOURCE,OPTIONS "$mp"
printf 'SHELL_STAGE_COMPLETE_UTC '; date -u +%FT%TZ
