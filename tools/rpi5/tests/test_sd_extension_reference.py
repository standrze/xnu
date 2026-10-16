# SPDX-License-Identifier: BSD-2-Clause
"""Fixed Linux CMD48 ioctl models; no device, network or card commands."""
import ctypes
import hashlib
import os
import stat
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.rpi5 import sd_extension_reference_core as core


class ExtensionReferenceTests(unittest.TestCase):
    def model(self,fault=None,payload=bytes(512)):
        calls=[]
        def ioctl(fd,request,buffer,*args):
            self.assertEqual(fd,73); calls.append(request)
            if request==0x80081272:
                return struct.pack('=Q',128177930240-(512 if fault=='capacity' else 0))
            self.assertEqual(request,0xc048b300); self.assertEqual(args,(True,))
            fields=list(struct.unpack('=iiII4I8IQ',buffer))
            self.assertEqual(fields[:16],[0,0,48,511,0,0,0,0,0x35,512,1,0,0,1000000000,1000,0])
            self.assertEqual(ctypes.string_at(fields[16],512),bytes([0xa5])*512)
            if fault=='ioctl': raise OSError('modeled Linux ioctl error')
            ctypes.memmove(fields[16],payload,512)
            fields[4]=0x400900 if fault=='r1' else 0x700 if fault=='state' else 0x900
            if fault=='metadata': fields[2]=49
            buffer[:]=struct.pack('=iiII4I8IQ',*fields)
            return 1 if fault=='return' else 0
        metadata=SimpleNamespace(st_mode=stat.S_IFREG if fault=='regular' else stat.S_IFBLK,st_rdev=179)
        with patch.object(core.platform,'machine',return_value='aarch64'), \
                patch.object(core.os,'open',return_value=73) as opened, \
                patch.object(core.os,'fstat',return_value=metadata), \
                patch.object(core.os,'stat',return_value=SimpleNamespace(st_rdev=180 if fault=='rdev' else 179)), \
                patch.object(core.os,'close') as closed,patch.object(core.fcntl,'ioctl',side_effect=ioctl):
            if fault:
                with self.assertRaises((ValueError,RuntimeError,OSError)): core.read_general_information()
            else:
                result=core.read_general_information()
                self.assertEqual(result['payload_hex'],payload.hex())
                self.assertEqual(result['payload_sha256'],hashlib.sha256(payload).hexdigest())
                self.assertIs(result['sentinel_unchanged'],payload==bytes([0xa5])*512)
            opened.assert_called_once_with('/dev/mmcblk0',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
            closed.assert_called_once_with(73)
        self.assertEqual(calls.count(0xc048b300),0 if fault in ('regular','rdev','capacity') else 1)

    def test_exact_read_only_descriptor_abi_command_and_complete_bytes(self):
        for data in (bytes(512),bytes(range(256))*2,bytes([0xa5])*512): self.model(payload=data)

    def test_failures_never_retry_or_issue_another_command(self):
        for fault in ('regular','rdev','capacity','ioctl','r1','state','metadata','return'):
            with self.subTest(fault=fault): self.model(fault)

    def test_wrong_architecture_stops_before_open(self):
        with patch.object(core.platform,'machine',return_value='x86_64'),patch.object(core.os,'open') as opened:
            with self.assertRaises(ValueError): core.read_general_information()
        opened.assert_not_called()

    def test_identity_checked_before_and_after_without_claiming_cache_admission(self):
        with patch.object(core,'identity',create=True,return_value={'exact':'current Linux'}) as identity, \
                patch.object(core,'read_general_information',return_value={'bytes':512}) as read:
            result=core.observe({'fixed':'plan'})
        self.assertEqual(identity.call_count,2); read.assert_called_once()
        self.assertIs(result['cache_admission'],False); self.assertIs(result['durability_verified'],False)
        with patch.object(core,'identity',create=True,side_effect=ValueError('wrong root')), \
                patch.object(core,'read_general_information') as read:
            with self.assertRaises(ValueError): core.observe({})
        read.assert_not_called()
        with patch.object(core,'identity',create=True,side_effect=[{'boot':1},{'boot':2}]), \
                patch.object(core,'read_general_information',return_value={}):
            with self.assertRaises(ValueError): core.observe({})


if __name__=='__main__': unittest.main()
