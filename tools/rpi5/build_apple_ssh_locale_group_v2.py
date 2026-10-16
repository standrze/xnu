#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Close the locale group's genuine numeric and multibyte helper units."""
import json
from pathlib import Path
from tools.rpi5 import build_apple_ssh_locale_group as group

HELPERS = ('locale/FreeBSD/fix_grouping.c', 'locale/FreeBSD/localeconv.c',
           'locale/FreeBSD/mbrtowc.c', 'locale/FreeBSD/wcrtomb.c',
           'string/FreeBSD/wcsncmp.c')


def build():
    module = group.parent.implementation()
    policy = {str(Path(p).resolve()):module.sha(p)
              for p in (group.__file__,group.parent.__file__,__file__)}
    module.__file__ = __file__
    module.UNITS += group.ADDITIONAL + HELPERS
    out, report = module.build()
    for name,digest in policy.items():
        if module.sha(name)!=digest:raise ValueError('Locale build policy changed')
    report['source_inputs_sha256'].update(policy)
    report['profile'] = 'original-apple-current-ssh-locale-group-v2'
    report['bounded_unit_count'] = len(module.UNITS)
    report['c_locale_target_runtime_executed'] = False
    report['non_c_locale_runtime_or_data_qualified'] = False
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(final_package=str(out),manifest_sha256=module.sha(out/'manifest.json'),
        units=len(module.UNITS),closed=report['closed_symbols'],
        added=report['newly_reachable_dependencies'],remaining=len(report['target_missing_symbols'])),indent=2))
    return out,report


if __name__=='__main__':build()
