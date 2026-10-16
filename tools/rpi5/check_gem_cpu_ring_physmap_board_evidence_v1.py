#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Create a versioned report from the retained CPU-ring physmap capture."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rpi5 import gem_cpu_ring_physmap_board_evidence_v1 as evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, default=evidence.CAPTURE)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    result = evidence.inspect(args.capture)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.report:
        with args.report.resolve().open("x") as stream:
            stream.write(encoded)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
