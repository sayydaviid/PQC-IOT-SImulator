"""Exporta seis painéis dos testes de contexto, sem executar novos experimentos."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[4]
PROFILES = ("classical", "hybrid", "pqc")
NAMES = (
    "X25519\nECDSA P-256",
    "X25519MLKEM768\nECDSA P-256",
    "X25519MLKEM768\nML-DSA-44",
)
POLICIES = ("full", "resume_volatile", "resume_preserved")
LABELS = ("Completo", "Perdido", "Preservado")
COLORS = ("#315a91", "#b56a29", "#227a65")
FILES = (
    "cadeias_custos_absolutos.csv",
    "cadeias_comparacoes_mesma_repeticao.csv",
    "amortizacao_custos_absolutos.csv",
    "amortizacao_comparacoes_mesma_repeticao.csv",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def one(rows, **where):
    def equal(actual, expected):
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            return float(actual) == expected
        return actual == str(expected)

    found = [r for r in rows if all(equal(r[k], v) for k, v in where.items())]
    assert len(found) == 1, (where, len(found))
    assert int(found[0]["blocks"]) == 10
    return found[0]


def style(ax):
    ax.grid(axis="y", alpha=0.18, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)


def key_title(ax):
    ax.set_title("X25519MLKEM768 + ML-DSA-44", fontsize=8, pad=6)


def panel_a(ax, chain, comparisons, amort, amort_cmp, diagnostic):
    x = np.arange(3)
    values = {}
    for j, (policy, color, label) in enumerate(zip(POLICIES, COLORS, LABELS)):
        ys = [
            float(
                one(
                    chain,
                    restart_fraction=1,
                    ack_fraction=1,
                    include_root=0,
                    profile=p,
                    treatment=policy,
                )["median_ipv4_bytes_per_confirmed_reading"]
            )
            / 1000
            for p in PROFILES
        ]
        values[policy] = ys
        ax.bar(x + (j - 1) * 0.25, ys, 0.23, color=color, label=label)
    assert abs(values["full"][2] - 41.4636666667) < 0.001
    assert abs(values["resume_preserved"][2] - 17.5047777778) < 0.001
    ax.set_xticks(x, NAMES)
    ax.set_ylabel("IPv4 por leitura (kB)")
    ax.set_ylim(0, 62)
    ax.set_title("Raiz omitida; ambas as falhas em 100%", fontsize=8, pad=6)
    ax.legend(ncol=3, fontsize=7.2, loc="upper left", columnspacing=0.7, handlelength=1)


def panel_b(ax, chain, comparisons, amort, amort_cmp, diagnostic):
    x = np.arange(3)
    series = (
        (1, "resume_volatile", COLORS[1], "//"),
        (0, "resume_volatile", COLORS[1], ""),
        (1, "resume_preserved", COLORS[2], "//"),
        (0, "resume_preserved", COLORS[2], ""),
    )
    for j, (root, policy, color, hatch) in enumerate(series):
        rows = [
            one(
                comparisons,
                restart_fraction=1,
                ack_fraction=1,
                include_root=root,
                profile=p,
                treatment=policy,
            )
            for p in PROFILES
        ]
        ys = [float(r["median_savings_pct"]) for r in rows]
        errors = [
            [y - float(r["savings_ci_low"]) for y, r in zip(ys, rows)],
            [float(r["savings_ci_high"]) - y for y, r in zip(ys, rows)],
        ]
        ax.bar(
            x + (j - 1.5) * 0.19,
            ys,
            0.18,
            color=color,
            hatch=hatch,
            edgecolor="white",
            linewidth=0.5,
            yerr=errors,
            capsize=1.5,
            error_kw={"elinewidth": 0.6},
        )
        if root == 0 and policy == "resume_volatile":
            assert abs(ys[2] + 19.70) < 0.02
    ax.axhline(0, color="black", linestyle="--", linewidth=0.65)
    ax.set_xticks(x, NAMES)
    ax.set_ylim(-37, 90)
    ax.set_ylabel("Economia frente ao completo (%)")
    first = ax.legend(
        handles=[Patch(facecolor=c, label=l) for c, l in zip(COLORS[1:], LABELS[1:])],
        loc="upper left",
        ncol=2,
        fontsize=7.3,
    )
    ax.add_artist(first)
    ax.legend(
        handles=[
            Patch(facecolor="white", edgecolor="#555", hatch=h, label=l)
            for h, l in (("//", "Raiz enviada"), ("", "Raiz omitida"))
        ],
        loc="lower left",
        ncol=2,
        fontsize=7,
        handlelength=1.4,
        columnspacing=0.7,
    )
    ax.set_title("Ambas as falhas em 100%", fontsize=8, pad=6)


def controls(diagnostic):
    ds = diagnostic["diagnostics"]
    ec, ml = ds[-2:]
    assert ec["client_key"] == "EC" and ml["client_key"] == "ML-DSA-44"
    assert ec["profile"] == ml["profile"] == "pqc" and ec["root"] == ml["root"] == 0
    for identity in ("server", "ca"):
        assert (
            ec["certificates"][identity]["sha256"]
            == ml["certificates"][identity]["sha256"]
        )
    return ec, ml


def panel_c(ax, chain, comparisons, amort, amort_cmp, diagnostic):
    ec, ml = controls(diagnostic)
    x = np.arange(3)
    for j, (d, color, label) in enumerate(
        zip((ec, ml), COLORS[:2], ("Cliente ECDSA P-256", "Cliente ML-DSA-44"))
    ):
        c = d["connections"][0]
        ys = [
            d["certificates"]["client"]["der_bytes"],
            c["ticket_plaintext_session_der_bytes"],
            c["tickets_tx_bytes"][0],
        ]
        assert ys == ([2775, 2927, 2992] if j == 0 else [4018, 4170, 4240])
        bars = ax.bar(x + (j - 0.5) * 0.36, ys, 0.34, color=color, label=label)
        for bar, y in zip(bars, ys):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                y + 70,
                f"{y:,}".replace(",", "."),
                ha="center",
                fontsize=7,
            )
    ax.set_xticks(x, ("Certificado\ndo cliente", "Estado\nda sessão", "Ticket"))
    ax.set_ylabel("Tamanho (bytes)")
    ax.set_ylim(0, 5500)
    ax.legend(fontsize=7.3, loc="upper left", ncol=1)
    ax.set_title("Servidor e CA com ML-DSA-44 mantidos", fontsize=8, pad=6)


def panel_d(ax, chain, comparisons, amort, amort_cmp, diagnostic):
    x = np.arange(3)
    for j, (policy, color, label) in enumerate(zip(POLICIES, COLORS, LABELS)):
        ys = [
            float(
                one(
                    amort, recovery=False, batch_size=b, profile="pqc", treatment=policy
                )["median_ipv4_bytes_per_confirmed_reading"]
            )
            / 1000
            for b in (1, 10, 100)
        ]
        ax.bar(x + (j - 1) * 0.25, ys, 0.23, color=color, label=label)
        if policy == "full":
            assert abs(ys[0] - 22.86518) < 0.001
    ax.set_xticks(x, ("1", "10", "100"))
    ax.set_xlabel("Limite de leituras por conexão")
    ax.set_ylabel("IPv4 por leitura (kB)")
    ax.set_ylim(0, 29)
    ax.legend(
        ncol=3, fontsize=7.2, loc="upper right", columnspacing=0.6, handlelength=1
    )
    key_title(ax)


def panel_e(ax, chain, comparisons, amort, amort_cmp, diagnostic):
    for policy, color, label in zip(POLICIES[1:], COLORS[1:], LABELS[1:]):
        rows = [
            one(amort_cmp, recovery=True, batch_size=b, profile="pqc", treatment=policy)
            for b in (1, 10, 100)
        ]
        ys = [float(r["median_savings_pct"]) for r in rows]
        errors = [
            [y - float(r["savings_ci_low"]) for y, r in zip(ys, rows)],
            [float(r["savings_ci_high"]) - y for y, r in zip(ys, rows)],
        ]
        ax.errorbar(
            (0, 1, 2),
            ys,
            yerr=errors,
            color=color,
            marker="o",
            markersize=4,
            label=label,
            linewidth=1.3,
            capsize=2,
        )
        assert abs(ys[-1] - (-5.12 if policy == "resume_volatile" else 15.11)) < 0.02
    ax.axhline(0, color="black", linestyle="--", linewidth=0.65)
    ax.set_xticks((0, 1, 2), ("1", "10", "100"))
    ax.set_xlabel("Limite de leituras por conexão")
    ax.set_ylabel("Economia frente ao completo (%)")
    ax.set_ylim(-15, 75)
    ax.legend(ncol=2, fontsize=7.4, loc="upper right")
    key_title(ax)


def panel_f(ax, chain, comparisons, amort, amort_cmp, diagnostic):
    for recovery, offset, color, marker, label in (
        (False, -0.07, COLORS[0], "s", "Sem falhas"),
        (True, 0.07, COLORS[2], "o", "Recuperação"),
    ):
        rows = [
            one(
                amort_cmp,
                recovery=recovery,
                batch_size=b,
                profile="pqc",
                treatment="resume_preserved",
            )
            for b in (1, 10, 100)
        ]
        ys = [float(r["median_ms_difference_per_reading"]) for r in rows]
        errors = [
            [y - float(r["ms_ci_low"]) for y, r in zip(ys, rows)],
            [float(r["ms_ci_high"]) - y for y, r in zip(ys, rows)],
        ]
        ax.errorbar(
            np.arange(3) + offset,
            ys,
            yerr=errors,
            color=color,
            fmt=marker,
            markersize=4,
            capsize=3,
            label=label,
        )
        if not recovery:
            assert abs(ys[-1] - 0.17) < 0.02
    ax.axhline(0, color="black", linestyle="--", linewidth=0.65)
    ax.set_xticks((0, 1, 2), ("1", "10", "100"))
    ax.set_xlabel("Limite de leituras por conexão")
    ax.set_ylabel("Diferença de tempo (ms/leitura)")
    ax.set_ylim(-150, 25)
    ax.legend(ncol=2, fontsize=7.4, loc="lower right")
    key_title(ax)


PANELS = (
    ("contexto_custos_sem_raiz", panel_a),
    ("contexto_economia_cadeias", panel_b),
    ("contexto_ticket_identidade", panel_c),
    ("contexto_leituras_custos", panel_d),
    ("contexto_leituras_recuperacao", panel_e),
    ("contexto_leituras_tempo", panel_f),
)


class ContextFigures:
    """Exporta seis painéis dos testes de contexto, sem executar novos experimentos.

    Configure once, then call ``run()`` from a notebook.
    """

    def __init__(
        self,
        *,
        data_dir=ROOT / "docs/resultados_contexto_20261106",
        diagnostic=ROOT / "docs/diagnostico_tickets_20261106.json",
        output=ROOT / "results/pesquisa/figuras",
    ):
        self.data_dir = Path(data_dir) if data_dir is not None else None
        self.diagnostic = Path(diagnostic) if diagnostic is not None else None
        self.output = Path(output) if output is not None else None

    def run(self):
        args = self
        args.output.mkdir(parents=True, exist_ok=True)
        paths = [args.data_dir / f for f in FILES] + [args.diagnostic]
        before = {p.name: sha(p) for p in paths}
        data = [read(p) for p in paths[:-1]] + [json.loads(args.diagnostic.read_text())]
        assert data[-1]["status"] == "PASS"
        assert len(data[0]) == 54 and len(data[2]) == 54
        blocks = {int(r["blocks"]) for r in data[0] + data[2]}
        if len(blocks) != 1:
            raise ValueError("chain and amortization block counts differ")
        blocks = blocks.pop()
        assert sum((int(r["executions"]) for r in data[0])) == 54 * blocks
        assert sum((int(r["executions"]) for r in data[2])) == 54 * blocks
        assert sum((int(r["confirmed_readings"]) for r in data[0])) == 486 * blocks
        assert sum((int(r["confirmed_readings"]) for r in data[2])) == 5400 * blocks
        assert all(
            (
                int(r["duplicate_effects"]) == 0 and int(r["unconfirmed_readings"]) == 0
                for r in data[0] + data[2]
            )
        )
        plt.rcParams.update(
            {
                "font.family": "DejaVu Sans",
                "font.size": 9,
                "axes.labelsize": 9,
                "xtick.labelsize": 7.3,
                "ytick.labelsize": 8.5,
                "pdf.fonttype": 42,
                "svg.fonttype": "none",
            }
        )
        for name, draw in PANELS:
            (fig, ax) = plt.subplots(figsize=(4, 2.6), layout="constrained")
            style(ax)
            draw(ax, *data)
            for ext in ("pdf", "png", "svg"):
                fig.savefig(args.output / (name + "." + ext), dpi=280)
            plt.close(fig)
        assert before == {p.name: sha(p) for p in paths}
        proof = {
            "status": "PASS",
            "inputs_sha256": before,
            "exporter_sha256": sha(Path(__file__)),
            "chain_executions": 54 * blocks,
            "chain_confirmed_readings": 486 * blocks,
            "amortization_executions": 54 * blocks,
            "amortization_confirmed_readings": 5400 * blocks,
            "blocks_per_condition": blocks,
            "scope": {
                "a": "Cadeias: 100%/100%, raiz omitida, mediana de bytes por leitura.",
                "b": "Cadeias: 100%/100%, medianas de comparações dentro da repetição; IC bootstrap exploratório 95%.",
                "c": "Controle local com exatamente mesmo servidor e CA; não é amostra de custo de rede.",
                "d": "100 leituras de 512 bytes, sem falhas, primeiro completo incluído, raiz omitida.",
                "e": "Mesma carga; reinício antes da 51ª leitura e supressão de sua primeira confirmação.",
                "f": "Contexto preservado menos completo, diferenças dentro do bloco e IC bootstrap exploratório 95%.",
            },
            "all_network_panels": {
                "packet_loss_pct": 0,
                "deduplication": True,
                "root_trust": "mantida",
            },
            "panels": [name for (name, _) in PANELS],
        }
        (args.output / "proveniencia.json").write_text(
            json.dumps(proof, ensure_ascii=False, indent=2) + "\n"
        )
        print(f"PASS: seis painéis; {blocks} blocos; dados de origem preservados.")
        return args.output
