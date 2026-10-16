# SPDX-License-Identifier: BSD-2-Clause
"""Bounded future file batch: syscall doubles and real Darwin ABI compile only."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]


class HFSWriteTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.binary=Path(cls.tmp.name)/'hfswrite'
        subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                        '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                        str(ROOT/'tools/rpi5/tests/hfswrite_host.c'),
                        str(ROOT/'tools/rpi5/user/hfswrite.c'),'-o',str(cls.binary)],check=True)

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def run_batch(self,*args,mode=''):
        result=subprocess.run([str(self.binary),*args],capture_output=True,timeout=10,
                              env={**os.environ,'HFSWRITE_FIXTURE':mode})
        self.assertNotIn(b'Sanitizer',result.stderr)
        return result

    def test_batch_has_exact_final_contents_and_only_fsync_marker(self):
        for mode in ('','partial'):
            result=self.run_batch('exercise',mode=mode)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,b'RPI5XNU:HFSWRITE:BATCH_FSYNCED FILES=5 RAW_WRITES=0 DURABILITY_VERIFIED=0\n')

    def test_invalid_arguments_never_make_syscalls(self):
        for args in ((),('write',),('exercise','/elsewhere'),('/dev/disk0s2',)):
            result=self.run_batch(*args)
            self.assertEqual(result.returncode,2,result.stderr)
            self.assertIn(b'STATS=0 DEVICE_OPENS=0 FILE_OPENS=0 CLOSES=0 IOCTLS=0 WRITES=0 SYNCS=0',result.stderr)

    def test_exact_mount_and_writable_partition_guards_precede_all_file_writes(self):
        for mode in ('stat','type','target','source','readonly','flags','unterminated','device-open',
                     'device-close','ioctl','blocksize','capacity','write-protect'):
            result=self.run_batch('exercise',mode=mode)
            self.assertEqual(result.returncode,1,result.stderr)
            self.assertEqual(result.stdout,b'')
            self.assertIn(b'FILE_OPENS=0',result.stderr); self.assertIn(b'WRITES=0 SYNCS=0',result.stderr)

    def test_any_file_write_read_sync_or_close_failure_emits_no_batch_marker(self):
        for mode in ('file-open','exists','write','zero-write','stalled-partial','fsync','file-close',
                     'read','short-eof','extra-eof','corrupt','overwrite-open','append-open',
                     'append-write','late-fsync','late-close','late-corrupt'):
            result=self.run_batch('exercise',mode=mode)
            self.assertEqual(result.returncode,1,result.stderr)
            self.assertEqual(result.stdout,b'')
            if mode=='stalled-partial': self.assertIn(b'WRITES=16 SYNCS=0',result.stderr)

    def test_real_darwin_freestanding_compile_has_only_runtime_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            obj=Path(directory)/'hfswrite.o'
            sdk=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()
            subprocess.run(['xcrun','clang','-isysroot',sdk,'-target','arm64-apple-darwin','-c','-Os',
                            '-ffreestanding','-fno-builtin','-fno-stack-protector','-Wall','-Wextra','-Werror',
                            str(ROOT/'tools/rpi5/user/hfswrite.c'),'-o',str(obj)],check=True)
            symbols=set(subprocess.check_output(['xcrun','nm','-ju',str(obj)],text=True).splitlines())
            self.assertEqual(symbols,{'_rt_call','_rt_open','_rt_close','_rt_read','_rt_write','_rt_error','_rt_equal','_rt_put'})


if __name__=='__main__': unittest.main()
