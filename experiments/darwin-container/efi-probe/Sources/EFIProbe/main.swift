// SPDX-License-Identifier: BSD-2-Clause
import Foundation

do {
    try ProbeCommand.execute(Array(CommandLine.arguments.dropFirst()))
} catch {
    FileHandle.standardError.write(Data("efi-probe: \(error)\n".utf8))
    exit(1)
}
