#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Narrow supplemental replay adapter for one frozen RP1 protocol API omission.

The installed seal and recorder bytes are never edited or reinterpreted.  Only
PREPARED_PREFIX is exposed from the exact already-sealed inherited protocol.
This source is separately approved by --adapter-sha256, not claimed to have
belonged to the original installation.  No launch or installer is provided.
"""
import argparse
import builtins
import json
from pathlib import Path
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_pcie_trial_v3 as original_stage
import pcie_trial_evidence_v3 as original_evidence

SELF = Path(__file__).resolve()
FORMAT = 'rpi5-rp1-config-prepared-prefix-supplement-v1'
PREFIX = b'RPI5XNU:PCIEID:PREPARED '


def facade(protocol):
    """Preserve every original object; add exactly the omitted public constant."""
    expected = original_stage.ROOT/'tools/rpi5/rp1_config_trace_serial_core.py'
    parent = original_stage.ROOT/'tools/rpi5/pcie_link_elapsed_serial_core.py'
    if (Path(protocol.__file__).resolve() != expected or
            Path(protocol.prior.__file__).resolve() != parent or
            hasattr(protocol, 'PREPARED_PREFIX') or
            protocol.prior.PREPARED_PREFIX != PREFIX or
            protocol.PREFIX + b'PREPARED ' != PREFIX):
        raise ValueError('Exact frozen missing-export boundary required')
    return types.SimpleNamespace(**vars(protocol), PREPARED_PREFIX=protocol.prior.PREPARED_PREFIX)


def controller(expected_sha, installation, seal_sha, plan_sha, capture):
    stage = original_stage
    if stage.sha(SELF) != expected_sha:
        raise ValueError('Separately retained supplemental adapter digest differs')
    supplemental = {str(SELF): expected_sha}
    # This runner is deliberately new. All OTHER dynamically loaded sources
    # must still belong to the original seal through its unmodified validator.
    def loaded_sources():
        stage.seals.check_pins(supplemental)
        return {p: h for p, h in stage.base.loaded_sources().items() if p != str(SELF)}
    base = types.SimpleNamespace(**vars(stage.base))
    base.loaded_sources = loaded_sources
    load_installation = stage.private(stage.load_installation, base=base)
    context = load_installation(installation, seal_sha, plan_sha)
    if context['descriptor']['record']['adapter'] != 'rp1-config-trace':
        raise ValueError('Only the frozen RP1 config descriptor is compatible')
    protocol = context['descriptor']['protocol']
    facade(protocol)
    for module in (protocol, protocol.prior):
        name = str(Path(module.__file__).resolve())
        if context['evidence'].get(name) != stage.sha(name):
            raise ValueError('Inherited protocol was not sealed before installation')
    capture = stage.local(capture)
    record_path = capture/'protocol-compatibility.json'
    record = dict(format=FORMAT, installation=context['installed'],
        supplemental_source_sha256=supplemental,
        supplemental_was_in_original_installation_seal=False,
        added_attribute='PREPARED_PREFIX', value_ascii=PREFIX.decode(),
        inherited_source=str(Path(protocol.prior.__file__).resolve()),
        inherited_source_sha256=context['evidence'][str(Path(protocol.prior.__file__).resolve())],
        parser_function_unchanged=True, capture_bytes_unchanged=True,
        success_deadlines_and_hardware_guards_unchanged=True,
        capture_sha256={n: stage.sha(capture/n) for n in
            ('armed.json', 'state.json', 'serial.bin', 'receive-events.jsonl')})

    def ensure_record(write=False):
        stage.seals.check_pins(supplemental)
        if record_path.exists():
            if not stage.engine.same(json.loads(record_path.read_text()), record):
                raise ValueError('Supplemental provenance changed')
        elif write:
            stage.save(record_path, record)
        else:
            raise ValueError('Separate supplemental provenance record required')
        return supplemental | {str(record_path): stage.sha(record_path)}

    def captured(ctx, directory):
        # The recorder still validates its original source/evidence maps.
        private_context = dict(ctx, descriptor=dict(ctx['descriptor'],
            protocol=facade(ctx['descriptor']['protocol'])))
        return original_evidence.captured(private_context, directory)

    def return_source_pins():
        return original_evidence.return_source_pins() | ensure_record()

    evidence = types.SimpleNamespace()
    evidence.captured = captured
    evidence.return_source_pins = return_source_pins
    evidence.inspect_return = stage.private(original_evidence.inspect_return,
        return_source_pins=return_source_pins)
    evidence.collect_return = stage.private(original_evidence.collect_return,
        captured=captured, return_source_pins=return_source_pins,
        inspect_return=evidence.inspect_return)
    evidence.load_return = stage.private(original_evidence.load_return,
        captured=captured, return_source_pins=return_source_pins,
        inspect_return=evidence.inspect_return)

    def import_(name, *args, **kwargs):
        if name == 'pcie_trial_evidence_v3':
            return evidence
        return builtins.__import__(name, *args, **kwargs)

    def create(audit, pins):
        # Supplemental source/provenance first enter a seal at restoration.
        return stage.seals.create(audit, stage.merge_pins(pins, ensure_record()))

    seals = types.SimpleNamespace(**vars(stage.seals))
    seals.create = create
    scoped = dict(vars(builtins), __import__=import_)
    prepare_restore = stage.private(stage.prepare_restore,
        load_installation=load_installation, seals=seals, __builtins__=scoped)
    replay = stage.private(stage.replay, load_installation=load_installation,
        prepare_restore=prepare_restore, __builtins__=scoped)
    return types.SimpleNamespace(context=context, record=record, ensure_record=ensure_record,
        captured=captured, evidence=evidence, prepare_restore=prepare_restore, replay=replay)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=('check', 'return', 'restore', 'replay'))
    p.add_argument('--adapter-sha256', required=True)
    p.add_argument('--installation', type=Path, required=True)
    p.add_argument('--seal-sha256', required=True)
    p.add_argument('--plan-sha256', required=True)
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--output', type=Path)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--restoration', type=Path)
    p.add_argument('--restore-seal-sha256')
    p.add_argument('--restore-plan-sha256')
    a = p.parse_args(argv)
    stage = original_stage
    if a.execute and a.operation != 'restore':
        p.error('--execute only applies to explicit restoration')
    if a.operation == 'restore' and a.output is None:
        p.error('restoration requires a distinct --output')
    if a.operation == 'replay' and not all((a.restoration, a.restore_seal_sha256, a.restore_plan_sha256)):
        p.error('replay requires complete separately retained restoration references')
    with stage.lease.hold(stage.ROOT, 'rp1-config-supplemental-replay-v1'):
        bound = controller(a.adapter_sha256, a.installation, a.seal_sha256, a.plan_sha256, a.capture)
        if a.operation == 'check':
            _, observed, _ = bound.captured(bound.context, a.capture)
            value = dict(supplemental_provenance=bound.record, observed=observed,
                hardware_access=False, receipt_written=False)
        else:
            bound.ensure_record(write=a.operation == 'return')
            if a.operation == 'return':
                value = bound.evidence.collect_return(bound.context, a.capture)
            elif a.operation == 'restore':
                checkpoint, pin, metrics = bound.prepare_restore(a.installation,
                    a.seal_sha256, a.plan_sha256, a.capture)
                metrics['supplemental_compatibility'] = bound.record
                value = stage.dispatch(checkpoint, pin, a.output, metrics, a.execute)
            else:
                value = bound.replay(a.installation, a.seal_sha256, a.plan_sha256,
                    a.capture, a.restoration, a.restore_seal_sha256, a.restore_plan_sha256)
        print(json.dumps(value, sort_keys=True))


if __name__ == '__main__':
    main()
