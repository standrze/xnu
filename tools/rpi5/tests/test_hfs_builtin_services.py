# SPDX-License-Identifier: BSD-2-Clause
"""Execute the patched service methods with host doubles, not IOKit/VFS proof."""
import platform
import re
import subprocess
import tempfile
from pathlib import Path
import unittest

from tools.rpi5.tests import test_storage_build_audit as storage_audit
from tools.rpi5.audit_storage_build import ROOT, staged_hfs


def function(text, name):
    start = text.index(name)
    end = text.index('\n}\n', start) + 3
    return text[start:end]


@unittest.skipUnless(platform.system() == 'Darwin', 'Requires native sanitizer compiler')
class HFSBuiltinServicesTests(unittest.TestCase):
    def test_native_resource_match_requires_every_dependency(self):
        # Execute XNU's unmodified matching function with host objects. This
        # checks its array/all-of logic, not OSObject/IOKit scheduling on Pi.
        text = (ROOT / 'iokit/Kernel/IOService.cpp').read_text()
        matcher = function(text, 'static bool\nIOResourcesMatchPropertyTable')
        harness = r'''
#include <cassert>
#include <cstring>
#include <initializer_list>
#include <set>
#include <string>
#include <vector>
struct OSObject {
    virtual ~OSObject() = default;
    virtual void iterateObjects(bool (^callback)(OSObject *)) { callback(this); }
};
struct OSString : OSObject {
    const char *value;
    explicit OSString(const char *v): value(v) {}
};
struct OSArray : OSObject {
    std::vector<OSObject *> values;
    explicit OSArray(std::initializer_list<OSObject *> v): values(v) {}
    void iterateObjects(bool (^callback)(OSObject *)) override {
        for (auto v: values) if (callback(v)) break;
    }
    unsigned getNextIndexOfObject(OSObject *v, unsigned) {
        for (unsigned i=0; i<values.size(); ++i) if (values[i] == v) return i;
        return -1U;
    }
};
struct OSDictionary {
    OSObject *match;
    OSObject *getObject(const char *key) {
        return std::strcmp(key, "match") == 0 ? match : nullptr;
    }
};
struct IOService {
    std::set<std::string> resources;
    OSObject *getProperty(OSString *name) {
        assert(name); return resources.count(name->value) ? name : nullptr;
    }
    OSObject *copyProperty(const char *) { return nullptr; }
};
static const char *gIOResourceMatchKey = "match", *gIOResourceMatchedKey = "matched";
#define OSDynamicCast(type, value) dynamic_cast<type *>(value)
#define OSSafeReleaseNULL(value) ((void)(value))
''' + matcher + r'''
int main() {
    OSString bsd("IOBSD"), converters("RPI5HFSEncodingsReady");
    OSArray requirements({&bsd, &converters});
    OSDictionary hfs{&requirements}, enc{&bsd};
    IOService root;
    assert(!IOResourcesMatchPropertyTable(&root, &enc));
    assert(!IOResourcesMatchPropertyTable(&root, &hfs));
    root.resources.insert("IOBSD");
    assert(IOResourcesMatchPropertyTable(&root, &enc));
    assert(!IOResourcesMatchPropertyTable(&root, &hfs));
    root.resources.insert("RPI5HFSEncodingsReady");
    assert(IOResourcesMatchPropertyTable(&root, &hfs));
    root.resources.erase("IOBSD");
    assert(!IOResourcesMatchPropertyTable(&root, &hfs));
}
'''
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            program, binary = work / 'matching.cpp', work / 'matching'
            program.write_text(harness)
            result = subprocess.run(['xcrun', 'clang++', '-std=c++17', '-fblocks',
                                     '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                                     str(program), '-o', str(binary)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            result = subprocess.run([str(binary)], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_actual_service_methods_gate_order_failure_and_permanent_lifetime(self):
        source, _ = storage_audit.StorageAuditTests().hfs_source()
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            staged = staged_hfs(source, work)
            hfs = (staged / 'core/hfs_iokit.cpp').read_text()
            enc = (staged / 'hfs_encodings/hfs_encodings_kext.cpp').read_text()
            helper = (staged / 'core/rpi5_hfs_builtin.h').read_text()
            helper = re.sub(r'^#include .*\n', '', helper, flags=re.M)
            classes = ''
            methods = ''
            for text, name in ((hfs, 'com_apple_filesystems_hfs'),
                               (enc, 'com_apple_filesystems_hfs_encodings')):
                start = text.index('class ' + name + ' :')
                classes += text[start:text.index('\n};', start) + 4] + '\n'
                methods += function(text, 'bool ' + name + '::start') + '\n'
                methods += function(text, 'void ' + name + '::stop') + '\n'
            flags = ''.join('#define ' + flag + ' 1\n'
                            for flag in sorted(set(re.findall(r'\bVFS_TBL[A-Z0-9_]+', methods))))
            harness = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
using UInt32 = uint32_t;
using IOOptionBits = unsigned;
using vfstable_t = void *;
#define OSDeclareDefaultStructors(name)
#define super IOService
#define FIFO 1
#define DEBUG 0
#define kPEICanHasAssertions 1
#define MAX_CACHED_ORIGINS_DEFAULT 8
#define MAX_CACHED_FILE_ORIGINS_DEFAULT 4
static bool panic_on_assert;
static uint32_t _hfs_max_origins, _hfs_max_file_origins;
static bool present = true, super_ok = true, fail_add;
static int boot_value = 1, converter_inits, converter_dones, zone_inits;
static int adds, removes, super_starts, super_stops;
static bool enc_ready, hfs_ready;
static std::vector<std::string> events;
static const void *kOSBooleanTrue = reinterpret_cast<void *>(1);
bool PE_parse_boot_argn(const char *key, void *out, int size) {
    assert(std::strcmp(key, "bcm2712_hfs") == 0 && size == sizeof(int));
    if (present) *static_cast<int *>(out) = boot_value;
    return present;
}
unsigned PE_i_can_has_kernel_configuration() { return 1; }
bool OSCompareAndSwap(UInt32 old, UInt32 value, volatile UInt32 *ptr) {
    return __atomic_compare_exchange_n(ptr, &old, value, false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
}
class IOService {
public:
    virtual ~IOService() = default;
    virtual bool start(IOService *) { ++super_starts; return super_ok; }
    virtual void stop(IOService *) { ++super_stops; }
    virtual bool terminate(IOOptionBits = 0) { return true; }
    virtual bool requestTerminate(IOService *, IOOptionBits) { return true; }
    static void publishResource(const char *name, const void *value) {
        assert(value == kOSBooleanTrue);
        events.emplace_back(name);
        if (std::strcmp(name, "RPI5HFSEncodingsReady") == 0) {
            assert(converter_inits == 1); enc_ready = true;
        } else {
            assert(std::strcmp(name, "RPI5HFSRegistered") == 0);
            assert(enc_ready && adds == 1 && !fail_add); hfs_ready = true;
        }
    }
};
struct vnodeopv_desc {};
static vnodeopv_desc hfs_vnodeop_opv_desc, hfs_specop_opv_desc, hfs_fifoop_opv_desc;
struct vfsops {};
static vfsops hfs_vfsops;
struct vfs_fsentry {
    vfsops *vfe_vfsops;
    unsigned long vfe_vopcnt;
    vnodeopv_desc **vfe_opvdescs;
    const char *vfe_fsname;
    unsigned vfe_flags;
};
void hfs_converterinit() { assert(!enc_ready); ++converter_inits; events.emplace_back("converters"); }
void hfs_converterdone() { ++converter_dones; }
void hfs_init_zones() { assert(enc_ready); ++zone_inits; events.emplace_back("zones"); }
int vfs_fsadd(vfs_fsentry *vfe, vfstable_t *out) {
    assert(enc_ready && zone_inits == 1 && !hfs_ready);
    assert(std::strcmp(vfe->vfe_fsname, "hfs") == 0 && vfe->vfe_vopcnt == 3);
    ++adds; events.emplace_back("vfsadd");
    if (fail_add) return 5;
    *out = reinterpret_cast<void *>(2); return 0;
}
void vfs_fsremove(vfstable_t) { ++removes; }
int kernel_sysctlbyname(const char *, void *, size_t *, void *, size_t) { return -1; }
''' + flags + helper + classes + methods + r'''
int main(int argc, char **argv) {
    assert(argc == 2);
    const std::string mode = argv[1];
    IOService provider;
    com_apple_filesystems_hfs_encodings enc;
    com_apple_filesystems_hfs hfs;
    if (mode == "missing" || mode == "zero" || mode == "two") {
        present = mode != "missing";
        boot_value = mode == "two" ? 2 : 0;
        assert(!enc.start(&provider) && !hfs.start(&provider));
        assert(super_starts == 0 && events.empty());
        return 0;
    }
    if (mode == "super-failure") {
        super_ok = false;
        assert(!enc.start(&provider) && !hfs.start(&provider));
        assert(events.empty());
        super_ok = true; // No claim was consumed before super::start succeeded.
    }
    fail_add = mode == "registration-failure";
    assert(enc.start(&provider));
    assert(hfs.start(&provider) == !fail_add);
    assert(!enc.start(&provider) && !hfs.start(&provider));
    assert(converter_inits == 1 && zone_inits == 1 && adds == 1);
    assert(enc_ready && hfs_ready == !fail_add);
    std::vector<std::string> expected = {"converters", "RPI5HFSEncodingsReady", "zones", "vfsadd"};
    if (!fail_add) expected.emplace_back("RPI5HFSRegistered");
    assert(events == expected);
    assert(!enc.terminate() && !hfs.terminate());
    assert(!enc.requestTerminate(&provider, 0) && !hfs.requestTerminate(&provider, 0));
    enc.stop(&provider); hfs.stop(&provider);
    assert(converter_dones == 0 && removes == 0 && super_stops == 2);
    assert(!enc.start(&provider) && !hfs.start(&provider));
    assert(converter_inits == 1 && zone_inits == 1 && adds == 1);
}
'''
            program, binary = work / 'services.cpp', work / 'services'
            program.write_text(harness)
            compiled = subprocess.run(['xcrun', 'clang++', '-std=gnu++20', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-DRPI5_HFS_BUILTIN=1',
                            str(program), '-o', str(binary)], capture_output=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr.decode())
            for mode in ('missing', 'zero', 'two', 'success', 'super-failure', 'registration-failure'):
                result = subprocess.run([str(binary), mode], capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, (mode, result.stdout, result.stderr))
