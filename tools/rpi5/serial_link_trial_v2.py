#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Sealed next-link receive-only recorder; no compiler or historical audit replay."""
import argparse
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_link_trial_v2 as stage
import serial_pcie_trace_trial as original


def bound_sources(context):
    current=stage.source_pins()|{str(Path(m.__file__).resolve()):stage.sha(Path(m.__file__)) for m in
        (sys.modules[__name__],context['descriptor']['protocol'])}
    if any(context['evidence'].get(name)!=digest for name,digest in current.items()):
        raise ValueError('Recorder source absent from seal or changed since staging')
    return {name:context['evidence'][name] for name in current}


def revalidate(context):
    stage.seals.check_pins(context['evidence'])
    bound_sources(context)


def bindings(context):
    protocol=context['descriptor']['protocol'];directory=context['installed']['directory']
    def installed(path):
        if str(stage.local(path))!=directory:raise ValueError('Exact sealed installed pair required')
        revalidate(context);return context['installed']
    def receipts(path):
        installed(path);return context['evidence']
    # New receipt shape stays separate from old 128-ancestor semantics. The
    # accepted UART engine only receives the already checked installed binding.
    guard=types.SimpleNamespace(__file__=stage.__file__,receipt_evidence_pins=receipts)
    globals_=dict(original.__dict__,staging=stage,protocol=protocol,installation=installed,
        inventory=protocol.inventory,receipt_guard=guard,__file__=__file__,__doc__=__doc__)
    return types.FunctionType(original.main.__code__,globals_,argdefs=original.main.__defaults__)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('device');p.add_argument('output',type=Path)
    p.add_argument('--installation',type=Path,required=True);p.add_argument('--seal-sha256',required=True)
    p.add_argument('--plan-sha256',required=True);p.add_argument('--seconds',type=int,default=600);a=p.parse_args(argv)
    context=stage.load_installation(a.installation,a.seal_sha256,a.plan_sha256)
    if not context['descriptor']['hardware_allowed']:raise ValueError('Offline descriptor cannot open UART')
    return bindings(context)([a.device,str(a.output),'--installation',str(a.installation),'--seconds',str(a.seconds)])


if __name__=='__main__':raise SystemExit(main())
