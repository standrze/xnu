# SPDX-License-Identifier: BSD-2-Clause
"""Offline acceptance test for the fixed embedded publisher namespace.

This is NOT a Python sandbox or a media authorization mechanism. Inputs must be
trusted, independently source-pinned generated programs. It rejects hidden host
file/import dependencies by executing the exact embedded sources with file,
process and network entry points disabled, never the final publisher dispatch.
The only execute-path test stops at an injected first identity-check sentinel.
Real target identity, files, devices, publication and recovery need their own
unchanged tests/admission. The preserved failed program is never rewritten.
"""
import ast
import builtins
import contextlib
import copy
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import re
import socket
import stat
import struct
import subprocess
import sys
import threading
import types
from unittest.mock import patch

HELPERS=('capture','helper','snapshots','reference','guarded',
         'pcie_trace_pair_core','trial_checkpoint_v2')
STANDARD={'copy','fcntl','hashlib','json','os','pathlib','pwd','re','stat',
          'struct','subprocess','types'}

class DependencyViolation(ValueError):
    pass

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def shape(node,text):
    return ast.dump(node,include_attributes=False)==ast.dump(ast.parse(text).body[0],include_attributes=False)

def unpack(source,expected_sha,expected_modules,expected_plan_sha):
    """Require the exact nine-module envelope, source bytes and sole dispatch.

    expected_modules maps each embedded name to its separately retained source
    digest. No digest obtained from this program grants it trust. Paths are
    identifiers only: the exercise below refuses even path resolution/stat.
    """
    if not isinstance(source,str) or sha(source.encode())!=expected_sha:
        raise ValueError('Separately retained remote-program bytes differ')
    tree=ast.parse(source)
    if len(tree.body)!=57 or not shape(tree.body[0],'import types,sys,json'):
        raise ValueError('Exact nine-module remote envelope required')
    rows=[]
    for i in range(9):
        nodes=tree.body[1+6*i:7+6*i]
        node=nodes[0]
        if not isinstance(node,ast.Assign) or len(node.targets)!=1 or not isinstance(node.targets[0],ast.Name):
            raise ValueError('Explicit module name required')
        name=node.targets[0].id
        if not re.fullmatch('[a-z][a-z0-9_]*',name):raise ValueError('Bounded module identifier required')
        try:
            filename=ast.literal_eval(nodes[2].value)
            text=ast.literal_eval(nodes[4].value)
        except (AttributeError,ValueError,TypeError) as e:raise ValueError('Literal file/source required') from e
        if (not isinstance(filename,str) or not filename.startswith('/') or not isinstance(text,str) or
            len(text)>1024*1024):raise ValueError('Bounded literal embedded source required')
        wanted=(f'{name}=types.ModuleType({name!r})',f'sys.modules[{name!r}]={name}',
                f'{name}.__file__={filename!r}',f'{name}.__package__=""',
                f'{name}._active_window_source={text!r}',f'exec({text!r},{name}.__dict__)')
        if any(not shape(a,b) for a,b in zip(nodes,wanted)):
            raise ValueError('Module source/identity/exec envelope differs')
        rows.append(dict(name=name,filename=filename,source=text,sha256=sha(text.encode())))
    names=tuple(r['name'] for r in rows)
    if (names[:7]!=HELPERS or len(set(names))!=9 or not names[7].endswith('_case_v1') or
        not names[8].endswith('_media_v1') or names[7][:-8]!=names[8][:-9] or
        type(expected_modules) is not dict or set(expected_modules)!=set(names) or
        any(expected_modules[r['name']]!=r['sha256'] for r in rows)):
        raise ValueError('Exact helper/case/media source inventory differs')
    try:plan=ast.literal_eval(tree.body[55].value.args[0]);plan=json.loads(plan)
    except (AttributeError,ValueError,TypeError,IndexError) as e:raise ValueError('Literal JSON plan required') from e
    if not shape(tree.body[55],'PLAN=json.loads('+repr(json.dumps(plan))+')'):
        # JSON whitespace is not authority, but the input expression must be
        # precisely json.loads of its unchanged literal string.
        literal=ast.literal_eval(tree.body[55].value.args[0])
        if not shape(tree.body[55],'PLAN=json.loads('+repr(literal)+')'):
            raise ValueError('Exact PLAN assignment required')
    if sha(canonical(plan))!=expected_plan_sha:raise ValueError('Separately retained plan differs')
    final=f'print(json.dumps({names[8]}.execute(PLAN,{expected_plan_sha!r},capture,helper,snapshots,reference,guarded)))'
    if not shape(tree.body[56],final):raise ValueError('Sole exact final dispatch required')
    return rows,plan

def hazards(rows):
    """Inventory possible I/O sites, not a claim that unused paths are reached."""
    result=[]
    interesting={'read_bytes','read_text','open','resolve','stat','lstat','readlink',
                 'sha','check_pins','revalidate','remote_source','source_pins'}
    for row in rows:
        class Visitor(ast.NodeVisitor):
            def __init__(self):self.scope='<module>'
            def visit_FunctionDef(self,node):
                before=self.scope;self.scope=node.name;self.generic_visit(node);self.scope=before
            visit_AsyncFunctionDef=visit_FunctionDef
            def visit_Call(self,node):
                name=node.func.attr if isinstance(node.func,ast.Attribute) else getattr(node.func,'id','')
                if name in interesting:
                    result.append(dict(module=row['name'],scope=self.scope,line=node.lineno,call=ast.unparse(node.func)))
                self.generic_visit(node)
        Visitor().visit(ast.parse(row['source']))
    return result

def exercise(rows,plan,expected_plan_sha):
    """No real target operation; zero-I/O bootstrap and pure runtime boundary.

    All imports must resolve to preloaded stdlib or the exact embedded modules.
    Source/plan construction is outside this guard; all embedded module bodies,
    validate_plan, bound_core and execute-to-identity run inside it. geteuid is
    explicitly a root double, identity immediately raises a unique sentinel.
    File APIs including stat/resolve are denied, not backed by host fixtures.
    """
    names={r['name'] for r in rows};events=[];old_import=builtins.__import__
    def denied(operation):
        def stop(*args,**kwargs):
            events.append(operation)
            raise DependencyViolation('Remote namespace attempted '+operation)
        return stop
    def restricted_import(name,globals=None,locals=None,fromlist=(),level=0):
        if level:raise ImportError('Embedded modules have no filesystem package')
        if name not in names and name not in STANDARD:
            raise DependencyViolation('Remote namespace attempted unembedded import: '+name)
        if name not in sys.modules:raise DependencyViolation('Remote namespace import not already embedded/preloaded: '+name)
        return old_import(name,globals,locals,fromlist,level)
    class IdentityBoundary(Exception):pass
    identity_calls=[]
    def identity(binding):
        if canonical(binding)!=canonical(plan['media']['identity_binding']):
            raise ValueError('Original publisher identity binding changed')
        identity_calls.append(True);raise IdentityBoundary()
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.dict(sys.modules,dict(sys.modules)))
        for module,attrs in (
            (builtins,('open',)),(io,('open',)),
            (os,('open','read','write','pread','pwrite','fdopen','fstat','fstatvfs','fsync','fchmod','fchown',
                 'stat','lstat','statvfs','scandir','listdir','readlink','access','chdir',
                 'mkdir','makedirs','remove','unlink','rename','replace','rmdir','system','fork',
                 'posix_spawn','posix_spawnp','execv','execve','execvp','execvpe')),
            (Path,('resolve',)),(subprocess,('Popen','run','check_output','call','check_call')),
            (socket,('socket','create_connection','getaddrinfo')),(fcntl,('ioctl','flock','fcntl')),
            (pwd,('getpwnam','getpwuid','getpwall')),
            (threading.Thread,('start',))):
            for attr in attrs:
                if hasattr(module,attr):stack.enter_context(patch.object(module,attr,denied(module.__name__+'.'+attr)))
        stack.enter_context(patch.object(os,'geteuid',lambda:0))
        stack.enter_context(patch.object(builtins,'__import__',restricted_import))
        namespace={}
        for row in rows:
            module=types.ModuleType(row['name']);module.__file__=row['filename'];module.__package__=''
            module._active_window_source=row['source'];sys.modules[row['name']]=module;namespace[row['name']]=module
            exec(compile(row['source'],'<sealed-embedded:'+row['name']+'>','exec'),module.__dict__)
        engine=namespace[rows[-1]['name']]
        engine.validate_plan(copy.deepcopy(plan))
        core=engine.bound_core(plan['tag']);core.validate_files(plan['media'])
        if core.TARGETS!=('config.txt','bl31.bin','probe.bin'):raise ValueError('Three-target runtime publisher required')
        capture=types.SimpleNamespace(identity=identity)
        try:
            engine.execute(copy.deepcopy(plan),expected_plan_sha,capture,
                namespace['helper'],namespace['snapshots'],namespace['reference'],namespace['guarded'])
        except IdentityBoundary:pass
        else:raise ValueError('Original publisher did not stop at first identity boundary')
    if events or identity_calls!=[True]:raise ValueError('Unexpected I/O or identity count')
    return dict(bootstrap_no_io=True,pure_plan_no_io=True,actual_execute_to_identity=True,
                identity_calls=1,root_is_test_double=True,dispatch_executed=False,
                device_access=False,publication_tested=False,whole_runtime_path_proven=False)

def inspect(source,expected_sha,expected_modules,expected_plan_sha):
    rows,plan=unpack(source,expected_sha,expected_modules,expected_plan_sha)
    return dict(profile='fixed-embedded-publisher-namespace-audit-v1',remote_sha256=expected_sha,
        plan_sha256=expected_plan_sha,modules={r['name']:r['sha256'] for r in rows},
        possible_io_sites=hazards(rows),**exercise(rows,plan,expected_plan_sha))
