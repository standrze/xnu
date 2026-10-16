# SPDX-License-Identifier: BSD-2-Clause
import ctypes as C
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"tools/rpi5"))
from payload_container import encode

class Payload(C.Structure):
    _fields_=[("offset",C.c_uint64),("length",C.c_uint64)]

class Container(C.Structure):
    _fields_=[("kernel",Payload),("init",Payload),("count",C.c_uint32)]


class LoaderSHA256Tests(unittest.TestCase):
    def test_reference_vectors(self):
        source=ROOT/"build/rpi5/bearssl-candidate"
        if not source.exists():
            self.skipTest("pinned BearSSL candidate not downloaded")
        self.assertEqual(subprocess.check_output(["git","-C",str(source),"rev-parse","HEAD"],text=True).strip(),"7bea48e5e850ab4cafbe68d3765cdaba13a86d6f")
        with tempfile.TemporaryDirectory() as directory:
            library=Path(directory)/"hash.dylib"
            subprocess.run(["xcrun","clang","-dynamiclib","-O2","-Wall","-Wextra","-Werror",
                "-I"+str(source/"src"),"-I"+str(source/"inc"),str(ROOT/"loader/rpi5/hash.c"),str(ROOT/"loader/rpi5/container.c"),
                *[str(source/"src"/unit) for unit in ("hash/sha2small.c","codec/dec32be.c","codec/enc32be.c")],
                "-o",str(library)],check=True)
            loaded=C.CDLL(str(library))
            digest=loaded.rpi5_sha256
            digest.argtypes=[C.c_void_p,C.c_size_t,C.c_void_p]; digest.restype=C.c_int
            for length in list(range(260))+[4096,65536,262143,262144,262145,524288,1000000]:
                data=bytes(i%251 for i in range(length))
                buffer=C.create_string_buffer(data); output=C.create_string_buffer(32)
                self.assertEqual(digest(buffer,length,output),0)
                self.assertEqual(output.raw,hashlib.sha256(data).digest())
            output=C.create_string_buffer(b"x"*32,32)
            self.assertEqual(digest(None,1,output),-1)
            self.assertEqual(output.raw,b"x"*32)
            self.assertEqual(digest(None,0,output),0)
            self.assertEqual(output.raw,hashlib.sha256(b"").digest())
            parse=loaded.rpi5_container_parse
            parse.argtypes=[C.c_void_p,C.c_size_t,C.POINTER(Container)]; parse.restype=C.c_int
            for init in (None,b"init"):
                packed=encode(b"kernel",init)
                buf=C.create_string_buffer(packed); result=Container()
                self.assertEqual(parse(buf,len(packed),C.byref(result)),0)
                self.assertEqual(result.count,1 if init is None else 2)
                self.assertEqual(packed[result.kernel.offset:result.kernel.offset+result.kernel.length],b"kernel")
                if init: self.assertEqual(packed[result.init.offset:result.init.offset+result.init.length],init)
                prior=bytes(result)
                for length in range(len(packed)):
                    self.assertEqual(parse(buf,length,C.byref(result)),-1)
                    self.assertEqual(bytes(result),prior)
                for index in (0,8,12,16,24,28,32,64,72,80,88,len(packed)-1):
                    bad=bytearray(packed); bad[index]^=1; mutation=C.create_string_buffer(bytes(bad))
                    self.assertEqual(parse(mutation,len(bad),C.byref(result)),-1)
                    self.assertEqual(bytes(result),prior)
                # Rehash malformed entries: structural rejection must not rely
                # solely on the metadata checksum failing.
                for index in (64,68,72,80,120):
                    bad=bytearray(packed); bad[index]^=1
                    table_end=64+64*result.count
                    bad[32:64]=hashlib.sha256(bad[64:table_end]).digest()
                    mutation=C.create_string_buffer(bytes(bad))
                    self.assertEqual(parse(mutation,len(bad),C.byref(result)),-1)
                    self.assertEqual(bytes(result),prior)
