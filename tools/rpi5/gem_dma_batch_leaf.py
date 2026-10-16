# SPDX-License-Identifier: BSD-2-Clause
"""Byte-only proof of the actual A76 fixed64-byte CPU-RAM access leaves.

This deliberately pins the compiler's narrow instruction shape. No disassembly
text, manifest-supplied instruction counts, execution, or DMA proof is trusted.
The containing source/compile recipe and pre/post ownership are separate checks.
"""
import hashlib
import struct

def functions(data):
    if len(data)<32 or struct.unpack_from('<IIII',data)!=(0xfeedfacf,0x100000c,0,1):
        raise ValueError('Exact arm64 Mach-O object required')
    ncmds,size=struct.unpack_from('<II',data,16)
    if ncmds>64 or 32+size>len(data):raise ValueError('Bad load commands')
    pos=32;sections=[];table=None
    for _ in range(ncmds):
        if pos+8>32+size:raise ValueError('Truncated command')
        cmd,length=struct.unpack_from('<II',data,pos)
        if length<8 or pos+length>32+size:raise ValueError('Bad command extent')
        if cmd==0x19:
            count=struct.unpack_from('<I',data,pos+64)[0]
            if length!=72+80*count:raise ValueError('Bad segment sections')
            for i in range(count):
                p=pos+72+i*80;name=data[p:p+16].rstrip(b'\0');seg=data[p+16:p+32].rstrip(b'\0')
                address,extent,offset=struct.unpack_from('<QQI',data,p+32)
                sections.append((name,seg,address,extent,offset))
        elif cmd==2:
            if table is not None or length!=24:raise ValueError('Ambiguous symbols')
            table=struct.unpack_from('<IIII',data,pos+8)
        pos+=length
    if pos!=32+size or table is None:raise ValueError('Missing symbols')
    off,count,strings,bytes_=table
    if off+count*16>len(data) or strings+bytes_>len(data):raise ValueError('Truncated symbols')
    matches=[(i+1,s) for i,s in enumerate(sections) if s[:2]==(b'__text',b'__TEXT')]
    if len(matches)!=1:raise ValueError('Ambiguous text')
    section,(name,seg,address,extent,offset)=matches[0]
    if offset+extent>len(data):raise ValueError('Truncated text')
    symbols=[]
    for i in range(count):
        index,type_,sect,desc,value=struct.unpack_from('<IBBHQ',data,off+16*i)
        if (type_&0xe)!=0xe or sect!=section:continue
        if index>=bytes_ or not address<=value<address+extent:raise ValueError('Bad symbol')
        stop=data.find(b'\0',strings+index,strings+bytes_)
        if stop<0:raise ValueError('Unterminated symbol')
        symbols.append((value,data[strings+index:stop].decode('ascii')))
    boundaries=sorted(set(v for v,_ in symbols)|{address+extent});result={}
    for value,name in symbols:
        end=next(p for p in boundaries if p>value)
        if name in result or (end-value)%4:raise ValueError('Ambiguous instruction span')
        result[name]=(offset+value-address,data[offset+value-address:offset+end-address])
    return result

def inspect(data):
    table=functions(data);report={}
    specs=(('write','__ZN18BCM2712GEMDMABatch9ringWriteEPvPK22rpi5_gem_stage_sessionjjPKj',
            19,8,[base+x for base in (0,16,32,48) for x in (8,12,4,0)]),
           ('read','__ZN18BCM2712GEMDMABatch8ringReadEPvPK22rpi5_gem_stage_sessionjjPj',
            8,23,list(range(0,64,4))))
    for label,symbol,source,destination,offsets in specs:
        if symbol not in table:raise ValueError('Missing actual batch leaf')
        file_offset,body=table[symbol];words=list(struct.unpack('<'+'I'*(len(body)//4),body))
        # Match both pointers, every offset and the exact LDR/STR interleave.
        # A scratch may alias the source only in the last pair (clang does so
        # for the last read). It must never destroy the destination pointer.
        found=[]
        for i in range(len(words)-31):
            valid=True
            for j,offset in enumerate(offsets):
                load,store=words[i+2*j:i+2*j+2];scratch=load&31
                valid &= scratch not in (31,destination) and (scratch!=source or j==15)
                valid &= load==(0xb9400000|((offset//4)<<10)|(source<<5)|scratch)
                valid &= store==(0xb9000000|((offset//4)<<10)|(destination<<5)|scratch)
            if valid:found.append(i)
        if len(found)!=1:raise ValueError('Exact16-pair straight-line batch missing: '+label)
        start=found[0]
        # There must be no additional 32-bit accesses through either batch
        # pointer outside this exact bounded sequence (stack/owner loads differ).
        accesses=[i for i,w in enumerate(words) if (w&0xffc00000) in (0xb9000000,0xb9400000)
                  and ((w>>5)&31) in (source,destination)]
        if any(i<start or i>=start+32 for i in accesses):raise ValueError('Extra unbounded batch access')
        report[label]=dict(symbol=symbol,file_offset=file_offset+4*start,
            instruction_bytes=128,loads=16,stores=16,offsets=offsets,
            no_calls_or_branches_inside=True,sha256=hashlib.sha256(body[4*start:4*(start+32)]).hexdigest())
    return report

def allocation_guard(data):
    """Require actual nullable-new branch before the actual constructor call."""
    table=functions(data);symbol='__ZN23BCM2712PCIePHYTransport20prepareCPUOwnedRingsEv'
    if symbol not in table:raise ValueError('Actual preparation body absent')
    function_offset,body=table[symbol];pos=32;relocations=None;symtab=None
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        cmd,size=struct.unpack_from('<II',data,pos)
        if cmd==2:symtab=struct.unpack_from('<IIII',data,pos+8)
        if cmd==0x19:
            for i in range(struct.unpack_from('<I',data,pos+64)[0]):
                at=pos+72+i*80
                if data[at:at+16].rstrip(b'\0')==b'__text':
                    text_offset=struct.unpack_from('<I',data,at+48)[0]
                    relocations=struct.unpack_from('<II',data,at+56)
        pos+=size
    if relocations is None or symtab is None:raise ValueError('Missing real text relocations')
    r,n=relocations;s,count,strings,string_bytes=symtab;calls={}
    if r+n*8>len(data):raise ValueError('Truncated relocations')
    for i in range(n):
        address,bits=struct.unpack_from('<II',data,r+8*i)
        if bits>>28!=2 or (bits>>24)&15!=13:continue # external PC-relative BRANCH26/length2
        index=bits&0xffffff
        if index>=count:raise ValueError('Bad relocation symbol')
        name_at=struct.unpack_from('<I',data,s+16*index)[0]
        end=data.find(b'\0',strings+name_at,strings+string_bytes)
        if end<0:raise ValueError('Bad relocation string')
        name=data[strings+name_at:end].decode()
        off=text_offset+address
        if function_offset<=off<function_offset+len(body):calls.setdefault(name,[]).append(off)
    alloc=calls.get('__Znwm',[]);ctor=calls.get('__ZN18BCM2712GEMDMABatchC1Ev',[])
    if len(alloc)!=1 or len(ctor)!=1 or ctor[0]!=alloc[0]+8:raise ValueError('Exact allocator/constructor boundary differs')
    branch=struct.unpack_from('<I',data,alloc[0]+4)[0]
    if branch&0xff00001f!=0xb4000000:raise ValueError('Nullable-new CBZ x0 absent')
    immediate=(branch>>5)&0x7ffff
    if immediate&0x40000:immediate-=0x80000
    target=alloc[0]+4+4*immediate
    if not ctor[0]+4<=target<function_offset+len(body):raise ValueError('Null allocation does not skip constructor')
    # Exact failure tail first detaches null handle, then stores irreversible
    # phase3. No additional constructor/allocation call exists on this branch.
    tail=struct.unpack_from('<III',data,target)
    if (tail[0]&0xffc0001f)!=0xf900001f or tail[1]!=0x52800068 or (tail[2]&0xffc0001f)!=0xb9000008:
        raise ValueError('Null allocation quarantine tail differs')
    return dict(allocation_call=alloc[0],constructor_call=ctor[0],null_branch=alloc[0]+4,
        failure_target=target,null_before_constructor=True,phase3_on_failure=True)
