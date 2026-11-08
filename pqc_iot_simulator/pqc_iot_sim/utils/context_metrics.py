"""Matched-block analysis of the new chain and connection-sharing experiments."""

import csv, hashlib, json, random, statistics
from pathlib import Path


class SessionCostMetrics:
    """Matched-block analysis of the new chain and connection-sharing experiments.

    Configure once, then call ``run()`` from a notebook.
    """

    @staticmethod
    def median(xs):
        return statistics.median(xs)

    @staticmethod
    def interval(xs):
        if not xs or any((x is None for x in xs)):
            return None
        rng = random.Random(20261106)
        res = sorted(
            (
                SessionCostMetrics.median(rng.choices(xs, k=len(xs)))
                for _ in range(10000)
            )
        )
        return [res[249], res[9749]]

    @staticmethod
    def bpr(c):
        n = c["confirmed_readings"]
        return (
            (c["capture"]["iot_tx_ip_bytes"] + c["capture"]["iot_rx_ip_bytes"]) / n
            if n
            else None
        )

    @staticmethod
    def cost(c):
        return c["capture"]["iot_tx_ip_bytes"] + c["capture"]["iot_rx_ip_bytes"]

    @staticmethod
    def ms(c):
        return (
            c["sequence_ms"] / c["readings"]
            if c["delivery_status"] == "complete"
            else None
        )

    @staticmethod
    def load(directory):
        result = json.loads((directory / "results.json").read_text())
        manifest = json.loads((directory / "manifest.json").read_text())
        if (
            result["status"] != "PASS"
            or manifest.get("local_smoke")
            or manifest.get("smoke")
        ):
            raise ValueError("requires definitive complete experiments")
        cases = result["cases"]
        assert len(cases) == manifest["planned_cases"]
        assert len({c["case_id"] for c in cases}) == len(cases)
        return (cases, manifest)

    @staticmethod
    def write(path, rows):
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    @staticmethod
    def summarize(cases, dimensions):
        groups = {}
        for c in cases:
            groups.setdefault(tuple((c[k] for k in dimensions)), []).append(c)
        rows = []
        for key, items in sorted(groups.items()):
            assert len({c["block"] for c in items}) == len(items)
            row = dict(zip(dimensions, key))
            row.update(
                blocks=len(items),
                executions=len(items),
                confirmed_readings=sum((c["confirmed_readings"] for c in items)),
                unconfirmed_readings=sum(
                    (len(c["unconfirmed_readings"]) for c in items)
                ),
                median_ipv4_total_bytes=SessionCostMetrics.median(
                    [SessionCostMetrics.cost(c) for c in items]
                ),
                median_ipv4_bytes_per_confirmed_reading=SessionCostMetrics.median(
                    [SessionCostMetrics.bpr(c) for c in items]
                )
                if all((c["confirmed_readings"] for c in items))
                else None,
                median_ms_per_reading=SessionCostMetrics.median(
                    [SessionCostMetrics.ms(c) for c in items]
                )
                if all((SessionCostMetrics.ms(c) is not None for c in items))
                else None,
                median_full_handshakes=SessionCostMetrics.median(
                    [
                        sum(
                            (
                                not r.get("reused", False)
                                for r in c["clients"]
                                if "version" in r
                            )
                        )
                        for c in items
                    ]
                ),
                median_resumed_handshakes=SessionCostMetrics.median(
                    [
                        sum(
                            (
                                bool(r.get("reused", False))
                                for r in c["clients"]
                                if "version" in r
                            )
                        )
                        for c in items
                    ]
                ),
                duplicate_effects=sum((c["duplicate_effects"] for c in items)),
            )
            rows.append(row)
        return rows

    @staticmethod
    def contrasts(cases, dimensions):
        lookup = {
            tuple((c[k] for k in dimensions)) + (c["block"], c["treatment"]): c
            for c in cases
        }
        rows = []
        for values in sorted({tuple((c[k] for k in dimensions)) for c in cases}):
            for treatment in ["resume_volatile", "resume_preserved"]:
                blocks = sorted(
                    (
                        c["block"]
                        for c in cases
                        if tuple((c[k] for k in dimensions)) == values
                        and c["treatment"] == "full"
                    )
                )
                savings = []
                time_diff = []
                byte_diff = []
                for block in blocks:
                    full = lookup[values + (block, "full")]
                    test = lookup[values + (block, treatment)]
                    savings.append(
                        100
                        * (
                            1
                            - SessionCostMetrics.bpr(test)
                            / SessionCostMetrics.bpr(full)
                        )
                        if SessionCostMetrics.bpr(test) is not None
                        and SessionCostMetrics.bpr(full)
                        else None
                    )
                    byte_diff.append(
                        SessionCostMetrics.bpr(test) - SessionCostMetrics.bpr(full)
                        if SessionCostMetrics.bpr(test) is not None
                        and SessionCostMetrics.bpr(full) is not None
                        else None
                    )
                    time_diff.append(
                        SessionCostMetrics.ms(test) - SessionCostMetrics.ms(full)
                        if SessionCostMetrics.ms(test) is not None
                        and SessionCostMetrics.ms(full) is not None
                        else None
                    )
                ci = SessionCostMetrics.interval(savings)
                ti = SessionCostMetrics.interval(time_diff)
                bi = SessionCostMetrics.interval(byte_diff)
                row = dict(zip(dimensions, values))
                row.update(
                    treatment=treatment,
                    blocks=len(blocks),
                    median_savings_pct=SessionCostMetrics.median(savings)
                    if None not in savings
                    else None,
                    savings_ci_low=ci[0] if ci else None,
                    savings_ci_high=ci[1] if ci else None,
                    median_bytes_difference_per_reading=SessionCostMetrics.median(
                        byte_diff
                    )
                    if None not in byte_diff
                    else None,
                    bytes_difference_ci_low=bi[0] if bi else None,
                    bytes_difference_ci_high=bi[1] if bi else None,
                    median_ms_difference_per_reading=SessionCostMetrics.median(
                        time_diff
                    )
                    if None not in time_diff
                    else None,
                    ms_ci_low=ti[0] if ti else None,
                    ms_ci_high=ti[1] if ti else None,
                )
                rows.append(row)
        return rows

    def __init__(self, *, chains, output, amortization=None):
        self.chains = Path(chains) if chains is not None else None
        self.amortization = Path(amortization) if amortization is not None else None
        self.output = Path(output) if output is not None else None

    def run(self):
        args = self
        args.output.mkdir(parents=True, exist_ok=False)
        (cases, manifest) = SessionCostMetrics.load(args.chains)
        expected = manifest["blocks"] * 3 * 3 * 3 * 2
        assert len(cases) == expected
        absolute = SessionCostMetrics.summarize(
            cases,
            [
                "restart_fraction",
                "ack_fraction",
                "profile",
                "include_root",
                "treatment",
            ],
        )
        paired = SessionCostMetrics.contrasts(
            cases, ["restart_fraction", "ack_fraction", "profile", "include_root"]
        )
        SessionCostMetrics.write(args.output / "cadeias_custos_absolutos.csv", absolute)
        SessionCostMetrics.write(
            args.output / "cadeias_comparacoes_mesma_repeticao.csv", paired
        )
        rootdiff = []
        lookup = {
            (
                c["block"],
                c["restart_fraction"],
                c["profile"],
                c["treatment"],
                c["include_root"],
            ): c
            for c in cases
        }
        for fraction in [0, 0.25, 1]:
            for profile in ["classical", "hybrid", "pqc"]:
                for treatment in ["full", "resume_volatile", "resume_preserved"]:
                    diffs = []
                    reductions = []
                    for block in range(
                        manifest.get("block_start", 0),
                        manifest.get("block_start", 0) + manifest["blocks"],
                    ):
                        withroot = lookup[block, fraction, profile, treatment, 1]
                        without = lookup[block, fraction, profile, treatment, 0]
                        (wr, wo) = (
                            SessionCostMetrics.bpr(withroot),
                            SessionCostMetrics.bpr(without),
                        )
                        diffs.append(
                            wr - wo if wr is not None and wo is not None else None
                        )
                        reductions.append(
                            100 * (1 - wo / wr) if wr and wo is not None else None
                        )
                    ci = SessionCostMetrics.interval(reductions)
                    rootdiff.append(
                        dict(
                            fault_fraction=fraction,
                            profile=profile,
                            treatment=treatment,
                            blocks=len(diffs),
                            median_bytes_saved_per_reading_by_omitting_root=SessionCostMetrics.median(
                                diffs
                            )
                            if None not in diffs
                            else None,
                            median_reduction_pct=SessionCostMetrics.median(reductions)
                            if None not in reductions
                            else None,
                            ci_low=ci[0] if ci else None,
                            ci_high=ci[1] if ci else None,
                        )
                    )
        SessionCostMetrics.write(args.output / "efeito_retirada_raiz.csv", rootdiff)
        audit = {
            "status": "PASS",
            "chain_cases": len(cases),
            "chain_readings": sum((c["readings"] for c in cases)),
            "chain_confirmed": sum((c["confirmed_readings"] for c in cases)),
            "chain_duplicate_effects": sum((c["duplicate_effects"] for c in cases)),
            "bootstrap_samples": 10000,
            "bootstrap_seed": 20261106,
            "inference": "exploratory per condition; block is repetition",
            "inputs": {
                str(args.chains / "results.json"): hashlib.sha256(
                    (args.chains / "results.json").read_bytes()
                ).hexdigest()
            },
            "analyzer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }
        if args.amortization:
            (rows, am) = SessionCostMetrics.load(args.amortization)
            assert len(rows) == am["blocks"] * 3 * 3 * 3 * 2
            SessionCostMetrics.write(
                args.output / "amortizacao_custos_absolutos.csv",
                SessionCostMetrics.summarize(
                    rows, ["recovery", "batch_size", "profile", "treatment"]
                ),
            )
            SessionCostMetrics.write(
                args.output / "amortizacao_comparacoes_mesma_repeticao.csv",
                SessionCostMetrics.contrasts(
                    rows, ["recovery", "batch_size", "profile"]
                ),
            )
            audit.update(
                amortization_cases=len(rows),
                amortization_readings=sum((c["readings"] for c in rows)),
                amortization_confirmed=sum((c["confirmed_readings"] for c in rows)),
                amortization_duplicate_effects=sum(
                    (c["duplicate_effects"] for c in rows)
                ),
            )
            audit["inputs"][str(args.amortization / "results.json")] = hashlib.sha256(
                (args.amortization / "results.json").read_bytes()
            ).hexdigest()
        (args.output / "audit.json").write_text(json.dumps(audit, indent=2))
        print(json.dumps(audit, indent=2))
        return args.output
