#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One guarded write batch; never stages, reboots, repairs or claims durability.

Arm before the distinct write image boots. No TX without intact, ordered fresh
loader/admission/HFS/shell lines. A failed batch is not retried or cleaned up.
Success still requires separate reboot/fsck/read-only/full-byte persistence.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import termios
import time

import stage_hfs_write_trial as installer
from check_hfs_write_package import WRITE_LOADER, sha256
from hfs_write_results import expected_entries
from hfs_write_serial_results import read_file
from serial_shell_trial import command, receive
from serial_terminal_trial import TERMINAL_LOADER, utc_now, valid_probe_device

ABORT = (*installer.boot.trial.ABORT_MARKERS, b'RPI5XNU:SD:READ_ONLY_READY',
         b'RPI5XNU:BL33:SD_READONLY_TRIAL', b'RPI5XNU:BL33:HFS_READONLY_TRIAL',
         b'RPI5XNU:HFSRO:', b'RPI5XNU:SD:WRITE_REFUSED', b'RPI5XNU:SD:WRITE_FAIL',
         b'RPI5XNU:SD:WRITE_INIT_FAIL', b'RPI5XNU:SD:WRITE_START_FAIL')
ADMISSION = re.compile(rb'RPI5XNU:SD:WRITE_ADMITTED SECTORS=250347520 START=1050624 '
                       rb'BLOCKS=262144 EPOCH=([1-9][0-9]{0,19}) CACHE=([12]) SPEC=([2-6]) DMA=0')
BATCH = b'RPI5XNU:HFSWRITE:BATCH_FSYNCED FILES=5 RAW_WRITES=0 DURABILITY_VERIFIED=0'
CHECKS = ['fresh_distinct_write_boot_cache_off_admission_hfs_and_shell', 'fresh_shell_nonce',
          'real_bsd_second_partition_node', 'writable_hfs_mount_and_status',
          'five_file_create_overwrite_append_fsync_and_same_boot_readback',
          'five_complete_serial_file_hashes', 'nonforced_unmount_and_covered_root_restored',
          'final_shell_nonce']


def load_inputs(inputs, installed, now=None):
    paths = {name: installer.evidence_path(path) for name,path in
             (('inputs',str(inputs)),('plan',str(installed/'plan.json')),('result',str(installed/'result.json')),
              ('remote_source',str(installed/'remote-source.sha256')))}
    bound = {name: sha256(path) for name,path in paths.items()}
    plan = json.loads(paths['plan'].read_text())
    if plan.get('profile')=='write-diagnostic':
        import stage_hfs_write_diagnostic as diagnostic
        expected=diagnostic.load_plan(paths['inputs'],now=now)
    elif plan.get('profile')=='write-cache-diagnostic':
        import stage_hfs_cache_diagnostic as diagnostic
        expected=diagnostic.load_plan(paths['inputs'],now=now)
    else:
        expected=installer.load_plan(paths['inputs'],now=now)
    result = json.loads(paths['result'].read_text())
    if ({key:value for key,value in plan.items() if key!='run'} != expected
            or not re.fullmatch(r'/home/sandrzej/xnu-gate4-hfs-write-[a-z0-9_]{8}',plan.get('run',''))
            or paths['remote_source'].read_text().strip() != hashlib.sha256(installer.remote_source(plan).encode()).hexdigest()):
        raise ValueError('Write image must bind the exact completed guarded installation')
    installer.validate_result(result,plan)
    if any(sha256(path)!=bound[name] for name,path in paths.items()):
        raise ValueError('Installation evidence changed before serial access')
    return plan,result,bound


def exact_lines(raw,marker):
    return list(re.finditer(rb'(?m)^'+re.escape(marker)+rb'\r{0,2}\n',raw))


def validate_boot(raw):
    """Pure bounded streaming guard; missing/partial lines never authorize TX."""
    if len(raw)>2*1024*1024 or any(marker in raw for marker in ABORT):
        raise ValueError('Unsafe, old or failed boot before write input')
    # Reject even torn duplicate prefixes rather than treating the second boot
    # as continuation of the first. SHELL:READY is deliberately repeated.
    for marker in (TERMINAL_LOADER,WRITE_LOADER,b'RPI5XNU:SD:WRITE_ADMITTED',b'RPI5XNU:HFS:REGISTERED'):
        if raw.count(marker)>1:
            raise ValueError('Duplicate write startup identity or intervening reset')
    admission_lines=list(re.finditer(rb'(?m)^RPI5XNU:SD:WRITE_ADMITTED[^\n]*\n',raw))
    parsed=None
    if admission_lines:
        line=admission_lines[0][0]
        match=ADMISSION.fullmatch(re.sub(rb'\r{0,2}\n$',b'',line))
        if not match or int(match[1])>0xffffffffffffffff:
            raise ValueError('Write admission does not prove exact extent/cache-off/epoch')
        parsed=dict(epoch=int(match[1]),cache_state=int(match[2]),sd_specification=int(match[3]),
                    sectors=250347520,start=1050624,blocks=262144,dma=0)
    loaders=[exact_lines(raw,marker) for marker in (TERMINAL_LOADER,WRITE_LOADER)]
    hfs=exact_lines(raw,b'RPI5XNU:HFS:REGISTERED')
    shell=exact_lines(raw,b'RPI5XNU:SHELL:READY')
    if not all(loaders) or not parsed or not hfs or not shell:
        return None
    terminal,write=loaders[0][0].start(),loaders[1][0].start()
    admitted,registered=admission_lines[0].start(),hfs[0].start()
    # IOKit storage and HFS resource matching are concurrent. Their relative
    # order is not an invariant (the passed RO raw boot proves this).
    if not terminal<write<min(admitted,registered):
        raise ValueError('Write startup markers are out of order')
    if shell[-1].start()<max(admitted,registered):
        return None # Wait for a fresh repeated userspace readiness line.
    return parsed


def wait_boot(fd,output,seconds):
    deadline=time.monotonic()+seconds; raw=b''
    admission=None
    while admission is None:
        if time.monotonic()>=deadline:
            raise TimeoutError('No complete fresh write-image admission/HFS/shell boot; zero input')
        raw+=receive(fd,output,deadline)
        admission=validate_boot(raw)
    # Let SMP startup chatter settle, preserving and checking it before TX.
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        raw+=receive(fd,output,deadline)
        validate_boot(raw)
    return admission


def mount_marker(op):
    return (f'RPI5XNU:HFSRW:{op} DEVICE=/dev/disk0s2 PATH=/mnt/hfs '
            'READONLY=0 DURABILITY_VERIFIED=0').encode()


def trial(fd,output,wait,progress):
    progress['admission']=wait_boot(fd,output,wait)
    progress['checks'].append(CHECKS[0])
    nonce='W'+secrets.token_hex(8)
    command(fd,output,'echo '+nonce,[nonce.encode()],progress)
    progress['checks'].append(CHECKS[1])
    command(fd,output,'ls /dev',[b'disk0s2'],progress)
    progress['checks'].append(CHECKS[2])
    command(fd,output,'hfsrw mount',[mount_marker('MOUNTED')],progress,seconds=120)
    progress['hfs_mounted']=True
    command(fd,output,'hfsrw status',[mount_marker('STATUS')],progress)
    progress['checks'].append(CHECKS[3])
    # One batch only; on failure never retry O_EXCL creation or issue cleanup.
    progress['write_batch_attempts']=1
    command(fd,output,'hfswrite exercise',[BATCH],progress,seconds=180)
    progress['checks'].append(CHECKS[4])
    for entry in expected_entries():
        progress['reads'].append(read_file(fd,output,entry,progress))
    progress['checks'].append(CHECKS[5])
    command(fd,output,'hfsrw unmount',[mount_marker('UNMOUNTED')],progress,seconds=180)
    progress['hfs_mounted']=False
    nonce='UNMOUNTED_'+secrets.token_hex(8)
    # Both utility-specific failure and conditional output are required: an
    # unrecognized command must not count as successful restored-root proof.
    command(fd,output,'hfsrw status || echo '+nonce,
            [b'hfsrw mounted identity/write guard: errno 22',nonce.encode()],progress)
    progress['checks'].append(CHECKS[6])
    nonce='W'+secrets.token_hex(8)
    command(fd,output,'echo '+nonce,[nonce.encode()],progress)
    progress['checks'].append(CHECKS[7])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device'); parser.add_argument('output',type=Path)
    parser.add_argument('--inputs',required=True,type=Path)
    parser.add_argument('--installed',required=True,type=Path)
    parser.add_argument('--boot-wait-seconds',default=600,type=int)
    args=parser.parse_args()
    if (not valid_probe_device(args.device) or not 30<=args.boot_wait_seconds<=3600
            or not args.output.resolve().is_relative_to(installer.ROOT/'build/rpi5')):
        parser.error('Use an exact probe device, fresh build/rpi5 output and bounded 30..3600 boot wait')
    plan,installed,bound=load_inputs(args.inputs,args.installed)
    args.output.mkdir(parents=True,exist_ok=False)
    state=dict(status='failed',started_utc=utc_now(),device=args.device,baud=115200,
        partition='/dev/disk0s2',image_sha256=plan['new_image_sha256'],linux_boot_id_before_write=plan['linux_boot_id'],
        evidence_sha256=bound,write_input_sha256=plan['evidence_sha256'],checks=[],reads=[],transmitted_bytes=0,
        recorder_source_sha256=sha256(Path(__file__)),
        write_batch_attempts=0,hfs_mounted=False,durability_verified=False,
        scope='One writable HFS batch and same-boot full-file reads; no reboot/fsck/remount durability proof')
    fd,original=None,None
    try:
        fd=os.open(args.device,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
        fcntl.ioctl(fd,termios.TIOCEXCL)
        original=termios.tcgetattr(fd); config=termios.tcgetattr(fd)
        config[0]=config[1]=config[3]=0; config[2]=termios.CS8|termios.CREAD|termios.CLOCAL
        config[4]=config[5]=termios.B115200
        config[6][termios.VMIN]=config[6][termios.VTIME]=0
        termios.tcsetattr(fd,termios.TCSANOW,config); termios.tcflush(fd,termios.TCIFLUSH)
        with (args.output/'serial.bin').open('xb',buffering=0) as output:
            print('HFS_WRITE_TRIAL_ARMED 115200 8N1 NO_TX_UNTIL_DISTINCT_WRITE_CACHE_OFF_HFS_SHELL_BOOT',flush=True)
            trial(fd,output,args.boot_wait_seconds,state)
            os.fsync(output.fileno())
        state['status']='batch_passed_not_durability'
    except (Exception,KeyboardInterrupt) as error:
        state['error']=str(error) or 'interrupted'
        # Preserve diagnostics without cleanup or retry input into unknown state.
        if fd is not None and (args.output/'serial.bin').exists():
            try:
                with (args.output/'serial.bin').open('ab',buffering=0) as output:
                    deadline=time.monotonic()+2
                    while time.monotonic()<deadline: receive(fd,output,deadline)
            except (Exception,KeyboardInterrupt) as drain:
                state['diagnostic_drain_error']=str(drain) or 'interrupted'
    finally:
        if fd is not None:
            try:
                if original is not None: termios.tcsetattr(fd,termios.TCSANOW,original)
            finally: os.close(fd)
        raw=args.output/'serial.bin'
        state.update(ended_utc=utc_now(),bytes=raw.stat().st_size if raw.exists() else 0,
                     serial_sha256=sha256(raw) if raw.exists() else None)
        (args.output/'state.json').write_text(json.dumps(state,indent=2)+'\n')
        print(json.dumps(state),flush=True)
    return 0 if state['status']=='batch_passed_not_durability' else 1


if __name__=='__main__': raise SystemExit(main())
