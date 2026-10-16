# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic exact-wire protocol tests, no serial input or hardware reads."""
import copy
import unittest
from tools.rpi5 import pcie_link_elapsed_serial_core as p


class LinkElapsedSerialTests(unittest.TestCase):
    def fixture(self):
        report=dict(image_bytes=18122328,boot_markers=[
            'RPI5XNU:BL33:PCIE_ID_LINK_ELAPSED_TRIAL TAG=fixture'],
            trace_contract=dict(end_format=p.package_source.TRACE_END,extra_mmio=False,
                changed_permissions=False,changed_deadlines=False),
            link_elapsed=dict(reset_min_us=100000,reset_max_us=110000,poll_max_us=100000,
                delay_max_chunk_us=1000,delay_max_chunks=100,delay_accounts_guard_time=True,
                prior_c1_axi_objects_unchanged=True,firmware_guards_unchanged=True,watchdogs_unchanged=True,
                additional_mappings=False,endpoint_writes=False,dma_enabled=False,
                physical_cause_proven=False,physical_correction_verified=False))
        end=(b'RPI5XNU:PCIEID:END OK=1 PHASE=5 LAST=5 LIFE=3 FLAGS=1f ID=00011de4 COMMAND=0000 '
            b'BAR1=00000000 GEN=2 LANES=4 UBUS_STEP=5 UBUS_RC=0 UBUS_CB=23 GUARD=0 BANK=0 '
            b'OFFSET=00004068 DIR=0 IO_STAGE=4 VALUE=000000b0 LINK_CALL=5 LINK_STEP=14 LINK_RC=0 '
            b'LINK_CB=41 RESET_START_US=1000000 RESET_END_US=1100000 RESET_US=100000 POLL_READS=1 POLL_US=0')
        lines=[b'Boot mode: SD (01)',b'Read probe.bin bytes 18122328 hnd 0',p.ENTRY,
            report['boot_markers'][0].encode(),p.TRANSFER,p.COMMIT,p.BEGIN,p.PREPARED,end,
            b'RPi: BOOTSYS release VERSION: fixture',b'BOOT_ORDER override: 0x000000f6',
            b'RPi: BOOTLOADER release VERSION: fixture',b'Boot mode: NVME (06)']
        return b'\r\n'.join(lines)+b'\r\n',report

    def test_complete_link_is_not_ethernet_or_independent_recovery(self):
        data,report=self.fixture();r=p.inspect(data,report)
        self.assertTrue(r['rp1_id_trial_pass']);self.assertEqual(r['telemetry']['reset_us'],100000)
        for key in ('ethernet_proven','irq_delivery','dma','independent_linux_return_proven','full_production_lifecycle_proven'):
            self.assertFalse(r[key])
        for old,new in ((b'LINK_CALL=5',b'LINK_CALL=4'),(b'LINK_STEP=14',b'LINK_STEP=13'),
            (b'LINK_RC=0',b'LINK_RC=-8'),(b'LINK_CB=41',b'LINK_CB=42'),(b'RESET_US=100000',b'RESET_US=110001'),
            (b'RESET_END_US=1100000',b'RESET_END_US=1100001'),(b'POLL_US=0',b'POLL_US=100001'),
            (b'ID=00011de4',b'ID=00000000'),(b'CPUS=1',b'CPUS=2')):
            with self.subTest(old=old),self.assertRaises(ValueError):p.inspect(data.replace(old,new),report)

    def test_failed_reset_timeout_is_valid_diagnostic_not_success(self):
        data,report=self.fixture()
        data=data.replace(b'OK=1 PHASE=5 LAST=5',b'OK=0 PHASE=6 LAST=12')
        data=data.replace(b'ID=00011de4',b'ID=00000000').replace(b'LINK_CALL=5 LINK_STEP=14 LINK_RC=0',b'LINK_CALL=3 LINK_STEP=6 LINK_RC=-8')
        data=data.replace(b'LINK_CB=41',b'LINK_CB=29').replace(b'RESET_END_US=1100000',b'RESET_END_US=1128000')
        data=data.replace(b'RESET_US=100000',b'RESET_US=128000').replace(b'POLL_READS=1',b'POLL_READS=0')
        result=p.inspect(data,report)
        self.assertTrue(result['trace_capture_valid']);self.assertFalse(result['rp1_id_trial_pass'])
        self.assertEqual(result['diagnostic_outcome'],'failed');self.assertEqual(result['telemetry']['link_rc'],-8)
        for old,new in ((b'LINK_CALL=3',b'LINK_CALL=6'),(b'LINK_STEP=6',b'LINK_STEP=15'),
            (b'LINK_RC=-8',b'LINK_RC=-11'),(b'LINK_CB=29',b'LINK_CB=122'),(b'POLL_READS=0',b'POLL_READS=22'),
            (b'RESET_US=128000',b'RESET_US=18446744073709551616')):
            with self.subTest(old=old),self.assertRaises(ValueError):p.inspect(data.replace(old,new),report)
        # Failure telemetry does not invent a monotonic-clock success contract.
        backward=data.replace(b'RESET_END_US=1128000',b'RESET_END_US=999999').replace(b'RESET_US=128000',b'RESET_US=0')
        self.assertFalse(p.inspect(backward,report)['rp1_id_trial_pass'])

    def test_truncated_duplicate_reordered_wrong_generation_or_return_refused(self):
        data,report=self.fixture()
        bad=(data.replace(b'POLL_US=0',b''),data+p.BEGIN+b'\n',
            data.replace(b'PCIE_ID_LINK_ELAPSED_TRIAL',b'PCIE_ID_AXI_TRACE_TRIAL'),
            data.replace(b'18122328',b'18122327'),data.replace(b'Boot mode: NVME (06)',b'Boot mode: SD (01)'),
            data.replace(p.BEGIN,b'TEMP').replace(p.PREPARED,p.BEGIN).replace(b'TEMP',p.PREPARED),
            data.replace(p.BEGIN,b'panic(cpu 0)\n'+p.BEGIN))
        for item in bad:
            with self.assertRaises(ValueError):p.inspect(item,report)
        for key,value in (('reset_max_us',120000),('delay_max_chunks',101),('watchdogs_unchanged',False),('physical_cause_proven',True)):
            altered=copy.deepcopy(report);altered['link_elapsed'][key]=value
            with self.assertRaises(ValueError):p.inspect(data,altered)


if __name__=='__main__':unittest.main()
