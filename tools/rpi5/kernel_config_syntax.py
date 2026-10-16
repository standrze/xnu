# SPDX-License-Identifier: BSD-2-Clause
"""Host syntax screen using XNU's unchanged OSUnserialize grammar and lexer.

Object builders are inert host stand-ins: this tests syntax only, never kernel
OSObject allocation, type semantics, service matching or device publication.
"""
from pathlib import Path
import hashlib
import struct
import subprocess
import tempfile

try:
    from .audit_macho import inspect as inspect_macho
except ImportError:
    from audit_macho import inspect as inspect_macho

ROOT = Path(__file__).resolve().parents[2]


def build_parser(work):
    original = (ROOT / 'libkern/c++/OSUnserialize.y').read_text()
    prologue = original[original.index('typedef\tstruct object'):original.index('__BEGIN_DECLS')]
    grammar = original[original.index('%token NUMBER'):original.index('static int\t\tlineNumber')]
    lexer = original[original.index('static int\t\tlineNumber'):original.index('// !@$')]
    # The original grammar and lexer above are not rewritten. Only kernel
    # allocation/build helpers are replaced in this isolated host harness.
    prelude = r'''
%{
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <iterator>
#include <string>
struct OSObject { void retain() {} };
'''
    helpers = r'''
static OSObject dummy;
static object_t *newObject() { return static_cast<object_t *>(std::calloc(1,sizeof(object_t))); }
static void freeObject(object_t *o) { std::free(o); }
static OSObject *buildOSDictionary(object_t *o) {
    while (o) { object_t *next=o->next; freeObject(o); o=next; }
    return &dummy;
}
static OSObject *buildOSArray(object_t *o) { return buildOSDictionary(o); }
static OSObject *buildOSSet(object_t *o) { return buildOSDictionary(o); }
static OSObject *buildOSString(object_t *o) { std::free(o); return &dummy; }
static OSObject *buildOSData(object_t *o) { std::free(o->object); freeObject(o); return &dummy; }
static OSObject *buildOSOffset(object_t *o) { freeObject(o); return &dummy; }
static OSObject *buildOSBoolean(object_t *) { return &dummy; }
static void rememberObject(int,object_t *) {}
static OSObject *retrieveObject(int) { return nullptr; }
int main() {
    std::string input((std::istreambuf_iterator<char>(std::cin)),std::istreambuf_iterator<char>());
    if (input.size()>65536) return 2;
    parseBuffer=input.c_str(); parseBufferIndex=0; parsedObject=nullptr;
    int result=yyparse();
    if (result || !parsedObject) { std::fputs(yyerror_message,stderr); return 1; }
    return 0;
}
'''
    # The lexer calls XNU's sized realloc/free wrappers; map their signatures
    # to the host allocator without altering the copied lexer.
    allocators = r'''
static void safe_free(void *p,size_t) { std::free(p); }
#define realloc(p, oldsize, newsize) std::realloc(p,newsize)
'''
    source = work / 'kernel-config-parser.y'
    source.write_text(prelude + prologue + '\n%}\n' + grammar + allocators + lexer + helpers)
    generated = work / 'kernel-config-parser.cpp'
    subprocess.run(['xcrun', 'bison', '-o', str(generated), str(source)], check=True, capture_output=True)
    executable = work / 'kernel-config-parser'
    subprocess.run(['xcrun', 'clang++', '-std=c++17', '-Wall', '-Wextra',
                    '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    str(generated), '-o', str(executable)], check=True, capture_output=True)
    return executable


def inspect_kernel_config(kernel, required_fragments=()):
    """Parse the string actually addressed by the linked kernel's global."""
    raw = kernel.read_bytes()
    segments = inspect_macho(raw)['segments']
    symbols = subprocess.check_output(['xcrun', 'nm', '-nm', str(kernel)], text=True).splitlines()
    matches = [int(line.split()[0], 16) for line in symbols if line.endswith(' _gIOKernelConfigTables')]
    if len(matches) != 1:
        raise ValueError('Missing or duplicate linked kernel config pointer')

    def location(address, length):
        owners = [s for s in segments if s['vmaddr'] <= address and
                  address+length <= s['vmaddr']+s['filesize']]
        if len(owners) != 1:
            raise ValueError('Kernel config pointer/string is not uniquely file-backed')
        s = owners[0]
        return s['fileoff']+address-s['vmaddr'], s['vmaddr']+s['filesize']-address

    offset, _ = location(matches[0], 8)
    target = struct.unpack_from('<Q', raw, offset)[0]
    offset, available = location(target, 1)
    end = raw.find(b'\0', offset, offset+min(65536, available))
    if end == -1:
        raise ValueError('Kernel config string exceeds bounded file-backed extent')
    table = raw[offset:end]
    with tempfile.TemporaryDirectory() as directory:
        parser = build_parser(Path(directory))
        result = subprocess.run([str(parser)], input=table, capture_output=True, timeout=30)
    return {'syntax_pass': result.returncode == 0, 'global_address': hex(matches[0]),
            'string_address': hex(target), 'table_sha256': hashlib.sha256(table).hexdigest(),
            'grammar_lexer_source_sha256': hashlib.sha256((ROOT / 'libkern/c++/OSUnserialize.y').read_bytes()).hexdigest(),
            'diagnostic': result.stderr.decode(errors='replace'),
            'required_fragments_present': {value: value.encode() in table for value in required_fragments},
            'scope': 'Actual linked global/string and XNU grammar/lexer; host builders do not prove IOKit runtime semantics'}
