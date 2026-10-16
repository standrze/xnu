#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Persist focused tests against the immutable original interface build."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from tools.rpi5 import build_apple_ssh_interface_helpers as build
from tools.rpi5.tests import test_apple_ssh_interface_helpers as tests


def check():
    manifest = tests.PACKAGE / 'manifest.json'
    if build.sha(manifest) != tests.SHA: raise ValueError('Frozen interface receipt changed')
    paths = [manifest, Path(__file__).resolve(), Path(tests.__file__).resolve(),
             Path(build.__file__).resolve(), build.HOST]
    pins = {str(path): build.sha(path) for path in paths}
    out = Path(tempfile.mkdtemp(prefix='apple-ssh-interface-helpers-tests-', dir=build.ROOT / 'build/rpi5'))
    command = [sys.executable, '-m', 'unittest', 'tools.rpi5.tests.test_apple_ssh_interface_helpers', '-v']
    result = subprocess.run(command, cwd=build.ROOT, capture_output=True, text=True, timeout=60)
    for name in ('stdout', 'stderr'): (out / ('focused-tests.' + name)).write_text(getattr(result, name))
    if result.returncode or 'Ran 4 tests' not in result.stderr or not result.stderr.endswith('OK\n'):
        raise ValueError('Focused interface tests failed: ' + result.stderr)
    for name, digest in pins.items():
        if build.sha(name) != digest: raise ValueError('Test input drift: ' + name)
    receipt = dict(profile='current-apple-ssh-interface-helpers-focused-tests-v1',
        source_inputs_sha256=pins, build_manifest=str(manifest), build_manifest_sha256=tests.SHA,
        command=command, cwd=str(build.ROOT), returncode=result.returncode, test_count=4,
        original_native_local_route_and_parser_asan_ubsan=True, exact_a76_instruction_and_relocation_audit=True,
        exact_full_client_link_delta_audited=True, target_executed=False,
        native_external_network_services=False, target_network_runtime_qualified=False,
        generated_sha256={str(path): build.sha(path) for path in out.iterdir() if path.is_file()})
    (out / 'manifest.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(package=str(out), manifest_sha256=build.sha(out / 'manifest.json'), tests=4), indent=2))
    return out, receipt


if __name__ == '__main__': check()
