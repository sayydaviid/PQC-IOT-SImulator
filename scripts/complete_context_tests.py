"""Run repository tests on the host after the measurement-image audits pass."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis',type=Path,required=True)
    args=parser.parse_args()
    final=args.analysis/'verificacao_final.json'
    previous=json.loads(final.read_text())
    for filename,digest in previous['analysis_sources_sha256'].items():
        assert hashlib.sha256((ROOT/filename).read_bytes()).hexdigest()==digest,filename
    for name in ['audit.json','auditoria_chains.json','auditoria_amortization.json']:
        assert json.loads((args.analysis/name).read_text())['status']=='PASS',name
    assert json.loads((ROOT/'results/raw/context_persistence_tls_20261106_v1/results.json').read_text())['status']=='PASS'
    analysis=json.loads((args.analysis/'audit.json').read_text())
    for filename,digest in analysis['inputs'].items():
        path=ROOT/Path(filename).relative_to('/workspace') if filename.startswith('/workspace/') else Path(filename)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,filename
    old_log=args.analysis/'testes.txt'
    archived=args.analysis/'testes_container.txt'
    if old_log.exists() and not archived.exists():
        archived.write_bytes(old_log.read_bytes())
    result=subprocess.run([sys.executable,'-m','pytest','-q'],cwd=ROOT,capture_output=True,text=True)
    old_log.write_text(result.stdout+result.stderr)
    summary=next((line for line in reversed(result.stdout.splitlines()) if line.strip()),'')
    previous.update(status='PASS' if result.returncode==0 else 'TEST_FAILURE',
        pytest_returncode=result.returncode,pytest_summary=summary,pytest_environment='host',
        measurement_container_test_attempt={'returncode':1,'reason':'pytest not installed in measurement image',
            'log':'testes_container.txt'})
    for name in ['scripts/complete_context_tests.py','tests/test_context_capture.py','scripts/continuity_ticket_sizes.py']:
        previous['analysis_sources_sha256'][name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    final.write_text(json.dumps(previous,indent=2))
    print(result.stdout+result.stderr)
    print(json.dumps({k:v for k,v in previous.items() if k!='analysis_sources_sha256'},indent=2))
    raise SystemExit(result.returncode)


if __name__=='__main__':main()
