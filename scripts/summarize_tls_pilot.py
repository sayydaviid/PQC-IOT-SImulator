"""Produce pilot statistics, a report and figures from verified TLS traces."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--docs", type=Path, default=ROOT / "docs")
    parser.add_argument("--figure", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((args.input / "manifest.json").read_text())
    for name, expected in manifest["source_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("pilot source changed: " + name)
    result_path = args.input / "results.json"
    result = json.loads(result_path.read_text())
    if result["status"] != "PASS":
        raise RuntimeError("cannot report a failed pilot as valid")
    cases = result["cases"]
    expected = (
        len(manifest["parameters"]["loss_pct"]) * manifest["parameters"]["blocks"] * 4
    )
    if len(cases) != expected:
        raise RuntimeError("incomplete pilot")
    args.docs.mkdir(parents=True, exist_ok=True)
    summary = []
    for loss in manifest["parameters"]["loss_pct"]:
        for deduplicate in (False, True):
            group = [
                c
                for c in cases
                if c["loss_pct"] == loss and c["deduplicate"] == deduplicate
            ]
            for mode in ("full", "resume"):
                selected = [c for c in group if c["mode"] == mode]
                wire = [
                    c["capture"]["iot_tx_ip_bytes"] + c["capture"]["iot_rx_ip_bytes"]
                    for c in selected
                ]
                retries = [
                    sum(
                        f["tx_payload"]
                        + f["rx_payload"]
                        - f["tx_unique_payload"]
                        - f["rx_unique_payload"]
                        for f in c["capture"]["tcp_flows"].values()
                    )
                    for c in selected
                ]
                kernel_retries = [
                    sum(r["tcp_retransmitted_segments"] for r in c["clients"])
                    + sum(
                        r["tcp_retransmitted_segments"] for r in c["server_connections"]
                    )
                    for c in selected
                ]
                acknowledgements = [
                    statistics.median(
                        r["first_reading_ack_ms"]
                        for r in c["clients"]
                        if r["acknowledged"]
                    )
                    for c in selected
                ]
                recoveries = [
                    statistics.median(
                        r["reading_recovery_ms"]
                        for r in c["clients"]
                        if r["acknowledged"]
                    )
                    for c in selected
                ]
                summary.append(
                    {
                        "loss_pct": loss,
                        "deduplicate": deduplicate,
                        "mode": mode,
                        "blocks": len(selected),
                        "median_ipv4_bytes": statistics.median(wire),
                        "min_ipv4_bytes": min(wire),
                        "max_ipv4_bytes": max(wire),
                        "median_observed_duplicate_payload_bytes": statistics.median(
                            retries
                        ),
                        "median_kernel_retransmitted_segments": statistics.median(
                            kernel_retries
                        ),
                        "median_of_block_ack_ms": statistics.median(acknowledgements),
                        "median_of_block_recovery_ms": statistics.median(recoveries),
                        "unique_readings": sum(
                            c["application"]["unique_readings"] for c in selected
                        ),
                        "duplicate_effects": sum(
                            c["application"]["duplicate_effects"] for c in selected
                        ),
                        "resumed_connections": sum(
                            r["reused"] for c in selected for r in c["clients"]
                        ),
                    }
                )
    with (args.docs / "resultado_tls_piloto.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    rows = "\n".join(
        f"| {s['loss_pct']:g}% | {'ativa' if s['deduplicate'] else 'desativada'} | {s['mode']} | {s['median_ipv4_bytes']:g} ({s['min_ipv4_bytes']}–{s['max_ipv4_bytes']}) | {s['median_kernel_retransmitted_segments']:g} | {s['median_of_block_ack_ms']:.1f} | {s['unique_readings']} | {s['duplicate_effects']} |"
        for s in summary
    )
    connections = [r for c in cases for r in c["clients"]]
    warm_full = [
        r["handshake_tx_tls_bytes"] + r["handshake_rx_tls_bytes"]
        for c in cases
        if c["mode"] == "full"
        for r in c["clients"]
        if r["boot"] == 1
    ]
    warm_resume = [
        r["handshake_tx_tls_bytes"] + r["handshake_rx_tls_bytes"]
        for c in cases
        if c["mode"] == "resume"
        for r in c["clients"]
        if r["boot"] == 1
    ]
    full_bytes, resume_bytes = (
        statistics.median(warm_full),
        statistics.median(warm_resume),
    )
    reduction = 100 * (1 - resume_bytes / full_bytes)
    without = sum(
        c["application"]["duplicate_effects"] for c in cases if not c["deduplicate"]
    )
    with_ledger = sum(
        c["application"]["duplicate_effects"] for c in cases if c["deduplicate"]
    )
    verified_cold = sum(
        not r["reused"]
        for c in cases
        if c["mode"] == "resume"
        for r in c["clients"]
        if r["boot"] == 2
    )
    restored = sum(
        r["reused"]
        for c in cases
        if c["mode"] == "resume"
        for r in c["clients"]
        if r["boot"] == 4
    )
    digest = hashlib.sha256(result_path.read_bytes()).hexdigest()
    report = f"""# Resultado: baseline TLS e piloto de recuperação

**Piloto concluído: {len(cases)} condições, {len(connections)} processos de cliente e {sum(c["application"]["unique_readings"] for c in cases)} entregas lógicas confirmadas.** São cinco blocos por configuração, com modos completo/retomado, deduplicação ativa/desativada e perdas de 0%, 1% e 5%. Cada ensaio tem cinco IDs de leitura e seis tentativas: uma confirmação perdida exige nova tentativa do mesmo ID. IDs/cargas são repetidos entre comparadores; as 300 entregas não são 300 amostras independentes de sensores.

## TLS efetivamente validado

{manifest["openssl"]}; commit `{manifest["openssl_commit"]}`. Todos os clientes negociaram TLS 1.3, `TLS_AES_256_GCM_SHA384` e `X25519MLKEM768`. No handshake completo houve CertificateVerify ML-DSA-44 nos dois sentidos (código 0x0904), cadeia verificada e nomes `gateway.local`/`iot_1` verificados. O grupo híbrido usa ML-KEM-768 e X25519; não é a mesma suíte da bancada ML-KEM-512. As comparações de TLS são feitas dentro do mesmo backend.

Sessões DER são salvas em checkpoints AES-GCM autenticados, vinculados ao nome do servidor e ao hash da CA. O servidor usa tickets stateful com cache em RAM; 0-RTT está desabilitado e o timeout configurado é 3600 s. Reiniciar o servidor remove o cache, preservando somente o ledger de leituras. Isto não representa um servidor com STEK/cache persistentemente restaurados.

O handshake quente completo teve mediana de **{full_bytes:g} bytes TLS**, contra **{resume_bytes:g}** na retomada: **{reduction:.2f}% de redução** até a conclusão de SSL_connect. Esta medida não inclui tickets pós-handshake, cabeçalhos IP ou todas as conexões do ensaio. A tabela abaixo inclui todo o tráfego IPv4 observado na interface do servidor. Não reutilizamos os 66,14% do protocolo JSON como resultado de TLS.

## Rede e aplicação

| Perda por direção | Deduplicação | Modo TLS | Bytes IPv4: mediana (mín–máx por bloco) | Segmentos retransmitidos pelo TCP: mediana | ACK após conexão TCP: mediana de medianas (ms) | Leituras lógicas | Efeitos duplicados |
|---|---|---|---:|---:|---:|---:|---:|
{rows}

O gateway reiniciado provocou **{verified_cold} handshakes completos** nas condições configuradas para retomar. A restauração de um checkpoint antigo, com gateway vivo, resultou em {restored} retomadas no boot 4. A aceitação de um ticket antigo não é, isoladamente, falha de nonce: houve key_share novo em cada conexão. As chaves de tráfego/IVs internos do OpenSSL não foram exportados; a auditoria verifica negociação e compartilhamentos públicos novos, não constitui observação direta de todos os pares chave/nonce do TLS.

Com ACK perdido, o controle sem deduplicação aplicou **{without} efeitos duplicados**, contra **{with_ledger}** com deduplicação durável. “Efeito” significa inserção de uma linha `(device,id,digest)` em SQLite; não significa execução exatamente uma vez de um atuador externo. Ambos os modos rastreiam IDs para a auditoria e rejeitam conteúdo conflitante; o controle desativa apenas a supressão de efeitos repetidos.

`WAL` e `synchronous=FULL` persistem a decisão antes do ACK. Os testes cobrem reinício, conteúdo conflitante e rollback de transação. Um controle separado demonstra que restaurar o banco inteiro desfaz a deduplicação; não alegamos resistência a rollback de todo o gateway.

## Auditoria e limites

Há captura PCAP em `h1-eth0` de cada condição. Os fluxos são identificados por sequência inicial TCP e hash do key_share público do ClientHello, porque portas podem ser reutilizadas. Exigimos cobertura contínua do handshake e do registro de leitura; em conexão confirmada todos os bytes TLS coincidem. Na conexão deliberadamente interrompida, um alerta terminal de 24 bytes pode não alcançar o receptor e é contabilizado separadamente. Retransmissões do TCP não são novas cifragens da aplicação.

As perdas netem são independentes nas duas direções do enlace cabeado AP–servidor, com 2 ms de atraso por direção; o sensor usa Wi-Fi emulado. Ordem dos quatro comparadores rotacionada por bloco. Os blocos compartilham a carga lógica, mas não a mesma sequência de perdas do kernel. O campo de ACK mede o intervalo após TCP conectado; `reading_recovery_ms` inclui execução do cliente e tentativas desde o disparo do controlador, no host. O CSV contém a mediana de recuperação por bloco, mas nenhum desses tempos é tempo de boot de ESP32.

Resultados descritivos de piloto, sem inferência de P95 robusto, energia ou desgaste de flash. São um sensor, uma implementação TLS e uma política de cache. A correção funcional não estabelece novidade científica nem prova formal de segurança.

Os segmentos retransmitidos são medidos por `TCP_INFO.tcpi_total_retrans` em ambos os endpoints antes de fechar os sockets. O CSV também registra payload duplicado observado no PCAP, que é somente um limite inferior: a captura após netem pode não observar a primeira cópia descartada. As duas métricas não são intercambiáveis.

O contador cobre também o encerramento TLS e as tentativas deliberadamente interrompidas. Retransmissões presentes em 0% de perda configurada não devem ser atribuídas ao netem. A amostragem ocorre antes do fechamento do socket e não inclui transmissões posteriores.

Dados: `{args.input}`. SHA-256 de results.json: `{digest}`. Os fontes de execução foram conferidos com o manifesto antes deste relatório. Dados agregados: [resultado_tls_piloto.csv](resultado_tls_piloto.csv).
"""
    if args.figure:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
        losses = sorted({s["loss_pct"] for s in summary})
        for i, mode in enumerate(("full", "resume")):
            values = [
                next(
                    s["median_ipv4_bytes"]
                    for s in summary
                    if s["loss_pct"] == loss and s["deduplicate"] and s["mode"] == mode
                )
                / 1000
                for loss in losses
            ]
            axes[0].bar(
                [x + (i - 0.5) * 0.35 for x in range(len(losses))],
                values,
                width=0.35,
                label=mode,
            )
        axes[0].set_xticks(range(len(losses)), [f"{x:g}%" for x in losses])
        axes[0].set_xlabel("Perda configurada por direção")
        axes[0].set_ylabel("Mediana de bytes IPv4 por ensaio (mil)")
        axes[0].legend()
        axes[1].bar(
            ["Desativada", "Durável"],
            [without, with_ledger],
            color=["#b76a29", "#227a65"],
        )
        axes[1].set_ylabel("Efeitos duplicados no conjunto de ensaios")
        axes[1].set_xlabel("Deduplicação de leitura")
        fig.suptitle("TLS PQC após reinício: tráfego e efeitos da confirmação perdida")
        path = args.docs / "figuras/tls_retomada.png"
        path.parent.mkdir(exist_ok=True)
        fig.savefig(path, dpi=180)
        plt.close(fig)
        report += (
            "\n![Tráfego TLS e duplicação da aplicação](figuras/tls_retomada.png)\n"
        )
    (args.docs / "resultado_tls_piloto.md").write_text(report)
    facts = {
        "cases": len(cases),
        "processes": len(connections),
        "full_bytes": full_bytes,
        "resume_bytes": resume_bytes,
        "warm_tls_reduction_pct": reduction,
        "duplicates_control": without,
        "duplicates_durable": with_ledger,
        "gateway_fallbacks": verified_cold,
        "summary": summary,
        "data_sha256": digest,
    }
    (args.docs / "tls_pilot_facts.json").write_text(json.dumps(facts, indent=2))
    print(json.dumps({k: v for k, v in facts.items() if k != "summary"}, indent=2))


if __name__ == "__main__":
    main()
