"""Block-level mean costs, break-even probability and held-out offer checks."""

from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
import statistics as st


class OfferMetrics:
    def __init__(self, directory, *, resamples=10000, seed=20261116):
        self.directory = Path(directory)
        self.resamples, self.seed = resamples, seed

    @staticmethod
    def threshold(full, accepted, rejected):
        """q must exceed this value only when rejection is costlier than acceptance."""
        return (rejected - full) / (rejected - accepted) if rejected > accepted else None

    def interval(self, values, statistic=st.mean):
        if len(values) < 2:
            return (None, None)
        rng = random.Random(self.seed)
        bootstrap = sorted(statistic(rng.choices(values, k=len(values))) for _ in range(self.resamples))
        return (bootstrap[int(.025 * self.resamples)], bootstrap[int(.975 * self.resamples)])

    @staticmethod
    def write(path, rows):
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def run(self):
        result = json.loads((self.directory / 'results.json').read_text())
        manifest = json.loads((self.directory / 'manifest.json').read_text())
        cases = result['cases']
        if result['status'] != 'PASS' or len(cases) != manifest['planned_cases']:
            raise ValueError('execução incompleta')
        if len({c['case_id'] for c in cases}) != len(cases):
            raise ValueError('execuções duplicadas')
        rows, calibration, validation = [], defaultdict(dict), defaultdict(list)
        for case in cases:
            capture = self.directory / case['case_id'] / 'traffic.pcap'
            if hashlib.sha256(capture.read_bytes()).hexdigest() != case['capture_sha256']:
                raise ValueError('captura alterada: ' + case['case_id'])
            if case['confirmed_readings'] != case['batch_size'] or case['duplicate_effects']:
                raise ValueError('entrega ou efeito inconsistente')
            client = case['client']
            row = dict(case_id=case['case_id'], block=case['block'], profile=case['profile'],
                batch_size=case['batch_size'], sample=case['sample'], probability=case['probability'],
                outcome=case['outcome'], offered=client['session_offered'], reused=client['reused'],
                ipv4_bytes=case['ipv4_bytes'], ipv4_per_reading=case['ipv4_bytes']/case['batch_size'],
                handshake_ms=client['handshake_ms'], handshake_cpu_ms=client['handshake_cpu_ms'],
                tcp_connect_ms=client['tcp_connect_ms'], tcp_to_ack_ms=client['tcp_to_ack_ms'],
                process_ms=case['process_ms'], startup_ms=case['startup_ms'],
                psk_identity_bytes=case['clienthello']['psk_identity_total_bytes'],
                clienthello_bytes=case['clienthello']['handshake_bytes'] if 'handshake_bytes' in case['clienthello'] else case['clienthello'].get('clienthello_handshake_bytes'),
                retransmissions=client['tcp_retransmitted_segments'])
            rows.append(row)
            key = (case['block'], case['profile'], case['batch_size'])
            if case['sample'] == 'calibration':
                if case['outcome'] in calibration[key]:
                    raise ValueError('calibração duplicada')
                calibration[key][case['outcome']] = row
            else:
                validation[key + (case['probability'],)].append(row)
        expected_groups = manifest['blocks'] * len(manifest['profiles']) * len(manifest['batches'])
        if len(calibration) != expected_groups or any(set(c) != {'full','accepted','rejected'} for c in calibration.values()):
            raise ValueError('faltam comparadores da calibração')
        validation_batches = manifest.get('validation_batches', manifest['batches'])
        if len(validation) != manifest['blocks'] * len(manifest['profiles']) * len(validation_batches) * len(manifest['probabilities']):
            raise ValueError('faltam condições de validação')
        for key, values in validation.items():
            if len(values) != manifest['attempts'] or sum(bool(v['reused']) for v in values) != round(key[-1]*manifest['attempts']):
                raise ValueError('aceitação observada difere da disponibilidade programada')
        summary, estimates, checks = [], [], []
        for profile in manifest['profiles']:
            for batch in manifest['batches']:
                groups = [calibration[(block,profile,batch)] for block in range(manifest['blocks'])]
                for outcome in ('full','accepted','rejected'):
                    values = [g[outcome] for g in groups]
                    summary.append(dict(profile=profile, batch_size=batch, outcome=outcome, blocks=len(groups),
                        mean_ipv4_bytes=st.mean(v['ipv4_bytes'] for v in values),
                        mean_ipv4_per_reading=st.mean(v['ipv4_per_reading'] for v in values),
                        mean_tcp_to_ack_ms=st.mean(v['tcp_to_ack_ms'] for v in values),
                        mean_handshake_ms=st.mean(v['handshake_ms'] for v in values),
                        mean_handshake_cpu_ms=st.mean(v['handshake_cpu_ms'] for v in values),
                        mean_process_ms=st.mean(v['process_ms'] for v in values),
                        mean_psk_identity_bytes=st.mean(v['psk_identity_bytes'] for v in values)))
                def estimate(sample):
                    full, accepted, rejected = (st.mean(g[o]['ipv4_bytes'] for g in sample) for o in ('full','accepted','rejected'))
                    return self.threshold(full,accepted,rejected)
                point = estimate(groups)
                rng = random.Random(self.seed)
                boots = [estimate(rng.choices(groups,k=len(groups))) for _ in range(self.resamples)] if len(groups)>1 else []
                finite = sorted(v for v in boots if v is not None)
                low = finite[int(.025*len(finite))] if finite and len(finite) == len(boots) else None
                high = finite[int(.975*len(finite))] if finite and len(finite) == len(boots) else None
                estimates.append(dict(profile=profile,batch_size=batch,blocks=len(groups),q_threshold=point,
                    bootstrap95_low=low,bootstrap95_high=high,undefined_bootstrap=len(boots)-len(finite),
                    interpretation='q > threshold' if point is not None else 'no monotone threshold'))
                for p in manifest['probabilities'] if batch in validation_batches else ():
                    observed, predicted, savings = [], [], []
                    for block,g in enumerate(groups):
                        sample=validation[(block,profile,batch,p)]
                        actual=st.mean(r['ipv4_bytes'] for r in sample)
                        prediction=p*g['accepted']['ipv4_bytes']+(1-p)*g['rejected']['ipv4_bytes']
                        observed.append(actual);predicted.append(prediction)
                        savings.append(g['full']['ipv4_bytes']-actual)
                    ci=self.interval(savings)
                    checks.append(dict(profile=profile,batch_size=batch,probability=p,blocks=len(groups),
                        observed_mean_ipv4_bytes=st.mean(observed),predicted_mean_ipv4_bytes=st.mean(predicted),
                        prediction_error_bytes=st.mean(a-b for a,b in zip(observed,predicted)),
                        savings_bytes_vs_full=st.mean(savings),savings_ci_low=ci[0],savings_ci_high=ci[1],
                        observed_acceptance=p))
        output=self.directory/'analysis';output.mkdir(exist_ok=True)
        for name,values in [('observacoes.csv',rows),('custos_condicionais.csv',summary),('limiar_aceitacao.csv',estimates),('validacao_disponibilidade.csv',checks)]:
            self.write(output/name,values)
        audit=dict(status='PASS',cases=len(cases),blocks=manifest['blocks'],confirmed_readings=sum(c['confirmed_readings'] for c in cases),
            duplicate_effects=sum(c['duplicate_effects'] for c in cases),
            measurements_sha256=hashlib.sha256((self.directory/'results.json').read_bytes()).hexdigest(),
            inference='ratio of block means; resample complete blocks jointly; independent conditional costs and held-out availability samples',
            scope='warm-up excluded; root trusted but not transmitted; one measured connection per attempt; no ACK loss; no inferred online policy')
        (output/'audit.json').write_text(json.dumps(audit,indent=2)+'\n')
        return output
