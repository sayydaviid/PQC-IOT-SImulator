"""Notebook API for the recovery experiments and their analyses."""

from __future__ import annotations

import hashlib
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

    def __init__(self, directory, blocks=10):
        self.directory = Path(directory).resolve()
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
        native = ROOT / "pqc_iot_simulator/pqc_iot_sim/engines/native"
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
        path.write_text(json.dumps(stages, indent=2, default=str) + "\n")
        return result

    def run_prototype(self):
        from pqc_iot_simulator.pqc_iot_sim.core.recovery_state_scenario import (
            RecoveryStateScenario,
        )
        from pqc_iot_simulator.pqc_iot_sim.core.recovery_transition_scenario import (
            RecoveryTransitionScenario,
        )

        security = RecoveryStateScenario(
            output=self.directory / "prototype", repetitions=10
        ).run()
        transitions = RecoveryTransitionScenario(
            output=self.directory / "transitions", repetitions=10
        ).run()
        return self._record(
            "prototype", {"security": str(security), "transitions": str(transitions)}
        )

    def run_continuity(self):
        from pqc_iot_simulator.pqc_iot_sim.engines.tls_continuity import (
            TLSContinuityEngine,
        )

        core = TLSContinuityEngine(
            output=self.directory / "core", blocks=self.blocks, phase="core"
        ).run()
        loss = TLSContinuityEngine(
            output=self.directory / "loss", blocks=self.blocks, phase="loss"
        ).run()
        return self._record("continuity", {"core": str(core), "loss": str(loss)})

    def run_chains(self):
        from pqc_iot_simulator.pqc_iot_sim.engines.tls_chains import (
            CertificateChainEngine,
        )

        result = CertificateChainEngine(
            output=self.directory / "chains", blocks=self.blocks
        ).run()
        return self._record("chains", result)

    def run_amortization(self):
        from pqc_iot_simulator.pqc_iot_sim.engines.tls_amortization import (
            ConnectionBatchEngine,
        )

        result = ConnectionBatchEngine(
            output=self.directory / "amortization", blocks=self.blocks
        ).run()
        return self._record("amortization", result)

    def run_security(self):
        from pqc_iot_simulator.pqc_iot_sim.validation.identity_tickets import (
            TicketIdentityValidation,
        )
        from pqc_iot_simulator.pqc_iot_sim.validation.persistence import (
            PersistenceValidation,
        )
        from pqc_iot_simulator.pqc_iot_sim.validation.tls_persistence import (
            TLSPersistenceValidation,
        )
        from pqc_iot_simulator.pqc_iot_sim.validation.continuity_security import (
            ContinuitySecurityValidation,
        )

        outcomes = {}
        for name, validation in (
            ("identity_tickets", TicketIdentityValidation),
            ("persistence", PersistenceValidation),
            ("tls_persistence", TLSPersistenceValidation),
            ("continuity_security", ContinuitySecurityValidation),
        ):
            outcomes[name] = str(validation(output=self.directory / name).run())
        return self._record("security", outcomes)

    def analyze_continuity(self):
        from pqc_iot_simulator.pqc_iot_sim.components.continuity_metrics import (
            ContinuityMetrics,
        )

        result = ContinuityMetrics(
            core=self.directory / "core",
            loss=self.directory / "loss",
            output=self.directory / "continuity_analysis",
        ).run()
        return self._record("continuity_analysis", result)

    def analyze_context(self):
        from pqc_iot_simulator.pqc_iot_sim.components.context_metrics import (
            SessionCostMetrics,
        )
        from pqc_iot_simulator.pqc_iot_sim.components.context_report import (
            ContextReport,
        )
        from pqc_iot_simulator.pqc_iot_sim.validation.context_results import (
            ContextResultsValidation,
        )

        analysis = SessionCostMetrics(
            chains=self.directory / "chains",
            amortization=self.directory / "amortization",
            output=self.directory / "context_analysis",
        ).run()
        for kind in ("chains", "amortization"):
            ContextResultsValidation(
                input=self.directory / kind,
                kind=kind,
                output=analysis / f"auditoria_{kind}.json",
            ).run()
        ContextReport(analysis=analysis, output=analysis / "resultados.md").run()
        return self._record("context_analysis", analysis)

    def compare_article(self):
        """Report agreement and every numerical difference with the article."""
        from pqc_iot_simulator.pqc_iot_sim.core.result_comparison import (
            ArticleReproductionAudit,
        )

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
