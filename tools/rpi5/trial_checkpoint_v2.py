# SPDX-License-Identifier: BSD-2-Clause
"""Once-completed offline audit, subsequently rechecked by exact content bytes.

This is a cache of a trusted caller's *complete* audit, not a signature or an
authorization token. The controller must retain the returned digest separately;
never trust a digest recomputed from an unknown checkpoint. No hardware access,
network calls, historical archive reads, retry or restoration is implemented.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

FORMAT='rpi5-complete-audit-byte-seal-v2'


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def digest(value):return hashlib.sha256(canonical(value)).hexdigest()


def sha(path):
    # A changed descriptor invalidates the check even if the final size matches.
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        before=os.fstat(f.fileno());h=hashlib.sha256()
        if not stat.S_ISREG(before.st_mode):raise ValueError('Regular local evidence file required')
        while block:=f.read(1024*1024):h.update(block)
        after=os.fstat(f.fileno())
    if any(getattr(before,k)!=getattr(after,k) for k in
           ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')):
        raise ValueError('Evidence changed during byte revalidation: '+str(path))
    return h.hexdigest()


def check_pins(pins):
    if not isinstance(pins,dict) or not pins or len(pins)>50000:
        raise ValueError('Bounded nonempty complete evidence closure required')
    for name,value in pins.items():
        if not isinstance(name,str) or not Path(name).is_absolute() or not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):
            raise ValueError('Absolute exact evidence pin required')
        if sha(name)!=value:raise ValueError('Sealed evidence bytes changed: '+name)


def create(full_audit,evidence_pins):
    """Call the full receipt/package auditor exactly once, with byte stability.

    evidence_pins must include that auditor's complete source/object/receipt
    closure, not only its top-level manifest. The caller obtains this closure
    from the exact package and prior accepted receipt chain, as before.
    """
    pins=dict(evidence_pins)
    for p in (Path(__file__).resolve(),Path(full_audit.__code__.co_filename).resolve()):
        name=str(p);actual=sha(p)
        if name in pins and pins[name]!=actual:
            raise ValueError('Expected automatic source pin differs: '+name)
        pins.setdefault(name,actual)
    check_pins(pins);payload=full_audit();check_pins(pins)
    value=dict(format=FORMAT,payload=json.loads(canonical(payload)),evidence_sha256=pins,
        full_audit_completed=True,revalidation='full-content-hashes-no-build-or-ancestry-replay',
        hardware_admission=False)
    return value,digest(value)


def revalidate(value,expected_digest):
    if not isinstance(expected_digest,str) or not re.fullmatch('[0-9a-f]{64}',expected_digest) or digest(value)!=expected_digest:
        raise ValueError('Separately retained checkpoint digest differs')
    if (set(value)!={'format','payload','evidence_sha256','full_audit_completed','revalidation','hardware_admission'} or
        value['format']!=FORMAT or value['full_audit_completed'] is not True or value['hardware_admission'] is not False or
        value['revalidation']!='full-content-hashes-no-build-or-ancestry-replay'):
        raise ValueError('Exact complete-audit seal schema required')
    check_pins(value['evidence_sha256'])
    return json.loads(canonical(value['payload']))


def save_new(path,value,expected_digest):
    revalidate(value,expected_digest);path=Path(path)
    with path.open('xb') as out:out.write(canonical(value)+b'\n');out.flush();os.fsync(out.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
