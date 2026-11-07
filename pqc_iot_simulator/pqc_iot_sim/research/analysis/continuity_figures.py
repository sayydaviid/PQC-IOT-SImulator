"""Export six article panels from the completed continuity analysis, without reruns."""

from __future__ import annotations

import csv
import hashlib
import json
import statistics as st
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "docs/resultados_continuidade_20261021_v5"
OUT = ROOT / "docs/figuras/continuidade/artigo"
DELIVERY = ROOT / "output/pdf/avaliacao_retomada_20261023"
PROFILES = ("classical", "hybrid", "pqc")
PROFILE_NAMES = ("Clássico", "Híbrido", "PQC")
TREATMENTS = ("full", "resume_volatile", "resume_preserved")
COLORS = ("#315a91", "#b56a29", "#227a65")
FILES = ("ensaios.csv", "contrastes_pareados.csv", "clienthello_tamanhos.csv")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(directory, name):
    with (directory / name).open() as handle:
        return list(csv.DictReader(handle))


def select(rows, **where):
    return [r for r in rows if all(r[k] == str(v) for k, v in where.items())]


def number(row, key):
    return float(row[key])


def style(ax):
    ax.grid(axis="y", alpha=0.18, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)


def panel_a(ax, rows, contrasts, hellos):
    x = np.arange(3)
    for j, (treatment, color, label) in enumerate(
        zip(TREATMENTS, COLORS, ("Completo", "Perdido", "Preservado"))
    ):
        values = []
        for profile in PROFILES:
            chosen = select(
                rows,
                phase="core",
                profile=profile,
                treatment=treatment,
                deduplicate=True,
                restart_fraction="1",
                ack_fraction="1",
            )
            assert len(chosen) == 10
            values.append(
                st.median(number(r, "ipv4_bytes_per_confirmed_reading") for r in chosen)
                / 1000
            )
        ax.bar(x + (j - 1) * 0.25, values, 0.23, color=color, label=label)
    ax.set_xticks(x, PROFILE_NAMES)
    ax.set_ylabel("IPv4 por leitura (kB)")
    ax.set_ylim(0, 80)
    ax.legend(ncol=3, fontsize=7.6, loc="upper left", columnspacing=0.7, handlelength=1)


def panel_b(ax, rows, contrasts, hellos):
    for treatment, color in zip(TREATMENTS[1:], COLORS[1:]):
        for ack, line, marker in (
            ("0", ":", "s"),
            ("0.25", "--", "^"),
            ("1", "-", "o"),
        ):
            chosen = sorted(
                select(
                    contrasts,
                    phase="core",
                    profile="pqc",
                    treatment=treatment,
                    deduplicate=True,
                    ack_fraction=ack,
                ),
                key=lambda r: number(r, "restart_fraction"),
            )
            assert len(chosen) == 3
            y = [number(r, "median_paired_saving_pct") for r in chosen]
            ax.errorbar(
                [100 * number(r, "restart_fraction") for r in chosen],
                y,
                yerr=[
                    [v - number(r, "bootstrap95_low") for v, r in zip(y, chosen)],
                    [number(r, "bootstrap95_high") - v for v, r in zip(y, chosen)],
                ],
                color=color,
                linestyle=line,
                marker=marker,
                markersize=3.2,
                linewidth=1.2,
                capsize=2,
            )
    ax.axhline(0, color="black", linestyle="--", linewidth=0.7)
    ax.set_xticks((0, 25, 100))
    ax.set_xlim(-4, 104)
    ax.set_ylim(-25, 92)
    ax.set_xlabel("Leituras com reinício (%)")
    ax.set_ylabel("Economia IPv4 (%)")
    first = ax.legend(
        handles=[
            Line2D([], [], color=c, label=l)
            for c, l in zip(COLORS[1:], ("Perdido", "Preservado"))
        ],
        ncol=2,
        fontsize=7.6,
        loc="upper center",
        columnspacing=0.8,
    )
    ax.add_artist(first)
    ax.legend(
        handles=[
            Line2D([], [], color="black", linestyle=s, marker=m, markersize=3, label=l)
            for s, m, l in ((":", "s", "0%"), ("--", "^", "25%"), ("-", "o", "100%"))
        ],
        title="Confirmações perdidas",
        title_fontsize=7.6,
        fontsize=7.6,
        ncol=3,
        loc="lower left",
        columnspacing=0.7,
        handlelength=1.5,
    )


def panel_c(ax, rows, contrasts, hellos):
    for x, (phase, loss) in enumerate((("core", "0"), ("loss", "1"), ("loss", "5"))):
        chosen = select(
            contrasts,
            phase=phase,
            loss_pct=loss,
            profile="pqc",
            treatment="resume_preserved",
            deduplicate=True,
            restart_fraction="0.25",
            ack_fraction="0.25",
        )
        assert len(chosen) == 1
        r = chosen[0]
        value = number(r, "median_paired_time_delta_ms")
        ax.errorbar(
            x,
            value,
            yerr=[
                [value - number(r, "time95_low")],
                [number(r, "time95_high") - value],
            ],
            fmt="o",
            color=COLORS[2],
            capsize=4,
            markersize=5,
        )
    ax.axhline(0, color="black", linestyle="--", linewidth=0.8)
    ax.set_xticks((0, 1, 2), ("0%", "1%", "5%"))
    ax.set_xlim(-0.45, 2.45)
    ax.set_xlabel("Perda de pacotes por direção")
    ax.set_ylabel("Diferença de tempo (ms/leitura)")


def panel_d(ax, rows, contrasts, hellos):
    for j, treatment in enumerate(TREATMENTS):
        chosen = select(
            rows,
            phase="core",
            profile="pqc",
            treatment=treatment,
            deduplicate=True,
            restart_fraction="1",
            ack_fraction="1",
        )
        assert len(chosen) == 10
        full = st.median(number(r, "full_handshakes") for r in chosen)
        resumed = st.median(number(r, "resumed_handshakes") for r in chosen)
        assert (full, resumed) == (
            (1, 16) if treatment == "resume_preserved" else (17, 0)
        )
        ax.bar(
            j, full, width=0.6, color=COLORS[0], label="Completo" if j == 0 else None
        )
        ax.bar(
            j,
            resumed,
            bottom=full,
            width=0.6,
            color=COLORS[2],
            label="Retomado" if j == 0 else None,
        )
        if full >= 3:
            ax.text(
                j,
                full / 2,
                f"{full:g}",
                ha="center",
                va="center",
                color="white",
                fontsize=10,
            )
        elif full:
            ax.annotate(
                f"{full:g}",
                xy=(j, full / 2),
                xytext=(j - 0.55, 1.5),
                ha="center",
                va="center",
                fontsize=9,
                arrowprops={"arrowstyle": "-", "color": "black", "lw": 0.7},
            )
        if resumed:
            ax.text(
                j,
                full + resumed / 2,
                f"{resumed:g}",
                ha="center",
                va="center",
                color="white",
                fontsize=10,
            )
    ax.set_xticks((0, 1, 2), ("Completo", "Perdido", "Preservado"))
    ax.set_ylim(0, 22)
    ax.set_yticks((0, 5, 10, 15, 20))
    ax.set_ylabel("Handshakes por sequência")
    ax.legend(ncol=2, fontsize=8.5, loc="upper center")


def panel_e(ax, rows, contrasts, hellos):
    for i, profile in enumerate(PROFILES):
        values = [
            number(r, "psk_identity_total_bytes")
            for r in hellos
            if r["profile"] == profile and int(r["psk_identity_count"]) > 0
        ]
        assert values
        middle, low, high = st.median(values), min(values), max(values)
        assert (low, high) == (
            (640, 640)
            if profile == "classical"
            else (640, 656)
            if profile == "hybrid"
            else (4240, 4240)
        )
        ax.bar(
            i,
            middle,
            width=0.6,
            color=COLORS[0],
            yerr=[[middle - low], [high - middle]],
            capsize=4,
        )
        label = f"{int(low):,}".replace(",", ".")
        if high != low:
            label = f"{int(low)}-{int(high)}"
        ax.text(i, high + 110, label, ha="center", va="bottom", fontsize=9)
    ax.set_xticks((0, 1, 2), PROFILE_NAMES)
    ax.set_ylabel("Identidade PSK (bytes)")
    ax.set_ylim(0, 5100)


def panel_f(ax, rows, contrasts, hellos):
    for i, (dedup, color, label) in enumerate(
        ((False, COLORS[1], "Sem supressão"), (True, COLORS[2], "Com supressão"))
    ):
        chosen = select(rows, phase="core", deduplicate=dedup)
        assert len(chosen) == 810
        assert sum(int(r["confirmed_readings"]) for r in chosen) == 7290
        value = sum(int(r["duplicate_effects"]) for r in chosen)
        assert value == (0 if dedup else 2700)
        ax.bar(i, value, width=0.55, color=color)
        ax.text(i, value + 85, f"{value:,}".replace(",", "."), ha="center", fontsize=10)
    ax.set_xticks((0, 1), ("Sem supressão", "Com supressão"))
    ax.set_ylabel("Efeitos duplicados no banco")
    ax.set_ylim(0, 3300)


PANELS = (
    ("tls_custos", "(a) Bytes por leitura: falhas em 100%", panel_a),
    ("tls_economia", "(b) PQC: política e frequência de falhas", panel_b),
    ("tls_tempo", "(c) PQC preservado: falhas em 25%", panel_c),
    ("tls_handshakes", "(d) PQC: falhas em 100%", panel_d),
    ("tls_identidade", "(e) Identidade de retomada", panel_e),
    ("tls_duplicacoes", "(f) Deduplicação: matriz principal", panel_f),
)


class ContinuityFigures:
    """Export six article panels from the completed continuity analysis, without reruns.

    Configure once, then call ``run()`` from a notebook.
    """

    def __init__(
        self, *, data_dir=SOURCE, output=ROOT / "results/pesquisa/figuras_continuidade"
    ):
        self.data_dir = Path(data_dir)
        self.output = Path(output)

    def run(self):
        SOURCE, OUT, DELIVERY = self.data_dir, self.output, self.output
        before = {name: digest(SOURCE / name) for name in FILES}
        (rows, contrasts, hellos) = (read(SOURCE, name) for name in FILES)
        blocks = len({int(r["block"]) for r in rows})
        if blocks != 10:
            raise ValueError("continuity article panels require ten blocks")
        assert len(rows) == 1800
        assert len(hellos) == sum(int(r["attempts"]) for r in rows)
        confirmed = sum(int(r["confirmed_readings"]) for r in rows)
        assert all((r["fully_confirmed"] == "True" for r in rows))
        OUT.mkdir(parents=True, exist_ok=True)
        DELIVERY.mkdir(parents=True, exist_ok=True)
        plt.rcParams.update(
            {
                "font.family": "DejaVu Sans",
                "font.size": 9.5,
                "axes.labelsize": 9.5,
                "xtick.labelsize": 9,
                "ytick.labelsize": 9,
                "pdf.fonttype": 42,
                "svg.fonttype": "none",
            }
        )
        for name, title, draw in PANELS:
            (fig, ax) = plt.subplots(figsize=(4.0, 2.65), layout="constrained")
            style(ax)
            draw(ax, rows, contrasts, hellos)
            for suffix in ("pdf", "svg", "png"):
                fig.savefig(OUT / f"{name}.{suffix}", dpi=250)
            plt.close(fig)
        (fig, axes) = plt.subplots(3, 2, figsize=(8.1, 8.8), layout="constrained")
        for ax, (_, title, draw) in zip(axes.flat, PANELS):
            style(ax)
            draw(ax, rows, contrasts, hellos)
            ax.set_title(title, fontsize=10, pad=9, loc="left")
        for suffix in ("pdf", "png"):
            fig.savefig(DELIVERY / f"figura_6_recuperacao_tls.{suffix}", dpi=220)
        plt.close(fig)
        assert before == {name: digest(SOURCE / name) for name in FILES}
        (OUT / "proveniencia.json").write_text(
            json.dumps(
                {
                    "source_directory": str(SOURCE),
                    "source_sha256": before,
                    "exporter_sha256": digest(Path(__file__)),
                    "cases": len(rows),
                    "confirmed_readings": confirmed,
                    "clienthellos": len(hellos),
                    "panel_a": "Median IPv4 bytes/confirmed reading, ten blocks, core 100%/100%, dedup on.",
                    "panel_b": "Existing paired medians and exploratory 95% bootstrap, PQC, core, dedup on.",
                    "panel_c": "Existing paired time contrasts, complete sequence/9, PQC preserved, 25%/25%.",
                    "panel_d": "Median handshakes per sequence, ten blocks, PQC 100%/100%, dedup on.",
                    "panel_e": "Median and observed min/max of public PSK identity lengths, all ClientHello with PSK.",
                    "panel_f": "Totals in core, 810 cases and 7290 logical readings per dedup mode.",
                    "limitations": "Server certificate chain includes the root CA; no optimized chain measured.",
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        print(f"Exported six panels to {OUT}; source hashes unchanged.")
        return self.output
