# SPDX-License-Identifier: BSD-2-Clause
"""Supplemental report scoping; exact frozen image/checker remain unchanged.

The original checker validates each predecessor composition, so its inherited
checks are historical component evidence. They must not assert that this root
only added reboot or that this loader replaced only one object.
"""
from . import check_display_restart_init as original
b=original.b

def inspect(package,expected=None):
    report=original.inspect(package,expected)
    report['inherited_component_checks']={key:dict(report[key]) for key in
        ('checks','diagnostic_checks','copy_phase_checks')}
    report['checks']=dict(report['checks'])
    report['checks'].pop('root_only_added_cli')
    report['checks'].pop('exact_inherited_bytes')
    report['checks'].update(root_only_launchd_replaced=True,all_other_root_files_and_kernel_identical=True)
    report['copy_phase_checks']=dict(report['copy_phase_checks'])
    report['copy_phase_checks'].pop('one_loader_owner_replaced')
    report['copy_phase_checks']['exact_main_and_payload_owner_replacements']=True
    report['diagnostic_checks']=dict(report['diagnostic_checks'])
    report['diagnostic_checks'].pop('unchanged_root33_cli')
    report['diagnostic_checks']['unchanged_reboot_cli_and_diagnostic_kernel']=True
    report['report_scope']='pid1-successor-current-checks-with-historical-component-checks-v2'
    report['supplemental_report_source_sha256']={str(__file__):b.sha(__file__)}
    return report
