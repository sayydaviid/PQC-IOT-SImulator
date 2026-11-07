"""One client process per workload; only the number of TLS connections varies."""
import argparse,hashlib,importlib.util,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('_amort_endpoint',Path(__file__).with_name('probe.py'))
endpoint=importlib.util.module_from_spec(spec);sys.modules[spec.name]=endpoint;spec.loader.exec_module(endpoint)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--config',type=Path,required=True);args=ap.parse_args()
 conf=json.loads(args.config.read_text());private=Path(conf['private']);directory=Path(conf['directory'])
 cred=Path(conf['credentials']);items=conf['items'];mode=conf['mode']
 ns=argparse.Namespace(credentials=str(cred),profile=conf['profile'],ticket_key=None)
 ctx=endpoint.context(ns,False);store=endpoint.SealedStore(private/'state',(cred/'wrapping.key').read_bytes())
 ca_hash=hashlib.sha256((cred/'ca.crt').read_bytes()).hexdigest()
 ns.host=conf['host'];ns.port=39911;ns.bind_host=conf['bind_host'];ns.mode=mode
 rows=[];next_reading=0;attempts={};unconfirmed=[];restarted=False
 while next_reading<len(items):
  if conf['recovery'] and next_reading==50 and not restarted:
   (private/'restart_request').write_text('restart')
   deadline=time.monotonic()+30
   while not (private/'restart_done').exists():
    if time.monotonic()>deadline:raise RuntimeError('gateway restart not acknowledged')
    time.sleep(.005)
   restarted=True
  end=min(len(items),next_reading+conf['batch_size'])
  if conf['recovery'] and not restarted:end=min(end,50)
  indices=list(range(next_reading,end));batch_file=private/'batch.json'
  batch_file.write_text(json.dumps(items[next_reading:end]));os.environ['CONTEXT_BATCH_FILE']=str(batch_file)
  saved=b'';fallback=False
  if mode=='resume' and (store.directory/'state').exists():
   try:
    state=store.read('state')
    if state['hostname']!='gateway.local' or state['ca_sha256']!=ca_hash:raise ValueError('trust context mismatch')
    saved=endpoint.unb64(state['der'])
   except ValueError:fallback=True
  ns.output=str(directory/f'client_{len(rows)}.json')
  try:endpoint.batch_client(ns,ctx,store,ca_hash,saved,fallback)
  except SystemExit as e:
   if e.code!=2:raise
  row=json.loads(Path(ns.output).read_text());row['requested_readings']=indices;row['gateway_epoch']=int(restarted)
  if [r['reading_id'] for r in row['confirmed']]!=[items[i]['reading_id'] for i in indices[:len(row['confirmed'])]]:
   raise RuntimeError('noncontiguous confirmations')
  next_reading+=len(row['confirmed'])
  if not row['acknowledged']:
   attempts[next_reading]=attempts.get(next_reading,0)+1
   if attempts[next_reading]>=3:unconfirmed.append(next_reading);next_reading+=1
  rows.append(row)
  with (directory/'client_progress.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
 result={'clients':rows,'unconfirmed_readings':unconfirmed,'pid':os.getpid()}
 (directory/'client_workload.json').write_text(json.dumps(result,indent=2))
if __name__=='__main__':main()
