#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Type the immutable v10 board capture as mapping-verification-only evidence.

This checker deliberately does not call the inherited RP1-ID trial parser.  The
image's terminal authority is mapping verification followed by discard, so an
unattempted RP1 identity/link path is required to remain zero rather than to
satisfy a different trial's live-link success predicate.
"""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT))
from tools.rpi5 import gem_physmap_mapping_serial_v5 as protocol
from tools.rpi5 import trial_checkpoint_v2 as seals

CAPTURE = ROOT / "build/rpi5/gem-physmap-mapping-v5-capture"
BASELINE = ROOT / "build/rpi5/gem-physmap-mapping-v4-restored"
INSTALLED = ROOT / "build/rpi5/gem-physmap-mapping-v5-installed"
RESTORE_PREPARED = ROOT / "build/rpi5/gem-physmap-mapping-v5-restore-prepared"
RESTORED = ROOT / "build/rpi5/gem-physmap-mapping-v5-restored"

SERIAL_SHA = "32af09d3ed9e5e6c456605507ae04994aee2ac8b5f725e1f2a9383a25731a12c"
MARKER = ("RPI5XNU:CPU_RINGS:ENTRY TAG=96a5f52e3bd546fc8687f63e9b6459e9 "
    "CPUS=1 NO_CPU_ON NO_QUEUE NO_DMA")
BOOT_BEFORE = "5a1f5c04-c3d6-463a-8785-d737a3d59935"
BOOT_AFTER = "2d237d96-a323-4df7-a8b4-ad9b4eb5f477"
LEGACY_ERROR = "Success row contradicts exact RP1-ID/link/elapsed conditions"

FILE_SHA256 = {
    CAPTURE / "armed.json": "605e4b988e2a97e83508b731df940655da025af2a9e45e00b402c8245ace7840",
    CAPTURE / "receive-events.jsonl": "86595cf7c56b98733306b710cb80b37ee79a8cdcf8d8d7aaf6c045601702d1bb",
    CAPTURE / "return.json": "9970c36664f85d5e54361dc08e4a2f877e579c2e7c24708048f748cc959c0f2b",
    CAPTURE / "serial.bin": SERIAL_SHA,
    CAPTURE / "state.json": "38fc7afccaa5f6e53ca6bc67c2d2afcf41468f6cc8655404cdd4d9627e6c8d24",
    BASELINE / "result.json": "20345faa425243b43f1578aa30f1c0c3983192cd21fde92a9906ee2555f38298",
    INSTALLED / "checkpoint.json": "6e58fcf9da7e43c791eab80615925830381a4acc59bf35606e79298b8ad08743",
    INSTALLED / "plan.json": "b785b932b138c0876c15bda896f29c30f295711d02d6cb731caadf7bea092fca",
    INSTALLED / "result.json": "a9840813d85cb72577b35428273d19f7fa7a17bff3cfa1324d7c15b3b0f44af6",
    RESTORE_PREPARED / "checkpoint.json": "9d872cdec4817bd3a35d61caf7f51a65abe170ce604e76cd1f2e37211f3a790e",
    RESTORE_PREPARED / "offline-plan.json": "1a27deb5ae77b12b45475b8b51d896f9bd14de8a19ab237f36314c8c2507c8b5",
    RESTORED / "checkpoint.json": "9d872cdec4817bd3a35d61caf7f51a65abe170ce604e76cd1f2e37211f3a790e",
    RESTORED / "plan.json": "92c7929e918977a951ca5ba55bf0222ecd3954fabae0573105913f56903e057c",
    RESTORED / "result.json": "f379d91a3ebf20f3105b38a349980581e3c12bafab630c7503d690de7ad1d930",
}

SEMANTIC = {
    "installed_checkpoint": "96126763389895b078bdc551005a4759143a8aa15a746ffd59a849fa2f08862a",
    "installed_plan": "91025632a8ccbdeca8820be869d1acbc1c15c1944720bda5f9327589c1cc847b",
    "restored_checkpoint": "91a00c05d5bee963e87e316a4748eeee4e38be706a8f6c6432238f3047180c00",
    "restored_plan": "0192c6a07d6947c41443aa24b18f1432a867c9f8c9676773a29e7b6a097e5058",
}

NORMAL_TRIPLE = {
    "config.txt": "aaccab184135aca272db4123fcba34e20874ae0959a90aed1ef6fd4d5e18ed28",
    "bl31.bin": "413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46",
    "probe.bin": "f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536",
}
TRIAL_TRIPLE = {
    "config.txt": "359263f7f9776c6300ebeba344aeb0e2dd2d07df7064fb344b55236219f4cde7",
    "bl31.bin": "dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b",
    "probe.bin": "5fad73f69c09f05431ece249204c7ae52b07e2f6df45b12370019f26ed1a39df",
}


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return sha_bytes(Path(path).read_bytes())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _fields(row, name, names):
    match = re.fullmatch(
        protocol.PREFIX + name.encode() + b" " +
        b" ".join(field.encode() + rb"=(-?\d+)" for field in names.split()), row)
    if not match:
        raise ValueError("Exact board mapping fields required: " + name)
    return dict(zip(names.lower().split(), map(int, match.groups())))


def _terminal(row):
    match = re.fullmatch(
        protocol.PREFIX + rb"END OK=(\d+) PHASE=(\d+) LAST=(\d+) LIFE=(\d+) "
        rb"FLAGS=([0-9A-Fa-f]+) ID=([0-9A-Fa-f]+) COMMAND=([0-9A-Fa-f]+) "
        rb"BAR1=([0-9A-Fa-f]+) GEN=(\d+) LANES=(\d+)", row)
    if not match:
        raise ValueError("Exact verification-only END row required")
    keys = "ok phase last life flags id command bar1 gen lanes".split()
    bases = (10, 10, 10, 10, 16, 16, 16, 16, 10, 10)
    return dict(zip(keys, (int(value, base) for value, base in zip(match.groups(), bases))))


def inspect_serial(data, require_immutable=True):
    if not isinstance(data, bytes) or (require_immutable and sha_bytes(data) != SERIAL_SHA):
        raise ValueError("Exact immutable v5 raw serial capture required")
    if data.count(MARKER.encode()) != 1:
        raise ValueError("Exact v10 trial marker required once")
    lines = [row.rstrip(b"\r") for row in data.split(b"\n") if row.startswith(protocol.PREFIX)]
    names = tuple(row.split(b" ", 1)[0][len(protocol.PREFIX):].decode() for row in lines)
    if len(lines) != 59 or names != protocol.ORDER:
        raise ValueError("Exact 59-row board record order required")

    first = len(protocol.old.ORDER) - 6
    prep = _fields(lines[first], "DMA_PREP", "STEP ERROR BYTES PACKETS")
    mapping = _fields(lines[first + 1], "DMA_MAP", "REASON PAGE ATTR VA PA PAR_R PAR_W")
    aliases = [_fields(lines[first + 2 + index], "DMA_ALIAS",
        "PAGE VA CACHE PA PAR_R PAR_W ATTR_R ATTR_W VALID") for index in range(4)]
    pgtable = _fields(lines[first + 6], "DMA_PGTABLE",
        "START END BYTES PAGES MAX EDGE UPPER PAGE_BYTES MAPPED RESERVATION_CLEAR")
    owner = _fields(lines[first + 7], "DMA_OWNER",
        "PREPARE STATE ATTEMPTED ACTIVE REVOKED DISABLED RECORD")
    route = _fields(lines[first + 9], "DMA_ROUTE", "PHYSICAL PCI RP1 BYTES")
    stage = _fields(lines[first + 10], "DMA_STAGE", "STATE ERROR ATTEMPTED WRITTEN READ CALLS CHECKS")
    rings = _fields(lines[first + 11], "DMA_RINGS", "RX TX GENERATION BYTES DESC SLOTS TAIL OWNED")
    terminal = _terminal(lines[first + 12])

    if prep != dict(step=16, error=0, bytes=32768, packets=0):
        raise ValueError("Board mapping preparation row differs")
    if mapping != dict(reason=41, page=0, attr=0, va=0, pa=0, par_r=0, par_w=0):
        raise ValueError("Board mapping success sentinel differs")
    expected_pairs = [(0, 1), (0, 2), (1, 1), (1, 2)]
    if [(row["page"], row["va"]) for row in aliases] != expected_pairs:
        raise ValueError("Both pages and retained/static VA classes are required in order")
    expected_pas = (185516032, 185516032, 185532416, 185532416)
    mask = 0x0000FFFFFFFFF000
    for row, physical in zip(aliases, expected_pas):
        if (row["cache"], row["pa"], row["attr_r"], row["attr_w"], row["valid"]) != \
                (6, physical, 0x44, 0x44, 1):
            raise ValueError("Exact Normal-NC board alias evidence differs")
        for key in ("par_r", "par_w"):
            par = row[key]
            if par & 1 or par >> 56 != 0x44 or par & mask != physical & mask:
                raise ValueError("Exact successful S1E1R/S1E1W board translation differs")
    if pgtable != dict(start=184745984, end=184827904, bytes=81920, pages=5, max=6,
            edge=2, upper=1, page_bytes=16384, mapped=100597760, reservation_clear=1):
        raise ValueError("Exact bounded board page-table accounting differs")
    if not (pgtable["pages"] <= pgtable["max"] <= 259 and
            pgtable["bytes"] == pgtable["pages"] * pgtable["page_bytes"] <= 4243456 and
            pgtable["end"] - pgtable["start"] == pgtable["bytes"]):
        raise ValueError("Board page-table accounting exceeds qualified bound")
    if owner != dict(prepare=2, state=8, attempted=0, active=0, revoked=0, disabled=0, record=1):
        raise ValueError("Discard-before-route owner state differs")
    if any(route.values()) or any(stage.values()) or any(rings.values()):
        raise ValueError("Mapping verifier activated route, callbacks, queues, DMA or TX")
    link = next(lines[index] for index, value in enumerate(names) if value == "LINK")
    expected_link = (protocol.PREFIX + b"LINK LINK_CALL=0 LINK_STEP=0 LINK_RC=0 LINK_CB=0 "
        b"RESET_START_US=0 RESET_END_US=0 RESET_US=0 POLL_READS=0 POLL_US=0")
    if link != expected_link:
        raise ValueError("Verification-only image attempted or reported live link work")
    if terminal != dict(ok=1, phase=1, last=1, life=0, flags=0, id=0,
            command=0, bar1=0, gen=0, lanes=0):
        raise ValueError("Verification-only terminal semantics differ")
    health = protocol.health.inspect(data, sha_bytes(data))
    positions = protocol.return_positions(data)
    if (not health["signature_scan_completed"] or health["faults"] or
            health["runtime_fault_signature_observed"] or health["complete_terminal_lines"] != 1 or
            not positions or len(positions) != 4):
        raise ValueError("Complete fault-free capture and watchdog-return tail required")
    return dict(rows=59, preparation=prep, mapping=mapping, aliases=aliases,
        page_table_accounting=pgtable, owner=owner, route=route, stage=stage,
        rings=rings, terminal=terminal, health=health, return_positions=positions)


def _events(text, serial_bytes):
    try:
        rows = [json.loads(line) for line in text.splitlines()]
    except json.JSONDecodeError as error:
        raise ValueError("Valid receive-event JSONL required") from error
    if len(rows) != 2552:
        raise ValueError("Exact receive-event count required")
    offset = 0
    previous = 0.0
    for row in rows:
        if (set(row) != {"offset", "bytes", "monotonic", "utc"} or
                row["offset"] != offset or not 0 < row["bytes"] <= 64 or
                not isinstance(row["monotonic"], (int, float)) or row["monotonic"] <= previous or
                not isinstance(row["utc"], str) or not row["utc"].endswith("+00:00")):
            raise ValueError("Contiguous bounded receive-event stream required")
        offset += row["bytes"]
        previous = row["monotonic"]
    if offset != serial_bytes:
        raise ValueError("Receive-event coverage differs from raw serial bytes")
    return dict(events=len(rows), first_offset=rows[0]["offset"], final_offset=offset,
        first_monotonic=rows[0]["monotonic"], last_monotonic=rows[-1]["monotonic"])


def _source_receipts(armed, state, returned):
    sources = state.get("source_sha256")
    receipts = state.get("receipt_evidence_sha256")
    if (not isinstance(sources, dict) or len(sources) != 1742 or
            not isinstance(receipts, dict) or len(receipts) != 14270 or
            armed.get("source_sha256") != sources or armed.get("receipt_evidence_sha256") != receipts or
            returned.get("source_sha256") != sources or
            returned.get("observation", {}).get("return_source_sha256") != sources):
        raise ValueError("Exact common capture/source receipt inventories required")
    for name, digest in sources.items():
        path = Path(name)
        if not path.is_file() or sha(path) != digest:
            raise ValueError("Captured v5 source byte changed: " + name)
    required = {
        str(ROOT / "tools/rpi5/stage_gem_physmap_mapping_trial_v5.py"):
            "7918ddb30cd0eca748016f0d7f16e576e1416c851b0ed7c898cd484698b39919",
        str(ROOT / "tools/rpi5/gem_physmap_mapping_media_v5.py"):
            "bb36e06392baa1ff0a5a138c70664e60a89bcb765900cd35afc5d86dd26a7405",
        str(ROOT / "tools/rpi5/gem_physmap_mapping_serial_v5.py"):
            "89b485ac70190bcd9a31449c2b0dbd0b5f4919ff10b0b705df424ebd4163c443",
        str(ROOT / "tools/rpi5/serial_gem_physmap_mapping_trial_v5.py"):
            "fada8210107baf7e13d24570d96a2b7360c0d374c38990baa4c2a213852caf23",
        str(ROOT / "tools/rpi5/gem_physmap_mapping_evidence_v5.py"):
            "cfd8745c258c3fed059a1123ac69c5e8b1f4248e203bd4bb1e4831ebaf214ee6",
        str(ROOT / "tools/rpi5/arm_gem_physmap_mapping_reboot_v5.py"):
            "6d4e595d472cf9c618d9b8a017ccde9158620781f8bd5be7193c47cd510b8802",
    }
    if any(sources.get(name) != digest for name, digest in required.items()):
        raise ValueError("Exact v5 transport source receipts required")
    return dict(source_files=len(sources), receipt_files=len(receipts), v5_sources=required)


def _capture_receipts(serial, events_text, armed, state, returned):
    installation = state.get("installation")
    expected_installation = dict(
        directory=str(INSTALLED), checkpoint_sha256=SEMANTIC["installed_checkpoint"],
        plan_sha256=SEMANTIC["installed_plan"], result_sha256=FILE_SHA256[INSTALLED / "result.json"],
        loader_sha256=TRIAL_TRIPLE["probe.bin"], config_sha256=TRIAL_TRIPLE["config.txt"],
        original_linux_boot_id=BOOT_BEFORE, triple_sha256=TRIAL_TRIPLE,
        pair_sha256={key: TRIAL_TRIPLE[key] for key in ("bl31.bin", "probe.bin")})
    if not isinstance(installation, dict) or any(installation.get(k) != v for k, v in expected_installation.items()):
        raise ValueError("Exact installed trial hashes required in capture state")
    if armed.get("installation") != installation or returned.get("installation") != installation:
        raise ValueError("Armed/state/return installation receipts differ")
    common = ("pid", "device", "baud", "started_utc", "armed_utc", "armed_monotonic")
    if any(armed.get(key) != state.get(key) for key in common):
        raise ValueError("Armed and terminal capture identity differs")
    if (armed.get("status") != "failed" or state.get("status") != "captured" or
            armed.get("transmitted_bytes") != 0 or state.get("transmitted_bytes") != 0 or
            armed.get("continuous_capture") is not False or state.get("continuous_capture") is not True or
            state.get("bytes") != len(serial) or state.get("serial_sha256") != SERIAL_SHA or
            state.get("diagnostic_error") != LEGACY_ERROR or
            state.get("inventory") != dict(id_lines=59,
                last_id_line=(protocol.PREFIX + b"END OK=1 PHASE=1 LAST=1 LIFE=0 FLAGS=00 "
                    b"ID=00000000 COMMAND=0000 BAR1=00000000 GEN=0 LANES=0").decode(), failed_rows=[])):
        raise ValueError("Exact old recorder state and known legacy classification required")
    events = _events(events_text, len(serial))
    if events["first_monotonic"] <= state["armed_monotonic"] or events["last_monotonic"] <= events["first_monotonic"]:
        raise ValueError("Recorder was not armed before receive events")
    return dict(installation=expected_installation, events=events,
        transmitted_bytes=0, legacy_diagnostic_error=LEGACY_ERROR)


def _catalog(result, count, digest, boot, triple):
    publication = result.get("publication", {})
    active = {key: publication.get("protected_files_sha256", {}).get(key) for key in triple}
    if (len(result.get("next_catalog", [])) != count or result.get("next_catalog_sha256") != digest or
            publication.get("identity", {}).get("boot_id") != boot or active != triple):
        raise ValueError("Exact catalog/triple publication differs")
    return dict(count=count, sha256=digest, boot_id=boot, triple=active)


def _chain(documents):
    baseline = documents["baseline_result"]
    installed_cp = documents["installed_checkpoint"]
    installed_plan = documents["installed_plan"]
    installed = documents["installed_result"]
    restore_cp = documents["restored_checkpoint"]
    restore_plan = documents["restored_plan"]
    restored = documents["restored_result"]
    offline = documents["offline_plan"]
    returned = documents["return"]
    if (seals.digest(installed_cp) != SEMANTIC["installed_checkpoint"] or
            seals.digest(installed_plan) != SEMANTIC["installed_plan"] or
            installed.get("checkpoint_sha256") != SEMANTIC["installed_checkpoint"] or
            installed.get("plan_sha256") != SEMANTIC["installed_plan"]):
        raise ValueError("Exact installed checkpoint/plan linkage required")
    if (seals.digest(restore_cp) != SEMANTIC["restored_checkpoint"] or
            seals.digest(restore_plan) != SEMANTIC["restored_plan"] or
            restored.get("checkpoint_sha256") != SEMANTIC["restored_checkpoint"] or
            restored.get("plan_sha256") != SEMANTIC["restored_plan"]):
        raise ValueError("Exact restored checkpoint/plan linkage required")
    base_row = _catalog(baseline, 512,
        "8f7be2df370eb5a6951e645fca95d0609db141cf07ac53da020e7bcd26964566", BOOT_BEFORE, NORMAL_TRIPLE)
    installed_row = _catalog(installed, 518,
        "e69d964799f7cf64fc60b82d8984db3ce329033f40f80d0a25f0603bbe6a2827", BOOT_BEFORE, TRIAL_TRIPLE)
    restored_row = _catalog(restored, 524,
        "5aa6a9e2f2c94090e6ded0dfa27129d26924f8ea98479f6aebb61e97d4d54c20", BOOT_AFTER, NORMAL_TRIPLE)
    if (installed["next_catalog"][:512] != baseline["next_catalog"] or
            restored["next_catalog"][:518] != installed["next_catalog"] or
            installed_plan.get("historical_catalog") != baseline["next_catalog"] or
            restore_plan.get("historical_catalog") != installed["next_catalog"]):
        raise ValueError("Exact append-only catalog512-to-518-to-524 chain required")
    ancestry = offline.get("media", {}).get("ancestry", {})
    if (offline.get("checkpoint_sha256") != SEMANTIC["restored_checkpoint"] or
            offline.get("hardware_admission") is not False or
            ancestry.get("return_sha256") != FILE_SHA256[CAPTURE / "return.json"] or
            ancestry.get("hashes") != {
                "checkpoint.json": FILE_SHA256[INSTALLED / "checkpoint.json"],
                "plan.json": FILE_SHA256[INSTALLED / "plan.json"],
                "result.json": FILE_SHA256[INSTALLED / "result.json"],
            } or offline.get("media", {}).get("identity_binding", {}).get("linux_boot_id_after_write") != BOOT_AFTER):
        raise ValueError("Exact independent return to restoration ancestry required")
    if (returned.get("format") != "rpi5-next-link-independent-return-v2" or
            returned.get("capture_valid") is not False or returned.get("capture_error") != "Incomplete/error/non-zero-TX capture" or
            returned.get("zero_serial_tx") is not True or
            returned.get("independent_normal_nvme_linux_return_verified") is not True or
            returned.get("linux_boot_id") != BOOT_AFTER or
            returned.get("observation", {}).get("identity", {}).get("identity", {}).get("root") !=
                "/dev/nvme0n1p2 ext4 04570742-280b-43cb-9564-73d454243b1c"):
        raise ValueError("Exact independent NVMe return receipt required")
    return dict(catalogs=[base_row, installed_row, restored_row], counts=[512, 518, 524],
        independent_nvme_return=True, exact_triple_restored=True,
        legacy_capture_classification=False, replay_chain_verified=True)


def load_documents():
    return {
        "serial": (CAPTURE / "serial.bin").read_bytes(),
        "events_text": (CAPTURE / "receive-events.jsonl").read_text(),
        "armed": json.loads((CAPTURE / "armed.json").read_text()),
        "state": json.loads((CAPTURE / "state.json").read_text()),
        "return": json.loads((CAPTURE / "return.json").read_text()),
        "baseline_result": json.loads((BASELINE / "result.json").read_text()),
        "installed_checkpoint": json.loads((INSTALLED / "checkpoint.json").read_text()),
        "installed_plan": json.loads((INSTALLED / "plan.json").read_text()),
        "installed_result": json.loads((INSTALLED / "result.json").read_text()),
        "restored_checkpoint": json.loads((RESTORED / "checkpoint.json").read_text()),
        "restored_plan": json.loads((RESTORED / "plan.json").read_text()),
        "restored_result": json.loads((RESTORED / "result.json").read_text()),
        "offline_plan": json.loads((RESTORE_PREPARED / "offline-plan.json").read_text()),
    }


def inspect_documents(documents):
    serial = documents["serial"]
    mapping = inspect_serial(serial)
    receipts = _capture_receipts(serial, documents["events_text"], documents["armed"],
        documents["state"], documents["return"])
    sources = _source_receipts(documents["armed"], documents["state"], documents["return"])
    chain = _chain(documents)
    return dict(
        profile="rpi5-gem-physmap-mapping-board-evidence-v1",
        status="pass",
        evidence_type="physical-board-mapping-verification-only",
        serial_sha256=SERIAL_SHA,
        serial_bytes=len(serial),
        marker=MARKER,
        complete_capture=True,
        zero_transmit=True,
        mapping_verification_pass=True,
        reason=41,
        four_normal_nc_aliases=True,
        bounded_page_table_accounting=True,
        discard_before_route=True,
        route_dma_irq_queues_packets_tx_activated=False,
        rp1_identity_or_link_success_claimed=False,
        ethernet_proven=False,
        legacy_recorder_classification=dict(capture_valid=False, error=LEGACY_ERROR,
            applicability="rejected: RP1-ID/link success is outside verification-only END authority"),
        mapping=mapping,
        capture_receipts=receipts,
        source_receipts=sources,
        restoration=chain,
    )


def check():
    for path, digest in FILE_SHA256.items():
        if sha(path) != digest:
            raise ValueError("Immutable board evidence artifact changed: " + str(path))
    documents = load_documents()
    capture_sha = documents["return"].get("capture_sha256")
    if capture_sha != {
            "armed.json": FILE_SHA256[CAPTURE / "armed.json"],
            "receive-events.jsonl": FILE_SHA256[CAPTURE / "receive-events.jsonl"],
            "serial.bin": SERIAL_SHA,
            "state.json": FILE_SHA256[CAPTURE / "state.json"],
            }:
        raise ValueError("Independent return capture hash receipt differs")
    result = inspect_documents(documents)
    result.update(
        checker_sha256=sha(Path(__file__)),
        immutable_artifacts={str(path): digest for path, digest in FILE_SHA256.items()},
        semantic_digests=SEMANTIC,
    )
    return result


def compact(result):
    """Stable typed board report; detailed receipts remain pinned by hashes."""
    return dict(
        profile=result["profile"], status=result["status"], evidence_type=result["evidence_type"],
        checker_sha256=result["checker_sha256"], serial_sha256=result["serial_sha256"],
        serial_bytes=result["serial_bytes"], marker=result["marker"],
        immutable_capture_sha256={
            Path(path).name: digest for path, digest in result["immutable_artifacts"].items()
            if str(CAPTURE) in path
        },
        complete_capture=result["complete_capture"], zero_transmit=result["zero_transmit"],
        receive_events=result["capture_receipts"]["events"],
        source_files=result["source_receipts"]["source_files"],
        receipt_files=result["source_receipts"]["receipt_files"],
        v5_source_sha256=result["source_receipts"]["v5_sources"],
        mapping_verification_pass=result["mapping_verification_pass"], reason=result["reason"],
        aliases=result["mapping"]["aliases"],
        page_table_accounting=result["mapping"]["page_table_accounting"],
        terminal=result["mapping"]["terminal"],
        discard_before_route=result["discard_before_route"],
        route_dma_irq_queues_packets_tx_activated=result["route_dma_irq_queues_packets_tx_activated"],
        rp1_identity_or_link_success_claimed=result["rp1_identity_or_link_success_claimed"],
        ethernet_proven=result["ethernet_proven"],
        legacy_recorder_classification=result["legacy_recorder_classification"],
        semantic_digests=result["semantic_digests"],
        restoration=result["restoration"],
    )


if __name__ == "__main__":
    print(json.dumps(compact(check()), sort_keys=True))
