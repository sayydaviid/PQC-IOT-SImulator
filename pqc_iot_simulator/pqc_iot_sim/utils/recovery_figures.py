"""Figures for the current recovery experiments, kept out of notebook cells."""

import csv
import hashlib
import json
import statistics
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

from ..crypto.tls.diagnostics import TicketDiagnostics

# Gráficos de falhas de estado e interrupções.

PROTOTYPE_ROOT = Path(__file__).resolve().parents[3]
PROTOTYPE_POLICIES = [
    "checkpoint",
    "persist_each",
    "reserve_blocks",
    "full_pqc",
    "psk_resume",
    "pqc_resume",
]
PROTOTYPE_LABELS = ["Checkpoint", "Por uso", "Blocos", "Completo", "PSK", "PSK+KEM"]
PROTOTYPE_MODES = ["full_pqc", "psk_resume", "pqc_resume"]
PROTOTYPE_NAMES = ["Completo", "PSK", "PSK+KEM"]
PROTOTYPE_COLORS = ["#315a91", "#b56a29", "#227a65"]
PROTOTYPE_FIGURES = {
    "figura_4_estado": (
        ("estado_energia", "(a) Queda de energia modelada."),
        ("estado_rollback", "(b) Rollback do armazenamento."),
        ("estado_textos", "(c) Textos recuperados."),
        ("estado_escritas", "(d) Escritas na fase estável."),
    ),
    "figura_5_interrupcoes": (
        ("transicoes_bytes", "(a) Bytes por interrupção."),
        ("transicoes_fallbacks", "(b) Autenticações completas."),
        ("transicoes_economia", "(c) Economia de bytes."),
        ("transicoes_duplicados", "(d) Efeitos duplicados."),
    ),
}


def save_formats(fig, path, dpi=300):
    for suffix in ("png", "pdf", "svg"):
        fig.savefig(path.with_suffix("." + suffix), dpi=dpi)


def read_campaign(directory):
    directory = Path(directory)
    manifest = (directory / "manifest.json").read_bytes()
    json.loads(manifest)
    raw = (directory / "results.json").read_bytes()
    return (
        json.loads(raw), hashlib.sha256(raw).hexdigest(),
        hashlib.sha256(manifest).hexdigest(),
    )


class PrototypeFigures:
    """Render panels from the measured and verified recovery campaigns.

    Configure once, then call ``run()`` from a notebook.
    """

    def __init__(self, *, security, transitions, output, tls=None):
        self.security = Path(security)
        self.transitions = Path(transitions)
        self.tls = Path(tls) if tls is not None else None
        self.output = Path(output)

    def run(self, *, _combined=False):
        args = self
        security, security_hash, security_manifest = read_campaign(args.security)
        transitions, transition_hash, transition_manifest = read_campaign(args.transitions)
        tls, tls_hash, tls_manifest = read_campaign(args.tls) if args.tls else (None, None, None)
        if (
            security["verdict"]["status"] != "SUPPORTED_IN_TESTED_MODEL"
            or transitions["assessment"]["status"] != "PASS"
        ):
            raise RuntimeError("failed experiments cannot support figures")
        state_parameters = json.loads((args.security / "manifest.json").read_text())["parameters"]
        transition_parameters = json.loads((args.transitions / "manifest.json").read_text())["parameters"]
        state_repetitions = state_parameters["repetitions"]
        transition_repetitions = transition_parameters["repetitions"]
        messages = state_parameters["messages"]
        if (len(security["cases"]) != state_repetitions * len(PROTOTYPE_POLICIES) * 4
                or len(transitions["cases"]) != transition_repetitions * len(PROTOTYPE_MODES) * len(transition_parameters["scenarios"])):
            raise ValueError("Os resultados não correspondem aos parâmetros do experimento")
        if tls is not None and (tls["status"] != "PASS" or len(tls["cases"]) != 60):
            raise ValueError("legacy TLS figures require the complete 60-case pilot")


        plt.rcParams.update(
            {
                "font.size": 9,
                "font.family": "DejaVu Sans",
                "axes.spines.top": False,
                "axes.spines.right": False,
                "pdf.fonttype": 42,
                "svg.fonttype": "none",
                "savefig.dpi": 300,
            }
        )
        args.output.mkdir(parents=True, exist_ok=True)
        panels = []
        combined = {}
        panel_axes = {}
        if _combined:
            for name, layout in PROTOTYPE_FIGURES.items():
                fig, axes = plt.subplots(2, 2, figsize=(9.2, 6.8), layout="constrained")
                combined[name] = fig
                for ax, (panel, caption) in zip(axes.flat, layout):
                    ax.text(0, 1.05, caption, transform=ax.transAxes, fontsize=9,
                            ha="left", va="bottom")
                    panel_axes[panel] = fig, ax

        def canvas(name=None):
            if name in panel_axes:
                fig, ax = panel_axes[name]
            else:
                fig, ax = plt.subplots(figsize=(4.6, 3.1), layout="constrained")
            ax.grid(axis="y", alpha=0.2)
            ax.set_axisbelow(True)
            return (fig, ax)

        def save(fig, name):
            if not _combined:
                save_formats(fig, args.output / name)
                plt.close(fig)
            panels.append(name)

        def bars(name, labels, values, ylabel, colors=None, rotate=0):
            (fig, ax) = canvas(name)
            ax.bar(range(len(values)), values, color=colors or PROTOTYPE_COLORS[0], width=0.65)
            ax.set_xticks(
                range(len(values)),
                labels,
                rotation=rotate,
                ha="right" if rotate else "center",
            )
            ax.set_ylabel(ylabel)
            ax.set_ylim(0, max(values, default=0) * 1.23 or 1)
            for i, value in enumerate(values):
                ax.annotate(
                    f"{value:g}",
                    (i, value),
                    xytext=(0, 4),
                    textcoords="offset points",
                    ha="center",
                )
            save(fig, name)

        security_summary = {}
        for fault in ("power_loss", "client_storage_rollback"):
            security_summary[fault] = []
            for policy in PROTOTYPE_POLICIES:
                rows = [
                    r
                    for r in security["cases"]
                    if r["fault"] == fault and r["policy"] == policy
                ]
                assert len(rows) == state_repetitions
                assert {r["repetition"] for r in rows} == set(range(state_repetitions))
                security_summary[fault].append(
                    {
                        "policy": policy,
                        "reuses": sum((r["reused_key_nonce"] for r in rows)),
                        "plaintexts": sum(
                            (r["known_plaintext_recoveries"] for r in rows)
                        ),
                        "writes": statistics.median(
                            (r["steady_state_writes"] for r in rows)
                        ),
                    }
                )
        for name, fault, field, ylabel in [
            (
                "estado_energia",
                "power_loss",
                "reuses",
                "Reutilizações após queda de energia",
            ),
            (
                "estado_rollback",
                "client_storage_rollback",
                "reuses",
                "Reutilizações após rollback completo",
            ),
            (
                "estado_textos",
                "client_storage_rollback",
                "plaintexts",
                "Textos recuperados após rollback",
            ),
            (
                "estado_escritas",
                "power_loss",
                "writes",
                f"Escritas na fase estável de {messages} leituras",
            ),
        ]:
            bars(
                name,
                PROTOTYPE_LABELS,
                [r[field] for r in security_summary[fault]],
                ylabel,
                rotate=30,
            )
        scenarios = list(dict.fromkeys((r["scenario"] for r in transitions["cases"])))
        scenario_labels = [
            "Sem falha",
            "ClientHello",
            "ServerHello",
            "ClientFinished",
            "Commit",
            "Confirmação",
            "Checkpoint",
            "Cifragem",
            "ACK perdido",
            "Truncado",
            "Raiz perdida",
        ]
        transition_summary = []
        for scenario in scenarios:
            row = {"scenario": scenario}
            for mode in PROTOTYPE_MODES:
                selected = [
                    r
                    for r in transitions["cases"]
                    if r["scenario"] == scenario and r["policy"] == mode
                ]
                assert len(selected) == transition_repetitions
                assert {r["repetition"] for r in selected} == set(range(transition_repetitions))
                row[mode] = {
                    "bytes": statistics.median(
                        (r["total_handshake_bytes"] for r in selected)
                    ),
                    "fallbacks": sum((r["full_fallback"] for r in selected)),
                    "duplicates": sum((r["application_duplicates"] for r in selected)),
                }
            transition_summary.append(row)
        (fig, ax) = canvas("transicoes_bytes")
        for mode, label, color in zip(PROTOTYPE_MODES, PROTOTYPE_NAMES, PROTOTYPE_COLORS):
            ax.plot(
                range(len(scenarios)),
                [r[mode]["bytes"] / 1000 for r in transition_summary],
                "o-",
                label=label,
                color=color,
                markersize=3,
            )
        ax.set_xticks(range(len(scenarios)), list("ABCDEFGHIJK"))
        ax.set_xlabel("Ponto de interrupção (A-K)")
        ax.set_ylabel("Mediana de bytes enquadrados (mil)")
        ax.legend(fontsize=8)
        save(fig, "transicoes_bytes")
        selected_faults = transition_summary[-2:]
        bars(
            "transicoes_fallbacks",
            ["Checkpoint\ntruncado", "Raiz\nperdida"],
            [r["pqc_resume"]["fallbacks"] for r in selected_faults],
            "Fallbacks completos: PSK+KEM",
        )
        savings = [
            100 * (1 - r["pqc_resume"]["bytes"] / r["full_pqc"]["bytes"])
            for r in transition_summary
        ]
        (fig, ax) = canvas("transicoes_economia")
        indices = [0, 9, 10]
        values = [savings[i] for i in indices]
        ax.bar(range(3), values, color=[PROTOTYPE_COLORS[2], PROTOTYPE_COLORS[2], PROTOTYPE_COLORS[1]])
        ax.axhline(0, color="#444444", linewidth=0.7)
        ax.set_xticks(range(3), ["Sem falha", "Truncado", "Raiz perdida"])
        ax.set_ylabel("Economia frente ao completo (%)")
        ax.set_ylim(-17, 82)
        for i, value in enumerate(values):
            ax.annotate(
                f"{value:.2f}%".replace(".", ","),
                (i, value),
                xytext=(0, 5 if value >= 0 else -13),
                textcoords="offset points",
                ha="center",
            )
        save(fig, "transicoes_economia")
        lost = next(
            (r for r in transition_summary if r["scenario"] == "lost_reading_ack")
        )
        bars(
            "transicoes_duplicados",
            PROTOTYPE_NAMES,
            [lost[m]["duplicates"] for m in PROTOTYPE_MODES],
            "Efeitos duplicados com ACK perdido",
            PROTOTYPE_COLORS,
        )
        tls_summary, warm, duplicates = [], {}, []
        if tls is not None and not _combined:
            cases = tls["cases"]
            tls_summary = []
            for loss in (0, 1, 5):
                for mode in ("full", "resume"):
                    selected = [
                        c
                        for c in cases
                        if c["loss_pct"] == loss
                        and c["mode"] == mode
                        and c["deduplicate"]
                    ]
                    assert len(selected) == 5
                    wire = [
                        c["capture"]["iot_tx_ip_bytes"]
                        + c["capture"]["iot_rx_ip_bytes"]
                        for c in selected
                    ]
                    row = {
                        "loss": loss,
                        "mode": mode,
                        "wire_median": statistics.median(wire),
                        "wire_min": min(wire),
                        "wire_max": max(wire),
                    }
                    for key in ("first_reading_ack_ms", "reading_recovery_ms"):
                        row[key] = statistics.median(
                            (
                                statistics.median(
                                    (r[key] for r in c["clients"] if r["acknowledged"])
                                )
                                for c in selected
                            )
                        )
                    row["tcp_retransmitted_segments"] = statistics.median(
                        (
                            sum(
                                (
                                    r["tcp_retransmitted_segments"]
                                    for r in c["clients"] + c["server_connections"]
                                )
                            )
                            for c in selected
                        )
                    )
                    tls_summary.append(row)
            warm = {
                mode: statistics.median(
                    (
                        r["handshake_tx_tls_bytes"] + r["handshake_rx_tls_bytes"]
                        for c in cases
                        if c["mode"] == mode
                        for r in c["clients"]
                        if r["boot"] == 1
                    )
                )
                for mode in ("full", "resume")
            }
            bars(
                "tls_handshake",
                ["Completo", "Retomada"],
                list(warm.values()),
                "Mediana de bytes TLS até SSL_connect",
                [PROTOTYPE_COLORS[0], PROTOTYPE_COLORS[2]],
            )
            for name, field, ylabel in [
                ("tls_ipv4", "wire_median", "Bytes IPv4 por ensaio (mil)"),
                (
                    "tls_ack",
                    "first_reading_ack_ms",
                    "Confirmação após TCP conectado (ms)",
                ),
                (
                    "tls_recuperacao",
                    "reading_recovery_ms",
                    "Recuperação da leitura no host (ms)",
                ),
                (
                    "tls_retransmissoes",
                    "tcp_retransmitted_segments",
                    "Segmentos TCP retransmitidos por ensaio",
                ),
            ]:
                (fig, ax) = canvas()
                for i, (mode, label, color) in enumerate(
                    zip(
                        ("full", "resume"),
                        ("Completo", "Retomada"),
                        (PROTOTYPE_COLORS[0], PROTOTYPE_COLORS[2]),
                    )
                ):
                    rows = [r for r in tls_summary if r["mode"] == mode]
                    scale = 1000 if field == "wire_median" else 1
                    x = [j + (i - 0.5) * 0.35 for j in range(3)]
                    values = [r[field] / scale for r in rows]
                    error = (
                        [
                            [v - r["wire_min"] / scale for (v, r) in zip(values, rows)],
                            [r["wire_max"] / scale - v for (v, r) in zip(values, rows)],
                        ]
                        if field == "wire_median"
                        else None
                    )
                    ax.bar(
                        x,
                        values,
                        width=0.35,
                        label=label,
                        color=color,
                        yerr=error,
                        capsize=3,
                    )
                ax.set_xticks(range(3), ["0%", "1%", "5%"])
                ax.set_xlabel("Perda configurada por direção")
                ax.set_ylabel(ylabel)
                ax.legend(fontsize=8)
                save(fig, name)
            duplicates = [
                sum(
                    (
                        c["application"]["duplicate_effects"]
                        for c in cases
                        if c["deduplicate"] == d
                    )
                )
                for d in (False, True)
            ]
            bars(
                "tls_duplicados",
                ["Desativada", "Durável"],
                duplicates,
                "Efeitos duplicados",
                [PROTOTYPE_COLORS[1], PROTOTYPE_COLORS[2]],
            )
        if _combined:
            for name, fig in combined.items():
                save_formats(fig, args.output / name)
                plt.close(fig)
            return args.output

        self.run(_combined=True)
        facts = {
            "source_sha256": {
                "security": security_hash,
                "transitions": transition_hash,
                "tls": tls_hash,
            },
            "manifest_sha256": {
                "security": security_manifest,
                "transitions": transition_manifest,
                "tls": tls_manifest,
            },
            "figure_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "combined_figures": list(PROTOTYPE_FIGURES),
            "security": security_summary,
            "transitions": transition_summary,
            "scenario_labels": scenario_labels,
            "tls": tls_summary,
            "tls_warm_bytes": warm,
            "tls_duplicates": duplicates,
            "panels": panels,
            "statistics": f"{state_repetitions} repetições de estado; {transition_repetitions} repetições de interrupções; medianas descritivas.",
        }
        (args.output / "dados_figuras.json").write_text(
            json.dumps(facts, indent=2, ensure_ascii=False)
        )
        return args.output


# Gráficos de cadeias, tickets e leituras por conexão.

CONTEXT_ROOT = Path(__file__).resolve().parents[3]
CONTEXT_PROFILES = ("classical", "hybrid", "pqc")
CONTEXT_NAMES = (
    "X25519\nECDSA P-256",
    "X25519MLKEM768\nECDSA P-256",
    "X25519MLKEM768\nML-DSA-44",
)
CONTEXT_POLICIES = ("full", "resume_volatile", "resume_preserved")
CONTEXT_LABELS = ("Completo", "Perdido", "Preservado")
CONTEXT_COLORS = ("#315a91", "#b56a29", "#227a65")
CONTEXT_FILES = (
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
    assert int(found[0]["blocks"]) > 0
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
    for j, (policy, color, label) in enumerate(zip(CONTEXT_POLICIES, CONTEXT_COLORS, CONTEXT_LABELS)):
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
            for p in CONTEXT_PROFILES
        ]
        values[policy] = ys
        ax.bar(x + (j - 1) * 0.25, ys, 0.23, color=color, label=label)
    ax.set_xticks(x, CONTEXT_NAMES)
    ax.set_ylabel("IPv4 por leitura (kB)")
    ax.margins(y=0.2)
    ax.set_ylim(bottom=0)
    ax.set_title("Raiz omitida; ambas as falhas em 100%", fontsize=8, pad=6)
    ax.legend(ncol=3, fontsize=7.2, loc="upper left", columnspacing=0.7, handlelength=1)


def panel_b(ax, chain, comparisons, amort, amort_cmp, diagnostic):
    x = np.arange(3)
    series = (
        (1, "resume_volatile", CONTEXT_COLORS[1], "//"),
        (0, "resume_volatile", CONTEXT_COLORS[1], ""),
        (1, "resume_preserved", CONTEXT_COLORS[2], "//"),
        (0, "resume_preserved", CONTEXT_COLORS[2], ""),
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
            for p in CONTEXT_PROFILES
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
    ax.axhline(0, color="black", linestyle="--", linewidth=0.65)
    ax.set_xticks(x, CONTEXT_NAMES)
    ax.margins(y=0.2)
    ax.set_ylabel("Economia frente ao completo (%)")
    first = ax.legend(
        handles=[Patch(facecolor=c, label=l) for c, l in zip(CONTEXT_COLORS[1:], CONTEXT_LABELS[1:])],
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

    return TicketDiagnostics(diagnostic).matched_client_controls()


def panel_c(ax, chain, comparisons, amort, amort_cmp, diagnostic):
    ec, ml = controls(diagnostic)
    x = np.arange(3)
    for j, (d, color, label) in enumerate(
        zip((ec, ml), CONTEXT_COLORS[:2], ("Cliente ECDSA P-256", "Cliente ML-DSA-44"))
    ):
        c = d["connections"][0]
        ys = [
            d["certificates"]["client"]["der_bytes"],
            c["ticket_plaintext_session_der_bytes"],
            c["tickets_tx_bytes"][0],
        ]
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
    ax.margins(y=0.2)
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=7.3, loc="upper left", ncol=1)
    ax.set_title("Servidor e CA com ML-DSA-44 mantidos", fontsize=8, pad=6)


def panel_d(ax, chain, comparisons, amort, amort_cmp, diagnostic):
    x = np.arange(3)
    for j, (policy, color, label) in enumerate(zip(CONTEXT_POLICIES, CONTEXT_COLORS, CONTEXT_LABELS)):
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
    ax.set_xticks(x, ("1", "10", "100"))
    ax.set_xlabel("Limite de leituras por conexão")
    ax.set_ylabel("IPv4 por leitura (kB)")
    ax.margins(y=0.2)
    ax.set_ylim(bottom=0)
    ax.legend(
        ncol=3, fontsize=7.2, loc="upper right", columnspacing=0.6, handlelength=1
    )
    key_title(ax)


def panel_e(ax, chain, comparisons, amort, amort_cmp, diagnostic):
    for policy, color, label in zip(CONTEXT_POLICIES[1:], CONTEXT_COLORS[1:], CONTEXT_LABELS[1:]):
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
    ax.axhline(0, color="black", linestyle="--", linewidth=0.65)
    ax.set_xticks((0, 1, 2), ("1", "10", "100"))
    ax.set_xlabel("Limite de leituras por conexão")
    ax.set_ylabel("Economia frente ao completo (%)")
    ax.margins(y=0.2)
    ax.legend(ncol=2, fontsize=7.4, loc="upper right")
    key_title(ax)


def panel_f(ax, chain, comparisons, amort, amort_cmp, diagnostic):
    for recovery, offset, color, marker, label in (
        (False, -0.07, CONTEXT_COLORS[0], "s", "Sem falhas"),
        (True, 0.07, CONTEXT_COLORS[2], "o", "Recuperação"),
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
    ax.axhline(0, color="black", linestyle="--", linewidth=0.65)
    ax.set_xticks((0, 1, 2), ("1", "10", "100"))
    ax.set_xlabel("Limite de leituras por conexão")
    ax.set_ylabel("Diferença de tempo (ms/leitura)")
    ax.margins(y=0.2)
    ax.legend(ncol=2, fontsize=7.4, loc="lower right")
    key_title(ax)


CONTEXT_PANELS = (
    ("contexto_custos_sem_raiz", panel_a),
    ("contexto_economia_cadeias", panel_b),
    ("contexto_ticket_identidade", panel_c),
    ("contexto_leituras_custos", panel_d),
    ("contexto_leituras_recuperacao", panel_e),
    ("contexto_leituras_tempo", panel_f),
)
CONTEXT_CAPTIONS = (
    "(a) Custos sem transmitir a raiz.",
    "(b) Efeito da cadeia na economia.",
    "(c) Certificado, estado e ticket.",
    "(d) Custos sem falhas.",
    "(e) Economia na recuperação.",
    "(f) Tempo com contexto preservado.",
)


class ContextFigures:
    """Exporta seis painéis dos testes de contexto, sem executar novos experimentos.

    Configure once, then call ``run()`` from a notebook.
    """

    def __init__(
        self,
        *,
        data_dir,
        diagnostic,
        output,
    ):
        self.data_dir = Path(data_dir) if data_dir is not None else None
        self.diagnostic = Path(diagnostic) if diagnostic is not None else None
        self.output = Path(output) if output is not None else None

    def run(self):
        args = self
        args.output.mkdir(parents=True, exist_ok=True)
        paths = [args.data_dir / f for f in CONTEXT_FILES] + [args.diagnostic]
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
        for name, draw in CONTEXT_PANELS:
            (fig, ax) = plt.subplots(figsize=(4, 2.6), layout="constrained")
            style(ax)
            draw(ax, *data)
            save_formats(fig, args.output / name, dpi=280)
            plt.close(fig)
        fig, axes = plt.subplots(3, 2, figsize=(8.5, 10), layout="constrained")
        for (_, draw), ax, caption in zip(CONTEXT_PANELS, axes.flat, CONTEXT_CAPTIONS):
            style(ax)
            draw(ax, *data)
            ax.text(0, 1.18, caption, transform=ax.transAxes, fontsize=9,
                    ha="left", va="bottom")
        save_formats(fig, args.output / "figura_6_contexto", dpi=280)
        plt.close(fig)
        assert before == {p.name: sha(p) for p in paths}
        proof = {
            "status": "PASS",
            "inputs_sha256": before,
            "figure_source_sha256": sha(Path(__file__)),
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
            "panels": [name for (name, _) in CONTEXT_PANELS],
            "combined_figures": ["figura_6_contexto"],
        }
        (args.output / "proveniencia.json").write_text(
            json.dumps(proof, ensure_ascii=False, indent=2) + "\n"
        )
        return args.output
