#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One exact corrective-kernel boot: raw metadata, original script, real zsh.

Strict fresh mount/copy markers and installed receipt required before any TX.
No same-boot waiver, retries, speculative commands, media writes or reboot.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import termios
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_zsh_metadata_package as package_check
import serial_statprobe_trial as diagnostic
import stage_zsh_metadata_trial as staging
from prepare_zsh_trial_root import files_from

t = diagnostic.transport
IMAGE_SHA = '352603430e44ee28e5543ab5de6bd8dba2d606ea8a406b8a0f32815a6a998faa'
IMAGE_BYTES = 18908864
ROOT_MARKER = diagnostic.ROOT_MARKER
COPY = b'RPI5XNU:BL33:RAMDISK_MATERIALIZED PA=0000000008198000 BYTES=0000000000160000 VERIFIED'
KERNEL = b'RPI5XNU:BL33:KERNEL_MATERIALIZED BYTES=000000000118c000 FULL_ENVELOPE_VERIFIED NO_BOOT_ARGS_WRITTEN NO_TRANSFER'
COMMIT = b'RPI5XNU:BL33:BOOT_DATA_COMMITTED TRANSFER_NEXT'
CHECKS = ['fresh_exact_corrective_kernel_copy_and_mounted_root', 'recovery_shell_fresh_nonce',
          'raw_file_diagnostic_complete', 'diagnostic_exit_zero', 'metadata_types_sizes_reads_and_errno_accepted',
          'original_zsh_script_and_exit_zero', 'interactive_zsh_fixed_prompt',
          'interactive_version_builtins_external_exec_returned_prompt', 'interactive_exit_and_live_recovery_shell']


def boot_ready(raw):
    data = t.normalized(raw)
    if not t.boot_ready(raw, IMAGE_BYTES, ROOT_MARKER):
        return False
    if b'FAILED_STOP' in data or b'RPI5XNU:RAMROOT:REJECT' in data:
        raise RuntimeError('Corrective payload/root validation failed')
    ordered = (b'Boot mode: SD (01)', b'Read probe.bin bytes 18908864 hnd ', t.ENTRY,
               t.TERMINAL_LOADER, COPY, KERNEL, t.package_check.TOPOLOGY_PASS,
               t.TRANSFER, COMMIT, ROOT_MARKER, t.READY)
    if any(data.count(marker) != 1 for marker in ordered[:-1]):
        raise RuntimeError('Missing/duplicate exact corrective payload-copy markers')
    positions = [data.index(marker) for marker in ordered]
    if positions != sorted(positions):
        raise RuntimeError('Corrective payload-copy/mount markers out of order')
    return True


def wait_boot(fd, output, seconds):
    deadline, data = time.monotonic()+seconds, b''
    while time.monotonic() < deadline:
        data += t.shell.receive(fd, output, deadline)
        if boot_ready(data): return data
    raise TimeoutError('No exact fresh corrective mounted-root boot; zero input sent')


def accept_metadata(observations, files):
    """Require actual raw types/sizes and original content, never diagnostic exit alone."""
    rows = observations.get('paths', [])
    if [row['path'] for row in rows] != list(diagnostic.PATHS):
        raise ValueError('Missing exact diagnostic paths')
    def metadata(value, mode, size):
        raw = bytes.fromhex(value['raw_hex'])
        if (value['rc'] != 0 or value['guards'] != 1 or len(raw) != 144
                or value.get('mode') != mode or int.from_bytes(raw[4:6], 'little') != mode
                or int.from_bytes(raw[96:104], 'little', signed=True) != size
                or value.get('is_regular') is not ((mode & 0xf000) == 0x8000)
                or value.get('is_directory') is not ((mode & 0xf000) == 0x4000)):
            raise ValueError('Raw metadata type/size/guard acceptance failed')
    for index, row in enumerate(rows):
        if index == 3:
            if row['access_f_ok'] != -2 or row['access_r_ok'] != -2 or row['opens']:
                raise ValueError('Missing-path control returned wrong errno')
            for value in (row['stat'], row['lstat']):
                if value != dict(rc=-2, raw_hex='a5'*144, guards=1):
                    raise ValueError('Missing-path metadata control changed buffer/errno')
            continue
        if row['access_f_ok'] != 0 or row['access_r_ok'] != 0:
            raise ValueError('Preserved path is not accessible')
        content, permission = files[row['path']] if index < 2 else (b'', 0o555)
        mode = permission | (0o100000 if index < 2 else 0o040000)
        for value in (row['stat'], row['lstat']): metadata(value, mode, len(content))
        if index == 2:
            if row['opens']: raise ValueError('Unexpected directory open observations')
            continue
        if [opened['flags'] for opened in row['opens']] != [0, 0x20000]:
            raise ValueError('Missing plain/NOCTTY open profiles')
        for opened in row['opens']:
            metadata(opened['fstat'], mode, len(content))
            if (not 0 <= opened['fd'] < opened['duplicate'] or opened['duplicate'] < 10
                    or opened['getfd'] != 0 or opened['getfl'] != 0
                    or opened['duplicate_close'] != 0 or opened['original_close'] != 0):
                raise ValueError('Descriptor flags/duplication/close acceptance failed')
            for value, expected in ((opened['duplicate_read'],content[:16]),
                                    (opened['original_read'],content[16:32])):
                if value != dict(rc=len(expected), hex=expected.hex()):
                    raise ValueError('Original file content/shared offset differs')
    return dict(raw_metadata_accepted=True, original_file_types_sizes_and_read_prefixes=True,
                negative_control_enoent=True, scope='Fixed preserved RAM-root paths only')


def installation(directory, report):
    directory = directory.resolve()
    if not directory.is_relative_to(staging.ROOT/'build/rpi5'):
        raise ValueError('Project installation receipt required')
    plan = json.loads((directory/'plan.json').read_text())
    result = json.loads((directory/'result.json').read_text())
    staging.validate_result(result, plan)
    if plan['preflight'] != report or result['image_sha256'] != IMAGE_SHA:
        raise ValueError('Installed receipt differs from exact corrective package')
    return dict(directory=str(directory),
                plan_sha256=hashlib.sha256((directory/'plan.json').read_bytes()).hexdigest(),
                result_sha256=hashlib.sha256((directory/'result.json').read_bytes()).hexdigest())


def trial(fd, output, seconds, state):
    wait_boot(fd, output, seconds)
    state['checks'].append(CHECKS[0])
    nonce = 'Z'+secrets.token_hex(8)
    state['nonce'] = nonce
    t.exchange(fd,output,'echo '+nonce,[nonce.encode()],t.shell.PROMPT,state)
    state['checks'].append(CHECKS[1])
    raw = t.exchange(fd,output,'/bin/statprobe',[diagnostic.BEGIN,diagnostic.END],t.shell.PROMPT,state)
    state['observations'] = diagnostic.parse_diagnostic(raw)
    state['checks'].append(CHECKS[2])
    t.exchange(fd,output,'echo $?', [b'0'],t.shell.PROMPT,state)
    state['checks'].append(CHECKS[3])
    state['metadata_acceptance'] = accept_metadata(state['observations'], files_from(package_check.previous.INIT.read_bytes()))
    state['checks'].append(CHECKS[4])
    t.exchange(fd,output,'zsh -f /etc/zsh-smoke.zsh',t.SMOKE_LINES,t.shell.PROMPT,state)
    t.exchange(fd,output,'echo $?', [b'0'],t.shell.PROMPT,state)
    state['script_file_acceptance'] = True
    state['checks'].append(CHECKS[5])
    prompt = t.re.compile(t.re.escape(t.ZPROMPT))
    launched = t.exchange(fd,output,t.LAUNCH,[b'DARWIN:ZSH:MAIN'],prompt,state)
    if t.normalized(launched).count(b'DARWIN:ZSH:MAIN\n') != 2:
        raise RuntimeError('Expected launcher and interactive zsh startup traces')
    state['checks'].append(CHECKS[6])
    t.exchange(fd,output,'print -r -- "PI_ZSH:$ZSH_VERSION"',[b'PI_ZSH:5.9'],prompt,state)
    t.exchange(fd,output,'a=(pi xnu); print -r -- "PI_BUILTINS:${a[2]}:$((6*7))"',[b'PI_BUILTINS:xnu:42'],prompt,state)
    t.exchange(fd,output,'/bin/echo PI_EXEC_'+nonce,[('PI_EXEC_'+nonce).encode()],prompt,state)
    state['checks'].append(CHECKS[7])
    t.exchange(fd,output,'exit',[],t.shell.PROMPT,state)
    t.exchange(fd,output,'echo RECOVERED_'+nonce,[('RECOVERED_'+nonce).encode()],t.shell.PROMPT,state)
    state['checks'].append(CHECKS[8])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device')
    parser.add_argument('output',type=Path)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--installation',type=Path,required=True)
    parser.add_argument('--image-sha256',required=True)
    parser.add_argument('--boot-wait-seconds',type=int,default=180)
    args = parser.parse_args()
    if not t.valid_probe_device(args.device) or not 30 <= args.boot_wait_seconds <= 3600:
        parser.error('Expected Debug Probe callout and bounded boot wait')
    report = package_check.inspect(args.package)
    if (report['image_sha256'] != args.image_sha256 or args.image_sha256 != IMAGE_SHA
            or report['image_bytes'] != IMAGE_BYTES or report['root_mount_marker'].encode() != ROOT_MARKER):
        raise ValueError('Exact corrective package required')
    installed = installation(args.installation,report)
    args.output.mkdir(parents=True,exist_ok=False)
    state = dict(status='failed',started_utc=t.utc_now(),device=args.device,baud=115200,
                 checks=[],transmitted_bytes=0,preflight=report,installation=installed,
                 script_file_acceptance=False,full_gate6_exit=False,networking=False,durability=False,
                 scope='One metadata/script/interactive zsh trial; no full distribution or storage acceptance')
    fd,original = None,None
    try:
        fd = os.open(args.device,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
        fcntl.ioctl(fd,termios.TIOCEXCL)
        original = termios.tcgetattr(fd)
        config = termios.tcgetattr(fd)
        config[0] = config[1] = config[3] = 0
        config[2] = termios.CS8|termios.CREAD|termios.CLOCAL
        config[4] = config[5] = termios.B115200
        config[6][termios.VMIN] = config[6][termios.VTIME] = 0
        termios.tcsetattr(fd,termios.TCSANOW,config)
        termios.tcflush(fd,termios.TCIFLUSH)
        with (args.output/'serial.bin').open('xb',buffering=0) as output:
            if installation(args.installation,report) != installed:
                raise ValueError('Installation evidence changed before arming')
            print('METADATA_ZSH_TRIAL_ARMED ZERO_TX_UNTIL_EXACT_FRESH_MOUNTED_BOOT',flush=True)
            trial(fd,output,args.boot_wait_seconds,state)
        state['status'] = 'passed'
    except (Exception,KeyboardInterrupt) as error:
        state['error'] = str(error) or 'interrupted'
    finally:
        if fd is not None:
            try:
                if original is not None: termios.tcsetattr(fd,termios.TCSANOW,original)
            except OSError as error:
                state['serial_restore_error'] = str(error); state['status'] = 'failed'
            finally: os.close(fd)
        raw = args.output/'serial.bin'
        state.update(ended_utc=t.utc_now(),bytes=raw.stat().st_size if raw.exists() else 0,
                     serial_sha256=hashlib.sha256(raw.read_bytes()).hexdigest() if raw.exists() else None)
        (args.output/'state.json').write_text(json.dumps(state,indent=2)+'\n')
        print(json.dumps(state),flush=True)
    return 0 if state['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
