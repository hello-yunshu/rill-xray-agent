import json,os,socket,tempfile,threading,time,unittest
from pathlib import Path
from rill_xray_agent.canonical import canonical_bytes
from rill_xray_agent.runtime_service import RuntimeService
class Tests(unittest.TestCase):
 def request_when_ready(self,sock,payload,timeout=5):
  deadline=time.monotonic()+timeout;last=None
  while time.monotonic()<deadline:
   try:
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
     s.settimeout(.5);s.connect(str(sock));s.sendall(canonical_bytes(payload)+b'\n');data=s.recv(65536)
     if data:return json.loads(data)
   except (FileNotFoundError,ConnectionRefusedError,socket.timeout,OSError,json.JSONDecodeError) as exc:
    last=exc;time.sleep(.02)
  raise AssertionError(f'Runtime did not become ready: {last!r}')
 def test_runtime_ipc(self):
  with tempfile.TemporaryDirectory() as td:
   r=Path(td);sock=r/'r.sock';svc=RuntimeService(r/'state',r/'tx',allowed_uids=[os.getuid()]);t=threading.Thread(target=svc.serve,args=(sock,),daemon=True);t.start()
   out=self.request_when_ready(sock,{'schemaVersion':3,'requestId':'x','capability':'route','method':'health','body':{}})
   self.assertTrue(out['ok']);self.assertEqual(out['result']['status'],'ready');svc.stop();t.join(timeout=3);self.assertFalse(t.is_alive());self.assertFalse(sock.exists())
 def test_reset_forbidden(self):
  with tempfile.TemporaryDirectory() as td:self.assertFalse(RuntimeService(Path(td)/'s',Path(td)/'t').handle({'schemaVersion':3,'requestId':'x','capability':'route','method':'reset','body':{}})['ok'])
 def test_rillml_status_fail_closed_when_tree_absent(self):
  with tempfile.TemporaryDirectory() as td:
   r=Path(td);svc=RuntimeService(r/'state',r/'tx',rillml_root=r/'rillml',allowed_uids=[os.getuid()])
   out=svc.handle({'schemaVersion':3,'requestId':'x','capability':'route','method':'rillmlStatus','body':{}})
   self.assertTrue(out['ok']);res=out['result']
   self.assertEqual(res['nativeRuntime']['status'],'unavailable')
   self.assertFalse(res['nativeRuntime']['verified'])
   self.assertEqual(res['fallback'],'portable-python')
 def test_rillml_status_never_mutates_tree(self):
  with tempfile.TemporaryDirectory() as td:
   r=Path(td);svc=RuntimeService(r/'state',r/'tx',rillml_root=r/'rillml',allowed_uids=[os.getuid()])
   out=svc.handle({'schemaVersion':3,'requestId':'x','capability':'route','method':'rillmlStatus','body':{}})
   self.assertTrue(out['ok']);self.assertFalse((r/'rillml').exists())

