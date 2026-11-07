"""Actual SQLite/file interruption checks. Process death is not power loss."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, signal, sqlite3, subprocess, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def component(name,file):
 spec=importlib.util.spec_from_file_location(name,ROOT/'pqc_iot_simulator/pqc_iot_sim/components'/file)
 mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod

class ControlledStop(BaseException):pass

def ledger_worker(directory,boundary,mode):
 mod=component('_persistence_ledger','reading_ledger.py')
 ledger=mod.ReadingLedger(directory/'db')
 real=ledger.connection
 def barrier():
  (directory/'ready').write_text(boundary)
  if mode=='normal':raise ControlledStop()
  while True:time.sleep(.01)
 class Proxy:
  def execute(self,sql,*args):
   if boundary=='before_commit' and sql=='COMMIT':barrier()
   result=real.execute(sql,*args)
   if ((boundary=='after_reading_insert' and sql.startswith('INSERT INTO readings'))
      or (boundary=='after_effect_insert' and sql.startswith('INSERT INTO effects'))
      or (boundary=='after_commit' and sql=='COMMIT')):barrier()
   return result
  def close(self):real.close()
 ledger.connection=Proxy()
 try:
  ledger.ingest('iot_1','sample-1',b'fixed reading payload')
  if boundary=='before_ack':barrier()
 except ControlledStop:pass
 finally:ledger.close()
 (directory/'normal_exit.json').write_text(json.dumps({'closed_normally':True,'ack_sent':False}))

def checkpoint_worker(directory,count):
 mod=component('_persistence_checkpoint','recovery.py')
 store=mod.SealedStore(directory/'state',(directory/'key').read_bytes())
 previous=store.read('state') if (directory/'state/state').exists() else {'round':0}
 samples=[]
 for i in range(count):
  store.write('state',{'round':previous['round']+i+1})
  raw=(directory/'state/state').read_bytes()
  samples.append(hashlib.sha256(raw[:12]).hexdigest())
 print(json.dumps({'nonce_digests':samples,'loaded_round':previous['round']}))

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path)
 ap.add_argument('--worker',choices=['ledger','checkpoint']);ap.add_argument('--directory',type=Path)
 ap.add_argument('--boundary');ap.add_argument('--mode');ap.add_argument('--count',type=int,default=50);ap.add_argument('--repetitions',type=int,default=10)
 args=ap.parse_args()
 if args.worker=='ledger':return ledger_worker(args.directory,args.boundary,args.mode)
 if args.worker=='checkpoint':return checkpoint_worker(args.directory,args.count)
 args.output.mkdir(parents=True,exist_ok=False)
 checks=[];module=component('_parent_ledger','reading_ledger.py')
 with tempfile.TemporaryDirectory(prefix='persistence-private-') as tmp:
  private=Path(tmp)
  for repetition in range(args.repetitions):
   for boundary in ['after_reading_insert','after_effect_insert','before_commit','after_commit','before_ack']:
    for mode in ['normal','sigkill']:
     directory=private/f'{repetition}_{boundary}_{mode}';directory.mkdir()
     log=directory/'worker.log'
     with log.open('w') as stream:
      process=subprocess.Popen([sys.executable,__file__,'--worker','ledger','--directory',str(directory),
       '--boundary',boundary,'--mode',mode],stdout=stream,stderr=subprocess.STDOUT)
      deadline=time.monotonic()+15
      while not (directory/'ready').exists():
       if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('barrier not reached: '+log.read_text())
       time.sleep(.005)
      if mode=='sigkill':process.kill()
      code=process.wait(timeout=10)
     assert code==(0 if mode=='normal' else -signal.SIGKILL),(mode,code,log.read_text())
     with sqlite3.connect(directory/'db') as db:
      assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
      history=db.execute('SELECT device,id,digest FROM readings').fetchall()
      effects=db.execute('SELECT device,id,digest FROM effects').fetchall()
     committed=boundary in ['after_commit','before_ack']
     assert len(history)==len(effects)==int(committed)
     assert history==effects
     ledger=module.ReadingLedger(directory/'db');retry=ledger.ingest('iot_1','sample-1',b'fixed reading payload')
     assert retry['duplicate']==committed
     assert ledger.counts()=={'unique_readings':1,'application_effects':1,'duplicate_effects':0}
     try:ledger.ingest('iot_1','sample-1',b'conflict')
     except module.ReadingConflict:pass
     else:raise AssertionError('conflicting content accepted')
     ledger.close()
     checks.append({'repetition':repetition,'boundary':boundary,'termination':mode,'exit_code':code,
       'rows_after_restart':len(history),'effects_after_restart':len(effects),'retry_duplicate':retry['duplicate'],
       'effects_after_retry':1,'ack_sent_before_stop':False,'integrity':'ok'})
  cdir=private/'checkpoint';cdir.mkdir();(cdir/'key').write_bytes(os.urandom(32))
  mod=component('_parent_checkpoint','recovery.py');store=mod.SealedStore(cdir/'state',(cdir/'key').read_bytes())
  store.write('state',{'round':0});old=(cdir/'state/state').read_bytes()
  nonces=[];loaded=[]
  for process_index in range(20):
   if process_index%2==0:(cdir/'state/state').write_bytes(old)
   row=json.loads(subprocess.check_output([sys.executable,__file__,'--worker','checkpoint','--directory',str(cdir),'--count','50']))
   nonces.extend(row['nonce_digests']);loaded.append(row['loaded_round'])
  assert len(nonces)==len(set(nonces))
  tampered=bytearray((cdir/'state/state').read_bytes());tampered[-1]^=1;(cdir/'state/state').write_bytes(tampered)
  try:store.read('state')
  except mod.Rejected:pass
  else:raise AssertionError('unauthenticated checkpoint accepted')
  (cdir/'state/state').write_bytes(old);assert store.read('state')['round']==0
  # A repeated RNG output is not detected/prevented by this store: negative control.
  original_urandom=mod.os.urandom
  try:
   mod.os.urandom=lambda n:b'\0'*n
   store.write('state',{'round':1});first=(cdir/'state/state').read_bytes()[:12]
   store.write('state',{'round':2});second=(cdir/'state/state').read_bytes()[:12]
   assert first==second
  finally:mod.os.urandom=original_urandom
 data={'status':'PASS','ledger_checks':checks,'checkpoint':{'processes':20,'encryptions':len(nonces),
  'file_rollback_before_processes':10,'observed_nonce_collisions':len(nonces)-len(set(nonces)),
  'nonce_bytes':12,'source':'os.urandom(12), host OS CSPRNG independent of checkpoint file',
  'birthday_collision_bound':'q*(q-1)/2**97 for q encryptions under the same key, assuming independent uniform nonces',
  'old_authenticated_snapshot_accepted':True,'tampered_snapshot_rejected':True,
  'forced_repeated_rng_nonce_reuse_observed':True,'rng_or_machine_snapshot_rollback_not_protected':True},
  'limits':'Graceful close versus SIGKILL of the process executing the unchanged gateway ledger. No physical power-cut, storage-device flush or external actuator guarantee.',
  'source_sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in ['scripts/verify_context_persistence.py',
    'pqc_iot_simulator/pqc_iot_sim/components/reading_ledger.py','pqc_iot_simulator/pqc_iot_sim/components/recovery.py']}}
 (args.output/'results.json').write_text(json.dumps(data,indent=2));print(json.dumps({'status':'PASS','ledger_checks':len(checks),'checkpoint_encryptions':len(nonces)}))
if __name__=='__main__':main()
