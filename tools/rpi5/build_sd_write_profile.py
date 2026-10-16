#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build a sealed, software-only SD/HFS write-admission profile.

This consumes already captured references. It never opens media, connects to a
host, changes a filesystem, stages an image or authorizes a physical write.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def integer(value, name, minimum=0, maximum=(1 << 64) - 1):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"invalid {name}")
    return value


def hex_bytes(value, name, length):
    if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{length * 2}}}", value):
        raise ValueError(f"invalid {name}")
    return bytes.fromhex(value)


def c_bytes(values):
    return ",".join(f"0x{value:02x}" for value in values)


def build(sd_path, fixture_path):
    sd = json.loads(sd_path.read_text())
    fixture = json.loads(fixture_path.read_text())
    identity = sd.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("missing SD identity")
    layout = identity.get("layout")
    card = identity.get("card")
    if not isinstance(layout, dict) or not isinstance(card, dict):
        raise ValueError("missing SD layout/card")
    if layout.get("label") != "dos" or layout.get("unit") != "sectors" or \
            layout.get("sectorsize") != 512:
        raise ValueError("unsupported partition table")
    partitions = layout.get("partitions")
    if not isinstance(partitions, list) or len(partitions) != 2:
        raise ValueError("expected exact boot and HFS partitions")
    boot, hfs = partitions
    if boot.get("type") != "c" or boot.get("bootable") is not True or hfs.get("type") != "af":
        raise ValueError("unexpected partition types")
    boot_start = integer(boot.get("start"), "boot start", 1, (1 << 32) - 1)
    boot_blocks = integer(boot.get("size"), "boot blocks", 1, (1 << 32) - 1)
    start = integer(hfs.get("start"), "HFS start", 1, (1 << 32) - 1)
    blocks = integer(hfs.get("size"), "HFS blocks", 1, (1 << 32) - 1)
    if boot_start + boot_blocks > start:
        raise ValueError("partition overlap")
    total_bytes = integer(identity.get("bytes"), "card bytes", 512)
    if total_bytes % 512:
        raise ValueError("unaligned card capacity")
    sectors = total_bytes // 512
    if start + blocks > sectors:
        raise ValueError("HFS extent exceeds media")
    if identity.get("partition_start") != start or identity.get("partition_sectors") != blocks:
        raise ValueError("partition identity mismatch")
    disk_id = layout.get("id")
    if not isinstance(disk_id, str) or not re.fullmatch(r"0x[0-9a-f]{8}", disk_id):
        raise ValueError("invalid MBR signature")
    cid = hex_bytes(card.get("cid"), "CID", 16)
    csd = hex_bytes(card.get("csd"), "CSD", 16)
    reads = sd.get("partition_reads")
    if not isinstance(reads, list) or len(reads) < 2:
        raise ValueError("two complete partition reads required")
    expected_hash = fixture.get("image_sha256")
    expected_bytes = integer(fixture.get("image_bytes"), "fixture bytes", 512)
    if expected_bytes != blocks * 512 or fixture.get("image_sectors") != blocks:
        raise ValueError("fixture geometry mismatch")
    for index, read in enumerate(reads, 1):
        if read.get("pass_number") != index or read.get("bytes") != expected_bytes or \
                read.get("sha256") != expected_hash:
            raise ValueError("partition read mismatch")
    if sd.get("fixture_reference_sha256") != sha256(fixture_path) or sd.get("sd_write_operations") != 0:
        raise ValueError("unbound or write-tainted SD reference")
    volume = fixture.get("volume_header")
    if not isinstance(volume, dict) or volume.get("signature") != "H+" or volume.get("version") != 4:
        raise ValueError("unsupported volume header")
    block_size = integer(volume.get("block_size"), "HFS block size", 512, (1 << 32) - 1)
    total_blocks = integer(volume.get("total_blocks"), "HFS total blocks", 1, (1 << 32) - 1)
    if block_size & (block_size - 1) or block_size * total_blocks != expected_bytes:
        raise ValueError("invalid HFS allocation geometry")
    if fixture.get("readonly_fsck_verified") is not True or fixture.get("mac_attachment_detached") is not True:
        raise ValueError("fixture did not pass read-only qualification")
    return {
        "sectors": sectors,
        "start": start,
        "blocks": blocks,
        "max_request_blocks": 32,
        "mbr_signature": int(disk_id, 16),
        "boot_start": boot_start,
        "boot_blocks": boot_blocks,
        "hfs_block_size": block_size,
        "hfs_total_blocks": total_blocks,
        "cid": cid,
        "csd": csd,
        "fixture_sha256": expected_hash,
        "sd_reference_sha256": sha256(sd_path),
        "fixture_reference_sha256": sha256(fixture_path),
    }


def source(profile):
    return f'''/* Generated by build_sd_write_profile.py; software-only sealed expectation. */
#include "rpi5_sd_write_policy.h"
const struct rpi5_sd_write_profile rpi5_sd_write_external_profile={{
    .sectors=UINT64_C({profile["sectors"]}), .start=UINT64_C({profile["start"]}),
    .blocks=UINT64_C({profile["blocks"]}), .max_request_blocks={profile["max_request_blocks"]},
    .mbr_signature=UINT32_C(0x{profile["mbr_signature"]:08x}),
    .boot_start={profile["boot_start"]}, .boot_blocks={profile["boot_blocks"]},
    .hfs_block_size={profile["hfs_block_size"]}, .hfs_total_blocks={profile["hfs_total_blocks"]},
    .cid={{{c_bytes(profile["cid"][:15])}}},
    .csd={{{c_bytes(profile["csd"])}}}
}};
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sd-reference", type=Path, required=True)
    parser.add_argument("--fixture-reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    profile = build(args.sd_reference.resolve(), args.fixture_reference.resolve())
    args.output.mkdir(parents=True)
    generated = source(profile)
    generated_path = args.output / "rpi5_sd_write_external_profile.c"
    generated_path.write_text(generated)
    report = {
        "format": "rpi5-sd-write-profile-v1",
        "software_only": True,
        "hardware_executed": False,
        "cache_state_proven": False,
        "write_authorized": False,
        "durability_verified": False,
        "sd_reference": str(args.sd_reference.resolve()),
        "fixture_reference": str(args.fixture_reference.resolve()),
        "sd_reference_sha256": profile["sd_reference_sha256"],
        "fixture_reference_sha256": profile["fixture_reference_sha256"],
        "fixture_sha256": profile["fixture_sha256"],
        "generated_source": generated_path.name,
        "generated_source_sha256": hashlib.sha256(generated.encode()).hexdigest(),
        "profile": {key: value.hex() if isinstance(value, bytes) else value
                    for key, value in profile.items() if not key.endswith("_sha256")},
    }
    (args.output / "profile.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
