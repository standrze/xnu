# SPDX-License-Identifier: BSD-2-Clause
"""One fixed Linux CMD48 read for comparison with failed XNU observation.

Independent new code using Linux MMC ioctl ABI/protocol facts, not copied
driver implementation. Sources: include/uapi/linux/mmc/ioctl.h,
include/linux/mmc/core.h and drivers/mmc/core/sd.c in torvalds/linux.
No write opcode, cache toggle/flush, retry, mount, reset or admission fallback.
Linux's own transport can perform internal commands: one userspace ioctl is
not a claim of exactly one wire command. Linux state is not XNU cache proof.
"""
import ctypes
import fcntl
import hashlib
import os
import platform
import stat
import struct
import sys


def read_general_information():
    if (platform.machine()!='aarch64' or sys.byteorder!='little'
            or ctypes.sizeof(ctypes.c_void_p)!=8 or struct.calcsize('=iiII4I8IQ')!=72):
        raise ValueError('Only the verified Linux ARM64 MMC ioctl ABI is supported')
    node='/dev/mmcblk0'
    fd=os.open(node,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        observed=os.fstat(fd)
        if (not stat.S_ISBLK(observed.st_mode) or observed.st_rdev!=os.stat(node).st_rdev
                or struct.unpack('=Q',fcntl.ioctl(fd,0x80081272,bytes(8)))[0]!=128177930240):
            raise ValueError('Not the exact disposable SD block descriptor/capacity')
        data=(ctypes.c_ubyte*512)(*([0xa5]*512))
        # mmc_ioc_cmd: write=0, ACMD=0, opcode48, FNO0/page0/offset0/LEN511;
        # RSP_R1|CMD_ADTC=0x35, one 512-byte read, bounded explicit timeouts.
        command=bytearray(struct.pack('=iiII4I8IQ',0,0,48,511,0,0,0,0,
            0x35,512,1,0,0,1000000000,1000,0,ctypes.addressof(data)))
        if fcntl.ioctl(fd,0xc048b300,command,True)!=0:
            raise RuntimeError('Unexpected Linux MMC ioctl return')
        fields=struct.unpack('=iiII4I8IQ',command)
        if fields[:4]!=(0,0,48,511) or fields[8:16]!=(0x35,512,1,0,0,1000000000,1000,0):
            raise ValueError('Linux MMC command metadata changed unexpectedly')
        response=list(fields[4:8]); r1=response[0]
        if r1&0xfff98088 or (r1&0x1f00)!=0x900:
            raise ValueError('CMD48 response does not establish ready transfer state')
        after=os.fstat(fd)
        if not stat.S_ISBLK(after.st_mode) or after.st_rdev!=observed.st_rdev:
            raise ValueError('SD descriptor changed during read')
        payload=bytes(data)
        return dict(opcode=48,argument=511,write_flag=0,is_acmd=0,blocks=1,bytes=512,
            flags=0x35,response=response,payload_hex=payload.hex(),
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            sentinel_unchanged=payload==bytes([0xa5])*512)
    finally:
        os.close(fd)


def observe(plan):
    # identity() is supplied by the embedded, already-tested read-only capture
    # core. It requires exact SSD/card/layout/new boot/unmounted/unheld media
    # and no active automounter both before and after the fixed ioctl.
    before=identity(plan)
    record=read_general_information()
    after=identity(plan)
    if before!=after: raise ValueError('Linux/card identity changed during control read')
    return dict(status='linux_reference_only',identity=before,general_information=record,
        userspace_cmd48_ioctls=1,userspace_write_commands=0,cache_admission=False,
        durability_verified=False,
        scope='Linux transport control only; not XNU transport, absent/disabled cache or durable writes')
