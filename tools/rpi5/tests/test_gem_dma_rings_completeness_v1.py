# SPDX-License-Identifier: BSD-2-Clause
"""Byte-only recipe tests; fixtures are not linked kernel/package admission."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from tools.rpi5 import gem_dma_rings_completeness_v1 as h
from tools.rpi5 import build_gem_dma_rings_package as b
ROOT=b.ROOT
PROTOTYPE=ROOT/'build/rpi5/gem-dma-rings-20261014-v2'
class GEMDMARingsCompletenessTests(unittest.TestCase):
    def test_actual_prototype_all69_vectors24scans_and_omission_flag_link_cwd_negatives(self):
        self.assertEqual(h.sha(PROTOTYPE/'manifest.json'),'01f55192a03dd5e0292d41f75b96aa861e40829b4e3ebf92871dc2aaba72eb82')
        m=json.loads((PROTOTYPE/'manifest.json').read_bytes())
        with patch('subprocess.run',side_effect=AssertionError('Compiler forbidden')):
            scans=h.command_bindings(PROTOTYPE,m)
            self.assertEqual(len(scans),24);self.assertEqual(len(m['commands']),69)
            for mode in ('omit-scan-label','omit-command','flag','link','cwd','duplicate','bool-return','unknown-profile'):
                bad=copy.deepcopy(m)
                if mode=='omit-scan-label':
                    bad['compiler_scans'].pop('kernel-reservation_record')
                elif mode=='omit-command':bad['commands']=[r for r in bad['commands'] if not r['log'].endswith('/kernel-reservation_record-compile.log')]
                elif mode=='flag':
                    row=next(r for r in bad['commands'] if r['log'].endswith('/dma-rings-compile.log'));row['command'].append('-DUNREVIEWED_OWNER=1')
                elif mode=='link':
                    row=next(r for r in bad['commands'] if r['log'].endswith('/loader-link.log'));row['command'].remove(str(PROTOTYPE/'loader-reservation_record.o'))
                elif mode=='cwd':bad['commands'][0]['cwd']=str(ROOT)
                elif mode=='duplicate':bad['commands'].append(copy.deepcopy(bad['commands'][0]))
                elif mode=='bool-return':bad['commands'][0]['returncode']=False
                else:bad['profile']='bcm2712-real-batch-owner-v99'
                with self.assertRaises(ValueError,msg=mode):h.command_bindings(PROTOTYPE,bad)
    def test_actual_prototype_complete_dependency_union_and_missing_input_negatives(self):
        m=json.loads((PROTOTYPE/'manifest.json').read_bytes())
        # V2 is an explicitly rejected OLD snapshot-provider prototype. Test
        # only its real command/dependency receipts here; canonical sources
        # have their own real pure-derivation tests and must reject that old TU.
        with patch('subprocess.run',side_effect=AssertionError('Compiler forbidden')), \
             patch.object(h,'canonical_sources',return_value=None) as sources:
            r=h.inspect(PROTOTYPE,m);self.assertEqual(r['canonical_compile_labels'],24)
            self.assertFalse(r['compiler_replayed']);self.assertFalse(r['hardware_admission']);sources.assert_called_once()
            for key in ('actual_headers_sha256','inputs_sha256'):
                bad=copy.deepcopy(m);path=next(iter(m['actual_headers_sha256']));bad[key].pop(path)
                with self.assertRaises(ValueError,msg=key):h.inspect(PROTOTYPE,bad)
    def test_canonical_private_provider_and_owner_sources_no_io_derivation(self):
        with tempfile.TemporaryDirectory(prefix='gem-dma-rings-completeness-source-',dir=ROOT/'build/rpi5') as d:
            folder=Path(d);(folder/'overlay').mkdir()
            for name,data in h.recipe.derive().items():(folder/'overlay'/name).write_bytes(data)
            for name,transform in [('arm_init',b.boot.arm),('probe_main',b.record.loader),('firmware_seed_tree',b.record.seed)]:
                (folder/(name+'.c')).write_text(transform((b.BASE/(name+'.c')).read_text()))
            pins={str(p):h.sha(p) for p in [*b.sources(),Path(h.__file__).resolve(),Path(h.recipe.__file__).resolve(),Path(__file__).resolve()]}
            with patch('subprocess.run',side_effect=AssertionError('Compiler forbidden')):
                h.canonical_sources(folder,pins)
                for name in h.recipe.derive():
                    p=folder/'overlay'/name;original=p.read_bytes();p.write_bytes(original+b'\n')
                    with self.assertRaises(ValueError,msg=name):h.canonical_sources(folder,pins)
                    p.write_bytes(original)
                missing=dict(pins);missing.pop(str(ROOT/'tools/rpi5/tests/gem_dma_memory_host.cpp'))
                with self.assertRaises(ValueError):h.canonical_sources(folder,missing)
                p=folder/'probe_main.c';original=p.read_bytes();p.write_bytes(original.replace(b'\n',b'\r\n'))
                with self.assertRaises(ValueError):h.canonical_sources(folder,pins)
                p.write_bytes(original+b'\n')
                with self.assertRaises(ValueError):h.canonical_sources(folder,pins)
    def test_canonical_payload_rejects_reserved_padding_offsets_root_and_assembly(self):
        # Tiny inert kernel bytes exercise ONLY encoding identity. They never
        # pass the outer Mach-O/ELF checker and are not a fake runnable image.
        with tempfile.TemporaryDirectory(prefix='gem-dma-rings-completeness-payload-',dir=ROOT/'build/rpi5') as d:
            folder=Path(d);kernel=b'INERT_RECIPE_FIXTURE_NOT_MACHO';(folder/'kernel.owned-rings').write_bytes(kernel)
            raw=(b.BASE/'payload.bin').read_bytes();off,n=struct.unpack_from('<QQ',raw,136);root=raw[off:off+n]
            packed=b.payload_container.encode(kernel,root);p=folder/'payload.bin';p.write_bytes(packed)
            assembly='.section .payload,"a"\n.balign 64\n.incbin "'+str(p)+'"\n';s=folder/'payload.S';s.write_text(assembly)
            with patch('subprocess.run',side_effect=AssertionError('Compiler forbidden')):
                h.canonical_payload(folder)
                for offset in (28,72,80,len(packed)-1):
                    bad=bytearray(packed);bad[offset]^=1;p.write_bytes(bad)
                    with self.assertRaises(ValueError,msg=str(offset)):h.canonical_payload(folder)
                p.write_bytes(packed+b'\0')
                with self.assertRaises(ValueError):h.canonical_payload(folder)
                p.write_bytes(packed);s.write_text(assembly+'\n')
                with self.assertRaises(ValueError):h.canonical_payload(folder)
                s.write_bytes(assembly.replace('\n','\r\n').encode())
                with self.assertRaises(ValueError):h.canonical_payload(folder)
if __name__=='__main__':unittest.main()
