# SPDX-License-Identifier: BSD-2-Clause
"""Package/staging/serial admission tests; never hardware acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import check_apple_network_package as package
from tools.rpi5 import stage_apple_network_trial as stage
from tools.rpi5 import serial_apple_network_trial as serial
from tools.rpi5 import audit_apple_network_trial as audit
from tools.rpi5 import serial_apple_network_followup as followup
from tools.rpi5 import audit_apple_network_followup as followup_audit

BOOT = 'deadbeef-0000-0000-0000-000000000001'
CANDIDATE = stage.ROOT/'build/rpi5/bl33-probe-i3d1ah4e'


class ApplePackageTests(unittest.TestCase):
    def test_actual_image_and_recovery_preservation(self):
        report = package.inspect(CANDIDATE)
        self.assertTrue(report['preflight_pass'])
        self.assertEqual(report['image_sha256'],stage.NEW_SHA)
        self.assertEqual(report['image_bytes'],serial.IMAGE_BYTES)
        self.assertEqual(report['root_mount_marker'].encode(),serial.ROOT_MARKER)
        for field in ('pi_executed','networking','durability','sd_actions','serial_actions','reboots'):
            self.assertFalse(report[field],field)
        with self.assertRaises(ValueError): package.inspect(package.ACCEPTED)
        with patch.object(package,'INIT_SHA','0'*64),self.assertRaises(ValueError): package.inspect(CANDIDATE)


class AppleStageTests(unittest.TestCase):
    def plan(self):
        with patch.object(stage.package_check,'inspect',return_value=dict(
                image='/candidate',image_sha256=stage.NEW_SHA,image_bytes=serial.IMAGE_BYTES)):
            return stage.load_plan(CANDIDATE,BOOT)

    def test_full_baseline_chain_and_fixed_remote_template(self):
        plan = self.plan()
        self.assertEqual(len(plan['nvme_backups']),36)
        self.assertEqual(plan['old_image_sha256'],stage.OLD_SHA)
        self.assertEqual(plan['protected_sha256']['boot'],stage.FAT_SHA)
        self.assertEqual(plan['nvme_backups'][-1]['sha256'],stage.previous.OLD_SHA)
        self.assertIn('probe.statprobe-diagnosed-20261012.bin',plan['protected_files'])
        source = stage.remote_source(plan); compile(source,'<remote>','exec')
        self.assertEqual(stage.remote_template().count(repr(stage.PREVIOUS_NAME)),3)
        self.assertIn(",'apple-network-trial')",source)
        self.assertNotIn("prefix='xnu-gate6-metadata-'",stage.PREPARE)

    def test_pinned_history_same_boot_and_drift_refused(self):
        boot = json.loads((stage.HISTORY/'result.json').read_text())['identity']['boot_id']
        for value in ('','../bad',boot):
            with self.assertRaises(ValueError): stage.load_plan(CANDIDATE,value)
        with patch.object(stage,'HISTORY_SHA',{'result.json':'0'*64}),self.assertRaises(ValueError):
            stage.load_plan(CANDIDATE,BOOT)
        plan = self.plan(); plan['source_sha256'][str(Path(stage.__file__))] = '0'*64
        with self.assertRaises(ValueError): stage.remote_source(plan)

    def test_complete_result_and_individual_protection_failures(self):
        plan = self.plan(); plan['run'] = '/home/sandrzej/xnu-gate6-apple-net-abcdefgh'
        result = json.loads((stage.HISTORY/'result.json').read_text())
        backup = stage.base.install_core.INSTALL_NAMES[stage.PROFILE][0]
        result.update(run=plan['run'],image_sha256=stage.NEW_SHA,
                      preserved_sd_image_sha256=stage.OLD_SHA,nvme_previous_image_sha256=stage.OLD_SHA,
                      sd_backup=backup,nvme_backups_verified=plan['nvme_backups'],
                      identity=dict(identity=plan['identity_binding']['expected'],boot_id=BOOT,hostname='kamidana'),
                      protected_files_sha256=dict(plan['protected_files'],**{'probe.bin':stage.NEW_SHA,backup:stage.OLD_SHA}))
        result['backups'][1]['sha256'] = stage.FAT_SHA
        result['protected_after']['boot']['sha256'] = 'b'*64
        stage.validate_result(result,plan)
        for name in result:
            changed = copy.deepcopy(result); del changed[name]
            with self.subTest(missing=name),self.assertRaises(ValueError): stage.validate_result(changed,plan)
        for key in ('mbr','hfs'):
            changed = copy.deepcopy(result); changed['protected_after'][key]['sha256'] = '0'*64
            with self.assertRaises(ValueError): stage.validate_result(changed,plan)


class AppleSerialTests(unittest.TestCase):
    def boot(self):
        t = serial.t
        return b'\n'.join((b'Boot mode: SD (01)',b'Read probe.bin bytes 19334848 hnd 1',
                           t.ENTRY,t.TERMINAL_LOADER,serial.COPY,serial.KERNEL,
                           t.package_check.TOPOLOGY_PASS,t.TRANSFER,serial.COMMIT,
                           serial.ROOT_MARKER,t.READY,b'xnu:/# '))

    def test_strict_exact_fresh_boot_no_copy_or_mount_waivers(self):
        raw = self.boot(); self.assertTrue(serial.boot_ready(raw))
        for marker in (serial.COPY,serial.KERNEL,serial.COMMIT,serial.ROOT_MARKER):
            for bad in (raw.replace(marker,b'wrong'),raw+marker):
                with self.subTest(marker=marker):
                    try: self.assertFalse(serial.boot_ready(bad))
                    except RuntimeError: pass
        for bad in (raw+serial.t.ENTRY,raw+b'panic(cpu',raw.replace(b'19334848',b'18908864')):
            with self.assertRaises(RuntimeError): serial.boot_ready(bad)

    def test_interface_parser_checks_real_output_and_status(self):
        self.assertEqual(serial.interfaces(b'lo0 \r\nNET_IFCONFIG_STATUS:0\r\nxnu:/# '),['lo0'])
        for bad in (b'echo lo0\nNET_IFCONFIG_STATUS:0\n',b'lo0\nNET_IFCONFIG_STATUS:1\n',
                    b'lo0\nlo0\nNET_IFCONFIG_STATUS:0\n',b'en0\nNET_IFCONFIG_STATUS:0\n'):
            with self.assertRaises(ValueError): serial.interfaces(bad)

    def test_bounded_command_sequence_preserves_recovery(self):
        state = dict(checks=[],transmitted_bytes=0)
        def exchange(fd,output,text,expected,prompt,progress):
            if text == serial.IFCONFIG: return b'lo0\nNET_IFCONFIG_STATUS:0\nxnu:/# '
            return b'\n'.join(expected)+b'\nxnu:/# '
        with patch.object(serial.t.shell,'receive',return_value=self.boot()), \
             patch.object(serial.t,'exchange',side_effect=exchange) as calls:
            serial.trial(1,None,30,state)
        self.assertEqual(state['checks'],serial.CHECKS)
        commands = [call.args[2] for call in calls.call_args_list]
        self.assertEqual(commands[3:5],[serial.IFCONFIG,serial.ROUTE])
        self.assertNotIn('get ',serial.ROUTE); self.assertNotIn('add ',serial.ROUTE)
        self.assertEqual(commands[-1],'echo RECOVERED_'+state['nonce'])


class AppleReplayTests(unittest.TestCase):
    def fixture(self):
        nonce = 'N0123456789abcdef'
        report = dict(image_sha256=stage.NEW_SHA,image_bytes=serial.IMAGE_BYTES,
                      init_sha256=package.INIT_SHA,kernel_sha256=package.metadata.KERNEL_SHA,
                      root_mount_marker=serial.ROOT_MARKER.decode(),preflight_pass=True,
                      checks={'synthetic':True})
        installed = {'directory':'/synthetic','plan_sha256':'a'*64,'result_sha256':'b'*64}
        raw = AppleSerialTests().boot()
        outputs = [[nonce.encode()],serial.t.SMOKE_LINES,[b'0'],[b'lo0',b'NET_IFCONFIG_STATUS:0'],
                   [serial.USAGE,b'NET_ROUTE_STATUS:64'],[('RECOVERED_'+nonce).encode()]]
        for command,lines in zip(audit.commands(nonce),outputs):
            raw += command.encode()+b'\n'+b'\n'.join(lines)+b'\nxnu:/# '
        state = dict(status='passed',checks=serial.CHECKS.copy(),baud=115200,
                     device='/dev/cu.usbmodem102',preflight=report,installation=installed,
                     bytes=len(raw),serial_sha256=hashlib.sha256(raw).hexdigest(),nonce=nonce,
                     started_utc='2026-10-12T19:00:00+00:00',ended_utc='2026-10-12T19:02:00+00:00',
                     transmitted_bytes=sum(len(c)+1 for c in audit.commands(nonce)),interface_names=['lo0'],
                     networking=False,nic_ready=False,ssh=False,durability=False)
        return state,raw,report,installed

    def test_raw_replay_not_summary_claims(self):
        result = audit.replay(*self.fixture())
        self.assertTrue(result['original_ifconfig_names_exit_zero'])
        self.assertTrue(result['original_route_socket_usage_exit_64'])
        self.assertFalse(result['nic_ready'])

    def test_changed_state_and_actual_output_or_commands_reject(self):
        state,raw,report,installed = self.fixture()
        for key,value in (('networking',True),('ssh',True),('interface_names',['en0']),
                          ('transmitted_bytes',0),('checks',[]),('serial_sha256','0'*64),
                          ('error','hidden failure'),('preflight',{}),('installation',{})):
            changed = copy.deepcopy(state); changed[key] = value
            with self.subTest(key=key),self.assertRaises(ValueError): audit.replay(changed,raw,report,installed)
        for old,new in ((b'NET_ROUTE_STATUS:64',b'NET_ROUTE_STATUS:0'),(b'lo0\n',b'en0\n'),
                        (serial.IFCONFIG.encode(),b'/sbin/ifconfig en0 up'),
                        (serial.COPY,b'torn copy'),(b'NET_IFCONFIG_STATUS:0',b'NET_IFCONFIG_STATUS:0\nNET_IFCONFIG_STATUS:0')):
            changed = raw.replace(old,new); updated = dict(state,bytes=len(changed),
                    serial_sha256=hashlib.sha256(changed).hexdigest())
            with self.subTest(old=old),self.assertRaises((ValueError,RuntimeError)):
                audit.replay(updated,changed,report,installed)


class AppleFollowupTests(unittest.TestCase):
    def test_only_missing_mount_with_exact_single_loader_copy_boot(self):
        raw = AppleSerialTests().boot().replace(serial.ROOT_MARKER,b'torn mount line')
        self.assertTrue(followup.payload_boot(raw))
        for value in (AppleSerialTests().boot(),raw+serial.t.ENTRY,
                      raw.replace(serial.COPY,b'missing'),raw+b'panic(cpu',
                      raw+serial.ROOT_MARKER.replace(b'NODES=27',b'NODES=25')+b'\n'):
            with self.assertRaises((ValueError,RuntimeError)): followup.payload_boot(value)

    def test_saved_zero_tx_source_receipt_and_digest_required(self):
        directory = stage.ROOT/'build/rpi5/mac-apple-network-trial-20261012'
        if not (directory/'state.json').exists(): self.skipTest('Physical zero-TX capture absent')
        state = json.loads((directory/'state.json').read_text())
        report = package.inspect(CANDIDATE)
        installed = serial.installation(Path(state['installation']['directory']),report)
        result = followup.evidence(directory,state['device'],report,installed,require_recent=False)
        self.assertFalse(result['strict_mounted_root_trial_passed'])
        self.assertFalse(result['mounted_root_node_count_observed'])
        with tempfile.TemporaryDirectory() as name:
            copydir = Path(name); raw = (directory/'serial.bin').read_bytes()
            (copydir/'serial.bin').write_bytes(raw)
            for key,value in (('transmitted_bytes',1),('checks',['made-up']),('preflight',{}),
                              ('installation',{}),('serial_sha256','0'*64),('status','passed')):
                changed = dict(state,**{key:value})
                (copydir/'state.json').write_text(json.dumps(changed))
                with self.subTest(key=key),self.assertRaises(ValueError):
                    followup.evidence(copydir,state['device'],report,installed,require_recent=False)


class ApplePhysicalReplayTests(unittest.TestCase):
    def saved(self):
        directory = stage.ROOT/'build/rpi5/mac-apple-network-followup-20261012'
        if not (directory/'validation.json').exists(): self.skipTest('Physical diagnostic capture absent')
        pins = {'serial.bin':'a26d7bb78c13af1b58eb4a3048a1f05018ac628f560a3994933957e1c2d7209a',
                'state.json':'a8eab6c2d818e6643925dcce74536ef1ab351a28069daa83b64e13e9c90cfe01',
                'validation.json':'c67de6d90d8ba8212f639e1b35caa4ca4dc29d2dc55e028c40969020ce43a422'}
        for name,pin in pins.items(): self.assertEqual(hashlib.sha256((directory/name).read_bytes()).hexdigest(),pin)
        return directory

    def test_saved_physical_diagnosis_replays_without_strict_mount_or_nic_claim(self):
        directory = self.saved(); result = followup_audit.audit(directory)
        self.assertEqual(result,json.loads((directory/'validation.json').read_text()))
        self.assertEqual(result['interface_names'],['lo0'])
        for field in ('original_zsh_script_passed','original_ifconfig_names_exit_zero',
                      'original_route_socket_usage_exit_64','recovery_verified'):
            self.assertTrue(result[field],field)
        for field in ('strict_mounted_root_trial_passed','mounted_root_node_count_observed',
                      'networking','nic_ready','ssh','durability'):
            self.assertFalse(result[field],field)

    def test_saved_diagnostic_replay_rejects_claim_and_output_mutations(self):
        directory = self.saved(); state = json.loads((directory/'state.json').read_text())
        raw = (directory/'serial.bin').read_bytes()
        source_state = json.loads((Path(state['source']['directory'])/'state.json').read_text())
        args = [state,raw,state['preflight'],state['installation'],state['source'],source_state]
        for key,value in (('strict_mounted_root_trial_passed',True),('nic_ready',True),
                          ('transmitted_bytes',0),('source',{}),('interface_names',['en0']),
                          ('status','passed'),('checks',[])):
            changed = dict(state,**{key:value})
            with self.subTest(key=key),self.assertRaises(ValueError): followup_audit.replay(changed,*args[1:])
        for old,new in ((b'lo0',b'en0'),(b'NET_ROUTE_STATUS:64',b'NET_ROUTE_STATUS:0'),
                        (serial.ROUTE.encode(),b'/sbin/route add default 1.2.3.4'),
                        (b'NET_IFCONFIG_STATUS:0',b'NET_IFCONFIG_STATUS:0\nNET_IFCONFIG_STATUS:0')):
            changed = raw.replace(old,new); updated = dict(state,bytes=len(changed),
                    serial_sha256=hashlib.sha256(changed).hexdigest())
            with self.subTest(old=old),self.assertRaises(ValueError):
                followup_audit.replay(updated,changed,*args[2:])


if __name__ == '__main__': unittest.main()
