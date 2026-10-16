// SPDX-License-Identifier: BSD-2-Clause
import Foundation
import XCTest

@testable import ProbeSupport

final class ProbeSupportTests: XCTestCase {
    func testCRCReferenceVector() {
        XCTAssertEqual(ProbeDisk.crc32(Data("123456789".utf8)), 0xCBF4_3926)
    }

    func testRejectsNonEFIAndWrongArchitecture() throws {
        XCTAssertThrowsError(try ProbeDisk.make(payload: Data(repeating: 0, count: 256)))
        var payload = validPayload()
        payload[0x85] = 0x86
        XCTAssertThrowsError(try ProbeDisk.validatePayload(payload))
    }

    func testImageHasGPTFATAndBlankBoundedResult() throws {
        let disk = try ProbeDisk.make(payload: validPayload())
        XCTAssertEqual(disk.count, ProbeDisk.byteCount)
        XCTAssertEqual(String(data: disk.subdata(in: 512..<520), encoding: .ascii), "EFI PART")
        XCTAssertEqual(disk[510], 0x55)
        XCTAssertEqual(disk[511], 0xAA)
        XCTAssertEqual(try ProbeDisk.result(from: disk), Data(count: 4096))
        XCTAssertEqual(try ProbeDisk.diagnostics(from: disk), Data(count: ProbeDisk.diagnosticByteCount))
        XCTAssertEqual(
            disk.subdata(in: 1024..<(1024 + 16384)),
            disk.subdata(in: (disk.count - 33 * 512)..<(disk.count - 512)))
    }

    func testRejectsBlankAndTruncatedDiagnosticRecords() throws {
        let nonce = "0123456789abcdef0123456789abcdef"
        XCTAssertThrowsError(
            try ProbeDiagnostics(bytes: Data(count: ProbeDisk.diagnosticByteCount), expectedNonce: nonce))
        var bytes = Data(count: ProbeDisk.diagnosticByteCount)
        bytes.replaceSubrange(0..<8, with: "EFIDIAG2".utf8)
        bytes[8] = 2
        bytes[12] = 120
        bytes.replaceSubrange(16..<48, with: nonce.utf8)
        bytes[48] = 1
        bytes[52] = 1
        bytes[64] = 3
        bytes[72] = 40
        XCTAssertNoThrow(try ProbeDiagnostics(bytes: bytes, expectedNonce: nonce))
        bytes[72] = 41
        XCTAssertThrowsError(try ProbeDiagnostics(bytes: bytes, expectedNonce: nonce))
        bytes[72] = 40
        bytes[52] = 0
        XCTAssertThrowsError(try ProbeDiagnostics(bytes: bytes, expectedNonce: nonce))
    }

    func testPackagesMaximumEmbeddedPayloadWithoutOverlappingOutputs() throws {
        var payload = validPayload()
        payload.append(Data(count: ProbeDisk.maximumPayloadByteCount - payload.count))
        payload[payload.count - 1] = 0xAB
        let image = try ProbeDisk.make(payload: payload)
        let dataOffset = (2048 + 1 + 256 + 32) * 512
        let payloadOffset = dataOffset + 2 * 2048
        XCTAssertEqual(image[payloadOffset + payload.count - 1], 0xAB)
        let finalCluster = 4 + payload.count / 2048 - 1
        let finalFATEntry = (2048 + 1) * 512 + finalCluster * 2
        XCTAssertEqual(image[finalFATEntry], 0xFF)
        XCTAssertEqual(image[finalFATEntry + 1], 0xFF)
        XCTAssertEqual(try ProbeDisk.result(from: image), Data(count: 4096))
        XCTAssertEqual(try ProbeDisk.diagnostics(from: image), Data(count: ProbeDisk.diagnosticByteCount))
        payload.append(0)
        XCTAssertThrowsError(try ProbeDisk.validatePayload(payload))
    }

    func testRejectsCorruptResultChain() throws {
        var disk = try ProbeDisk.make(payload: validPayload())
        let root = (2048 + 1 + 256) * 512
        disk[root + 32 + 26] = 0
        disk[root + 32 + 27] = 0
        XCTAssertThrowsError(try ProbeDisk.result(from: disk))
    }

    func testNonceAndReportChecks() throws {
        let nonce = "0123456789abcdef0123456789abcdef"
        XCTAssertNoThrow(try ProbeDisk.validateNonce(nonce))
        XCTAssertThrowsError(try ProbeDisk.validateNonce("../bad"))
        let content = """
            DARWIN_EFI_PROBE_V1
            nonce=\(nonce)
            scope=uefi-payload-only-not-xnu
            current_el=0x0000000000000001
            counter_hz=0x00000000016e3600
            memory_map_status=0x0000000000000000
            memory_descriptor_count=0x0000000000000008
            report_complete=1
            END_DARWIN_EFI_PROBE_V1
            """
        let report = Data(content.padding(toLength: 4096, withPad: " ", startingAt: 0).utf8)
        XCTAssertNoThrow(try ProbeReport(bytes: report, expectedNonce: nonce))
        XCTAssertThrowsError(try ProbeReport(bytes: report, expectedNonce: String(repeating: "f", count: 32)))
        XCTAssertThrowsError(try ProbeReport(bytes: Data(count: 4096), expectedNonce: nonce))
    }

    private func validPayload() -> Data {
        var data = Data(count: 256)
        data[0] = 0x4D
        data[1] = 0x5A
        data[60] = 0x80
        data[0x80] = 0x50
        data[0x81] = 0x45
        data[0x84] = 0x64
        data[0x85] = 0xAA
        data[0x98] = 0x0B
        data[0x99] = 0x02
        data[0xDC] = 10
        return data
    }
}
