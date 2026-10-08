// swift-tools-version: 6.0
// The swift-tools-version declares the minimum version of Swift required to
// build this package.

import PackageDescription

let package = Package(
    name: "ArxivDigest",
    platforms: [
        .iOS(.v17),
        .macOS(.v14),
    ],
    products: [
        // The pure logic layer: models, API client, scoring display.
        // Builds and tests from VS Code via `swift build` / `swift test`.
        // The iOS app itself is an Xcode project (see project.yml) that links
        // this library.
        .library(name: "ArxivDigestCore", targets: ["ArxivDigestCore"]),
    ],
    targets: [
        .target(
            name: "ArxivDigestCore",
            path: "Sources/ArxivDigestCore"
        ),
        .testTarget(
            name: "ArxivDigestCoreTests",
            dependencies: ["ArxivDigestCore"],
            path: "Tests/ArxivDigestCoreTests"
        ),
    ]
)
