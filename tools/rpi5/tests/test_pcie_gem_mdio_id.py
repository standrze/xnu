# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.rpi5 import build_pcie_gem_mdio_id_kernel as b
from tools.rpi5.tests import test_rp1_gem_mdio as original


class GEMMDIOIDTests(unittest.TestCase):
    def test_actual_core_all_eight_mostly_f_ids_and_adjacent_valid_ids(self):
        with tempfile.TemporaryDirectory(prefix='mdio-id-v2-') as name:
            folder=Path(name);overlay=folder/'overlay';b.profile.emit(overlay)
            old=(b.ROOT/'loader/rpi5/rp1_gem_mdio.c').read_text()
            self.assertEqual((overlay/'rp1_gem_mdio.c').read_text(),b.profile.refined(old))
            text=Path(original.__file__).with_name('rp1_gem_mdio_host.c').read_text()
            test=r'''
    for(unsigned upper=0;upper<8;upper++){
        uint32_t id=(upper<<29)|0x1fffffffu;
        setup(&m);m.reply[0]=id>>16;m.reply[1]=id&0xffff;failed(&m);
        assert(m.ncr==0&&m.ncfgr==0&&m.commands_count==5&&m.s.error==-6);
        setup(&m);id--;m.reply[0]=id>>16;m.reply[1]=id&0xffff;
        assert(!run(&m)&&m.out.phy_id==id&&m.ncr==0&&m.ncfgr==0);
    }
    printf("MDIO_ID_REFINEMENT_PASS REJECTED=8 ADJACENT_VALID=8 NO_ACCESS_CHANGE=1\n");
'''
            text=b.profile.core.util.once(text,'    struct model m;setup(&m);assert(!run(&m));','    struct model m;'+test+'\nsetup(&m);assert(!run(&m));')
            src=folder/'host.c';src.write_text(text);exe=folder/'host'
            flags=['-std=c11','-Wall','-Wextra','-Werror','-I',str(overlay),'-I',str(b.ROOT/'loader/rpi5')]
            r=subprocess.run(['xcrun','clang',*flags,'-fsanitize=address,undefined',str(src),
                str(overlay/'rp1_gem_mdio.c'),str(overlay/'rp1_gem_identify.c'),'-o',str(exe)],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run([exe],capture_output=True,text=True,timeout=30);self.assertEqual(r.returncode,0,r.stderr)
            self.assertIn('REJECTED=8 ADJACENT_VALID=8',r.stdout);print(r.stdout,end='')
            r=subprocess.run(['xcrun','clang',*flags,'--target=aarch64-none-elf','-mcpu=cortex-a76',
                '-mstrict-align','-mgeneral-regs-only','-ffreestanding','-fno-builtin','-fno-stack-protector',
                '-O2','-c',str(overlay/'rp1_gem_mdio.c'),'-o',str(folder/'core.o')],capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)

    def test_actual_full_owner_and_adapter_faults_with_refined_core(self):
        t=b.private.load_private(Path(original.__file__).resolve(),'_mdio_id_full_native')
        previous=t.source
        def source(folder,main,mutation=None):
            text=previous(folder,main,mutation)
            path=folder/'rp1_gem_mdio.c';path.write_text(b.profile.refined(path.read_text()))
            return text
        t.source=source
        for name in ('test_actual_full_owner_phy_roundtrip_and_worst_poll_budget',
            'test_actual_adapter_failures_preserve_global_owner_and_quarantine'):
            t.GEMMDIOTests(name).debug()

    def test_primary_id_rule_and_linked_delta_when_present(self):
        refs=b.contract()['primary_sources']['sources'];row=next(v for v in refs if v['path'].endswith('/phy_device.c'))
        path=b.ROOT/row['path'];self.assertEqual(b.audit.sha(path),row['sha256'])
        self.assertIn('if ((*phy_id & 0x1fffffff) == 0x1fffffff)',path.read_text())
        folder=b.ROOT/'build/rpi5/pcie-gem-mdio-kernel-20261014-v2'
        if not (folder/'manifest.json').exists():return
        m=json.loads((folder/'manifest.json').read_text());b.engine.verify(m['inputs_sha256']|m['generated_sha256'])
        self.assertEqual(m['mdio_contract'],b.contract());self.assertEqual(m['profile'],b.PROFILE)
        self.assertEqual(len(m['compiles']),2);self.assertEqual(len(m['mdio_object_replacements']),1)
        self.assertEqual(m['kernel_sha256'],b.audit.sha(folder/'kernel.rp1-config'))
        self.assertEqual(m['logging_calls'],53);self.assertTrue(m['owner_client_core_secure_objects_unchanged'])


if __name__=='__main__':unittest.main()
