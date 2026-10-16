#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Root42 once-audit preparation with structured compiler-document traversal.

Preserves the reviewed stager and all prior graph implementations. Compiler
command strings are argument vectors, not pathnames; they are parsed, never
executed. Both the literal command document and resolved file bytes are sealed.
"""
import argparse
import json
from pathlib import Path
import shlex
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_root42_pthread_trial as stage


def package_graph(package,prior_pins):
    pins=dict(prior_pins);pending=[];seen=set()
    def add(name):
        if not isinstance(name,str) or not name.startswith('/') or name.startswith('/home/'):return
        path=Path(name).resolve();name=str(path)
        if name in pins or name.startswith('/home/'):return
        if path.is_dir() and path.is_relative_to(stage.ROOT/'build/rpi5'):
            manifest=path/'manifest.json'
            if manifest.is_file():add(str(manifest))
        elif path.is_file():
            pins[name]=stage.sha(path)
            if path.suffix=='.json':pending.append(path)
    def walk(value):
        if isinstance(value,dict):
            for name,item in value.items():
                add(name)
                if name=='command' and isinstance(item,str):
                    for argument in shlex.split(item):add(argument)
                else:walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
        elif isinstance(value,str):add(value)
    add(str(package/'manifest.json'))
    while pending:
        path=pending.pop()
        if path in seen:continue
        seen.add(path)
        if len(seen)>2000:raise ValueError('New package document graph exceeded bound')
        raw=path.read_text();offset=0;decoder=json.JSONDecoder()
        while raw[offset:].strip():
            offset+=len(raw[offset:])-len(raw[offset:].lstrip())
            if offset and raw[offset:].strip()==',':break
            try:value,end=decoder.raw_decode(raw,offset)
            except json.JSONDecodeError as error:raise ValueError('Unparseable new dependency report: '+str(path)) from error
            walk(value);offset=end
    return pins


def source_pins():
    paths=(Path(__file__).resolve(),stage.ROOT/'tools/rpi5/tests/test_root42_prepare_graph.py')
    return stage.source_pins()|{str(p):stage.sha(p) for p in paths}


def prepare_install(directory,prior_seal,prior_plan,boot,package=stage.PACKAGE):
    prior=types.SimpleNamespace(**{**vars(stage.prior),'package_graph':package_graph})
    return stage.private(stage.prepare_install,prior=prior,source_pins=source_pins)(directory,prior_seal,prior_plan,boot,package)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--prior-seal-sha256',required=True);p.add_argument('--prior-plan-sha256',required=True)
    p.add_argument('--linux-boot-id',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
    checkpoint,pin,metrics=prepare_install(a.baseline,a.prior_seal_sha256,a.prior_plan_sha256,a.linux_boot_id)
    out=stage.local(a.output);out.mkdir(exist_ok=False);stage.seals.save_new(out/'checkpoint.json',checkpoint,pin);stage.save(out/'metrics.json',metrics)
    print(json.dumps(dict(status='prepared_only',checkpoint_sha256=pin,output=str(out),metrics=metrics),indent=2,sort_keys=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
