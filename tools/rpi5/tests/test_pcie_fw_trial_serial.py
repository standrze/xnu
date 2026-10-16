# SPDX-License-Identifier: BSD-2-Clause
import unittest
from tools.rpi5 import pcie_fw_trial_serial_core as core
TAG='0123456789abcdef0123456789abcdef'
IMAGE='1'*64
FIRMWARE='2'*64


def fixture():
    def head(kind):return core.PREFIX+kind.encode()+b' TAG='+TAG.encode()
    def line(kind,values):return head(kind)+b' '+b' '.join(k.encode()+f'=0x{v:016X}'.encode() for k,v in values.items())
    lines=[head('ENTRY')+b' EL2 NO_XNU NO_CPU_ON CONTROLLER_WRITES=0 DMA=0',
        head('EL1')+b' MMU_CACHE_OFF DAIF_MASKED PRIMARY_ONLY FREQUENCY=0x00000000000F4240']
    def event(kind,pm,gic,rpc,checks,fid=0,token=0,raw=(0,0,0,0)):
        lines.append(line(kind,dict(FID=fid,TOKEN=token,**dict(zip(('X0','X1','X2','X3'),raw)),
            PM_WRITES=pm,GIC_WRITES=gic,RPC_CALLS=rpc,PM_CHECKS=checks)))
    event('ARMED',1,0,0,0);event('MASKED',1,3,0,71)
    for index,(fid,checks) in enumerate(((0xc2007f10,112),(0xc2007f11,194),
        (0xc2007f12,277),(0xc2007f12,360),(0xc2007f12,443)),1):
        seq=1 if index<=2 else index-1;facts=3 if index==1 else 31;counter=1000000+index*3000
        event('RPC_BEGIN',1,3,index-1,checks,fid,0 if index==1 else 0x9001234)
        event('RPC_END',1,3,index,checks,fid,0 if index==1 else 0x9001234,(0,seq,counter,facts))
        if index>2:event('CHECKED',1,3,index,checks+41,raw=(0,seq,counter,facts))
    lines.append(line('RESULT',dict(RC=0,PHASE=2,PM_WRITES=1,GIC_WRITES=3,RPC_CALLS=5,SEQUENCE=4,FACTS=31,PM_CHECKS=485)))
    lines.append(head('STOP')+b' NO_RELOAD WAIT_FOR_RESET CONTROLLER_WRITES=0 DMA=0 RESET_RETURN_PROVEN=0')
    return b'\r\n'.join(lines)+b'\r\n'


class FirmwareABISerialTests(unittest.TestCase):
    def test_complete_sequence_does_not_claim_reset_or_xnu_runtime(self):
        r=core.inspect(fixture(),TAG,IMAGE,FIRMWARE)
        self.assertTrue(r['firmware_abi_observation_pass']);self.assertEqual(r['pm_checks'],485)
        self.assertFalse(r['physical_reset_return_proven']);self.assertFalse(r['xnu_pe_runtime_proven'])

    def test_every_missing_duplicate_reordered_or_foreign_tag_line_refused(self):
        lines=fixture().splitlines(keepends=True)
        for i in range(len(lines)):
            for bad in (b''.join(lines[:i]+lines[i+1:]),fixture()+lines[i],
                b''.join(lines[:i]+[lines[i].replace(TAG.encode(),b'0'*32)]+lines[i+1:])):
                with self.subTest(line=i),self.assertRaises(ValueError):core.inspect(bad,TAG,IMAGE,FIRMWARE)
        for i in range(len(lines)-1):
            bad=list(lines);bad[i],bad[i+1]=bad[i+1],bad[i]
            with self.assertRaises(ValueError):core.inspect(b''.join(bad),TAG,IMAGE,FIRMWARE)

    def test_each_event_field_mutation_and_timing_failure_refused(self):
        lines=fixture().splitlines(keepends=True)
        for i,line in enumerate(lines):
            if not any(k in line for k in (b':ARMED ',b':MASKED ',b':RPC_',b':CHECKED ')):continue
            for key in core.EVENT_KEYS:
                marker=key.encode()+b'=0x';start=line.index(marker)+len(marker)
                value=int(line[start:start+16],16);bad=list(lines)
                # QUERY/CLAIM counters have no duplicated CHECKED observation;
                # a one-tick difference is legitimate. Zero is unambiguously
                # invalid; do not tighten the protocol just to reject it.
                changed=0 if key=='X2' and i in (5,7) else value^1
                bad[i]=line[:start]+f'{changed:016X}'.encode()+line[start+16:]
                with self.subTest(line=i,key=key),self.assertRaises(ValueError):core.inspect(b''.join(bad),TAG,IMAGE,FIRMWARE)
        for raw in (fixture()+core.PREFIX+b'FAULT TAG='+TAG.encode()+b'\r\n',
            fixture().replace(b'CONTROLLER_WRITES=0',b'CONTROLLER_WRITES=1',1),
            fixture().replace(b'FREQUENCY=0x00000000000F4240',b'FREQUENCY=0x0000000000000000'),
            fixture().replace(b'X2=0x00000000000F6568',b'X2=0x0000000000989680')):
            with self.assertRaises(ValueError):core.inspect(raw,TAG,IMAGE,FIRMWARE)
        for tag,im,fw in (('x',IMAGE,FIRMWARE),(TAG,'x',FIRMWARE),(TAG,IMAGE,'x')):
            with self.assertRaises(ValueError):core.inspect(fixture(),tag,im,fw)


if __name__=='__main__':unittest.main()
