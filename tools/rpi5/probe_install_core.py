# SPDX-License-Identifier: BSD-2-Clause
"""Regular-file probe installation only; caller proves the exact mounted SD.

No device discovery, mount, partition, reboot, rollback or automatic retry.
Retain the old image and incomplete temporary file on failure. A rename is
not claimed to be power-loss atomic on FAT; verified NVMe backups are required.
"""
import hashlib
import os
import re
import stat

CHUNK = 1024 * 1024
MAX_IMAGE = 32 * CHUNK


def regular(fd):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= MAX_IMAGE:
        raise ValueError('Expected one bounded, non-linked regular image')
    return info.st_size


def digest_fd(fd):
    size = regular(fd)
    digest = hashlib.sha256()
    for offset in range(0, size, CHUNK):
        length = min(CHUNK, size - offset)
        data = os.pread(fd, length, offset)
        if len(data) != length:
            raise RuntimeError('Short image read')
        digest.update(data)
    if regular(fd) != size:
        raise RuntimeError('Image length changed while hashing')
    return digest.hexdigest()


def copy_image(source, directory, name, expected):
    fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        size = regular(source)
        for offset in range(0, size, CHUNK):
            data = os.pread(source, min(CHUNK, size - offset), offset)
            if len(data) != min(CHUNK, size - offset):
                raise RuntimeError('Short image source read')
            done = 0
            for _ in range(16):
                try:
                    count = os.pwrite(fd, data[done:], offset + done)
                except InterruptedError:
                    continue
                if type(count) is not int or not 0 < count <= len(data) - done:
                    raise RuntimeError('Invalid image write progress')
                done += count
                if done == len(data):
                    break
            if done != len(data):
                raise RuntimeError('Image write progress limit')
        os.fsync(fd)
        if digest_fd(fd) != expected or digest_fd(source) != expected:
            raise RuntimeError('Copied image/source readback differs')
    finally:
        os.close(fd)


INSTALL_NAMES = {
    'initial': ('probe.sd-read-passed-20261012.bin', 'probe.hfs-read-20261012.tmp'),
    'statfs-correction': ('probe.hfs-statfs-failed-20261012.bin', 'probe.hfs-statfs-corrected-20261012.tmp'),
    'write-trial': ('probe.hfs-read-passed-20261012.bin', 'probe.hfs-write-trial-20261012.tmp'),
    'write-diagnostic': ('probe.hfs-write-no-admission-20261012.bin', 'probe.hfs-write-diagnostic-20261012.tmp'),
    'write-cache-diagnostic': ('probe.hfs-write-cache-probe-failed-20261012.bin', 'probe.hfs-write-cache-diagnostic-20261012.tmp'),
    'pcie-topology': ('probe.hfs-cache-buffer-failed-20261012.bin', 'probe.pcie-topology-20261012.tmp'),
    'zsh-trial': ('probe.pcie-topology-passed-20261012.bin', 'probe.zsh-trial-20261012.tmp'),
    'statprobe-trial': ('probe.zsh-interactive-passed-20261012.bin', 'probe.statprobe-trial-20261012.tmp'),
    'zsh-metadata-trial': ('probe.statprobe-diagnosed-20261012.bin', 'probe.zsh-metadata-trial-20261012.tmp'),
    'apple-network-trial': ('probe.zsh-metadata-passed-20261012.bin', 'probe.apple-network-trial-20261012.tmp'),
}


def install(directory, candidate, old_hash, new_hash, profile='initial'):
    """Fixed filenames only; never overwrite an existing backup or temp file."""
    if not isinstance(profile, str) or profile not in INSTALL_NAMES:
        raise ValueError('Unknown fixed installation profile')
    if any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value)
           for value in (old_hash, new_hash)) or old_hash == new_hash:
        raise ValueError('Distinct exact image hashes required')
    if not stat.S_ISDIR(os.fstat(directory).st_mode) or digest_fd(candidate) != new_hash:
        raise ValueError('Invalid boot directory or candidate')
    old = os.open('probe.bin', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    backup, temporary = INSTALL_NAMES[profile]
    try:
        if digest_fd(old) != old_hash:
            raise ValueError('Installed image differs from the exact expected prior candidate')
        # Unknown prior partial work is a diagnostic condition, never a retry.
        for name in (backup, temporary):
            try:
                os.stat(name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise ValueError('Existing installation artifact; inspect before retry: ' + name)
        copy_image(old, directory, backup, old_hash)
        os.fsync(directory)
        copy_image(candidate, directory, temporary, new_hash)
        current = os.open('probe.bin', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        try:
            if digest_fd(current) != old_hash:
                raise RuntimeError('Installed image changed before publication')
        finally:
            os.close(current)
        os.rename(temporary, 'probe.bin', src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
        current = os.open('probe.bin', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        try:
            if digest_fd(current) != new_hash:
                raise RuntimeError('Published image readback differs; preserve backups')
        finally:
            os.close(current)
        return dict(image_sha256=new_hash, preserved_sd_image_sha256=old_hash,
                    sd_backup=backup, temporary_published=True,
                    power_loss_atomicity_claimed=False)
    finally:
        os.close(old)
