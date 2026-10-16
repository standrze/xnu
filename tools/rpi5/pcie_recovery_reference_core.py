# SPDX-License-Identifier: BSD-2-Clause
"""Read-only exact-card boot reference; never a latched override/reset receipt.

The original capture module is injected explicitly and remains unchanged.
Only the FAT boot partition is mounted, read-only, and only after exact root,
boot, CID, layout, unmounted-state and whole-MBR/FAT hashes match the baseline.
No HFS mount, SD write, mailbox setter, raw MMIO, watchdog control or reboot.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess

MOUNTPOINT = '/mnt/xnu-probe'
BOOT_NODE = '/dev/mmcblk0p1'
BOOT_PROPERTIES = ('boot-mode', 'partition', 'tryboot')
ALTERNATE_FILES = ('autoboot.txt', 'tryboot.txt', 'boot.img', 'tryboot.img', 'recovery.bin')
EXTENTS = {'mbr': ('/dev/mmcblk0', 128177930240, 512),
           'boot': (BOOT_NODE, 536870912, 536870912)}
OPERATIONS = dict(sd_write_operations=0, fat_readonly_mounts=1, hfs_mounts=0,
                  serial_actions=0, raw_mmio_actions=0, mailbox_control_changes=0,
                  firmware_changes=0, reboots=0)
LIMITATIONS = dict(latched_override_verified=False, watchdog_running_verified=False,
                   watchdog_reset_return_proven=False, hardware_timeout_measured=False, installation_admitted=False,
                   xnu_pcie_access_admitted=False, inherited_domains_proven=False,
                   nvme_backup_chain_reverified=False, hfs_content_rehashed=False)


def config_profile(raw):
    """Conservative fixed Pi5 config subset, not a general firmware evaluator."""
    if not isinstance(raw, bytes) or len(raw) > 65536 or b'\0' in raw:
        raise ValueError('Invalid bounded boot configuration')
    text = raw.decode('ascii')
    enabled = True
    values = {}
    selected = {'set_reboot_order', 'kernel_watchdog_timeout', 'kernel_watchdog_partition',
                'kernel', 'armstub', 'device_tree', 'arm_64bit', 'kernel_address'}
    reasons = []
    for number, original in enumerate(text.splitlines(), 1):
        line = original.strip()
        if not line or line.startswith('#'): continue
        if len(original) > 98:
            reasons.append('line exceeds firmware limit: ' + str(number))
        if line.startswith('['):
            if line not in ('[all]', '[pi5]', '[none]'):
                reasons.append('unsupported filter: ' + str(number))
            enabled = line != '[none]'
            continue
        match = re.fullmatch(r'([a-z0-9_]+)=(.*)', line)
        if not match:
            reasons.append('unsupported directive/include: ' + str(number)); continue
        key, value = match.groups()
        if enabled and key in selected:
            if key in values: reasons.append('duplicate selected setting: ' + key)
            values[key] = value
    def number(key):
        value = values.get(key)
        if value is None: return None
        if not re.fullmatch(r'(?:0x[0-9a-fA-F]+|[0-9]+)', value):
            reasons.append('invalid numeric setting: ' + key); return None
        return int(value, 16 if value.startswith('0x') else 10)
    order, timeout, partition = map(number, ('set_reboot_order', 'kernel_watchdog_timeout', 'kernel_watchdog_partition'))
    return dict(supported_subset=not reasons, reasons=reasons, selected_settings=values,
                set_reboot_order=order, kernel_watchdog_timeout=timeout, kernel_watchdog_partition=partition,
                configured_nvme_only_next_order=not reasons and order == 0xf6)


def eeprom_profile(text):
    if not isinstance(text, str) or len(text) > 65536: raise ValueError('Invalid EEPROM reference')
    values = {}
    for original in text.splitlines():
        line = original.strip()
        if not line or line.startswith('#') or line == '[all]': continue
        match = re.fullmatch(r'([A-Z0-9_]+)=([^#\s]+)', line)
        if not match or match[1] in values: raise ValueError('Unsupported/duplicate EEPROM setting')
        values[match[1]] = match[2]
    raw = values.get('BOOT_ORDER')
    if raw is None or not re.fullmatch(r'(?:0x[0-9a-fA-F]{1,8}|[0-9]{1,10})', raw):
        raise ValueError('Missing/invalid EEPROM boot order')
    value = int(raw, 16 if raw.startswith('0x') else 10)
    if not 0 < value <= 0xffffffff: raise ValueError('EEPROM order outside word range')
    nibbles = []
    while value:
        nibbles.append(value & 15); value >>= 4
    return dict(boot_order=raw, order_right_to_left=nibbles,
                persistent_order_sd_first=nibbles[0] == 1)


def configured_return(files):
    profile = files['config_profile']
    # set_reboot_order controls the next boot independently of the firmware's
    # requested watchdog seconds. The diagnostic will verify a running PM
    # countdown before its own 15-second reload; don't manufacture a config
    # change requirement from an unmeasured timeout request (currently 60).
    return (profile['configured_nvme_only_next_order'] and
            profile['kernel_watchdog_partition'] in (None, 0) and
            profile['selected_settings'].get('kernel') == 'probe.bin' and
            profile['selected_settings'].get('armstub') == 'bl31.bin' and
            not any(files['alternate_files_present'].values()))


def same(left, right):
    if type(left) is not type(right): return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
    return left == right


def mount_record(command, required=True):
    result = command(['findmnt', '--json', '--mountpoint', MOUNTPOINT,
                      '-o', 'ID,SOURCE,FSTYPE,OPTIONS,TARGET'])
    if result.returncode == 1 and not result.stdout.strip() and not required: return None
    if result.returncode: raise ValueError('Exact mount lookup failed')
    rows = json.loads(result.stdout).get('filesystems')
    if not isinstance(rows, list) or len(rows) != 1: raise ValueError('Ambiguous boot mount')
    row = rows[0]
    if set(row) != {'id', 'source', 'fstype', 'options', 'target'}:
        raise ValueError('Unexpected mount record')
    try: identifier = int(row['id'])
    except (ValueError, TypeError): raise ValueError('Invalid mount identifier') from None
    if identifier <= 0 or isinstance(row['id'], bool): raise ValueError('Invalid mount identifier')
    if not isinstance(row['options'], str): raise ValueError('Invalid mount options')
    options = set(row['options'].split(','))
    if (row['source'] != BOOT_NODE or row['fstype'] != 'vfat' or row['target'] != MOUNTPOINT or
            not {'ro', 'nosuid', 'nodev', 'noexec'}.issubset(options) or 'rw' in options):
        raise ValueError('Not the exact protected read-only FAT mount')
    return dict(id=identifier, source=row['source'], fstype=row['fstype'],
                target=row['target'], options=sorted(options))


def read_files(directory, expected):
    """Fixed single-component names; no symlink following or unbounded reads."""
    allowed = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,95}')
    if not expected or not all(allowed.fullmatch(name) and re.fullmatch('[0-9a-f]{64}', digest)
                               for name, digest in expected.items()):
        raise ValueError('Invalid protected boot-file map')
    files, configuration = {}, None
    for name, digest in expected.items():
        fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
                    before.st_dev != os.fstat(directory).st_dev or not 0 < before.st_size <= 32*1024*1024):
                raise ValueError('Unexpected protected boot file: ' + name)
            if name == 'config.txt' and before.st_size > 65536: raise ValueError('Oversized boot config')
            value, chunks = hashlib.sha256(), []
            for offset in range(0, before.st_size, 1024*1024):
                wanted = min(1024*1024, before.st_size-offset)
                data = os.pread(fd, wanted, offset)
                if len(data) != wanted: raise ValueError('Short boot file read')
                value.update(data)
                if name == 'config.txt': chunks.append(data)
            after = os.fstat(fd)
            if any(getattr(before, key) != getattr(after, key) for key in
                   ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')):
                raise ValueError('Protected file changed during read')
            if value.hexdigest() != digest: raise ValueError('Protected boot file differs: ' + name)
            files[name] = dict(bytes=before.st_size, sha256=digest)
            if name == 'config.txt': configuration = b''.join(chunks)
        finally: os.close(fd)
    if configuration is None: raise ValueError('Protected config required')
    alternate = {}
    for name in ALTERNATE_FILES:
        try: os.stat(name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError: alternate[name] = False
        else: alternate[name] = True
    return dict(files=files, config_text=configuration.decode('ascii'),
                config_profile=config_profile(configuration), alternate_files_present=alternate)


def boot_properties():
    result = {}
    for name in BOOT_PROPERTIES:
        # Never enumerate or read the rest of /chosen (seeds/identities).
        path = Path('/proc/device-tree/chosen/bootloader') / name
        try:
            with path.open('rb') as source: raw = source.read(5)
        except FileNotFoundError: result[name] = None; continue
        if len(raw) != 4: raise ValueError('Invalid bootloader property: ' + name)
        result[name] = struct.unpack('>I', raw)[0]
    return result


def capture_recovery(plan, original, run=None):
    if os.geteuid() != 0: raise ValueError('Root required for exact read-only FAT access')
    if run is None:
        run = lambda args: subprocess.run(args, text=True, capture_output=True, timeout=20)
    before = original.identity(plan['identity_binding'])
    properties = boot_properties()
    eeprom = original.command('rpi-eeprom-config')
    def blocks():
        result = {name: original.snapshot(*extent) for name, extent in EXTENTS.items()}
        if {name: row['sha256'] for name, row in result.items()} != plan['protected_extents_sha256']:
            raise ValueError('Complete protected MBR/FAT differs')
        return result
    first = blocks()
    if original.identity(plan['identity_binding']) != before: raise ValueError('Identity changed before mount')
    mp = Path(MOUNTPOINT)
    if mp.resolve() != mp or not mp.is_dir() or any(mp.iterdir()):
        raise ValueError('Exact empty existing boot mountpoint required')
    if mount_record(run, required=False) is not None: raise ValueError('Boot mountpoint already occupied')
    # The command has a fixed target and RO flags; no remount/RW path exists.
    mounted = run(['mount', '-t', 'vfat', '-o', 'ro,nosuid,nodev,noexec', BOOT_NODE, MOUNTPOINT])
    if mounted.returncode: raise ValueError('Read-only mount failed; inspect mount state before retry')
    owned = None
    try:
        owned = mount_record(run)
        directory = os.open(MOUNTPOINT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: read = read_files(directory, plan['protected_files_sha256'])
        finally: os.close(directory)
        if mount_record(run) != owned: raise ValueError('Boot mount ownership/options changed')
    finally:
        # Never unmount a foreign/replaced mount after a timeout or race. An
        # unidentifiable success must be inspected, not blindly cleaned up.
        if owned is None or mount_record(run) != owned:
            raise ValueError('Cannot safely clean up unidentified/replaced mount; inspect it')
        unmounted = run(['umount', MOUNTPOINT])
        if unmounted.returncode: raise ValueError('Read-only unmount failed; inspect current state')
    after = original.identity(plan['identity_binding'])
    last = blocks()
    if (before != after or first != last or boot_properties() != properties or
            original.command('rpi-eeprom-config') != eeprom):
        raise ValueError('Boot identity/configuration/protected bytes changed during capture')
    parsed = eeprom_profile(eeprom)
    return dict(identity_before=before, identity_after=after,
                protected_before=first, protected_after=last, bootloader_properties=properties,
                eeprom_text=eeprom, eeprom_profile=parsed, boot_files=read, mount=owned,
                configured_one_shot_nvme_return=bool(configured_return(read)), operations=OPERATIONS,
                requested_watchdog_seconds=read['config_profile']['kernel_watchdog_timeout'],
                limitations=LIMITATIONS, boot_unmounted=True)


def validate_recovery(report, plan):
    expected = dict(identity=plan['identity_binding']['expected'],
                    boot_id=plan['identity_binding']['linux_boot_id_after_write'], hostname='kamidana')
    if not same(report['identity_before'], expected) or not same(report['identity_after'], expected):
        raise ValueError('Incomplete exact fresh boot identity')
    if not same(report.get('operations'), OPERATIONS) or not same(report.get('limitations'), LIMITATIONS) or report.get('boot_unmounted') is not True:
        raise ValueError('Unsupported recovery operations/claims')
    for field in ('protected_before', 'protected_after'):
        if set(report[field]) != set(EXTENTS): raise ValueError('Incomplete protected read coverage')
        for name, (node, _, length) in EXTENTS.items():
            if not same(report[field][name], dict(device=node, bytes=length, sha256=plan['protected_extents_sha256'][name])):
                raise ValueError('Protected block receipt differs')
    files = report['boot_files']
    if set(files['files']) != set(plan['protected_files_sha256']): raise ValueError('Incomplete protected file map')
    for name, digest in plan['protected_files_sha256'].items():
        row = files['files'][name]
        if row.get('sha256') != digest or type(row.get('bytes')) is not int or not 0 < row['bytes'] <= 32*1024*1024:
            raise ValueError('Invalid protected file receipt')
    raw = files['config_text'].encode('ascii')
    if (hashlib.sha256(raw).hexdigest() != plan['protected_files_sha256']['config.txt'] or
            files['files']['config.txt']['bytes'] != len(raw) or not same(config_profile(raw), files['config_profile'])):
        raise ValueError('Boot config bytes/profile mismatch')
    if not same(eeprom_profile(report['eeprom_text']), report['eeprom_profile']):
        raise ValueError('EEPROM profile mismatch')
    alternate = files['alternate_files_present']
    if set(alternate) != set(ALTERNATE_FILES) or any(type(v) is not bool for v in alternate.values()):
        raise ValueError('Incomplete alternate boot-file checks')
    properties = report['bootloader_properties']
    if set(properties) != set(BOOT_PROPERTIES) or any(v is not None and (type(v) is not int or not 0 <= v <= 0xffffffff)
                                                                  for v in properties.values()):
        raise ValueError('Unallowlisted/invalid boot property')
    expected_configured = configured_return(files)
    if type(report['configured_one_shot_nvme_return']) is not bool or report['configured_one_shot_nvme_return'] != expected_configured:
        raise ValueError('Configured return claim differs')
    if not same(report.get('requested_watchdog_seconds'), files['config_profile']['kernel_watchdog_timeout']):
        raise ValueError('Requested timeout differs; not a hardware timing receipt')
    mount = report['mount']
    if (type(mount.get('id')) is not int or mount['id'] <= 0 or mount.get('source') != BOOT_NODE or
        mount.get('target') != MOUNTPOINT or mount.get('fstype') != 'vfat' or
        not {'ro', 'nosuid', 'nodev', 'noexec'}.issubset(mount.get('options', [])) or 'rw' in mount['options']):
        raise ValueError('Missing exact read-only mount receipt')
