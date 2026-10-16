# SPDX-License-Identifier: BSD-2-Clause
"""Actual C parser/resolver/handoff/codec/hash; hardware remains unqualified."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from tools.rpi5 import reservation_record_loader_profile as profile
from tools.rpi5.tests.test_pcie_fdt import _cells, _node, _encode_fdt, PINNED, PINNED_SHA256
sys.path.insert(0,str(Path(__file__).resolve().parent))
from tools.rpi5.tests.test_handoff import image
ROOT=profile.ROOT
def fixture(missing=False):
    # Current captured geometry expressed as synthetic FDT, not a current raw
    # capture: actual same-boot authority exists only in future loader execution.
    root=_node('',{'#address-cells':_cells(2),'#size-cells':_cells(2)},
        _node('memory@0',{'device_type':b'memory\0','reg':_cells(0,0,0,0x3f400000,0,0x40000000,0,0xc0000000,1,0,1,0)}),
        _node('chosen',{'rng-seed':bytes(64)}))
    if not missing:root['children'].append(_node('reserved-memory',{'#address-cells':_cells(2),'#size-cells':_cells(2),'ranges':b''},
        _node('linux,cma',{'size':_cells(0,0x4000000),'alignment':_cells(0,1),'alloc-ranges':_cells(0,0,0,0x40000000),'reusable':b''})))
    return _encode_fdt(root)
CORES=('reservation_record','reservation_record_tree','fdt','ranges','reservations','tree_handoff','board_tree',
    'cpu_tree','serial_tree','seed_tree','boot_seed','apple_dt','handoff','macho','bootstrap','boot_args','memory_type','hash','firmware_seed_fdt','display_xnu_handoff')
BEAR=ROOT/'build/rpi5/bearssl-candidate'
def sources():return [ROOT/'loader/rpi5'/(p+'.c') for p in CORES]+[BEAR/'src'/p for p in ('hash/sha2small.c','codec/dec32be.c','codec/enc32be.c')]
class ReservationRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.work=Path(cls.temp.name)
        cls.seed=cls.work/'firmware_seed_tree.c';cls.seed.write_text(profile.seed((ROOT/'build/rpi5/display-xnu-console-5cd94fg_/firmware_seed_tree.c').read_text()))
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_native_actual_planner_codec_atomicity_seed_order_and_omission(self):
        self.assertEqual(hashlib.sha256(PINNED.read_bytes()).hexdigest(),PINNED_SHA256)
        binary=self.work/'native'
        derived=profile.loader((ROOT/'build/rpi5/display-xnu-console-5cd94fg_/probe_main.c').read_text())
        fragment=derived.split('    tree.chosen.properties=display_tree.properties;',1)[1].split('    handoff=display_handoff;',1)[0]
        fragment='    tree.chosen.properties=display_tree.properties;'+fragment
        # Bind the actual generated prefix commit body to native pointer
        # parameters only. The real unchanged display helper is linked below.
        fragment=fragment.replace('tree.chosen','tree->chosen').replace('display_tree.properties','display_tree->properties').replace('reservation_tree.properties','reservation_tree->properties')
        fragment=fragment.replace('&tree,','tree,').replace('&display_record,','record,').replace('&display_tree)','display_tree)')
        prefix=self.work/'prefix.c';prefix.write_text('#include "reservation_record_tree.h"\n#include "display_xnu_handoff.h"\nint actual_display_prefix(struct rpi5_board_tree *tree,struct rpi5_display_xnu_tree *display_tree,struct rpi5_reservation_record_tree *reservation_tree,const struct rpi5_display_xnu_record *record) {\n'+fragment+'return 1;\n}\n')
        command=['xcrun','clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
            '-DRPI5_FIRMWARE_FDT_HANDOFF=1','-I'+str(ROOT/'loader/rpi5'),'-I'+str(BEAR/'inc'),'-I'+str(BEAR/'src'),
            str(ROOT/'tools/rpi5/tests/reservation_record_host.c'),str(self.seed),str(prefix),*map(str,sources()),'-o',str(binary)]
        r=subprocess.run(command,capture_output=True,text=True,timeout=60);self.assertEqual(r.returncode,0,r.stderr)
        paths=[]
        for name,data in [('geometry.dtb',fixture()),('kernel',image()),('missing.dtb',fixture(True))]:
            p=self.work/name;p.write_bytes(data);paths.append(p)
        r=subprocess.run([binary,*paths,PINNED],capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr);self.assertIn('REAL_PLANNER_CODEC_SHA SEED_ERASE_BEFORE_DIGEST',r.stdout)
    def test_exact_overlays_fail_closed_and_preserve_original_owners(self):
        original=(ROOT/'build/rpi5/display-xnu-console-5cd94fg_/probe_main.c').read_text();new=profile.loader(original)
        self.assertIn('reservation_pending=2;',new)
        self.assertLess(new.index('rpi5_reservation_record_tree_reserve(&tree'),new.index('/* Geometry first;'))
        self.assertLess(new.index('tree.chosen.property_count=5;',new.index('/* Commit the unchanged')),new.index('int display_commit='))
        self.assertLess(new.index('tree.chosen.property_count=6;',new.index('int display_commit=')),new.index('reservation_pending=1;'))
        seed=self.seed.read_text();self.assertLess(seed.index('int status=consume('),seed.index('rpi5_reservation_record_finalize(tree)'))
        self.assertLess(seed.index('rpi5_reservation_record_finalize(tree)'),seed.index('status=rpi5_adt_encode('))
        self.assertEqual(new.count('rpi5_resolved_tree_handoff('),original.count('rpi5_resolved_tree_handoff('))
        for mutate in (original.replace('#include "display_xnu_handoff.h"',''),new):
            with self.assertRaises(ValueError):profile.loader(mutate)
        with self.assertRaises(ValueError):profile.seed(seed)
    def test_real_a76_codec_and_loader_helpers_no_imports(self):
        objects=[]
        for i,source in enumerate(sources()):
            obj=self.work/(str(i)+'.o');objects.append(obj)
            r=subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align','-mgeneral-regs-only',
                '-ffreestanding','-fno-builtin','-fno-stack-protector','-fstack-usage','-O2','-Wall','-Wextra','-Werror',
                '-I'+str(ROOT/'loader/rpi5'),'-I'+str(ROOT/'loader/rpi5/freestanding'),'-I'+str(BEAR/'inc'),'-I'+str(BEAR/'src'),'-c',source,'-o',obj],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
        memory=self.work/'memory.o';objects.append(memory)
        subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-c',ROOT/'loader/rpi5/memory.S','-o',memory],check=True,capture_output=True,timeout=30)
        elf=self.work/'NOT_RUN.elf'
        r=subprocess.run([ROOT/'tools/rpi5/tfa-lld','--no-undefined','-e','rpi5_reservation_record_make',*objects,'-o',elf],capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(subprocess.check_output(['xcrun','llvm-nm','--undefined-only',elf],text=True),'')
    def test_real_whole_loader_overlay_and_seed_a76_stack_bound(self):
        parent=ROOT/'build/rpi5/display-xnu-console-5cd94fg_';m=json.loads((parent/'manifest.json').read_text())
        fresh=self.work/'probe_main.c';fresh.write_text(profile.loader((parent/'probe_main.c').read_text()))
        for original,derived in ((parent/'probe_main.c',fresh),(parent/'firmware_seed_tree.c',self.seed)):
            rows=[x for x in m['commands'] if '-c' in x['command'] and str(original) in x['command']]
            self.assertEqual(len(rows),1);row=rows[0];command=list(row['command'])
            command[command.index(str(original))]=str(derived)
            command[command.index('-o')+1]=str(self.work/(derived.stem+'.o'))
            command[command.index('-MF')+1]=str(self.work/(derived.stem+'.d'))
            r=subprocess.run(command,cwd=row['cwd'],capture_output=True,text=True,timeout=60)
            self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stderr,'')
        # Sum every frame from all potentially called codec/FDT/resolver/hash
        # units, even mutually exclusive leaves. This is a nonrecursive path;
        # ADT encoding happens only AFTER finalization returns. Original seed
        # assembly uses its separate isolated stack before the callback starts.
        wanted=profile.STACK_UNITS
        frames=[]
        for i,source in enumerate(sources()):
            if source.stem not in wanted:continue
            su=self.work/(str(i)+'.su')
            if not su.exists():
                # This group is independently runnable without relying on test order.
                obj=self.work/(str(i)+'.o')
                subprocess.run(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align','-mgeneral-regs-only',
                    '-ffreestanding','-fno-builtin','-fno-stack-protector','-fstack-usage','-O2','-Wall','-Wextra','-Werror',
                    '-I'+str(ROOT/'loader/rpi5'),'-I'+str(ROOT/'loader/rpi5/freestanding'),'-I'+str(BEAR/'inc'),'-I'+str(BEAR/'src'),'-c',source,'-o',obj],check=True,capture_output=True,timeout=30)
            for line in su.read_text().splitlines():
                location,size,kind=line.rsplit('\t',2);self.assertEqual(kind,'static');frames.append((location,int(size)))
        caller={}
        for name in ('probe_main','firmware_seed_tree'):
            for line in (self.work/(name+'.su')).read_text().splitlines():
                location,size,kind=line.rsplit('\t',2);self.assertEqual(kind,'static');caller[location.rsplit(':',1)[-1]]=int(size)
        receipt=profile.stack_budget({source.stem:self.work/(str(i)+'.su') for i,source in enumerate(sources()) if source.stem in wanted},
            self.work/'probe_main.su',self.work/'firmware_seed_tree.su')
        total=receipt['conservative_bytes']
        with self.assertRaises(ValueError):profile.stack_budget({},self.work/'probe_main.su',self.work/'firmware_seed_tree.su')
        self.assertLess(total+512,32768)
        print('RESERVATION_A76_STACK conservative_bytes='+str(total)+' stack_bytes=32768 margin='+str(32768-total))
if __name__=='__main__':unittest.main()
