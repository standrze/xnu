#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Passive transport/UBUS failure telemetry, preserving the failed ID inputs."""
import argparse
import json
from pathlib import Path
try:
    from . import build_pcie_id_progress_kernel as prior
except ImportError:
    import build_pcie_id_progress_kernel as prior

ROOT=prior.ROOT
BASE=ROOT/'build/rpi5/pcie-id-progress-kernel-20261013-final'
BASE_SHA='d57393c77dffea0a55249756c034becd04e5257222f6afe891f1bbc89aa2dd5e'
replace=prior.previous.base.replace_once


def trace_header(text):
    text=replace(text,'    unsigned trialLastPhase = BCM2712_PHY_EMPTY;',
        '    unsigned diagGuard=0, diagIOBank=0, diagIOOffset=0, diagIODirection=0, diagIOStage=0, diagIOValue=0;\n'
        '    unsigned diagUBUSStep=0; int diagUBUSRC=0;\n'
        '    unsigned trialLastPhase = BCM2712_PHY_EMPTY;')
    return replace(text,'    unsigned trialPhase() const { return getPhase(); }',
        '    unsigned traceGuard() const { return diagGuard; }\n'
        '    unsigned traceBank() const { return diagIOBank; }\n'
        '    unsigned traceOffset() const { return diagIOOffset; }\n'
        '    unsigned traceDirection() const { return diagIODirection; }\n'
        '    unsigned traceIOStage() const { return diagIOStage; }\n'
        '    unsigned traceValue() const { return diagIOValue; }\n'
        '    unsigned traceUBUSStep() const { return diagUBUSStep; }\n'
        '    int traceUBUSRC() const { return diagUBUSRC; }\n'
        '    unsigned traceUBUSCallbacks() const { return ubus.completed_callbacks; }\n'
        '    unsigned trialPhase() const { return getPhase(); }')


def trace_access(text):
    start=text.index('int BCM2712PCIePHYTransport::read32(')
    end=text.index('int BCM2712PCIePHYTransport::resetStatus(',start)
    functions=text[start:end]
    functions=replace(functions,'    if (!out || !bcm2712_controller_access_allowed',
        '    diagIOBank=bank;diagIOOffset=offset;diagIODirection=0;diagIOStage=1;diagIOValue=0;\n'
        '    if (!out || !bcm2712_controller_access_allowed')
    functions=replace(functions,'    if (!bcm2712_controller_access_allowed',
        '    diagIOBank=bank;diagIOOffset=offset;diagIODirection=1;diagIOStage=1;diagIOValue=value;\n'
        '    if (!bcm2712_controller_access_allowed')
    # No additional load/store to a device: record only already acquired values.
    functions=functions.replace('    __asm__ volatile("dmb osh" ::: "memory");',
        '    diagIOStage=2;\n    __asm__ volatile("dmb osh" ::: "memory");')
    functions=replace(functions,'    if (!guard()) return -1;\n    *out = value;',
        '    diagIOValue=value;diagIOStage=3;\n    if (!guard()) return -1;\n'
        '    diagIOStage=4;\n    *out = value;')
    functions=replace(functions,'    return guard() ? 0 : -1;',
        '    diagIOStage=3;\n    if(!guard())return -1;\n    diagIOStage=4;return 0;')
    return text[:start]+functions+text[end:]


def trace_guard(text):
    offset=text.index('bool BCM2712PCIePHYTransport::guard()')
    prefix,text=text[:offset],text[offset:]
    text=replace(text,'    unsigned currentPhase=getPhase();',
        '    unsigned currentPhase=getPhase();\n'
        '#define TRACE_FAIL(n) do { if(!diagGuard)diagGuard=(n);fail();return false; } while(0)')
    text=replace(text,'!ownerProvider || !ownerProvider->isOpen(this) || !pe_rpi5_watchdog_check_pcie(this)){fail();return false;}',
        '!ownerProvider || !ownerProvider->isOpen(this) || !pe_rpi5_watchdog_check_pcie(this))TRACE_FAIL(1);')
    text=replace(text,
        '        if(checkingLifecycle || claimingIRQ || claimingFW || !irqClaimed || !fwClaimed || !controllerAdmission.check ||\n'
        '            !pe_rpi5_pcie_irq_check(this,&irq) || !pe_rpi5_pcie_fw_check(this,&fw)){fail();return false;}',
        '        if(checkingLifecycle || claimingIRQ || claimingFW || !irqClaimed || !fwClaimed || !controllerAdmission.check)TRACE_FAIL(2);\n'
        '        if(!pe_rpi5_pcie_irq_check(this,&irq))TRACE_FAIL(3);\n'
        '        if(!pe_rpi5_pcie_fw_check(this,&fw))TRACE_FAIL(4);')
    text=replace(text,
        '        if(result || !onOwnerThread() || getPhase()!=currentPhase ||\n'
        '            __atomic_load_n(&phyOwner,__ATOMIC_ACQUIRE)!=this || !providerOpened ||\n'
        '            !ownerProvider || !ownerProvider->isOpen(this) || !pe_rpi5_pcie_fw_check(this,&fw) ||\n'
        '            !pe_rpi5_pcie_irq_check(this,&irq) || !pe_rpi5_watchdog_check_pcie(this)){fail();return false;}',
        '        if(result)TRACE_FAIL(5);\n'
        '        if(!onOwnerThread() || getPhase()!=currentPhase ||\n'
        '            __atomic_load_n(&phyOwner,__ATOMIC_ACQUIRE)!=this || !providerOpened ||\n'
        '            !ownerProvider || !ownerProvider->isOpen(this))TRACE_FAIL(6);\n'
        '        if(!pe_rpi5_pcie_fw_check(this,&fw))TRACE_FAIL(7);\n'
        '        if(!pe_rpi5_pcie_irq_check(this,&irq))TRACE_FAIL(8);\n'
        '        if(!pe_rpi5_watchdog_check_pcie(this))TRACE_FAIL(9);')
    return prefix+replace(text,'    return true;\n}', '    return true;\n#undef TRACE_FAIL\n}')


def trace_ubus(text):
    return replace(text,
        '    if (!guard() || rpi5_pcie_ubus_init(&ubus, &serdes) ||\n'
        '        rpi5_pcie_ubus_configure(&ubus, &result.ubus) || !guard()) {\n'
        '        fail();\n        return false;\n    }',
        '    diagUBUSStep=1;\n    if(!guard()){fail();return false;}\n'
        '    diagUBUSStep=2;diagUBUSRC=rpi5_pcie_ubus_init(&ubus,&serdes);\n'
        '    if(diagUBUSRC){fail();return false;}\n'
        '    diagUBUSStep=3;diagUBUSRC=rpi5_pcie_ubus_configure(&ubus,&result.ubus);\n'
        '    if(diagUBUSRC){fail();return false;}\n'
        '    diagUBUSStep=4;\n    if(!guard()){fail();return false;}\n'
        '    diagUBUSStep=5;')


def trace_body(text):
    text=replace(text,'GEN=%u LANES=%u\\n',
        'GEN=%u LANES=%u UBUS_STEP=%u UBUS_RC=%d UBUS_CB=%u GUARD=%u BANK=%u OFFSET=%08x DIR=%u IO_STAGE=%u VALUE=%08x\\n')
    return replace(text,'observed.controller.link.generation,observed.controller.link.lanes);',
        'observed.controller.link.generation,observed.controller.link.lanes,\n'
        '        transport?transport->traceUBUSStep():0,transport?transport->traceUBUSRC():0,\n'
        '        transport?transport->traceUBUSCallbacks():0,transport?transport->traceGuard():0,\n'
        '        transport?transport->traceBank():0,transport?transport->traceOffset():0,\n'
        '        transport?transport->traceDirection():0,transport?transport->traceIOStage():0,\n'
        '        transport?transport->traceValue():0);')


def build(output):
    audit=prior.previous.audit;base=prior.previous.base
    if audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Failed ID candidate changed')
    report=json.loads((BASE/'manifest.json').read_text())
    pins={**report['inputs_sha256'],**report['generated_sha256'],str(BASE/'manifest.json'):BASE_SHA}
    for name,digest in pins.items():
        if audit.sha(Path(name))!=digest:raise ValueError('Frozen ID input changed: '+name)
    for source in (Path(__file__).resolve(),ROOT/'tools/rpi5/tests/test_pcie_id_trace.py'):
        pins[str(source)]=audit.sha(source)
    old_inputs,old_header,old_body=base.inputs,prior.transform_header,prior.transform_body
    old_overlay=prior.previous.overlay
    def inputs():
        current,p,o=old_inputs()
        for name,digest in pins.items():
            if name in current and current[name]!=digest:raise ValueError('Trace input conflict: '+name)
            current[name]=digest
        return current,p,o
    def overlay(directory):
        cpp=old_overlay(directory);folder=cpp.parent
        cpp.write_text(trace_access(cpp.read_text()))
        for name,transform in (('BCM2712PCIeFWTransport.inc',trace_guard),('BCM2712PCIeUBUS.inc',trace_ubus)):
            path=folder/name
            source=path if path.exists() else ROOT/'iokit/Kernel'/name
            path.write_text(transform(source.read_text()))
        return cpp
    base.inputs=inputs;prior.previous.overlay=overlay
    prior.transform_header=lambda text:trace_header(old_header(text))
    prior.transform_body=lambda text:trace_body(old_body(text))
    try:result=prior.build(output.resolve())
    finally:
        base.inputs=old_inputs;prior.previous.overlay=old_overlay
        prior.transform_header=old_header;prior.transform_body=old_body
    result.update(profile='pcie-id-passive-failure-trace-v1',trace_adds_mmio=False,
        trace_changes_permissions=False,trace_changes_deadlines=False,
        trace_fields=['UBUS_STEP','UBUS_RC','UBUS_CB','GUARD','BANK','OFFSET','DIR','IO_STAGE','VALUE'],
        trace_guard_reasons={1:'phase-owner-or-PM',2:'claim-state',3:'IRQ-before',4:'firmware-before',
            5:'lifecycle-provider',6:'owner-after',7:'firmware-after',8:'IRQ-after',9:'PM-after'},
        trace_ubus_steps={1:'initial-guard',2:'init',3:'configure',4:'final-guard',5:'complete'},
        trace_io_stages={1:'requested',2:'admitted-before-access',3:'access-completed',4:'post-guard-complete'},
        candidate_only=True,hardware_failure_receipt='build/rpi5/rp1-id-serial-20261013')
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    result=build(parser.parse_args().output_dir)
    print(json.dumps({k:result[k] for k in ('profile','kernel','kernel_sha256','kernel_bytes')}))
