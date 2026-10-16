# SPDX-License-Identifier: BSD-2-Clause
"""Freestanding arm64 link audit of the aggregate crypto candidate, not a kernel boot."""
import hashlib
import argparse
import json
import subprocess
from pathlib import Path
import tempfile
from probe_bearssl import ROOT, SOURCE, REVISION, UNITS, run

ADAPTERS = ('sha512_compress','sha512_digest','sha256_digest','legacy_digest',
    'digest_dispatch','hmac','crypto_digest','crypto_hmac','aes_ecb','aes_gcm',
    'des','cts','ccrng','crypto_random','rsa','rsa_digest','rsa_verify',
    'chacha_stream','poly1305','chachapoly','chachapoly_binding','crypto_table')
EXTRA = ('symcipher/aes_ct64','symcipher/aes_ct64_enc','symcipher/aes_ct64_dec',
    'symcipher/aes_ct64_cbcenc','symcipher/aes_ct64_cbcdec','symcipher/aes_ct64_ctr',
    'aead/gcm','hash/ghash_ctmul64','symcipher/des_ct','symcipher/des_ct_cbcenc',
    'symcipher/des_ct_cbcdec','symcipher/des_support','symcipher/chacha20_ct',
    'rsa/rsa_i31_pub','rsa/rsa_i31_pkcs1_vrfy','rsa/rsa_pkcs1_sig_unpad',
    'int/i32_div32','codec/ccopy')

def dependency_closure(records, root):
    """Object-granularity closure; do not mistake it for function dead stripping."""
    owners={}
    for index,(defined,_) in enumerate(records):
        for symbol in defined:
            if symbol in owners:
                raise RuntimeError('Duplicate global definition: '+symbol)
            owners[symbol]=index
    if root not in owners:
        raise RuntimeError('Missing root: '+root)
    pending=[owners[root]]; selected=set()
    while pending:
        index=pending.pop()
        if index in selected:
            continue
        selected.add(index)
        pending.extend(owners[s] for s in records[index][1] if s in owners)
    return sorted(selected)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-adapters',action='store_true',
        help='compile adapters with recorded BCM2712 flags; primitives remain freestanding')
    parser.add_argument('--with-startup',action='store_true',
        help='also link PRNG adapters and coordinator; requires --kernel-adapters')
    parser.add_argument('--build-root',type=Path,default=ROOT/'build/rpi5',
        help='Build workspace for recorded compiler flags and candidate outputs')
    args=parser.parse_args()
    if args.with_startup and not args.kernel_adapters:
        parser.error('--with-startup requires --kernel-adapters')
    revision=run(['git','-C',str(SOURCE),'rev-parse','HEAD']).strip()
    if revision!=REVISION or run(['git','-C',str(SOURCE),'status','--porcelain','--untracked-files=all']).strip():
        raise RuntimeError('Requires the clean pinned BearSSL candidate')
    build_root=args.build_root.resolve()
    if not build_root.is_relative_to((ROOT/'build').resolve()):
        raise RuntimeError('Crypto build root must stay under this project build directory')
    directory=Path(tempfile.mkdtemp(prefix='crypto-table-probe-',dir=build_root))
    sources=[SOURCE/'src'/(u+'.c') for u in UNITS+EXTRA]
    sources+=sorted((SOURCE/'src/int').glob('i31_*.c'))
    sources+=[ROOT/'osfmk/prng'/('rpi5_'+u+'.c') for u in ADAPTERS]
    if args.with_startup:
        sources+=[ROOT/'osfmk/prng'/('rpi5_'+u+'.c') for u in
            ('prng_generator','prng_refresh','prng_provider','prng_binding','prng_platform','crypto_startup')]
    flags=['-arch','arm64','-mcpu=cortex-a76','-mgeneral-regs-only','-ffreestanding',
        '-fno-builtin','-fno-stack-protector','-D_FORTIFY_SOURCE=0','-O2',
        '-I'+str(SOURCE/'inc'),'-I'+str(SOURCE/'src'),
        '-I'+str(ROOT/'EXTERNAL_HEADERS'),'-I'+str(ROOT/'libkern')]
    commands=[]; objects=[]
    kernel_entry=None; kernel_command=None; record=None
    if args.kernel_adapters:
        record=build_root/'obj/DEVELOPMENT_ARM64_BCM2712/osfmk/DEVELOPMENT/prng_random.o.json'
        kernel_entry=json.loads(record.read_text().strip().rstrip(','))
        kernel_command=[]
        iterator=iter(kernel_entry['arguments'])
        for arg in iterator:
            if arg in ('-o','-MF','-MT','-MQ','-MJ'):
                next(iterator)
            elif arg not in ('-MD','-MMD',kernel_entry['file']):
                kernel_command.append(arg)
        kernel_command+=['-I'+str(SOURCE/'inc')]
    for number,source in enumerate(sources):
        obj=directory/(str(number)+'-'+source.stem+'.o')
        command=['xcrun','clang',*flags,'-c',str(source),'-o',str(obj)]
        if kernel_command and source.parent==ROOT/'osfmk/prng':
            command=[*kernel_command,str(source),'-o',str(obj)]
            result=subprocess.run(command,cwd=kernel_entry['directory'],text=True,capture_output=True)
            if result.returncode:
                raise RuntimeError(result.stdout+result.stderr)
        else:
            run(command)
        commands.append(command); objects.append(str(obj))
    records=[]
    for obj in objects:
        defined=set(); unresolved=set()
        for line in run(['xcrun','nm','-g',obj]).splitlines():
            fields=line.split()
            if len(fields)<2:
                continue
            kind,symbol=fields[-2:]
            (unresolved if kind=='U' else defined).add(symbol)
        records.append((defined,unresolved))
    selected=dependency_closure(records,'_rpi5_crypto_platform_start' if args.with_startup else '_rpi5_crypto_functions')
    combined=directory/'crypto-table.o'
    command=['xcrun','ld','-r','-arch','arm64','-o',str(combined),*[objects[i] for i in selected]]
    commands.append(command); run(command)
    undefined=set(run(['xcrun','nm','-u',str(combined)]).split())
    # Clang lowers some zero-initialized cipher contexts to bzero even with
    # -fno-builtin. It is an expected XNU memory primitive, not a libc RNG.
    allowed={'_memcpy','_memset','_memcmp','_memmove','_bzero','_read_random'}
    if args.kernel_adapters:
        allowed|={'___stack_chk_guard','___stack_chk_fail'}
    if args.with_startup:
        allowed|={'_boot_cpu_id','_cpu_number','_crypto_init','_g_crypto_funcs','_startup_phase',
            '_early_random','_register_crypto_functions','_register_and_init_prng',
            '_panic','_lck_grp_init','_lck_mtx_init','_lck_mtx_lock','_lck_mtx_try_lock','_lck_mtx_unlock'}
    if undefined!=allowed:
        raise RuntimeError(f'Unexpected dependency set: {sorted(undefined)}; artifacts: {directory}')
    symbols=run(['xcrun','nm','-g',str(combined)])
    if '_rpi5_crypto_functions' not in symbols:
        raise RuntimeError('Missing aggregate table symbol')
    report={'bearssl_revision':revision,'scope':('crypto table plus PRNG adapters/coordinator; kernel services external'
        if args.with_startup else 'crypto table, excludes kernel PRNG implementation/startup'),
        'with_startup':args.with_startup,
        'kernel_adapter_flags':args.kernel_adapters,
        'kernel_flags_record_sha256':hashlib.sha256(record.read_bytes()).hexdigest() if record else None,
        'undefined':sorted(undefined),'commands':commands,
        'selected_sources':[str(sources[i].relative_to(ROOT)) for i in selected],
        'omitted_sources':[str(s.relative_to(ROOT)) for i,s in enumerate(sources) if i not in selected],
        'source_sha256':{str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in sources},
        'object_sha256':hashlib.sha256(combined.read_bytes()).hexdigest(),
        'compiler':run(['xcrun','clang','--version'])}
    (directory/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'directory':str(directory),'compiled_sources':len(sources),
        'linked_sources':len(selected),'omitted_sources':report['omitted_sources'],'undefined':sorted(undefined)}))

if __name__=='__main__':
    main()
