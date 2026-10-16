//===----------------------------------------------------------------------===//
// Copyright © 2026 the Darwin container project authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//   https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//===----------------------------------------------------------------------===//

import ContainerizationDarwin
import Darwin
import Foundation

/// Explicitly opt-in VZ trials for direct argv launch failure and public API task cancellation.
@main
struct HostTrial {
    static let usage = """
        Usage: host-trial missing-exec|cancel-task --boot-disk PATH --output-dir FRESH_PATH
          [--variable-store PATH] [--timeout-seconds 30] [--cancel-after-seconds 1]
        Native checks without a VM: host-trial --self-test [EXISTING_SERIAL_BIN]

        missing-exec executes direct argv ["/this-path-is-missing"].
        cancel-task executes direct argv ["/bin/agent-escape"], then cancels the public session
        task after STARTED is observed in raw serial evidence and the requested delay elapses.
        This launches an actual VM only when given a mode and explicit paths.
        """

    @MainActor
    static func main() async {
        let arguments = Array(CommandLine.arguments.dropFirst())
        if arguments.isEmpty || arguments == ["--help"] {
            print(usage)
            return
        }
        do {
            if arguments.first == "--self-test" {
                guard arguments.count <= 2 else { throw DarwinGuestSessionError.invalid("--self-test accepts at most one existing serial path") }
                try selfTest(existingSerialPath: arguments.count == 2 ? arguments[1] : nil)
                return
            }
            let options = try Options(arguments)
            let command = try DarwinAgentCommand(arguments: [
                options.mode == "missing-exec" ? "/this-path-is-missing" : "/bin/agent-escape"
            ])
            let session = DarwinGuestSession()
            let task = Task { @MainActor in
                try await session.run(
                    bootDiskURL: URL(fileURLWithPath: options.bootDisk),
                    outputDirectory: URL(fileURLWithPath: options.outputDirectory),
                    variableStoreTemplateURL: options.variableStore.map { URL(fileURLWithPath: $0) },
                    timeoutSeconds: options.timeoutSeconds,
                    streamOutput: false,
                    agentCommands: [command]
                )
            }
            let cancellation: Task<Void, Never>?
            if options.mode == "cancel-task" {
                cancellation = Task { @MainActor in
                    let deadline = ProcessInfo.processInfo.systemUptime + Double(options.timeoutSeconds)
                    let serialURL = URL(fileURLWithPath: options.outputDirectory).appendingPathComponent(
                        "serial.bin")
                    while !Task.isCancelled && ProcessInfo.processInfo.systemUptime < deadline {
                        // This read controls trial timing only. The session independently validates
                        // CRC, sequence, session ID and PID before accepting STARTED as evidence.
                        if let bytes = try? Data(contentsOf: serialURL), observedStarted(bytes) {
                            do { try await Task.sleep(for: .seconds(options.cancelAfterSeconds)) } catch {
                                return
                            }
                            task.cancel()
                            return
                        }
                        do { try await Task.sleep(for: .milliseconds(50)) } catch { return }
                    }
                }
            } else {
                cancellation = nil
            }
            defer { cancellation?.cancel() }
            let result = try await task.value
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try FileHandle.standardOutput.write(contentsOf: encoder.encode(result) + Data([10]))
            // A deliberate exec failure/cancellation is a completed trial, not successful execution.
            let complete =
                result.started && result.guestStopped && result.agent?.complete == true
                && result.agent?.protocolValid == true
            let observed: Bool
            if options.mode == "missing-exec" {
                observed =
                    result.termination == .guestStopped && result.error == nil
                    && result.agent?.commands.first?.exitStatus == 127
            } else {
                observed =
                    result.termination == .interrupted
                    && result.agent?.commands.first?.cancellationRequested == true
                    && result.agent?.commands.first?.cancellationAccepted == true
                    && result.agent?.commands.first?.cleanupVerified == true
            }
            if !complete || !observed { exit(1) }
        } catch {
            try? FileHandle.standardError.write(contentsOf: Data("host-trial: \(error)\n".utf8))
            exit(1)
        }
    }

    private static func observedStarted(_ bytes: Data) -> Bool {
        var start = bytes.startIndex
        for end in bytes.indices where bytes[end] == 0x0a {
            var line = bytes[start..<end]
            start = bytes.index(after: end)
            while line.last == 0x0d { line = line.dropLast() }
            guard let text = String(data: line, encoding: .ascii) else { continue }
            let fields = text.split(separator: "|", omittingEmptySubsequences: false)
            if fields.count == 9 && fields[0] == "DGA1" && fields[1] == "G" && fields[3] == "00000001"
                && fields[5] == "STARTED"
            {
                return true
            }
        }
        return false
    }

    private static func selfTest(existingSerialPath: String?) throws {
        // Cross-language golden guest_started vector from ../wire-vectors.json.
        let record = "DGA1|G|00112233445566778899aabbccddeeff|00000001|00000002|STARTED|0004|00000003|58b837d4"
        var checks = 0
        func expect(_ condition: Bool, _ message: String) throws {
            guard condition else { throw DarwinGuestSessionError.invalid("native self-test: \(message)") }
            checks += 1
        }
        for ending in ["\n", "\r\n", "\r\r\n"] {
            let fixture = Data(("kernel noise" + ending + "DARWIN:AGENT:READY:1" + ending + record + ending).utf8)
            for boundary in 0...fixture.count {
                var polledBytes = Data(fixture.prefix(boundary))
                try expect(observedStarted(polledBytes) == (boundary == fixture.count), "incomplete record accepted at byte \(boundary)")
                polledBytes.append(contentsOf: fixture.dropFirst(boundary))
                try expect(observedStarted(polledBytes), "fragmented \(ending.debugDescription) input was missed")
            }
        }
        for noise in [
            record, record + "\r", "prompt " + record + "\r\n",
            record.replacingOccurrences(of: "|G|", with: "|H|") + "\r\n",
            record.replacingOccurrences(of: "00000001|00000002", with: "00000002|00000002") + "\r\n",
        ] {
            try expect(!observedStarted(Data(noise.utf8)), "noise, host echo or incomplete line accepted")
        }
        if let existingSerialPath {
            try expect(observedStarted(Data(contentsOf: URL(fileURLWithPath: existingSerialPath))), "existing serial file has no complete STARTED record")
        }
        print("Native STARTED timing checks passed: \(checks); no VM launched")
    }

    private struct Options {
        let mode: String
        let bootDisk: String
        let outputDirectory: String
        let variableStore: String?
        let timeoutSeconds: Int
        let cancelAfterSeconds: Int

        init(_ arguments: [String]) throws {
            guard let mode = arguments.first, ["missing-exec", "cancel-task"].contains(mode),
                arguments.count % 2 == 1
            else { throw Self.invalid("expected a trial mode and option/value pairs") }
            var values: [String: String] = [:]
            for index in stride(from: 1, to: arguments.count, by: 2) {
                let key = arguments[index]
                guard
                    [
                        "--boot-disk", "--output-dir", "--variable-store", "--timeout-seconds",
                        "--cancel-after-seconds",
                    ].contains(key),
                    values[key] == nil, !arguments[index + 1].isEmpty
                else { throw Self.invalid("unknown, repeated or empty option \(key)") }
                values[key] = arguments[index + 1]
            }
            guard let bootDisk = values["--boot-disk"], let outputDirectory = values["--output-dir"]
            else { throw Self.invalid("explicit --boot-disk and --output-dir are required") }
            guard let timeoutSeconds = Int(values["--timeout-seconds"] ?? "30"),
                (1...3600).contains(timeoutSeconds),
                let cancelAfterSeconds = Int(values["--cancel-after-seconds"] ?? "1"),
                (1...3600).contains(cancelAfterSeconds)
            else { throw Self.invalid("deadlines must be integers from 1 through 3600") }
            self.mode = mode
            self.bootDisk = bootDisk
            self.outputDirectory = outputDirectory
            variableStore = values["--variable-store"]
            self.timeoutSeconds = timeoutSeconds
            self.cancelAfterSeconds = cancelAfterSeconds
        }

        private static func invalid(_ message: String) -> DarwinGuestSessionError { .invalid(message) }
    }
}
