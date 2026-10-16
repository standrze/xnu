#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause
# Authorized disposable Pi SD only. Run only after the local SD preflight passes.
set -eu
new=${1:?Usage: sudo sh stage_sd_read_trial.sh CANDIDATE_SHA256}
test ${#new} = 64
case "$new" in *[!0-9a-f]*) exit 2 ;; esac
sd=/dev/mmcblk0p1
mp=/mnt/xnu-probe
candidate=/home/sandrzej/xnu-sd-read-candidate-20261011.bin
old=bf01b0eedcce48249a7358772f74613d0b0453217f35576369945de25d50374f
# One explicitly identified failed trial may be replaced; unknown media still
# fails closed. It is kept separately, never confused with the working shell.
failed=e78dbcef7a9206b3361c181e94d3a16c80ee54bf8206df3acb8250e70a0c0286
failed2=d9bcba80ea2e02054f0277e61d3e0b03f72168adf6d5200d24f89b413d3ec098
failed3=cd920787529426f6d32130f067e6d153f59de263e4e6d1dd0d5a53f293262f96
hash() { sha256sum "$1" | cut -d ' ' -f 1; }
test "$(hostname)" = kamidana
test "$(findmnt -n -o SOURCE /)" = /dev/nvme0n1p2
test "$(findmnt -n -o UUID /)" = 04570742-280b-43cb-9564-73d454243b1c
test "$(cat /sys/block/mmcblk0/size)" = 250347520
test "$(blkid -s UUID -o value "$sd")" = 4FA7-3725
test "$(blkid -s PARTUUID -o value "$sd")" = 5ae1f07e-01
test "$(blkid -s LABEL -o value "$sd")" = XNU_PROBE
sfdisk --json /dev/mmcblk0 | python3 -c '
import json,sys
d=json.load(sys.stdin)["partitiontable"]
assert all(d[k]==v for k,v in dict(label="dos",id="0x5ae1f07e",device="/dev/mmcblk0",unit="sectors",sectorsize=512).items())
assert d["partitions"]==[dict(node="/dev/mmcblk0p1",start=2048,size=1048576,type="c",bootable=True)]
'
test "$(hash "$candidate")" = "$new"
mkdir -p "$mp"
if ! findmnt -n "$sd" >/dev/null; then mount -o ro "$sd" "$mp"; fi
test "$(findmnt -n -o SOURCE "$mp")" = "$sd"
current=$(hash "$mp/probe.bin")
test "$current" = "$old" || test "$current" = "$failed" || test "$current" = "$failed2" || test "$current" = "$failed3"
test "$(hash "$mp/config.txt")" = aaccab184135aca272db4123fcba34e20874ae0959a90aed1ef6fd4d5e18ed28
test "$(hash "$mp/bl31.bin")" = 413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46
test "$(hash "$mp/bcm2712-rpi-5-b.dtb")" = e67017e5d45b97af478ebc93d651a086f2adcb6a650fe453eb9f1cf47e66473f
test "$(hash "$mp/probe.gate3-20260927.bin")" = 454906aa802f013549ef936a9d15bcc42b10638ed73d6759a276797737b1d06c
printf 'SD_READ_STAGE_START_UTC '; date -u +%FT%TZ
blkid "$sd"
rpi-eeprom-config
cat "$mp/config.txt"
nvme_backup=/home/sandrzej/xnu-shell-passed-backup-20261011.bin
if test ! -e "$nvme_backup"; then
    test "$current" = "$old"
    cp -p "$mp/probe.bin" "$nvme_backup"
fi
test "$(hash "$nvme_backup")" = "$old"
trap 'sync; mount -o remount,ro /mnt/xnu-probe' EXIT
mount -o remount,rw "$mp"
backup=$mp/probe.shell-passed-20261011.bin
if test ! -e "$backup"; then
    test "$current" = "$old"
    cp -p "$mp/probe.bin" "$backup"
fi
test "$(hash "$backup")" = "$old"
if test "$current" = "$failed"; then
    failed_backup=$mp/probe.sd-read-attempt1-failed-20261011.bin
    if test ! -e "$failed_backup"; then cp -p "$mp/probe.bin" "$failed_backup"; fi
    test "$(hash "$failed_backup")" = "$failed"
fi
if test "$current" = "$failed2"; then
    failed_backup=$mp/probe.sd-read-attempt2-failed-20261011.bin
    if test ! -e "$failed_backup"; then cp -p "$mp/probe.bin" "$failed_backup"; fi
    test "$(hash "$failed_backup")" = "$failed2"
fi
if test "$current" = "$failed3"; then
    failed_backup=$mp/probe.sd-read-attempt3-registerdiag-20261011.bin
    if test ! -e "$failed_backup"; then cp -p "$mp/probe.bin" "$failed_backup"; fi
    test "$(hash "$failed_backup")" = "$failed3"
fi
test ! -e "$mp/probe.sd-read-20261011.tmp"
cp "$candidate" "$mp/probe.sd-read-20261011.tmp"
test "$(hash "$mp/probe.sd-read-20261011.tmp")" = "$new"
mv "$mp/probe.sd-read-20261011.tmp" "$mp/probe.bin"
sync
mount -o remount,ro "$mp"
test "$(hash "$mp/probe.bin")" = "$new"
sha256sum "$mp/probe.bin" "$backup" "$nvme_backup" "$mp/config.txt"
findmnt -n -o SOURCE,OPTIONS "$mp"
printf 'SD_READ_STAGE_COMPLETE_UTC '; date -u +%FT%TZ
