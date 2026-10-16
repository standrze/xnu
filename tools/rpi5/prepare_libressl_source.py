#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Verify the official signify-signed checksums and extract one pristine release."""
import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
VERSION = '4.3.3'
KEY = 'RWT44PcJDPu8ZDd5GfXWW2vuE+xq4M3haXXfYohnEnWoEYCKHNFut6W8'
OPENSSL = Path('/opt/homebrew/opt/openssl@3/bin/openssl').resolve()


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(download):
    download = download.resolve()
    if download.parent != ROOT / 'build/rpi5' or not download.name.startswith('libressl-4.3.3-input-'):
        raise ValueError('Fresh Pi-only LibreSSL input directory required')
    manifest = download / 'source-manifest.json'
    source = download / ('libressl-' + VERSION)
    if manifest.exists() or source.exists(): raise FileExistsError('Already verified/extracted release')
    signature_file = download / 'SHA256.sig'
    first, signature, message = signature_file.read_bytes().split(b'\n', 2)
    if not first.startswith(b'untrusted comment: '): raise ValueError('Invalid signify envelope')
    decoded, key = base64.b64decode(signature, validate=True), base64.b64decode(KEY, validate=True)
    if len(decoded) != 74 or len(key) != 42 or decoded[:10] != key[:10] or key[:2] != b'Ed':
        raise ValueError('Wrong signify algorithm/key identity')
    # signify's Ed envelope is raw Ed25519; use the real OpenSSL verifier,
    # not a project-authored cryptographic implementation.
    public, sig, sums = download / 'signify-public.der', download / 'signature.bin', download / 'SHA256'
    public.write_bytes(bytes.fromhex('302a300506032b6570032100') + key[10:])
    sig.write_bytes(decoded[10:]); sums.write_bytes(message)
    command = [str(OPENSSL), 'pkeyutl', '-verify', '-pubin', '-keyform', 'DER',
        '-inkey', str(public), '-rawin', '-in', str(sums), '-sigfile', str(sig)]
    result = subprocess.run(command, text=True, capture_output=True, timeout=30)
    (download / 'signature-verification.stdout').write_text(result.stdout)
    (download / 'signature-verification.stderr').write_text(result.stderr)
    if result.returncode or result.stdout.strip() != 'Signature Verified Successfully':
        raise ValueError('Official signed checksum verification failed: ' + result.stderr)
    name = 'libressl-' + VERSION + '.tar.gz'
    hashes = re.findall(rb'^SHA256 \(' + re.escape(name.encode()) + rb'\) = ([0-9a-f]{64})$', message, re.M)
    archive = download / name
    if len(hashes) != 1 or sha(archive) != hashes[0].decode(): raise ValueError('Official archive checksum mismatch')
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != source.name:
                raise ValueError('Archive path escapes the distinct source tree')
            if not member.isfile() and not member.isdir():
                raise ValueError('Unexpected link or special file in portable source archive')
        tar.extractall(download, filter='data')
    pins = {str(p): sha(p) for p in source.rglob('*') if p.is_file()}
    report = dict(version=VERSION, archive=str(archive), archive_sha256=sha(archive),
        source=str(source), source_files_sha256=pins, signature_verified=True,
        signify_public_key=KEY, signing_key_source='https://www.libressl.org/releases.html',
        archive_url='https://ftp.openbsd.org/pub/OpenBSD/LibreSSL/' + name,
        signature_url='https://ftp.openbsd.org/pub/OpenBSD/LibreSSL/SHA256.sig',
        verifier=str(OPENSSL), verifier_sha256=sha(OPENSSL), verification_command=command,
        generated_sha256={str(p): sha(p) for p in download.iterdir() if p.is_file()},
        builder_sha256=sha(Path(__file__)), original_sources_changed=False, installed=False)
    manifest.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('download', type=Path)
    r = prepare(parser.parse_args().download)
    print(json.dumps({k: r[k] for k in ('source', 'archive_sha256', 'signature_verified')}, indent=2))
