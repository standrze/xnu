# SPDX-License-Identifier: BSD-2-Clause
"""Narrow v2 oracle for the real Apple pwd shared-bootstrap prolog.

The frozen v1 failure is preserved. This parses command observations only:
no serial open, no replayed commands, no retroactive final-exit acceptance.
"""
import types
try:
    from . import root41_batch_trial_core as original
except ImportError:
    import root41_batch_trial_core as original

PWD_STARTUP=(b'DARWIN:ZSH:ENTRY',b'DARWIN:ZSH:TSD',b'DARWIN:ZSH:ENTROPY',b'DARWIN:ZSH:MAIN')
for _name in ('hashlib','re','t','previous','statprobe','metadata','clean_lines','markers','STEPS',
              'CRYPTO_BEGIN','CRYPTO_PASS','CHECKS','WATCHDOG','WATCHDOG_PROFILE','DEVICE','FDT','IDENTITY',
              'boot_ready','validate_root','returned','batch_command','recovery_command','nonce_valid','script'):
    globals()[_name]=getattr(original,_name)


def inspect_batch(raw,nonce,files):
    lines=clean_lines(raw);expected=markers(nonce)
    if [line for line in lines if line.startswith(b'B41:')]!=expected:
        raise ValueError('Missing/duplicate/reordered/nonzero batch result or wrong nonce')
    if any(m in raw for m in (*t.FORBIDDEN,b'RPI5XNU:SSHBUFFER:FAIL',b'RPI5XNU:SSHCRYPTO:FAIL')):
        raise ValueError('Failed batch executable')
    bodies={name:lines[lines.index(expected[1+2*i])+1:lines.index(expected[2+2*i])]
            for i,(name,_) in enumerate(STEPS)}
    def exact(name,required):
        if bodies[name]!=required:raise ValueError('Actual '+name+' output differs')
    previous.exact_lines(b'\n'.join(bodies['zsh']),t.SMOKE_LINES)
    previous.exact_lines(b'\n'.join(bodies['buffer']),[previous.BEGIN,previous.PASS])
    previous.exact_lines(b'\n'.join(bodies['crypto']),[CRYPTO_BEGIN,CRYPTO_PASS])
    exact('pwd',list(PWD_STARTUP)+[b'/']);exact('uname',[b'Darwin'])
    motd=files['/etc/motd'][0]
    words=len(re.findall(rb'[^ \t\n\r\v\f]+',motd))
    exact('wc',[f'{motd.count(bytes([10]))} {words} {len(motd)}'.encode()])
    hexed=b''.join(f'{value:02x}'.encode()+(b'\n' if (i+1)%16==0 else b' ') for i,value in enumerate(motd))
    if len(motd)%16:hexed+=b'\n'
    exact('hex',hexed.splitlines())
    observed=statprobe.parse_diagnostic(b'\n'.join(bodies['stat']))
    accepted=metadata.accept_metadata(observed,files)
    return dict(batch_framing_and_all_eight_statuses_zero=True,nonce=nonce,
        commands=[dict(name=name,command=command,status=0,output_sha256=hashlib.sha256(b'\n'.join(bodies[name])).hexdigest()) for name,command in STEPS],
        actual_zsh_smoke=True,actual_ssh_buffer=True,actual_chacha_poly1305_public_kats=True,
        actual_apple_pwd_physical_root=True,canonical_multicall_utilities=True,metadata=accepted,
        batch_process_exit_verified=False,ssh_daemon=False,ssh_transport=False,networking=False,
        crypto_scope='Public primitive KATs/boundaries only; not SSH, entropy or AEAD proof')


# Future recorder may select this explicit version, while all timing, TX bounds,
# identity and separate real recovery-status semantics remain unchanged.
_bindings=dict(original.__dict__,inspect_batch=inspect_batch)
commands=types.FunctionType(original.commands.__code__,_bindings,argdefs=original.commands.__defaults__)
