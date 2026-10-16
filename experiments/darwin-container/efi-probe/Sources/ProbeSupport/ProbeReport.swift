// SPDX-License-Identifier: BSD-2-Clause
import Foundation

public struct ProbeReport: Codable {
    public let scope: String
    public let nonce: String
    public let fields: [String: String]

    public init(bytes: Data, expectedNonce: String) throws {
        try ProbeDisk.validateNonce(expectedNonce)
        guard bytes.count == 4096, let text = String(data: bytes, encoding: .utf8) else {
            throw ProbeError.invalid("invalid report encoding or length")
        }
        let lines = text.trimmingCharacters(in: .whitespacesAndNewlines).split(separator: "\n").map(String.init)
        guard lines.first == "DARWIN_EFI_PROBE_V1", lines.last == "END_DARWIN_EFI_PROBE_V1" else {
            throw ProbeError.invalid("no complete guest report")
        }
        var parsed: [String: String] = [:]
        for line in lines.dropFirst().dropLast() {
            let parts = line.split(separator: "=", maxSplits: 1).map(String.init)
            guard parts.count == 2, parsed[parts[0]] == nil else { throw ProbeError.invalid("malformed report field") }
            parsed[parts[0]] = parts[1]
        }
        guard parsed["nonce"] == expectedNonce, parsed["scope"] == "uefi-payload-only-not-xnu",
            parsed["report_complete"] == "1", parsed["memory_map_status"] == "0x0000000000000000",
            let frequency = parsed["counter_hz"], (Self.number(frequency) ?? 0) > 0,
            let el = parsed["current_el"], let parsedEL = Self.number(el), [UInt64(1), UInt64(2)].contains(parsedEL),
            let count = parsed["memory_descriptor_count"], Self.number(count) ?? 0 > 0
        else {
            throw ProbeError.invalid("guest report failed identity/inventory checks")
        }
        self.scope = "uefi-payload-only-not-xnu"
        self.nonce = expectedNonce
        self.fields = parsed
    }

    private static func number(_ value: String) -> UInt64? {
        guard value.hasPrefix("0x"), value.count == 18 else { return nil }
        return UInt64(value.dropFirst(2), radix: 16)
    }
}
