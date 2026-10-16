#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact XNU console preparation with one pinned compiler-directory alias.

The immutable compiler argument document uses security//.. as an include
directory. It is metadata, not a file dependency or permission to walk a tree.
Only its22 exact -I argument positions in that document are admitted. All file
paths keep the preceding strict policy; the full checker and recorder admission
still execute. Frozen package/controller/publication sources are not modified.
"""
import json
from pathlib import Path
import types
from tools.rpi5 import stage_display_xnu_trial as stage

COMPILER_DOCUMENT=stage.ROOT/'build/rpi5-xcode27/fresh-435uage7/obj/DEVELOPMENT_ARM64_BCM2712/compile_commands.json'
COMPILER_SHA='a37e7544ade678f7d39679c53bfe92e69a734b14305523ce1a23ead2a7735f61'
INCLUDE_LITERAL=str(stage.ROOT)+'/security//..'


def include_directory(document,pin,arguments,index):
    if (document!=COMPILER_DOCUMENT or pin!=COMPILER_SHA or not isinstance(arguments,list) or
        type(index) is not int or not 0<index<len(arguments) or arguments[index-1]!='-I' or
        arguments[index]!=INCLUDE_LITERAL):
        raise ValueError('Noncanonical path is not the exact pinned include-directory metadata')
    path=Path(INCLUDE_LITERAL)
    if not path.is_dir() or path.resolve(strict=True)!=stage.ROOT:
        raise ValueError('Pinned include directory no longer resolves to exact workspace')


def package_graph(package,prior_pins):
    manifest=package/'manifest.json'
    if stage.sha(manifest)!=stage.MANIFEST_SHA:raise ValueError('Exact XNU console manifest required')
    record=json.loads(manifest.read_text())
    if record['inputs_sha256'].get(str(COMPILER_DOCUMENT))!=COMPILER_SHA or stage.sha(COMPILER_DOCUMENT)!=COMPILER_SHA:
        raise ValueError('Actual manifest-bound compiler document changed')
    pins=dict(prior_pins);pending=[];seen=set();admitted=[]
    def add(name,document=None,arguments=None,index=None):
        if not isinstance(name,str) or not name.startswith('/') or name.startswith('/home/'):return
        path=Path(name)
        if '..' in path.parts:
            include_directory(document,pins.get(str(document)),arguments,index)
            admitted.append((id(arguments),index));return
        if name in pins:return
        if path.is_dir() and path.is_relative_to(stage.ROOT/'build/rpi5'):
            child=path/'manifest.json'
            if child.is_file():add(str(child),document)
        elif path.is_file():
            pins[name]=stage.sha(path)
            if path.suffix=='.json':pending.append(path)
    def walk(value,document):
        if isinstance(value,dict):
            for name,item in value.items():
                add(name,document)
                if name=='arguments' and isinstance(item,list):
                    for index,argument in enumerate(item):
                        if isinstance(argument,str):add(argument,document,item,index)
                        else:walk(argument,document)
                else:walk(item,document)
        elif isinstance(value,list):
            for item in value:walk(item,document)
        elif isinstance(value,str):add(value,document)
    add(str(manifest))
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
            walk(value,path);offset=end
    # If already sealed, its immutable dependency edges are not walked again.
    expected=0 if str(COMPILER_DOCUMENT) in prior_pins else 22
    if len(admitted)!=expected:raise ValueError('Exact22 include argument positions required')
    return pins


def source_pins():
    files=(Path(__file__).resolve(),stage.ROOT/'tools/rpi5/tests/test_display_xnu_prepare.py')
    return stage.source_pins()|{str(path):stage.sha(path) for path in files}


def prepare_install(directory,prior_seal,prior_plan,boot):
    preceding=types.SimpleNamespace(**{**vars(stage.preceding),'package_graph':package_graph})
    prepare=stage.private(stage.prepare_install,preceding=preceding,source_pins=source_pins)
    return prepare(directory,prior_seal,prior_plan,boot)


main=stage.private(stage.main,prepare_install=prepare_install,__doc__=__doc__)
if __name__=='__main__':raise SystemExit(main())
