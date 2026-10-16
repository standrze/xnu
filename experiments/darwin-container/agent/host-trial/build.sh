#!/usr/bin/env bash
set -euo pipefail

trial_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
experiment_dir="$(cd "$trial_dir/../.." && pwd)"
build_dir="$trial_dir/.build"
mkdir -p "$build_dir/module-cache"

# Compile only the Foundation/VZ host library sources. No SwiftPM, package
# resolution, network, installed services or frozen CLI build are involved.
swiftc -parse-as-library -swift-version 6 -warnings-as-errors \
  -module-cache-path "$build_dir/module-cache" \
  -emit-library -emit-module -module-name ContainerizationDarwin \
  -emit-module-path "$build_dir/ContainerizationDarwin.swiftmodule" \
  -Xlinker -install_name -Xlinker '@rpath/libContainerizationDarwin.dylib' \
  -framework Virtualization \
  "$experiment_dir"/containerization/Sources/ContainerizationDarwin/*.swift \
  -o "$build_dir/libContainerizationDarwin.dylib"
swiftc -parse-as-library -swift-version 6 -warnings-as-errors \
  -module-cache-path "$build_dir/module-cache" \
  -I "$build_dir" -L "$build_dir" -lContainerizationDarwin \
  -Xlinker -rpath -Xlinker '@executable_path' \
  "$trial_dir/HostTrial.swift" -o "$build_dir/host-trial"
codesign --force --sign - "$build_dir/libContainerizationDarwin.dylib"
codesign --force --sign - \
  --entitlements "$experiment_dir/container/signing/container-darwin-development.entitlements" \
  "$build_dir/host-trial"
codesign --verify --strict "$build_dir/libContainerizationDarwin.dylib"
codesign --verify --strict "$build_dir/host-trial"
printf '%s\n' "$build_dir/host-trial"
