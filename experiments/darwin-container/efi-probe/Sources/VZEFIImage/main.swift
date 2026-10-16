// SPDX-License-Identifier: BSD-2-Clause
import Foundation
import ProbeSupport

do {
    let arguments = Array(CommandLine.arguments.dropFirst())
    guard arguments.count == 2 else {
        throw ProbeError.invalid("usage: vz-efi-image PAYLOAD OUTPUT")
    }
    let payloadURL = URL(fileURLWithPath: arguments[0])
    let outputURL = URL(fileURLWithPath: arguments[1])
    let properties = try payloadURL.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
    guard properties.isRegularFile == true, let size = properties.fileSize,
        size >= 256, size <= ProbeDisk.maximumPayloadByteCount
    else {
        throw ProbeError.invalid("payload must be a regular ARM64 EFI PE file between 256 bytes and 32 MiB")
    }
    let payload = try Data(contentsOf: payloadURL)
    let image = try ProbeDisk.make(payload: payload)
    try image.write(to: outputURL, options: .withoutOverwriting)
    print("VZ_EFI_IMAGE_CREATED \(outputURL.path) bytes=\(image.count) payload_bytes=\(payload.count)")
    print("Packaging only: no VM started and no boot or XNU execution verified.")
} catch {
    FileHandle.standardError.write(Data("vz-efi-image: \(error)\n".utf8))
    exit(1)
}
