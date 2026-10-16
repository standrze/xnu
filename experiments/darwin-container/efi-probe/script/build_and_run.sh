#!/bin/bash
# SPDX-License-Identifier: BSD-2-Clause
set -euo pipefail

probe_package="$(cd "$(dirname "$0")/.." && pwd)"
probe_repository="$(cd "$probe_package/../../.." && pwd)"
probe_mode="${1:---build-only}"
if [[ "$#" -gt 1 || ( "$probe_mode" != "--build-only" && "$probe_mode" != "--run" ) ]]; then
    echo "usage: $0 [--build-only | --run]" >&2
    exit 2
fi
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
    echo "This probe requires an Apple-silicon macOS host." >&2
    exit 2
fi
probe_zig="$probe_repository/build/rpi5/zig-aarch64-macos-0.16.0/zig"
if [[ ! -x "$probe_zig" ]]; then
    echo "Missing pinned local Zig/LLD: $probe_zig (no download/install attempted)." >&2
    exit 2
fi
probe_directory="$(mktemp -d /private/tmp/darwin-efi-probe.XXXXXX)"
probe_nonce="$(/usr/bin/uuidgen | /usr/bin/tr -d '-' | /usr/bin/tr 'A-F' 'a-f')"
export CLANG_MODULE_CACHE_PATH="$probe_directory/module-cache"
export SWIFT_MODULECACHE_PATH="$probe_directory/module-cache"
echo "Preserved probe artifacts: $probe_directory"
echo "Run nonce: $probe_nonce"

/usr/bin/xcrun clang --target=aarch64-pc-windows-msvc -std=c11 -ffreestanding -fshort-wchar \
    -fno-stack-protector -fno-builtin -mgeneral-regs-only -O2 -Wall -Wextra -Werror \
    "-DPROBE_NONCE=\"$probe_nonce\"" -c "$probe_package/guest/probe.c" -o "$probe_directory/probe.obj"
"$probe_zig" lld-link /subsystem:efi_application /entry:efi_main /nodefaultlib /machine:arm64 \
    /fixed:no /dynamicbase "/out:$probe_directory/BOOTAA64.EFI" "$probe_directory/probe.obj"
/usr/bin/file "$probe_directory/BOOTAA64.EFI"

probe_swift_options=(--package-path "$probe_package" --scratch-path "$probe_directory/swift-build" \
    --cache-path "$probe_directory/swift-cache" --disable-sandbox)
/usr/bin/xcrun swift test "${probe_swift_options[@]}"
/usr/bin/xcrun swift build "${probe_swift_options[@]}" --product efi-probe
probe_binary_directory="$(/usr/bin/xcrun swift build "${probe_swift_options[@]}" --show-bin-path)"
/bin/cp "$probe_binary_directory/efi-probe" "$probe_directory/efi-probe"
/usr/bin/codesign --force --sign - --entitlements "$probe_package/virtualization.entitlements" \
    "$probe_directory/efi-probe"
/usr/bin/codesign --verify --strict "$probe_directory/efi-probe"
"$probe_directory/efi-probe" prepare "$probe_directory" "$probe_nonce" "$probe_directory/BOOTAA64.EFI"
/usr/bin/shasum -a 256 "$probe_package/Package.swift" "$probe_package"/Sources/*/*.swift \
    "$probe_package"/guest/* "$probe_package/virtualization.entitlements" \
    "$probe_package"/script/*.sh > "$probe_directory/source-hashes.txt"
/usr/bin/shasum -a 256 "$probe_directory/BOOTAA64.EFI" "$probe_directory/efi-probe" \
    > "$probe_directory/binary-hashes.txt"

if [[ "$probe_mode" == "--run" ]]; then
    exec /bin/bash "$probe_package/script/run_prepared.sh" "$probe_directory"
fi
echo "Prepared only: no VM was started and no disk was mounted."
echo "To run this exact prepared probe:"
printf '  /bin/bash %q %q\n' "$probe_package/script/run_prepared.sh" "$probe_directory"
