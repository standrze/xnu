// SPDX-License-Identifier: BSD-2-Clause
import Foundation

/// Strict decoder for this probe's bounded TLV snapshot, not a general ACPI interpreter.
public struct ProbeDiagnostics {
    public struct Record {
        public let kind: Int
        public let index: Int
        public let bytes: Data
    }

    public let records: [Record]
    public let nonce: String

    public init(bytes: Data, expectedNonce: String) throws {
        try ProbeDisk.validateNonce(expectedNonce)
        guard bytes.count == ProbeDisk.diagnosticByteCount,
            String(decoding: bytes.prefix(8), as: UTF8.self) == "EFIDIAG2",
            Self.read(bytes, 8, 4) == 2,
            String(decoding: bytes[16..<48], as: UTF8.self) == expectedNonce,
            Self.read(bytes, 52, 4) == 1
        else {
            throw ProbeError.invalid("diagnostic header/nonce/completion check failed")
        }
        let used = Int(Self.read(bytes, 12, 4))
        let count = Int(Self.read(bytes, 48, 4))
        guard used >= 64, used <= bytes.count, count > 0, count <= 128 else {
            throw ProbeError.invalid("invalid diagnostic bounds")
        }
        var parsed: [Record] = []
        var offset = 64
        var identities = Set<String>()
        for _ in 0..<count {
            guard offset <= used - 16 else { throw ProbeError.invalid("truncated diagnostic record") }
            let kind = Int(Self.read(bytes, offset, 4))
            let index = Int(Self.read(bytes, offset + 4, 4))
            let length = Int(Self.read(bytes, offset + 8, 4))
            guard (1...5).contains(kind), length > 0, length <= used - offset - 16,
                identities.insert("\(kind):\(index)").inserted
            else {
                throw ProbeError.invalid("invalid diagnostic record")
            }
            let payload = bytes.subdata(in: (offset + 16)..<(offset + 16 + length))
            if kind == 2 {
                guard payload.count >= 36, Self.read(payload, 4, 4) == payload.count,
                    payload.reduce(UInt8(0), &+) == 0,
                    payload.prefix(4).allSatisfy({ (32...126).contains($0) })
                else {
                    throw ProbeError.invalid("ACPI table checksum/length/signature failed")
                }
            }
            if kind == 5 && length != 288 { throw ProbeError.invalid("invalid PCI snapshot length") }
            parsed.append(Record(kind: kind, index: index, bytes: payload))
            offset += 16 + length
        }
        guard offset == used, parsed.filter({ $0.kind == 3 }).count == 1 else {
            throw ProbeError.invalid("diagnostic record count or memory map mismatch")
        }
        self.records = parsed
        self.nonce = expectedNonce
    }

    /// Save exact raw tables and a compact decoded platform inventory; never mounts a disk.
    public func write(to directory: URL, report: ProbeReport) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
        var tables: [[String: Any]] = []
        var memory: [[String: Any]] = []
        var pci: [[String: Any]] = []
        var serial: [[String: Any]] = []
        for record in records {
            let bytes = record.bytes
            let filename: String
            switch record.kind {
            case 1:
                filename = "RSDP-\(record.index).bin"
            case 2:
                let signature = String(decoding: bytes.prefix(4), as: UTF8.self)
                guard signature.utf8.allSatisfy({ (65...90).contains($0) || (48...57).contains($0) || $0 == 95 }) else {
                    throw ProbeError.invalid("unsafe ACPI filename signature")
                }
                filename = "\(signature)-\(record.index).bin"
                tables.append(try Self.tableSummary(bytes, filename: filename))
            case 3:
                filename = "efi-memory-map.bin"
                guard let value = report.fields["memory_descriptor_size"],
                    let width = Int(value.dropFirst(2), radix: 16), width >= 40, width <= 256,
                    bytes.count % width == 0
                else { throw ProbeError.invalid("invalid memory descriptor width") }
                for offset in stride(from: 0, to: bytes.count, by: width) {
                    memory.append([
                        "type": Self.read(bytes, offset, 4),
                        "physical_start": Self.hex(Self.read(bytes, offset + 8, 8)),
                        "virtual_start": Self.hex(Self.read(bytes, offset + 16, 8)),
                        "pages": Self.read(bytes, offset + 24, 8),
                        "attributes": Self.hex(Self.read(bytes, offset + 32, 8)),
                    ])
                }
            case 4:
                filename = "serial-device-path-\(record.index).bin"
                serial.append([
                    "index": record.index, "device_path_file": filename,
                    "device_path_hex": bytes.map { String(format: "%02x", $0) }.joined(),
                ])
            case 5:
                filename = "pci-\(record.index).bin"
                let barValues = stride(from: 48, to: 72, by: 4).map { Self.hex(Self.read(bytes, $0, 4)) }
                pci.append([
                    "segment": Self.read(bytes, 0, 8), "bus": Self.read(bytes, 8, 8),
                    "device": Self.read(bytes, 16, 8), "function": Self.read(bytes, 24, 8),
                    "vendor_id": Self.hex(Self.read(bytes, 32, 2)),
                    "device_id": Self.hex(Self.read(bytes, 34, 2)),
                    "command": Self.hex(Self.read(bytes, 36, 2)),
                    "class_code": Self.hex(Self.read(bytes, 41, 3)),
                    "bars_raw": barValues, "interrupt_line": bytes[92], "interrupt_pin": bytes[93],
                    "raw_file": filename,
                ])
            default:
                throw ProbeError.invalid("unknown diagnostic kind")
            }
            try bytes.write(to: directory.appendingPathComponent(filename), options: .withoutOverwriting)
        }
        let summary: [String: Any] = [
            "nonce": nonce, "scope": "uefi-platform-inventory-not-xnu", "acpi_tables": tables,
            "efi_memory_map": memory, "pci_devices": pci, "serial_device_paths": serial,
        ]
        let json = try JSONSerialization.data(withJSONObject: summary, options: [.prettyPrinted, .sortedKeys])
        try json.write(to: directory.appendingPathComponent("platform.json"), options: .withoutOverwriting)
    }

    private static func tableSummary(_ bytes: Data, filename: String) throws -> [String: Any] {
        let signature = String(decoding: bytes.prefix(4), as: UTF8.self)
        var fields: [String: Any] = [
            "signature": signature, "length": bytes.count, "revision": bytes[8],
            "oem_id": String(decoding: bytes[10..<16], as: UTF8.self), "raw_file": filename,
        ]
        switch signature {
        case "APIC":
            guard bytes.count >= 44 else { throw ProbeError.invalid("short MADT") }
            var entries: [[String: Any]] = []
            var offset = 44
            while offset < bytes.count {
                guard offset + 2 <= bytes.count else { throw ProbeError.invalid("truncated MADT header") }
                let kind = bytes[offset]
                let length = Int(bytes[offset + 1])
                guard length >= 2, offset + length <= bytes.count else { throw ProbeError.invalid("bad MADT entry") }
                var entry: [String: Any] = ["type": kind, "length": length]
                if kind == 11 && length >= 80 {
                    entry["cpu_interface_number"] = read(bytes, offset + 4, 4)
                    entry["flags"] = hex(read(bytes, offset + 12, 4))
                    entry["cpu_interface_base"] = hex(read(bytes, offset + 32, 8))
                    entry["gicr_base"] = hex(read(bytes, offset + 60, 8))
                    entry["mpidr"] = hex(read(bytes, offset + 68, 8))
                } else if kind == 12 && length >= 24 {
                    entry["distributor_base"] = hex(read(bytes, offset + 8, 8))
                    entry["version"] = bytes[offset + 20]
                } else if kind == 14 && length >= 16 {
                    entry["redistributor_base"] = hex(read(bytes, offset + 4, 8))
                    entry["redistributor_length"] = hex(read(bytes, offset + 12, 4))
                }
                entries.append(entry)
                offset += length
            }
            fields["entries"] = entries
        case "GTDT":
            guard bytes.count >= 96 else { throw ProbeError.invalid("short GTDT") }
            fields["counter_control_base"] = hex(read(bytes, 36, 8))
            fields["secure_el1_gsiv"] = read(bytes, 48, 4)
            fields["nonsecure_el1_gsiv"] = read(bytes, 56, 4)
            fields["virtual_timer_gsiv"] = read(bytes, 64, 4)
            fields["nonsecure_el2_gsiv"] = read(bytes, 72, 4)
            fields["nonsecure_el1_flags"] = hex(read(bytes, 60, 4))
            fields["virtual_timer_flags"] = hex(read(bytes, 68, 4))
        case "MCFG":
            guard bytes.count >= 44, (bytes.count - 44) % 16 == 0 else { throw ProbeError.invalid("bad MCFG") }
            fields["regions"] = stride(from: 44, to: bytes.count, by: 16).map { offset -> [String: Any] in
                [
                    "base": hex(read(bytes, offset, 8)), "segment": read(bytes, offset + 8, 2),
                    "start_bus": bytes[offset + 10], "end_bus": bytes[offset + 11],
                ]
            }
        case "FACP":
            guard bytes.count >= 132 else { throw ProbeError.invalid("short ARM FADT") }
            let flags = read(bytes, 129, 2)
            fields["arm_boot_architecture"] = hex(flags)
            fields["psci_compliant"] = flags & 1 != 0
            fields["psci_use_hvc"] = flags & 2 != 0
        case "SPCR":
            guard bytes.count >= 62 else { throw ProbeError.invalid("short SPCR") }
            fields["interface_type"] = bytes[36]
            fields["address_space"] = bytes[40]
            fields["base_address"] = hex(read(bytes, 44, 8))
            fields["interrupt_type"] = bytes[52]
            fields["global_interrupt"] = read(bytes, 54, 4)
        default:
            break
        }
        return fields
    }

    private static func read(_ bytes: Data, _ offset: Int, _ count: Int) -> UInt64 {
        (0..<count).reduce(0) { $0 | UInt64(bytes[offset + $1]) << (8 * $1) }
    }
    private static func hex(_ value: UInt64) -> String { String(format: "0x%016llx", value) }
}
