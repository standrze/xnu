#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Native emitted-tree contract for the exact retained-FDT no-init loader."""
import hashlib
from pathlib import Path
import shlex
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools/rpi5/tests'))
from tools.rpi5.tests.test_pcie_fdt import _synthetic_tree, _encode_fdt, _node
from tools.rpi5.tests.test_handoff import image

CORES = ('firmware_fdt_tree', 'fdt_sanitize', 'pcie_fdt', 'fdt', 'fdt_reg', 'board_tree',
    'memory_type', 'cpu_tree', 'serial_tree', 'apple_dt', 'seed_tree', 'boot_seed',
    'tree_handoff', 'handoff', 'bootstrap', 'boot_args', 'ranges', 'macho', 'reservations',
    'pcie_device_handoff')
EXPECTED = ('FIRMWARE_FDT_PASS SEEDS=1 RETAINED=1 APPLE_TREE=1 PCIE_DECODE=1 NO_MMIO=1\n'
    'PCIE_ID_HANDOFF NO_INIT=1 SERIALIZED_CHOSEN=1 KERNEL_DECODE=1 NORMAL_RETAINED=1 '
    'DEVICE_RESOURCES=3 MISSING_REJECT=1 NO_MMIO=1\n')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def audit(loader):
    sources = [ROOT / 'tools/rpi5/tests/pcie_id_handoff_host.c', loader / 'firmware_seed_tree.c']
    sources += [ROOT / ('loader/rpi5/' + name + '.c') for name in CORES]
    flags = ['xcrun', 'clang', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
        '-DRPI5_FIRMWARE_FDT_HANDOFF=1', '-fsanitize=address,undefined',
        '-I', str(ROOT / 'loader/rpi5')]
    pins = {}
    # Scan all actual include closures before and after executing this fixture.
    def capture():
        result = {}
        for source in sources:
            r = subprocess.run(flags + ['-M', str(source)], cwd=ROOT,
                text=True, capture_output=True, timeout=30)
            if r.returncode:
                raise ValueError('Handoff dependency scan failed: ' + r.stderr)
            for value in shlex.split(r.stdout.replace('\\\n', ' ').partition(':')[2]):
                path = Path(value).resolve(); result[str(path)] = digest(path)
        return result
    pins = capture()
    with tempfile.TemporaryDirectory(prefix='pcie-id-handoff-') as temporary:
        work = Path(temporary)
        program, fixture, kernel = work / 'host', work / 'fixture.dtb', work / 'kernel'
        tree = _synthetic_tree()
        tree['children'].append(_node('chosen', {'rng-seed': bytes(range(64))}))
        fixture.write_bytes(_encode_fdt(tree)); kernel.write_bytes(image())
        command = flags + list(map(str, sources)) + ['-o', str(program)]
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=60)
        if result.returncode or result.stderr:
            raise ValueError('Native handoff compilation failed: ' + result.stderr)
        run = subprocess.run([str(program), str(fixture), str(kernel), 'accept'],
            text=True, capture_output=True, timeout=30)
        if run.returncode or run.stderr or run.stdout != EXPECTED:
            raise ValueError('No-init serialized handoff contract failed: ' + repr(run))
        fixture_sha, kernel_sha = digest(fixture), digest(kernel)
    if pins != capture():
        raise ValueError('Native handoff dependencies changed during execution')
    return dict(native_pass=True, asan_ubsan=True, no_init=True, serialized_chosen=True,
        actual_kernel_record_and_map_decoders=True, missing_descriptor_rejected=True,
        inputs_sha256=pins, fixture_sha256=fixture_sha, synthetic_kernel_sha256=kernel_sha,
        stdout=EXPECTED, physical_execution=False)
