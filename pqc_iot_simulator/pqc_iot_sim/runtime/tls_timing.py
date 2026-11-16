"""Separate checkpoint persistence from TLS time in the 100-reading workload."""

from datetime import datetime, timezone
import json
from pathlib import Path
import random
import statistics
import tempfile

from ..metadata import RunMetadata
from ..crypto.tls.credentials import provision
from .tls_amortization import execute
from .tls_chains import topology
from .tls_continuity import environment


class StorageTimingEngine:
    """A performance control, not a durability claim for tmpfs."""

    def __init__(self, *, output, network=None, source='iot_1', destination='server_1', blocks=3):
        self.output=Path(output)
        self.network,self.source,self.destination=network,source,destination
        if isinstance(blocks,bool) or not isinstance(blocks,int) or blocks<1:
            raise ValueError('blocos devem ser inteiros positivos')
        self.blocks=blocks

    def run(self):
        self.output.mkdir(parents=True,exist_ok=False)
        initial=RunMetadata.source_hashes()
        manifest=dict(started_utc=datetime.now(timezone.utc).isoformat(),blocks=self.blocks,
            readings=100,batch_size=1,payload_bytes=512,source_sha256=initial,environment=environment(),
            source=self.source,destination=self.destination,
            storage={'disk':'/tmp','memory':'/dev/shm'},
            scope='performance diagnostic only; tmpfs is not persistent across host power loss; not mixed into offer cost estimates')
        (self.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        rows=[]
        with tempfile.TemporaryDirectory(prefix='timing-credentials-') as cred_root:
            for block in range(self.blocks):
                cred=Path(cred_root)/str(block);provision(cred,'pqc',self.source)
                engine=None
                try:
                    engine,sta,dst,cip,sip,interface,qdiscs=topology(network=self.network,source=self.source,destination=self.destination)
                    jobs=[(storage,treatment) for storage in ('disk','memory') for treatment in ('full','resume_preserved')]
                    random.Random(20261116+block).shuffle(jobs)
                    for storage,treatment in jobs:
                        case_id=f'b{block}_{storage}_{treatment}'
                        with tempfile.TemporaryDirectory(prefix='timing-private-',dir=manifest['storage'][storage]) as tmp:
                            row=execute(sta,dst,cip,sip,interface,self.output/case_id,Path(tmp)/'work',
                                cred,'pqc',treatment,1,False,block,device_id=self.source)
                        if row['confirmed_readings']!=100 or len(row['clients'])!=100:
                            raise RuntimeError('carga temporal incompleta')
                        fulls=sum(not c['reused'] for c in row['clients'])
                        if fulls!=(100 if treatment=='full' else 1):
                            raise RuntimeError('handshakes do controle temporal inconsistentes')
                        previous=row['clients'][:-1]
                        row.update(case_id=case_id,storage=storage,
                            checkpoint_writes=sum(c['checkpoint_writes'] for c in row['clients']),
                            checkpoint_ms_in_sequence=sum(c['checkpoint_write_ms'] for c in previous),
                            handshake_cpu_ms=sum(c['handshake_cpu_ms'] for c in row['clients']),
                            handshake_wall_ms=sum(c['handshake_ms'] for c in row['clients']))
                        (self.output/case_id/'case.json').write_text(json.dumps(row,indent=2)+'\n')
                        rows.append(row)
                        print(json.dumps(dict(completed=len(rows),planned=self.blocks*4,case=case_id)),flush=True)
                finally:
                    if engine is not None:engine.stop()
        if initial!=RunMetadata.source_hashes():raise RuntimeError('fontes alteradas durante controle temporal')
        (self.output/'results.json').write_text(json.dumps(dict(status='PASS',cases=rows),indent=2)+'\n')
        summary=[]
        for storage in ('disk','memory'):
            pairs=[]
            for block in range(self.blocks):
                full=next(r for r in rows if r['block']==block and r['storage']==storage and r['treatment']=='full')
                resumed=next(r for r in rows if r['block']==block and r['storage']==storage and r['treatment']=='resume_preserved')
                pairs.append(dict(block=block,
                    sequence_delta_ms_per_reading=(resumed['sequence_ms']-full['sequence_ms'])/100,
                    checkpoint_delta_ms_per_reading=(resumed['checkpoint_ms_in_sequence']-full['checkpoint_ms_in_sequence'])/100,
                    handshake_cpu_delta_ms_per_reading=(resumed['handshake_cpu_ms']-full['handshake_cpu_ms'])/100,
                    full_checkpoint_writes=full['checkpoint_writes'],resumed_checkpoint_writes=resumed['checkpoint_writes']))
            summary.append(dict(storage=storage,blocks=self.blocks,
                mean_sequence_delta_ms_per_reading=statistics.mean(r['sequence_delta_ms_per_reading'] for r in pairs),
                mean_checkpoint_delta_ms_per_reading=statistics.mean(r['checkpoint_delta_ms_per_reading'] for r in pairs),
                mean_handshake_cpu_delta_ms_per_reading=statistics.mean(r['handshake_cpu_delta_ms_per_reading'] for r in pairs),pairs=pairs))
        (self.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        return self.output
