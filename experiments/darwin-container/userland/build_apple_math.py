#!/usr/bin/env python3
"""Source-build the small Apple-distributed Libm closure required by zsh."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    old = HERE / "upstream/apple-Libm-93/i386.subproj"
    newer = HERE / "upstream/apple-Libm/Source/ARM"
    commands, sources, objects = [], {}, []
    for original in (old / "e_pow.c", old / "s_scalbn.c", old / "math_private.h", newer / "fmod.c", newer / "fpclassify.c"):
        staged = out / original.name
        shutil.copyfile(original, staged)
        sources[str(original.relative_to(HERE))] = hashlib.sha256(original.read_bytes()).hexdigest()
    flags = ["clang", "-arch", "arm64", "-Os", "-ffreestanding", "-fno-builtin", "-fno-stack-protector",
             "-fno-math-errno", "-D_FORTIFY_SOURCE=0", "-D__SOFTFP__=1", "-Dsqrt=__builtin_sqrt",
             "-Dcopysign=__builtin_copysign", "-Dfabs=__builtin_fabs", "-include", "machine/endian.h"]
    with (out / "build.log").open("w") as log:
        for name in ("e_pow", "s_scalbn", "fmod", "fpclassify", "apple_math_adapters"):
            obj = out / (name + ".o")
            src = HERE / "runtime/apple_math_adapters.c" if name == "apple_math_adapters" else out / (name + ".c")
            cmd = flags + ["-c", str(src), "-o", str(obj)]
            commands.append(cmd)
            subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT)
            objects.append(obj)
        cmd = ["ar", "rcs", str(out / "libapple-math.a"), *map(str, objects)]
        commands.append(cmd)
        subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT)
    manifest = {"repositories": [{"url": "https://github.com/apple-oss-distributions/Libm", "tag": "Libm-93", "commit": "21cbbd293ced890ff7eb7a898af184eca0aa9cfa"},
                                  {"url": "https://github.com/apple-oss-distributions/Libm", "tag": "Libm-2026", "commit": "17a5f9daa3f5679f7536b26f133b40cc078753c3"}],
                "source_sha256": sources, "commands": commands,
                "project_adapter_sha256": hashlib.sha256((HERE / "runtime/apple_math_adapters.c").read_bytes()).hexdigest(),
                "adaptation": "Unmodified C algorithm sources staged apart from architecture-specific math.h; arm64 SDK declarations and compiler hardware sqrt/fabs/copysign builtins; select ARM C soft-float fmod algorithm; project isinf/isnan name adapters delegate to Apple __fpclassify.",
                "archive_sha256": hashlib.sha256((out / "libapple-math.a").read_bytes()).hexdigest()}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(manifest["archive_sha256"])


if __name__ == "__main__":
    main()
