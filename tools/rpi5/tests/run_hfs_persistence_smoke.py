#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Mac-only synthetic HFS audit smoke. NEVER physical SD/durability evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_hfs_persistence_image as audit
from hfs_write_results import VECTORS, payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', required=True, type=Path)
    args = parser.parse_args()
    fixture_path = audit.owned_path(args.fixture)
    fixture = json.loads(fixture_path.read_bytes())
    audit.validate_fixture(fixture)
    original_source = Path(fixture['image']).parent / 'source'
    audit.verify_fixture_files(original_source, fixture['files'])
    run = Path(tempfile.mkdtemp(prefix='hfs-persistence-audit-smoke-', dir=audit.ROOT / 'build/rpi5')).resolve()
    source = run / 'source'; source.mkdir()
    report = dict(status='running', scope='Synthetic Mac HFS image only; no Pi access or durability claim',
                  durability_verified=False, created_at=datetime.now(timezone.utc).isoformat())
    try:
        for entry in fixture['files']:
            data = (original_source / entry['path'].lstrip('/')).read_bytes()
            if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise ValueError('Original source changed during synthetic copy')
            target = source / entry['path'].lstrip('/'); target.parent.mkdir(exist_ok=True)
            with target.open('xb') as stream: stream.write(data)
            target.chmod(entry['mode'])
        for name, length, seed in VECTORS:
            with (source / name).open('xb') as stream: stream.write(payload(length, seed))
        audit.verify_fixture_files(source, fixture['files'])
        image = run / 'synthetic.cdr'
        command = ['hdiutil', 'create', '-size', '128m', '-srcfolder', str(source), '-fs', 'HFS+',
                   '-volname', audit.VOLUME, '-layout', 'NONE', '-format', 'UDTO', '-nospotlight',
                   '-anyowners', str(image)]
        result = subprocess.run(command, capture_output=True, timeout=180)
        (run / 'create.stdout').write_bytes(result.stdout); (run / 'create.stderr').write_bytes(result.stderr)
        report.update(create_command=command, create_returncode=result.returncode)
        if result.returncode: raise RuntimeError('Synthetic image creation failed')
        record = audit.plan(image, audit.digest(image), fixture_path)
        output = run / 'audit'; output.mkdir()
        (output / 'plan.json').write_text(json.dumps(record, indent=2) + '\n')
        outcome = audit.execute(record, output)
        report.update(status='synthetic_mac_smoke_passed', audit_result_sha256=audit.digest(output / 'result.json'),
                      image_sha256=audit.digest(image), image_unchanged=outcome['image_unchanged'],
                      readonly_fsck_verified=outcome['readonly_fsck_verified'],
                      readonly_remount_verified=outcome['readonly_remount_verified'])
    except BaseException as error:
        report.update(status='failed', error=str(error)); raise
    finally:
        (run / 'smoke.json').write_text(json.dumps(report, indent=2) + '\n')
        print(run)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
