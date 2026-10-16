# SPDX-License-Identifier: BSD-2-Clause
"""Complete root42 command replay plus one independent normal-NVMe witness.

An incomplete trial is retained as a failure, even when Linux recovery succeeds.
Neither a synthetic fixture nor a pthread marker alone is runtime acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import types
try:
    from . import stage_root42_pthread_trial as stage
    from . import serial_root42_pthread_trial as recorder
    from . import root42_pthread_command_evidence as commands
    from . import audit_root41_trial as original
    from . import pcie_trace_evidence as identity
    from . import capture_pcie_trace_linux_return as remote
    from . import stage_pcie_trial_v3 as helpers
except ImportError:
    import stage_root42_pthread_trial as stage
    import serial_root42_pthread_trial as recorder
    import root42_pthread_command_evidence as commands
    import audit_root41_trial as original
    import pcie_trace_evidence as identity
    import capture_pcie_trace_linux_return as remote
    import stage_pcie_trial_v3 as helpers

FORMAT = 'rpi5-root42-independent-return-v1'


def source_pins(context):
    pins = recorder.bound_sources(context) | {str(Path(m.__file__).resolve()): stage.sha(m.__file__)
        for m in (commands, original, identity, remote)} | {str(Path(__file__).resolve()): stage.sha(__file__)}
    if any(context['evidence'].get(n) != h for n, h in pins.items()):
        raise ValueError('Return/replay helpers must be sealed before the trial')
    return pins


def captured(context, directory):
    recorder.revalidate(context); directory = stage.local(directory)
    state = json.loads((directory/'state.json').read_text())
    armed = json.loads((directory/'armed.json').read_text()); raw = (directory/'serial.bin').read_bytes()
    report = context['installed']['preflight']; pins = recorder.bound_sources(context)
    nonce = 'B'+'0'*16
    tx_max = sum(len(s)+1 for s in (recorder.core.IDENTITY,
        recorder.core.batch_command(nonce), recorder.core.recovery_command(nonce)))
    same = helpers.engine.same
    if (state.get('status') not in ('passed', 'failed') or not same(state.get('installation'), context['installed']) or
        not same(state.get('preflight'), report) or not same(state.get('source_sha256'), pins) or
        not same(state.get('receipt_evidence_sha256'), context['evidence']) or
        not same(state.get('package_evidence_sha256'), recorder.package_pins(context)) or
        type(state.get('bytes')) is not int or state['bytes'] != len(raw) or len(raw)>4*1024*1024 or
        type(state.get('transmitted_bytes')) is not int or not 0<=state['transmitted_bytes']<=tx_max or
        state.get('serial_sha256') != hashlib.sha256(raw).hexdigest() or
        type(state.get('pid')) is not int or state['pid']<=0 or type(state.get('baud')) is not int or state.get('baud')!=115200 or
        not recorder.t.valid_probe_device(state.get('device', '')) or
        any(state.get(k) is not False for k in ('independent_linux_return_verified', 'ssh_daemon',
            'networking', 'controller_initialized', 'durability'))):
        raise ValueError('Changed/unbounded root42 recorder or receipt binding')
    keys = ('started_utc', 'pid', 'device', 'baud', 'preflight', 'installation', 'source_sha256',
        'receipt_evidence_sha256', 'package_evidence_sha256', 'armed_utc', 'armed_monotonic')
    expected = {k: state[k] for k in keys}
    expected.update(status='failed', checks=[], exchanges=[], transmitted_bytes=0,
        command_tests_passed=False, normal_nvme_boot_observed=False,
        independent_linux_return_verified=False, ssh_daemon=False, networking=False,
        controller_initialized=False, durability=False)
    if not helpers.engine.same(armed, expected):
        raise ValueError('Exact zero-TX root42 armed snapshot required')
    times = [identity.zoned(state[k]) for k in ('started_utc', 'armed_utc', 'ended_utc')]
    if not times[0]<=times[1]<=times[2] or not 0<(times[2]-times[0]).total_seconds()<840:
        raise ValueError('Bounded armed root42 timestamps required')
    diagnostic = None; error = None
    if state['status']=='passed':
        facade = types.SimpleNamespace(core=recorder.checked_core, t=recorder.t, root_profile=recorder.root_profile,
            source_pins=lambda: pins, package_evidence_pins=lambda _: recorder.package_pins(context))
        replay = helpers.private(original.replay, recorder=facade, core=recorder.checked_core,
            t=recorder.t, stage=stage, command_evidence=commands)
        receipt = json.loads(Path(report['root_manifest']).read_text())
        try:
            diagnostic = replay(state, raw, report, context['installed'], receipt)
            diagnostic['status'] = 'root42_pthread_serial_replayed'
        except (ValueError, KeyError, TypeError, RuntimeError) as invalid:
            error = str(invalid)
    else:
        error = state.get('error') or state.get('serial_restore_error')
        if not isinstance(error, str) or not error:
            raise ValueError('Explicit failed recorder reason required')
    observed = dict(capture_valid=diagnostic is not None, diagnostic=diagnostic, capture_error=error,
        serial_sha256=state['serial_sha256'], nvme_selected_utc=state['ended_utc'],
        independent_linux_return_proven=False, networking=False, ssh_daemon=False)
    return state, observed, {n: stage.sha(directory/n) for n in ('armed.json', 'state.json', 'serial.bin')}


def inspect_return(value, context, observed):
    fn = helpers.private(identity.inspect_return, stage=stage,
        same=helpers.engine.same, return_source_pins=lambda: source_pins(context))
    return fn(value, context['plan']['media'], context['installed'], observed)


def collect_return(context, directory):
    directory = stage.local(directory)
    if (directory/'return.json').exists():
        raise ValueError('Return exists; never overwrite/retry implicitly')
    state, observed, bound = captured(context, directory); pins = source_pins(context)
    program = remote.remote_source(context['plan']['media'], context['installed'], state['serial_sha256'], pins)
    response = subprocess.run(stage.SSH+['sudo -n python3 -'], input=program,
        text=True, capture_output=True, timeout=60)
    response.check_returncode(); value = json.loads(response.stdout)
    boot = inspect_return(value, context, observed)
    if captured(context, directory)!=(state, observed, bound) or source_pins(context)!=pins:
        raise ValueError('Root42 evidence changed during independent observation')
    result = dict(format=FORMAT, capture_valid=observed['capture_valid'], diagnostic=observed['diagnostic'],
        capture_error=observed['capture_error'], observation=value, linux_boot_id=boot,
        capture_sha256=bound, installation=context['installed'], source_sha256=pins,
        remote_source_sha256=hashlib.sha256(program.encode()).hexdigest(),
        independent_normal_nvme_linux_return_verified=True, networking=False, ssh_daemon=False)
    helpers.save(directory/'return.json', result)
    return result


def load_return(context, directory):
    directory = stage.local(directory); value = json.loads((directory/'return.json').read_text())
    state, observed, bound = captured(context, directory)
    expected = dict(format=FORMAT, capture_valid=observed['capture_valid'], diagnostic=observed['diagnostic'],
        capture_error=observed['capture_error'], capture_sha256=bound, installation=context['installed'],
        source_sha256=source_pins(context), independent_normal_nvme_linux_return_verified=True,
        networking=False, ssh_daemon=False)
    if any(not helpers.engine.same(value.get(k), v) for k, v in expected.items()):
        raise ValueError('Exact root42 return receipt required')
    boot = inspect_return(value['observation'], context, observed)
    program = remote.remote_source(context['plan']['media'], context['installed'], state['serial_sha256'], source_pins(context))
    if value.get('linux_boot_id')!=boot or value.get('remote_source_sha256')!=hashlib.sha256(program.encode()).hexdigest():
        raise ValueError('Root42 return boot or exact observer program differs')
    return value, boot


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=('return', 'replay'))
    p.add_argument('--installation', type=Path, required=True)
    p.add_argument('--seal-sha256', required=True); p.add_argument('--plan-sha256', required=True)
    p.add_argument('--capture', type=Path, required=True)
    a=p.parse_args(argv)
    if a.operation=='return':
        with stage.lease.hold(stage.ROOT, 'root42-read-only-independent-return'):
            context=stage.load_installation(a.installation, a.seal_sha256, a.plan_sha256)
            result=collect_return(context, a.capture)
    else:
        context=stage.load_installation(a.installation, a.seal_sha256, a.plan_sha256)
        result=load_return(context, a.capture)[0]
    print(json.dumps(result, indent=2, sort_keys=True)); return 0


if __name__=='__main__':
    raise SystemExit(main())
