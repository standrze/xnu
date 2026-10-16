#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One read-only SSH verification after a completed, receipt-bound ABI capture.

No wait loop, reboot, serial, mount, SD write, repair or restore. A timeout has
no success result; the same capture/boot can be inspected, never blindly reset.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
try:
    from . import pcie_fw_recovery_evidence as evidence
except ImportError:
    import pcie_fw_recovery_evidence as evidence
import rpi5_board_lease as lease
stage=evidence.stage


def remote_source(plan,installed,serial_sha,sources):
    capture,reference=stage.base.MODULES[0],stage.base.reference
    return ('import json,types,copy\nfrom pathlib import Path\nfrom datetime import datetime,timezone\n'+
        'capture=types.ModuleType("read_only_identity")\nexec('+repr(Path(capture.__file__).read_text())+',capture.__dict__)\n'+
        'reference=types.ModuleType("read_only_boot_properties")\nexec('+repr(Path(reference.__file__).read_text())+',reference.__dict__)\n'+
        'PLAN=json.loads('+repr(json.dumps(plan))+')\n'+
        'boot=Path("/proc/sys/kernel/random/boot_id").read_text().strip()\n'+
        'if boot==PLAN["linux_boot_id"]:raise ValueError("No new Linux boot after trial")\n'+
        'binding=copy.deepcopy(PLAN["identity_binding"])\n'+
        'binding["linux_boot_id_before_write"]=PLAN["linux_boot_id"]\n'+
        'binding["linux_boot_id_after_write"]=boot\n'+
        'before=capture.identity(binding)\nproperties=reference.boot_properties()\n'+
        'after=capture.identity(binding)\n'+
        'if before!=after:raise ValueError("Linux/card identity changed during return observation")\n'+
        'result=dict(host=PLAN["host"],boot_id=boot,identity=after,root=after["identity"]["root"].split(),'+
        'bootloader=properties,sd_partitions_unmounted=True,read_only=True,'+
        'observed_utc=datetime.now(timezone.utc).isoformat(),installation=json.loads('+repr(json.dumps(installed))+'),'+
        'serial_sha256='+repr(serial_sha)+',return_source_sha256=json.loads('+repr(json.dumps(sources))+'))\n'+
        'print(json.dumps(result,sort_keys=True))\n')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--installation',type=Path,required=True);p.add_argument('--capture',type=Path,required=True)
    args=p.parse_args(argv)
    installation,capture=map(evidence.local_child,(args.installation,args.capture))
    target=capture/'linux-return.json'
    if target.exists() or target.is_symlink():raise ValueError('Existing Linux return outcome; inspect, never overwrite')
    with lease.hold(stage.ROOT,'read-only-firmware-trial-linux-return'):
        plan,installed,observations=evidence.load_capture(installation,capture)
        sources=evidence.return_source_pins()
        program=remote_source(plan,installed,observations['serial_sha256'],sources)
        r=subprocess.run(stage.SSH+['sudo -n python3 -'],input=program,text=True,capture_output=True,timeout=60)
        r.check_returncode();returned=json.loads(r.stdout)
        evidence.inspect_return(returned,plan,installed,observations)
        if evidence.return_source_pins()!=sources or evidence.load_capture(installation,capture)!=(plan,installed,observations):
            raise ValueError('Source or captured trial changed during return observation')
        returned['remote_program_sha256']=hashlib.sha256(program.encode()).hexdigest()
        with target.open('x') as out:
            out.write(json.dumps(returned,indent=2)+'\n');out.flush()
            os.fsync(out.fileno())
    print(json.dumps(dict(normal_nvme_linux_return_verified=True,boot_id=returned['boot_id'],output=str(target),
        restored_pair=False,controller_initialization_admitted=False)))
    return 0


if __name__=='__main__':raise SystemExit(main())
