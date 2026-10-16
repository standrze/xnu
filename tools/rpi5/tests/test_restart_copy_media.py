# SPDX-License-Identifier: BSD-2-Clause
"""Execute the unchanged actual config/loader publisher with device doubles."""
import types
import unittest
from tools.rpi5 import display_restart_copy_media_v1 as engine
from tools.rpi5.tests import test_display_xnu_media_v1 as old

_scope=dict(vars(old),engine=engine,TRIAL=old.ROOT/'build/rpi5/display-restart-copy-sgf9_m1d/probe.bin')
class RestartCopyMediaTests(unittest.TestCase):
    pass
for _name,_fn in vars(old.DisplayAllocateMediaTests).items():
    if not callable(_fn) or _name.startswith('__'):continue
    if _name in ('test_compact_temporary_names_are_distinct_and_rollback_alias_unchanged',
                 'test_generated_exact_remote_program_executes_with_only_explicit_device_doubles'):continue
    if hasattr(_fn,'__wrapped__'):
        _bound=types.FunctionType(_fn.__wrapped__.__code__,_scope,argdefs=_fn.__wrapped__.__defaults__)
        _bound=old.contextlib.contextmanager(_bound)
    else:_bound=types.FunctionType(_fn.__code__,_scope,argdefs=_fn.__defaults__)
    setattr(RestartCopyMediaTests,_name,_bound)
def names(self):
    core=engine.bound_core(old.TAG)
    self.assertEqual(core.NAMES[engine.TRIAL]['probe.bin'][0],engine.original.REUSED_ZSH_BACKUP)
    for profile in (engine.TRIAL,engine.RESTORE):
        for row in core.NAMES[profile].values():self.assertIn('displayrestartcopy-',row[1])
RestartCopyMediaTests.test_new_archive_names_same_working_alias=names
def remote(self):
    with self.fixture() as row:
        code=engine.remote_source(row[8],row[9],row[0],row[1])
        boundary=code.rindex('print(json.dumps(display_restart_copy_media_v1.execute(PLAN,')
        namespace={};modules=dict(old.sys.modules)
        with old.patch.dict(old.sys.modules,modules),old.contextlib.redirect_stdout(old.io.StringIO()) as out:
            exec(compile(code[:boundary],'<actual-sealed-remote-prefix>','exec'),namespace)
            namespace.update(capture=row[2],helper=old.prior.helper,snapshots=row[3],reference=old.prior.reference,
                guarded=types.SimpleNamespace(**{**vars(old.prior.core),'command':row[4]}))
            exec(compile(code[boundary:],'<actual-sealed-remote-call>','exec'),namespace)
        result=old.json.loads(out.getvalue())
        self.assertEqual(result['publication']['pair_publication_order'],['config.txt','probe.bin'])
        self.assertEqual((row[6]/'config.txt').read_bytes(),engine.TRIAL_CONFIG)
        self.assertFalse(row[5]['mounted'])
RestartCopyMediaTests.test_generated_actual_remote_body=remote
if __name__=='__main__':unittest.main()
