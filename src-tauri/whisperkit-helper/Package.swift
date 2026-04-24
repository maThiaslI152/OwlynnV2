// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "whisperkit-helper",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "whisperkit-helper", targets: ["whisperkit-helper"])
    ],
    dependencies: [
        .package(url: "https://github.com/argmaxinc/WhisperKit", from: "0.18.0")
    ],
    targets: [
        .executableTarget(
            name: "whisperkit-helper",
            dependencies: ["WhisperKit"],
            path: "Sources",
            resources: [
                .copy("Resources/AthenaSoundClassifier.mlmodelc")
            ]
        )
    ]
)
