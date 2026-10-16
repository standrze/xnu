#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One bounded current-Apple locale group; preserve prior slice artifacts."""
import json
from pathlib import Path
from tools.rpi5 import build_apple_ssh_locale_slice_v2 as parent

ADDITIONAL = (
    'locale/isctype.c', 'locale/FreeBSD/mbtowc.c',
    'locale/FreeBSD/wcwidth.c', 'locale/FreeBSD/nl_langinfo.c',
    'locale/FreeBSD/setlocale.c', 'locale/FreeBSD/setrunelocale.c',
    'locale/FreeBSD/ldpart.c', 'locale/FreeBSD/rune.c',
    'locale/FreeBSD/lmessages.c', 'locale/FreeBSD/lmonetary.c',
    'locale/FreeBSD/lnumeric.c', 'stdtime/FreeBSD/timelocal.c',
    'locale/FreeBSD/ascii.c', 'locale/FreeBSD/utf8.c',
    'locale/FreeBSD/utf2.c', 'locale/FreeBSD/euc.c',
    'locale/FreeBSD/gb18030.c', 'locale/FreeBSD/gb2312.c',
    'locale/FreeBSD/gbk.c', 'locale/FreeBSD/big5.c',
    'locale/FreeBSD/mskanji.c', 'locale/FreeBSD/mbsnrtowcs.c',
    'locale/FreeBSD/wcsnrtombs.c', 'locale/runedepreciated.c',
    'locale/FreeBSD/tolower.c', 'locale/FreeBSD/toupper.c',
)


def build():
    module = parent.implementation()
    parent_path = Path(parent.__file__).resolve()
    parent_pin = module.sha(parent_path)
    module.__file__ = __file__
    module.UNITS = module.UNITS + ADDITIONAL
    out, report = module.build()
    if module.sha(parent_path) != parent_pin:
        raise ValueError('Header-build policy changed during group build')
    report['source_inputs_sha256'][str(parent_path)] = parent_pin
    report['profile'] = 'original-apple-current-ssh-locale-group-v1'
    report['bounded_unit_count'] = len(module.UNITS)
    report['c_locale_target_runtime_executed'] = False
    report['non_c_locale_runtime_or_data_qualified'] = False
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(final_package=str(out),manifest_sha256=module.sha(out/'manifest.json'),
        units=len(module.UNITS),closed=report['closed_symbols'],
        added=report['newly_reachable_dependencies'],remaining=len(report['target_missing_symbols'])),indent=2))
    return out,report


if __name__=='__main__':build()
