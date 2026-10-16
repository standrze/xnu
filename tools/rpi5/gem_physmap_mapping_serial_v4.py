# SPDX-License-Identifier: BSD-2-Clause
"""Strict zero-TX parser for the page-granular physmap verification image."""
import copy
import hashlib
import json
import re

from tools.rpi5 import gem_cpu_ring_retry_serial as retry
from tools.rpi5 import gem_cpu_ring_retry_case_v1 as parent_case
from tools.rpi5 import gem_physmap_mapping_check_v1 as checker

PREFIX = retry.PREFIX
TRANSFER = retry.TRANSFER
ENTRY = retry.ENTRY
COMMIT = retry.COMMIT
BEGIN = retry.BEGIN
old = retry.old
health = retry.health
return_positions = retry.return_positions
inventory = retry.old.inventory
PREPARED = retry.old.PREPARED
PREPARED_PREFIX = retry.old.PREPARED_PREFIX

TAIL = ("DMA_PREP", "DMA_MAP", "DMA_ALIAS", "DMA_ALIAS", "DMA_ALIAS", "DMA_ALIAS",
        "DMA_PGTABLE", "DMA_OWNER", "DMA_RECORD", "DMA_ROUTE", "DMA_STAGE", "DMA_RINGS")
ORDER = retry.old.ORDER[:-6] + TAIL + ("END",)


def _fields(row, name, names):
    match = re.fullmatch(
        PREFIX + name.encode() + b" " +
        b" ".join(n.encode() + rb"=(-?\d+)" for n in names.split()),
        row,
    )
    if not match:
        raise ValueError("Exact physmap mapping fields required: " + name)
    return dict(zip(names.lower().split(), map(int, match.groups())))


def inspect(data, report):
    if not isinstance(data, bytes) or not 0 < len(data) <= 4 * 1024 * 1024:
        raise ValueError("Bounded original physmap capture required")
    scan = health.inspect(data, hashlib.sha256(data).hexdigest())
    if scan["runtime_fault_signature_observed"] or b"RPI5XNU:FAULT" in data:
        raise ValueError("Fault in complete physmap capture including return tail")
    if return_positions(data) is None:
        raise ValueError("Automatic watchdog NVMe return not recorded")
    tag = report.get("tag", "")
    marker = report.get("marker", "")
    expected = checker.b.retry.trial.marker(tag)
    if not re.fullmatch("[0-9a-f]{32}", tag) or marker != expected or data.count(marker.encode()) != 1:
        raise ValueError("Exact physmap verification image marker required")

    lines = [row.rstrip(b"\r") for row in data.split(b"\n") if row.startswith(PREFIX)]
    names = tuple(row.split(b" ", 1)[0][len(PREFIX):].decode() for row in lines)
    if len(lines) != 59 or names != ORDER:
        raise ValueError("Exactly 59 ordered records with four DMA_ALIAS and one DMA_PGTABLE required")
    if names.count("DMA_ALIAS") != 4 or names.count("DMA_PGTABLE") != 1:
        raise ValueError("Exact physmap evidence row cardinality required")

    first = len(retry.old.ORDER) - 6
    prep = _fields(lines[first], "DMA_PREP", "STEP ERROR BYTES PACKETS")
    mapping = _fields(lines[first + 1], "DMA_MAP", "REASON PAGE ATTR VA PA PAR_R PAR_W")
    aliases = [_fields(lines[first + 2 + i], "DMA_ALIAS",
        "PAGE VA CACHE PA PAR_R PAR_W ATTR_R ATTR_W VALID") for i in range(4)]
    pgtable = _fields(lines[first + 6], "DMA_PGTABLE",
        "START END BYTES PAGES MAX PAGE_BYTES MAPPED RESERVATION_CLEAR")
    owner = _fields(lines[first + 7], "DMA_OWNER",
        "PREPARE STATE ATTEMPTED ACTIVE REVOKED DISABLED RECORD")
    record = _fields(lines[first + 8], "DMA_RECORD", "FIXED DYNAMIC MANAGED_START MANAGED_END")
    route = _fields(lines[first + 9], "DMA_ROUTE", "PHYSICAL PCI RP1 BYTES")
    stage = _fields(lines[first + 10], "DMA_STAGE", "STATE ERROR ATTEMPTED WRITTEN READ CALLS CHECKS")
    rings = _fields(lines[first + 11], "DMA_RINGS", "RX TX GENERATION BYTES DESC SLOTS TAIL OWNED")

    if prep != dict(step=16, error=0, bytes=32768, packets=0):
        raise ValueError("Discard-only preparation state differs")
    if mapping != dict(reason=41, page=0, attr=0, va=0, pa=0, par_r=0, par_w=0):
        raise ValueError("Physmap mapping success sentinel differs")
    if [(r["page"], r["va"]) for r in aliases] != [(0, 1), (0, 2), (1, 1), (1, 2)]:
        raise ValueError("Both pages and both VA classes are required in order")
    base = aliases[0]["pa"]
    mask = 0x0000FFFFFFFFF000
    if not base or base & 0x3FFF:
        raise ValueError("First retained physical page is not 16KiB aligned")
    for row in aliases:
        wanted_pa = base + row["page"] * 0x4000
        if (row["cache"], row["pa"], row["attr_r"], row["attr_w"], row["valid"]) != (6, wanted_pa, 0x44, 0x44, 1):
            raise ValueError("Exact Normal-NC alias evidence differs")
        for key in ("par_r", "par_w"):
            par = row[key]
            if par & 1 or (par >> 56) != 0x44 or (par & mask) != (wanted_pa & mask):
                raise ValueError("Exact successful S1E1R/S1E1W translation differs")
    if not (pgtable["start"] and pgtable["end"] > pgtable["start"] and
            pgtable["page_bytes"] == 0x4000 and
            1 <= pgtable["pages"] <= pgtable["max"] <= 257 and
            pgtable["bytes"] == pgtable["pages"] * 0x4000 and
            pgtable["end"] - pgtable["start"] == pgtable["bytes"] and
            pgtable["bytes"] <= 4210688 and pgtable["mapped"] > 0 and
            pgtable["reservation_clear"] == 1):
        raise ValueError("Bounded page-table accounting or reservation exclusion differs")
    if owner != dict(prepare=2, state=8, attempted=0, active=0, revoked=0, disabled=0, record=1):
        raise ValueError("Discard-before-route owner state differs")
    if not 1 <= record["fixed"] <= 32 or not 1 <= record["dynamic"] <= 8 or \
            (record["managed_start"], record["managed_end"]) != (0x6000000, 0x10000000):
        raise ValueError("Same-boot reservation record differs")
    if any(route.values()) or any(stage.values()) or any(rings.values()):
        raise ValueError("Physmap verifier activated route, rings, queues or packets")

    normalized = data
    for row in lines[first:first + 7]:
        wire = row + (b"\r\n" if row + b"\r\n" in normalized else b"\n")
        normalized = normalized.replace(wire, b"", 1)
    owner_wire = lines[first + 7]
    owner_term = b"\r\n" if owner_wire + b"\r\n" in normalized else b"\n"
    legacy_owner = (b"RPI5XNU:PCIEID:DMA_OWNER PREPARE=3 STATE=5 ATTEMPTED=0 "
        b"ACTIVE=0 REVOKED=0 DISABLED=0 RECORD=1")
    normalized = normalized.replace(owner_wire + owner_term, legacy_owner + owner_term, 1)
    normalized = normalized.replace(BEGIN, retry.old.BEGIN, 1)
    adapted = json.loads(parent_case.REPORT.read_text())
    old_marker = adapted["marker"]
    adapted.update(report)
    adapted["boot_markers"] = [
        value.replace(old_marker, report["marker"]) for value in
        json.loads(parent_case.REPORT.read_text())["boot_markers"]
    ]
    result = retry.old.inspect(normalized, adapted)
    if result["cpu_ring_trial_pass"] or result.get("dma") or result.get("irq_delivery") or result.get("queue_publication"):
        raise ValueError("Physmap verifier must remain discarded before activation")
    result.update(
        physmap_mapping_verification_pass=True,
        mapping_predicate=mapping,
        aliases=aliases,
        page_table_accounting=pgtable,
        preparation=prep,
        cpu_ring_owner=owner,
        reservation_record_summary=record,
        dma_candidate_route=route,
        cpu_ring_stage=stage,
        cpu_ring_geometry=rings,
        observed_field_rows=59,
        packet_spans=0,
        packet_mapping=False,
        bme=False,
        dma=False,
        irq_delivery=False,
        queue_publication=False,
        ethernet_proven=False,
        discard_before_route_observed=True,
        full_original_capture_health_scan=True,
        capture_health=scan,
        normal_nvme_serial_boot_observed=True,
        automatic_watchdog_return_observed=True,
        scope="Four page/VA alias rows plus bounded page-table accounting; discarded before route",
    )
    return result

