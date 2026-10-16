# SPDX-License-Identifier: BSD-2-Clause
"""Actual fixed CPU-only batch body, exhaustive faults; no hardware authority."""
from pathlib import Path
import hashlib
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]
CORE=ROOT/'iokit/Kernel/rpi5_gem_ring_batch.c'
def host():
    source=(ROOT/'tools/rpi5/tests/gem_ring_stage_host.c').read_text()
    source=source.replace('"rpi5_gem_ring_stage.h"','"rpi5_gem_ring_batch.h"')
    source=source.replace('rpi5_gem_ring_stage(','rpi5_gem_ring_batch(').replace('rpi5_gem_stage_io','rpi5_gem_batch_io')
    a=source.index('static int write32(');b=source.index('static void init(',a)
    source=source[:a]+'''static unsigned partial;
static int write64(void *context,const struct rpi5_gem_stage_session *s,unsigned ring,uint32_t offset,const uint32_t values[16])
{
    assert(context==&events && s==&session);
    assert(rpi5_gem_ring_batch_access_allowed(s,RPI5_GEM_STAGE_WRITE,ring,offset));
    assert(rpi5_gem_ring_batch_values(s,&request,ring,offset,values));
    uint32_t wrong[16];memcpy(wrong,values,sizeof wrong);wrong[15]^=1;
    assert(!rpi5_gem_ring_batch_values(s,&request,ring,offset,wrong));
    assert(!rpi5_gem_ring_batch_access_allowed(s,RPI5_GEM_STAGE_WRITE,ring,offset+4));
    events++;assert(events==s->callbacks);
    if(events==target && mode==FAIL_BEFORE_WRITE)return -1;
    const unsigned order[]={2,3,1,0};unsigned count=0;
    for(unsigned descriptor=0;descriptor<4;descriptor++)for(unsigned p=0;p<4;p++){
        unsigned index=4*descriptor+order[p];
        *(uint32_t *)(void *)(rings[ring]+offset+4*index)=values[index];
        if(++count==partial && events==target)return -1;
    }
    return finish();
}
static int read64(void *context,const struct rpi5_gem_stage_session *s,unsigned ring,uint32_t offset,uint32_t values[16])
{
    assert(context==&events && s==&session);
    assert(rpi5_gem_ring_batch_access_allowed(s,RPI5_GEM_STAGE_READ,ring,offset));
    events++;assert(events==s->callbacks);
    for(unsigned i=0;i<16;i++)values[i]=*(uint32_t *)(void *)(rings[ring]+offset+4*i);
    if(corrupt==events)values[15]^=1;
    return finish();
}
static int barrier(void *context,const struct rpi5_gem_stage_session *s)
{
    assert(context==&events && s==&session);
    assert(rpi5_gem_ring_batch_access_allowed(s,RPI5_GEM_STAGE_BARRIER,0,0));
    events++;assert(events==41 && events==s->callbacks);return finish();
}
'''+source[b:]
    source=source.replace('events=currents=target=mode=revoke=corrupt=0;','events=currents=target=mode=revoke=corrupt=partial=0;')
    source=source.replace('current,write32,read32,barrier','current,write64,read64,barrier')
    source=source.replace('io.read32','io.read64').replace('io.write32','io.write64')
    source=source.replace('1281','81').replace('2564','164')
    source=source.replace('pos<=640','pos<=40').replace('pos=642','pos=42')
    source=source.replace('session.writes_attempted==pos && session.writes_completed==pos-1',
        'session.writes_attempted==pos*16 && session.writes_completed==(pos-1)*16')
    source=source.replace('session.writes_attempted==1 && session.writes_completed==0',
        'session.writes_attempted==16 && session.writes_completed==0')
    source=source.replace('rpi5_gem_ring_stage_access_allowed(&session,RPI5_GEM_STAGE_WRITE,0,0,0)',
        'rpi5_gem_ring_batch_access_allowed(&session,RPI5_GEM_STAGE_WRITE,0,0)')
    a=source.index('    const unsigned event_edges[]=');b=source.index(';',a)
    source=source[:a]+'    const unsigned event_edges[]={1,2,15,16,17,19,20,21,36,39,40,41,42,60,79,80,81}'+source[b:]
    a=source.index('    const unsigned current_edges[]=');b=source.index(';',a)
    source=source[:a]+'    const unsigned current_edges[]={1,2,3,4,5,32,33,40,41,42,80,81,82,83,84,120,121,160,161,162,163,164}'+source[b:]
    source=source.replace('    /* Actual partial side-effect', '''    for(unsigned pos=1;pos<=40;pos++)for(unsigned n=1;n<=16;n++){
        init();target=pos;partial=n;failed();
        assert(session.writes_attempted==pos*16 && session.writes_completed==(pos-1)*16);event_cases++;
    }
    /* Actual partial side-effect''')
    return source.replace('GEM_RING_STAGE_PASS','GEM_RING_BATCH_PASS')
class GEMRingBatchTests(unittest.TestCase):
    def test_actual_sanitized_batch_faults_and_all_descriptor_values(self):
        with tempfile.TemporaryDirectory(prefix='ring-batch-') as d:
            folder=Path(d);source=folder/'host.c';source.write_text(host());exe=folder/'host'
            subprocess.run(['xcrun','clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                '-I',str(CORE.parent),source,CORE,'-o',exe],check=True,capture_output=True,timeout=60)
            p=subprocess.run([exe],capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stderr);self.assertIn('GEM_RING_BATCH_PASS',p.stdout);print(p.stdout,end='')
    def test_target_a76_and_exact_shared_span_encoding(self):
        old=(CORE.parent/'rpi5_gem_ring_stage.c').read_text();new=CORE.read_text()
        self.assertEqual(old[old.index('static int same('):old.index('int rpi5_gem_ring_stage_access_allowed')],
            new[new.index('static int same('):new.index('int rpi5_gem_ring_batch_access_allowed')])
        with tempfile.TemporaryDirectory(prefix='ring-batch-a76-') as d:
            obj=Path(d)/'batch.o'
            subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76','-mgeneral-regs-only',
                '-ffreestanding','-fno-builtin','-O2','-Wall','-Wextra','-Werror','-c',CORE,'-o',obj],check=True,capture_output=True,timeout=60)
            self.assertEqual(subprocess.check_output(['xcrun','llvm-nm','--undefined-only',obj],text=True),'')
            self.assertNotIn('volatile',new)
if __name__=='__main__':unittest.main()
