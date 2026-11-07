"""Matched 100-reading workloads with 1/10/100 readings per TLS connection."""
from __future__ import annotations
import argparse, hashlib, itertools, json, os, random, signal, subprocess, sys, tempfile, time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_context_costs import topology,certificate_sizes,PROBE
from scripts.continuity_design import PROFILES,TREATMENTS,check_tls
from scripts.continuity_credentials import provision
from scripts.tls_capture import tls_capture
from scripts.continuity_capture import covered_attempt
from scripts.run_continuity_campaign import environment
SOURCES=['docs/metodo_amortizacao_20261106.md','experiments/context_costs/amortization_client.py','scripts/run_context_amortization.py','scripts/run_context_costs.py','experiments/context_costs/probe.py',
 'experiments/context_costs/native.c','scripts/continuity_credentials.py','scripts/continuity_design.py',
 'pqc_iot_simulator/pqc_iot_sim/components/reading_ledger.py','pqc_iot_simulator/pqc_iot_sim/components/recovery.py',
 'scripts/tls_capture.py','scripts/continuity_capture.py']
def hashes():return {f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in SOURCES}

def execute(sta,dst,cip,sip,interface,directory,private,cred,profile,treatment,batch,recovery,block):
 directory.mkdir();private.mkdir(mode=0o700);state=private/'state';db=private/'db';ticket=private/'ticket.key'
 ticket.write_bytes(os.urandom(80));ticket.chmod(0o600)
 env=dict(os.environ,CONTEXT_CHAIN_ROOT='0');port='39911'
 logs=[];processes=[];clients=[];servers=[];epoch=-1;ticket_epoch=None;last_ack_ns=None
 gateway=None;stop=None;server_output=None;counts=None;total=100;next_reading=0;attempts={};unconfirmed=[]
 ids=[hashlib.sha256(f'amort block={block} reading={i}'.encode()).hexdigest()[:32] for i in range(total)]
 payloads=[]
 for i in range(total):
  # Fixed 512-byte telemetry, identical across all comparators in the block.
  prefix=f'block={block:03};reading={i:03};'.encode();data=(prefix+b'x'*512)[:512]
  path=private/f'payload_{i}';path.write_bytes(data);payloads.append(path)
 drops=[ids[50]] if recovery else []
 capture=dst.popen(['tcpdump','-B','16384','--immediate-mode','-U','-n','-s','0','-i',interface,
  '-w',str(directory/'traffic.pcap'),'tcp','port',port],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
 from pqc_iot_simulator.pqc_iot_sim.engines.mininet_wifi_engine import MininetWiFiEngine
 ok,detail=MininetWiFiEngine._wait_for_tcpdump_ready(capture)
 if not ok:raise RuntimeError(detail)
 def collect():
  nonlocal counts
  stop.write_text('stop')
  if gateway.wait(timeout=20):raise RuntimeError('gateway exit failure')
  row=json.loads(server_output.read_text());servers.extend(row['connections'])
  counts={k:row[k] for k in ['unique_readings','application_effects','duplicate_effects']}
 def start_server():
  nonlocal gateway,stop,server_output,epoch
  epoch+=1;ready=private/f'ready{epoch}';stop=private/f'stop{epoch}';server_output=directory/f'server_{epoch}.json'
  log=(directory/f'server_{epoch}.log').open('w');logs.append(log)
  cmd=[sys.executable,PROBE,'server','--host',sip,'--port',port,'--credentials',str(cred),
   '--profile',profile,'--ledger',str(db),'--ready',str(ready),'--output',str(server_output),
   '--stop-file',str(stop),'--deduplicate','--drop-reading-id',*drops]
  if treatment=='resume_preserved':cmd.extend(['--ticket-key',str(ticket)])
  gateway=dst.popen(cmd,env=dict(env,CONTEXT_BATCH_SERVER='1'),stdout=log,stderr=subprocess.STDOUT);processes.append(gateway)
  deadline=time.monotonic()+15
  while not ready.exists():
   if gateway.poll() is not None or time.monotonic()>deadline:raise RuntimeError('gateway startup failure')
   time.sleep(.005)
 start_ns=time.perf_counter_ns();restarted=False
 try:
  start_server()
  config=private/'client_config.json'
  config.write_text(json.dumps({'private':str(private),'directory':str(directory),'credentials':str(cred),
   'items':[{'reading_id':ids[i],'payload':str(payloads[i])} for i in range(total)],
   'mode':'full' if treatment=='full' else 'resume','host':sip,'bind_host':cip,'profile':profile,
   'recovery':recovery,'batch_size':batch}))
  driver=ROOT/'experiments/context_costs/amortization_client.py'
  client_log=(directory/'client_workload.log').open('w');logs.append(client_log)
  client=sta.popen([sys.executable,str(driver),'--config',str(config)],env=env,stdout=client_log,stderr=subprocess.STDOUT)
  processes.append(client);deadline=time.monotonic()+600
  while client.poll() is None:
   if (private/'restart_request').exists() and not restarted:
    collect();start_server();restarted=True;(private/'restart_done').write_text('ready')
   if time.monotonic()>deadline:raise RuntimeError('workload watchdog; incomplete block retained')
   time.sleep(.005)
  if client.returncode:raise RuntimeError('client workload failed: '+(directory/'client_workload.log').read_text())
  workload=json.loads((directory/'client_workload.json').read_text())
  clients=workload['clients'];unconfirmed=workload['unconfirmed_readings']
  assert len({c['pid'] for c in clients})==1
  active_ticket_epoch=None
  for c in clients:
   ep=c['gateway_epoch'];offered=treatment!='full' and active_ticket_epoch is not None
   if 'version' in c:check_tls(c,profile,offered and (treatment=='resume_preserved' or active_ticket_epoch==ep))
   if bool(c['session_offered'])!=offered:raise RuntimeError('unexpected ticket availability')
   if c['resumable_session_saved']:active_ticket_epoch=ep
  ack_times=[r['ack_monotonic_ns'] for c in clients for r in c['confirmed']]
  if ack_times and not start_ns <= max(ack_times) <= time.perf_counter_ns():raise RuntimeError('client/controller clocks differ')
  sequence_ms=(max(ack_times)-start_ns)/1e6 if ack_times else None
  for field in ('client_share_sha256','server_share_sha256'):
   shares=[c[field] for c in clients if field in c]
   if len(shares)!=len(set(shares)):raise RuntimeError('TLS key share repeated')
  collect()
 finally:
  capture.send_signal(signal.SIGINT);_,capture_log=capture.communicate(timeout=10)
  (directory/'tcpdump.log').write_text(capture_log)
  for p in processes:
   if p.poll() is None:p.kill();p.wait(timeout=5)
  for log in logs:log.close()
 if '0 packets dropped by kernel' not in capture_log:raise RuntimeError('capture drops')
 if cip==sip:
  trace={'local_functional_check_only':True}
 else:
  trace=tls_capture(directory/'traffic.pcap',cip)
  if not all(covered_attempt(trace,c,servers) for c in clients):raise RuntimeError('incomplete byte coverage')
 received=[r for s in servers for r in s['readings']]
 unique=len({r['reading_id'] for r in received})
 assert counts=={'unique_readings':unique,'application_effects':unique,'duplicate_effects':0}
 for c in clients:
  if 'version' in c and not c['reused']:
   assert len(c['wire_cert_tx_der_bytes'])==len(c['wire_cert_rx_der_bytes'])==1
 result={'block':block,'profile':profile,'treatment':treatment,'batch_size':batch,'recovery':recovery,
  'readings':total,'confirmed_readings':total-len(unconfirmed),'unconfirmed_readings':unconfirmed,
  'delivery_status':'complete' if not unconfirmed else 'budget_exhausted','payload_bytes':512,'include_root':0,
  'fault_schedule':{'restart_before':[50] if recovery else [],'drop_first_ack':[50] if recovery else []},
  'sequence_ms':sequence_ms,'clients':clients,'servers':servers,'capture':trace,**counts}
 (directory/'case.json').write_text(json.dumps(result,indent=2));return result

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
 ap.add_argument('--blocks',type=int,default=10);ap.add_argument('--smoke',action='store_true');ap.add_argument('--local-smoke',action='store_true')
 args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=False);before=hashes()
 if hashlib.sha256(Path('/opt/pqc-tls/context_costs/native.c').read_bytes()).hexdigest()!=before['experiments/context_costs/native.c']:raise RuntimeError('native source differs')
 matrix=list(itertools.product(PROFILES,TREATMENTS,(1,10,100),(False,True)))
 if args.local_smoke:matrix=[('pqc','resume_preserved',b,True) for b in (1,10,100)]
 elif args.smoke:matrix=[('pqc',t,b,r) for t in TREATMENTS for b in (1,10,100) for r in (False,True)]
 manifest={'started_utc':datetime.now(timezone.utc).isoformat(),'source_sha256':before,'environment':{**environment(),'context_module_sha256':hashlib.sha256(Path(__import__('_context_tls').__file__).read_bytes()).hexdigest()},
  'blocks':args.blocks,'planned_cases':len(matrix)*args.blocks,'logical_readings_per_case':100,'payload_bytes':512,
  'same_workload':'all treatments one client process, 100 logical readings; connection cap 1/10/100; no extra warm-up',
  'recovery':'restart before reading index 50, suppress its first ACK after commit; can split a persistent connection',
  'chain':'leaf only sent in both directions; CA root still trusted','packet_loss_pct':0,'deduplicate':True,
  'bootstrap_unit':'matched block','smoke':args.smoke or args.local_smoke}
 (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2));rows=[]
 with tempfile.TemporaryDirectory(prefix='amort-private-') as tmp:
  private=Path(tmp)
  for block in range(args.blocks):
   creds={}
   for profile in PROFILES:creds[profile]=private/f'b{block}_{profile}';provision(creds[profile],profile)
   (args.output/f'certificates_block{block}.json').write_text(json.dumps({p:certificate_sizes(d) for p,d in creds.items()},indent=2))
   if args.local_smoke:
    from scripts.run_continuity_campaign import LocalNode
    engine=None;sta=dst=LocalNode();cip=sip='127.0.0.1';interface='lo';qdiscs=[]
   else:engine,sta,dst,cip,sip,interface,qdiscs=topology()
   try:
    (args.output/f'network_block{block}.json').write_text(json.dumps(qdiscs))
    order=matrix[:];random.Random(20261107+block).shuffle(order)
    for profile,treatment,batch,recovery in order:
     cid=f'b{block}_{profile}_{treatment}_n{batch}_recovery{int(recovery)}'
     row=execute(sta,dst,cip,sip,interface,args.output/cid,private/cid,creds[profile],profile,treatment,batch,recovery,block)
     row['case_id']=cid;(args.output/cid/'case.json').write_text(json.dumps(row,indent=2));rows.append(row)
     with (args.output/'progress.jsonl').open('a') as f:f.write(json.dumps({'completed':len(rows),'case':cid})+'\n')
     print(json.dumps({'completed':len(rows),'planned':manifest['planned_cases'],'case':cid}),flush=True)
   finally:
    if engine:engine.stop()
 if before!=hashes():raise RuntimeError('source changed')
 (args.output/'results.json').write_text(json.dumps({'status':'PASS','cases':rows},indent=2))
 print(json.dumps({'status':'PASS','cases':len(rows)}))
if __name__=='__main__':main()
