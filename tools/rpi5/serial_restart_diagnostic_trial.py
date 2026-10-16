#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One fresh diagnostic image; genuine reboot once after four proven exchanges."""
import hashlib
from pathlib import Path
_parent=Path(__file__).with_name('serial_display_xnu_trial.py')
_raw=_parent.read_bytes()
if hashlib.sha256(_raw).hexdigest()!='c6fae18287d73b3356480604431b754666733879eec3f7df21332a4ebb4fe2fb':
    raise ValueError('Exact bounded display receiver required')
_text=_raw.decode()
_changes=[
    ('import stage_display_xnu_trial as stage','import stage_restart_diagnostic_trial as stage'),
    ('from tools.rpi5 import display_xnu_serial as protocol','from tools.rpi5 import restart_diagnostic_serial as protocol'),
    ('sd_time+240','sd_time+HOST_RETURN_SECONDS'),
    ("for name,command,expected,prompt in protocol.exchanges(nonce):",
     "for name,command,expected,prompt in protocol.exchanges(nonce)+[('restart',protocol.restart_command(nonce),[],protocol.PROMPT)]:"),
    ('tx_end=time.monotonic();response_deadline=min(deadline,tx_end+30)',
     '''tx_end=time.monotonic()
                        if name=='restart':
                            if len(state['exchanges'])!=4:raise ValueError('Four actual interactive checks must precede reboot')
                            state['command_tests_passed']=True
                            state['reboot_request']=dict(command=command,offset=offset,pending_offset=pending_start,
                                pending_bytes=offset-pending_start,pending_sha256=hashlib.sha256(received[pending_start:offset]).hexdigest(),
                                tx_started_monotonic=tx_start,tx_ended_monotonic=tx_end)
                            return
                        response_deadline=min(deadline,tx_end+30)'''),
    ("if __name__=='__main__':raise SystemExit(main())",''),
]
for _old,_new in _changes:
    if _text.count(_old)!=1:raise ValueError('Exact restart receiver derivation boundary')
    _text=_text.replace(_old,_new)
HOST_RETURN_SECONDS=300
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
_initial=initial

def initial(context,device,pid=None,started=None):
    value=_initial(context,device,pid,started)
    value.update(reboot_request=None,physical_psci_causality_proven=False,
        host_return_window=dict(total_seconds=300,loader_allowance_seconds=60,terminal_service_seconds=180,
            hardware_countdown_seconds=15,firmware_linux_allowance_seconds=45,kernel_deadline_changed=False))
    return value

def package_pins(context):
    path=stage.PACKAGE/'manifest.json'
    if context['evidence'].get(str(path))!=stage.MANIFEST_SHA or stage.sha(path)!=stage.MANIFEST_SHA:raise ValueError('Exact restart package seal required')
    m=json.loads(path.read_text());pins={str(path):stage.MANIFEST_SHA}
    for key in ('inputs_sha256','headers_sha256','generated_sha256'):pins=stage.prior.merge_pins(pins,m[key])
    if any(context['evidence'].get(n)!=v for n,v in pins.items()):raise ValueError('Complete diagnostic package closure absent')
    return pins

def armed_line(report):return 'RESTART_DIAGNOSTIC_ARMED NO_TX_UNTIL_FRESH_READY IMAGE_SHA='+report['image_sha256']+' TAG='+report['tag']

if __name__=='__main__':raise SystemExit(main())
