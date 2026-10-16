# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]

class CryptoTableTests(unittest.TestCase):
    def test_all_declared_slots_explicit(self):
        header=(ROOT/'libkern/libkern/crypto/register_crypto.h').read_text()
        body=header.split('typedef struct crypto_functions {',1)[1].split('} *crypto_functions_t;',1)[0]
        body=re.sub(r'/\*.*?\*/|//[^\n]*','',body,flags=re.S)
        fields=re.findall(r'\b(\w+)\s*;',body)
        self.assertEqual(len(fields),56)
        source=(ROOT/'osfmk/prng/rpi5_crypto_table.c').read_text()
        mappings=re.findall(r'\.(\w+)\s*=\s*(&?\w+)\s*,',source)
        self.assertEqual(len(mappings),len(fields))
        self.assertEqual(set(fields),{name for name,_ in mappings})
        self.assertTrue(all(value.startswith(('rpi5_','&rpi5_')) for _,value in mappings))
        self.assertNotRegex(source,r'\bregister_crypto_functions\s*\(')
        self.assertNotRegex(source,r'\bSTARTUP\s*\(')

    def test_missing_slot_rejected(self):
        header=(ROOT/'libkern/libkern/crypto/register_crypto.h').read_text()
        body=header.split('typedef struct crypto_functions {',1)[1].split('} *crypto_functions_t;',1)[0]
        body=re.sub(r'/\*.*?\*/|//[^\n]*','',body,flags=re.S)
        fields=re.findall(r'\b(\w+)\s*;',body)
        # These non-NULL sentinels are never called or dereferenced: this
        # checks presence only, not callable implementations.
        source='#include <libkern/crypto/rpi5_crypto_slots.h>\n#include <assert.h>\nint main(void) {\n'
        source+='struct crypto_functions f={0}; assert(!rpi5_crypto_slots_present(NULL)); assert(!rpi5_crypto_slots_present(&f));\n'
        source+='\n'.join(f'f.{name}=(__typeof__(f.{name}))1;' for name in fields)
        source+='\nassert(rpi5_crypto_slots_present(&f));\n'
        for name in fields:
            source+=f'f.{name}=NULL; assert(!rpi5_crypto_slots_present(&f)); f.{name}=(__typeof__(f.{name}))1;\n'
        source+='}\n'
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory); (p/'test.c').write_text(source)
            subprocess.run(['xcrun','clang','-Wall','-Wextra','-Werror',
                '-I'+str(ROOT/'libkern'),'-I'+str(ROOT/'EXTERNAL_HEADERS'),
                str(p/'test.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
