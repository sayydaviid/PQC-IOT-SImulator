"""Analyze complete, registered continuity campaigns without pseudo-replication."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.continuity_ticket_sizes import capture_hellos


def interval(values, seed=20261018, resamples=10000):
    """Percentile bootstrap of the median of block-level paired contrasts."""
    if len(values) < 2:
        raise ValueError("at least two independent blocks required")
    if any(v is None for v in values):
        return None, None, None
    rng = random.Random(seed)
    boot = sorted(st.median(rng.choices(values, k=len(values))) for _ in range(resamples))
    return st.median(values), boot[int(.025 * resamples)], boot[int(.975 * resamples)]


def metrics(c):
    capture = c["capture"]
    total = capture["iot_tx_ip_bytes"] + capture["iot_rx_ip_bytes"]
    clients = c["clients"]
    acknowledgements = [r for r in clients if r["acknowledged"]]
    negotiated = [r for r in clients if "version" in r]
    confirmed = c["confirmed_readings"]
    if len(acknowledgements) != confirmed:
        raise ValueError("confirmation count mismatch")
    rows_by_reading = defaultdict(list)
    for r in clients:
        rows_by_reading[r["reading"]].append(r)
    repeated_full = 0
    restart_ack_no_ticket = 0
    for rows in rows_by_reading.values():
        rows.sort(key=lambda x: x["retry"])
        if len(rows) >= 2 and "reused" in rows[1] and not rows[1]["reused"]:
            repeated_full += 1
            if rows[0]["restarted_before"] and "reused" in rows[0] and not rows[0]["reused"] and not rows[0]["resumable_session_saved"]:
                restart_ack_no_ticket += 1
    return dict(case_id=c["case_id"], block=c["block"], loss_pct=c["loss_pct"],
                restart_fraction=c["restart_fraction"], ack_fraction=c["ack_fraction"],
                profile=c["profile"], treatment=c["treatment"], deduplicate=c["deduplicate"],
                ipv4_bytes=total, ipv4_bytes_per_reading=total/c["readings"],
                ipv4_bytes_per_confirmed_reading=total/confirmed if confirmed else None,
                scheduled_readings=c["readings"], confirmed_readings=confirmed,
                fully_confirmed=confirmed == c["readings"],
                unplanned_unacknowledged=sum(r["unplanned_unacknowledged"] for r in clients),
                watchdog_censored_attempts=sum(r.get("watchdog_censored", False) for r in clients),
                sequence_ms=c["sequence_ms"], mean_sequence_ms_per_reading=c["sequence_ms"]/c["readings"],
                median_reading_recovery_ms=st.median(r["reading_recovery_ms"] for r in acknowledgements) if acknowledgements else None,
                median_ack_after_tcp_ms=st.median(r["first_reading_ack_ms"] for r in acknowledgements) if acknowledgements else None,
                full_handshakes=sum(not r["reused"] for r in negotiated),
                resumed_handshakes=sum(bool(r["reused"]) for r in negotiated),
                fallbacks=sum(r["session_offered"] and not r["reused"] for r in negotiated),
                ticket_absent_after_full_ack_loss=sum(not r["acknowledged"] and not r["reused"] and not r["resumable_session_saved"] for r in negotiated),
                retry_full_handshakes=repeated_full,
                restart_ack_retry_without_replacement_ticket=restart_ack_no_ticket,
                attempts=len(clients), unique_readings=c["unique_readings"], duplicate_effects=c["duplicate_effects"],
                kernel_retransmissions=sum(r.get("tcp_retransmitted_segments", 0) for r in clients+c["servers"]))


def median_or_missing(values):
    values = list(values)
    return st.median(values) if values and all(v is not None for v in values) else None


def write_csv(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def validate(path):
    manifest = json.loads((path / "manifest.json").read_text())
    data = json.loads((path / "results.json").read_text())
    if data["status"] != "PASS" or len(data["cases"]) != manifest["planned_cases"]:
        raise ValueError("incomplete campaign: " + str(path))
    expected = {(b, *cell) for b in range(manifest["blocks"]) for cell in manifest["design"]}
    seen = set()
    for c in data["cases"]:
        key = (c["block"], c["loss_pct"], c["restart_fraction"], c["ack_fraction"], c["profile"], c["treatment"], c["deduplicate"])
        if key in seen:
            raise ValueError("duplicated comparator/block")
        seen.add(key)
    if seen != expected:
        raise ValueError("matrix differs from registered design")
    return manifest, data["cases"]


def analyze(rows):
    # Preserve the complete block across all three treatments in each resample.
    groups = defaultdict(dict)
    for r in rows:
        key = (r["phase"], r["loss_pct"], r["restart_fraction"], r["ack_fraction"], r["profile"], r["deduplicate"])
        groups[key].setdefault(r["treatment"], {})[r["block"]] = r
    contrasts, aggregates, state = [], [], []
    for key, treatments in sorted(groups.items()):
        phase, loss, restart, ack, profile, dedup = key
        base = dict(phase=phase, loss_pct=loss, restart_fraction=restart, ack_fraction=ack, profile=profile, deduplicate=dedup)
        for treatment, blocks in sorted(treatments.items()):
            sample = list(blocks.values())
            aggregates.append(dict(**base, treatment=treatment, blocks=len(sample),
                median_ipv4_bytes_per_reading=st.median(r["ipv4_bytes_per_reading"] for r in sample),
                median_mean_sequence_ms_per_reading=st.median(r["mean_sequence_ms_per_reading"] for r in sample),
                median_reading_recovery_ms=median_or_missing(r["median_reading_recovery_ms"] for r in sample),
                median_full_handshakes=st.median(r["full_handshakes"] for r in sample),
                median_resumed_handshakes=st.median(r["resumed_handshakes"] for r in sample),
                median_retry_full_handshakes=st.median(r["retry_full_handshakes"] for r in sample),
                duplicate_effects=sum(r["duplicate_effects"] for r in sample),
                confirmed_readings=sum(r["confirmed_readings"] for r in sample),
                unconfirmed_readings=sum(r["scheduled_readings"]-r["confirmed_readings"] for r in sample),
                unplanned_unacknowledged=sum(r["unplanned_unacknowledged"] for r in sample)))
        reference = treatments["full"]
        for treatment in ("resume_volatile", "resume_preserved"):
            sample = treatments[treatment]
            if set(reference) != set(sample):
                raise ValueError("missing paired comparator")
            blocks = sorted(reference)
            saving = [100*(1-sample[b]["ipv4_bytes_per_confirmed_reading"]/reference[b]["ipv4_bytes_per_confirmed_reading"])
                      if sample[b]["confirmed_readings"] and reference[b]["confirmed_readings"] else None for b in blocks]
            delta = [sample[b]["mean_sequence_ms_per_reading"]-reference[b]["mean_sequence_ms_per_reading"]
                     if sample[b]["fully_confirmed"] and reference[b]["fully_confirmed"] else None for b in blocks]
            pct, low, high = interval(saving)
            dt, dt_low, dt_high = interval(delta)
            contrasts.append(dict(**base, treatment=treatment, blocks=len(blocks),
                                 median_paired_saving_pct=pct, bootstrap95_low=low, bootstrap95_high=high,
                                 all_deliveries_complete=all(sample[b]["fully_confirmed"] and reference[b]["fully_confirmed"] for b in blocks),
                                 median_paired_time_delta_ms=dt, time95_low=dt_low, time95_high=dt_high))
        volatile, preserved = treatments["resume_volatile"], treatments["resume_preserved"]
        blocks = sorted(reference)
        gain = [volatile[b]["ipv4_bytes_per_reading"]-preserved[b]["ipv4_bytes_per_reading"] for b in blocks]
        estimate, low, high = interval(gain)
        per_confirmed = [volatile[b]["ipv4_bytes_per_confirmed_reading"]-
                         preserved[b]["ipv4_bytes_per_confirmed_reading"]
                         if volatile[b]["confirmed_readings"] and preserved[b]["confirmed_readings"]
                         else None for b in blocks]
        ce, cl, ch = interval(per_confirmed)
        dt, dtlow, dthigh = interval([volatile[b]["mean_sequence_ms_per_reading"]-preserved[b]["mean_sequence_ms_per_reading"] if volatile[b]["fully_confirmed"] and preserved[b]["fully_confirmed"] else None for b in blocks])
        state.append(dict(**base, blocks=len(blocks), median_bytes_saved_by_preservation=estimate,
                          bootstrap95_low=low, bootstrap95_high=high,
                          median_saved_bytes_per_confirmed_reading=ce,
                          confirmed_bootstrap95_low=cl, confirmed_bootstrap95_high=ch,
                          median_ms_saved_by_preservation=dt, time95_low=dtlow, time95_high=dthigh))
    profiles = defaultdict(dict)
    for r in rows:
        key = (r["phase"], r["loss_pct"], r["restart_fraction"], r["ack_fraction"], r["treatment"], r["deduplicate"])
        profiles[key].setdefault(r["profile"], {})[r["block"]] = r
    migration = []
    for key, data in sorted(profiles.items()):
        phase, loss, restart, ack, treatment, dedup = key
        for source, target, label in (("classical", "hybrid", "key_exchange"), ("hybrid", "pqc", "authentication"), ("classical", "pqc", "whole_configuration")):
            if set(data[source]) != set(data[target]):
                raise ValueError("unmatched profile blocks")
            blocks = sorted(data[source])
            delta = [data[target][b]["ipv4_bytes_per_reading"]-data[source][b]["ipv4_bytes_per_reading"] for b in blocks]
            est, low, high = interval(delta)
            per_confirmed = [data[target][b]["ipv4_bytes_per_confirmed_reading"]-
                             data[source][b]["ipv4_bytes_per_confirmed_reading"]
                             if data[target][b]["confirmed_readings"] and data[source][b]["confirmed_readings"]
                             else None for b in blocks]
            ce, cl, ch = interval(per_confirmed)
            migration.append(dict(phase=phase, loss_pct=loss, restart_fraction=restart, ack_fraction=ack,
                                  treatment=treatment, deduplicate=dedup, contrast=label, blocks=len(blocks),
                                  median_added_bytes_per_reading=est, bootstrap95_low=low, bootstrap95_high=high,
                                  median_added_bytes_per_confirmed_reading=ce,
                                  confirmed_bootstrap95_low=cl, confirmed_bootstrap95_high=ch))
    return aggregates, contrasts, state, migration


def fault_interactions(rows):
    """Within-block departure from additive state-preservation benefits.

    Four corners are matched before bootstrapping: S(r,a)-S(r,0)-S(0,a)+S(0,0).
    S is volatile minus preserved IPv4 cost per confirmed reading. A positive
    value means the joint faults amplify the preservation benefit beyond the
    sum of their separate effects; it is not a security or novelty test.
    """
    index = {(r["profile"], r["deduplicate"], r["block"], r["restart_fraction"],
              r["ack_fraction"], r["treatment"]): r for r in rows
             if r["phase"] == "core" and r["loss_pct"] == 0}
    blocks = sorted({r["block"] for r in rows if r["phase"] == "core"})
    result = []
    for profile in ("classical", "hybrid", "pqc"):
        for dedup in (False, True):
            for restart in (.25, 1):
                for ack in (.25, 1):
                    contrasts = []
                    for block in blocks:
                        effects = []
                        for r, a in ((restart, ack), (restart, 0), (0, ack), (0, 0)):
                            try:
                                pair = [index[(profile, dedup, block, r, a, t)]
                                        for t in ("resume_volatile", "resume_preserved")]
                            except KeyError as exc:
                                raise ValueError("missing factorial interaction corner") from exc
                            effects.append(pair[0]["ipv4_bytes_per_confirmed_reading"] -
                                           pair[1]["ipv4_bytes_per_confirmed_reading"]
                                           if all(x["confirmed_readings"] for x in pair) else None)
                        contrasts.append(effects[0]-effects[1]-effects[2]+effects[3]
                                         if all(v is not None for v in effects) else None)
                    est, low, high = interval(contrasts)
                    result.append(dict(profile=profile, deduplicate=dedup,
                        restart_fraction=restart, ack_fraction=ack, blocks=len(blocks),
                        median_interaction_bytes_per_confirmed_reading=est,
                        bootstrap95_low=low, bootstrap95_high=high))
    return result


def figures(out, contrasts, aggregates):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = ("#315b8a", "#1b7d6b", "#d18a35")
    profiles = [("classical", "X25519 + ECDSA"), ("hybrid", "Híbrido + ECDSA"), ("pqc", "Híbrido + ML-DSA")]
    fig, axes = plt.subplots(2, 3, figsize=(11, 6.6), sharex=True, sharey=True, constrained_layout=True)
    for col, (profile, title) in enumerate(profiles):
        for row, (treatment, label) in enumerate((("resume_volatile", "Contexto perdido"), ("resume_preserved", "Contexto preservado"))):
            ax = axes[row,col]
            for color, ack in zip(colors, (0, .25, 1)):
                selected = sorted([r for r in contrasts if r["phase"] == "core" and r["profile"] == profile
                    and r["treatment"] == treatment and r["deduplicate"] and r["ack_fraction"] == ack and r["median_paired_saving_pct"] is not None], key=lambda r:r["restart_fraction"])
                ax.errorbar([100*r["restart_fraction"] for r in selected], [r["median_paired_saving_pct"] for r in selected],
                    yerr=[[r["median_paired_saving_pct"]-r["bootstrap95_low"] for r in selected],
                          [r["bootstrap95_high"]-r["median_paired_saving_pct"] for r in selected]],
                    marker="o", capsize=3, color=color, label=f"1ª confirmação perdida: {100*ack:g}%")
            ax.axhline(0, color="black", lw=.8, linestyle="--")
            ax.grid(alpha=.2)
            ax.set_title(title + "\n" + label)
            ax.set_xticks([0,25,100])
            if row == 1: ax.set_xlabel("Leituras elegíveis com reinício (%)")
            if col == 0: ax.set_ylabel("Economia por leitura confirmada (%)")
    axes[0,0].legend(fontsize=8)
    for ext in ("png", "svg", "pdf"):
        fig.savefig(out / ("economia_por_falhas."+ext), dpi=220)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), constrained_layout=True)
    labels = []
    for j, treatment in enumerate(("full", "resume_volatile", "resume_preserved")):
        selected = [r for r in aggregates if r["phase"] == "core" and r["profile"] == "pqc"
                    and r["deduplicate"] and r["restart_fraction"] == 1 and r["ack_fraction"] == 1 and r["treatment"] == treatment]
        r = selected[0]
        axes[0].bar(j, r["median_full_handshakes"], color=colors[0], label="Completo" if j == 0 else None)
        axes[0].bar(j, r["median_resumed_handshakes"], bottom=r["median_full_handshakes"], color=colors[1], label="Retomado" if j == 0 else None)
        axes[0].text(j, r["median_full_handshakes"]+r["median_resumed_handshakes"]+.25,
                     f'{r["median_full_handshakes"]+r["median_resumed_handshakes"]:g}', ha="center")
        labels.append({"full":"Sempre completo", "resume_volatile":"Contexto perdido", "resume_preserved":"Contexto preservado"}[treatment])
    axes[0].set_xticks(range(3), labels, rotation=12)
    axes[0].set_ylabel("Handshakes por sequência (mediana)")
    axes[0].set_ylim(0, 20)
    axes[0].set_yticks([0, 5, 10, 15, 20])
    axes[0].set_title("PQC: reinício e confirmação perdida em 100%")
    axes[0].legend(loc="upper center", ncol=2, fontsize=9)
    for color, (profile, title) in zip(colors, profiles):
        selected = [r for r in contrasts if r["phase"] == "core" and r["profile"] == profile and r["deduplicate"]]
        for r in selected:
            if r["median_paired_saving_pct"] is None or r["median_paired_time_delta_ms"] is None:
                continue
            axes[1].scatter(r["median_paired_saving_pct"], r["median_paired_time_delta_ms"], color=color,
                            marker="o" if r["treatment"] == "resume_volatile" else "^", alpha=.8)
        axes[1].scatter([], [], color=color, label=title)
    axes[1].axhline(0, color="black", lw=.8, linestyle="--")
    axes[1].axvline(0, color="black", lw=.8, linestyle="--")
    axes[1].set_xlabel("Economia de bytes IPv4 (%)")
    axes[1].set_ylabel("Diferença no tempo da sequência / 9 (ms)")
    axes[1].set_title("Diferenças pareadas frente ao completo")
    profile_legend = axes[1].legend(fontsize=8, loc="upper right")
    axes[1].add_artist(profile_legend)
    from matplotlib.lines import Line2D
    axes[1].legend(handles=[Line2D([], [], color="black", marker="o", linestyle="", label="Contexto perdido"),
                            Line2D([], [], color="black", marker="^", linestyle="", label="Contexto preservado")],
                   fontsize=8, loc="lower left")
    axes[1].grid(alpha=.2)
    for ext in ("png", "svg", "pdf"):
        fig.savefig(out / ("handshakes_e_tempo."+ext), dpi=220)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--core", type=Path, required=True)
    p.add_argument("--loss", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows, raw_cases, provenance, hellos = [], [], {}, []
    for phase, path in (("core", args.core), ("loss", args.loss)):
        manifest, cases = validate(path)
        if manifest["phase"] != phase:
            raise ValueError("wrong campaign phase")
        raw_cases.extend(cases)
        provenance[phase] = {"path":str(path), "blocks":manifest["blocks"], "cases":len(cases),
            "sha256": {name:hashlib.sha256((path/name).read_bytes()).hexdigest() for name in ("manifest.json", "results.json")}}
        for c in cases:
            r = metrics(c)
            r["phase"] = phase
            rows.append(r)
            public = capture_hellos(path/c["case_id"]/"traffic.pcap")
            for client in c["clients"]:
                matches = [h for h in public if h["client_tcp_port"] == client.get("client_tcp_port")
                           and (not client.get("client_share_sha256") or
                                h.get("client_share_sha256") == client["client_share_sha256"])]
                if len(matches) != 1:
                    if "version" in client:
                        raise ValueError("missing public ClientHello for established TLS connection")
                    continue
                h = matches[0]
                if "version" in client and bool(h["psk_identity_count"]) != client["session_offered"]:
                    raise ValueError("PSK offer differs from observed ClientHello")
                hellos.append(dict(phase=phase, case_id=c["case_id"], block=c["block"],
                    profile=c["profile"], treatment=c["treatment"], reading=client["reading"],
                    retry=client["retry"], acknowledged=client["acknowledged"],
                    reused=client.get("reused"), **h))
    capture_hashes = {}
    for phase, path in (("core", args.core), ("loss", args.loss)):
        for f in sorted(path.glob("*/traffic.pcap")):
            capture_hashes[f"{phase}/{f.parent.name}/traffic.pcap"] = hashlib.sha256(f.read_bytes()).hexdigest()
    if len(capture_hashes) != len(rows):
        raise ValueError("missing raw capture")
    (args.output/"capture_sha256.json").write_text(json.dumps(capture_hashes, indent=2))
    aggregates, contrasts, state, migration = analyze(rows)
    for filename, data in (("ensaios.csv", rows), ("medianas.csv", aggregates), ("contrastes_pareados.csv", contrasts),
                           ("preservacao_contexto.csv", state), ("custos_migracao.csv", migration)):
        write_csv(args.output/filename, data)
    write_csv(args.output/"interacoes_falhas.csv", fault_interactions(rows))
    write_csv(args.output/"clienthello_tamanhos.csv", hellos)
    figures(args.output, contrasts, aggregates)
    audit = dict(status="PASS", provenance=provenance,
                 analysis_python=sys.version,
                 analysis_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 ticket_sizes_source_sha256=hashlib.sha256(
                     Path(__file__).with_name("continuity_ticket_sizes.py").read_bytes()).hexdigest(),
                 analyzed_public_clienthellos=len(hellos),
                 cases=len(rows), logical_readings=sum(r["scheduled_readings"] for r in rows),
                 confirmed_logical_readings=sum(r["confirmed_readings"] for r in rows),
                 unconfirmed_logical_readings=sum(r["scheduled_readings"]-r["confirmed_readings"] for r in rows),
                 unplanned_unacknowledged=sum(r["unplanned_unacknowledged"] for r in rows),
                 client_attempts=sum(r["attempts"] for r in rows),
                 duplicate_effects_enabled=sum(r["duplicate_effects"] for r in rows if r["deduplicate"]),
                 duplicate_effects_disabled=sum(r["duplicate_effects"] for r in rows if not r["deduplicate"]),
                 eligible_restart_ack_intersections=sum(len(set(c["fault_schedule"]["restart_before"])&set(c["fault_schedule"]["drop_first_ack"])) for c in raw_cases),
                 restart_ack_retry_without_replacement_ticket=sum(r["restart_ack_retry_without_replacement_ticket"] for r in rows if r["treatment"] == "resume_volatile"),
                 inference="median of within-block paired contrasts; percentile bootstrap 10000, seed 20261018; exploratory per-cell intervals, not simultaneous; readings are not independent repetitions")
    (args.output/"audit.json").write_text(json.dumps(audit, indent=2))
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
