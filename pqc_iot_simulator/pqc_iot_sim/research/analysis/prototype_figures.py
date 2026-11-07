"""Render article panels from frozen, verified recovery campaigns (no new trials)."""

from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
POLICIES = [
    "checkpoint",
    "persist_each",
    "reserve_blocks",
    "full_pqc",
    "psk_resume",
    "pqc_resume",
]
LABELS = ["Checkpoint", "Por uso", "Blocos", "Completo", "PSK", "PSK+KEM"]
MODES = ["full_pqc", "psk_resume", "pqc_resume"]
NAMES = ["Completo", "PSK", "PSK+KEM"]
COLORS = ["#315a91", "#b56a29", "#227a65"]


def read_campaign(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    for file, digest in manifest["source_sha256"].items():
        if hashlib.sha256((ROOT / file).read_bytes()).hexdigest() != digest:
            raise RuntimeError("source differs from frozen campaign: " + file)
    raw = (directory / "results.json").read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


class PrototypeFigures:
    """Render article panels from frozen, verified recovery campaigns (no new trials).

    Configure once, then call ``run()`` from a notebook.
    """

    def __init__(self, *, security, transitions, output, tls=None):
        self.security = Path(security)
        self.transitions = Path(transitions)
        self.tls = Path(tls) if tls is not None else None
        self.output = Path(output)

    def run(self):
        args = self
        security, security_hash = read_campaign(args.security)
        transitions, transition_hash = read_campaign(args.transitions)
        tls, tls_hash = read_campaign(args.tls) if args.tls else (None, None)
        if (
            security["verdict"]["status"] != "SUPPORTED_IN_TESTED_MODEL"
            or transitions["assessment"]["status"] != "PASS"
        ):
            raise RuntimeError("failed experiments cannot support figures")
        if len(security["cases"]) != 240 or len(transitions["cases"]) != 330:
            raise ValueError(
                "prototype figures require the complete ten-repetition design"
            )
        if tls is not None and (tls["status"] != "PASS" or len(tls["cases"]) != 60):
            raise ValueError("legacy TLS figures require the complete 60-case pilot")
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.rcParams.update(
            {
                "font.size": 9,
                "axes.spines.top": False,
                "axes.spines.right": False,
                "svg.fonttype": "none",
                "savefig.dpi": 300,
            }
        )
        args.output.mkdir(parents=True, exist_ok=True)
        panels = []

        def canvas():
            (fig, ax) = plt.subplots(figsize=(4.6, 3.1), layout="constrained")
            ax.grid(axis="y", alpha=0.2)
            ax.set_axisbelow(True)
            return (fig, ax)

        def save(fig, name):
            for suffix in ("png", "svg"):
                fig.savefig(args.output / (name + "." + suffix))
            plt.close(fig)
            panels.append(name)

        def bars(name, labels, values, ylabel, colors=None, rotate=0):
            (fig, ax) = canvas()
            ax.bar(range(len(values)), values, color=colors or COLORS[0], width=0.65)
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
            for policy in POLICIES:
                rows = [
                    r
                    for r in security["cases"]
                    if r["fault"] == fault and r["policy"] == policy
                ]
                assert len(rows) == 10
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
                "Escritas na fase estável de 8 leituras",
            ),
        ]:
            bars(
                name,
                LABELS,
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
            for mode in MODES:
                selected = [
                    r
                    for r in transitions["cases"]
                    if r["scenario"] == scenario and r["policy"] == mode
                ]
                assert len(selected) == 10
                row[mode] = {
                    "bytes": statistics.median(
                        (r["total_handshake_bytes"] for r in selected)
                    ),
                    "fallbacks": sum((r["full_fallback"] for r in selected)),
                    "duplicates": sum((r["application_duplicates"] for r in selected)),
                }
            transition_summary.append(row)
        (fig, ax) = canvas()
        for mode, label, color in zip(MODES, NAMES, COLORS):
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
        (fig, ax) = canvas()
        indices = [0, 9, 10]
        values = [savings[i] for i in indices]
        ax.bar(range(3), values, color=[COLORS[2], COLORS[2], COLORS[1]])
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
            NAMES,
            [lost[m]["duplicates"] for m in MODES],
            "Efeitos duplicados com ACK perdido",
            COLORS,
        )
        tls_summary, warm, duplicates = [], {}, []
        if tls is not None:
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
                [COLORS[0], COLORS[2]],
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
                        (COLORS[0], COLORS[2]),
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
                "Efeitos duplicados no conjunto de ensaios",
                [COLORS[1], COLORS[2]],
            )
        facts = {
            "source_sha256": {
                "security": security_hash,
                "transitions": transition_hash,
                "tls": tls_hash,
            },
            "security": security_summary,
            "transitions": transition_summary,
            "scenario_labels": scenario_labels,
            "tls": tls_summary,
            "tls_warm_bytes": warm,
            "tls_duplicates": duplicates,
            "panels": panels,
            "statistics": "Ten prototype repetitions; optional legacy TLS pilot uses five blocks; descriptive medians.",
        }
        (args.output / "dados_figuras.json").write_text(
            json.dumps(facts, indent=2, ensure_ascii=False)
        )
        print(
            json.dumps(
                {
                    "panels": len(panels),
                    "warm_tls_bytes": warm,
                    "duplicate_effects": duplicates,
                    "sources": facts["source_sha256"],
                },
                indent=2,
            )
        )
        return args.output
