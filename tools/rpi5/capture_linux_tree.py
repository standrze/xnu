#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Capture a filtered Linux live tree, NEVER a firmware ownership/seed snapshot."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from fdt import parse

# Filtering runs on the Pi BEFORE reading property contents or transmitting them.
# Excludes chosen (including seeds, bootargs and identity), aliases, symbols and
# all unrelated subtrees. The result lacks the original FDT reservation header.
REMOTE = r'''
import json
from pathlib import Path
root=Path('/proc/device-tree')
storage_capture=False
allowed=set('compatible device_type status reg ranges #address-cells #size-cells #interrupt-cells interrupt-controller interrupt-parent interrupts interrupt-names interrupts-extended phandle linux,phandle clocks clock-names clock-frequency #clock-cells method enable-method size alignment alloc-ranges no-map reusable iommu-addresses'.split())
if storage_capture:
    allowed.update('reg-names gpio-controller #gpio-cells brcm,gpio-bank-widths brcm,gpio-direct gpios cd-gpios pinctrl-0 pinctrl-names pins function bias-pull-up bias-pull-down bias-disable vmmc-supply vqmmc-supply bus-width non-removable mmc-pwrseq regulator-min-microvolt regulator-max-microvolt regulator-settling-time-us states enable-active-high gpio enable-gpios enable-gpio gpio-open-drain vin-supply'.split())
def visit(path):
    props={}
    children=[]
    for item in sorted(path.iterdir()):
        if item.is_dir():
            roots=('cpus','psci','timer','clocks','reserved-memory','soc@107c000000')
            if storage_capture: roots+=('sd-vcc-reg','sd-io-1v8-reg')
            if path==root and item.name not in roots and not item.name.startswith('memory@'):
                continue
            children.append(visit(item))
        elif item.name in allowed:
            data=item.read_bytes()
            if len(data)>65536: raise ValueError('oversized property')
            props[item.name]=data.hex()
    return dict(name='' if path==root else path.name,properties=props,children=children)
print(json.dumps(visit(root)))
'''


def encode(node):
    strings=bytearray()
    def walk(n):
        name=n['name'].encode()+b'\0'
        out=struct.pack('>I',1)+name+bytes(-len(name)%4)
        for key,value in n['properties'].items():
            offset=len(strings); strings.extend(key.encode()+b'\0')
            data=bytes.fromhex(value)
            out+=struct.pack('>III',3,len(data),offset)+data+bytes(-len(data)%4)
        for child in n['children']: out+=walk(child)
        return out+struct.pack('>I',2)
    body=walk(node)+struct.pack('>I',9)
    return struct.pack('>10I',0xd00dfeed,56+len(body)+len(strings),56,56+len(body),40,17,16,0,len(strings),len(body))+bytes(16)+body+strings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    parser.add_argument('--storage',action='store_true',help='Include SD regulator, GPIO and pin binding properties; still no seeds/chosen/identity')
    args=parser.parse_args()
    if args.host.startswith('-'): parser.error('invalid host')
    result=subprocess.run(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
                           '-o','ConnectTimeout=8',args.host,'python3 -'],
                          input=REMOTE.replace('storage_capture=False','storage_capture='+str(args.storage),1),
                          text=True,capture_output=True,check=True,timeout=30)
    data=encode(json.loads(result.stdout))
    parse(data)
    base=Path(__file__).resolve().parents[2]/'build/rpi5'
    base.mkdir(parents=True,exist_ok=True)
    output=Path(tempfile.mkdtemp(prefix='linux-filtered-tree-',dir=base))
    (output/'filtered.dtb').write_bytes(data)
    metadata={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
              'source':'Linux /proc/device-tree; filtered properties/subtrees',
              'original_fdt':False,'header_reservations_captured':False,
              'sd_wiring_properties_captured':args.storage,
              'ownership_complete':False,'bootable':False}
    (output/'manifest.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(output)


if __name__=='__main__': main()
