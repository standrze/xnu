# Pi 5 Gate 0 tools

Requires macOS, Xcode and Python 3.12 or newer. Run from the repository root:

```sh
python3 tools/rpi5/rpi5.py doctor
python3 tools/rpi5/rpi5.py bootstrap
python3 tools/rpi5/rpi5.py build --target exporthdrs
python3 tools/rpi5/rpi5.py firehose
python3 tools/rpi5/rpi5.py build
python3 -m unittest discover -s tools/rpi5/tests -v
```

The canonical toolchain is locked in `inputs.lock.json` (Xcode 26.6 / 17F113,
SDK 26.5). The host now has Xcode 27.0 / 27A266a, SDK 27.0. Do not use
`--allow-toolchain-mismatch` against the canonical `build/rpi5` workspace: it
will reject the preserved SDK, and that provenance must remain intact. For an
isolated exploratory qualification, append `--profile xcode27` to every
command above. This requires the observed 27.0 installation and uses only
`build/rpi5-xcode27` for SDK, dependencies, objects and run manifests. The
result stays explicitly noncanonical until separately audited and hardware
tested. A profile cannot silently relabel the Xcode 26.6 build.

`bootstrap --cache build/rpi5/downloads` can reuse downloaded `availability.tar.gz` and
`libdispatch.tar.gz`; every archive must match its locked SHA-256. Otherwise
bootstrap downloads the pinned archives via HTTPS. It clones the public SDK
into `build/rpi5/sdk` and uses AvailabilityVersions' own generator to install
availability headers/tooling. This source generator needs no CMake or Ninja.
The separate `firehose` command builds the matching single-source kernel logging
archive using the generated DEVELOPMENT configuration and exported XNU headers.
Run it after exporthdrs and again whenever the kernel configuration changes.
It preserves input hashes, compiler command and output archive hash. Compiler
runtime library closure remains incomplete.

`build` invokes the real XNU make system and retains logs plus source/toolchain
provenance in `build/rpi5/run-*`. It propagates failures; missing libraries or
providers are not replaced with empty archives or fake successful implementations.
The logging header is exported with upstream's kernel unifdef settings.
The BCM2712 target is DEVELOPMENT-only and does not consume a KDK platform archive.

Gate 0 is incomplete until a full kernel links and its runtime dependencies and
image contract have been inspected. Exported headers, configuration probes and
host tools are intermediate evidence only. See [status](../../docs/rpi5/STATUS.md).

No command flashes an SD card or alters Xcode's installed SDK. Generated outputs
are ignored by Git. Preserve failed runs when investigating or changing toolchain;
there is deliberately no broad automatic cleanup command.
# Read-only export triage

`python3 tools/rpi5/probe_bearssl.py` rebuilds the five-source candidate PRNG
subset, checks its external symbols, and runs the host known-answer probe.
It requires the unmodified pinned candidate checkout and records commands,
compiler identity, source hashes and test output in a new evidence directory.
This is not a kernel provider or an entropy/concurrency test.

For a new kernel-output tree without deleting previous artifacts, run
`python3 tools/rpi5/rpi5.py build --allow-toolchain-mismatch --jobs 4 --fresh`.
This reuses the prepared SDK and dependencies. The manifest records the new
output root; it is not a claim of a clean dependency rebuild.

`audit_exports.py --symbols PATH EXPORTS...` reports unmatched export providers
with source lines and input hashes. Use the linked kernel's `config/allsymbols`
as PATH. Pass the selected common, arm64 and platform export files explicitly.
Aliases are checked against their implementation names. This tool neither edits
export lists nor replaces `kextsymboltool`; matches do not prove ABI compatibility.
Add `--kernel PATH` to inspect global absolute-zero definitions using `xcrun nm`.
These can satisfy name matching without providing callable implementations.
The JSON field is null when this additional inspection was not requested.
# Read-only Mach-O inventory

Run `python3 tools/rpi5/audit_macho.py <kernel>` to emit a JSON inventory with
the image hash, bounded segment/section layout, entry, link-edit data and local
relocation types. Unknown load commands and malformed ranges fail closed.
The reported physical-base residue is the requirement for a mapping congruent
with the lowest nonempty virtual segment at 32 MiB L2 granularity, not a chosen
physical placement. This does not validate relocation application, instructions,
RAM reservations or boot behavior. Run the normal host unittest suite to test
malformed-input rejection.
