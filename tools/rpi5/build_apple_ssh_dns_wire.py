#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Current Apple DNS wire-parser prerequisite; never resolver I/O or a service.

Preserve original whole units and their bounded-input failures. Derive only
explicit size/truncation guards, retaining the compression and message parser.
The original full OpenSSH client/config stays intact. Target files never run.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_daemon as prior
from tools.rpi5 import prepare_pid1

ROOT, sha = prior.ROOT, prior.sha
BASE = ROOT/'build/rpi5/apple-ssh-daemon-q7mo0l8m'
BASE_SHA = '30e2b0e27ad7475af67269f9275ec05863fada044d36bfc668655bfeaba6521d'
SOURCE = ROOT/'build/rpi5/apple-libresolv-candidate-20261014'
COMMIT = 'e48cd914edc1cb14f8289b8e2dfdaac360481cd2'
UNITS = ('res_comp.c','ns_name.c','ns_netint.c','ns_parse.c')
HARNESS = ROOT/'tools/rpi5/tests/ssh_dns_wire_host.c'
TEST = ROOT/'tools/rpi5/tests/test_apple_ssh_dns_wire.py'
CLOSURE_TEST = ROOT/'tools/rpi5/tests/test_apple_pthread_startup_contract.py'
BOUNDARIES = ('zero-unpack','negative-expand','empty-skip','unterminated-skip',
              'short-extended-skip','short-extended-unpack')


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Exact original parser guard boundary required')
    return text.replace(old,new,1)


def checked(name, text):
    if name == 'res_comp.c':
        text=once(text,'#include <stdio.h>','#include <stdio.h>\n#include <errno.h>')
        return once(text, '{\n\tint n = ns_name_uncompress(msg, eom, src, dst, (size_t)dstsiz);',
            '{\n\tif (dstsiz <= 0) { errno = EMSGSIZE; return (-1); }\n'
            '\tint n = ns_name_uncompress(msg, eom, src, dst, (size_t)dstsiz);')
    if name != 'ns_name.c':
        return text
    text = once(text, '\tlen = -1;\n\tchecked = 0;\n\tdstp = dst;',
        '\tif (dstsiz == 0) { errno = EMSGSIZE; return (-1); }\n'
        '\tlen = -1;\n\tchecked = 0;\n\tdstp = dst;')
    text = once(text, '\t\t\t/* Limit checks. */\n\t\t\tif ((l = labellen(srcp - 1)) < 0)',
        '\t\t\t/* The extended label length byte is part of the bounded message. */\n'
        '\t\t\tif ((n & NS_CMPRSFLGS) == NS_TYPE_ELT && srcp >= eom) {\n'
        '\t\t\t\terrno = EMSGSIZE; return (-1);\n\t\t\t}\n'
        '\t\t\t/* Limit checks. */\n\t\t\tif ((l = labellen(srcp - 1)) < 0)')
    text = once(text, '\tcp = *ptrptr;\n\twhile (cp < eom',
        '\tcp = *ptrptr;\n\tif (cp >= eom) { errno = EMSGSIZE; return (-1); }\n\twhile (cp < eom')
    text = once(text, '\t\tcase 0:\t\t\t/*%< normal case, n == len */\n\t\t\tcp += n;',
        '\t\tcase 0:\t\t\t/*%< normal case, n == len */\n'
        '\t\t\tif ((size_t)(eom - cp) <= n) { errno = EMSGSIZE; return (-1); }\n\t\t\tcp += n;')
    text = once(text, '\t\t\tif (cp < eom && (l = labellen(cp - 1)) < 0)',
        '\t\t\tif (cp >= eom || (l = labellen(cp - 1)) < 0 || (size_t)(eom - cp) <= (size_t)l)')
    return text


def merge(*groups):
    result = {}
    for group in groups:
        for name,digest in group.items():
            if name in result and result[name] != digest:
                raise ValueError('Conflicting source pin '+name)
            result[name] = digest
    return result


def build():
    if sha(BASE/'manifest.json') != BASE_SHA:
        raise ValueError('Exact genuine full40 client predecessor required')
    base = json.loads((BASE/'manifest.json').read_text())
    pins = merge({str(BASE/'manifest.json'):BASE_SHA},
        *[base[k] for k in ('source_inputs_sha256','headers_sha256','generated_sha256')])
    for path in (Path(__file__).resolve(),HARNESS,TEST,CLOSURE_TEST,prior.preceding.FLAGS,
                 prior.preceding.ROOT/'tools/rpi5/prepare_pid1.py',*[SOURCE/n for n in UNITS]):
        pins=merge(pins,{str(path):sha(path)})
    for name in UNITS:
        if (SOURCE/name).read_bytes()!=subprocess.check_output(['git','-C',SOURCE,'show',COMMIT+':'+name]):
            raise ValueError('Exact whole original Apple libresolv source required')
    tools={str(Path(subprocess.check_output(['xcrun','--find',n],text=True).strip()).resolve()):None
        for n in ('clang','ar','nm','ld','llvm-objdump')}
    tools[str(Path('/usr/bin/xcrun').resolve())]=None
    tools={n:sha(n) for n in tools};pins=merge(pins,tools)
    def verify():
        for name,digest in pins.items():
            if sha(name)!=digest:raise ValueError('Source drift '+name)
    verify()
    out=Path(tempfile.mkdtemp(prefix='apple-ssh-dns-wire-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True)
    commands=[];headers={};records={}
    def run(args,label,allowed=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=90)
        for stream in ('stdout','stderr'):(out/(label+'.'+stream)).write_text(getattr(r,stream))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-5000:])
        return r
    def deps(text):
        return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    def compile_(flags,path,label):
        before=deps(run([*flags,'-M',path],label+'-scan').stdout)
        dep,obj=out/(label+'.d'),out/(label+'.o')
        run([*flags,'-MD','-MF',dep,'-c',path,'-o',obj],label+'-compile')
        after=deps(dep.read_text())
        if before!=after:raise ValueError('Actual compiler dependency changed')
        headers.update(before);records[label]=dict(scanned_sha256=before,consumed_sha256=after)
        return obj
    flags_doc=json.loads(prior.preceding.FLAGS.read_text())
    template=next(c['command'] for c in flags_doc['commands'] if c['stdout'].endswith('/readpassphrase-compile.stdout'))
    flags=template[:template.index('-MD')]+['-I',str(SOURCE)]
    native=[n for n in flags if n not in ('-ffreestanding','-mcpu=cortex-a76')]
    at=native.index('-target');del native[at:at+2]
    native+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=undefined']
    caller=compile_(native,HARNESS,'host-caller')
    originals=[compile_(native,SOURCE/n,'original-'+Path(n).stem) for n in UNITS]
    original_host=out/'original-dns-host';run([*native,*originals,caller,'-o',original_host],'original-host-link')
    negative={}
    for case in BOUNDARIES:
        r=run([original_host,case],'original-'+case,True)
        if case=='short-extended-unpack':
            if r.returncode==0 or 'AddressSanitizer: heap-buffer-overflow' not in r.stderr:
                raise ValueError('Original bounded extended-label failure not reproduced')
        elif case=='negative-expand':
            if r.returncode==0 or r.stdout or 'runtime error: addition of unsigned offset' not in r.stderr or 'UndefinedBehaviorSanitizer: undefined-behavior' not in r.stderr:
                raise ValueError('Original signed destination-size overflow not reproduced')
        elif (r.returncode,r.stdout,r.stderr)!=(38,'APPLE_DNS_BOUNDARY '+case+' SAFE=0\n',''):
            raise ValueError('Original boundary negative differs '+case)
        negative[case]=dict(returncode=r.returncode,stdout=r.stdout,
            sanitizer_heap_read=case=='short-extended-unpack',
            sanitizer_pointer_overflow=case=='negative-expand')
    overlay=out/'overlay';overlay.mkdir();targets=[];hosts=[]
    for name in UNITS:
        path=overlay/name;path.write_text(checked(name,(SOURCE/name).read_text()))
        targets.append(compile_(flags,path,'target-'+Path(name).stem))
        hosts.append(compile_(native,path,'host-'+Path(name).stem))
    archive=out/'libapple-dns-wire-checked.a';run(['xcrun','ar','rcs',archive,*targets],'archive')
    exported=[]
    for obj in targets:
        symbols=run(['xcrun','nm','-gjU',obj],obj.stem+'-exports').stdout.splitlines()
        exported.extend(symbols)
    forced=sorted(set(exported))
    if len(forced)!=len(exported) or '_res_9_dn_expand' not in forced:
        raise ValueError('Whole original units have missing/duplicate API owners')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    original_link=list(link)
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    linked=run([*link,archive],'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',linked.stderr,re.M)))
    duplicate=sorted(set(re.findall(r"duplicate symbol '([^']+)'",linked.stderr)))
    closed=sorted(set(base['target_missing_symbols'])-set(missing));added=sorted(set(missing)-set(base['target_missing_symbols']))
    if linked.returncode==0 or duplicate or closed!=['_res_9_dn_expand'] or added:
        raise ValueError('Unexpected full-client DNS closure delta '+repr((closed,added,duplicate)))
    directory=json.loads((prior.BASE/'manifest.json').read_text())
    contract=list(next(c['command'] for c in directory['commands'] if c['stdout'].endswith('/contract-link.stdout')))
    contract[contract.index('-o')+1]=str(out/'NOT_RUN_dns_contract')
    contract[contract.index('-map')+1]=str(out/'contract.map')
    contract += [str(archive)]+[v for symbol in forced for v in ('-u',symbol)]
    run(contract,'contract-link')
    target=out/'NOT_RUN_dns_contract'
    if run(['xcrun','nm','-ju',target],'contract-undefined').stdout:
        raise ValueError('Forced DNS APIs require unresolved providers')
    inspection=prepare_pid1.inspect(target.read_bytes())
    mapping=(out/'contract.map').read_text()
    object_map={int(i):n for i,n in re.findall(r'^\[\s*(\d+)\]\s+(.+)$',mapping,re.M)}
    owners={}
    for line in mapping.splitlines():
        match=re.match(r'^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+(\S+)$',line)
        if match and match[2] in forced+['___error']:
            owners[match[2]]=object_map[int(match[1])]
    if any(not owners.get(n,'').startswith(str(archive)+'(') for n in forced):
        raise ValueError('Actual live DNS symbols must come from this archive')
    host=out/'dns-host';run([*native,*hosts,caller,'-o',host],'host-link')
    good=run([host],'host-run')
    if not re.fullmatch(r'APPLE_DNS_WIRE PASS CASES=\d+ WHOLE_UNITS=4 BOUNDARY_CORRECTIONS=6 NO_NETWORK TARGET_NOT_RUN\n',good.stdout) or good.stderr:
        raise ValueError('Native whole-parser oracle differs')
    if run([host,'bad-expectation'],'host-negative',True).returncode!=37:raise ValueError('Negative oracle accepted')
    for case in BOUNDARIES:
        r=run([host,case],'checked-'+case)
        if r.stdout!='APPLE_DNS_BOUNDARY '+case+' SAFE=1\n' or r.stderr:raise ValueError('Checked boundary differs')
    verify()
    if any(sha(n)!=h for n,h in headers.items()):raise ValueError('Consumed header drift')
    report=dict(profile='current-apple-libresolv-wire-parser-checked-v1',source_inputs_sha256=pins,
        headers_sha256=headers,generated_sha256={},tools_sha256=tools,dependency_records=records,commands=commands,
        original_libresolv_commit=COMMIT,original_units=list(UNITS),whole_translation_units=True,
        derived_units=['res_comp.c','ns_name.c'],unchanged_units=['ns_netint.c','ns_parse.c'],
        boundary_corrections=list(BOUNDARIES),original_boundary_failures=negative,
        target_archive=str(archive),target_missing_symbols=missing,target_duplicate_symbols=duplicate,
        closed_symbols=closed,newly_reachable_symbols=added,previous_missing_count=40,remaining_missing_count=len(missing),
        original_full_client_link_command=original_link,all176_original_client_inputs_unchanged=True,
        original_openssh_config_unchanged=True,accepted_runtime_modified=False,provider_stubs=False,
        forced_apis=forced,live_symbol_owners=owners,static_inspection=inspection,
        native_asan_ubsan_pass=True,native_stdout=good.stdout,native_host_libc=True,
        native_all_exported_apis_exercised=False,parser_exhaustive_audit_claimed=False,
        network_operations=False,resolver_transport_qualified=False,resolver_service_qualified=False,
        full_client_qualified=False,target_executed=False,private_FILE_abi_mixed=False,
        remaining_provider_groups=prior.categories(missing))
    report['generated_sha256']={str(p):sha(p) for p in out.rglob('*') if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(output=str(out),manifest_sha256=sha(out/'manifest.json'),closed=closed,
        added=added,remaining=len(missing),forced_apis=len(forced),native_stdout=good.stdout),indent=2))
    return out,report


if __name__=='__main__':build()
