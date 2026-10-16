# SPDX-License-Identifier: BSD-2-Clause
"""Build and test the pinned candidate subset; does not modify kernel inputs."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "build/rpi5/bearssl-candidate"
REVISION = "7bea48e5e850ab4cafbe68d3765cdaba13a86d6f"
UNITS = ("rand/hmac_drbg", "mac/hmac", "hash/sha2small", "codec/dec32be", "codec/enc32be",
         "hash/sha2big", "codec/dec64be", "codec/enc64be", "hash/md5", "hash/sha1",
         "codec/dec32le", "codec/enc32le")


def run(command):
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command!r}\n"
                           f"{result.stdout}\n{result.stderr}")
    return result.stdout


def main():
    revision = run(["git", "-C", str(SOURCE), "rev-parse", "HEAD"]).strip()
    if revision != REVISION or run(["git", "-C", str(SOURCE), "status", "--porcelain", "--untracked-files=all"]).strip():
        raise RuntimeError("Candidate must be the unmodified pinned revision")
    evidence = Path(tempfile.mkdtemp(prefix="bearssl-probe-", dir=ROOT / "build/rpi5"))
    flags = ["-arch", "arm64", "-mcpu=cortex-a76", "-ffreestanding", "-fno-builtin",
             "-fno-stack-protector", "-D_FORTIFY_SOURCE=0", "-O2",
             "-I" + str(SOURCE / "src"), "-I" + str(SOURCE / "inc")]
    commands = []
    objects = []
    for unit in UNITS:
        obj = evidence / (Path(unit).name + ".o")
        command = ["xcrun", "clang", *flags, "-c", str(SOURCE / "src" / (unit + ".c")), "-o", str(obj)]
        commands.append(command)
        run(command)
        objects.append(str(obj))
    combined = evidence / "subset.o"
    adapter = ROOT / "osfmk/prng/rpi5_sha512_compress.c"
    adapter_obj = evidence / "sha512_adapter.o"
    command = ["xcrun", "clang", *flags, "-c", str(adapter), "-o", str(adapter_obj)]
    commands.append(command)
    run(command)
    objects.append(str(adapter_obj))
    descriptor = ROOT / "osfmk/prng/rpi5_sha512_digest.c"
    descriptor_obj = evidence / "sha512_descriptor.o"
    command = ["xcrun", "clang", *flags, "-I" + str(ROOT / "EXTERNAL_HEADERS"),
               "-c", str(descriptor), "-o", str(descriptor_obj)]
    commands.append(command)
    run(command)
    objects.append(str(descriptor_obj))
    extra = [ROOT / 'osfmk/prng' / name for name in
             ('rpi5_sha256_digest.c', 'rpi5_digest_dispatch.c', 'rpi5_hmac.c', 'rpi5_legacy_digest.c')]
    for source in extra:
        obj = evidence / (source.stem + '.o')
        command = ['xcrun', 'clang', *flags, '-I'+str(ROOT/'EXTERNAL_HEADERS'),
                   '-c', str(source), '-o', str(obj)]
        commands.append(command)
        run(command)
        objects.append(str(obj))
    command = ["xcrun", "ld", "-r", "-arch", "arm64", "-o", str(combined), *objects]
    commands.append(command)
    run(command)
    undefined = run(["xcrun", "nm", "-u", str(combined)]).split()
    if set(undefined) != {"_memcpy", "_memset"}:
        raise RuntimeError(f"Unexpected primitive dependencies: {undefined}")
    harness = ROOT / "tools/rpi5/tests/bearssl_drbg_probe.c"
    wrapper_source = ROOT / "libkern/crypto/corecrypto_sha2.c"
    wrapper_text = wrapper_source.read_text()
    # Preserve the source license and exact SHA256/SHA384/SHA512 implementations, excluding
    # unrelated digests and kernel-only include infrastructure in this host test.
    wrapper = evidence / "sha512_wrappers.c"
    wrapper.write_text(wrapper_text[:wrapper_text.index("#include")] +
        '#include <libkern/crypto/sha2.h>\n#include <libkern/crypto/register_crypto.h>\n'
        'extern struct crypto_functions *g_crypto_funcs;\n'
        'void panic(const char *, ...) __attribute__((noreturn));\n' +
        wrapper_text[wrapper_text.index("void\nSHA256_Init("):wrapper_text.index("\n#else")])
    command = ["xcrun", "clang", "-I" + str(SOURCE / "inc"), "-I" + str(ROOT / "EXTERNAL_HEADERS"),
               "-I" + str(ROOT / "libkern"), str(harness), str(wrapper), str(combined), "-o", str(evidence / "test")]
    commands.append(command)
    run(command)
    result = run([str(evidence / "test")])
    checked = {"SHA512": [], "SHA384": [], "SHA256": []}
    for line in result.splitlines():
        if line.startswith(("SHA512 ", "SHA384 ", "SHA256 ")):
            algorithm, length, actual = line.split()
            length = int(length)
            expected = hashlib.new(algorithm.lower(), bytes(i & 255 for i in range(length))).hexdigest()
            if actual != expected:
                raise RuntimeError(f"{algorithm} mismatch at {length} bytes")
            checked[algorithm].append(length)
    for algorithm, lengths in checked.items():
        expected_lengths = ([0, 1, 55, 56, 63, 64, 65, 127, 128, 129, 255, 256, 257]
                            if algorithm == 'SHA256' else [0, 1, 111, 112, 127, 128, 129, 255, 256, 257])
        if lengths != expected_lengths:
            raise RuntimeError(f"Missing {algorithm} boundary coverage")
    # Recompile every source, including primitives and extracted wrappers, with
    # instrumentation. Linking an instrumented harness to subset.o would leave
    # the adapter and primitive memory accesses unchecked. Keep the original
    # freestanding dependency audit separate from sanitizer runtime symbols.
    sanitized = evidence / "test-sanitized"
    command = ["xcrun", "clang", *flags,
               "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
               "-I" + str(ROOT / "EXTERNAL_HEADERS"), "-I" + str(ROOT / "libkern"),
               str(harness), str(wrapper), str(adapter), str(descriptor),
               *map(str, extra),
               *[str(SOURCE / "src" / (u + ".c")) for u in UNITS],
               "-o", str(sanitized)]
    commands.append(command)
    run(command)
    execution = subprocess.run([str(sanitized)], text=True, capture_output=True)
    (evidence / "sanitizer.stdout").write_text(execution.stdout)
    (evidence / "sanitizer.stderr").write_text(execution.stderr)
    if execution.returncode or execution.stderr or execution.stdout != result:
        raise RuntimeError(f"Sanitizer run failed or disagreed; see {evidence}")
    inputs = [SOURCE / "src" / (u + ".c") for u in UNITS] + [harness, adapter, descriptor, wrapper_source, SOURCE / "LICENSE.txt"] + extra
    inputs += [ROOT / 'osfmk/prng' / name for name in
               ('rpi5_digest_abi.h', 'rpi5_sha512_compress.h')]
    report = {"revision": revision, "commands": commands, "undefined": undefined,
              "result": result, "sanitizers": {
                  "enabled": ["address", "undefined"], "all_sources_instrumented": True,
                  "exit_code": execution.returncode, "output_matches": True},
              "compiler": run(["xcrun", "clang", "--version"]),
              "inputs_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
              "scope": "host execution of candidate SHA-2 dispatch/adapters and extracted XNU wrappers; no kernel registration or entropy validation"}
    (evidence / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(result.strip())
    print(evidence / "manifest.json")


if __name__ == "__main__":
    main()
