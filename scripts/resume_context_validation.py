"""Resume an infrastructure-interrupted run, replacing its whole final block."""
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'results/raw'
OLD = RAW / 'context_chain_registered_20261106_v1'
REPEAT = RAW / 'context_chain_repeated_block9_20261107_v1'
MERGED = RAW / 'context_chain_completed_20261107_v1'
AMORT = RAW / 'context_amortization_registered_20261106_v1'


def run(*args):
    subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, check=True)


def main():
    manifest = json.loads((OLD / 'manifest.json').read_text())
    for filename, digest in manifest['source_sha256'].items():
        assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() == digest, filename
    existing = [json.loads(p.read_text()) for p in OLD.glob('*/case.json')]
    assert Counter(c['block'] for c in existing) == Counter({**dict.fromkeys(range(9), 54), 9: 51})
    # The incomplete block is retained in OLD and excluded in its entirety.
    run('scripts/run_context_costs.py', '--blocks', '1', '--block-start', '9', '--output', REPEAT)
    repeated_manifest = json.loads((REPEAT / 'manifest.json').read_text())
    assert repeated_manifest['source_sha256'] == manifest['source_sha256']
    repeated = json.loads((REPEAT / 'results.json').read_text())
    assert repeated['status'] == 'PASS' and len(repeated['cases']) == 54
    MERGED.mkdir(exist_ok=False)
    cases = [c for c in existing if c['block'] < 9] + repeated['cases']
    assert len(cases) == 540
    for c in cases:
        source = OLD if c['block'] < 9 else REPEAT
        (MERGED / c['case_id']).symlink_to(os.path.relpath(source / c['case_id'], MERGED))
    for block in range(10):
        source = OLD if block < 9 else REPEAT
        for stem in ['certificates', 'network']:
            name = f'{stem}_block{block}.json'
            (MERGED / name).symlink_to(os.path.relpath(source / name, MERGED))
    manifest['completed_utc'] = datetime.now(timezone.utc).isoformat()
    manifest['infrastructure_interruption'] = {
        'original': str(OLD.relative_to(ROOT)),
        'original_completed_cases': len(existing),
        'excluded_whole_block': 9,
        'excluded_completed_cases': 51,
        'replacement': str(REPEAT.relative_to(ROOT)),
        'reason': 'Runtime processes terminated before the matrix finished; all 54 cells of block 9 repeated.',
        'merger_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'replacement_manifest_sha256': hashlib.sha256((REPEAT / 'manifest.json').read_bytes()).hexdigest(),
    }
    (MERGED / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    (MERGED / 'results.json').write_text(json.dumps({'status': 'PASS', 'cases': cases}, indent=2))
    print('Completed chains: 9 original complete blocks and 1 whole repeated block.', flush=True)
    run('scripts/run_context_amortization.py', '--blocks', '10', '--output', AMORT)
    run('scripts/finalize_context_validation.py', '--chains', MERGED, '--amortization', AMORT,
        '--output', ROOT / 'docs/resultados_contexto_20261106',
        '--report', ROOT / 'docs/resultado_contexto_20261106.md')


if __name__ == '__main__':
    main()
