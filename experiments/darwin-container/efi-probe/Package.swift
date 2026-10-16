// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "EFIProbe",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "efi-probe", targets: ["EFIProbe"]),
        .executable(name: "vz-efi-image", targets: ["VZEFIImage"]),
    ],
    targets: [
        .target(name: "ProbeSupport"),
        .executableTarget(name: "EFIProbe", dependencies: ["ProbeSupport"]),
        .executableTarget(name: "VZEFIImage", dependencies: ["ProbeSupport"]),
        .testTarget(name: "ProbeSupportTests", dependencies: ["ProbeSupport"]),
    ],
    swiftLanguageModes: [.v5]
)
