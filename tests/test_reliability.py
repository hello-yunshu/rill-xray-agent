import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from rill_xray_agent.audit import AuditLog,AuditError
from rill_xray_agent.backup import create_backup,restore_backup
from rill_xray_agent.errors import DecisionIdentityConflict
from rill_xray_agent.health import health
from rill_xray_agent.root_txn import RootTransaction
from rill_xray_agent.state import RuntimeState
class Tests(unittest.TestCase):
 def test_audit_recovery(self):
  with tempfile.TemporaryDirectory() as td:
   a=AuditLog(Path(td))
   with patch.dict(os.environ,{'RILL_AUDIT_FAIL_AFTER_EVENT':'1'}):
    with self.assertRaises(AuditError):a.append('fault')
   self.assertEqual(a.reconcile()['events'],1);a.append('next');self.assertEqual(a.verify()['events'],2)
 def test_identity_conflict(self):
  with tempfile.TemporaryDirectory() as td:
   s=RuntimeState(Path(td)/'s.json');s.register('route','x',7,1);self.assertEqual(s.register('route','x',7,1)['status'],'idempotent')
   with self.assertRaises(DecisionIdentityConflict):s.register('route','x',7,2)
 def test_nested_transaction_health(self):
  with tempfile.TemporaryDirectory() as td:
   r=Path(td);w=r/'tx/d';w.mkdir(parents=True);(w/'state.json').write_text('{"state":"applied"}')
   self.assertEqual(health(r/'state',r/'tx')['status'],'recovery-required')
 def test_backup_symlink_no_escape(self):
  with tempfile.TemporaryDirectory() as td:
   r=Path(td);src=r/'src';src.mkdir();(src/'a.json').write_text('{"safe":true}');z=r/'b.zip';create_backup(z,[('runtime',src)]);outside=r/'outside';outside.mkdir();target=r/'target';target.mkdir();(target/'runtime').symlink_to(outside,target_is_directory=True);restore_backup(z,target,force=True);self.assertFalse((target/'runtime').is_symlink());self.assertFalse(any(outside.iterdir()))
 def test_commit_bundle_recovery(self):
  with tempfile.TemporaryDirectory() as td:
   r=Path(td);m=r/'managed';m.write_text('old');g=r/'gen';g.write_text('1\n');tx=RootTransaction(r/'tx',r/'delivery',g);req={'recommendationId':'d','configurationGeneration':1}
   with patch.dict(os.environ,{'RILL_FAIL_AFTER_COMMIT_BUNDLE':'1'}):
    with self.assertRaises(Exception):tx.apply(req,m,lambda:m.write_text('new'),lambda:True)
   self.assertEqual(tx.recover_all(),[tx.work_dir_name('d')]);self.assertEqual(g.read_text().strip(),'2');self.assertTrue((r/'delivery/route-delivery.json').is_file())
 def test_rollback_restores_managed(self):
  with tempfile.TemporaryDirectory() as td:
   r=Path(td);m=r/'managed';m.write_text('old');g=r/'gen';g.write_text('1\n');tx=RootTransaction(r/'tx',r/'delivery',g);req={'recommendationId':'x','configurationGeneration':1}
   out=tx.apply(req,m,lambda:m.write_text('new'),lambda:False)
   self.assertEqual(out['status'],'rolledBack');self.assertEqual(m.read_text(),'old');self.assertEqual(g.read_text().strip(),'1');self.assertEqual(tx.recover_all(),[tx.work_dir_name('x')]);self.assertTrue((r/'delivery/route-delivery.json').is_file())
 def test_invalid_recommendation_id_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   r=Path(td);m=r/'managed';m.write_text('old');g=r/'gen';g.write_text('1\n');tx=RootTransaction(r/'tx',r/'delivery',g)
   for bad in ['../../escape','a/b','x'*129,'','sp ace']:
    with self.assertRaises(Exception):tx.apply({'recommendationId':bad,'configurationGeneration':1},m,lambda:None,lambda:True)
   self.assertFalse((r/'tx').exists() or (Path(r/'tx')/'escape').exists())
