#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bind the sealed CPU-ring contract before parsing the immutable v2 capture.

Transport v2 passed only its small admission report to the inherited parser.
That report intentionally omitted the large, software-only contract dictionaries
and the two materialization markers.  This adapter reconstructs those values
from pinned software bytes.  No value observed from the board is invented or
rewritten: the inherited 53-row parser still validates the original serial
bytes and returns all decoded hardware values.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import struct

from tools.rpi5 import gem_cpu_ring_retry_serial as protocol
from tools.rpi5 import gem_dma_batch_contract as contracts


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "build/rpi5/gem-cpu-ring-physmap-trial-20261014-v2"
MANIFEST_SHA256 = "9cc31e53c773af491806b2cee60a794679034da042df4fd4a6c50ab1522b6b80"
IMAGE_SHA256 = "fbfca7c3e40893ddd383b5183b5f5f3db9a52fbbfb3b87c749523c2d6a3fcbae"
KERNEL_SHA256 = "6afdabf0ca98b0e854f7ee27e29e9868ee31b60cf955899867eb39572a14d128"
PAYLOAD_SHA256 = "415d2a5e08d57765d5d38b723c09986e575a7824a7ae766bc52ba5bbd9330709"
CONTRACT_SOURCE = ROOT / "tools/rpi5/gem_dma_batch_contract.py"
CONTRACT_SOURCE_SHA256 = "05d425f0bc61d25c97ddc4e90a8a857ddd8e1d92855ebb7439cd56cbe9f8bc8a"
SEALED_CONTRACT_REPORT = ROOT / "build/rpi5/gem-cpu-ring-retry-check-20261014-v1.json"
SEALED_CONTRACT_REPORT_SHA256 = "2d15b2ce7e0c9dc68cadf459021543f9ebcbc2decc80c71e6909383cc5fbee39"
EXPECTED_TAG = "4c9d25d41fbd43b2a08f27d147b46171"
EXPECTED_MARKER = (
    "RPI5XNU:CPU_RINGS:ENTRY TAG=4c9d25d41fbd43b2a08f27d147b46171 "
    "CPUS=1 NO_CPU_ON NO_QUEUE NO_DMA"
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def same(left, right):
    return json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, separators=(",", ":"))


def _checked_json(path, digest):
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or sha256(path) != digest:
        raise ValueError("Pinned JSON bytes differ: " + str(path))
    return json.loads(Path(path).read_bytes())


def _macho_envelope(data):
    if data[:4] != b"\xcf\xfa\xed\xfe" or struct.unpack_from("<I", data, 4)[0] != 0x0100000C:
        raise ValueError("Exact AArch64 Mach-O kernel required")
    count, command_bytes = struct.unpack_from("<II", data, 16)
    offset = 32
    segments = []
    if offset + command_bytes > len(data):
        raise ValueError("Mach-O load commands truncated")
    for _ in range(count):
        command, size = struct.unpack_from("<II", data, offset)
        if size < 8 or offset + size > 32 + command_bytes:
            raise ValueError("Invalid Mach-O load command")
        if command == 0x19:
            _, virtual, memory, file_offset, file_size, _, _, _, _ = struct.unpack_from(
                "<16sQQQQIIII", data, offset + 8)
            if file_offset + file_size > len(data):
                raise ValueError("Mach-O segment exceeds checked kernel")
            segments.append((virtual, memory))
        offset += size
    if offset != 32 + command_bytes or not segments or not any(memory for _, memory in segments):
        raise ValueError("Complete Mach-O segment inventory required")
    start = min(virtual for virtual, memory in segments if memory)
    end = max(virtual + memory for virtual, memory in segments)
    if end <= start:
        raise ValueError("Positive Mach-O envelope required")
    return end - start


def bind_report(report, source_pins):
    """Return a parser report whose omitted fields are bound to sealed bytes."""
    if not isinstance(report, dict) or not isinstance(source_pins, dict):
        raise ValueError("Sealed report and source pin dictionary required")
    required_pins = {
        str(CONTRACT_SOURCE): CONTRACT_SOURCE_SHA256,
        str(SEALED_CONTRACT_REPORT): SEALED_CONTRACT_REPORT_SHA256,
        str(PACKAGE / "manifest.json"): MANIFEST_SHA256,
        str(PACKAGE / "probe.bin"): IMAGE_SHA256,
    }
    for path, digest in required_pins.items():
        if source_pins.get(path) != digest or sha256(path) != digest:
            raise ValueError("Contract source absent from the sealed capture: " + path)

    manifest = _checked_json(PACKAGE / "manifest.json", MANIFEST_SHA256)
    generated = manifest.get("generated_sha256", {})
    checked = {
        PACKAGE / "probe.bin": IMAGE_SHA256,
        PACKAGE / "kernel.cpu-rings": KERNEL_SHA256,
        PACKAGE / "payload.bin": PAYLOAD_SHA256,
    }
    for path, digest in checked.items():
        if generated.get(str(path)) != digest or sha256(path) != digest:
            raise ValueError("Checked physmap package member differs: " + str(path))
    if (manifest.get("tag"), manifest.get("trial_marker"), manifest.get("image_sha256"),
            manifest.get("kernel_sha256")) != (
                EXPECTED_TAG, EXPECTED_MARKER, IMAGE_SHA256, KERNEL_SHA256):
        raise ValueError("Exact checked physmap package identity required")

    sealed = _checked_json(SEALED_CONTRACT_REPORT, SEALED_CONTRACT_REPORT_SHA256)
    cpu_contract = contracts.contract()
    inherited_contracts = contracts.inherited()
    if (not same(sealed.get("cpu_ring_contract"), cpu_contract) or
            not same(sealed.get("inherited_capability_contracts"), inherited_contracts)):
        raise ValueError("Pinned gem_dma_batch_contract values differ")

    probe = (PACKAGE / "probe.bin").read_bytes()
    payload = (PACKAGE / "payload.bin").read_bytes()
    payload_offset = manifest.get("payload_offset")
    if (type(payload_offset) is not int or payload_offset < 0 or probe[payload_offset:] != payload):
        raise ValueError("Exact embedded payload boundary required")
    if len(payload) < 152:
        raise ValueError("Complete payload header required")
    root_offset, root_bytes = struct.unpack_from("<QQ", payload, 136)
    if (root_offset + root_bytes > len(payload) or root_bytes != manifest.get("root_bytes") or
            hashlib.sha256(payload[root_offset:root_offset + root_bytes]).hexdigest() != manifest.get("root_sha256")):
        raise ValueError("Exact embedded ramdisk bytes required")

    envelope = _macho_envelope((PACKAGE / "kernel.cpu-rings").read_bytes())
    args_pa = (0x07004000 + envelope + 0x3FFF) & ~0x3FFF
    root_pa = args_pa + 0x8000
    root_marker = (
        f"RPI5XNU:BL33:RAMDISK_MATERIALIZED PA={root_pa:016x} "
        f"BYTES={root_bytes:016x} VERIFIED"
    )
    kernel_marker = (
        f"RPI5XNU:BL33:KERNEL_MATERIALIZED BYTES={envelope:016x} "
        "FULL_ENVELOPE_VERIFIED NO_BOOT_ARGS_WRITTEN NO_TRANSFER"
    )
    if (root_marker, kernel_marker) != (
            sealed.get("root_copy_marker"), sealed.get("kernel_copy_marker")):
        raise ValueError("Derived materialization markers differ from the sealed predecessor")

    bound = copy.deepcopy(report)
    if (bound.get("tag"), bound.get("marker")) != (EXPECTED_TAG, EXPECTED_MARKER):
        raise ValueError("Exact physical-trial admission identity required")
    bound.update(
        cpu_ring_contract=cpu_contract,
        inherited_capability_contracts=inherited_contracts,
        root_copy_marker=root_marker,
        kernel_copy_marker=kernel_marker,
        boot_markers=[
            EXPECTED_MARKER, contracts.HOST, contracts.DEVICE, contracts.FDT,
            root_marker, kernel_marker,
        ],
    )
    return bound


def inspect(data, report, source_pins):
    if not isinstance(data, bytes):
        raise ValueError("Original serial bytes required")
    bound = bind_report(report, source_pins)
    marker_positions = [data.find(marker.encode()) for marker in bound["boot_markers"]]
    if (any(position < 0 for position in marker_positions) or
            marker_positions != sorted(marker_positions) or
            any(data.count(marker.encode()) != 1 for marker in bound["boot_markers"])):
        raise ValueError("Exact unique ordered package-derived boot markers required")
    result = protocol.inspect(data, bound)
    rows = [row.rstrip(b"\r") for row in data.split(b"\n") if row.startswith(protocol.PREFIX)]
    if len(rows) != 53 or tuple(
            row.split(b" ", 1)[0][len(protocol.PREFIX):].decode("ascii") for row in rows
            ) != protocol.ORDER:
        raise ValueError("Strict 53-row physical record order required")
    positions = protocol.return_positions(data)
    if positions is None or positions != sorted(positions) or len(positions) != 4:
        raise ValueError("Exact ordered automatic-return markers required")
    row_wire = b"\n".join(rows) + b"\n"
    result.update(
        parser_profile="rpi5-gem-cpu-ring-physmap-serial-v3",
        contract_binding="sealed-source-pins-and-checked-package-bytes",
        ordered_record_names=list(protocol.ORDER),
        ordered_records=[row.decode("ascii") for row in rows],
        ordered_records_sha256=hashlib.sha256(row_wire).hexdigest(),
        return_marker_positions=positions,
        exact_return_marker_count=4,
        no_fault_through_return=True,
    )
    return result
