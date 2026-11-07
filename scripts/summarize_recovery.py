"""Build an auditable Portuguese report from security and complete PCAP results."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--security", type=Path, required=True)
    parser.add_argument("--network", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/resultado_hipotese_retomada.md"
    )
    parser.add_argument("--figure", action="store_true")
    args = parser.parse_args()
    for directory in (args.security, args.network):
        manifest = json.loads((directory / "manifest.json").read_text())
        for name, expected in manifest["source_sha256"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise RuntimeError("source differs from experiment: " + name)
    security_path, network_path = (
        args.security / "results.json",
        args.network / "network_results.json",
    )
    security, network = (
        json.loads(security_path.read_text()),
        json.loads(network_path.read_text()),
    )
    if (
        security["verdict"]["status"] != "SUPPORTED_IN_TESTED_MODEL"
        or network["status"] != "PASS"
    ):
        raise RuntimeError("failed campaign cannot be reported as supported")
    # Reject the early integration captures that had only a bidirectional check.
    for case in network["cases"]:
        for boot in case["boots_results"]:
            flow = case["tcp_flows"][str(boot["client_tcp_port"])]
            if (
                flow["tx_unique_payload"] != boot["total_framed_tx_bytes"]
                or flow["rx_unique_payload"] != boot["total_framed_rx_bytes"]
            ):
                raise RuntimeError("incomplete per-process packet capture")
    parameters = json.loads((args.security / "manifest.json").read_text())["parameters"]
    repetitions, messages, block_size = (
        parameters["repetitions"],
        parameters["messages"],
        parameters["block_size"],
    )
    boots_per_policy = network["cases"][0]["boots"]
    torn = [c for c in security["cases"] if c["fault"] == "torn_checkpoint"]
    fallbacks = sum(c["full_handshake_fallback"] for c in torn)
    groups = defaultdict(list)
    for case in security["cases"]:
        groups[(case["policy"], case["fault"])].append(case)
    summary = []
    for (policy, fault), cases in groups.items():
        summary.append(
            {
                "policy": policy,
                "fault": fault,
                "traces": len(cases),
                "nonce_reuses": sum(c["reused_key_nonce"] for c in cases),
                "plaintext_recoveries": sum(
                    c["known_plaintext_recoveries"] for c in cases
                ),
                "accepted_records": sum(c["accepted_after_restart"] for c in cases),
                "fallbacks": sum(c["full_handshake_fallback"] for c in cases),
                "median_restart_bytes": statistics.median(
                    c["restart_framed_bytes"] for c in cases
                ),
                "steady_writes_per_boot": statistics.median(
                    c["steady_state_writes"] for c in cases
                ),
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = args.output.with_suffix(".csv")
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    policies = [c["policy"] for c in summary if c["fault"] == "client_storage_rollback"]
    rows = []
    for policy in policies:
        rollback, power = (
            groups[(policy, "client_storage_rollback")],
            groups[(policy, "power_loss")],
        )
        rows.append(
            f"| `{policy}` | {sum(c['reused_key_nonce'] for c in power)} | {sum(c['reused_key_nonce'] for c in rollback)} | {sum(c['known_plaintext_recoveries'] for c in rollback)} | {sum(c['accepted_after_restart'] for c in rollback)} | {rollback[0]['steady_state_writes']} |"
        )
    wire_rows = []
    medians = {}
    for case in network["cases"]:
        boots = case["boots_results"]
        median = statistics.median(b["handshake_framed_bytes"] for b in boots[1:])
        medians[case["policy"]] = median
        wire_rows.append(
            f"| `{case['policy']}` | {case['boots']} | {case['client_storage_rollbacks']} | {median:g} | {case['iot_tx_ip_bytes'] + case['iot_rx_ip_bytes']} |"
        )
    reduction = 100 * (1 - medians["pqc_resume"] / medians["full_pqc"])
    checks = security["security_checks"]
    boot_count = sum(c["boots"] for c in network["cases"])
    text = f"""# Resultado: retomada de sessões PQC após reinício

**A hipótese passou nos cenários implementados; a novidade para publicação ainda precisa ser estabelecida.** A retomada autenticada com segredo persistente e ML-KEM novo apresentou zero reutilizações de chave/nonce e {reduction:.2f}% menos bytes de handshake que o estabelecimento completo deste protocolo experimental.

## 1. Pergunta e decisão

Pergunta: quais garantias dependem de conservar o contador, de conservar uma autoridade de estado ou de estabelecer um segredo assimétrico novo após o reinício?

Mantemos o tema para desenvolver o artigo. O resultado sustenta uma avaliação de falhas e custos. Ele não demonstra um protocolo criptográfico inédito, segurança formal, interoperabilidade TLS ou vantagem energética em ESP32.

## 2. Experimentos e critérios

Foram executados **{len(security["cases"])} traços**: seis políticas, quatro falhas, {repetitions} repetições independentes com criptografia real. Cada traço transmite {messages} leituras antes e {messages} depois do reinício. O observador verifica as cifragens antes da decisão do receptor. Checkpoints são arquivos cifrados/autenticados reais, restaurados do disco; a reserva do contador usa fsync e rename.

Também passaram **{len(checks)}/{len(checks)} verificações funcionais de segurança**, incluindo controles negativos deliberadamente vulneráveis: adulteração de mensagens e limites, replay, identidades não autorizadas, confirmação de chave, expiração, orçamento no gateway, contador esgotado, crash após reserva, perda de estado do gateway e divulgação tardia do PSK. Passar o controle negativo significa demonstrar a falha esperada, não atribuir segurança à política vulnerável.

O Mininet-WiFi executou **{boot_count} processos novos de cliente**, uma leitura validada pelo servidor por processo, e restauração do primeiro checkpoint válido nas {boots_per_policy - 1} reinicializações de cada política. Todas as conexões têm os bytes únicos enviados/recebidos confirmados no PCAP por porta e sequência TCP; retransmissões não contam duas vezes nessa verificação. O cliente autentica a confirmação da leitura.

Os critérios foram registrados em manifestos antes da execução: testemunho de falha no controle; unicidade e entrega nas políticas com chave nova; persistência segura com journal preservado e vulnerável quando ele é restaurado; verificações funcionais aprovadas; retomada ML-KEM menor que handshake completo. Todos passaram. **Repetições cobrem novas execuções criptográficas; não são uma prova estatística contra todo atacante.**

## 3. Falhas de estado

Cada célula acumula {repetitions} traços de {messages} mensagens após reinício ({repetitions * messages} mensagens). “Escritas” conta a fase estável de {messages} leituras; exclui provisionamento, inicialização e checkpoint do boot. O orçamento de mensagens aceitas permanece no gateway.

| Política | Reusos: queda de energia | Reusos: rollback completo | Textos recuperados no rollback | Leituras aceitas no rollback | Escritas na fase estável |
|---|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

Checkpoint antigo provocou repetição de chave/nonce em AES-GCM. Com uma leitura sintética conhecida, a relação entre os dois ciphertexts recuperou integralmente a outra leitura. O gateway rejeitou esses registros repetidos; a rejeição não impediu o vazamento já presente no enlace.

Persistir antes de cada uso e reservar blocos evitaram a falha quando o journal durável permaneceu atual. Restaurar também esse journal reproduziu a falha. Com blocos de {block_size} e {messages} mensagens usadas, a reinicialização salta {block_size - messages} posições restantes. Essas políticas não fornecem proteção contra rollback integral de memória não volátil sem uma âncora externa.

Checkpoints truncados acionaram estabelecimento completo: {fallbacks} fallbacks nos {len(torn)} traços dessa falha. As políticas de retomada persistem somente o segredo de retomada; as antigas chaves de tráfego não são gravadas.

## 4. Custo de retomada na rede

| Política | Processos/leituras entregues | Restaurações de snapshot | Mediana de bytes por handshake após bootstrap | Bytes IPv4 capturados, ambas as direções |
|---|---:|---:|---:|---:|
{chr(10).join(wire_rows)}

Os {medians["pqc_resume"]:g} bytes da retomada ML-KEM são {reduction:.2f}% menores que os {medians["full_pqc"]:g} bytes do handshake completo. Esta é a soma de quatro mensagens JSON/Base64 e seus prefixos de tamanho; não inclui cabeçalhos TCP/IP. A coluna IPv4 inclui os {boots_per_policy} boots, o bootstrap completo, leituras, ACKs e eventuais retransmissões. O bootstrap é excluído apenas da mediana de retomada.

Ambos os comparadores usam ML-KEM-512 efêmero; o completo autentica os dois participantes com ML-DSA-44 e chaves públicas previamente fixadas. A retomada usa o segredo autenticado no bootstrap, com HMAC, e conserva ML-KEM novo. O provisionamento das identidades e o transporte de certificados ficam fora deste modelo para ambos.

Retomada somente com PSK tem garantia distinta: o teste recuperou a leitura passada ao revelar posteriormente o PSK retido. Na variante com ML-KEM novo, a tentativa de decifrar somente com esse PSK falhou. Isso é um teste funcional de separação de chaves, não prova de forward secrecy. Comprometimento do PSK antes do handshake permite impersonação ativa; perda de estado do gateway exige autenticação completa.

## 5. Limites e relação com trabalhos existentes

A autoridade do gateway e a entropia fresca permanecem fora do rollback do cliente. O controle que repete a entropia do cliente e reproduz o handshake antigo regenera a chave na política PSK: a condição de aleatoriedade é essencial. Não foram avaliados rollback simultâneo de gateway e cliente, extração de todas as credenciais, canais laterais, garantia física de apagamento em Python, consumo real de flash, perdas em rajadas ou implantação em ESP32.

AES-GCM exige unicidade de IV por chave ([NIST SP 800-38D](https://csrc.nist.gov/pubs/sp/800/38/d/final)). Recuperação de contexto e persistência de sequências já aparecem em OSCORE ([RFC 8613, seção 7.5 e apêndice B](https://datatracker.ietf.org/doc/html/rfc8613#section-7.5)). TLS distingue retomada PSK pura e com segredo assimétrico novo ([RFC 9846](https://datatracker.ietf.org/doc/html/rfc9846#section-2.2)). Portanto, reservar contadores ou reduzir bytes via retomada não constitui novidade por si só.

O recorte candidato a WQuNets é a avaliação reproduzível das condições de retomada pós-quântica diante de reinício, rollback e divulgação de estado, com custos registrados e controles negativos. A comparação com implementações de protocolos padronizados e a revisão aprofundada de trabalhos relacionados permanecem necessárias antes de sustentar a contribuição de publicação.

## 6. Evidências e reprodução

Campanha de segurança: `{args.security.relative_to(ROOT) if args.security.is_absolute() else args.security}`.

Verificação de rede válida: `{args.network.relative_to(ROOT) if args.network.is_absolute() else args.network}`.

SHA-256 dos resultados: segurança `{hashlib.sha256(security_path.read_bytes()).hexdigest()}`; rede `{hashlib.sha256(network_path.read_bytes()).hexdigest()}`. Os manifestos contêm hashes dos fontes efetivamente executados; este relatório exige que eles coincidam com a árvore atual. Dados agregados: [{csv_path.name}]({csv_path.name}).

As capturas exploratórias anteriores, sem auditoria de todos os bytes por conexão, são excluídas dos números deste relatório. As credenciais e snapshots usados nos testes são temporários e apagados; os resultados públicos não contêm chaves ou leituras em claro.

Comandos e modelo de ameaça: [experimento_retomada.md](experimento_retomada.md).
"""
    if args.figure:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
        positions = list(range(len(policies)))
        for offset, fault, label in (
            (-0.18, "power_loss", "Queda de energia"),
            (0.18, "client_storage_rollback", "Rollback de todo o estado"),
        ):
            heights = [
                statistics.mean(c["reused_key_nonce"] for c in groups[(p, fault)])
                for p in policies
            ]
            axes[0].bar(
                [x + offset for x in positions], heights, width=0.36, label=label
            )
        axes[0].set_xticks(positions, policies, rotation=35, ha="right")
        axes[0].set_ylabel("Reutilizações de chave/nonce por traço")
        axes[0].set_title("O journal resolve crash; rollback o desfaz")
        axes[0].legend(fontsize=8)
        axes[0].set_ylim(0, 10)
        axes[1].bar(
            list(medians),
            list(medians.values()),
            color=["#666666", "#c87828", "#227a65"],
        )
        axes[1].set_ylabel("Bytes das mensagens e enquadramento")
        axes[1].set_title("Handshake após bootstrap (TCP real)")
        for x, value in enumerate(medians.values()):
            axes[1].text(x, value + 100, f"{value:g}", ha="center")
        axes[1].set_ylim(0, 10500)
        fig.suptitle("Retomada PQC: falhas de estado e bytes do protocolo experimental")
        figure = args.output.parent / "figuras/retomada.png"
        figure.parent.mkdir(exist_ok=True)
        fig.savefig(figure, dpi=180)
        plt.close(fig)
        text += "\n![Falhas de estado e bytes de retomada](figuras/retomada.png)\n\nPSK puro e ML-KEM novo possuem garantias distintas; os bytes não representam TLS interoperável.\n"
    args.output.write_text(text)
    print(
        json.dumps(
            {
                "report": str(args.output),
                "security_cases": len(security["cases"]),
                "network_boots": boot_count,
                "resume_byte_reduction_pct": reduction,
            }
        )
    )


if __name__ == "__main__":
    main()
