# SPDX-License-Identifier: BSD-2-Clause
"""59-row full-capture reset/C22 restoration; propagated -6 remains failure."""
import copy
import hashlib
from pathlib import Path
import re
from tools.rpi5 import pcie_gem_mdio_serial_core as prior
from tools.rpi5 import build_pcie_phy_reset_package as package_source
PREFIX,BEGIN,TRANSFER,ENTRY,COMMIT,PREPARED,PREPARED_PREFIX=(getattr(prior,n) for n in
    ('PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX'))
inventory,return_positions,health,same=prior.inventory,prior.return_positions,prior.health,prior.same
ADDITIONS=('PHYRESET','PHYRESET_MAP','PHYRESET_CTRL','PHYRESET_RIO','PHYRESET_INPUT','PHYRESET_TIME')
ORDER=prior.ORDER[:-1]+ADDITIONS+('END',)


def refined(module,label,replacements=()):
    """Fixed old parser byte sources, explicit successor policy delta only."""
    path=Path(module.__file__).resolve();text=path.read_text()
    for old,new in replacements:text=package_source.kernel.profile.core.util.once(text,old,new)
    result=package_source.private.load_private(path,label)
    exec(compile(text,str(path),'exec'),result.__dict__)
    return result


def configured_parser():
    # The old MDIO image/reader/invalid receipt remain immutable. Its callback
    # error -6 was already propagated by the actual core; the NEW parser must
    # preserve that error through root/GEM/decode bounds, never rewrite it.
    cap=refined(prior.prior,'_reset_cap_parser')
    selected=refined(prior.prior.prior,'_reset_selected_parser')
    root=refined(selected.prior,'_reset_root_parser',[("not -5<=progress['rc']<=0","not -6<=progress['rc']<=0")])
    gem=refined(root.prior,'_reset_gem_parser',[("not -5<=progress['rc']<=0","not -6<=progress['rc']<=0")])
    decode=refined(gem.prior,'_reset_decode_parser',[("not -5<=progress['rc']<=0","not -6<=progress['rc']<=0")])
    gem.prior=decode;gem.clock_profile=selected.clock_profile;root.prior=gem
    root.package_source=selected.package_source;selected.configured_parser=lambda:root;cap.prior=selected
    result=refined(prior,'_reset_mdio_parser',[
        ("('mdio_contract','mdio_contract')","('reset_contract','reset_contract')"),
        ("io['clocks']>57","io['clocks']>2"),
        ("io['clocks']!=io['reads']+io['writes']+2","io['clocks']!=2")])
    # Marker conversion is a fixed private adapter, not weakening any data
    # row or live-restoration criterion of the retained C22 parser.
    text=Path(prior.__file__).read_text().replace('PCIE_GEM_MDIO_TRIAL','PCIE_PHY_RESET_TRIAL')
    for old,new in (("('mdio_contract','mdio_contract')","('reset_contract','reset_contract')"),
        ("io['clocks']>57","io['clocks']>2"),("io['clocks']!=io['reads']+io['writes']+2","io['clocks']!=2")):
        text=package_source.kernel.profile.core.util.once(text,old,new)
    exec(compile(text,prior.__file__,'exec'),result.__dict__)
    result.prior=cap;result.package_source=package_source;return result


def inspect(data,report):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:raise ValueError('Bounded original reset capture required')
    if health.inspect(data,hashlib.sha256(data).hexdigest())['runtime_fault_signature_observed'] or b'RPI5XNU:FAULT' in data:
        raise ValueError('Fault anywhere in complete original reset capture')
    for name,factory in (('reset_contract','reset_contract'),('rp1_device_handoff','gpio_handoff_contract')):
        if not same(report.get(name),getattr(package_source,factory)()):raise ValueError('Exact reset report required: '+name)
    marker=report.get('marker','');device=package_source.DEVICE_MARKER
    if not marker.startswith('RPI5XNU:BL33:PCIE_PHY_RESET_TRIAL TAG=') or data.count(marker.encode())!=1 or data.count(device.encode())!=1:
        raise ValueError('Unique reset image and nine-page marker required')
    lines=[row.rstrip(b'\r') for row in data.split(b'\n') if row.startswith(PREFIX)]
    if len(lines)!=59 or tuple(row.split(b' ',1)[0][len(PREFIX):].decode('ascii') for row in lines)!=ORDER:
        raise ValueError('Exactly59 ordered reset diagnostic records required')
    row=lambda name:lines[ORDER.index(name)]
    def fields(name,labels,bases=None):
        labels=labels.split();bases=bases or [10]*len(labels)
        pattern=b' '.join(k.encode()+(rb'=(-?\d+)' if base==10 else rb'=([0-9a-f]{'+str(base).encode()+rb'})') for k,base in zip(labels,bases))
        m=re.fullmatch(PREFIX+name.encode()+b' '+pattern,row(name))
        if not m:raise ValueError('Exact reset row required: '+name)
        return dict(zip((k.lower() for k in labels),(int(v,10 if base==10 else 16) for v,base in zip(m.groups(),bases))))
    progress=fields('PHYRESET','STATE RC STEP READS WRITES PENDING')
    maps=fields('PHYRESET_MAP','STATE RC MAPPED UNMAPPED LINK_CONTROL',[10,10,1,1,4])
    ctrl=fields('PHYRESET_CTRL','BEFORE AFTER PAD_BEFORE PAD_AFTER',[8]*4)
    rio=fields('PHYRESET_RIO','OUT_BEFORE OUT_AFTER OE_BEFORE OE_AFTER',[8]*4)
    inputs=fields('PHYRESET_INPUT','LOW HIGH PCIE_INTE',[8]*3)
    times=fields('PHYRESET_TIME','START_US LAST_US DEADLINE_US ASSERTED_US DEASSERTED_US COMPLETED_US')
    if (not 0<=progress['state']<=3 or not -6<=progress['rc']<=0 or not 0<=progress['step']<=8 or
        not 0<=progress['reads']<=32 or not 0<=progress['writes']<=12 or not 0<=progress['pending']<=5 or
        not 0<=maps['state']<=3 or not -6<=maps['rc']<=0 or maps['mapped']>7 or maps['unmapped']>7 or
        maps['unmapped']&~maps['mapped'] or any(not 0<=v<=2**64-1 for v in times.values())):
        raise ValueError('Reset/map/deadline bounds exceeded')
    normalized=data
    for name in ADDITIONS:
        line=row(name);wire=line+b'\r\n' if line+b'\r\n' in normalized else line+b'\n';normalized=normalized.replace(wire,b'',1)
    olddevice=prior.prior.package_source.DEVICE_MARKER
    normalized=normalized.replace(device.encode(),olddevice.encode())
    adapted=copy.deepcopy(report);adapted['boot_markers']=[v.replace(device,olddevice) for v in report['boot_markers']]
    result=configured_parser().inspect(normalized,adapted);passed=result['mdio_trial_pass']
    if passed:
        if (tuple(progress.values())!=(2,0,8,19,12,0) or tuple(maps.values())[:4]!=(2,0,7,7) or maps['link_control']&0x103):
            raise ValueError('Complete reset and exact map restoration required')
        if (ctrl['before']&~0xf09f or (ctrl['before']&31)>8 and (ctrl['before']&31)!=31 or
            ctrl['after']!=ctrl['before'] or ctrl['pad_before']&~255 or ctrl['pad_after']!=ctrl['pad_before'] or
            rio['out_after']!=rio['out_before'] or rio['oe_after']!=rio['oe_before'] or
            inputs['pcie_inte']&16 or inputs['low']&16 or not inputs['high']&16):
            raise ValueError('Exact original GPIO fields and asserted/deasserted input readbacks required')
        if (times['deadline_us']!=times['start_us']+40000 or not times['start_us']<times['asserted_us'] or
            not times['asserted_us']+5000<=times['deasserted_us']<times['completed_us']<times['deadline_us'] or
            times['last_us']!=times['completed_us'] or result['mdio_timing']['start_us']<times['deasserted_us'] or
            result['mdio_timing']['deadline_us']>times['deadline_us'] or result['mdio_timing']['last_us']>times['completed_us']):
            raise ValueError('Enclosing reset and bounded nested management clocks required')
    # A child -6 is valid diagnostic failure, never restoration success.
    propagated=[result['root_forward_progress']['rc'],result['gem_progress']['rc'],result['decode_telemetry']['rc']]
    unadmitted=tuple(progress.values())==(0,0,0,0,0,0)
    if -6 in propagated and (passed or maps['rc']!=-6 or maps['state']!=3 or
        not (progress['rc']==-6 or unadmitted)):
        raise ValueError('Propagated -6 must remain a captured reset failure')
    result.update(phy_reset_trial_pass=passed,phy_reset_progress=progress,phy_reset_maps=maps,phy_reset_ctrl=ctrl,
        phy_reset_rio=rio,phy_reset_inputs=inputs,phy_reset_times=times,gpio_register_writes_attempted=progress['writes'],
        gpio_reset_sequence_completed=passed,gpio_original_fields_restored=passed,gpio_mappings_revoked=passed,
        reset_action_refused_before_core_entry=unadmitted and maps['state']==3,
        phy_reset_cause_of_prior_floating_reads_proven=False,packets_proven=False,ethernet_proven=False,
        observed_field_rows=59,endpoint_register_reads_attempted=result['endpoint_register_reads_attempted']+progress['reads'],
        endpoint_register_reads_completed=48+result['mdio_io']['reads']+19 if passed else None,
        endpoint_register_writes_attempted=result['mdio_io']['writes']+progress['writes'],
        full_original_capture_health_scan=True,scope='Fresh GPIO32 pulse and C22 observations with complete restoration; no packets')
    return result
