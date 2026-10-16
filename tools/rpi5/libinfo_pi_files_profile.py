# SPDX-License-Identifier: BSD-2-Clause
"""Explicit Pi service composition; never an unmodified macOS Libinfo claim."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'build/rpi5/apple-libinfo-main-candidate-20261013'
PROFILE='pi-libinfo600-static-files-stat-validation-v1'
MACROS=('DEBUG=0','__DARWIN_NON_CANCELABLE=1','__MigTypeCheck=1','INET6=1','CONFIG_MAC',
        'RPI5_LIBINFO_FILE_STAT_VALIDATION=1')
FIXTURES={
    'master.passwd':'root:*:0:0::0:0:System Administrator:/var/root:/bin/zsh\nsandrzej:*:501:20::0:0:Pi Fixture User:/Users/sandrzej:/bin/zsh\n',
    'passwd':'root:*:0:0:System Administrator:/var/root:/bin/zsh\nsandrzej:*:501:20:Pi Fixture User:/Users/sandrzej:/bin/zsh\n',
    'group':'wheel:*:0:root\nstaff:*:20:sandrzej\nfixture:*:80:root,sandrzej\n',
    'hosts':'127.0.0.1 localhost\n::1 localhost\n192.0.2.23 pi-fixture.example pi-fixture\n',
    'services':'ssh 22/tcp\nfixture 4242/udp\n',
    'protocols':'tcp 6 TCP\nudp 17 UDP\n',
    'sysinfo.conf':'default: cache file\nuser: cache file\ngroup: cache file\ngrouplist: cache file\nhost: cache file\nservice: cache file\naddrinfo: cache file\nnameinfo: cache file\n',
}


def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Original Libinfo configuration boundary changed: '+old[:70])
    return text.replace(old,new)


def transform(name,text):
    if name=='si_module.c':
        text=once(text,'#include <dispatch/private.h>',
                  '#include "rpi5_dispatch_queue_flags.h" /* Exact original private enum, no runtime replacement. */')
        text=once(text,'\t\t{ "mdns", si_module_static_mdns, NULL },\n','')
        start=text.index('\n\tpthread_mutex_lock(&module_mutex);',text.index('si_module_with_name(const char *name)'))
        end=text.index('\n}\n\nLIBINFO_EXPORT\nsi_mod_t *\nsi_module_retain',start)
        # Static inventory is an explicit platform feature. Unknown providers
        # fail; no empty module/vtable or successful DNS answer is fabricated.
        text=text[:start]+'\n\t/* Pi static service composition: plugins are not installed. */\n\terrno = ENOTSUP;\n\treturn NULL;'+text[end:]
    elif name=='search_module.c':
        text=once(text,'\t\t\t"mdns",\n','')
    elif name=='file_module.c':
        text=once(text,'if (bit & pp->validation_notify_mask)',
                  'if (!RPI5_LIBINFO_FILE_STAT_VALIDATION && (bit & pp->validation_notify_mask))')
        text=once(text,'if (pp->notify_token[vtype] < 0)\n\t{\n\t\tpath = _fsi_validation_path(vtype);',
                  'if (RPI5_LIBINFO_FILE_STAT_VALIDATION || pp->notify_token[vtype] < 0)\n\t{\n\t\tpath = _fsi_validation_path(vtype);')
        text=once(text,'pp->validation_notify_mask = VALIDATION_MASK_HOSTS | VALIDATION_MASK_SERVICES | VALIDATION_MASK_PROTOCOLS;',
                  'pp->validation_notify_mask = 0; /* Pi: genuine stat/mtime validation for all files. */')
    elif name=='darwin_directory_enabled.h':
        text=once(text,'#include <os/feature_private.h>\n#include <os/variant_private.h>',
                  '#include <os/base.h>\n#ifdef DARWIN_DIRECTORY_AVAILABLE\n#include <os/feature_private.h>\n#include <os/variant_private.h>\n#endif')
    elif name=='libinfo.c':
        # There is no dyld identifier/use anywhere else in this original TU.
        text=once(text,'#include <mach-o/dyld_priv.h>',
                  '/* Pi: unused dyld-private include omitted; no loader API calls changed. */')
    elif name=='ils.c':
        text=once(text,'size_t memsize, hsize, csize, csizep1, csizep2, slen, largest;',
                  'size_t memsize, hsize, csize, csizep1, csizep2, slen, largest, payload_size = 0;')
        text=once(text,'\t\tmemsize += csize;\n\t\tmemsize += slen;\n\t\thsize += csize;',
'''\t\t/* Pi correction: in-line data pointers are consumed as typed arrays.
\t\t * Align payload allocations, not just the struct/header fields. */
\t\tsize_t payload_pad = 0;
\t\tif (*f == 's' || *f == '*' || *f == 'a' || *f == 'b' || *f == 'c' || *f == '@')
\t\t\tpayload_pad = ((size_t)0 - payload_size) & 7;
\t\tif (payload_pad > SIZE_MAX - payload_size || slen > SIZE_MAX - payload_size - payload_pad ||
\t\t\tcsize > SIZE_MAX - hsize || csize > SIZE_MAX - memsize ||
\t\t\tslen > SIZE_MAX - memsize - csize || payload_pad > SIZE_MAX - memsize - csize - slen) {
\t\t\tva_end(ap); errno = ENOMEM; return NULL;
\t\t}
\t\tpayload_size += payload_pad + slen;
\t\tmemsize += csize + slen + payload_pad;
\t\thsize += csize;''')
        text=once(text,'\tpad = padsize(hsize, largest, align);\n\tmemsize += pad;',
                  '\tpad = padsize(hsize, largest, align);\n\tif (pad > SIZE_MAX - memsize || pad > SIZE_MAX - hsize) { errno = ENOMEM; return NULL; }\n\tmemsize += pad;')
        text=once(text,'\t/* second pass: copy data */\n\tva_start(ap, fmt);\n\tfor (f = fmt; (*f) != \'\\0\'; f++)\n\t{\n\t\tswitch (*f)',
'''\t/* second pass: copy data */
\tva_start(ap, fmt);
\tfor (f = fmt; (*f) != '\\0'; f++)
\t{
\t\tif (*f == 's' || *f == '*' || *f == 'a' || *f == 'b' || *f == 'c' || *f == '@') {
\t\t\tsize_t offset = (uint8_t *)dp - (uint8_t *)ils;
\t\t\tsize_t payload_pad = ((size_t)0 - offset) & 7;
\t\t\tif (offset > memsize || payload_pad > memsize - offset) {
\t\t\t\tva_end(ap); free(ils); errno = ENOMEM; return NULL;
\t\t\t}
\t\t\tmemset(dp, 0, payload_pad); dp += payload_pad;
\t\t}
\t\tswitch (*f)''')
    return text


def native_paths(directory):
    names={'_PATH_MASTERPASSWD':'master.passwd','_PATH_PASSWD':'passwd','_PATH_GROUP':'group',
           '_PATH_HOSTS':'hosts','_PATH_SERVICES':'services','_PATH_PROTOCOLS':'protocols'}
    text='/* Native fixture only: real POSIX I/O in a private disposable directory. */\n#include <paths.h>\n#include <pwd.h>\n#include <grp.h>\n#include <netdb.h>\n'
    for macro,leaf in names.items():text+=f'#undef {macro}\n#define {macro} "{directory/leaf}"\n'
    return text
