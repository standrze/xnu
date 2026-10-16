// SPDX-License-Identifier: BSD-2-Clause
import Foundation

public enum ProbeError: Error, CustomStringConvertible {
    case invalid(String)

    public var description: String {
        switch self {
        case .invalid(let reason): return reason
        }
    }
}

/// A fixed, disposable 64-MiB GPT/FAT16 image. Never reads or writes a host device.
public enum ProbeDisk {
    public static let byteCount = 64 * 1024 * 1024
    public static let diagnosticByteCount = 256 * 1024
    public static let maximumPayloadByteCount = 32 * 1024 * 1024
    private static let sectorSize = 512
    private static let sectorCount = byteCount / sectorSize
    private static let partitionStart = 2048
    private static let partitionSectors = 126_976
    private static let fatSectors = 128
    private static let rootSectors = 32
    private static let clusterBytes = 2048
    private static let rootOffset = (partitionStart + 1 + 2 * fatSectors) * sectorSize
    private static let dataOffset = rootOffset + rootSectors * sectorSize

    public static func validateNonce(_ nonce: String) throws {
        guard nonce.utf8.count == 32, nonce.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) })
        else {
            throw ProbeError.invalid("nonce must be 32 lowercase hexadecimal characters")
        }
    }

    /// Produces an image with an EFI application and an existing blank RESULT.TXT.
    public static func make(payload: Data) throws -> Data {
        try validatePayload(payload)
        let payloadClusters = (payload.count + clusterBytes - 1) / clusterBytes
        let resultCluster = 4 + payloadClusters
        let diagnosticCluster = resultCluster + 2
        let diagnosticClusters = diagnosticByteCount / clusterBytes
        let availableClusters = (partitionSectors - 1 - 2 * fatSectors - rootSectors) * sectorSize / clusterBytes
        guard diagnosticCluster + diagnosticClusters <= availableClusters + 2,
            (diagnosticCluster + diagnosticClusters) * 2 <= fatSectors * sectorSize
        else {
            throw ProbeError.invalid("EFI payload and output files exceed fixed FAT16 capacity")
        }
        var disk = Data(count: byteCount)

        // Protective MBR and two independently checksummed GPT headers/entry arrays.
        disk[446 + 4] = 0xEE
        write(1, to: &disk, at: 446 + 8, bytes: 4)
        write(UInt64(sectorCount - 1), to: &disk, at: 446 + 12, bytes: 4)
        disk[510] = 0x55
        disk[511] = 0xAA
        var entries = Data(count: 128 * 128)
        entries.replaceSubrange(
            0..<16,
            with: [
                0x28, 0x73, 0x2A, 0xC1, 0x1F, 0xF8, 0xD2, 0x11,
                0xBA, 0x4B, 0x00, 0xA0, 0xC9, 0x3E, 0xC9, 0x3B,
            ])
        entries.replaceSubrange(16..<32, with: uuidBytes())
        write(UInt64(partitionStart), to: &entries, at: 32, bytes: 8)
        write(UInt64(partitionStart + partitionSectors - 1), to: &entries, at: 40, bytes: 8)
        for (index, code) in "EFI PROBE".utf16.enumerated() {
            write(UInt64(code), to: &entries, at: 56 + index * 2, bytes: 2)
        }
        disk.replaceSubrange(1024..<(1024 + entries.count), with: entries)
        let backupEntries = (sectorCount - 33) * sectorSize
        disk.replaceSubrange(backupEntries..<(backupEntries + entries.count), with: entries)
        let diskID = uuidBytes()
        let entriesCRC = crc32(entries)
        installGPT(in: &disk, current: 1, other: sectorCount - 1, entries: 2, id: diskID, entriesCRC: entriesCRC)
        installGPT(
            in: &disk, current: sectorCount - 1, other: 1, entries: sectorCount - 33,
            id: diskID, entriesCRC: entriesCRC)

        let boot = partitionStart * sectorSize
        disk.replaceSubrange(boot..<(boot + 3), with: [0xEB, 0x3C, 0x90])
        putASCII("EFIPROBE", in: &disk, at: boot + 3)
        write(512, to: &disk, at: boot + 11, bytes: 2)
        disk[boot + 13] = 4
        write(1, to: &disk, at: boot + 14, bytes: 2)
        disk[boot + 16] = 2
        write(512, to: &disk, at: boot + 17, bytes: 2)
        disk[boot + 21] = 0xF8
        write(UInt64(fatSectors), to: &disk, at: boot + 22, bytes: 2)
        write(32, to: &disk, at: boot + 24, bytes: 2)
        write(64, to: &disk, at: boot + 26, bytes: 2)
        write(UInt64(partitionStart), to: &disk, at: boot + 28, bytes: 4)
        write(UInt64(partitionSectors), to: &disk, at: boot + 32, bytes: 4)
        disk[boot + 36] = 0x80
        disk[boot + 38] = 0x29
        write(0x4546_4950, to: &disk, at: boot + 39, bytes: 4)
        putASCII("EFI_PROBE  ", in: &disk, at: boot + 43)
        putASCII("FAT16   ", in: &disk, at: boot + 54)
        disk[boot + 510] = 0x55
        disk[boot + 511] = 0xAA

        var fat = Data(count: fatSectors * sectorSize)
        write(0xFFF8, to: &fat, at: 0, bytes: 2)
        write(0xFFFF, to: &fat, at: 2, bytes: 2)
        write(0xFFFF, to: &fat, at: 4, bytes: 2)
        write(0xFFFF, to: &fat, at: 6, bytes: 2)
        for cluster in 4..<resultCluster {
            write(UInt64(cluster + 1 == resultCluster ? 0xFFFF : cluster + 1), to: &fat, at: cluster * 2, bytes: 2)
        }
        write(UInt64(resultCluster + 1), to: &fat, at: resultCluster * 2, bytes: 2)
        write(0xFFFF, to: &fat, at: (resultCluster + 1) * 2, bytes: 2)
        for cluster in diagnosticCluster..<(diagnosticCluster + diagnosticClusters) {
            let next = cluster + 1 == diagnosticCluster + diagnosticClusters ? 0xFFFF : cluster + 1
            write(UInt64(next), to: &fat, at: cluster * 2, bytes: 2)
        }
        for copy in 0..<2 {
            let offset = (partitionStart + 1 + copy * fatSectors) * sectorSize
            disk.replaceSubrange(offset..<(offset + fat.count), with: fat)
        }
        directoryEntry("EFI        ", attributes: 0x10, cluster: 2, size: 0, in: &disk, at: rootOffset)
        directoryEntry(
            "RESULT  TXT", attributes: 0x20, cluster: resultCluster, size: 4096,
            in: &disk, at: rootOffset + 32)
        directoryEntry(
            "DIAG    BIN", attributes: 0x20, cluster: diagnosticCluster, size: diagnosticByteCount,
            in: &disk, at: rootOffset + 64)
        let efiDirectory = clusterOffset(2)
        directoryEntry(".          ", attributes: 0x10, cluster: 2, size: 0, in: &disk, at: efiDirectory)
        directoryEntry("..         ", attributes: 0x10, cluster: 0, size: 0, in: &disk, at: efiDirectory + 32)
        directoryEntry("BOOT       ", attributes: 0x10, cluster: 3, size: 0, in: &disk, at: efiDirectory + 64)
        let bootDirectory = clusterOffset(3)
        directoryEntry(".          ", attributes: 0x10, cluster: 3, size: 0, in: &disk, at: bootDirectory)
        directoryEntry("..         ", attributes: 0x10, cluster: 2, size: 0, in: &disk, at: bootDirectory + 32)
        directoryEntry(
            "BOOTAA64EFI", attributes: 0x20, cluster: 4, size: payload.count,
            in: &disk, at: bootDirectory + 64)
        let payloadOffset = clusterOffset(4)
        disk.replaceSubrange(payloadOffset..<(payloadOffset + payload.count), with: payload)
        return disk
    }

    /// Reads only the bounded result-file chain from this fixed-format image.
    public static func result(from disk: Data) throws -> Data {
        try file(from: disk, shortName: "RESULT  TXT", expectedSize: 4096)
    }

    public static func diagnostics(from disk: Data) throws -> Data {
        try file(from: disk, shortName: "DIAG    BIN", expectedSize: diagnosticByteCount)
    }

    private static func file(from disk: Data, shortName: String, expectedSize: Int) throws -> Data {
        guard disk.count == byteCount, disk[510] == 0x55, disk[511] == 0xAA else {
            throw ProbeError.invalid("unexpected probe image geometry")
        }
        let expectedName = Data(shortName.utf8)
        var entry: Int?
        for index in 0..<512 {
            let offset = rootOffset + index * 32
            if disk.subdata(in: offset..<(offset + 11)) == expectedName {
                guard entry == nil, disk[offset + 11] & 0x18 == 0 else {
                    throw ProbeError.invalid("ambiguous result file")
                }
                entry = offset
            }
        }
        guard let entry, read(disk, at: entry + 28, bytes: 4) == expectedSize else {
            throw ProbeError.invalid("missing or resized result file")
        }
        var cluster = Int(read(disk, at: entry + 26, bytes: 2))
        var visited = Set<Int>()
        var output = Data()
        let fat = (partitionStart + 1) * sectorSize
        let clusters = expectedSize / clusterBytes
        for index in 0..<clusters {
            guard cluster >= 2, cluster < 31_673, visited.insert(cluster).inserted else {
                throw ProbeError.invalid("invalid result cluster chain")
            }
            let offset = clusterOffset(cluster)
            output.append(disk.subdata(in: offset..<(offset + clusterBytes)))
            let next = Int(read(disk, at: fat + cluster * 2, bytes: 2))
            if index == clusters - 1 {
                guard next >= 0xFFF8 else { throw ProbeError.invalid("unterminated result chain") }
            } else {
                cluster = next
            }
        }
        return output
    }

    public static func validatePayload(_ payload: Data) throws {
        guard payload.count >= 256, payload.count <= maximumPayloadByteCount,
            payload[0] == 0x4D, payload[1] == 0x5A
        else {
            throw ProbeError.invalid("expected bounded PE/COFF EFI application")
        }
        let pe = Int(read(payload, at: 60, bytes: 4))
        guard pe >= 64, pe <= payload.count - 96,
            read(payload, at: pe, bytes: 4) == 0x4550,
            read(payload, at: pe + 4, bytes: 2) == 0xAA64,
            read(payload, at: pe + 24, bytes: 2) == 0x20B,
            read(payload, at: pe + 24 + 68, bytes: 2) == 10
        else {
            throw ProbeError.invalid("payload must be ARM64 PE32+ EFI application")
        }
    }

    private static func installGPT(
        in disk: inout Data, current: Int, other: Int, entries: Int,
        id: [UInt8], entriesCRC: UInt32
    ) {
        var header = Data(count: sectorSize)
        putASCII("EFI PART", in: &header, at: 0)
        write(0x10000, to: &header, at: 8, bytes: 4)
        write(92, to: &header, at: 12, bytes: 4)
        write(UInt64(current), to: &header, at: 24, bytes: 8)
        write(UInt64(other), to: &header, at: 32, bytes: 8)
        write(34, to: &header, at: 40, bytes: 8)
        write(UInt64(sectorCount - 34), to: &header, at: 48, bytes: 8)
        header.replaceSubrange(56..<72, with: id)
        write(UInt64(entries), to: &header, at: 72, bytes: 8)
        write(128, to: &header, at: 80, bytes: 4)
        write(128, to: &header, at: 84, bytes: 4)
        write(UInt64(entriesCRC), to: &header, at: 88, bytes: 4)
        write(UInt64(crc32(header.prefix(92))), to: &header, at: 16, bytes: 4)
        let offset = current * sectorSize
        disk.replaceSubrange(offset..<(offset + sectorSize), with: header)
    }

    private static func directoryEntry(
        _ name: String, attributes: UInt8, cluster: Int, size: Int,
        in disk: inout Data, at offset: Int
    ) {
        putASCII(name, in: &disk, at: offset)
        disk[offset + 11] = attributes
        write(0x21, to: &disk, at: offset + 24, bytes: 2)  // 1980-01-01, valid FAT date.
        write(UInt64(cluster), to: &disk, at: offset + 26, bytes: 2)
        write(UInt64(size), to: &disk, at: offset + 28, bytes: 4)
    }

    private static func clusterOffset(_ cluster: Int) -> Int { dataOffset + (cluster - 2) * clusterBytes }
    private static func putASCII(_ text: String, in data: inout Data, at offset: Int) {
        data.replaceSubrange(offset..<(offset + text.utf8.count), with: text.utf8)
    }
    private static func write(_ value: UInt64, to data: inout Data, at offset: Int, bytes: Int) {
        for index in 0..<bytes { data[offset + index] = UInt8(truncatingIfNeeded: value >> (8 * index)) }
    }
    private static func read(_ data: Data, at offset: Int, bytes: Int) -> UInt64 {
        (0..<bytes).reduce(0) { $0 | UInt64(data[offset + $1]) << (8 * $1) }
    }
    private static func uuidBytes() -> [UInt8] {
        var value = UUID().uuid
        return withUnsafeBytes(of: &value) { Array($0) }
    }
    public static func crc32(_ data: Data) -> UInt32 {
        var crc: UInt32 = 0xFFFF_FFFF
        for byte in data {
            crc ^= UInt32(byte)
            for _ in 0..<8 { crc = (crc >> 1) ^ (crc & 1 == 1 ? 0xEDB8_8320 : 0) }
        }
        return ~crc
    }
}
