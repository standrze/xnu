# SPDX-License-Identifier: BSD-2-Clause
"""Inspect target bytes; execute only separately linked native sanitizer tests."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tools.rpi5.prepare_pid1 import inspect

ROOT = Path(__file__).resolve().parents[3]
TARGET = Path(os.environ.get("RPI5_SSH_PROBE", ROOT / "build/rpi5/apple-ssh-probe-dx1kcy5m"))
BASE = ROOT / "build/rpi5/apple-ssh-reset-7j7hbjqx"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class SSHStaticProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp(prefix="ssh-static-audit-", dir=ROOT / "build/rpi5"))
        cls.program = TARGET / "sshbufferprobe"
        cls.data = cls.program.read_bytes()
        cls.audit = inspect(cls.data)
        cls.manifest = json.loads((TARGET / "manifest.json").read_text())
        cls.commands = []
        cls.completed = []
        cls.pins = {str(cls.program): sha(cls.program), str(TARGET / "manifest.json"): sha(TARGET / "manifest.json"),
                    str(TARGET / "link.map"): sha(TARGET / "link.map"), str(Path(__file__)): sha(__file__)}
        cls.segments = []
        cls.symbols = {}
        offset = 32
        for _ in range(struct.unpack_from("<I", cls.data, 16)[0]):
            command, length = struct.unpack_from("<II", cls.data, offset)
            if command == 0x19:
                cls.segments.append(struct.unpack_from("<4Q", cls.data, offset + 24))
            elif command == 2:
                symoff, nsyms, stroff, strsize = struct.unpack_from("<4I", cls.data, offset + 8)
                for index in range(nsyms):
                    strx, kind, section, desc, address = struct.unpack_from("<IBBHQ", cls.data, symoff + 16 * index)
                    end = cls.data.index(b"\0", stroff + strx, stroff + strsize)
                    name = cls.data[stroff + strx:end].decode("ascii")
                    cls.symbols[name] = address
            offset += length
        base = json.loads((BASE / "manifest.json").read_text())
        reference = base["commands"][1]["command"]
        cls.common = reference[:reference.index("-target")]

    @classmethod
    def tearDownClass(cls):
        report = dict(target=str(cls.program), target_audit=cls.audit,
                      checks_passed=cls.completed, commands=cls.commands,
                      inputs_sha256=cls.pins,
                      generated_sha256={str(p): sha(p) for p in cls.out.iterdir() if p.is_file()},
                      target_executed=False, pi_executed=False, installed=False,
                      full_ssh_server_or_transport_tested=False,
                      scope="Mach-O/instruction audit plus separately linked native sanitizer programs; no Pi execution")
        (cls.out / "validation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print("SSH_STATIC_AUDIT=" + str(cls.out / "validation.json"))

    @classmethod
    def run_command(cls, args, label):
        args = list(map(str, args))
        result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=60)
        (cls.out / (label + ".stdout")).write_text(result.stdout)
        (cls.out / (label + ".stderr")).write_text(result.stderr)
        cls.commands.append(dict(command=args, returncode=result.returncode,
                                 stdout=str(cls.out / (label + ".stdout")), stderr=str(cls.out / (label + ".stderr"))))
        if result.returncode:
            raise AssertionError(label + " failed: " + result.stderr)
        return result

    @classmethod
    def words(cls, name, count):
        address = cls.symbols[name]
        mappings = [(fileoff + address - vmaddr, filesize - (address - vmaddr))
                    for vmaddr, vmsize, fileoff, filesize in cls.segments if vmaddr <= address < vmaddr + filesize]
        if len(mappings) != 1 or mappings[0][1] < count * 4:
            raise AssertionError("Function has no bounded file mapping: " + name)
        return struct.unpack_from("<" + "I" * count, cls.data, mappings[0][0])

    @classmethod
    def calls(cls, name, count, include_tail_calls=False):
        result = []
        for index, word in enumerate(cls.words(name, count)):
            if word & 0xfc000000 == 0x94000000 or (include_tail_calls and word & 0xfc000000 == 0x14000000):
                displacement = word & 0x03ffffff
                if displacement & 0x02000000:
                    displacement -= 0x04000000
                result.append(cls.symbols[name] + index * 4 + displacement * 4)
        return result

    def test_static_layout_entry_and_no_dynamic_or_thread_imports(self):
        self.assertEqual(self.audit["entry_pc"], self.symbols["_start"])
        self.assertEqual(self.manifest["link_returncode"], 0)
        self.assertEqual(self.manifest["linker_missing_symbols"], [])
        linkmap = (TARGET / "link.map").read_text()
        for name in ("_pthread_key_create", "_pthread_setspecific", "_pthread_getspecific", "_pthread_key_delete"):
            self.assertNotIn(name, self.symbols)
            self.assertRegex(linkmap, r"<<dead>>[^\n]+" + name)
        for name in ("_sshbuf_new", "_sshbuf_reset", "_recallocarray", "_explicit_bzero", "_memset_s", "_raise",
                     "_strsignal", "_syslog$DARWIN_EXTSN", "_strnvis"):
            self.assertIn(name, self.symbols)
        self.completed.append(self._testMethodName)

    def test_real_syscall_numbers_error_path_and_tsd(self):
        master = (ROOT / "bsd/kern/syscalls.master").read_text()
        self.pins[str(ROOT / "bsd/kern/syscalls.master")] = sha(ROOT / "bsd/kern/syscalls.master")
        for name, number in (("socket", 97), ("connect", 98), ("sendto", 133), ("writev", 121)):
            words = self.words("_" + name, 10)
            self.assertEqual(words[0], 0xd2800010 | (number << 5))  # mov x16, #syscall
            self.assertEqual(words[1], 0xd4001001)  # svc #0x80
            self.assertEqual(words[2], 0x540000e3)  # b.cc to success ret
            self.assertEqual(words[-1], 0xd65f03c0)
            self.assertIn(self.symbols["_cerror_nocancel"], self.calls("_" + name, 10))
            self.assertRegex(master, rf"(?m)^{number}\s+[^\n]+\b{name}\(")
        cerror = self.words("_cerror_nocancel", 10)
        self.assertIn(0xd53bd068, cerror)  # mrs x8, TPIDRRO_EL0
        self.assertIn(0x92800000, cerror)  # mov x0, #-1
        self.assertIn(0xb9000100, cerror)  # str w0, [x8] writes real errno
        self.completed.append(self._testMethodName)

    def test_startup_real_entropy_entry_and_secure_erase_calls(self):
        start = self.words("_start", 6)
        self.assertEqual(start[0], 0x910003e0)  # pass original process stack
        self.assertEqual(start[2], 0x927ced29)  # align stack to sixteen bytes
        self.assertIn(self.symbols["_darwin_static_start"], self.calls("_start", 6))
        startup_calls = self.calls("_darwin_static_start", 75)
        for name in ("__thread_set_tsd_base", "_darwin_task_self", "_getentropy", "_zsh_main", "_exit"):
            self.assertIn(self.symbols[name], startup_calls)
        self.assertIn(self.symbols["_memset"], self.calls("_memset_s", 24))
        self.assertIn(self.symbols["_kill"], self.calls("_raise", 9, include_tail_calls=True))
        self.completed.append(self._testMethodName)

    def test_actual_probe_native_with_preserved_buffer_objects_and_sanitizers(self):
        source = ROOT / "tools/rpi5/user/sshbufferprobe.c"
        objects = [BASE / (str(i) + "-native.o") for i in range(12)]
        for path in (source, *objects):
            self.pins[str(path)] = sha(path)
        program = self.out / "native-sshbufferprobe"
        self.run_command(self.common + ["-O1", "-g", "-fsanitize=address,undefined", source, *objects,
                                       "-Wl,-dead_strip", "-o", program], "native-link")
        result = self.run_command([program], "native-run")
        self.assertEqual(result.stdout.splitlines(), [
            "RPI5XNU:SSHBUFFER:BEGIN ORIGINAL_BUFFERS RESET_OVERLAY NO_NETWORK NO_KEYS",
            "RPI5XNU:SSHBUFFER:PASS ROUNDTRIP LOW_MAX_RESET REUSE NOT_SSH_OR_CRYPTO_PROOF"])
        self.assertEqual(result.stderr, "")
        self.completed.append(self._testMethodName)

    def test_actual_modern_memset_s_provider_bounds_and_erasure(self):
        source = ROOT / "experiments/darwin-container/userland/upstream/apple-Libc-1752.120.2/string/NetBSD/memset_s.c"
        adornments = ROOT / "tools/rpi5/user/ssh_runtime_build.h"
        for path in (source, adornments):
            self.pins[str(path)] = sha(path)
        harness = self.out / "memset-host.c"
        harness.write_text(r'''#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
int memset_s(void *, size_t, int, size_t);
int main(void) {
    unsigned char b[18]; memset(b, 0xa5, sizeof b);
    assert(memset_s(NULL, 8, 0, 8) == EINVAL);
    assert(memset_s(b + 1, SIZE_MAX, 0, 1) == E2BIG);
    for (unsigned i = 0; i < sizeof b; i++) assert(b[i] == 0xa5);
    assert(memset_s(b + 1, 16, 0, 16) == 0);
    for (unsigned i = 1; i < 17; i++) assert(b[i] == 0);
    assert(b[0] == 0xa5 && b[17] == 0xa5);
    assert(memset_s(b + 1, 16, 0x5a, 17) == EOVERFLOW);
    for (unsigned i = 1; i < 17; i++) assert(b[i] == 0x5a);
    assert(b[0] == 0xa5 && b[17] == 0xa5);
    assert(memset_s(b + 1, 16, 0, SIZE_MAX) == E2BIG);
    for (unsigned i = 1; i < 17; i++) assert(b[i] == 0);
    assert(memset_s(b + 1, 0, 0x55, 1) == EOVERFLOW);
    assert(b[1] == 0 && b[0] == 0xa5 && b[17] == 0xa5);
    return 0;
}
''')
        obj = self.out / "memset-native.o"
        program = self.out / "memset-native-test"
        self.run_command(self.common + ["-O1", "-g", "-fsanitize=address,undefined",
                                       "-include", adornments, "-c", source, "-o", obj], "memset-native-compile")
        self.run_command(self.common + ["-O1", "-g", "-fsanitize=address,undefined", harness, obj, "-o", program],
                         "memset-native-link")
        result = self.run_command([program], "memset-native-run")
        self.assertEqual(result.stdout + result.stderr, "")
        self.completed.append(self._testMethodName)


if __name__ == "__main__":
    unittest.main()
