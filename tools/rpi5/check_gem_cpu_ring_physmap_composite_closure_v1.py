#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Close the completed CPU-ring physmap trial without rewriting history.

The original return receipt is intentionally retained with capture_valid=false:
its parser predates the scoped CPU-ring contracts.  A separately generated,
immutable board-evidence report types the same receive-only serial bytes.  This
checker binds those two artifacts to the exact install/restore receipt chain.

Historical catalogs are replayed as append-only metadata.  This checker does
not turn that replay into a claim that every historical archive was re-read.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.rpi5 import trial_checkpoint_v2 as seals


BUILD = ROOT / "build/rpi5"
CAPTURE = BUILD / "gem-cpu-ring-physmap-v2-capture-r6"
INSTALLED = BUILD / "gem-cpu-ring-physmap-v2-installed-r6"
RESTORED = BUILD / "gem-cpu-ring-physmap-v2-restored-r6"
BOARD_REPORT = BUILD / "gem-cpu-ring-physmap-board-evidence-20261014-v1.json"

SERIAL_SHA256 = "adb0cdd8d16da53fcf8951b0bf3004c6a4371cc9729cb965cadb3e31da64bd70"
SERIAL_BYTES = 36518
BOARD_REPORT_SHA256 = "050d50a2efd723ddd3bf37ad3b0f7753b4242396ee41d6271b5a5729e5d5b96f"
RETURN_SHA256 = "8ad09ae246520cbd7158aaca7c252e1787e09c6ee9ae28197c33e590b5ca7b1a"
FRESH_BOOT_ID = "d2fd08b0-1ff7-46ab-b237-e2e64f20446a"
ORIGINAL_BOOT_ID = "2d237d96-a323-4df7-a8b4-ad9b4eb5f477"
ROOT_DEVICE = "/dev/nvme0n1p2 ext4 04570742-280b-43cb-9564-73d454243b1c"
LEGACY_ERROR = "Exact CPU-only and scoped inherited contracts required"

INSTALLED_CHECKPOINT_SEAL = "304e3a6b4360b8e4452959b1915a4d573bfe5ad65846e08044588e931e44e27a"
INSTALLED_PLAN_SEAL = "8d3902aeecd4949327c51e1a07aecb4ef084c2848d6c41004f7cd38e7fc2848c"
RESTORED_CHECKPOINT_SEAL = "16225779191c09f6117fde4608a94afa46a45a39606253d7180b90a67bdc2b05"
RESTORED_PLAN_SEAL = "0aa869d844f5e5d966d2cbf7f628d51c928e9623c4cfe858c3e55a6ef9742500"

CATALOG_SHA256 = {
    524: "5aa6a9e2f2c94090e6ded0dfa27129d26924f8ea98479f6aebb61e97d4d54c20",
    530: "bfbc0a5be77a520e978c6a519050b8c7c46d2ad0ef80c0ddcb76aeb4c8659fb1",
    536: "0cf1c6e316577f7e47ce196db16977fad7c5f80cda26cea118993249fa26e226",
}

TRIAL_TRIPLE = {
    "config.txt": "359263f7f9776c6300ebeba344aeb0e2dd2d07df7064fb344b55236219f4cde7",
    "bl31.bin": "dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b",
    "probe.bin": "fbfca7c3e40893ddd383b5183b5f5f3db9a52fbbfb3b87c749523c2d6a3fcbae",
}
RESTORED_TRIPLE = {
    "config.txt": "aaccab184135aca272db4123fcba34e20874ae0959a90aed1ef6fd4d5e18ed28",
    "bl31.bin": "413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46",
    "probe.bin": "f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536",
}

FILE_SHA256 = {
    BOARD_REPORT: BOARD_REPORT_SHA256,
    CAPTURE / "serial.bin": SERIAL_SHA256,
    CAPTURE / "return.json": RETURN_SHA256,
    INSTALLED / "checkpoint.json": "6e72a8d5ec4b6374ec187e47b8d8f8e1f90f2e2fa3d8c2b5cb6995cf03979644",
    INSTALLED / "plan.json": "08161d90ea0da2f527fbd24b98e284d27f44ac354e74e334a361c878b76023e7",
    INSTALLED / "result.json": "3e2b0980b69a2d9f960bf078e8ac404c364e25e0ffa6cf6ef89d98a789e21054",
    RESTORED / "checkpoint.json": "47e7708f74a375d430a82dcb8c98e25199f00a4ea4b8b7942dbeae4fdf53893a",
    RESTORED / "plan.json": "42d70ca46f48815191e5a4b916700544be1088c485941dd82106acd6f55bbb43",
    RESTORED / "result.json": "7375ac09c4602431f4ad7a368f971882e9e35e523c452d3e46915055f9dce49a",
}


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return sha_bytes(Path(path).read_bytes())


def _catalog(value, count, digest, label):
    if not isinstance(value, list) or len(value) != count or seals.digest(value) != digest:
        raise ValueError(f"Exact catalog{count} {label} required")


def _seal(document, expected, label):
    if seals.digest(document) != expected:
        raise ValueError(f"Exact {label} semantic seal required")


def load_documents():
    def load(path):
        return json.loads(path.read_bytes())

    return {
        "board_report": load(BOARD_REPORT),
        "serial": (CAPTURE / "serial.bin").read_bytes(),
        "return": load(CAPTURE / "return.json"),
        "installed_checkpoint": load(INSTALLED / "checkpoint.json"),
        "installed_plan": load(INSTALLED / "plan.json"),
        "installed_result": load(INSTALLED / "result.json"),
        "restored_checkpoint": load(RESTORED / "checkpoint.json"),
        "restored_plan": load(RESTORED / "plan.json"),
        "restored_result": load(RESTORED / "result.json"),
    }


def _board(board, serial):
    diagnostic = board.get("diagnostic", {})
    if sha_bytes(serial) != SERIAL_SHA256 or len(serial) != SERIAL_BYTES:
        raise ValueError("Exact immutable CPU-ring serial bytes required")
    required_true = (
        "cpu_ring_physical_trial_pass",
        "automatic_watchdog_return_observed",
        "normal_nvme_serial_boot_observed",
        "full_original_capture_health_scan",
        "raw_capture_immutable",
        "zero_serial_transmit",
        "legacy_error_is_receipt_omission_not_hardware_failure",
    )
    required_false = (
        "runtime_fault_signature_observed",
        "ethernet_proven",
        "dma",
        "irq_delivery",
        "queue_publication",
        "packets",
    )
    if (board.get("profile") != "rpi5-gem-cpu-ring-physmap-board-evidence-v1" or
            board.get("status") != "pass" or board.get("serial_sha256") != SERIAL_SHA256 or
            board.get("serial_bytes") != SERIAL_BYTES or board.get("legacy_parser_error") != LEGACY_ERROR or
            any(board.get(key) is not True for key in required_true) or
            any(board.get(key) is not False for key in required_false)):
        raise ValueError("Exact supplemental CPU-ring board report required")
    if (diagnostic.get("cpu_ring_retry_trial_pass") is not True or
            diagnostic.get("no_fault_through_return") is not True or
            diagnostic.get("ethernet_proven") is not False or
            diagnostic.get("dma") is not False or diagnostic.get("irq_delivery") is not False or
            diagnostic.get("queue_publication") is not False or
            diagnostic.get("preparation") != {"step": 17, "error": 0, "bytes": 32768, "packets": 0} or
            diagnostic.get("cpu_ring_stage") != {
                "state": 2, "error": 0, "attempted": 640, "written": 640,
                "read": 640, "calls": 81, "checks": 164,
            } or diagnostic.get("cpu_ring_geometry", {}).get("owned") != 160):
        raise ValueError("Exact bounded CPU-owned ring observations required")
    return {
        "report_sha256": BOARD_REPORT_SHA256,
        "serial_sha256": SERIAL_SHA256,
        "serial_bytes": SERIAL_BYTES,
        "physical_cpu_ring_trial": True,
        "zero_serial_transmit": True,
        "watchdog_return_observed": True,
    }


def _legacy_return(returned):
    observation = returned.get("observation", {})
    identity = observation.get("identity", {})
    installation = returned.get("installation", {})
    capture_hashes = returned.get("capture_sha256", {})
    if (returned.get("format") != "rpi5-next-link-independent-return-v2" or
            returned.get("capture_valid") is not False or
            returned.get("capture_error") != "Incomplete/error/non-zero-TX capture" or
            returned.get("diagnostic") is not None or returned.get("zero_serial_tx") is not True or
            returned.get("ethernet_proven") is not False or
            returned.get("independent_normal_nvme_linux_return_verified") is not True or
            returned.get("linux_boot_id") != FRESH_BOOT_ID or
            observation.get("boot_id") != FRESH_BOOT_ID or
            identity.get("boot_id") != FRESH_BOOT_ID or
            identity.get("identity", {}).get("root") != ROOT_DEVICE or
            capture_hashes.get("serial.bin") != SERIAL_SHA256 or
            installation.get("original_linux_boot_id") != ORIGINAL_BOOT_ID or
            installation.get("triple_sha256") != TRIAL_TRIPLE):
        raise ValueError("Exact retained legacy return and fresh NVMe boot required")
    return {
        "return_sha256": RETURN_SHA256,
        "capture_valid": False,
        "classification": "retained-parser-omission-superseded-by-supplemental-board-evidence",
        "fresh_linux_boot_id": FRESH_BOOT_ID,
        "independent_normal_nvme_linux_return": True,
    }


def _chain(documents):
    installed_cp = documents["installed_checkpoint"]
    installed_plan = documents["installed_plan"]
    installed = documents["installed_result"]
    restored_cp = documents["restored_checkpoint"]
    restored_plan = documents["restored_plan"]
    restored = documents["restored_result"]

    _seal(installed_cp, INSTALLED_CHECKPOINT_SEAL, "installed checkpoint")
    _seal(installed_plan, INSTALLED_PLAN_SEAL, "installed plan")
    _seal(restored_cp, RESTORED_CHECKPOINT_SEAL, "restored checkpoint")
    _seal(restored_plan, RESTORED_PLAN_SEAL, "restored plan")
    if (installed.get("checkpoint_sha256") != INSTALLED_CHECKPOINT_SEAL or
            installed.get("plan_sha256") != INSTALLED_PLAN_SEAL or
            restored.get("checkpoint_sha256") != RESTORED_CHECKPOINT_SEAL or
            restored.get("plan_sha256") != RESTORED_PLAN_SEAL or
            installed.get("status") != "complete" or restored.get("status") != "complete"):
        raise ValueError("Exact install/restore checkpoint and plan linkage required")

    c524 = installed_plan.get("historical_catalog")
    c530 = installed.get("next_catalog")
    c536 = restored.get("next_catalog")
    _catalog(c524, 524, CATALOG_SHA256[524], "baseline")
    _catalog(c530, 530, CATALOG_SHA256[530], "installed")
    _catalog(c536, 536, CATALOG_SHA256[536], "restored")
    if (installed_plan.get("historical_catalog_sha256") != CATALOG_SHA256[524] or
            installed.get("historical_catalog") != c524 or
            installed.get("historical_catalog_sha256") != CATALOG_SHA256[524] or
            installed.get("next_catalog_sha256") != CATALOG_SHA256[530] or
            restored_plan.get("historical_catalog") != c530 or
            restored_plan.get("historical_catalog_sha256") != CATALOG_SHA256[530] or
            restored.get("historical_catalog") != c530 or
            restored.get("historical_catalog_sha256") != CATALOG_SHA256[530] or
            restored.get("next_catalog_sha256") != CATALOG_SHA256[536] or
            c530[:524] != c524 or c536[:530] != c530):
        raise ValueError("Exact append-only catalog524-to-530-to-536 replay required")

    ancestry = restored_plan.get("media", {}).get("ancestry", {})
    expected_ancestry = {
        "checkpoint.json": FILE_SHA256[INSTALLED / "checkpoint.json"],
        "plan.json": FILE_SHA256[INSTALLED / "plan.json"],
        "result.json": FILE_SHA256[INSTALLED / "result.json"],
    }
    if (ancestry.get("return_sha256") != RETURN_SHA256 or
            ancestry.get("hashes") != expected_ancestry):
        raise ValueError("Exact legacy return-to-restoration ancestry required")

    publication = restored.get("publication", {})
    active = {name: publication.get("protected_files_sha256", {}).get(name)
              for name in RESTORED_TRIPLE}
    previous = publication.get("nvme_previous_triple_sha256")
    media = restored_plan.get("media", {})
    binding = media.get("identity_binding", {})
    if (active != RESTORED_TRIPLE or previous != TRIAL_TRIPLE or
            publication.get("identity", {}).get("boot_id") != FRESH_BOOT_ID or
            binding.get("linux_boot_id_before_write") != ORIGINAL_BOOT_ID or
            binding.get("linux_boot_id_after_write") != FRESH_BOOT_ID):
        raise ValueError("Exact restored normal triple and fresh boot binding required")

    for value in (installed_plan, installed, restored_plan, restored):
        if value.get("historical_archives_reverified") is not False:
            raise ValueError("Historical catalog replay must not claim archive re-verification")
    for value in (installed_plan, installed, restored_plan, restored):
        if value.get("no_implicit_retry_or_rollback") is not True:
            raise ValueError("No implicit retry or rollback is required")
    if (installed.get("deleted_archives") != [] or restored.get("deleted_archives") != [] or
            installed.get("created_archive_count") != 6 or restored.get("created_archive_count") != 6 or
            installed.get("preserved_archive_count") != 524 or restored.get("preserved_archive_count") != 530 or
            installed.get("newly_created_rollback_archives_verified") in (None, []) or
            restored.get("newly_created_rollback_archives_verified") in (None, [])):
        raise ValueError("Exact preservation and rollback-archive semantics required")

    return {
        "checkpoint_seals": {
            "installed": INSTALLED_CHECKPOINT_SEAL,
            "restored": RESTORED_CHECKPOINT_SEAL,
        },
        "plan_seals": {"installed": INSTALLED_PLAN_SEAL, "restored": RESTORED_PLAN_SEAL},
        "restored_result_sha256": FILE_SHA256[RESTORED / "result.json"],
        "catalog_counts": [524, 530, 536],
        "catalog_sha256": [CATALOG_SHA256[count] for count in (524, 530, 536)],
        "catalog_append_only": True,
        "restored_triple_sha256": RESTORED_TRIPLE,
        "legacy_catalog_replay": True,
        "historical_archives_reverified": False,
        "new_rollback_archives_verified": True,
        "history_deleted": False,
        "implicit_retry_or_rollback": False,
    }


def inspect_documents(documents):
    board = _board(documents["board_report"], documents["serial"])
    returned = _legacy_return(documents["return"])
    chain = _chain(documents)
    return {
        "profile": "rpi5-gem-cpu-ring-physmap-composite-closure-v1",
        "status": "pass",
        "evidence_type": "supplemental-board-report-plus-retained-return-plus-restoration-chain",
        "cpu_ring_physmap_trial_closed": True,
        "board_evidence": board,
        "legacy_return": returned,
        "restoration": chain,
        "authority": {
            "cpu_owned_descriptor_store_readback_and_owner_lifecycle": True,
            "dma": False,
            "irq_delivery": False,
            "queue_publication": False,
            "packets": False,
            "ethernet_proven": False,
        },
    }


def check():
    for path, digest in FILE_SHA256.items():
        if sha(path) != digest:
            raise ValueError("Immutable CPU-ring closure artifact changed: " + str(path))
    return inspect_documents(load_documents())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = check()
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as out:
            out.write(encoded)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
