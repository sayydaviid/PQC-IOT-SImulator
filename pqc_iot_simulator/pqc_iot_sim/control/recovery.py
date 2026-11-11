"""Notebook API for the recovery experiments and their analyses."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
import importlib.util
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class RecoverySimulation:
    """Reproduce the study in a new output directory, preserving reference data.

    Blocks are the independent repetitions of the TLS comparisons. The default
    reproduces the measured design (ten blocks), rather than a reduced example.
    Methods can also be called separately from notebook cells.
    """

    def __init__(self, directory=None, blocks=10, network=None):
        if directory is None:
            directory = (
                Path.cwd()
                / "results/retomada"
                / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            )
        self.directory = Path(directory).resolve()
        self.network = network
        self.article_directory = None
        if isinstance(blocks, bool) or not isinstance(blocks, int) or blocks < 1:
            raise ValueError("blocks must be a positive integer")
        self.blocks = blocks

    def preflight(self):
        """Check the isolated TLS runtime before starting measured executions."""
        missing = [
            name
            for name in (
                "_context_tls",
                "_continuity_tls",
                "_pqc_tls",
                "mn_wifi",
                "oqs",
            )
            if importlib.util.find_spec(name) is None
        ]
        missing += [
            name
            for name in ("tcpdump", "tc", "ovs-vsctl")
            if shutil.which(name) is None
        ]
        if os.geteuid() != 0:
            missing.append("root inside the privileged research container")
        if missing:
            raise RuntimeError(
                "Start the research notebook container; missing: " + ", ".join(missing)
            )
        native = ROOT / "pqc_iot_simulator/pqc_iot_sim/runtime/native"
        installed = {
            "tls": "/opt/pqc-tls/native/native.c",
            "continuity": "/opt/pqc-tls/continuity/native.c",
            "context_costs": "/opt/pqc-tls/context_costs/native.c",
        }
        for profile, filename in installed.items():
            if (
                hashlib.sha256((native / profile / "native.c").read_bytes()).digest()
                != hashlib.sha256(Path(filename).read_bytes()).digest()
            ):
                raise RuntimeError(
                    "rebuild the research image: native source differs for " + profile
                )
        return {
            "status": "PASS",
            "blocks": self.blocks,
            "directory": str(self.directory),
        }

    def _record(self, stage, result):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / "stages.json"
        stages = json.loads(path.read_text()) if path.exists() else {}
        stages[stage] = result
        if self.network is not None:
            self.network.logger.log(f"Recuperação: {stage} concluído")
        path.write_text(json.dumps(stages, indent=2, default=str) + "\n")
        return result

    def run_prototype(self, *, repetitions=10, messages=8, block_size=32):
        from .state_scenarios import RecoveryStateScenario
        from .interruption_scenarios import RecoveryTransitionScenario

        security = RecoveryStateScenario(
            output=self.directory / "prototype",
            repetitions=repetitions,
            messages=messages,
            block_size=block_size,
        ).run()
        transitions = RecoveryTransitionScenario(
            output=self.directory / "transitions", repetitions=repetitions
        ).run()
        return self._record(
            "prototype", {"security": str(security), "transitions": str(transitions)}
        )

    def run_continuity(
        self, *, source="iot_1", destination="server_1", blocks=None, readings=9
    ):
        self._validate_endpoints(source, destination)
        from ..runtime.tls_continuity import TLSContinuityEngine

        core = TLSContinuityEngine(
            output=self.directory / "core",
            blocks=self.blocks if blocks is None else blocks,
            phase="core",
            readings=readings,
            network=self.network,
            source=source,
            destination=destination,
        ).run()
        loss = TLSContinuityEngine(
            output=self.directory / "loss",
            blocks=self.blocks if blocks is None else blocks,
            phase="loss",
            readings=readings,
            network=self.network,
            source=source,
            destination=destination,
        ).run()
        return self._record("continuity", {"core": str(core), "loss": str(loss)})

    def run_chains(self, *, source="iot_1", destination="server_1", blocks=None):
        self._validate_endpoints(source, destination)
        from ..runtime.tls_chains import CertificateChainEngine

        result = CertificateChainEngine(
            output=self.directory / "chains",
            blocks=self.blocks if blocks is None else blocks,
            network=self.network,
            source=source,
            destination=destination,
        ).run()
        return self._record("chains", result)

    def run_amortization(self, *, source="iot_1", destination="server_1", blocks=None):
        self._validate_endpoints(source, destination)
        from ..runtime.tls_amortization import ConnectionBatchEngine

        result = ConnectionBatchEngine(
            output=self.directory / "amortization",
            blocks=self.blocks if blocks is None else blocks,
            network=self.network,
            source=source,
            destination=destination,
        ).run()
        return self._record("amortization", result)

    def run_sessions(
        self,
        *,
        source="iot_1",
        destination="server_1",
        profile="pqc",
        treatment="resume_preserved",
        readings=9,
        restart_fraction=0.25,
        ack_fraction=0.25,
        deduplicate=True,
        repetitions=10,
        loss_pct=0,
        payload_bytes=31,
        delay_ms=2,
    ):
        """Executa uma condição TLS entre os nós escolhidos.

        As falhas atingem as leituras após a inicial; sua quantidade é
        arredondada para um inteiro. O retorno contém as medições por repetição.
        """
        from ..runtime.tls_continuity import TLSContinuityEngine
        from ..crypto.tls.design import PROFILES, TREATMENTS
        from ..utils.continuity_metrics import ContinuityMetrics
        import pandas as pd

        if profile not in PROFILES or treatment not in TREATMENTS:
            raise ValueError("perfil TLS ou política de retomada inválidos")
        self._validate_endpoints(source, destination)
        trials = self.directory / "sessions"
        number = 1
        while (trials / str(number)).exists():
            number += 1
        output = trials / str(number)
        result = TLSContinuityEngine(
            output=output,
            blocks=repetitions,
            readings=readings,
            network=self.network,
            source=source,
            destination=destination,
            design=[
                (
                    loss_pct,
                    restart_fraction,
                    ack_fraction,
                    profile,
                    treatment,
                    deduplicate,
                )
            ],
            payload_bytes=payload_bytes,
            delay_ms=delay_ms,
        ).run()
        self._record("sessions", str(result))
        cases = json.loads((output / "results.json").read_text())["cases"]
        return pd.DataFrame([ContinuityMetrics.metrics(case) for case in cases])

    def _validate_endpoints(self, source, destination):
        if self.network is None:
            from ..topology.network import Network

            network = Network(verbose=False, log_level="silent")
            network.set_ready_topology("star", 1)
        else:
            network = self.network
        if (
            source not in network.topology_data.nodes
            or destination not in network.topology_data.nodes
        ):
            raise ValueError("origem e destino devem existir na topologia da rede")
        if not source.startswith("iot_") or not destination.startswith("server_"):
            raise ValueError(
                "a origem deve ser um sensor IoT e o destino um servidor TLS"
            )
        return network

    def reproduce_article(self):
        """Recalcula os resultados publicados a partir das observações originais."""
        from ..utils.reanalysis import ArticleNumericalReanalysis

        destination = self.directory / "artigo"
        number = 1
        while destination.exists():
            number += 1
            destination = self.directory / f"artigo_{number}"
        ArticleNumericalReanalysis(destination).run()
        self.article_directory = destination
        return self._record("article_reanalysis", destination)

    def table(self, name, *, article=False):
        """Obtém uma tabela dos experimentos desta rede."""
        import pandas as pd

        tables = {
            "tls": "continuity_analysis/medianas.csv",
            "tls_comparisons": "continuity_analysis/contrastes_pareados.csv",
            "chains": "context_analysis/cadeias_custos_absolutos.csv",
            "chain_comparisons": "context_analysis/cadeias_comparacoes_mesma_repeticao.csv",
            "amortization": "context_analysis/amortizacao_custos_absolutos.csv",
            "amortization_comparisons": "context_analysis/amortizacao_comparacoes_mesma_repeticao.csv",
        }
        if article and self.article_directory is None:
            raise ValueError("Execute primeiro rede.recovery.reproduce_article().")
        directory = self.article_directory if article else self.directory
        return pd.read_csv(directory / tables[name])

    def run_security(self):
        from .identity_scenarios import IdentityScenarios
        from .persistence_scenarios import PersistenceScenarios
        from .tls_persistence_scenarios import TLSPersistenceScenarios
        from .tls_failure_scenarios import TLSFailureScenarios

        outcomes = {}
        for name, validation in (
            ("identity_tickets", IdentityScenarios),
            ("persistence", PersistenceScenarios),
            ("tls_persistence", TLSPersistenceScenarios),
            ("continuity_security", TLSFailureScenarios),
        ):
            outcomes[name] = str(validation(output=self.directory / name).run())
        return self._record("security", outcomes)

    def analyze_continuity(self):
        from ..utils.continuity_metrics import ContinuityMetrics

        result = ContinuityMetrics(
            core=self.directory / "core",
            loss=self.directory / "loss",
            output=self.directory / "continuity_analysis",
        ).run()
        return self._record("continuity_analysis", result)

    def analyze_context(self):
        from ..utils.context_metrics import SessionCostMetrics
        from ..utils.report import ContextReport
        from ..utils.session_results import SessionResultsAudit

        analysis = SessionCostMetrics(
            chains=self.directory / "chains",
            amortization=self.directory / "amortization",
            output=self.directory / "context_analysis",
        ).run()
        for kind in ("chains", "amortization"):
            SessionResultsAudit(
                input=self.directory / kind,
                kind=kind,
                output=analysis / f"auditoria_{kind}.json",
            ).run()
        ContextReport(analysis=analysis, output=analysis / "resultados.md").run()
        return self._record("context_analysis", analysis)

    def compare_article(self):
        """Report agreement and every numerical difference with the article."""
        from ..utils.comparison import ArticleReproductionAudit

        result = ArticleReproductionAudit(
            directory=self.directory, output=self.directory / "article_comparison"
        ).run()
        return self._record("article_comparison", result)

    def run_all(self):
        """Execute the full registered design. This can take several hours."""
        self.preflight()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.run_prototype()
        self.run_continuity()
        self.run_chains()
        self.run_amortization()
        self.run_security()
        self.analyze_continuity()
        self.analyze_context()
        self.compare_article()
        return self.directory
