# SPDX-License-Identifier: BSD-2-Clause
"""Wait identity parser only; no network, serial or SD access."""
import unittest
from tools.rpi5 import wait_nvme_linux as wait


class LinuxWaitTests(unittest.TestCase):
    def test_exact_root_hostname_and_boot_identity(self):
        boot='906666a5-2d99-42e2-80d2-c58328746127'
        report=wait.identity('kamidana\n'+wait.ROOT+'\n'+boot+'\n')
        self.assertEqual(report,dict(hostname='kamidana',root=wait.ROOT,boot_id=boot))

    def test_ssh_success_is_not_permission_for_wrong_or_malformed_root(self):
        good='kamidana\n'+wait.ROOT+'\n906666a5-2d99-42e2-80d2-c58328746127\n'
        for changed in (good.replace('kamidana','other'),good.replace('nvme0n1p2','mmcblk0p2'),
                        good.replace('04570742','04570743'),good+'extra\n',good.replace('906666a5','invalid'),
                        'kamidana\n',good.replace('ext4','hfsplus')):
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                wait.identity(changed)


if __name__=='__main__':
    unittest.main()
