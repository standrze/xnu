// SPDX-License-Identifier: BSD-2-Clause
import CryptoKit
import Foundation
import ProbeSupport

enum ProbeCommand {
    static func execute(_ arguments: [String]) throws {
        guard arguments.count >= 3 else { throw usage }
        let command = arguments[0]
        let directory = try outputDirectory(arguments[1])
        let nonce = arguments[2]
        try ProbeDisk.validateNonce(nonce)
        switch command {
        case "prepare":
            guard arguments.count == 4 else { throw usage }
            let payload = try Data(contentsOf: URL(fileURLWithPath: arguments[3]))
            guard payload.range(of: Data(nonce.utf8)) != nil else {
                throw ProbeError.invalid("payload does not contain this run nonce")
            }
            let disk = try ProbeDisk.make(payload: payload)
            try disk.write(to: directory.appendingPathComponent("disk.img"), options: .withoutOverwriting)
            try writeJSON(
                [
                    "status": "prepared-not-booted",
                    "nonce": nonce,
                    "scope": "uefi-payload-only-not-xnu",
                    "payload_sha256": hash(payload),
                    "prepared_disk_sha256": hash(disk),
                ], to: directory.appendingPathComponent("prepared.json"))
            print("EFI_PROBE_PREPARED \(directory.path)")
        case "run":
            guard arguments.count == 4, let seconds = Int(arguments[3]), (5...45).contains(seconds) else { throw usage }
            let before = try checkedDisk(directory)
            guard try ProbeDisk.result(from: before).allSatisfy({ $0 == 0 }),
                try ProbeDisk.diagnostics(from: before).allSatisfy({ $0 == 0 })
            else {
                throw ProbeError.invalid("result file is not blank; use a fresh run directory")
            }
            let prepared = try JSONDecoder().decode(
                [String: String].self,
                from: Data(contentsOf: directory.appendingPathComponent("prepared.json")))
            guard prepared["nonce"] == nonce, prepared["prepared_disk_sha256"] == hash(before) else {
                throw ProbeError.invalid("prepared image identity changed")
            }
            try writeJSON(
                ["nonce": nonce, "status": "starting", "start": timestamp()],
                to: directory.appendingPathComponent("started.json"))
            do {
                try VMRunner().run(directory: directory, seconds: seconds)
                try writeJSON(
                    ["nonce": nonce, "status": "guest-stopped", "end": timestamp()],
                    to: directory.appendingPathComponent("stopped.json"))
            } catch {
                try? writeJSON(
                    [
                        "nonce": nonce, "status": "failed", "error": String(describing: error),
                        "end": timestamp(),
                    ], to: directory.appendingPathComponent("failed.json"))
                throw error
            }
            try verify(directory: directory, nonce: nonce)
        case "verify":
            guard arguments.count == 3 else { throw usage }
            try verify(directory: directory, nonce: nonce)
        default:
            throw usage
        }
    }

    private static func verify(directory: URL, nonce: String) throws {
        let stopped = try JSONDecoder().decode(
            [String: String].self,
            from: Data(contentsOf: directory.appendingPathComponent("stopped.json")))
        guard stopped["nonce"] == nonce, stopped["status"] == "guest-stopped" else {
            throw ProbeError.invalid("no successful guest-stop record for this nonce")
        }
        let disk = try checkedDisk(directory)
        let raw = try ProbeDisk.result(from: disk)
        let report = try ProbeReport(bytes: raw, expectedNonce: nonce)
        guard report.fields["diagnostic_errors"] == "0x0000000000000000",
            report.fields["diagnostic_write_status"] == "0x0000000000000000"
        else {
            throw ProbeError.invalid("guest diagnostic capture/write failed")
        }
        let diagnosticBytes = try ProbeDisk.diagnostics(from: disk)
        let diagnostics = try ProbeDiagnostics(bytes: diagnosticBytes, expectedNonce: nonce)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let json = try encoder.encode(report)
        let reportURL = directory.appendingPathComponent("verified.json")
        if FileManager.default.fileExists(atPath: reportURL.path) {
            guard try Data(contentsOf: reportURL) == json else {
                throw ProbeError.invalid("existing verification differs")
            }
        } else {
            try diagnostics.write(to: directory.appendingPathComponent("diagnostics"), report: report)
            try diagnosticBytes.write(
                to: directory.appendingPathComponent("diagnostics.bin"), options: .withoutOverwriting)
            try json.write(to: reportURL, options: .withoutOverwriting)
            try raw.write(to: directory.appendingPathComponent("guest-report.txt"), options: .withoutOverwriting)
            try writeJSON(
                ["disk_sha256": hash(disk), "report_sha256": hash(raw)],
                to: directory.appendingPathComponent("result-hashes.json"))
        }
        print("EFI_PROBE_PAYLOAD_PASSED nonce=\(nonce) scope=uefi-payload-only-not-xnu")
        print(String(decoding: json, as: UTF8.self))
    }

    private static func outputDirectory(_ path: String) throws -> URL {
        let url = URL(fileURLWithPath: path, isDirectory: true).resolvingSymlinksInPath()
        let parent = url.deletingLastPathComponent().path
        let temporaryRoot = URL(fileURLWithPath: "/private/tmp", isDirectory: true).resolvingSymlinksInPath().path
        guard parent == temporaryRoot, url.lastPathComponent.hasPrefix("darwin-efi-probe."),
            try url.resourceValues(forKeys: [.isDirectoryKey]).isDirectory == true
        else {
            throw ProbeError.invalid("output must be an existing mktemp directory /private/tmp/darwin-efi-probe.XXXXXX")
        }
        return url
    }

    private static func checkedDisk(_ directory: URL) throws -> Data {
        let url = directory.appendingPathComponent("disk.img")
        let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        guard values.isRegularFile == true, values.isSymbolicLink != true, values.fileSize == ProbeDisk.byteCount,
            (attributes[.referenceCount] as? NSNumber)?.intValue == 1
        else {
            throw ProbeError.invalid("refusing a non-regular, linked or wrong-size VM disk")
        }
        return try Data(contentsOf: url)
    }

    private static func writeJSON(_ value: [String: String], to url: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(value).write(to: url, options: .withoutOverwriting)
    }

    private static func hash(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
    private static func timestamp() -> String { ISO8601DateFormatter().string(from: Date()) }
    private static var usage: ProbeError {
        .invalid("usage: efi-probe prepare DIR NONCE PAYLOAD | run DIR NONCE SECONDS | verify DIR NONCE")
    }
}
