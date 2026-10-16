# SPDX-License-Identifier: BSD-2-Clause
"""Execute the actual kernel getter with native mount/attribute doubles.

Not a mockfs boot, real VFS dispatch, HFS mount or hardware acceptance test.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from tools.rpi5.tests.test_kernel_contracts import function_text

ROOT = Path(__file__).resolve().parents[3]


class MockfsStatfsTests(unittest.TestCase):
    def test_native_actual_getter_bounds_readonly_geometry_and_supported_attributes(self):
        getter = function_text('bsd/miscfs/mockfs/mockfs_vfsops.c','mockfs_vfs_getattr','static int')
        mount_header = (ROOT/'bsd/sys/mount.h').read_text()
        fields = ('f_bsize','f_iosize','f_blocks','f_bused','f_bfree','f_bavail','f_files','f_ffree','f_fssubtype')
        definitions = '\n'.join(re.search(r'^#define VFSATTR_'+field+r' .*$',mount_header,re.M).group()
                                for field in fields)
        definitions += '\n'+'\n'.join(re.search(r'^#define '+macro+r'\(.*$',mount_header,re.M).group()
                                        for macro in ('VFSATTR_SET_SUPPORTED','VFSATTR_RETURN'))
        harness = r'''
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <assert.h>
#include <string.h>
#include <miscfs/mockfs/rpi5_ramroot_format.h>
#ifndef __unused
#define __unused __attribute__((unused))
#endif
typedef void *vfs_context_t;
struct mockfs_mount { uint32_t ramroot_count; uint64_t ramroot_bytes; void *mockfs_root; };
typedef struct mockfs_mount *mockfs_mount_t;
struct mount { void *mnt_data; };
typedef struct mount *mount_t;
struct vfs_attr {
    uint64_t f_supported,f_bsize,f_iosize,f_blocks,f_bused,f_bfree,f_bavail,f_files,f_ffree,f_fssubtype;
};
''' + definitions + '\n' + getter + r'''
int main(void) {
    struct mockfs_mount data={.ramroot_count=4,.ramroot_bytes=2*RPI5_RFS_PAGE,.mockfs_root=&data};
    struct mount mount={&data}; struct vfs_attr attributes={0};
    uint64_t supported=VFSATTR_f_bsize|VFSATTR_f_iosize|VFSATTR_f_blocks|VFSATTR_f_bused|
        VFSATTR_f_bfree|VFSATTR_f_bavail|VFSATTR_f_files|VFSATTR_f_ffree|VFSATTR_f_fssubtype;
    for (uint64_t bytes=2*RPI5_RFS_PAGE;bytes<=RPI5_RFS_MAX;bytes+=RPI5_RFS_PAGE) {
        data.ramroot_bytes=bytes;
        for (unsigned count=4;count<=RPI5_RFS_NODES;count++) {
            data.ramroot_count=count; memset(&attributes,0xff,sizeof attributes); attributes.f_supported=0;
            assert(!mockfs_vfs_getattr(&mount,&attributes,0));
            assert(attributes.f_supported==supported && attributes.f_bsize==RPI5_RFS_PAGE &&
                attributes.f_iosize==RPI5_RFS_PAGE && attributes.f_blocks==bytes/RPI5_RFS_PAGE &&
                attributes.f_bused==attributes.f_blocks && !attributes.f_bfree && !attributes.f_bavail &&
                attributes.f_files==count && !attributes.f_ffree && !attributes.f_fssubtype);
        }
    }
    const uint64_t bad[]={0,RPI5_RFS_PAGE,2*RPI5_RFS_PAGE+1,RPI5_RFS_MAX+RPI5_RFS_PAGE,UINT64_MAX};
    for (unsigned i=0;i<sizeof bad/sizeof bad[0];i++) {
        data.ramroot_bytes=bad[i]; attributes=(struct vfs_attr){0};
        assert(mockfs_vfs_getattr(&mount,&attributes,0)==EIO && !attributes.f_supported);
    }
    data.ramroot_bytes=2*RPI5_RFS_PAGE; data.ramroot_count=RPI5_RFS_NODES+1;
    assert(mockfs_vfs_getattr(&mount,&attributes,0)==EIO);
    data.ramroot_count=1; assert(mockfs_vfs_getattr(&mount,&attributes,0)==EIO);
    data.ramroot_count=4; data.mockfs_root=0;
    assert(mockfs_vfs_getattr(&mount,&attributes,0)==EIO);
    data.ramroot_count=0;
    assert(mockfs_vfs_getattr(&mount,&attributes,0)==ENOTSUP);
    mount.mnt_data=0; assert(mockfs_vfs_getattr(&mount,&attributes,0)==ENOTSUP);
    assert(mockfs_vfs_getattr(0,&attributes,0)==EINVAL);
    assert(mockfs_vfs_getattr(&mount,0,0)==EINVAL);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source,binary = Path(directory)/'statfs.c',Path(directory)/'statfs'
            source.write_text(harness)
            subprocess.run(['xcrun','clang','-std=c11','-Wall','-Wextra','-Werror',
                            '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                            '-I',str(ROOT/'bsd'),str(source),'-o',str(binary)],check=True)
            result = subprocess.run([str(binary)],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr.decode())

    def test_getter_is_wired_only_for_archive_profile_and_extent_is_saved_before_publish(self):
        source = (ROOT/'bsd/miscfs/mockfs/mockfs_vfsops.c').read_text()
        self.assertRegex(source,r'#if MOCKFS_RPI5_RAMROOT\s+\.vfs_getattr = mockfs_vfs_getattr,\s+#endif')
        mounted = function_text('bsd/miscfs/mockfs/mockfs_vfsops.c','mockfs_ramroot_mount','static int')
        self.assertLess(mounted.index('data->ramroot_bytes = bytes;'),mounted.index('mp->mnt_data ='))


if __name__ == '__main__':
    unittest.main()
