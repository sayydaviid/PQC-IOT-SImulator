"""Audit and summarize completed experiments; never sample partial blocks."""
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--chains',type=Path,required=True)
 ap.add_argument('--amortization',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
 ap.add_argument('--report',type=Path,required=True);ap.add_argument('--wait',action='store_true')
 ap.add_argument('--resume-postprocessing',action='store_true');args=ap.parse_args()
 if args.wait:
  print('Aguardando os dois results.json completos antes de consolidar.',flush=True)
  while not all((p/'results.json').exists() for p in [args.chains,args.amortization]):time.sleep(2)
 def run(*items):subprocess.run([sys.executable,*map(str,items)],cwd=ROOT,check=True)
 if not args.resume_postprocessing:
  run('scripts/verify_context_persistence_tls.py','--output',ROOT/'results/raw/context_persistence_tls_20261106_v1')
  run('scripts/summarize_context_costs.py','--chains',args.chains,'--amortization',args.amortization,'--output',args.output)
 else:
  assert json.loads((ROOT/'results/raw/context_persistence_tls_20261106_v1/results.json').read_text())['status']=='PASS'
  existing=json.loads((args.output/'audit.json').read_text());assert existing['status']=='PASS'
  assert existing['analyzer_sha256']==hashlib.sha256((ROOT/'scripts/summarize_context_costs.py').read_bytes()).hexdigest()
  for path,digest in existing['inputs'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
 for kind,path in [('chains',args.chains),('amortization',args.amortization)]:
  run('scripts/verify_context_results.py','--kind',kind,'--input',path,'--output',args.output/f'auditoria_{kind}.json')
 run('scripts/report_context_costs.py','--analysis',args.output,'--output',args.report)
 check=subprocess.run([sys.executable,'-m','pytest','-q'],cwd=ROOT,capture_output=True,text=True)
 (args.output/'testes.txt').write_text(check.stdout+check.stderr)
 status={'status':'PASS' if check.returncode==0 else 'TEST_FAILURE','pytest_returncode':check.returncode,
  'pytest_summary':check.stdout.splitlines()[-1] if check.stdout.splitlines() else '',
  'analysis_sources_sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in ['scripts/summarize_context_costs.py',
   'scripts/verify_context_results.py','scripts/report_context_costs.py','scripts/finalize_context_validation.py','tests/test_context_costs_analysis.py','scripts/verify_context_persistence_tls.py','scripts/resume_context_validation.py','scripts/context_capture.py']}}
 (args.output/'verificacao_final.json').write_text(json.dumps(status,indent=2))
 # These are requested editable documentation artifacts, not private runtime files.
 uid,gid=ROOT.stat().st_uid,ROOT.stat().st_gid
 for p in [args.output,*args.output.rglob('*'),args.report]:
  try:os.chown(p,uid,gid)
  except PermissionError:pass
 print(json.dumps(status,indent=2),flush=True)
 if check.returncode:raise SystemExit(check.returncode)
if __name__=='__main__':main()
